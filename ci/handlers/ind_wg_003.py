#!/usr/bin/env python3
"""Closed IND-WG-003 governance and integration acceptance handler."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from planeon_industry_packs import __version__ as framework_version  # noqa: E402
from planeon_industry_packs.canonical import canonical_json_bytes  # noqa: E402
from planeon_industry_packs.index import build_index  # noqa: E402
from planeon_industry_packs.loader import ValidatedPack, load_pack  # noqa: E402
from planeon_industry_packs.package import archive_bytes  # noqa: E402

PACK_ROOT = ROOT / "packs/white-goods"
COMMON_ROOT = ROOT / "common"
GOVERNANCE_FIXTURES = PACK_ROOT / "fixtures/governance"

STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
REASON_CODE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

PREDECESSOR_BINDING = {
    "commit": "a4d3df9b169e95c285e22a2fdb2b4c9d711230e2",
    "packDigest": "e0ad15c9da5f126c4aa20c88f75d4e9b15808ee841347ba4663dd99664248177",
    "packYamlSha256": "3bc885342cd43870624a1a188851af2aa314ec333ba87cb8170597f7b3d8f674",
    "frameworkWheelSha256": "d34a1a3c523b1e60f10602fff072d5dbf83f46f2220f29a4f13b9a31facf91f4",
}
CONTRACT_BINDING = {
    "apiVersion": "harness.planeon.ai/industry-governance-contract-binding/v1alpha1",
    "kind": "IndustryGovernanceContractBinding",
    "id": "white-goods.governance.contract-binding",
    "stage": "governance-and-regulation",
    "repository": "caglarsubas/mas-harness-contracts",
    "commit": "2146278a95344cd2a8e22596b2f315b46edffc88",
    "releaseManifestSha256": "c5dd4c39d1c69d07f8d8de3d1a09584bb906172fee2d5ac20ad25ff344b0db79",
    "approvalRequestSchema": {
        "path": "schemas/v1alpha1/lifecycle/approval-request.schema.json",
        "sha256": "4fe8d214a920690008a4390919acebf797b0ab4e6c649a7a88e0882f3b2a1b27",
        "status": "AVAILABLE",
    },
    "lifecycleCommonSchema": {
        "path": "schemas/v1alpha1/lifecycle/common.schema.json",
        "sha256": "dce5d8030eea3a19694511eb26513614dcc720ef4e0d650772131b14ed58f075",
    },
    "compositionCommonSchema": {
        "path": "schemas/v1alpha1/composition/common.schema.json",
        "sha256": "11b55d3eafa8d87a90956345da0919f67478a7738d5ca118025904f8ff58b5f0",
    },
    "unavailablePublicKinds": [
        {"kindName": "ControlRequirement", "status": "NOT_AVAILABLE_IN_BOUND_RELEASE"},
        {"kindName": "IntegrationDeclaration", "status": "NOT_AVAILABLE_IN_BOUND_RELEASE"},
    ],
    "packLocalDataKinds": [
        "IndustryControlRequirementRecordSet",
        "IndustryIntegrationDeclarationRecordSet",
    ],
    "schemaBytesCopied": False,
    "publicConformanceClaimed": False,
}
WAIVER_POLICY = {
    "apiVersion": "harness.planeon.ai/industry-waiver-policy/v1alpha1",
    "kind": "IndustryWaiverPolicy",
    "id": "white-goods.governance.waiver-policy",
    "stage": "governance-and-regulation",
    "illustrative": True,
    "tenantReplacementRequired": True,
    "requiredFields": [
        "controlId",
        "scopeId",
        "approvalRequest",
        "justificationEvidenceIds",
        "compensatingControlId",
        "expiresAt",
        "renewable",
    ],
    "approvalType": "WAIVER",
    "sameControlRequired": True,
    "sameCompleteScopeRequired": True,
    "compensatingControlRequired": True,
    "unexpiredApprovalRequired": True,
    "renewable": False,
    "waiverEffect": "DOCUMENT_EXCEPTION_ONLY_PROMOTION_REMAINS_BLOCKED",
    "waiverSatisfiesPromotion": False,
    "requiredPromotionEvidence": "FRESH_PASS_FOR_EVERY_REQUIRED_CONTROL",
}
GOVERNANCE_RULE = {
    "apiVersion": "harness.planeon.ai/pack-rule/v1alpha1",
    "kind": "PackRule",
    "id": "white-goods.governance.block-unsafe-action",
    "stage": "governance-and-regulation",
    "when": {
        "all": [
            {
                "in": [
                    "answers.action-category",
                    ["REVERSIBLE_WRITE", "IRREVERSIBLE_WRITE", "UNKNOWN_SIDE_EFFECT"],
                ]
            },
            {"eq": ["answers.governance-evidence-complete", False]},
        ]
    },
    "action": {
        "type": "BLOCK_READINESS",
        "target": "white-goods.governance.write-evidence",
        "message": "Write-capable or unknown-side-effect demand requires complete tenant governance evidence.",
    },
}
GOVERNANCE_EVIDENCE = {
    "source": False,
    "candidate": False,
    "ci": False,
    "merge": False,
    "artifact": False,
    "published": False,
    "deployment": False,
    "runtime": False,
    "assurance": False,
    "tenantAcceptance": False,
}

PREDECESSOR_FILE_DIGESTS = {
    "contracts.lock.json": "81d7470e28b452cbf8de2e4903b47b5335709b09cf6375f78481057973d75c91",
    "data/api/service-observations.json": "36ed7fe18c4f6e723de3deb1e8be441311bc0210f1d2bd830b38a799ef7e5ee5",
    "data/contract-binding.json": "d0f9a1ce1635a2ec35fe44b2e16061bc43ec5615ed4d16e481a456918af7783c",
    "data/dataset.lock.json": "80e43a1167dcabe9ba60af5871ace462a777fb0c72d0026220a792dea3ec2a11",
    "data/events/telemetry.jsonl": "d480858dd46eab179b9a06deda1ab69c140aca3cb1ad65504aeece70a3784e24",
    "data/files/inspection-evidence.md": "b3fd732ccb1ae30e775f1425dc0aae660ea88bc486bbf3d55dcaf1388f4ae3b1",
    "data/postgresql/quality-observations.csv": "e4bf5abfdc5d51692740382b957c30a053e9648d9d1c4e5674ff0c4f46a2637b",
    "data/readiness-policy.json": "7b496afdd8cd9749bf261ba4752e474a8062d54368b735a6c2553090db107c59",
    "fixtures/answers/accepted-pilot.json": "b76421c1f0cfa258c97f159a48f0f8f53782ec6415384b9fed3acc57119da052",
    "fixtures/answers/incomplete-outcome-evidence.json": "7c575020bb396a098cbcfc148b54db5657084642243994dfdabed5097dda1c6d",
    "fixtures/answers/missing-owner.json": "f0e9d2e862998a3b2d711e5d84dae467dd327416857cce66f8ab4b56a18325ad",
    "fixtures/answers/ontology-invalid.ttl": "f659112808bf9ccd9dd5a4efc7425a30dfeb61cde27c7f8644760918611431e2",
    "fixtures/answers/ontology-valid.ttl": "e8b5d7244788360432f119361db7f07ad40bd8ac8a7848e7f70f7bd7d94b3b67",
    "fixtures/answers/unverified-plant-claim.json": "096ba203960461488fc0326102582781414682d02cd57e41f2a4948c3a24d443",
    "fixtures/readiness/fail-duplicate.json": "384fe15132b77dbb38c70fefd9c7c777fe5554d6435c5918baef2a8bd8773ecc",
    "fixtures/readiness/fail-missing.json": "a1fa4538cddd12112693bcad9fce3de2c7714f338ab8cbd79489aa69cdecea4d",
    "fixtures/readiness/fail-stale.json": "596d2cddc2fdad71a773acdd77f24743e66289e05ed6aa93067d8eb38a7358ff",
    "fixtures/readiness/fail-unclassified.json": "6d7d50052b5db98b0f4cd47c24490d5129718fe6152c870e79cac0578e23b32d",
    "fixtures/readiness/fail-unprovenanced.json": "0524c87aa1da35e4fb9ecc2881bff4a4b6d8822930d201275ad6b58879c01711",
    "fixtures/readiness/pass.json": "9f91f09cdd33d37d94cf4d92f340fa9445bbd0bc376a4abc5e13ddccbdad329f",
    "fixtures/readiness/warn-freshness.json": "0d57ce6f10cd4040d08861ea9293ee98d25c4e740daed868ad579019b7b24fff",
    "fixtures/sources/source-inventory.json": "863a362490b64b91fa725e8de8a268d2b4863c37d1f25dda8e853980861b6e72",
    "journey.yaml": "950a6d21c68a35117a3cd36d67491cde85274ef911d78ff8585e1be8671db2fb",
    "ontology/white-goods.shacl.ttl": "aaca9fb6b50e205aee3d93ab0ec520fa4ef6482652b27a1b15f5b765b65410b0",
    "ontology/white-goods.ttl": "ff512027f26c2a61522086d7c0ea854194d1631325dcd1007ed3803bb4262310",
    "questions/business/acceptance.yaml": "2c0f6e48d4e2f270549c004bcf5478b5c12b3cdfc1720f6cda9984f64705e7f9",
    "questions/business/objectives.yaml": "72ffc9d09a703951d71e33af834ea61c1992141ffd2159acd01aea9da995a58a",
    "questions/business/roles.yaml": "1ed3be96b5a42ae59b503486c99306ba23835536b38d1ed7a4881a088beb7065",
    "questions/data/readiness.yaml": "0ac059d0dd1f02cd84484d2708b730618706001133d9912a1b38d9425026d8b3",
    "questions/data/sources.yaml": "d45829a0ca9e691679503de56bb247b2b7dde4849c478f47cf4a68ba7223eebd",
    "rules/data-readiness.json": "d363e816562a9099e18febe98585553fc7a62ed462c5c9bfcb8a8aa2337e390f",
}

QUESTION_CONTRACT = {
    "governance-applicability-owner-role": ("string", True, None, None),
    "jurisdiction-market-scope": ("string", True, None, None),
    "governance-applicability-themes": (
        "choice",
        True,
        True,
        ("product-safety", "data-protection", "cybersecurity", "quality-management", "environmental-energy"),
    ),
    "governance-applicability-evidence-refs": ("string", True, None, None),
    "tenant-authority-review-complete": ("boolean", True, None, None),
    "action-category": (
        "choice",
        True,
        False,
        ("READ_ONLY", "REVERSIBLE_WRITE", "IRREVERSIBLE_WRITE", "UNKNOWN_SIDE_EFFECT"),
    ),
    "autonomy-level": (
        "choice",
        True,
        False,
        ("OBSERVE", "RECOMMEND", "APPROVAL_REQUIRED", "BOUNDED_AUTONOMOUS"),
    ),
    "accountable-operator-role": ("string", True, None, None),
    "policy-reference-id": ("string", False, None, None),
    "mutation-approval-reference-id": ("string", False, None, None),
    "approval-separation-required": ("boolean", True, None, None),
    "required-approval-quorum": ("number", True, None, None),
    "durable-receipt-requirement-id": ("string", False, None, None),
    "idempotency-requirement-id": ("string", False, None, None),
    "compensation-mode": (
        "choice",
        True,
        False,
        ("NOT_APPLICABLE", "COMPENSATE", "OUTCOME_REVIEW_ONLY"),
    ),
    "compensation-reference-id": ("string", False, None, None),
    "outcome-review-reference-id": ("string", False, None, None),
    "governance-evidence-complete": ("boolean", True, None, None),
    "waiver-control-id": ("string", False, None, None),
    "waiver-scope-id": ("string", False, None, None),
    "waiver-approval-reference-id": ("string", False, None, None),
    "waiver-justification-evidence-refs": ("string", False, None, None),
    "waiver-compensating-control-id": ("string", False, None, None),
    "waiver-expiry-time": ("string", False, None, None),
    "waiver-does-not-satisfy-promotion-confirmed": ("boolean", True, None, None),
    "integration-class-scope": ("choice", True, True, ("api", "postgresql", "files", "events")),
    "integration-operation-class": ("choice", True, False, ("READ", "WRITE")),
    "integration-side-effect-class": (
        "choice",
        True,
        False,
        ("NONE", "REVERSIBLE", "IRREVERSIBLE", "UNKNOWN"),
    ),
    "integration-owner-role": ("string", True, None, None),
    "integration-custodian-role": ("string", True, None, None),
    "access-credential-reference-id": ("string", True, None, None),
    "scoped-access-approved": ("boolean", True, None, None),
    "integration-data-classification-scope": ("string", True, None, None),
    "integration-evidence-refs": ("string", True, None, None),
}

DECLARATION_CONTRACT = {
    "white-goods.integration.api-read": ("api", "READ", "READ_ONLY", "NONE", False, False, "NOT_APPLICABLE"),
    "white-goods.integration.api-reversible-write": (
        "api",
        "WRITE",
        "REVERSIBLE_WRITE",
        "REVERSIBLE",
        True,
        True,
        "COMPENSATE",
    ),
    "white-goods.integration.postgresql-read": (
        "postgresql",
        "READ",
        "READ_ONLY",
        "NONE",
        False,
        False,
        "NOT_APPLICABLE",
    ),
    "white-goods.integration.postgresql-reversible-write": (
        "postgresql",
        "WRITE",
        "REVERSIBLE_WRITE",
        "REVERSIBLE",
        True,
        True,
        "COMPENSATE",
    ),
    "white-goods.integration.files-read": ("files", "READ", "READ_ONLY", "NONE", False, False, "NOT_APPLICABLE"),
    "white-goods.integration.events-read": ("events", "READ", "READ_ONLY", "NONE", False, False, "NOT_APPLICABLE"),
}

FIXTURE_FIELDS = {
    "apiVersion",
    "kind",
    "id",
    "stage",
    "synthetic",
    "evaluationTime",
    "demand",
    "approvalRequest",
    "waiverRecord",
    "evidence",
    "expectedDecision",
}
DEMAND_FIELDS = {
    "demandId",
    "organizationId",
    "scopeId",
    "requiredControlId",
    "actionCategory",
    "autonomyLevel",
    "integrationDeclarationId",
    "policyReferenceId",
    "accessCredentialReferenceId",
    "accessScopeApproved",
    "receiptRequirementId",
    "idempotencyRequirementId",
    "compensationMode",
    "compensationReferenceId",
    "outcomeReviewReferenceId",
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json(pack: ValidatedPack, path: str) -> dict[str, Any]:
    value = json.loads(pack.files[path])
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("time must be an explicit UTC timestamp")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() is None:
        raise ValueError("time lacks an offset")
    return parsed


def _require_stable(value: Any, field: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not STABLE_ID.fullmatch(value):
        raise ValueError(f"{field} is not a stable identifier")


def _question_contract(pack: ValidatedPack) -> dict[str, tuple[Any, ...]]:
    questions: dict[str, tuple[Any, ...]] = {}
    paths: list[str] = []
    for resource in pack.manifest["content"]["questionnaires"]:
        path = resource["path"]
        if not (path.startswith("questions/governance/") or path.startswith("questions/integrations/")):
            continue
        paths.append(path)
        value = yaml.safe_load(pack.files[path])
        expected_identity = {
            "apiVersion": "harness.planeon.ai/questionnaire/v1alpha1",
            "kind": "Questionnaire",
            "id": resource["id"],
            "stage": resource["stage"],
        }
        if {key: value[key] for key in expected_identity} != expected_identity:
            raise ValueError(f"questionnaire identity differs: {path}")
        if set(value) != {*expected_identity, "title", "questions"}:
            raise ValueError(f"questionnaire fields differ: {path}")
        for question in value["questions"]:
            identifier = question["id"]
            if identifier in questions:
                raise ValueError(f"duplicate governance question: {identifier}")
            choices = tuple(question.get("choices", ())) or None
            multiple = question.get("multiple") if question["responseType"] == "choice" else None
            questions[identifier] = (question["responseType"], question["required"], multiple, choices)
    if paths != [
        "questions/governance/applicability.yaml",
        "questions/governance/autonomy.yaml",
        "questions/governance/waivers.yaml",
        "questions/integrations/declarations.yaml",
    ]:
        raise ValueError("governance questionnaire inventory differs")
    return questions


def validate_control_requirements(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if set(value) != {
        "apiVersion",
        "kind",
        "id",
        "stage",
        "contractStatus",
        "tenantPolicyRequired",
        "requirements",
    }:
        raise ValueError("control requirement record-set fields differ")
    if value["apiVersion"] != "harness.planeon.ai/industry-control-requirements/v1alpha1":
        raise ValueError("control requirement api version differs")
    if value["kind"] != "IndustryControlRequirementRecordSet" or value["contractStatus"] != "PACK_LOCAL_DATA_ONLY":
        raise ValueError("control requirement public-contract status differs")
    if value["tenantPolicyRequired"] is not True:
        raise ValueError("control requirements must remain tenant-policy dependent")
    expected_ids = [
        "white-goods.control.regulatory-applicability",
        "white-goods.control.accountability",
        "white-goods.control.mutation-policy",
        "white-goods.control.mutation-approval",
        "white-goods.control.durable-receipt",
        "white-goods.control.compensation-review",
        "white-goods.control.scoped-access",
    ]
    requirements = value["requirements"]
    if [item.get("id") for item in requirements] != expected_ids:
        raise ValueError("control requirement inventory differs")
    fields = {
        "id",
        "title",
        "ownerRole",
        "applicabilityQuestionIds",
        "requiredEvidenceKinds",
        "appliesToActionCategories",
        "waiverEligible",
        "freshnessRequirement",
        "promotionDisposition",
    }
    for item in requirements:
        if set(item) != fields:
            raise ValueError(f"control requirement fields differ: {item.get('id')}")
        _require_stable(item["id"], "control id")
        _require_stable(item["ownerRole"], "control owner role")
        if item["promotionDisposition"] != "FRESH_PASS_REQUIRED":
            raise ValueError(f"control could bypass fresh PASS: {item['id']}")
        if item["applicabilityQuestionIds"] != sorted(set(item["applicabilityQuestionIds"])):
            raise ValueError(f"control questions are not sorted and unique: {item['id']}")
        if not item["requiredEvidenceKinds"] or len(item["requiredEvidenceKinds"]) != len(set(item["requiredEvidenceKinds"])):
            raise ValueError(f"control evidence requirements differ: {item['id']}")
    return {item["id"]: item for item in requirements}


def validate_integration_declarations(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if set(value) != {"apiVersion", "kind", "id", "stage", "contractStatus", "synthetic", "declarations"}:
        raise ValueError("integration declaration record-set fields differ")
    if value["apiVersion"] != "harness.planeon.ai/industry-integration-declarations/v1alpha1":
        raise ValueError("integration declaration api version differs")
    if value["kind"] != "IndustryIntegrationDeclarationRecordSet" or value["contractStatus"] != "PACK_LOCAL_DATA_ONLY":
        raise ValueError("integration declaration public-contract status differs")
    if value["synthetic"] is not True:
        raise ValueError("integration declarations must remain synthetic")
    fields = {
        "id",
        "integrationClass",
        "operationClass",
        "actionCategory",
        "sideEffectClass",
        "ownerRole",
        "custodianRole",
        "accessCredentialReferenceRequired",
        "scopedAccessApprovalRequired",
        "durableReceiptRequired",
        "idempotencyRequired",
        "compensationMode",
    }
    actual: dict[str, tuple[Any, ...]] = {}
    declarations: dict[str, dict[str, Any]] = {}
    for item in value["declarations"]:
        if set(item) != fields:
            raise ValueError(f"integration declaration fields differ: {item.get('id')}")
        identifier = item["id"]
        _require_stable(identifier, "integration declaration id")
        if identifier in declarations:
            raise ValueError(f"duplicate integration declaration: {identifier}")
        if item["accessCredentialReferenceRequired"] is not True or item["scopedAccessApprovalRequired"] is not True:
            raise ValueError(f"integration access requirement weakened: {identifier}")
        actual[identifier] = (
            item["integrationClass"],
            item["operationClass"],
            item["actionCategory"],
            item["sideEffectClass"],
            item["durableReceiptRequired"],
            item["idempotencyRequired"],
            item["compensationMode"],
        )
        declarations[identifier] = item
    if actual != DECLARATION_CONTRACT:
        raise ValueError("integration declaration contract differs")
    return declarations


def _validate_resource_ref(value: Any, field: str) -> None:
    if not isinstance(value, dict) or set(value) != {"kind", "id", "digest"}:
        raise ValueError(f"{field} resource reference fields differ")
    _require_stable(value["kind"], f"{field} kind")
    _require_stable(value["id"], f"{field} id")
    if not isinstance(value["digest"], str) or not SHA256.fullmatch(value["digest"]):
        raise ValueError(f"{field} digest differs")


def _validate_actor(value: Any, field: str) -> str:
    if not isinstance(value, dict) or set(value) != {"type", "id"}:
        raise ValueError(f"{field} actor fields differ")
    if value["type"] not in {"HUMAN", "WORKLOAD", "SYSTEM", "TENANT"}:
        raise ValueError(f"{field} actor type differs")
    _require_stable(value["id"], f"{field} actor id")
    return value["id"]


def validate_approval_request(
    value: Any,
    *,
    approval_type: str,
    organization_id: str,
    subject_id: str,
) -> tuple[dict[str, Any], str, set[str]]:
    if not isinstance(value, dict) or set(value) != {"apiVersion", "kind", "metadata", "spec"}:
        raise ValueError("ApprovalRequest fields differ")
    if value["apiVersion"] != "harness.planeon.ai/v1alpha1" or value["kind"] != "ApprovalRequest":
        raise ValueError("ApprovalRequest identity differs")
    metadata = value["metadata"]
    if not isinstance(metadata, dict) or set(metadata) != {"id", "version"}:
        raise ValueError("ApprovalRequest metadata fields differ")
    _require_stable(metadata["id"], "ApprovalRequest metadata id")
    if not isinstance(metadata["version"], str) or not SEMVER.fullmatch(metadata["version"]):
        raise ValueError("ApprovalRequest metadata version differs")
    spec = value["spec"]
    expected_fields = {
        "organizationId",
        "approvalType",
        "state",
        "subject",
        "policyRef",
        "requiredDecisions",
        "requestedBy",
        "requestedAt",
        "expiresAt",
        "decisions",
        "reasonCode",
    }
    if not isinstance(spec, dict) or set(spec) != expected_fields:
        raise ValueError("ApprovalRequest spec fields differ")
    if spec["organizationId"] != organization_id or spec["approvalType"] != approval_type:
        raise ValueError("ApprovalRequest scope or type differs")
    if spec["state"] != "APPROVED" or spec["reasonCode"] is not None:
        raise ValueError("ApprovalRequest is not an approved request")
    _validate_resource_ref(spec["subject"], "ApprovalRequest subject")
    _validate_resource_ref(spec["policyRef"], "ApprovalRequest policy")
    if spec["subject"]["id"] != subject_id:
        raise ValueError("ApprovalRequest subject id differs")
    required = spec["requiredDecisions"]
    if isinstance(required, bool) or not isinstance(required, int) or not 1 <= required <= 32:
        raise ValueError("ApprovalRequest decision quorum differs")
    requester = _validate_actor(spec["requestedBy"], "ApprovalRequest requester")
    requested_at = _parse_time(spec["requestedAt"])
    expires_at = _parse_time(spec["expiresAt"])
    if requested_at >= expires_at:
        raise ValueError("ApprovalRequest validity window differs")
    decisions = spec["decisions"]
    if not isinstance(decisions, list) or canonical_json_bytes(decisions) != canonical_json_bytes(
        json.loads(canonical_json_bytes(decisions))
    ):
        raise ValueError("ApprovalRequest decisions are not canonical data")
    approvers: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, dict) or set(decision) != {"actor", "decision", "decidedAt", "reasonCode"}:
            raise ValueError("ApprovalRequest decision fields differ")
        actor = _validate_actor(decision["actor"], "ApprovalRequest decision")
        if actor in approvers:
            raise ValueError("ApprovalRequest approver identities are not unique")
        approvers.add(actor)
        if decision["decision"] != "APPROVE" or not REASON_CODE.fullmatch(decision["reasonCode"]):
            raise ValueError("ApprovalRequest decision differs")
        decided_at = _parse_time(decision["decidedAt"])
        if not requested_at <= decided_at < expires_at:
            raise ValueError("ApprovalRequest decision time differs")
    if len(approvers) < required:
        raise ValueError("ApprovalRequest quorum is not met")
    return spec, requester, approvers


def _validate_demand(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != DEMAND_FIELDS:
        raise ValueError("governance demand fields differ")
    for field in (
        "demandId",
        "organizationId",
        "scopeId",
        "requiredControlId",
        "integrationDeclarationId",
    ):
        _require_stable(value[field], field)
    for field in (
        "policyReferenceId",
        "accessCredentialReferenceId",
        "receiptRequirementId",
        "idempotencyRequirementId",
        "compensationReferenceId",
        "outcomeReviewReferenceId",
    ):
        _require_stable(value[field], field, nullable=True)
    if value["actionCategory"] not in {"READ_ONLY", "REVERSIBLE_WRITE", "IRREVERSIBLE_WRITE", "UNKNOWN_SIDE_EFFECT"}:
        raise ValueError("action category differs")
    if value["autonomyLevel"] not in {"OBSERVE", "RECOMMEND", "APPROVAL_REQUIRED", "BOUNDED_AUTONOMOUS"}:
        raise ValueError("autonomy level differs")
    if value["compensationMode"] not in {"NOT_APPLICABLE", "COMPENSATE", "OUTCOME_REVIEW_ONLY"}:
        raise ValueError("compensation mode differs")
    if not isinstance(value["accessScopeApproved"], bool):
        raise ValueError("access-scope approval type differs")
    return value


def _evaluate_waiver(
    waiver: Any,
    *,
    demand: dict[str, Any],
    evaluation_time: datetime,
) -> set[str]:
    if not isinstance(waiver, dict):
        raise ValueError("waiver record must be an object")
    fields = {
        "apiVersion",
        "kind",
        "controlId",
        "scopeId",
        "justificationEvidenceIds",
        "compensatingControlId",
        "expiresAt",
        "renewable",
        "approvalRequest",
    }
    if set(waiver) != fields:
        raise ValueError("waiver record fields differ")
    if waiver["apiVersion"] != "harness.planeon.ai/industry-waiver-record/v1alpha1" or waiver["kind"] != "IndustryWaiverRecord":
        raise ValueError("waiver record identity differs")
    _require_stable(waiver["controlId"], "waiver control id")
    _require_stable(waiver["scopeId"], "waiver scope id")
    _require_stable(waiver["compensatingControlId"], "waiver compensating control id", nullable=True)
    evidence_ids = waiver["justificationEvidenceIds"]
    if not isinstance(evidence_ids, list) or evidence_ids != sorted(set(evidence_ids)):
        raise ValueError("waiver justification evidence differs")
    for identifier in evidence_ids:
        _require_stable(identifier, "waiver justification evidence id")
    spec, requester, approvers = validate_approval_request(
        waiver["approvalRequest"],
        approval_type="WAIVER",
        organization_id=demand["organizationId"],
        subject_id=waiver["controlId"],
    )
    reasons = {"WAIVER_DOES_NOT_SATISFY_PROMOTION"}
    if requester in approvers:
        reasons.add("WAIVER_SELF_APPROVAL_FORBIDDEN")
    if waiver["scopeId"] != demand["scopeId"] or waiver["controlId"] != demand["requiredControlId"]:
        reasons.add("WAIVER_SCOPE_MISMATCH")
    if not evidence_ids:
        reasons.add("WAIVER_JUSTIFICATION_REQUIRED")
    if waiver["compensatingControlId"] is None:
        reasons.add("WAIVER_COMPENSATING_CONTROL_REQUIRED")
    if waiver["renewable"] is not False:
        reasons.add("WAIVER_RENEWAL_FORBIDDEN")
    expires_at = _parse_time(waiver["expiresAt"])
    if expires_at != _parse_time(spec["expiresAt"]):
        raise ValueError("waiver and approval expiry differ")
    if expires_at <= evaluation_time:
        reasons.add("WAIVER_EXPIRED")
    return reasons


def evaluate_fixture(value: dict[str, Any], declarations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(value) != FIXTURE_FIELDS:
        raise ValueError("governance fixture fields differ")
    if value["apiVersion"] != "harness.planeon.ai/governance-fixture/v1alpha1" or value["kind"] != "GovernanceFixture":
        raise ValueError("governance fixture identity differs")
    if value["stage"] != "governance-and-regulation" or value["synthetic"] is not True:
        raise ValueError("governance fixture must be synthetic governance data")
    _require_stable(value["id"], "governance fixture id")
    if value["evidence"] != GOVERNANCE_EVIDENCE:
        raise ValueError("governance fixture asserted unavailable evidence")
    evaluated_at = _parse_time(value["evaluationTime"])
    demand = _validate_demand(value["demand"])
    reasons: set[str] = set()
    action = demand["actionCategory"]

    declaration = declarations.get(demand["integrationDeclarationId"])
    if declaration is None:
        reasons.add("INTEGRATION_DECLARATION_REQUIRED")
    if action == "UNKNOWN_SIDE_EFFECT":
        reasons.add("UNKNOWN_SIDE_EFFECT")
    elif declaration is not None and declaration["actionCategory"] != action:
        reasons.add("ACTION_DECLARATION_MISMATCH")

    if demand["accessCredentialReferenceId"] is None:
        reasons.add("MISSING_SCOPED_CREDENTIAL_REFERENCE")
    if demand["accessScopeApproved"] is not True:
        reasons.add("SCOPED_ACCESS_APPROVAL_REQUIRED")

    if action in {"REVERSIBLE_WRITE", "IRREVERSIBLE_WRITE"}:
        if demand["policyReferenceId"] is None:
            reasons.add("MISSING_POLICY_REFERENCE")
        approval = value["approvalRequest"]
        if approval is None:
            reasons.add("MISSING_MUTATION_APPROVAL")
        else:
            spec, requester, approvers = validate_approval_request(
                approval,
                approval_type="MUTATION",
                organization_id=demand["organizationId"],
                subject_id=demand["demandId"],
            )
            if demand["policyReferenceId"] is not None and spec["policyRef"]["id"] != demand["policyReferenceId"]:
                reasons.add("MUTATION_POLICY_MISMATCH")
            if _parse_time(spec["expiresAt"]) <= evaluated_at:
                reasons.add("MUTATION_APPROVAL_EXPIRED")
            if requester in approvers:
                reasons.add("SELF_APPROVAL_FORBIDDEN")
        if demand["receiptRequirementId"] is None:
            reasons.add("MISSING_RECEIPT_REQUIREMENT")
        if demand["idempotencyRequirementId"] is None:
            reasons.add("MISSING_IDEMPOTENCY_REQUIREMENT")
        if demand["compensationMode"] == "COMPENSATE" and demand["compensationReferenceId"] is None:
            reasons.add("MISSING_COMPENSATION_REFERENCE")
        elif demand["compensationMode"] == "OUTCOME_REVIEW_ONLY" and demand["outcomeReviewReferenceId"] is None:
            reasons.add("MISSING_OUTCOME_REVIEW_REFERENCE")
        elif demand["compensationMode"] == "NOT_APPLICABLE":
            reasons.add("MISSING_COMPENSATION_STRATEGY")
        if action == "IRREVERSIBLE_WRITE" and demand["compensationMode"] != "OUTCOME_REVIEW_ONLY":
            reasons.add("IRREVERSIBLE_WRITE_REQUIRES_OUTCOME_REVIEW")
    elif action == "READ_ONLY":
        if demand["compensationMode"] != "NOT_APPLICABLE":
            reasons.add("READ_ONLY_COMPENSATION_MISMATCH")
        if value["approvalRequest"] is not None:
            raise ValueError("read-only fixture must not carry mutation approval")

    if value["waiverRecord"] is not None:
        reasons.update(_evaluate_waiver(value["waiverRecord"], demand=demand, evaluation_time=evaluated_at))

    decision = {"status": "BLOCKED" if reasons else "READY", "reasonCodes": sorted(reasons)}
    if value["expectedDecision"] != decision:
        raise ValueError(f"declared governance decision differs: {value['id']}")
    return decision


def validate_pack_contract(pack: ValidatedPack, common: ValidatedPack) -> None:
    if pack.manifest["metadata"]["version"] != "0.4.0":
        raise ValueError("white-goods pack version differs")
    if pack.manifest["compatibility"]["frameworkVersion"] != "0.1.0":
        raise ValueError("pack framework compatibility differs")
    if pack.files["contracts.lock.json"] != common.files["contracts.lock.json"]:
        raise ValueError("common contracts lock changed")
    if pack.files["journey.yaml"] != common.files["journey.yaml"]:
        raise ValueError("common journey changed")
    for path, digest in PREDECESSOR_FILE_DIGESTS.items():
        if _sha256(pack.files[path]) != digest:
            raise ValueError(f"predecessor content changed: {path}")
    if len(pack.files) != 64 or len(pack.resource_ids) != 61:
        raise ValueError("white-goods file or resource inventory differs")


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["white-goods"]:
        raise SystemExit("IND-WG-003 accepts only PACK=white-goods")
    if framework_version != "0.1.1":
        raise SystemExit(f"framework version differs: {framework_version}")

    pack = load_pack(PACK_ROOT, common_root=COMMON_ROOT)
    common = load_pack(COMMON_ROOT)
    validate_pack_contract(pack, common)
    if _question_contract(pack) != QUESTION_CONTRACT:
        raise SystemExit("governance questionnaire contract differs")
    if _json(pack, "controls/contract-binding.json") != CONTRACT_BINDING:
        raise SystemExit("public governance contract binding differs")
    controls = validate_control_requirements(_json(pack, "controls/control-requirements.json"))
    declarations = validate_integration_declarations(_json(pack, "controls/integration-declarations.json"))
    if _json(pack, "controls/waiver-policy.json") != WAIVER_POLICY:
        raise SystemExit("waiver policy differs")
    if _json(pack, "rules/governance.json") != GOVERNANCE_RULE:
        raise SystemExit("governance rule differs")
    if set(controls) != {
        "white-goods.control.regulatory-applicability",
        "white-goods.control.accountability",
        "white-goods.control.mutation-policy",
        "white-goods.control.mutation-approval",
        "white-goods.control.durable-receipt",
        "white-goods.control.compensation-review",
        "white-goods.control.scoped-access",
    }:
        raise SystemExit("control inventory differs")

    fixture_digests: dict[str, str] = {}
    expected_fixtures = {
        "fail-active-waiver-promotion-blocked.json",
        "fail-expired-waiver.json",
        "fail-missing-approval.json",
        "fail-missing-compensation.json",
        "fail-missing-policy.json",
        "fail-missing-receipt.json",
        "fail-self-approval.json",
        "fail-unknown-side-effect.json",
        "fail-waiver-missing-compensating-control.json",
        "ready-read-only.json",
        "ready-reversible-write.json",
    }
    for path in sorted(GOVERNANCE_FIXTURES.glob("*.json")):
        value = json.loads(path.read_bytes())
        evaluate_fixture(value, declarations)
        fixture_digests[path.name] = _sha256(canonical_json_bytes(value))
    if set(fixture_digests) != expected_fixtures:
        raise SystemExit("governance fixture inventory differs")

    first_index, second_index = build_index(PACK_ROOT), build_index(PACK_ROOT)
    first_archive, second_archive = archive_bytes(PACK_ROOT), archive_bytes(PACK_ROOT)
    if canonical_json_bytes(first_index) != canonical_json_bytes(second_index) or first_archive != second_archive:
        raise SystemExit("white-goods index or archive is not byte reproducible")
    if first_index["evidence"] != {
        "published": False,
        "runtimeEvidence": False,
        "assuranceEvidence": False,
        "tenantAcceptance": False,
    }:
        raise SystemExit("pack index asserted unavailable evidence")

    print(
        canonical_json_bytes(
            {
                "archiveSha256": _sha256(first_archive[1]),
                "contractBindingSha256": _sha256(canonical_json_bytes(CONTRACT_BINDING)),
                "controlRequirementsSha256": _sha256(canonical_json_bytes(_json(pack, "controls/control-requirements.json"))),
                "evidence": GOVERNANCE_EVIDENCE,
                "fixtureDigests": fixture_digests,
                "frameworkVersion": framework_version,
                "indexSha256": _sha256(canonical_json_bytes(first_index)),
                "integrationDeclarationsSha256": _sha256(
                    canonical_json_bytes(_json(pack, "controls/integration-declarations.json"))
                ),
                "packDigest": pack.digest,
                "packVersion": pack.manifest["metadata"]["version"],
                "predecessorBinding": PREDECESSOR_BINDING,
                "retainedArtifacts": False,
                "waiverPolicySha256": _sha256(canonical_json_bytes(WAIVER_POLICY)),
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
