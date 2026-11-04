"""IND-BANK-001 banking business-domain acceptance tests."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from pyshacl import validate as shacl_validate
from rdflib import Graph, Namespace, RDF
from rdflib.namespace import OWL

from planeon_industry_packs.canonical import canonical_json_bytes, sha256_bytes
from planeon_industry_packs.errors import PackValidationError
from planeon_industry_packs.index import build_index
from planeon_industry_packs.loader import load_pack, validate_pack
from planeon_industry_packs.package import archive_bytes
from planeon_industry_packs.rules import validate_static_data

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common"
PACK_ROOT = ROOT / "packs/banking"
BANK = Namespace("urn:planeon:banking:")
SH = Namespace("http://www.w3.org/ns/shacl#")
QUESTIONNAIRES = tuple(sorted((PACK_ROOT / "questions/business").glob("*.yaml")))
ANSWERS = tuple(sorted((PACK_ROOT / "fixtures/answers").glob("*.json")))
SEMANTIC_FILES = ("ontology/banking.ttl", "ontology/banking.shacl.ttl", "fixtures/answers/ontology-valid.ttl", "fixtures/answers/ontology-invalid.ttl")

# The packet handler is loaded by file location (no package import, no sys.path edit here).
_SPEC = importlib.util.spec_from_file_location("ind_bank_001_handler", ROOT / "ci/handlers/ind_bank_001.py")
assert _SPEC and _SPEC.loader
HANDLER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(HANDLER)


def _questions() -> dict:
    return HANDLER.questionnaire_contract(load_pack(PACK_ROOT, common_root=COMMON))[0]


def _vector(name: str) -> dict:
    return json.loads((PACK_ROOT / "fixtures/answers" / name).read_text(encoding="utf-8"))


def _shacl(fixture: str) -> tuple[bool, Graph]:
    conforms, report, _ = shacl_validate(
        HANDLER.load_graph(PACK_ROOT / "ontology/banking.ttl", PACK_ROOT / "fixtures/answers" / fixture),
        shacl_graph=HANDLER.load_graph(PACK_ROOT / "ontology/banking.shacl.ttl"),
        inference="none",
        advanced=False,
        js=False,
        do_owl_imports=False,
    )
    assert isinstance(report, Graph)
    return bool(conforms), report


def _luhn_pair() -> tuple[str, str]:
    """Return a Luhn-valid and a Luhn-invalid 16-digit string, built from arithmetic at run time."""
    body = "".join(str((7 * index + 3) % 10) for index in range(15))
    check = next(digit for digit in range(10) if HANDLER.luhn_valid(body + str(digit)))
    return body + str(check), body + str((check + 1) % 10)


def _iban_pair() -> tuple[str, str]:
    """Return a mod-97-valid and a mod-97-invalid IBAN shape with the unassigned country code XX, built at run time."""
    country = "X" * 2
    bban = "".join(str((3 * index + 1) % 10) for index in range(16))
    numeric = int("".join(str(int(character, 36)) for character in bban + country + "0" * 2))
    check = 98 - numeric % 97
    wrong = check + 1 if check < 98 else check - 1
    return f"{country}{check:02d}{bban}", f"{country}{wrong:02d}{bban}"


def test_sector_pack_is_closed_and_pinned_to_exact_common_foundation() -> None:
    report = validate_pack(PACK_ROOT, common_root=COMMON)
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    common = load_pack(COMMON)
    assert report.accepted
    assert report.pack_id == "banking.financial-services"
    assert report.pack_version == "0.2.0"
    assert report.evidence == HANDLER.EVIDENCE
    assert pack.manifest["metadata"]["industry"] == "banking"
    assert pack.manifest["metadata"]["packKind"] == "SECTOR"
    assert pack.manifest["metadata"]["license"] == "Apache-2.0"
    assert pack.manifest["compatibility"]["frameworkVersion"] == "0.1.0"
    assert pack.manifest["overlayMode"] == "APPEND_ONLY"
    assert pack.manifest["extends"] == {
        "id": "common.foundation",
        "version": "1.0.0",
        "packDigest": "3cfea19e6e0a4a653d63622e250f40001b4f8221ebab18fa5bfc1601b8eddea3",
    }
    for empty in ("controls", "providerPreferences"):
        assert pack.manifest["content"][empty] == []
    assert [item["id"] for item in pack.manifest["content"]["rules"]] == ["banking.data.block-unready"]
    assert [item["id"] for item in pack.manifest["content"]["readiness"]] == [
        "banking.data.contract-binding", "banking.data.dataset-lock", "banking.data.readiness-policy",
    ]
    assert pack.files["contracts.lock.json"] == common.files["contracts.lock.json"]
    assert pack.files["journey.yaml"] == common.files["journey.yaml"]
    assert len(pack.files) == 38
    assert len(pack.resource_ids) == 35
    assert not (pack.resource_ids & common.resource_ids)


def test_questionnaire_contract_is_typed_unique_and_mutually_closed() -> None:
    questions = _questions()
    assert set(questions) == {
        "acceptance-outcome", "business-owner-role", "channel-scope", "compliance-owner-role",
        "data-steward-role", "deferred-institution-specific-choices", "domain-owner-role",
        "evidence-approver-role", "institution-specific-claims", "kpi-scope", "outcome-evidence-refs",
        "pilot-decision-scope", "primary-business-objective", "product-family-scope", "risk-owner-role",
        "role-separation-confirmed", "tenant-evidence-verified", "unacceptable-outcome",
    }
    assert questions["product-family-scope"]["multiple"] is True
    assert questions["pilot-decision-scope"]["choices"] == ["information-only", "human-reviewed-recommendation", "automated-decision-out-of-pilot-scope"]
    assert set(questions["deferred-institution-specific-choices"]["choices"]) == {
        "institution-identity", "jurisdiction", "licence-type", "risk-appetite", "observation-window", "regulatory-applicability",
    }
    for path in QUESTIONNAIRES:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert set(document) == {"apiVersion", "kind", "id", "stage", "title", "questions"}
        for question in document["questions"]:
            assert question["responseType"] in {"string", "boolean", "number", "choice"}
            assert isinstance(question["required"], bool)
            if question["responseType"] != "choice":
                assert "choices" not in question and "multiple" not in question


def test_questionnaire_choices_bind_to_ontology_stable_ids_and_glossary_is_complete() -> None:
    graph = HANDLER.load_graph(PACK_ROOT / "ontology/banking.ttl")
    questions = _questions()
    for question, class_name in HANDLER.CHOICE_BINDINGS.items():
        assert set(questions[question]["choices"]) == HANDLER.stable_ids(graph, class_name)
    terms = HANDLER.check_glossary(graph, questions)
    classes = set(graph.subjects(RDF.type, OWL.Class))
    assert len(classes) == 27
    assert terms == 79
    alignments = {str(value) for value in graph.objects(None, BANK.alignsWithStandard)}
    assert alignments and alignments <= HANDLER.ALIGNMENT_LITERALS


def test_ontology_accountability_is_exactly_one_role_per_objective_kpi_and_outcome() -> None:
    graph = HANDLER.load_graph(PACK_ROOT / "ontology/banking.ttl")
    roles = set(graph.subjects(RDF.type, BANK.AccountableRole))
    assert len(roles) == 6
    for class_name, expected in {"BusinessObjective": 6, "KeyPerformanceIndicator": 6, "AcceptanceOutcome": 3}.items():
        subjects = set(graph.subjects(RDF.type, BANK[class_name]))
        assert len(subjects) == expected
        for subject in subjects:
            owners = set(graph.objects(subject, BANK.accountableRole))
            assert len(owners) == 1 and owners <= roles


def test_semantic_files_have_no_import_remote_iri_or_execution_surface() -> None:
    for relative in SEMANTIC_FILES:
        text = (PACK_ROOT / relative).read_text(encoding="utf-8")
        validate_static_data(text, path=relative)
        for forbidden in ("owl:imports", "sh:sparql", "sh:js", "skos"):
            assert forbidden not in text.casefold()
        HANDLER.check_graph_surface(HANDLER.load_graph(PACK_ROOT / relative), relative)
    with pytest.raises(PackValidationError, match="NETWORK_TARGET_FORBIDDEN"):
        validate_static_data("@prefix remote: <https://example.invalid/remote#> .", path="ontology/remote.ttl")
    remote = Graph()
    remote.parse(data="<urn:planeon:banking:A> <urn:planeon:banking:b> <urn:other:c> .", format="turtle")
    with pytest.raises(ValueError, match="outside the admitted namespaces"):
        HANDLER.check_graph_surface(remote, "inline")


def test_local_shacl_positive_conforms_and_negative_fails_closed_constraints() -> None:
    positive, _ = _shacl("ontology-valid.ttl")
    negative, report = _shacl("ontology-invalid.ttl")
    assert positive and not negative
    components = set(report.objects(None, SH.sourceConstraintComponent))
    assert {SH.MinCountConstraintComponent, SH.InConstraintComponent, SH.OrConstraintComponent} <= components
    assert {BANK.dimension, BANK.targetDirection, BANK.accountableRole, BANK.evidenceClass, BANK.provenance} <= set(report.objects(None, SH.resultPath))
    assert set(report.objects(None, SH.focusNode)) == {BANK.SyntheticIncompleteKpi}


def test_answer_vectors_are_canonical_synthetic_and_deterministic() -> None:
    questions = _questions()
    expected = {
        "accepted-pilot.json": {"status": "READY", "reasonCodes": []},
        "decision-scope-deferred.json": {"status": "BLOCKED", "reasonCodes": ["DECISION_SCOPE_REQUIRES_GOVERNANCE_STAGE"]},
        "incomplete-outcome-evidence.json": {"status": "BLOCKED", "reasonCodes": ["INCOMPLETE_OUTCOME_EVIDENCE"]},
        "missing-owner.json": {"status": "BLOCKED", "reasonCodes": ["MISSING_ACCOUNTABLE_OWNER"]},
        "personal-data-in-answer.json": {"status": "BLOCKED", "reasonCodes": ["PERSONAL_DATA_FORBIDDEN"]},
        "role-separation-unconfirmed.json": {"status": "BLOCKED", "reasonCodes": ["ROLE_SEPARATION_UNCONFIRMED"]},
        "unverified-institution-claim.json": {"status": "BLOCKED", "reasonCodes": ["UNVERIFIED_INSTITUTION_SPECIFIC_CHOICE"]},
    }
    assert {path.name for path in ANSWERS} == set(expected)
    for path in ANSWERS:
        raw = path.read_bytes()
        value = json.loads(raw)
        assert raw == canonical_json_bytes(value) + b"\n"
        assert value["synthetic"] is True
        assert value["evidence"] == HANDLER.EVIDENCE
        assert HANDLER.evaluate_answer_set(value, questions) == expected[path.name]


def test_answer_vector_canonical_digests_are_frozen() -> None:
    assert {path.name: sha256_bytes(canonical_json_bytes(json.loads(path.read_bytes()))) for path in ANSWERS} == {
        "accepted-pilot.json": "a439272389b05c7375f422e00c03ac01fd73adfa0036747f0b8fef5d4082ac9c",
        "decision-scope-deferred.json": "0ab5ea4b6de1ee781d9b6e7609b10785b5dedf96ebd75ac37f015ce14b393aed",
        "incomplete-outcome-evidence.json": "ba7b5ca267b54cf3df91f718d09c3e3b65542e6deafd008e1b2ba534001076b7",
        "missing-owner.json": "4ddd04839a9ab8fabaf3feb0f86bc58ddddc4b6f6b8eb211fcbbfa4045be6357",
        "personal-data-in-answer.json": "287b170b796f56fefcf195f591dd02b0fdb6c59139da3107157e75aaf24e5e44",
        "role-separation-unconfirmed.json": "9ddddce86711d37d0a27c56a1219cbf88e5ca063d6356b8a081e37484498bc4e",
        "unverified-institution-claim.json": "9298d4993d40a4e83d38cd537b4ed66b06fa28cf83ec898591d6848b779d8f14",
    }


def test_unknown_missing_or_mistyped_answer_keys_are_refused_not_blocked() -> None:
    questions = _questions()
    unknown = _vector("accepted-pilot.json")
    unknown["answers"]["undeclared-question"] = "value"
    missing = _vector("accepted-pilot.json")
    del missing["answers"]["risk-owner-role"]
    mistyped = _vector("accepted-pilot.json")
    mistyped["answers"]["role-separation-confirmed"] = "yes"
    outside = _vector("accepted-pilot.json")
    outside["answers"]["channel-scope"] = ["telegraph"]
    cross_empty = _vector("accepted-pilot.json")
    cross_empty["answers"]["role-separation-confirmed"] = ""
    cross_empty_choice = _vector("accepted-pilot.json")
    cross_empty_choice["answers"]["channel-scope"] = ""
    cases = ((unknown, "answer keys"), (missing, "answer keys"), (mistyped, "boolean answer"), (outside, "outside closed set"),
             (cross_empty, "boolean answer"), (cross_empty_choice, "choice answer type"))
    for value, message in cases:
        with pytest.raises(ValueError, match=message):
            HANDLER.evaluate_answer_set(value, questions)


def test_disallowed_data_detection_uses_run_time_values() -> None:
    luhn_valid, luhn_invalid = _luhn_pair()
    iban_valid, iban_invalid = _iban_pair()
    assert HANDLER.find_disallowed(f"ref {luhn_valid} end") == [luhn_valid]
    grouped = " ".join(luhn_valid[index:index + 4] for index in range(0, 16, 4))
    assert HANDLER.find_disallowed(grouped) == [grouped]
    assert HANDLER.find_disallowed(f"ref {iban_valid} end") == [iban_valid]
    assert HANDLER.find_disallowed(luhn_invalid) == []
    assert HANDLER.find_disallowed(iban_invalid) == []
    assert HANDLER.find_disallowed("synthetic-evidence:banking-business-domain-v1") == []
    questions = _questions()
    for detected in (luhn_valid, iban_valid):
        value = _vector("accepted-pilot.json")
        value["answers"]["unacceptable-outcome"] = f"Synthetic text with {detected} inside."
        value["expectedDecision"] = {"status": "BLOCKED", "reasonCodes": ["PERSONAL_DATA_FORBIDDEN"]}
        assert HANDLER.evaluate_answer_set(value, questions)["reasonCodes"] == ["PERSONAL_DATA_FORBIDDEN"]
    for undetected in (luhn_invalid, iban_invalid):
        value = _vector("accepted-pilot.json")
        value["answers"]["unacceptable-outcome"] = f"Synthetic text with {undetected} inside."
        assert HANDLER.evaluate_answer_set(value, questions) == {"status": "READY", "reasonCodes": []}
    pinned = _vector("personal-data-in-answer.json")["answers"]["outcome-evidence-refs"]
    assert pinned == HANDLER.PINNED_VALUE and HANDLER.find_disallowed(pinned) == [pinned]


def test_every_vector_keeps_institution_specific_choices_deferred() -> None:
    choices = set(_questions()["deferred-institution-specific-choices"]["choices"])
    for path in ANSWERS:
        assert set(json.loads(path.read_bytes())["answers"]["deferred-institution-specific-choices"]) == choices


def test_decision_with_changed_expectation_is_refused() -> None:
    value = copy.deepcopy(_vector("accepted-pilot.json"))
    value["expectedDecision"] = {"status": "BLOCKED", "reasonCodes": ["MISSING_ACCOUNTABLE_OWNER"]}
    with pytest.raises(ValueError, match="decisions differ"):
        HANDLER.evaluate_answer_set(value, _questions())


def test_sector_index_and_archive_are_byte_reproducible() -> None:
    first_index, second_index = build_index(PACK_ROOT), build_index(PACK_ROOT)
    first_archive, second_archive = archive_bytes(PACK_ROOT), archive_bytes(PACK_ROOT)
    assert canonical_json_bytes(first_index) == canonical_json_bytes(second_index)
    assert first_archive == second_archive
    assert first_index["evidence"] == HANDLER.EVIDENCE
    assert first_archive[0] == "banking.financial-services-0.2.0.tar.gz"


def test_packet_handler_accepts_only_the_closed_banking_target(capsys: pytest.CaptureFixture[str]) -> None:
    assert HANDLER.main(["banking"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["dependencyVersions"] == {"pyshacl": "0.40.1", "rdflib": "7.6.0"}
    assert output["frameworkVersion"] == "0.1.1"
    assert output["retainedArtifacts"] is False
    assert output["disallowedDataFindings"] == [["fixtures/answers/personal-data-in-answer.json", "outcome-evidence-refs"]]
    with pytest.raises(SystemExit, match="accepts only PACK=banking"):
        HANDLER.main(["white-goods"])


def _hex_letters(count: int) -> str:
    return "".join("abcdef"[(3 * index + 1) % 6] for index in range(count))


def _hex_token_around(length: int, run: str) -> str:
    """A lowercase hexadecimal token of exactly `length` characters whose only digits are `run`, delimited by hex letters."""
    return "e" + run + "f" + _hex_letters(length - len(run) - 2)


def test_raw_scan_finds_runs_glued_to_words_and_ignores_only_standalone_digest_tokens() -> None:
    luhn_valid, _ = _luhn_pair()
    # (a) a run glued directly to a word is still found by the raw scan.
    for prefix in ("ref", "id", "code"):
        assert HANDLER.find_disallowed_raw(f"{prefix}{luhn_valid}") == [luhn_valid]
    # (b) inside a standalone lowercase 40- or 64-character token: ignored by the raw scan, found by the strict scan.
    for length in (40, 64):
        token = _hex_token_around(length, luhn_valid)
        assert len(token) == length
        for text in (f"digest {token} end", f'"{token}"', f"`{token}`"):
            assert HANDLER.find_disallowed_raw(text) == []
            assert HANDLER.find_disallowed(text) == [luhn_valid]
    # (c) a non-hex letter glued to either end means the token is not a standalone digest.
    token = _hex_token_around(64, luhn_valid)
    for text in (f"g{token}", f"{token}Z"):
        assert luhn_valid in HANDLER.find_disallowed_raw(text)
    # (d) no uppercase exemption.
    assert luhn_valid in HANDLER.find_disallowed_raw(f" {token.upper()} ")


def test_raw_scan_reports_grouped_runs_that_straddle_a_digest_token() -> None:
    luhn_valid, _ = _luhn_pair()
    groups = [luhn_valid[index:index + 4] for index in range(0, 16, 4)]
    grouped = " ".join(groups)
    # (e) the last group is the first characters of a standalone 64-hex token, followed there by each hex letter.
    for letter in "abcdef":
        token = groups[3] + letter + _hex_letters(59)
        assert len(token) == 64
        assert HANDLER.find_disallowed_raw(f"{groups[0]} {groups[1]} {groups[2]} {token}") == [grouped]
    # (e, mirror) the first group is the tail of a standalone 64-hex token.
    token = _hex_letters(60) + groups[0]
    assert len(token) == 64
    assert HANDLER.find_disallowed_raw(f"{token} {groups[1]} {groups[2]} {groups[3]}") == [grouped]


def test_raw_scan_exempts_only_exact_digest_lengths() -> None:
    luhn_valid, luhn_invalid = _luhn_pair()
    # (f) a bare space-delimited run is found, and so is a run inside a 39-, 41-, 63- or 65-character token.
    assert HANDLER.find_disallowed_raw(f"value {luhn_valid} end") == [luhn_valid]
    assert HANDLER.find_disallowed_raw(f"value {luhn_invalid} end") == []
    for length in (39, 41, 63, 65):
        token = _hex_token_around(length, luhn_valid)
        assert len(token) == length
        assert HANDLER.find_disallowed_raw(f" {token} ") == [luhn_valid]


def test_optional_null_business_answer_keeps_the_decision() -> None:
    questions = _questions()
    for name in ("accepted-pilot.json", "missing-owner.json"):
        value = _vector(name)
        expected = HANDLER.evaluate_answer_set(copy.deepcopy(value), questions)
        value["answers"]["institution-specific-claims"] = None
        assert HANDLER.evaluate_answer_set(value, questions) == expected


def test_cross_type_empty_business_answers_are_refused() -> None:
    questions = _questions()
    cases = (
        ("primary-business-objective", "", "outside closed set"),
        ("tenant-evidence-verified", [], "boolean answer"),
        ("institution-specific-claims", [], "string answer"),
    )
    for key, empty, message in cases:
        value = _vector("accepted-pilot.json")
        value["answers"][key] = empty
        with pytest.raises(ValueError, match=message):
            HANDLER.evaluate_answer_set(value, questions)


def test_undeclared_non_business_questionnaire_is_still_refused() -> None:
    import dataclasses

    pack = load_pack(PACK_ROOT, common_root=COMMON)
    manifest = copy.deepcopy(pack.manifest)
    manifest["content"]["questionnaires"].append({"id": "banking.data.undeclared", "stage": "data-readiness", "path": "questions/data/undeclared.yaml"})
    with pytest.raises(ValueError, match="questionnaire outside the business stage"):
        HANDLER.questionnaire_contract(dataclasses.replace(pack, manifest=manifest))
