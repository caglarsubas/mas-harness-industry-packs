"""IND-WG-003 white-goods governance and integration acceptance tests."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ci.handlers.ind_wg_003 import (
    CONTRACT_BINDING,
    DECLARATION_CONTRACT,
    GOVERNANCE_EVIDENCE,
    GOVERNANCE_RULE,
    PREDECESSOR_BINDING,
    PREDECESSOR_FILE_DIGESTS,
    QUESTION_CONTRACT,
    WAIVER_POLICY,
    _json,
    _question_contract,
    _sha256,
    evaluate_fixture,
    main,
    validate_approval_request,
    validate_control_requirements,
    validate_integration_declarations,
    validate_pack_contract,
)
from planeon_industry_packs.canonical import canonical_json_bytes
from planeon_industry_packs.index import build_index
from planeon_industry_packs.loader import load_pack, validate_pack
from planeon_industry_packs.package import archive_bytes

COMMON = ROOT / "common"
PACK_ROOT = ROOT / "packs/white-goods"
FIXTURE_ROOT = PACK_ROOT / "fixtures/governance"
FIXTURES = tuple(sorted(FIXTURE_ROOT.glob("*.json")))


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_bytes())


def _declarations() -> dict[str, dict]:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    return validate_integration_declarations(_json(pack, "controls/integration-declarations.json"))


def test_sector_pack_advances_only_the_governance_slice() -> None:
    report = validate_pack(PACK_ROOT, common_root=COMMON)
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    common = load_pack(COMMON)
    assert report.accepted and report.pack_version == "0.3.0"
    assert pack.manifest["compatibility"]["frameworkVersion"] == "0.1.0"
    assert pack.manifest["extends"]["packDigest"] == "3cfea19e6e0a4a653d63622e250f40001b4f8221ebab18fa5bfc1601b8eddea3"
    assert len(pack.files) == 52
    assert len(pack.resource_ids) == 49
    validate_pack_contract(pack, common)


def test_predecessor_binding_and_every_predecessor_content_byte_are_frozen() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    assert PREDECESSOR_BINDING == {
        "commit": "a4d3df9b169e95c285e22a2fdb2b4c9d711230e2",
        "packDigest": "e0ad15c9da5f126c4aa20c88f75d4e9b15808ee841347ba4663dd99664248177",
        "packYamlSha256": "3bc885342cd43870624a1a188851af2aa314ec333ba87cb8170597f7b3d8f674",
        "frameworkWheelSha256": "d34a1a3c523b1e60f10602fff072d5dbf83f46f2220f29a4f13b9a31facf91f4",
    }
    assert len(PREDECESSOR_FILE_DIGESTS) == 31
    assert {path: _sha256(pack.files[path]) for path in PREDECESSOR_FILE_DIGESTS} == PREDECESSOR_FILE_DIGESTS


def test_governance_and_integration_questionnaires_are_closed() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    assert _question_contract(pack) == QUESTION_CONTRACT
    assert len(QUESTION_CONTRACT) == 34
    assert QUESTION_CONTRACT["action-category"][3] == (
        "READ_ONLY",
        "REVERSIBLE_WRITE",
        "IRREVERSIBLE_WRITE",
        "UNKNOWN_SIDE_EFFECT",
    )
    assert QUESTION_CONTRACT["integration-class-scope"][3] == ("api", "postgresql", "files", "events")


def test_public_contract_binding_records_schema_gap_without_false_conformance() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    assert _json(pack, "controls/contract-binding.json") == CONTRACT_BINDING
    assert CONTRACT_BINDING["schemaBytesCopied"] is False
    assert CONTRACT_BINDING["publicConformanceClaimed"] is False
    assert CONTRACT_BINDING["unavailablePublicKinds"] == [
        {"kindName": "ControlRequirement", "status": "NOT_AVAILABLE_IN_BOUND_RELEASE"},
        {"kindName": "IntegrationDeclaration", "status": "NOT_AVAILABLE_IN_BOUND_RELEASE"},
    ]
    assert CONTRACT_BINDING["approvalRequestSchema"]["status"] == "AVAILABLE"


def test_control_requirements_are_tenant_owned_and_fresh_pass_only() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    controls = validate_control_requirements(_json(pack, "controls/control-requirements.json"))
    assert len(controls) == 7
    assert all(item["promotionDisposition"] == "FRESH_PASS_REQUIRED" for item in controls.values())
    assert controls["white-goods.control.mutation-approval"]["waiverEligible"] is True
    assert controls["white-goods.control.scoped-access"]["waiverEligible"] is False


def test_pack_local_integration_declarations_are_data_only_and_closed() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    value = _json(pack, "controls/integration-declarations.json")
    declarations = validate_integration_declarations(value)
    assert value["contractStatus"] == "PACK_LOCAL_DATA_ONLY"
    assert value["synthetic"] is True
    assert {
        identifier: (
            item["integrationClass"],
            item["operationClass"],
            item["actionCategory"],
            item["sideEffectClass"],
            item["durableReceiptRequired"],
            item["idempotencyRequired"],
            item["compensationMode"],
        )
        for identifier, item in declarations.items()
    } == DECLARATION_CONTRACT


def test_rule_and_waiver_policy_are_fail_closed() -> None:
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    assert _json(pack, "rules/governance.json") == GOVERNANCE_RULE
    assert _json(pack, "controls/waiver-policy.json") == WAIVER_POLICY
    assert WAIVER_POLICY["waiverSatisfiesPromotion"] is False
    assert WAIVER_POLICY["renewable"] is False
    assert WAIVER_POLICY["requiredPromotionEvidence"] == "FRESH_PASS_FOR_EVERY_REQUIRED_CONTROL"


def test_governance_vectors_produce_exact_sorted_decisions() -> None:
    declarations = _declarations()
    expected = {
        "fail-active-waiver-promotion-blocked.json": ["WAIVER_DOES_NOT_SATISFY_PROMOTION"],
        "fail-expired-waiver.json": ["WAIVER_DOES_NOT_SATISFY_PROMOTION", "WAIVER_EXPIRED"],
        "fail-missing-approval.json": ["MISSING_MUTATION_APPROVAL"],
        "fail-missing-compensation.json": ["MISSING_COMPENSATION_REFERENCE"],
        "fail-missing-policy.json": ["MISSING_POLICY_REFERENCE"],
        "fail-missing-receipt.json": ["MISSING_RECEIPT_REQUIREMENT"],
        "fail-self-approval.json": ["SELF_APPROVAL_FORBIDDEN"],
        "fail-unknown-side-effect.json": ["UNKNOWN_SIDE_EFFECT"],
        "fail-waiver-missing-compensating-control.json": [
            "WAIVER_COMPENSATING_CONTROL_REQUIRED",
            "WAIVER_DOES_NOT_SATISFY_PROMOTION",
            "WAIVER_SCOPE_MISMATCH",
        ],
        "ready-read-only.json": [],
        "ready-reversible-write.json": [],
    }
    assert len(FIXTURES) == 11
    for path in FIXTURES:
        value = json.loads(path.read_bytes())
        assert value["evidence"] == GOVERNANCE_EVIDENCE
        decision = evaluate_fixture(value, declarations)
        assert decision["reasonCodes"] == expected[path.name]
        assert decision["status"] == ("READY" if not expected[path.name] else "BLOCKED")
        assert evaluate_fixture(json.loads(canonical_json_bytes(value)), declarations) == decision


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("accessCredentialReferenceId", None, "MISSING_SCOPED_CREDENTIAL_REFERENCE"),
        ("accessScopeApproved", False, "SCOPED_ACCESS_APPROVAL_REQUIRED"),
        ("idempotencyRequirementId", None, "MISSING_IDEMPOTENCY_REQUIREMENT"),
    ],
)
def test_additional_write_prerequisites_block(field: str, replacement: object, reason: str) -> None:
    value = _fixture("ready-reversible-write.json")
    value["demand"][field] = replacement
    value["expectedDecision"] = {"status": "BLOCKED", "reasonCodes": [reason]}
    assert evaluate_fixture(value, _declarations()) == value["expectedDecision"]


def test_public_approval_shape_quorum_and_separation_fail_closed() -> None:
    value = _fixture("ready-reversible-write.json")
    approval = value["approvalRequest"]
    spec, requester, approvers = validate_approval_request(
        approval,
        approval_type="MUTATION",
        organization_id=value["demand"]["organizationId"],
        subject_id=value["demand"]["demandId"],
    )
    assert spec["requiredDecisions"] == 2
    assert requester not in approvers and len(approvers) == 2

    duplicate = deepcopy(approval)
    duplicate["spec"]["decisions"][1]["actor"] = duplicate["spec"]["decisions"][0]["actor"]
    with pytest.raises(ValueError, match="not unique"):
        validate_approval_request(
            duplicate,
            approval_type="MUTATION",
            organization_id=value["demand"]["organizationId"],
            subject_id=value["demand"]["demandId"],
        )

    low_quorum = deepcopy(approval)
    low_quorum["spec"]["requiredDecisions"] = 3
    with pytest.raises(ValueError, match="quorum"):
        validate_approval_request(
            low_quorum,
            approval_type="MUTATION",
            organization_id=value["demand"]["organizationId"],
            subject_id=value["demand"]["demandId"],
        )


def test_active_waiver_never_changes_blocked_promotion_to_ready() -> None:
    declarations = _declarations()
    active = _fixture("fail-active-waiver-promotion-blocked.json")
    expired = _fixture("fail-expired-waiver.json")
    invalid = _fixture("fail-waiver-missing-compensating-control.json")
    assert evaluate_fixture(active, declarations)["status"] == "BLOCKED"
    assert "WAIVER_EXPIRED" in evaluate_fixture(expired, declarations)["reasonCodes"]
    assert evaluate_fixture(invalid, declarations)["reasonCodes"] == [
        "WAIVER_COMPENSATING_CONTROL_REQUIRED",
        "WAIVER_DOES_NOT_SATISFY_PROMOTION",
        "WAIVER_SCOPE_MISMATCH",
    ]


def test_fixture_canonical_digests_are_stable_per_two_reads() -> None:
    first = {path.name: _sha256(canonical_json_bytes(json.loads(path.read_bytes()))) for path in FIXTURES}
    second = {path.name: _sha256(canonical_json_bytes(json.loads(path.read_bytes()))) for path in FIXTURES}
    assert first == second
    assert len(first) == 11 and all(len(digest) == 64 for digest in first.values())


def test_sector_index_archive_and_handler_are_reproducible(capsys: pytest.CaptureFixture[str]) -> None:
    first_index, second_index = build_index(PACK_ROOT), build_index(PACK_ROOT)
    first_archive, second_archive = archive_bytes(PACK_ROOT), archive_bytes(PACK_ROOT)
    assert canonical_json_bytes(first_index) == canonical_json_bytes(second_index)
    assert first_archive == second_archive
    assert first_archive[0] == "white-goods.manufacturing-0.3.0.tar.gz"
    assert main(["white-goods"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["packVersion"] == "0.3.0"
    assert output["frameworkVersion"] == "0.1.1"
    assert output["evidence"] == GOVERNANCE_EVIDENCE
    assert output["retainedArtifacts"] is False
    assert output["predecessorBinding"] == PREDECESSOR_BINDING
    with pytest.raises(SystemExit, match="accepts only PACK=white-goods"):
        main(["another-pack"])
