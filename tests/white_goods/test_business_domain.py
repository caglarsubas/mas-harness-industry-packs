"""IND-WG-001 white-goods business-domain acceptance tests."""

from __future__ import annotations

import email.parser
import email.policy
import json
import sys
import zipfile
from pathlib import Path

import pytest
import yaml
from pyshacl import validate as shacl_validate
from rdflib import Graph, Namespace, RDF

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ci.handlers.ind_wg_001 import EVIDENCE, _questionnaire_contract, evaluate_answer_set, main
from planeon_industry_packs import build_backend
from planeon_industry_packs.canonical import canonical_json_bytes, sha256_bytes
from planeon_industry_packs.errors import PackValidationError
from planeon_industry_packs.index import build_index
from planeon_industry_packs.loader import load_pack, validate_pack
from planeon_industry_packs.package import archive_bytes
from planeon_industry_packs.rules import validate_static_data

COMMON = ROOT / "common"
PACK_ROOT = ROOT / "packs/white-goods"
WG = Namespace("urn:planeon:white-goods:")
SH = Namespace("http://www.w3.org/ns/shacl#")
QUESTIONNAIRES = tuple(sorted((PACK_ROOT / "questions/business").glob("*.yaml")))
ANSWERS = tuple(sorted((PACK_ROOT / "fixtures/answers").glob("*.json")))


def _graph(*relative_paths: str) -> Graph:
    graph = Graph()
    for relative in relative_paths:
        graph.parse(PACK_ROOT / relative, format="turtle", publicID="urn:planeon:explicit-local-graph:")
    return graph


def _shacl(fixture: str) -> tuple[bool, Graph]:
    conforms, report, _ = shacl_validate(
        _graph("ontology/white-goods.ttl", f"fixtures/answers/{fixture}"),
        shacl_graph=_graph("ontology/white-goods.shacl.ttl"),
        inference="none",
        advanced=False,
        js=False,
        do_owl_imports=False,
    )
    assert isinstance(report, Graph)
    return bool(conforms), report


def test_sector_pack_is_closed_and_pinned_to_exact_common_foundation() -> None:
    report = validate_pack(PACK_ROOT, common_root=COMMON)
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    common = load_pack(COMMON)
    assert report.accepted
    assert report.pack_id == "white-goods.manufacturing"
    assert report.pack_version == "0.3.0"
    assert report.evidence == EVIDENCE
    assert pack.manifest["overlayMode"] == "APPEND_ONLY"
    assert pack.manifest["extends"] == {
        "id": "common.foundation",
        "version": "1.0.0",
        "packDigest": "3cfea19e6e0a4a653d63622e250f40001b4f8221ebab18fa5bfc1601b8eddea3",
    }
    assert pack.files["contracts.lock.json"] == common.files["contracts.lock.json"]
    assert pack.files["journey.yaml"] == common.files["journey.yaml"]
    assert len(pack.files) == 52
    assert len(pack.resource_ids) == 49
    assert not (pack.resource_ids & common.resource_ids)


def test_questionnaire_contract_is_typed_unique_and_mutually_closed() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    questions = _questionnaire_contract(pack)
    expected = {
        "acceptance-outcome",
        "business-owner-role",
        "ctq-scope",
        "data-steward-role",
        "decision-boundary",
        "deferred-plant-specific-choices",
        "domain-owner-role",
        "evidence-approver-role",
        "kpi-scope",
        "manufacturing-process-scope",
        "outcome-evidence-refs",
        "plant-specific-claims",
        "primary-business-objective",
        "product-family-scope",
        "quality-owner-role",
        "role-separation-confirmed",
        "tenant-evidence-verified",
        "unacceptable-outcome",
    }
    assert set(questions) == expected
    for path in QUESTIONNAIRES:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert set(document) == {"apiVersion", "kind", "id", "stage", "title", "questions"}
        for question in document["questions"]:
            assert question["responseType"] in {"string", "boolean", "number", "choice"}
            assert isinstance(question["required"], bool)
            if question["responseType"] == "choice":
                assert question["multiple"] in {True, False}
                assert question["choices"] and len(question["choices"]) == len(set(question["choices"]))
            else:
                assert "choices" not in question and "multiple" not in question


def test_questionnaire_choices_bind_to_ontology_stable_ids() -> None:
    graph = _graph("ontology/white-goods.ttl")
    questions = _questionnaire_contract(load_pack(PACK_ROOT, common_root=COMMON))

    def stable_ids(class_name: str) -> set[str]:
        return {str(value) for subject in graph.subjects(RDF.type, WG[class_name]) for value in graph.objects(subject, WG.stableId)}

    assert set(questions["primary-business-objective"]["choices"]) == stable_ids("BusinessObjective")
    assert set(questions["product-family-scope"]["choices"]) == stable_ids("ProductFamily")
    assert set(questions["manufacturing-process-scope"]["choices"]) == stable_ids("ProcessStep")
    assert set(questions["ctq-scope"]["choices"]) == stable_ids("CriticalToQuality")
    assert set(questions["kpi-scope"]["choices"]) == stable_ids("KeyPerformanceIndicator")
    assert set(questions["acceptance-outcome"]["choices"]) == stable_ids("AcceptanceOutcome")


