#!/usr/bin/env python3
"""Closed IND-BANK-003 banking governance-integrations and readiness-evaluate acceptance handler."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from planeon_industry_packs import __version__ as framework_version  # noqa: E402
from planeon_industry_packs.canonical import canonical_json_bytes  # noqa: E402
from planeon_industry_packs.loader import ValidatedPack, load_pack  # noqa: E402
from planeon_industry_packs.readiness import evaluate as readiness_evaluate  # noqa: E402
from planeon_industry_packs.readiness import personal_data_hits  # noqa: E402

PACK_ROOT = ROOT / "packs/banking"
PACK_ID = "banking.financial-services"
PACK_VERSION = "0.3.0"
PACK_FILE_COUNT = 79
PACK_RESOURCE_COUNT = 76
EVALUATOR_INPUT = ROOT / "tests/fixtures/banking/evaluator/input"
EVALUATOR_EXPECTED = ROOT / "tests/fixtures/banking/evaluator/expected.json"
STAGE = "governance-and-regulation"
INTEGRATION_STAGE = "integration-readiness"
EVIDENCE = {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False}

# Predecessor binding (CONTRACT section 6): the post-edit bytes of 001 and 002, frozen at build.
PREDECESSOR_FILE_DIGESTS = {
    "ci/handlers/ind_bank_001.py": "b7b8ec389d245b11f2279582bd50b793d23357d791bfece65d87948665afb2ef",
    "ci/handlers/ind_bank_002.py": "8e3a48e85249f2db89ec6a103e74bf158139a36e2a524b4651fb58cda90f87b6",
}
PREDECESSOR_MODULE = "ind_bank_001_for_ind_bank_003"

CONTROL_TRIPLES = (
    ("banking.governance.contract-binding", STAGE, "controls/contract-binding.json"),
    ("banking.governance.control-requirements", STAGE, "controls/control-requirements.json"),
    ("banking.integrations.declaration-records", INTEGRATION_STAGE, "controls/integration-declarations.json"),
    ("banking.governance.waiver-policy", STAGE, "controls/waiver-policy.json"),
    ("banking.governance.autonomy-policy", STAGE, "controls/autonomy-policy.json"),
    ("banking.governance.outcome-states", STAGE, "controls/outcome-states.json"),
    ("banking.governance.ai-act-deployer-map", STAGE, "controls/ai-act-deployer-map.json"),
)
RULE_TRIPLE = ("banking.governance.block-unsafe-action", STAGE, "rules/governance.json")
QUESTIONNAIRE_TRIPLES = (
    ("banking.governance.applicability", "questions/governance/applicability.yaml", STAGE),
    ("banking.governance.autonomy", "questions/governance/autonomy.yaml", STAGE),
    ("banking.governance.waivers", "questions/governance/waivers.yaml", STAGE),
    ("banking.integrations.declarations", "questions/integrations/declarations.yaml", INTEGRATION_STAGE),
)
BLOCKED = "BLOCKED"
READY = "READY"
EXPECTED_VECTORS = {
    "fail-a1-submit-tool": "ACTION_NOT_ADMITTED_AT_MODE",
    "fail-a3-approves-payment": "AGENT_APPROVES_PAYMENT",
    "fail-a3-agent-submit": "AGENT_SUBMIT_FORBIDDEN",
    "fail-a2-executes": "AGENT_EXECUTION_ABOVE_DECLARED_MODE",
    "fail-mode-mismatch": "DERIVED_MODE_MISMATCH",
    "fail-summary-broadens-child": "SUMMARY_BROADENS_CHILD",
    "fail-child-mode-missing": "CHILD_MODE_MISSING",
    "fail-profile-above-case": "PROFILE_ABOVE_CASE",
    "fail-case-above-profile": "CASE_ABOVE_PROFILE",
    "fail-executor-mismatch": "EXECUTOR_MISMATCH",
    "fail-unknown-side-effect": "UNKNOWN_SIDE_EFFECT",
    "fail-self-approval": "SELF_APPROVAL",
    "fail-missing-approval": "MISSING_APPROVAL",
    "fail-missing-policy": "MISSING_POLICY_REFERENCE",
    "fail-missing-receipt": "MISSING_RECEIPT",
    "fail-missing-compensation": "MISSING_COMPENSATION",
    "fail-a3-after-failed-check": "EXECUTION_NOT_DISABLED_AFTER_FAILED_CHECK",
    "fail-manifest-grant-field": "GRANT_FIELD_FORBIDDEN",
    "ready-a1-read-only": None,
    "ready-a2-human-submit": None,
    "ready-a3-task-update": None,
    "ready-downgrade-after-failed-check": None,
    "fail-submitted-not-won": "SUBMITTED_IS_NOT_WON",
    "fail-upload-not-acceptance": "UPLOAD_IS_NOT_ACCEPTANCE",
    "fail-readiness-flag-not-disbursement": "READINESS_FLAG_IS_NOT_DISBURSEMENT",
    "ready-outcome-final": None,
    "fail-expired-waiver": "WAIVER_EXPIRED",
    "fail-waiver-missing-compensating-control": "WAIVER_MISSING_COMPENSATING_CONTROL",
    "fail-active-waiver-promotion-blocked": "WAIVER_DOES_NOT_SATISFY_PROMOTION",
}
INVARIANTS = {
    "INV01": "Installing a pack MUST NOT create data grants, execution rights or business authority.",
    "INV03": "The permitted action, executor, approval and derived mode MUST agree; a summary mode MUST NOT broaden child actions.",
    "INV18": "A failed compatibility, capability or protected-policy check MUST disable affected execution; fallback MUST use a separately defined preparation scope.",
}
CONTRACTS_REPOSITORY = "mas-harness-contracts"
CONTRACTS_COMMIT = "2146278a95344cd2a8e22596b2f315b46edffc88"
# The three bound schemas at CONTRACTS_COMMIT, pinned by exact path and sha256 (the values harness-onion publishes for
# the same commit, e.g. task-packets/IND-WG-003.yaml); the binding must name exactly these.
BINDING_SCHEMA_PINS = {
    "approvalRequestSchema": ("schemas/v1alpha1/lifecycle/approval-request.schema.json",
                              "4fe8d214a920690008a4390919acebf797b0ab4e6c649a7a88e0882f3b2a1b27"),
    "lifecycleCommonSchema": ("schemas/v1alpha1/lifecycle/common.schema.json",
                              "dce5d8030eea3a19694511eb26513614dcc720ef4e0d650772131b14ed58f075"),
    "compositionCommonSchema": ("schemas/v1alpha1/composition/common.schema.json",
                                "11b55d3eafa8d87a90956345da0919f67478a7738d5ca118025904f8ff58b5f0"),
}
# INV01 (pack side): no record set may carry a grant, entitlement or authority field at any depth.
AUTHORITY_TERMS = ("grant", "entitlement", "authority", "authorization", "permission")
FORBIDDEN_PROMPT_TERMS = (
    "credential value", "secret", "password", "connection string", "endpoint", "account number", "card number",
    "customer record", "transaction record", "production fact",
)

# Closed field sets, one per record kind (CONTRACT section 4; the 003 handler refuses anything else).
RECORD_FIELDS = {
    "controls/contract-binding.json": {
        "apiVersion", "kind", "id", "stage", "repository", "commit", "approvalRequestSchema", "lifecycleCommonSchema",
        "compositionCommonSchema", "unavailablePublicKinds", "packLocalDataKinds", "schemaBytesCopied", "publicConformanceClaimed",
    },
    "controls/control-requirements.json": {
        "apiVersion", "kind", "id", "stage", "contractStatus", "publicKindStatus", "tenantPolicyRequired", "controlClasses", "requirements",
    },
    "controls/integration-declarations.json": {
        "apiVersion", "kind", "id", "stage", "contractStatus", "publicKindStatus", "synthetic", "declarations",
    },
    "controls/waiver-policy.json": {
        "apiVersion", "kind", "id", "stage", "illustrative", "tenantReplacementRequired", "requiredFields", "approvalType",
        "sameControlRequired", "sameCompleteScopeRequired", "compensatingControlRequired", "unexpiredApprovalRequired", "renewable",
        "waiverEffect", "waiverSatisfiesPromotion", "promotionReasonCode", "requiredPromotionEvidence",
    },
    "controls/autonomy-policy.json": {
        "apiVersion", "kind", "id", "stage", "contractStatus", "modes", "executorKinds", "actionClasses", "approvalType",
        "writeRules", "preparationScopes", "unknownActionDisposition", "effectiveModeDirection", "invariants",
    },
    "controls/outcome-states.json": {
        "apiVersion", "kind", "id", "stage", "contractStatus", "stateOrderRequired", "states", "negativeRules",
    },
    "controls/ai-act-deployer-map.json": {
        "apiVersion", "kind", "id", "stage", "contractStatus", "candidateOnly", "legalTextQuoted", "applicabilityRuledBy",
        "candidateHighRiskUses", "entries",
    },
}
RECORD_KINDS = {
    "controls/contract-binding.json": "IndustryGovernanceContractBinding",
    "controls/control-requirements.json": "IndustryControlRequirementRecordSet",
    "controls/integration-declarations.json": "IndustryIntegrationDeclarationRecordSet",
    "controls/waiver-policy.json": "IndustryWaiverPolicy",
    "controls/autonomy-policy.json": "IndustryAutonomyPolicy",
    "controls/outcome-states.json": "IndustryOutcomeStateSet",
    "controls/ai-act-deployer-map.json": "IndustryDeployerDutyEvidenceMap",
}
SCHEMA_REF_FIELDS = {"path", "sha256"}
KIND_STATUS_FIELDS = {"kindName", "status"}
REQUIREMENT_FIELDS = {
    "id", "capId", "title", "controlClass", "ownerRole", "applicabilityQuestionIds", "requiredEvidenceKinds",
    "appliesToActionCategories", "waiverEligible", "freshnessRequirement", "promotionDisposition",
}
DECLARATION_FIELDS = {
    "id", "profileId", "label", "integrationClass", "operationClass", "actionCategory", "sideEffectClass", "maxMode",
    "ownerRole", "custodianRole", "accessCredentialReferenceRequired", "scopedAccessApprovalRequired",
    "durableReceiptRequired", "idempotencyRequired", "compensationMode", "counterpartyReferenceForm",
}
MODE_FIELDS = {"mode", "rank", "label"}
ACTION_FIELDS = {
    "actionClass", "sideEffectCategory", "agentModes", "executorWhenNotAgent", "humanExecutorModes", "approvalRequired",
    "receiptRequirement", "taskScope",
}
INVARIANT_FIELDS = {"id", "statement", "packSideEnforcement"}
STATE_FIELDS = {"state", "order", "requiredEvidenceKind", "meaning"}
NEGATIVE_RULE_FIELDS = {"id", "claimedState", "insufficientEvidenceKind", "reasonCode"}
HIGH_RISK_USE_FIELDS = {"id", "status", "evidenceSlot"}
DUTY_FIELDS = {"id", "candidateDuty", "candidateArticleReference", "status", "evidenceSlot", "namedGap"}
QUESTIONNAIRE_FIELDS = {"apiVersion", "kind", "id", "stage", "title", "questions"}
QUESTION_FIELDS = {"id", "prompt", "responseType", "required", "choices", "multiple"}
RESPONSE_TYPES = {"choice", "boolean", "string", "number"}
RULE_FIELDS = {"apiVersion", "kind", "id", "stage", "when", "action"}
VECTOR_FIELDS = {"apiVersion", "kind", "id", "stage", "synthetic", "family", "summary", "scenario", "expectedDecision", "evidence"}
CASE_FIELDS = {"caseId", "declaredMode", "preparationScope", "profiles", "checkResults", "effectiveMode", "steps", "children"}
CHILD_FIELDS = {"childId", "declaredMode", "steps", "children"}
STEP_FIELDS = {"stepId", "actionClass", "sideEffectCategory", "executor", "enabled", "write"}
WRITE_FIELDS = {
    "policyReferenceId", "approval", "receiptRequirementId", "idempotencyRequirementId", "compensationMode",
    "compensationReferenceId", "scopedAccessReferenceId", "taskScope",
}
APPROVAL_FIELDS = {"requestId", "approvalType", "status", "requesterRef", "approverRefs", "requiredQuorum", "decisionTime", "expiresAt"}
CHECK_FIELDS = {"compatibility", "capability", "protectedPolicy"}
CLAIM_FIELDS = {"state", "evidenceKind"}
COMPENSATION_MODES = {"COMPENSATE", "OUTCOME_REVIEW_ONLY"}


class Refusal(ValueError):
    """A closed-shape or binding failure; the handler refuses."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise Refusal(f"time is not a string: {label}")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def _closed(value: Any, fields: set[str], label: str, *, optional: frozenset[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict) or not (fields - optional) <= set(value) <= fields:
        raise Refusal(f"fields are not closed: {label}")
    return value


