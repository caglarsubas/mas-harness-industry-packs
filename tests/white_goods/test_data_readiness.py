"""IND-WG-002 white-goods data-readiness acceptance tests."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ci.handlers.ind_wg_002 import (
    CONTRACT_BINDING,
    DATA_PATHS,
    GATE_ORDER,
    QUESTION_CONTRACT,
    READINESS_EVIDENCE,
    READINESS_POLICY,
    _data_questions,
    build_assessment,
    evaluate_fixture,
    evaluate_measurements,
    main,
    validate_assessment_contract,
    validate_dataset_lock,
    validate_source_inventory,
)
from planeon_industry_packs.canonical import canonical_json_bytes, sha256_bytes
from planeon_industry_packs.index import build_index
from planeon_industry_packs.loader import load_pack, validate_pack
from planeon_industry_packs.package import archive_bytes

COMMON = ROOT / "common"
PACK_ROOT = ROOT / "packs/white-goods"
FIXTURES = tuple(sorted((PACK_ROOT / "fixtures/readiness").glob("*.json")))


def _fixture(name: str) -> dict:
    return json.loads((PACK_ROOT / "fixtures/readiness" / name).read_text(encoding="utf-8"))


def test_sector_pack_advances_only_the_data_slice() -> None:
    report = validate_pack(PACK_ROOT, common_root=COMMON)
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    common = load_pack(COMMON)
    assert report.accepted and report.pack_version == "0.2.0"
    assert pack.manifest["compatibility"]["frameworkVersion"] == "0.1.0"
    assert pack.manifest["extends"]["packDigest"] == "3cfea19e6e0a4a653d63622e250f40001b4f8221ebab18fa5bfc1601b8eddea3"
    assert pack.files["contracts.lock.json"] == common.files["contracts.lock.json"]
    assert pack.files["journey.yaml"] == common.files["journey.yaml"]
    assert len(pack.files) == 32
    assert len(pack.resource_ids) == 29
    assert not (pack.resource_ids & common.resource_ids)


def test_data_questionnaires_are_typed_unique_and_closed() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    assert _data_questions(pack) == QUESTION_CONTRACT
    assert set(QUESTION_CONTRACT) == {
        "classified-observation-count",
        "data-classification-scope",
        "data-custodian-role",
        "data-owner-role",
        "data-readiness-evaluator-state",
        "data-source-class-scope",
        "duplicate-observation-count",
        "expected-observation-count",
        "latest-observation-time",
        "nonnull-required-field-count",
        "provenanced-observation-count",
        "readiness-policy-evidence-refs",
        "source-evidence-refs",
        "synthetic-examples-confirmed",
        "tenant-readiness-policy-approved",
    }


def test_public_contract_binding_and_illustrative_policy_are_exact() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    assert json.loads(pack.files["data/contract-binding.json"]) == CONTRACT_BINDING
    assert json.loads(pack.files["data/readiness-policy.json"]) == READINESS_POLICY
    assert CONTRACT_BINDING["schemaBytesCopied"] is False
    assert CONTRACT_BINDING["historicalLockObservation"] == {
        "recordedPath": "schemas/v1alpha1/guidance/data-readiness-assessment.schema.json",
        "authoritativePath": "schemas/v1alpha1/readiness/data-readiness-assessment.schema.json",
        "contentDigestMatches": True,
        "status": "DOCUMENTED_NOT_CORRECTED",
    }
    assert READINESS_POLICY["illustrative"] is True
    assert READINESS_POLICY["tenantReplacementRequired"] is True


def test_source_inventory_and_dataset_lock_bind_all_synthetic_members() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    inventory = validate_source_inventory(pack)
    lock = validate_dataset_lock(pack)
    assert [source["sourceClass"] for source in inventory["sources"]] == ["api", "events", "files", "postgresql"]
    assert [member["path"] for member in lock["members"]] == list(DATA_PATHS)
    assert all(source["classification"] == "internal-synthetic" for source in inventory["sources"])
    assert all(member["recordCount"] > 0 and len(member["sha256"]) == 64 for member in lock["members"])


def test_dataset_lock_detects_a_tampered_member() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    tampered = dict(pack.files)
    tampered[DATA_PATHS[0]] += b"\n"
    with pytest.raises(ValueError, match="dataset member binding differs"):
        validate_dataset_lock(replace(pack, files=tampered))


def test_readiness_vectors_are_deterministic_and_contract_shaped() -> None:
    policy = deepcopy(READINESS_POLICY)
    expected = {
        "fail-duplicate.json": {"status": "FAIL", "reasonCodes": ["DUPLICATE_DATA"]},
        "fail-missing.json": {"status": "FAIL", "reasonCodes": ["MISSING_DATA"]},
        "fail-stale.json": {"status": "FAIL", "reasonCodes": ["STALE_DATA"]},
        "fail-unclassified.json": {"status": "FAIL", "reasonCodes": ["UNCLASSIFIED_DATA"]},
        "fail-unprovenanced.json": {"status": "FAIL", "reasonCodes": ["UNPROVENANCED_DATA"]},
        "pass.json": {"status": "PASS", "reasonCodes": []},
        "warn-freshness.json": {"status": "WARN", "reasonCodes": ["FRESHNESS_NEEDS_INPUT"]},
    }
    for path in FIXTURES:
        value = json.loads(path.read_bytes())
        assert value["synthetic"] is True
        assert value["evidence"] == READINESS_EVIDENCE
        assert evaluate_fixture(value, policy) == expected[path.name]
        assert evaluate_fixture(json.loads(canonical_json_bytes(value)), policy) == expected[path.name]
        validate_assessment_contract(value["assessment"])
        assert [item["gateId"] for item in value["assessment"]["spec"]["gateResults"]] == list(GATE_ORDER)


def test_warn_and_fail_never_advance_readiness() -> None:
    for path in FIXTURES:
        value = json.loads(path.read_bytes())
        decision = evaluate_fixture(value, READINESS_POLICY)
        assessment = value["assessment"]["spec"]
        assert (assessment["overallStatus"] == "READY") == (decision["status"] == "PASS")
        if decision["status"] != "PASS":
            assert assessment["overallStatus"] == "BLOCKED"
            assert assessment["missingGateIds"]


def test_missing_data_suppresses_derived_metric_findings() -> None:
    value = _fixture("fail-missing.json")
    decision, states = evaluate_measurements(value["measurements"], value["evaluationTime"], READINESS_POLICY)
    assert decision == {"status": "FAIL", "reasonCodes": ["MISSING_DATA"]}
    assert states == {"missing": "FAIL"}
    assessment = build_assessment(value["id"], decision, states)
    metric_gates = assessment["spec"]["gateResults"][4:8]
    assert all(item["status"] == "NOT_APPLICABLE" for item in metric_gates)
    assert assessment["spec"]["missingGateIds"] == ["data.quality"]


def test_threshold_boundaries_use_decimal_safe_precedence() -> None:
    base = _fixture("pass.json")
    measurements = base["measurements"]
    evaluated_at = base["evaluationTime"]

    warn_complete = deepcopy(measurements)
    warn_complete["nonnullRequiredFieldCount"] = 95
    assert evaluate_measurements(warn_complete, evaluated_at, READINESS_POLICY)[0] == {
        "status": "WARN",
        "reasonCodes": ["COMPLETENESS_NEEDS_INPUT"],
    }
    fail_complete = deepcopy(measurements)
    fail_complete["nonnullRequiredFieldCount"] = 94
    assert evaluate_measurements(fail_complete, evaluated_at, READINESS_POLICY)[0] == {
        "status": "FAIL",
        "reasonCodes": ["INCOMPLETE_DATA"],
    }
    warn_duplicate = deepcopy(measurements)
    warn_duplicate["duplicateObservationCount"] = 2
    assert evaluate_measurements(warn_duplicate, evaluated_at, READINESS_POLICY)[0]["status"] == "WARN"
    fail_duplicate = deepcopy(measurements)
    fail_duplicate["duplicateObservationCount"] = 3
    assert evaluate_measurements(fail_duplicate, evaluated_at, READINESS_POLICY)[0]["reasonCodes"] == ["DUPLICATE_DATA"]
    warn_classification = deepcopy(measurements)
    warn_classification["classifiedObservationCount"] = 98
    assert evaluate_measurements(warn_classification, evaluated_at, READINESS_POLICY)[0]["status"] == "WARN"
    fail_provenance = deepcopy(measurements)
    fail_provenance["provenancedObservationCount"] = 97
    assert evaluate_measurements(fail_provenance, evaluated_at, READINESS_POLICY)[0]["reasonCodes"] == ["UNPROVENANCED_DATA"]


def test_invalid_measurement_counts_and_future_time_fail_closed() -> None:
    value = _fixture("pass.json")
    invalid = deepcopy(value["measurements"])
    invalid["duplicateObservationCount"] = 101
    with pytest.raises(ValueError, match="derived counts exceed"):
        evaluate_measurements(invalid, value["evaluationTime"], READINESS_POLICY)
    future = deepcopy(value["measurements"])
    future["latestObservationTime"] = "2026-01-15T12:01:00Z"
    with pytest.raises(ValueError, match="after evaluation time"):
        evaluate_measurements(future, value["evaluationTime"], READINESS_POLICY)


def test_fixture_canonical_digests_are_stable_per_two_reads() -> None:
    first = {path.name: sha256_bytes(canonical_json_bytes(json.loads(path.read_bytes()))) for path in FIXTURES}
    second = {path.name: sha256_bytes(canonical_json_bytes(json.loads(path.read_bytes()))) for path in FIXTURES}
    assert first == second
    assert len(first) == 7 and all(len(digest) == 64 for digest in first.values())


def test_sector_index_archive_and_handler_are_reproducible(capsys: pytest.CaptureFixture[str]) -> None:
    first_index, second_index = build_index(PACK_ROOT), build_index(PACK_ROOT)
    first_archive, second_archive = archive_bytes(PACK_ROOT), archive_bytes(PACK_ROOT)
    assert canonical_json_bytes(first_index) == canonical_json_bytes(second_index)
    assert first_archive == second_archive
    assert first_archive[0] == "white-goods.manufacturing-0.2.0.tar.gz"
    assert main(["white-goods"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["packVersion"] == "0.2.0"
    assert output["frameworkVersion"] == "0.1.1"
    assert output["evidence"] == READINESS_EVIDENCE
    assert output["retainedArtifacts"] is False
    with pytest.raises(SystemExit, match="accepts only PACK=white-goods"):
        main(["another-pack"])