def test_ontology_covers_the_closed_business_domain_and_accountability() -> None:
    graph = _graph("ontology/white-goods.ttl")
    required_classes = {
        "BusinessObjective",
        "AccountableRole",
        "ProductFamily",
        "ProductModel",
        "ManufacturingProcess",
        "ProcessStep",
        "QualityCharacteristic",
        "CriticalToQuality",
        "KeyPerformanceIndicator",
        "AcceptanceOutcome",
    }
    assert all((WG[name], RDF.type, Namespace("http://www.w3.org/2002/07/owl#").Class) in graph for name in required_classes)
    for class_name, expected_count in {
        "BusinessObjective": 5,
        "AccountableRole": 5,
        "ProductFamily": 4,
        "ProcessStep": 6,
        "CriticalToQuality": 6,
        "KeyPerformanceIndicator": 5,
        "AcceptanceOutcome": 3,
    }.items():
        assert len(set(graph.subjects(RDF.type, WG[class_name]))) == expected_count
    accountable = set(graph.subjects(RDF.type, WG.AccountableRole))
    for class_name in ("BusinessObjective", "CriticalToQuality", "KeyPerformanceIndicator"):
        for subject in graph.subjects(RDF.type, WG[class_name]):
            owners = set(graph.objects(subject, WG.accountableRole))
            assert len(owners) == 1 and owners <= accountable


def test_semantic_files_have_no_import_or_remote_execution_surface() -> None:
    for relative in ("ontology/white-goods.ttl", "ontology/white-goods.shacl.ttl", "fixtures/answers/ontology-valid.ttl", "fixtures/answers/ontology-invalid.ttl"):
        text = (PACK_ROOT / relative).read_text(encoding="utf-8")
        validate_static_data(text, path=relative)
        assert "owl:imports" not in text
        assert "sh:sparql" not in text
        assert "sh:js" not in text
    with pytest.raises(PackValidationError, match="NETWORK_TARGET_FORBIDDEN"):
        validate_static_data("@prefix remote: <https://example.invalid/remote#> .", path="ontology/remote.ttl")


def test_local_shacl_positive_conforms_and_negative_fails_closed_constraints() -> None:
    positive, positive_report = _shacl("ontology-valid.ttl")
    negative, negative_report = _shacl("ontology-invalid.ttl")
    assert positive and not negative
    assert len(positive_report) > 0
    assert (None, SH.sourceConstraintComponent, SH.MinCountConstraintComponent) in negative_report
    result_paths = set(negative_report.objects(None, SH.resultPath))
    assert {WG.numeratorDefinition, WG.denominatorDefinition, WG.dimension, WG.targetDirection, WG.accountableRole} <= result_paths


def test_answer_vectors_are_canonical_synthetic_and_deterministic() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    questions = _questionnaire_contract(pack)
    expected = {
        "accepted-pilot.json": {"status": "READY", "reasonCodes": []},
        "incomplete-outcome-evidence.json": {"status": "BLOCKED", "reasonCodes": ["INCOMPLETE_OUTCOME_EVIDENCE"]},
        "missing-owner.json": {"status": "BLOCKED", "reasonCodes": ["MISSING_ACCOUNTABLE_OWNER"]},
        "unverified-plant-claim.json": {"status": "BLOCKED", "reasonCodes": ["UNVERIFIED_PLANT_SPECIFIC_CHOICE"]},
    }
    for path in ANSWERS:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["synthetic"] is True
        assert value["evidence"] == EVIDENCE
        assert value["deferredPlantSpecificChoices"]
        assert evaluate_answer_set(value, questions) == expected[path.name]
        assert evaluate_answer_set(json.loads(canonical_json_bytes(value)), questions) == expected[path.name]


def test_answer_vector_canonical_digests_are_frozen() -> None:
    assert {
        path.name: sha256_bytes(canonical_json_bytes(json.loads(path.read_bytes())))
        for path in ANSWERS
    } == {
        "accepted-pilot.json": "59bb698424cbcf23f7d48e4e5ac8ac3eda0a789439958034d3b4769e1131994a",
        "incomplete-outcome-evidence.json": "67a9d4fe4d0e4907a2b62a60707f065e74a6cf14ca00dd56ccc10f74b88d7645",
        "missing-owner.json": "5d893ef2e963bd1f317ee981525092d154b541a74b2d83c8dc1fa5dcccc5aa7d",
        "unverified-plant-claim.json": "f7b4abf5a835d88a305dd4e36a480b1a8ce5087905188f93e887b6fd0ccd2acf",
    }


def test_sector_index_and_archive_are_byte_reproducible() -> None:
    first_index, second_index = build_index(PACK_ROOT), build_index(PACK_ROOT)
    first_archive, second_archive = archive_bytes(PACK_ROOT), archive_bytes(PACK_ROOT)
    assert canonical_json_bytes(first_index) == canonical_json_bytes(second_index)
    assert first_archive == second_archive
    assert first_index["evidence"] == EVIDENCE
    assert first_index["packDigest"] == load_pack(PACK_ROOT).digest
    assert first_archive[0] == "white-goods.manufacturing-0.3.0.tar.gz"


def test_framework_0_1_1_wheel_keeps_runtime_dependencies_closed(tmp_path: Path) -> None:
    wheel_path = tmp_path / build_backend.build_wheel(str(tmp_path))
    with zipfile.ZipFile(wheel_path) as wheel:
        metadata_name = next(name for name in wheel.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = email.parser.BytesParser(policy=email.policy.default).parsebytes(wheel.read(metadata_name))
    assert metadata["Version"] == "0.1.1"
    assert sorted(metadata.get_all("Requires-Dist")) == ["PyYAML==6.0.2", "jsonschema==4.24.0"]


def test_packet_handler_accepts_only_the_closed_white_goods_target(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["white-goods"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["dependencyVersions"] == {
        "pyshacl": "0.40.1",
        "rdflib": "7.6.0",
    }
    assert output["frameworkVersion"] == "0.1.1"
    assert output["retainedArtifacts"] is False
    with pytest.raises(SystemExit, match="accepts only PACK=white-goods"):
        main(["another-pack"])
