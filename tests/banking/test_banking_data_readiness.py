"""IND-BANK-002 banking data-readiness acceptance tests."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from planeon_industry_packs.loader import load_pack

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common"
PACK_ROOT = ROOT / "packs/banking"

# The packet handler is loaded by file location (no package import, no sys.path edit here).
_SPEC = importlib.util.spec_from_file_location("ind_bank_002_handler", ROOT / "ci/handlers/ind_bank_002.py")
assert _SPEC and _SPEC.loader
HANDLER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(HANDLER)

FILES_SENTENCE = (
    "Synthetic product terms and policy text written for this pack; not an institution document. "
    "Each tenant replaces it with its own approved sources."
)
LABEL = "illustrative, tenant-overridable"
GATES = (
    "business.owner", "business.outcome", "data.owner", "data.quality", "data.completeness",
    "data.freshness", "data.provenance", "data.classification", "integration.readiness", "autonomy.boundary",
)
NO_OBSERVATIONS = {gate: ("NOT_APPLICABLE", "data.no-observations") for gate in ("data.completeness", "data.freshness", "data.provenance", "data.classification")}
# DESIGN 4.4 table: class, decision, reason codes, non-PASS gates (status, reason), missingGateIds.
VECTORS = {
    "pass.json": ("events", "PASS", [], {}, []),
    "warn-freshness.json": (
        "events", "WARN", ["FRESHNESS_NEEDS_INPUT"],
        {"data.quality": ("NEEDS_INPUT", "data.quality-needs-input"), "data.freshness": ("NEEDS_INPUT", "data.freshness-needs-input")},
        ["data.freshness", "data.quality"],
    ),
    "fail-missing.json": (
        "postgresql", "FAIL", ["MISSING_DATA"], {"data.quality": ("BLOCKED", "data.missing"), **NO_OBSERVATIONS}, ["data.quality"],
    ),
    "fail-stale.json": (
        "events", "FAIL", ["STALE_DATA"],
        {"data.quality": ("BLOCKED", "data.quality-blocked"), "data.freshness": ("BLOCKED", "data.stale")},
        ["data.freshness", "data.quality"],
    ),
    "fail-duplicate.json": ("events", "FAIL", ["DUPLICATE_DATA"], {"data.quality": ("BLOCKED", "data.duplicate")}, ["data.quality"]),
    "fail-unclassified.json": (
        "postgresql", "FAIL", ["UNCLASSIFIED_DATA"],
        {"data.quality": ("BLOCKED", "data.quality-blocked"), "data.classification": ("BLOCKED", "data.unclassified")},
        ["data.classification", "data.quality"],
    ),
    "fail-unprovenanced.json": (
        "files", "FAIL", ["UNPROVENANCED_DATA"],
        {"data.quality": ("BLOCKED", "data.quality-blocked"), "data.provenance": ("BLOCKED", "data.unprovenanced")},
        ["data.provenance", "data.quality"],
    ),
    "fail-reconciliation.json": (
        "postgresql", "FAIL", ["DATA_RECONCILIATION_MISMATCH"], {"data.quality": ("BLOCKED", "data.reconciliation-mismatch")}, ["data.quality"],
    ),
    "fail-disallowed-data.json": (
        "api", "FAIL", ["PERSONAL_DATA_FORBIDDEN"],
        {"data.quality": ("BLOCKED", "data.quality-blocked"), "data.classification": ("BLOCKED", "data.personal-data-forbidden")},
        ["data.classification", "data.quality"],
    ),
}
# DESIGN 4.3 band table (PASS / WARN), illustrative only.
BAND_TABLE = {
    "events": {"completeness": ("0.99", "0.97"), "freshnessMinutes": ("5", "15"), "duplicateRate": ("0.000", "0.005"), "classificationCoverage": ("1.00", "0.99"), "provenanceCoverage": ("1.00", "0.99")},
    "postgresql": {"completeness": ("1.00", "0.99"), "freshnessMinutes": ("1440", "2880"), "duplicateRate": ("0.000", "0.001"), "classificationCoverage": ("1.00", "0.99"), "provenanceCoverage": ("1.00", "0.99")},
    "api": {"completeness": ("0.98", "0.95"), "freshnessMinutes": ("60", "240"), "duplicateRate": ("0.01", "0.02"), "classificationCoverage": ("1.00", "0.98"), "provenanceCoverage": ("1.00", "0.98")},
    "files": {"completeness": ("0.95", "0.90"), "freshnessMinutes": ("10080", "43200"), "duplicateRate": ("0.02", "0.05"), "classificationCoverage": ("1.00", "0.98"), "provenanceCoverage": ("1.00", "0.99")},
}


def _pack():
    return load_pack(PACK_ROOT, common_root=COMMON)


def _json(relative: str) -> dict:
    return json.loads((PACK_ROOT / relative).read_text(encoding="utf-8"))


def _sources(pack=None) -> dict:
    pack = pack or _pack()
    return HANDLER.check_source_inventory(json.loads(pack.files["fixtures/sources/source-inventory.json"]), pack.files["ontology/banking.ttl"].decode("utf-8"))


def _independent_luhn(digits: str) -> bool:
    total = 0
    for position, character in enumerate(reversed(digits)):
        value = int(character) * (2 if position % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def test_handler_accepts_only_banking_and_reports_closed_evidence(capsys: pytest.CaptureFixture[str]) -> None:
    assert HANDLER.main(["banking"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["packVersion"] == "0.2.0"
    assert output["frameworkVersion"] == "0.1.1"
    assert output["retainedArtifacts"] is False
    assert output["scannerModule"] == "ind_bank_001_handler"
    assert set(output["evidence"].values()) == {False}
    assert {name: decision["status"] for name, decision in output["decisions"].items()} == {name: row[1] for name, row in VECTORS.items()}
    with pytest.raises(SystemExit, match="accepts only PACK=banking"):
        HANDLER.main(["white-goods"])


def test_scanner_reuse_takes_exactly_three_predecessor_functions() -> None:
    assert HANDLER.SCANNER_NAMES == ("find_disallowed", "luhn_valid", "find_disallowed_raw")
    for name in HANDLER.SCANNER_NAMES:
        assert getattr(HANDLER, name).__module__ == "ind_bank_001_handler"


def test_every_vector_matches_the_design_table_and_the_ten_gate_contract() -> None:
    pack = _pack()
    sources = _sources(pack)
    names = sorted(path.name for path in (PACK_ROOT / "fixtures/readiness").glob("*.json"))
    assert names == sorted(VECTORS)
    for name, (source_class, status, codes, non_pass, missing) in VECTORS.items():
        value = _json(f"fixtures/readiness/{name}")
        assert value["sourceClass"] == source_class
        assert value["expectedDecision"] == {"status": status, "reasonCodes": codes}
        assert set(value["evidence"].values()) == {False}
        spec = value["assessment"]["spec"]
        assert [gate["gateId"] for gate in spec["gateResults"]] == list(GATES)
        for gate in spec["gateResults"]:
            if gate["gateId"] in non_pass:
                assert (gate["status"], gate["reasonCode"]) == non_pass[gate["gateId"]]
            elif gate["gateId"] in ("integration.readiness", "autonomy.boundary"):
                assert (gate["status"], gate["reasonCode"], gate["evidenceIds"]) == ("NOT_APPLICABLE", "scope.not-applicable", [])
            else:
                assert (gate["status"], gate["reasonCode"]) == ("PASS", "evidence.satisfied")
        assert spec["missingGateIds"] == missing
        assert spec["overallStatus"] == ("READY" if status == "PASS" else "BLOCKED")
        assert HANDLER.check_fixture(name, value, sources, pack.files) == {"status": status, "reasonCodes": codes}


def test_missing_data_suppresses_banking_codes_and_override_keeps_metric_evidence() -> None:
    pack = _pack()
    sources = _sources(pack)
    missing = _json("fixtures/readiness/fail-missing.json")
    missing["reconciliation"]["unresolvedHolderCount"] = 1
    missing["mutation"] = copy.deepcopy(_json("fixtures/readiness/fail-disallowed-data.json")["mutation"])
    missing["sourceClass"] = "api"
    decision, detail = HANDLER.evaluate_fixture(missing, sources, pack.files)
    assert decision == {"status": "FAIL", "reasonCodes": ["MISSING_DATA"]} and detail is None
    classification = next(gate for gate in _json("fixtures/readiness/fail-missing.json")["assessment"]["spec"]["gateResults"] if gate["gateId"] == "data.classification")
    assert classification["status"] == "NOT_APPLICABLE"
    gates = {gate["gateId"]: gate for gate in _json("fixtures/readiness/fail-disallowed-data.json")["assessment"]["spec"]["gateResults"]}
    assert gates["data.classification"]["evidenceIds"] == gates["data.completeness"]["evidenceIds"] != []


def test_disallowed_data_mutation_is_built_at_run_time() -> None:
    pack = _pack()
    sources = _sources(pack)
    value = HANDLER.build_luhn_run()
    assert len(value) == 16 and value.isdigit() and _independent_luhn(value)
    assert value not in (PACK_ROOT / "fixtures/readiness/fail-disallowed-data.json").read_text(encoding="utf-8")
    vector = _json("fixtures/readiness/fail-disallowed-data.json")
    assert HANDLER.apply_mutation(vector["mutation"], sources["api"], pack.files) == [value]
    unmutated = copy.deepcopy(vector)
    unmutated["mutation"] = None
    assert HANDLER.evaluate_fixture(unmutated, sources, pack.files)[0] == {"status": "PASS", "reasonCodes": []}
    for field, replacement, message in (("builder", "typed-literal", "not closed"), ("member", "data/files/product-terms.md", "undeclared member")):
        broken = copy.deepcopy(vector["mutation"])
        broken[field] = replacement
        with pytest.raises(ValueError, match=message):
            HANDLER.apply_mutation(broken, sources["api"], pack.files)


def test_literal_rule_and_strict_scan_hold_for_every_data_member() -> None:
    pack = _pack()
    HANDLER.check_data_members(pack.files)
    for path in HANDLER.DATA_PATHS:
        text = pack.files[path].decode("utf-8")
        assert HANDLER.literal_runs(text) == [] and HANDLER.find_disallowed(text) == []
    thirteen = "".join(str((3 * index + 1) % 10) for index in range(13))
    assert HANDLER.literal_runs(f"id {thirteen} end") == [thirteen]
    hyphenated = "-".join(thirteen[index:index + 4] for index in range(0, 13, 4))
    spaced = " ".join(thirteen[index:index + 4] for index in range(0, 13, 4))
    assert HANDLER.literal_runs(hyphenated) == [hyphenated] and HANDLER.literal_runs(spaced) == [spaced]
    assert HANDLER.literal_runs(thirteen[:12]) == []
    assert HANDLER.literal_runs("2026-01-15T11:40:00Z") == []


def test_committed_members_reconcile_and_a_dangling_reference_is_counted() -> None:
    pack = _pack()
    records = HANDLER.check_dataset_lock(_json("data/dataset.lock.json"), pack.files)
    assert HANDLER.reconciliation_counts(records) == {"unresolvedHolderCount": 0, "unresolvedEventAccountCount": 0}
    dangling = copy.deepcopy(records)
    dangling["data/postgresql/accounts.csv"][0]["holder_party_id"] = "party-" + "9" * 4
    dangling["data/events/transactions.jsonl"][0]["accountId"] = "acct-" + "9" * 4
    assert HANDLER.reconciliation_counts(dangling) == {"unresolvedHolderCount": 1, "unresolvedEventAccountCount": 1}
    assert _json("fixtures/readiness/fail-reconciliation.json")["reconciliation"] == {"unresolvedHolderCount": 1, "unresolvedEventAccountCount": 0}


def test_tampered_byte_count_path_or_classification_is_refused() -> None:
    pack = _pack()
    lock = _json("data/dataset.lock.json")
    path = "data/postgresql/parties.csv"
    data = pack.files[path]
    tampered = dict(pack.files)
    tampered[path] = data[:-2] + bytes([data[-2] ^ 1]) + data[-1:]
    with pytest.raises(ValueError, match="digest differs"):
        HANDLER.check_dataset_lock(lock, tampered)
    counted = copy.deepcopy(lock)
    counted["members"][0]["recordCount"] += 1
    with pytest.raises(ValueError, match="record count differs"):
        HANDLER.check_dataset_lock(counted, pack.files)
    moved = copy.deepcopy(lock)
    moved["members"][0]["path"] = "data/api/other-catalogue.json"
    with pytest.raises(ValueError, match="member paths differ"):
        HANDLER.check_dataset_lock(moved, pack.files)
    typed = copy.deepcopy(lock)
    typed["members"][0]["mediaType"] = "text/plain"
    with pytest.raises(ValueError, match="media type differs"):
        HANDLER.check_dataset_lock(typed, pack.files)
    inventory = json.loads(pack.files["fixtures/sources/source-inventory.json"])
    inventory["sources"][3]["classification"] = "internal-synthetic"
    with pytest.raises(ValueError, match="classification differs"):
        HANDLER.check_source_inventory(inventory, pack.files["ontology/banking.ttl"].decode("utf-8"))


def test_gate_outside_the_ten_or_reordered_is_refused() -> None:
    assessment = _json("fixtures/readiness/pass.json")["assessment"]
    HANDLER.check_assessment_contract(assessment)
    extra = copy.deepcopy(assessment)
    extra["spec"]["gateResults"].append({"gateId": "data.lineage", "status": "PASS", "evidenceIds": [], "reasonCode": "evidence.satisfied"})
    with pytest.raises(ValueError, match="outside the ten"):
        HANDLER.check_assessment_contract(extra)
    reordered = copy.deepcopy(assessment)
    gates = reordered["spec"]["gateResults"]
    gates[3], gates[4] = gates[4], gates[3]
    with pytest.raises(ValueError, match="ten ordered"):
        HANDLER.check_assessment_contract(reordered)
    shortened = copy.deepcopy(assessment)
    shortened["spec"]["gateResults"].pop()
    with pytest.raises(ValueError, match="ten ordered"):
        HANDLER.check_assessment_contract(shortened)


def test_policy_bands_class_labels_and_files_sentence() -> None:
    policy = _json("data/readiness-policy.json")
    HANDLER.check_policy(policy)
    assert policy["illustrative"] is True and policy["tenantReplacementRequired"] is True
    assert policy["decisionPrecedence"] == ["FAIL", "WARN", "PASS"] and policy["missingDataReasonCode"] == "MISSING_DATA"
    assert set(policy["sourceClasses"]) == set(BAND_TABLE)
    for name, bands in BAND_TABLE.items():
        entry = policy["sourceClasses"][name]
        assert entry["label"] == LABEL
        for metric, (first, second) in bands.items():
            assert tuple(entry["metrics"][metric].values()) == (first, second)
    relabelled = copy.deepcopy(policy)
    relabelled["sourceClasses"]["files"]["label"] = "production"
    with pytest.raises(ValueError, match="readiness policy differs"):
        HANDLER.check_policy(relabelled)
    files_source = next(item for item in _json("fixtures/sources/source-inventory.json")["sources"] if item["sourceClass"] == "files")
    assert files_source["description"] == FILES_SENTENCE
    assert FILES_SENTENCE in (PACK_ROOT / "questions/data/sources.yaml").read_text(encoding="utf-8")
    assert FILES_SENTENCE in (ROOT / "docs/banking/data-readiness.md").read_text(encoding="utf-8")
    assert FILES_SENTENCE in (PACK_ROOT / "data/files/product-terms.md").read_text(encoding="utf-8")


def test_data_questions_are_closed_and_source_classes_exact() -> None:
    pack = _pack()
    prompts = HANDLER.check_data_questionnaires(pack)
    assert prompts
    assert HANDLER.QUESTION_CONTRACT["banking.data.sources"]["data-source-class-scope"][3] == ("api", "postgresql", "events", "files")
    assert HANDLER.QUESTION_CONTRACT["banking.data.sources"]["data-owner-role"][3] == HANDLER.ROLE_IDS


def test_contract_binding_names_the_repository_only() -> None:
    pack = _pack()
    binding = _json("data/contract-binding.json")
    lock = json.loads(pack.files["contracts.lock.json"])
    HANDLER.check_contract_binding(binding, lock, pack)
    assert binding["repository"] == "mas-harness-contracts" and "/" not in binding["repository"]
    assert binding["historicalLockObservation"]["status"] == "DOCUMENTED_NOT_CORRECTED" and binding["schemaBytesCopied"] is False
    for key, replacement in (("repository", "other-contracts"), ("commit", "0" * 40)):
        changed = copy.deepcopy(binding)
        changed[key] = replacement
        with pytest.raises(ValueError, match="binding differs"):
            HANDLER.check_contract_binding(changed, lock, pack)
    other = copy.deepcopy(lock)
    other["repository"] = "example/other-contracts"
    with pytest.raises(ValueError, match="suffix differs"):
        HANDLER.check_contract_binding(binding, other, pack)


def test_packet_owned_files_pass_the_raw_scan() -> None:
    for relative in HANDLER.PACKET_OWNED_FILES:
        assert HANDLER.find_disallowed_raw((ROOT / relative).read_text(encoding="utf-8")) == []