def _keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [key for item in value.items() for key in [item[0], *_keys(item[1])]]
    if isinstance(value, list):
        return [key for item in value for key in _keys(item)]
    return []


# --- binding ---------------------------------------------------------------------------------------------------------


def bind_predecessors() -> dict[str, str]:
    digests = {}
    for relative, expected in PREDECESSOR_FILE_DIGESTS.items():
        actual = _sha256((ROOT / relative).read_bytes())
        if actual != expected:
            raise Refusal(f"predecessor bytes differ from the frozen binding: {relative}")
        digests[relative] = actual
    spec = importlib.util.spec_from_file_location(PREDECESSOR_MODULE, ROOT / "ci/handlers/ind_bank_001.py")
    if spec is None or spec.loader is None:
        raise Refusal("the IND-BANK-001 handler has no loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.DECLARED_GOVERNANCE_QUESTIONNAIRES != set(QUESTIONNAIRE_TRIPLES):
        raise Refusal("the declared governance questionnaires differ from IND-BANK-001's closed set")
    return digests


# --- manifest and record sets ----------------------------------------------------------------------------------------


def check_manifest(pack: ValidatedPack) -> None:
    metadata, content = pack.manifest["metadata"], pack.manifest["content"]
    if (metadata["id"], metadata["version"]) != (PACK_ID, PACK_VERSION):
        raise Refusal("banking pack identity differs")
    if len(pack.files) != PACK_FILE_COUNT or len(pack.resource_ids) != PACK_RESOURCE_COUNT:
        raise Refusal("banking pack file or resource count differs")
    if tuple((item["id"], item["stage"], item["path"]) for item in content["controls"]) != CONTROL_TRIPLES:
        raise Refusal("control resource triples differ")
    if content["providerPreferences"]:
        raise Refusal("provider preferences stay empty")
    if RULE_TRIPLE not in [(item["id"], item["stage"], item["path"]) for item in content["rules"]]:
        raise Refusal("the governance rule resource is absent")
    questionnaires = {(item["id"], item["path"], item["stage"]) for item in content["questionnaires"]}
    if not set(QUESTIONNAIRE_TRIPLES) <= questionnaires:
        raise Refusal("a governance questionnaire resource is absent")
    governance = [item for item in content["fixtures"] if item["path"].startswith("fixtures/governance/")]
    stems = [Path(item["path"]).stem for item in governance]
    if sorted(stems) != sorted(EXPECTED_VECTORS) or len(stems) != len(set(stems)):
        raise Refusal("governance vector names differ")
    for item in governance:
        stem = Path(item["path"]).stem
        if item["id"] != f"banking.governance.vector.{stem}" or item["stage"] != STAGE:
            raise Refusal(f"governance vector resource identity differs: {stem}")
    if sum(path.startswith("fixtures/readiness/") for path in pack.files) != 9:
        raise Refusal("the nine readiness fixtures changed")
    if any(path.endswith(".schema.json") for path in pack.files):
        raise Refusal("the pack carries a schema file")


def check_record_sets(pack: ValidatedPack) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for identifier, stage, path in CONTROL_TRIPLES:
        value = _closed(json.loads(pack.files[path]), RECORD_FIELDS[path], path)
        if (value["id"], value["stage"], value["kind"]) != (identifier, stage, RECORD_KINDS[path]):
            raise Refusal(f"record set identity differs: {path}")
        bad = sorted({key for key in _keys(value) if any(term in key.casefold() for term in AUTHORITY_TERMS)})
        if bad:
            raise Refusal(f"record set carries a grant, entitlement or authority field: {path}")
        records[path] = value

    binding = records["controls/contract-binding.json"]
    for name, (pinned_path, pinned_sha) in BINDING_SCHEMA_PINS.items():
        ref = _closed(binding[name], SCHEMA_REF_FIELDS | {"status"}, name, optional=frozenset({"status"}))
        if len(ref["sha256"]) != 64:
            raise Refusal(f"schema reference digest is not exact: {name}")
        if (ref["path"], ref["sha256"]) != (pinned_path, pinned_sha):
            raise Refusal(f"schema reference differs from its pin: {name}")
    for item in binding["unavailablePublicKinds"]:
        _closed(item, KIND_STATUS_FIELDS, "unavailablePublicKinds")
    if binding["repository"] != CONTRACTS_REPOSITORY or binding["commit"] != CONTRACTS_COMMIT or binding["schemaBytesCopied"] is not False:
        raise Refusal("contract binding differs")
    lock = json.loads(pack.files["contracts.lock.json"])
    if not str(lock.get("repository", "")).endswith("/" + CONTRACTS_REPOSITORY) or lock.get("commit") != CONTRACTS_COMMIT:
        raise Refusal("the contracts lock does not match the binding (compared by suffix)")

    requirements = records["controls/control-requirements.json"]
    if requirements["publicKindStatus"] != {"kindName": "ControlRequirement", "status": "NOT_AVAILABLE_IN_BOUND_RELEASE"}:
        raise Refusal("control requirement public kind status differs")
    if requirements["controlClasses"] != ["AUTOMATED", "MANUAL", "TECHNOLOGY_DEPENDENT"]:
        raise Refusal("control classes differ")
    caps = [_closed(item, REQUIREMENT_FIELDS, "requirement")["capId"] for item in requirements["requirements"]]
    if caps != [f"CAP{index:02d}" for index in range(1, 14)]:
        raise Refusal("control objectives are not CAP01-13")
    if any(item["controlClass"] not in requirements["controlClasses"] for item in requirements["requirements"]):
        raise Refusal("a control class is outside the closed set")

    declarations = records["controls/integration-declarations.json"]
    if declarations["publicKindStatus"] != {"kindName": "IntegrationDeclaration", "status": "NOT_AVAILABLE_IN_BOUND_RELEASE"}:
        raise Refusal("integration declaration public kind status differs")
    profiles = [_closed(item, DECLARATION_FIELDS, "declaration")["profileId"] for item in declarations["declarations"]]
    if profiles != ["IP16", "IP17", "IP18"] or any(item["accessCredentialReferenceRequired"] is not True for item in declarations["declarations"]):
        raise Refusal("integration profiles differ")

    waiver = records["controls/waiver-policy.json"]
    if waiver["promotionReasonCode"] != "WAIVER_DOES_NOT_SATISFY_PROMOTION" or waiver["waiverSatisfiesPromotion"] is not False:
        raise Refusal("waiver rule differs")

    autonomy = records["controls/autonomy-policy.json"]
    if [_closed(item, MODE_FIELDS, "mode")["mode"] for item in autonomy["modes"]] != ["A1", "A2", "A3"]:
        raise Refusal("autonomy modes differ")
    classes = [_closed(item, ACTION_FIELDS, "action class")["actionClass"] for item in autonomy["actionClasses"]]
    if classes != ["read_evidence", "prepare_action", "submit", "task_update", "approve_payment"]:
        raise Refusal("action classes differ")
    invariants = {_closed(item, INVARIANT_FIELDS, "invariant")["id"]: item["statement"] for item in autonomy["invariants"]}
    if invariants != INVARIANTS:
        raise Refusal("the INV01, INV03 and INV18 rows are not verbatim")
    if autonomy["effectiveModeDirection"] != "DOWN_ONLY" or autonomy["unknownActionDisposition"] != "BLOCK":
        raise Refusal("autonomy direction or unknown-action disposition differs")

    outcomes = records["controls/outcome-states.json"]
    if [_closed(item, STATE_FIELDS, "state")["state"] for item in outcomes["states"]] != ["accepted", "committed", "final"]:
        raise Refusal("outcome states differ")
    if len([_closed(item, NEGATIVE_RULE_FIELDS, "negative rule") for item in outcomes["negativeRules"]]) != 3:
        raise Refusal("outcome negative rules differ")

    duty_map = records["controls/ai-act-deployer-map.json"]
    if duty_map["candidateOnly"] is not True or duty_map["legalTextQuoted"] is not False:
        raise Refusal("the deployer-duty map is not candidate-only")
    for item in duty_map["candidateHighRiskUses"]:
        if _closed(item, HIGH_RISK_USE_FIELDS, "high-risk use")["status"] != "CANDIDATE":
            raise Refusal("a high-risk use is not a candidate")
    for item in duty_map["entries"]:
        entry = _closed(item, DUTY_FIELDS, "duty")
        if entry["status"] != "CANDIDATE" or (entry["evidenceSlot"] is None and not entry["namedGap"]):
            raise Refusal(f"a deployer duty is not a candidate with a slot or a named gap: {entry['id']}")
    return records


def check_questionnaires_and_rule(pack: ValidatedPack) -> None:
    for identifier, path, stage in QUESTIONNAIRE_TRIPLES:
        value = _closed(yaml.safe_load(pack.files[path]), QUESTIONNAIRE_FIELDS, path)
        if (value["id"], value["stage"]) != (identifier, stage):
            raise Refusal(f"questionnaire identity differs: {path}")
        ids = []
        for question in value["questions"]:
            item = _closed(question, QUESTION_FIELDS, path, optional=frozenset({"choices", "multiple"}))
            if item["responseType"] not in RESPONSE_TYPES or (item["responseType"] == "choice") != ("choices" in item):
                raise Refusal(f"question type is not closed: {path}")
            if any(term in item["prompt"].casefold() for term in FORBIDDEN_PROMPT_TERMS):
                raise Refusal(f"a question asks for a record, credential or endpoint: {path}")
            ids.append(item["id"])
        if len(ids) != len(set(ids)):
            raise Refusal(f"question ids are not unique: {path}")
    rule = _closed(json.loads(pack.files[RULE_TRIPLE[2]]), RULE_FIELDS, RULE_TRIPLE[2])
    if (rule["id"], rule["stage"], rule["kind"]) != (RULE_TRIPLE[0], RULE_TRIPLE[1], "PackRule"):
        raise Refusal("governance rule identity differs")


def check_no_account_shapes(pack: ValidatedPack) -> None:
    prefixes = ("controls/", "questions/governance/", "questions/integrations/", "rules/governance.json", "fixtures/governance/")
    for path, data in sorted(pack.files.items()):
        if path.startswith(prefixes) and personal_data_hits(data.decode("utf-8")):
            raise Refusal(f"a governance file holds a card- or account-shaped value: {path}")
    for path in sorted(EVALUATOR_INPUT.rglob("*")):
        if path.is_file() and personal_data_hits(path.read_text(encoding="utf-8")):
            raise Refusal("an evaluator input file holds a card- or account-shaped value")


# --- vector evaluation -----------------------------------------------------------------------------------------------


class Decision(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _walk(node: dict[str, Any], owner_mode: str | None, in_child: bool):
    for step in node["steps"]:
        yield step, owner_mode, in_child
    for child in node.get("children", []):
        _closed(child, CHILD_FIELDS, "child", optional=frozenset({"declaredMode", "children"}))
        yield from _walk(child, child.get("declaredMode"), True)


def _children(node: dict[str, Any]):
    for child in node.get("children", []):
        yield child
        yield from _children(child)


def evaluate_case(case: dict[str, Any], records: dict[str, Any]) -> None:
    """Raise Decision with the first failing reason code; return when the case is READY."""
    autonomy = records["controls/autonomy-policy.json"]
    rank = {item["mode"]: item["rank"] for item in autonomy["modes"]}
    actions = {item["actionClass"]: item for item in autonomy["actionClasses"]}
    categories = {item["sideEffectCategory"] for item in actions.values()}
    profiles = {item["profileId"]: item for item in records["controls/integration-declarations.json"]["declarations"]}
    _closed(case, CASE_FIELDS, "case")
    _closed(case["checkResults"], CHECK_FIELDS, "checkResults")
    declared = case["declaredMode"]
    if declared not in rank:
        raise Decision("DECLARED_MODE_UNKNOWN")
    steps = list(_walk(case, declared, False))
    for step, _, _ in steps:
        _closed(step, STEP_FIELDS, "step")
        action = actions.get(step["actionClass"])
        if action is None or step["sideEffectCategory"] not in categories:
            raise Decision("UNKNOWN_SIDE_EFFECT")
        if step["sideEffectCategory"] != action["sideEffectCategory"]:
            raise Decision("SIDE_EFFECT_MISMATCH")
    if any(child.get("declaredMode") is None for child in _children(case)):
        raise Decision("CHILD_MODE_MISSING")
    if any(child["declaredMode"] not in rank for child in _children(case)):
        raise Decision("DECLARED_MODE_UNKNOWN")

    for step, mode, in_child in steps:
        action = actions[step["actionClass"]]
        executor = step["executor"]
        if executor not in autonomy["executorKinds"]:
            raise Decision("EXECUTOR_MISMATCH")
        if executor == "AGENT":
            if step["actionClass"] == "submit":
                raise Decision("AGENT_SUBMIT_FORBIDDEN")
            if step["actionClass"] == "approve_payment":
                raise Decision("AGENT_APPROVES_PAYMENT")
            if not action["agentModes"]:
                raise Decision("EXECUTOR_MISMATCH")
            if mode not in action["agentModes"]:
                raise Decision("SUMMARY_BROADENS_CHILD" if in_child else "AGENT_EXECUTION_ABOVE_DECLARED_MODE")
        else:
            if action["executorWhenNotAgent"] is None or executor != action["executorWhenNotAgent"]:
                raise Decision("EXECUTOR_MISMATCH")
            if mode not in action["humanExecutorModes"]:
                raise Decision("ACTION_NOT_ADMITTED_AT_MODE")
        check_write(step, action, autonomy)

    derived = max((min(rank[mode] for mode in actions[step["actionClass"]]["agentModes"]) for step, _, _ in steps if step["executor"] == "AGENT"), default=1)
    if derived != rank[declared]:
        raise Decision("DERIVED_MODE_MISMATCH")

    for profile_id in case["profiles"]:
        profile = profiles.get(profile_id)
        if profile is None:
            raise Decision("UNKNOWN_PROFILE")
        if rank[profile["maxMode"]] > rank[declared]:
            raise Decision("PROFILE_ABOVE_CASE")
        if rank[declared] > rank[profile["maxMode"]] or derived > rank[profile["maxMode"]]:
            raise Decision("CASE_ABOVE_PROFILE")

    scope = case["preparationScope"]
    if scope not in autonomy["preparationScopes"] or rank[scope] > rank[declared]:
        raise Decision("PREPARATION_SCOPE_INVALID")
    results = set(case["checkResults"].values())
    if not results <= {"PASS", "FAIL"}:
        raise Decision("CHECK_RESULT_UNKNOWN")
    failed = "FAIL" in results
    expected_effective = scope if failed else declared
    if case["effectiveMode"] != expected_effective:
        raise Decision("EXECUTION_NOT_DISABLED_AFTER_FAILED_CHECK" if failed else "EFFECTIVE_MODE_INVALID")
    if failed:
        for step, _, _ in steps:
            action = actions[step["actionClass"]]
            admitted = action["agentModes"] if step["executor"] == "AGENT" else action["humanExecutorModes"]
            if step["enabled"] and expected_effective not in admitted:
                raise Decision("EXECUTION_NOT_DISABLED_AFTER_FAILED_CHECK")


def check_write(step: dict[str, Any], action: dict[str, Any], autonomy: dict[str, Any]) -> None:
    write = step["write"]
    if not action["approvalRequired"]:
        if write is not None:
            raise Decision("UNEXPECTED_WRITE")
        return
    if write is None:
        raise Decision("MISSING_POLICY_REFERENCE")
    _closed(write, WRITE_FIELDS, "write")
    if not write["policyReferenceId"]:
        raise Decision("MISSING_POLICY_REFERENCE")
    approval = write["approval"]
    if approval is None:
        raise Decision("MISSING_APPROVAL")
    _closed(approval, APPROVAL_FIELDS, "approval")
    if approval["approvalType"] != autonomy["approvalType"] or approval["status"] != "APPROVED":
        raise Decision("MISSING_APPROVAL")
    if _time(approval["expiresAt"], "expiresAt") <= _time(approval["decisionTime"], "decisionTime"):
        raise Decision("MISSING_APPROVAL")
    if approval["requesterRef"] in approval["approverRefs"]:
        raise Decision("SELF_APPROVAL")
    if type(approval["requiredQuorum"]) is not int or approval["requiredQuorum"] < 2 or len(set(approval["approverRefs"])) < approval["requiredQuorum"]:
        raise Decision("APPROVER_QUORUM_NOT_MET")
    if not write["receiptRequirementId"]:
        raise Decision("MISSING_RECEIPT")
    if not write["idempotencyRequirementId"]:
        raise Decision("MISSING_IDEMPOTENCY")
    if not write["scopedAccessReferenceId"]:
        raise Decision("MISSING_SCOPED_ACCESS_REFERENCE")
    if write["compensationMode"] not in COMPENSATION_MODES or not write["compensationReferenceId"]:
        raise Decision("MISSING_COMPENSATION")
    if write["taskScope"] != action["taskScope"]:
        raise Decision("TASK_SCOPE_MISMATCH")


def evaluate_claims(claims: Any, records: dict[str, Any]) -> None:
    outcomes = records["controls/outcome-states.json"]
    states = {item["state"]: item for item in outcomes["states"]}
    if not isinstance(claims, list) or not claims:
        raise Decision("OUTCOME_CLAIMS_EMPTY")
    for claim in claims:
        _closed(claim, CLAIM_FIELDS, "claim")
        if claim["state"] not in states:
            raise Decision("UNKNOWN_OUTCOME_STATE")
        for rule in outcomes["negativeRules"]:
            if (claim["state"], claim["evidenceKind"]) == (rule["claimedState"], rule["insufficientEvidenceKind"]):
                raise Decision(rule["reasonCode"])
        if claim["evidenceKind"] != states[claim["state"]]["requiredEvidenceKind"]:
            raise Decision("OUTCOME_EVIDENCE_MISMATCH")
    order = [states[claim["state"]]["order"] for claim in claims]
    if outcomes["stateOrderRequired"] and order != list(range(1, len(order) + 1)):
        raise Decision("OUTCOME_ORDER_INVALID")


def evaluate_waiver(scenario: dict[str, Any], records: dict[str, Any]) -> None:
    policy = records["controls/waiver-policy.json"]
    _closed(scenario, {"evaluationTime", "waiver"}, "waiver scenario")
    waiver = scenario["waiver"]
    if not isinstance(waiver, dict) or set(waiver) != set(policy["requiredFields"]):
        raise Decision("WAIVER_FIELDS_NOT_CLOSED")
    if waiver["approvalType"] != policy["approvalType"]:
        raise Decision("WAIVER_APPROVAL_TYPE_INVALID")
    if _time(waiver["expiresAt"], "expiresAt") <= _time(scenario["evaluationTime"], "evaluationTime"):
        raise Decision("WAIVER_EXPIRED")
    controls = {item["id"] for item in records["controls/control-requirements.json"]["requirements"]}
    if not waiver["compensatingControlId"]:
        raise Decision("WAIVER_MISSING_COMPENSATING_CONTROL")
    if waiver["controlId"] not in controls or waiver["compensatingControlId"] not in controls:
        raise Decision("WAIVER_CONTROL_UNKNOWN")
    if waiver["renewable"] is not policy["renewable"] or not waiver["justificationEvidenceIds"]:
        raise Decision("WAIVER_INCOMPLETE")
    # A complete, active waiver documents an exception only: promotion stays blocked.
    raise Decision(policy["promotionReasonCode"])


def evaluate_integrity(scenario: dict[str, Any], pack: ValidatedPack) -> None:
    _closed(scenario, {"target", "location", "addedField"}, "integrity scenario")
    if scenario["target"] != "pack.yaml":
        raise Refusal("integrity vector target differs")
    manifest = copy.deepcopy(yaml.safe_load(pack.files["pack.yaml"]))
    if not isinstance(manifest.get(scenario["location"]), dict):
        raise Refusal("integrity vector location differs")
    manifest[scenario["location"]][scenario["addedField"]] = [{"synthetic": True}]
    schema = json.loads((ROOT / "schemas/industry-pack.schema.json").read_text(encoding="utf-8"))
    if any(True for _ in Draft202012Validator(schema).iter_errors(manifest)):
        raise Decision("GRANT_FIELD_FORBIDDEN")


def evaluate_vector(stem: str, value: Any, records: dict[str, Any], pack: ValidatedPack) -> dict[str, Any]:
    vector = _closed(value, VECTOR_FIELDS, stem)
    if (vector["id"], vector["stage"], vector["synthetic"], vector["evidence"]) != (f"banking.governance.vector.{stem}", STAGE, True, EVIDENCE):
        raise Refusal(f"vector identity or evidence differs: {stem}")
    scenario = vector["scenario"]
    try:
        if vector["family"] == "autonomy":
            _closed(scenario, {"case"}, stem)
            evaluate_case(scenario["case"], records)
        elif vector["family"] == "outcome":
            _closed(scenario, {"claims"}, stem)
            evaluate_claims(scenario["claims"], records)
        elif vector["family"] == "waiver":
            evaluate_waiver(scenario, records)
        elif vector["family"] == "integrity":
            evaluate_integrity(scenario, pack)
        else:
            raise Refusal(f"vector family is not closed: {stem}")
    except Decision as decision:
        return {"status": BLOCKED, "reasonCodes": [decision.code]}
    return {"status": READY, "reasonCodes": []}


# --- forms -----------------------------------------------------------------------------------------------------------


def run_governance() -> tuple[dict[str, Any], bool]:
    digests = bind_predecessors()
    pack = load_pack(PACK_ROOT, common_root=ROOT / "common")
    check_manifest(pack)
    records = check_record_sets(pack)
    check_questionnaires_and_rule(pack)
    check_no_account_shapes(pack)
    decisions, vector_digests, mismatches = {}, {}, []
    for stem in sorted(EXPECTED_VECTORS):
        data = pack.files[f"fixtures/governance/{stem}.json"]
        value = json.loads(data)
        decision = evaluate_vector(stem, value, records, pack)
        expected_code = EXPECTED_VECTORS[stem]
        expected = {"status": BLOCKED, "reasonCodes": [expected_code]} if expected_code else {"status": READY, "reasonCodes": []}
        if value["expectedDecision"] != expected:
            raise Refusal(f"vector label differs from the closed list: {stem}")
        if decision != expected:
            mismatches.append(stem)
        decisions[stem] = decision
        vector_digests[stem] = _sha256(data)
    report = {
        "packetId": "IND-BANK-003",
        "packVersion": PACK_VERSION,
        "packDigest": pack.digest,
        "frameworkVersion": framework_version,
        "predecessorFileDigests": digests,
        "controls": [item[0] for item in CONTROL_TRIPLES],
        "questionnaires": [item[0] for item in QUESTIONNAIRE_TRIPLES],
        "rule": RULE_TRIPLE[0],
        "decisions": decisions,
        "vectorDigests": vector_digests,
        "vectorsMeetingLabel": len(decisions) - len(mismatches),
        "vectorCount": len(decisions),
        "mismatches": mismatches,
        "evidence": EVIDENCE,
    }
    return report, not mismatches


def run_readiness() -> tuple[bytes, bool]:
    verdict = canonical_json_bytes(readiness_evaluate(PACK_ROOT, EVALUATOR_INPUT))
    return verdict, verdict == EVALUATOR_EXPECTED.read_bytes()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if framework_version != "0.1.1":
        raise SystemExit(f"framework version differs: {framework_version}")
    try:
        if arguments == ["banking"]:
            report, accepted = run_governance()
            print(canonical_json_bytes(report).decode("utf-8"))
            return 0 if accepted else 1
        if arguments == ["readiness-evaluate", "banking"]:
            verdict, accepted = run_readiness()
            print(verdict.decode("utf-8"))
            if not accepted:
                print("IND-BANK-003 refuses: the readiness verdict differs from expected.json", file=sys.stderr)
            return 0 if accepted else 1
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"IND-BANK-003 refuses: {exc}") from None
    raise SystemExit("IND-BANK-003 accepts only PACK=banking or readiness-evaluate PACK=banking")


if __name__ == "__main__":
    raise SystemExit(main())
