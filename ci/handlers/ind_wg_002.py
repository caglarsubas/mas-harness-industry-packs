#!/usr/bin/env python3
"""Closed IND-WG-002 data-readiness acceptance handler."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from planeon_industry_packs import __version__ as framework_version  # noqa: E402
from planeon_industry_packs.canonical import canonical_json_bytes  # noqa: E402
from planeon_industry_packs.index import build_index  # noqa: E402
from planeon_industry_packs.io import media_type  # noqa: E402
from planeon_industry_packs.loader import ValidatedPack, load_pack  # noqa: E402
from planeon_industry_packs.package import archive_bytes  # noqa: E402

PACK_ROOT = ROOT / "packs/white-goods"
COMMON_ROOT = ROOT / "common"
READINESS_FIXTURES = PACK_ROOT / "fixtures/readiness"

CONTRACT_BINDING = {
    "apiVersion": "harness.planeon.ai/data-contract-binding/v1alpha1",
    "kind": "DataContractBinding",
    "id": "white-goods.data.contract-binding",
    "stage": "data-readiness",
    "repository": "caglarsubas/mas-harness-contracts",
    "commit": "2146278a95344cd2a8e22596b2f315b46edffc88",
    "readinessSchema": {
        "path": "schemas/v1alpha1/readiness/data-readiness-assessment.schema.json",
        "sha256": "ffe003a1a7ec0773f49d8f394ac3dd6281114bd4335ff05c87d223412faf92a5",
    },
    "commonSchema": {
        "path": "schemas/v1alpha1/guidance/common.schema.json",
        "sha256": "4d77297073d4c2e559f1131fbada566b499197f87113f7e28b136f0b4ae5f429",
    },
    "historicalLockObservation": {
        "recordedPath": "schemas/v1alpha1/guidance/data-readiness-assessment.schema.json",
        "authoritativePath": "schemas/v1alpha1/readiness/data-readiness-assessment.schema.json",
        "contentDigestMatches": True,
        "status": "DOCUMENTED_NOT_CORRECTED",
    },
    "schemaBytesCopied": False,
}
READINESS_POLICY = {
    "apiVersion": "harness.planeon.ai/data-readiness-policy/v1alpha1",
    "kind": "DataReadinessPolicy",
    "id": "white-goods.data.readiness-policy",
    "stage": "data-readiness",
    "version": "0.2.0",
    "illustrative": True,
    "tenantReplacementRequired": True,
    "decisionPrecedence": ["FAIL", "WARN", "PASS"],
    "missingDataReasonCode": "MISSING_DATA",
    "metrics": {
        "completeness": {"passMinimum": "0.98", "warnMinimum": "0.95"},
        "freshnessMinutes": {"passMaximum": "15", "warnMaximum": "60"},
        "duplicateRate": {"passMaximum": "0.01", "warnMaximum": "0.02"},
        "classificationCoverage": {"passMinimum": "1.00", "warnMinimum": "0.98"},
        "provenanceCoverage": {"passMinimum": "1.00", "warnMinimum": "0.98"},
    },
}
READINESS_EVIDENCE = {
    "published": False,
    "deploymentEvidence": False,
    "runtimeEvidence": False,
    "assuranceEvidence": False,
    "tenantAcceptance": False,
}
QUESTION_CONTRACT = {
    "classified-observation-count": ("number", True, None, None),
    "data-classification-scope": ("string", True, None, None),
    "data-custodian-role": ("string", True, None, None),
    "data-owner-role": ("string", True, None, None),
    "data-readiness-evaluator-state": ("choice", True, False, ("pass", "warn", "fail")),
    "data-source-class-scope": ("choice", True, True, ("api", "postgresql", "files", "events")),
    "duplicate-observation-count": ("number", True, None, None),
    "expected-observation-count": ("number", True, None, None),
    "latest-observation-time": ("string", True, None, None),
    "nonnull-required-field-count": ("number", True, None, None),
    "provenanced-observation-count": ("number", True, None, None),
    "readiness-policy-evidence-refs": ("string", True, None, None),
    "source-evidence-refs": ("string", True, None, None),
    "synthetic-examples-confirmed": ("boolean", True, None, None),
    "tenant-readiness-policy-approved": ("boolean", True, None, None),
}
DATA_PATHS = (
    "data/api/service-observations.json",
    "data/events/telemetry.jsonl",
    "data/files/inspection-evidence.md",
    "data/postgresql/quality-observations.csv",
)
GATE_ORDER = (
    "business.owner",
    "business.outcome",
    "data.owner",
    "data.quality",
    "data.completeness",
    "data.freshness",
    "data.provenance",
    "data.classification",
    "integration.readiness",
    "autonomy.boundary",
)
GATE_IDS = frozenset(GATE_ORDER)
STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
FIXTURE_FIELDS = {
    "apiVersion",
    "kind",
    "id",
    "stage",
    "synthetic",
    "evaluationTime",
    "measurements",
    "expectedDecision",
    "evidence",
    "assessment",
}
MEASUREMENT_FIELDS = {
    "expectedObservationCount",
    "observedRecordCount",
    "nonnullRequiredFieldCount",
    "duplicateObservationCount",
    "classifiedObservationCount",
    "provenancedObservationCount",
    "latestObservationTime",
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json(pack: ValidatedPack, relative: str) -> dict[str, Any]:
    value = json.loads(pack.files[relative])
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {relative}")
    return value


def _data_questions(pack: ValidatedPack) -> dict[str, tuple[str, bool, bool | None, tuple[str, ...] | None]]:
    result: dict[str, tuple[str, bool, bool | None, tuple[str, ...] | None]] = {}
    resources = [item for item in pack.manifest["content"]["questionnaires"] if item["path"].startswith("questions/data/")]
    if [item["id"] for item in resources] != ["white-goods.data.readiness-evidence", "white-goods.data.sources"]:
        raise ValueError("data questionnaire inventory differs")
    for resource in resources:
        document = yaml.safe_load(pack.files[resource["path"]])
        if set(document) != {"apiVersion", "kind", "id", "stage", "title", "questions"}:
            raise ValueError(f"questionnaire fields differ: {resource['path']}")
        for question in document["questions"]:
            identifier = question["id"]
            if identifier in result:
                raise ValueError(f"duplicate data question: {identifier}")
            response_type = question["responseType"]
            multiple = question.get("multiple")
            choices = tuple(question["choices"]) if "choices" in question else None
            expected_fields = {"id", "prompt", "responseType", "required"}
            if response_type == "choice":
                expected_fields |= {"choices", "multiple"}
            if set(question) != expected_fields or not isinstance(question["prompt"], str) or not question["prompt"]:
                raise ValueError(f"data question is not closed: {identifier}")
            result[identifier] = (response_type, question["required"], multiple, choices)
    return result


def _record_count(path: str, data: bytes) -> int:
    if path.endswith(".json"):
        value = json.loads(data)
        records = value.get("records") if isinstance(value, dict) else None
        if not isinstance(records, list):
            raise ValueError(f"JSON data member has no records: {path}")
        return len(records)
    if path.endswith(".jsonl"):
        lines = [line for line in data.decode("utf-8").splitlines() if line]
        values = [json.loads(line) for line in lines]
        if not all(isinstance(item, dict) for item in values):
            raise ValueError(f"JSONL member is not object-only: {path}")
        return len(values)
    if path.endswith(".csv"):
        rows = list(csv.DictReader(data.decode("utf-8").splitlines()))
        if not rows or any(None in row for row in rows):
            raise ValueError(f"CSV member is malformed: {path}")
        return len(rows)
    if path.endswith(".md"):
        text = data.decode("utf-8")
        if "synthetic" not in text.casefold() or "white-goods.evidence.file-inspection" not in text:
            raise ValueError(f"document evidence is not synthetic and bound: {path}")
        return 1
    raise ValueError(f"unsupported locked data member: {path}")


def validate_dataset_lock(pack: ValidatedPack) -> dict[str, Any]:
    lock = _json(pack, "data/dataset.lock.json")
    if set(lock) != {"apiVersion", "kind", "id", "stage", "synthetic", "algorithm", "members"}:
        raise ValueError("dataset lock fields differ")
    if lock["synthetic"] is not True or lock["algorithm"] != "SHA-256":
        raise ValueError("dataset lock identity differs")
    members = lock["members"]
    if not isinstance(members, list) or [item.get("path") for item in members] != list(DATA_PATHS):
        raise ValueError("dataset lock members are not the exact sorted data surface")
    for item in members:
        if set(item) != {"path", "mediaType", "recordCount", "size", "sha256"}:
            raise ValueError(f"dataset member fields differ: {item.get('path')}")
        path = item["path"]
        data = pack.files[path]
        expected = {
            "path": path,
            "mediaType": media_type(path),
            "recordCount": _record_count(path, data),
            "size": len(data),
            "sha256": _sha256(data),
        }
        if item != expected:
            raise ValueError(f"dataset member binding differs: {path}")
    return lock


def validate_source_inventory(pack: ValidatedPack) -> dict[str, Any]:
    inventory = _json(pack, "fixtures/sources/source-inventory.json")
    if set(inventory) != {"apiVersion", "kind", "id", "stage", "synthetic", "sources"} or inventory["synthetic"] is not True:
        raise ValueError("source inventory fields differ")
    sources = inventory["sources"]
    if not isinstance(sources, list) or [item["sourceClass"] for item in sources] != ["api", "events", "files", "postgresql"]:
        raise ValueError("source classes differ")
    if [item["dataPath"] for item in sources] != list(DATA_PATHS):
        raise ValueError("source and dataset paths differ")
    for item in sources:
        if set(item) != {"id", "sourceClass", "ownerRole", "custodianRole", "classification", "dataPath", "evidenceIds"}:
            raise ValueError(f"source fields differ: {item.get('id')}")
        if item["ownerRole"] != "quality-owner" or item["custodianRole"] != "data-steward":
            raise ValueError(f"source ownership differs: {item['id']}")
        if item["classification"] != "internal-synthetic" or len(item["evidenceIds"]) != 1:
            raise ValueError(f"source evidence differs: {item['id']}")
        if not STABLE_ID.fullmatch(item["id"]) or not STABLE_ID.fullmatch(item["evidenceIds"][0]):
            raise ValueError(f"source identifiers are not stable: {item['id']}")
    return inventory


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("readiness time must be an explicit UTC value")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() is None:
        raise ValueError("readiness time lacks an offset")
    return parsed


def _minimum_state(value: Decimal, limits: dict[str, str]) -> str:
    if value >= Decimal(limits["passMinimum"]):
        return "PASS"
    if value >= Decimal(limits["warnMinimum"]):
        return "WARN"
    return "FAIL"


def _maximum_state(value: Decimal, limits: dict[str, str]) -> str:
    if value <= Decimal(limits["passMaximum"]):
        return "PASS"
    if value <= Decimal(limits["warnMaximum"]):
        return "WARN"
    return "FAIL"


def evaluate_measurements(measurements: dict[str, Any], evaluation_time: str, policy: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    if set(measurements) != MEASUREMENT_FIELDS:
        raise ValueError("measurement fields differ")
    count_fields = MEASUREMENT_FIELDS - {"latestObservationTime"}
    if any(isinstance(measurements[name], bool) or not isinstance(measurements[name], int) or measurements[name] < 0 for name in count_fields):
        raise ValueError("measurement counts must be non-negative integers")
    expected = measurements["expectedObservationCount"]
    observed = measurements["observedRecordCount"]
    if expected <= 0 or observed > expected:
        raise ValueError("observation counts exceed the closed evaluation scope")
    bounded = ("nonnullRequiredFieldCount", "duplicateObservationCount", "classifiedObservationCount", "provenancedObservationCount")
    if any(measurements[name] > observed for name in bounded):
        raise ValueError("derived counts exceed observed records")
    if observed == 0:
        if measurements["latestObservationTime"] is not None or any(measurements[name] != 0 for name in bounded):
            raise ValueError("missing-data measurement contains derived evidence")
        return {"status": "FAIL", "reasonCodes": [policy["missingDataReasonCode"]]}, {"missing": "FAIL"}

    latest = _parse_time(measurements["latestObservationTime"])
    evaluated = _parse_time(evaluation_time)
    if latest > evaluated:
        raise ValueError("latest observation is after evaluation time")
    freshness_minutes = Decimal(str((evaluated - latest).total_seconds())) / Decimal("60")
    metric_states = {
        "completeness": _minimum_state(Decimal(measurements["nonnullRequiredFieldCount"]) / Decimal(expected), policy["metrics"]["completeness"]),
        "freshness": _maximum_state(freshness_minutes, policy["metrics"]["freshnessMinutes"]),
        "duplicate": _maximum_state(Decimal(measurements["duplicateObservationCount"]) / Decimal(observed), policy["metrics"]["duplicateRate"]),
        "classification": _minimum_state(Decimal(measurements["classifiedObservationCount"]) / Decimal(observed), policy["metrics"]["classificationCoverage"]),
        "provenance": _minimum_state(Decimal(measurements["provenancedObservationCount"]) / Decimal(observed), policy["metrics"]["provenanceCoverage"]),
    }
    reason_codes: list[str] = []
    codes = {
        "completeness": {"WARN": "COMPLETENESS_NEEDS_INPUT", "FAIL": "INCOMPLETE_DATA"},
        "freshness": {"WARN": "FRESHNESS_NEEDS_INPUT", "FAIL": "STALE_DATA"},
        "duplicate": {"WARN": "DUPLICATE_RATE_NEEDS_INPUT", "FAIL": "DUPLICATE_DATA"},
        "classification": {"WARN": "CLASSIFICATION_NEEDS_INPUT", "FAIL": "UNCLASSIFIED_DATA"},
        "provenance": {"WARN": "PROVENANCE_NEEDS_INPUT", "FAIL": "UNPROVENANCED_DATA"},
    }
    for name, state in metric_states.items():
        if state != "PASS":
            reason_codes.append(codes[name][state])
    status = "FAIL" if "FAIL" in metric_states.values() else "WARN" if "WARN" in metric_states.values() else "PASS"
    return {"status": status, "reasonCodes": sorted(reason_codes)}, metric_states


def _gate(gate_id: str, state: str, reason: str, *, evidence: bool = True) -> dict[str, Any]:
    statuses = {"PASS": "PASS", "WARN": "NEEDS_INPUT", "FAIL": "BLOCKED", "NOT_APPLICABLE": "NOT_APPLICABLE"}
    evidence_ids = ["white-goods.evidence.synthetic-measurements"] if evidence else []
    return {"gateId": gate_id, "status": statuses[state], "evidenceIds": evidence_ids, "reasonCode": reason}


def build_assessment(fixture_id: str, decision: dict[str, Any], metric_states: dict[str, str]) -> dict[str, Any]:
    gates = [
        {"gateId": "business.owner", "status": "PASS", "evidenceIds": ["white-goods.evidence.business-owner"], "reasonCode": "evidence.satisfied"},
        {"gateId": "business.outcome", "status": "PASS", "evidenceIds": ["white-goods.evidence.business-outcome"], "reasonCode": "evidence.satisfied"},
        {"gateId": "data.owner", "status": "PASS", "evidenceIds": ["white-goods.evidence.data-owner"], "reasonCode": "evidence.satisfied"},
    ]
    if metric_states == {"missing": "FAIL"}:
        gates.append(_gate("data.quality", "FAIL", "data.missing", evidence=False))
        for gate_id in ("data.completeness", "data.freshness", "data.provenance", "data.classification"):
            gates.append(_gate(gate_id, "NOT_APPLICABLE", "data.no-observations", evidence=False))
    else:
        overall_state = decision["status"]
        if overall_state == "PASS":
            quality_reason = "evidence.satisfied"
        elif metric_states["duplicate"] != "PASS" and all(metric_states[name] == "PASS" for name in metric_states if name != "duplicate"):
            quality_reason = "data.duplicate-needs-input" if overall_state == "WARN" else "data.duplicate"
        else:
            quality_reason = "data.quality-needs-input" if overall_state == "WARN" else "data.quality-blocked"
        gates.append(_gate("data.quality", overall_state, quality_reason))
        gate_metrics = {
            "data.completeness": ("completeness", "data.completeness-needs-input", "data.incomplete"),
            "data.freshness": ("freshness", "data.freshness-needs-input", "data.stale"),
            "data.provenance": ("provenance", "data.provenance-needs-input", "data.unprovenanced"),
            "data.classification": ("classification", "data.classification-needs-input", "data.unclassified"),
        }
        for gate_id, (metric, warn_reason, fail_reason) in gate_metrics.items():
            state = metric_states[metric]
            reason = "evidence.satisfied" if state == "PASS" else warn_reason if state == "WARN" else fail_reason
            gates.append(_gate(gate_id, state, reason))
    gates.extend(
        [
            _gate("integration.readiness", "NOT_APPLICABLE", "scope.not-applicable", evidence=False),
            _gate("autonomy.boundary", "NOT_APPLICABLE", "scope.not-applicable", evidence=False),
        ]
    )
    missing = sorted(gate["gateId"] for gate in gates if gate["status"] in {"NEEDS_INPUT", "BLOCKED"})
    return {
        "apiVersion": "harness.planeon.ai/v1alpha1",
        "kind": "DataReadinessAssessment",
        "metadata": {"id": fixture_id, "version": "0.2.0"},
        "spec": {
            "questionnaireSessionId": "white-goods.session.synthetic-data-readiness",
            "overallStatus": "READY" if decision["status"] == "PASS" else "BLOCKED",
            "gateResults": gates,
            "missingGateIds": missing,
        },
    }


def validate_assessment_contract(value: dict[str, Any]) -> None:
    if set(value) != {"apiVersion", "kind", "metadata", "spec"}:
        raise ValueError("assessment fields differ")
    if value["apiVersion"] != "harness.planeon.ai/v1alpha1" or value["kind"] != "DataReadinessAssessment":
        raise ValueError("assessment identity differs")
    metadata = value["metadata"]
    if set(metadata) != {"id", "version"} or metadata["version"] != "0.2.0" or not STABLE_ID.fullmatch(metadata["id"]):
        raise ValueError("assessment metadata differs")
    spec = value["spec"]
    if set(spec) != {"questionnaireSessionId", "overallStatus", "gateResults", "missingGateIds"}:
        raise ValueError("assessment spec fields differ")
    if not STABLE_ID.fullmatch(spec["questionnaireSessionId"]) or spec["overallStatus"] not in {"READY", "BLOCKED"}:
        raise ValueError("assessment status or session differs")
    gates = spec["gateResults"]
    if not isinstance(gates, list) or [item.get("gateId") for item in gates] != list(GATE_ORDER):
        raise ValueError("assessment must contain the ten ordered gates")
    for gate in gates:
        if set(gate) != {"gateId", "status", "evidenceIds", "reasonCode"}:
            raise ValueError(f"gate fields differ: {gate.get('gateId')}")
        if gate["gateId"] not in GATE_IDS or gate["status"] not in {"PASS", "NEEDS_INPUT", "BLOCKED", "NOT_APPLICABLE"}:
            raise ValueError(f"gate status differs: {gate['gateId']}")
        if gate["evidenceIds"] != sorted(set(gate["evidenceIds"])) or any(not STABLE_ID.fullmatch(item) for item in gate["evidenceIds"]):
            raise ValueError(f"gate evidence differs: {gate['gateId']}")
        if not STABLE_ID.fullmatch(gate["reasonCode"]):
            raise ValueError(f"gate reason code differs: {gate['gateId']}")
    if spec["missingGateIds"] != sorted(set(spec["missingGateIds"])) or any(item not in GATE_IDS for item in spec["missingGateIds"]):
        raise ValueError("missing gate ids differ")
    expected_missing = sorted(item["gateId"] for item in gates if item["status"] in {"NEEDS_INPUT", "BLOCKED"})
    if spec["missingGateIds"] != expected_missing:
        raise ValueError("missing gate ids do not match non-pass gates")
    if (spec["overallStatus"] == "READY") != (not expected_missing):
        raise ValueError("assessment readiness contradicts gate results")


def evaluate_fixture(value: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if set(value) != FIXTURE_FIELDS:
        raise ValueError("readiness fixture fields differ")
    if value["apiVersion"] != "harness.planeon.ai/data-readiness-fixture/v1alpha1" or value["kind"] != "DataReadinessFixture":
        raise ValueError("readiness fixture identity differs")
    if value["stage"] != "data-readiness" or value["synthetic"] is not True or value["evidence"] != READINESS_EVIDENCE:
        raise ValueError("readiness fixture asserted unavailable evidence")
    decision, states = evaluate_measurements(value["measurements"], value["evaluationTime"], policy)
    if decision != value["expectedDecision"]:
        raise ValueError(f"declared decision differs: {value['id']}")
    expected_assessment = build_assessment(value["id"], decision, states)
    validate_assessment_contract(value["assessment"])
    if value["assessment"] != expected_assessment:
        raise ValueError(f"declared assessment differs: {value['id']}")
    return decision


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["white-goods"]:
        raise SystemExit("IND-WG-002 accepts only PACK=white-goods")
    if framework_version != "0.1.1":
        raise SystemExit(f"framework version differs: {framework_version}")

    pack = load_pack(PACK_ROOT, common_root=COMMON_ROOT)
    common = load_pack(COMMON_ROOT)
    if pack.manifest["metadata"]["version"] != "0.4.0" or pack.manifest["compatibility"]["frameworkVersion"] != "0.1.0":
        raise SystemExit("white-goods version or framework compatibility differs")
    if pack.files["contracts.lock.json"] != common.files["contracts.lock.json"] or pack.files["journey.yaml"] != common.files["journey.yaml"]:
        raise SystemExit("common predecessor files changed")
    if _sha256(pack.files["contracts.lock.json"]) != "81d7470e28b452cbf8de2e4903b47b5335709b09cf6375f78481057973d75c91":
        raise SystemExit("contracts lock digest differs")
    if _data_questions(pack) != QUESTION_CONTRACT:
        raise SystemExit("data questionnaire contract differs")
    if _json(pack, "data/contract-binding.json") != CONTRACT_BINDING:
        raise SystemExit("public readiness contract binding differs")
    policy = _json(pack, "data/readiness-policy.json")
    if policy != READINESS_POLICY:
        raise SystemExit("readiness policy differs")
    lock = validate_dataset_lock(pack)
    validate_source_inventory(pack)

    fixture_digests: dict[str, str] = {}
    for path in sorted(READINESS_FIXTURES.glob("*.json")):
        value = json.loads(path.read_bytes())
        evaluate_fixture(value, policy)
        fixture_digests[path.name] = _sha256(canonical_json_bytes(value))
    if set(fixture_digests) != {
        "fail-duplicate.json",
        "fail-missing.json",
        "fail-stale.json",
        "fail-unclassified.json",
        "fail-unprovenanced.json",
        "pass.json",
        "warn-freshness.json",
    }:
        raise SystemExit("readiness fixture inventory differs")

    first_index, second_index = build_index(PACK_ROOT), build_index(PACK_ROOT)
    first_archive, second_archive = archive_bytes(PACK_ROOT), archive_bytes(PACK_ROOT)
    if canonical_json_bytes(first_index) != canonical_json_bytes(second_index) or first_archive != second_archive:
        raise SystemExit("white-goods index or archive is not byte reproducible")
    if first_index["evidence"] != {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False}:
        raise SystemExit("pack index asserted unavailable evidence")
    if len(pack.files) != 64 or len(pack.resource_ids) != 61:
        raise SystemExit("white-goods file or resource inventory differs")

    print(
        canonical_json_bytes(
            {
                "archiveSha256": _sha256(first_archive[1]),
                "contractBindingSha256": _sha256(canonical_json_bytes(CONTRACT_BINDING)),
                "datasetLockSha256": _sha256(canonical_json_bytes(lock)),
                "evidence": READINESS_EVIDENCE,
                "fixtureDigests": fixture_digests,
                "frameworkVersion": framework_version,
                "indexSha256": _sha256(canonical_json_bytes(first_index)),
                "packDigest": pack.digest,
                "packVersion": pack.manifest["metadata"]["version"],
                "retainedArtifacts": False,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
