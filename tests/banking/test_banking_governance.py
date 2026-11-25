"""IND-BANK-003 banking governance-integrations acceptance tests."""

from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
import shutil
from pathlib import Path

import pytest
import yaml

from planeon_industry_packs.errors import PackValidationError
from planeon_industry_packs.loader import load_pack

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common"
PACK_ROOT = ROOT / "packs/banking"


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HANDLER = _load("ind_bank_003_handler", "ci/handlers/ind_bank_003.py")
IB1 = _load("ind_bank_001_handler_for_003_tests", "ci/handlers/ind_bank_001.py")

STEMS = sorted(HANDLER.EXPECTED_VECTORS)


@pytest.fixture(scope="module")
def pack():
    return load_pack(PACK_ROOT, common_root=COMMON)


@pytest.fixture(scope="module")
def records(pack):
    return HANDLER.check_record_sets(pack)


def _vector(stem: str) -> dict:
    return json.loads((PACK_ROOT / f"fixtures/governance/{stem}.json").read_text(encoding="utf-8"))


def _with_file(pack, path: str, value) -> object:
    files = dict(pack.files)
    files[path] = json.dumps(value).encode("utf-8")
    return dataclasses.replace(pack, files=files)


def test_vector_names_equal_contract_section_5() -> None:
    assert len(STEMS) == 29
    assert sorted(path.stem for path in (PACK_ROOT / "fixtures/governance").glob("*.json")) == STEMS
    assert sum(stem.startswith("ready-") for stem in STEMS) == 5


def test_governance_form_meets_every_label() -> None:
    report, accepted = HANDLER.run_governance()
    assert accepted is True
    assert report["vectorCount"] == 29 and report["vectorsMeetingLabel"] == 29 and report["mismatches"] == []
    assert report["packVersion"] == "0.3.0"
    assert report["evidence"] == {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False}


@pytest.mark.parametrize("stem", STEMS)
def test_every_vector_meets_its_label(stem: str, pack, records) -> None:
    value = _vector(stem)
    assert HANDLER.evaluate_vector(stem, value, records, pack) == value["expectedDecision"]


def test_handler_refuses_other_argv() -> None:
    for argv in ([], ["white-goods"], ["readiness-evaluate"], ["readiness-evaluate", "white-goods"], ["banking", "extra"]):
        with pytest.raises(SystemExit):
            HANDLER.main(argv)


@pytest.mark.parametrize("path", [item[2] for item in HANDLER.CONTROL_TRIPLES])
def test_record_set_fields_are_closed(path: str, pack) -> None:
    value = json.loads(pack.files[path])
    value["unexpectedField"] = True
    with pytest.raises(HANDLER.Refusal, match="fields are not closed"):
        HANDLER.check_record_sets(_with_file(pack, path, value))


@pytest.mark.parametrize("field", ["dataGrants", "executionEntitlement", "businessAuthority"])
def test_record_set_refuses_grant_entitlement_or_authority_field(field: str, pack) -> None:
    path = "controls/autonomy-policy.json"
    value = json.loads(pack.files[path])
    value["actionClasses"][0][field] = []
    with pytest.raises(HANDLER.Refusal):
        HANDLER.check_record_sets(_with_file(pack, path, value))


def test_nested_record_fields_are_closed(pack) -> None:
    path = "controls/integration-declarations.json"
    value = json.loads(pack.files[path])
    value["declarations"][0]["connectionProfile"] = "synthetic"
    with pytest.raises(HANDLER.Refusal, match="fields are not closed"):
        HANDLER.check_record_sets(_with_file(pack, path, value))


def test_fifth_undeclared_governance_questionnaire_is_refused_with_the_same_message(pack) -> None:
    manifest = copy.deepcopy(pack.manifest)
    manifest["content"]["questionnaires"].append(
        {"id": "banking.governance.undeclared", "stage": "governance-and-regulation", "path": "questions/governance/undeclared.yaml"}
    )
    with pytest.raises(ValueError, match="questionnaire outside the business stage"):
        IB1.questionnaire_contract(dataclasses.replace(pack, manifest=manifest))


def test_the_four_declared_governance_questionnaires_pass_the_business_contract(pack) -> None:
    IB1.questionnaire_contract(pack)
    assert IB1.DECLARED_GOVERNANCE_QUESTIONNAIRES == set(HANDLER.QUESTIONNAIRE_TRIPLES)


def test_invariant_rows_are_verbatim(records) -> None:
    rows = {item["id"]: item["statement"] for item in records["controls/autonomy-policy.json"]["invariants"]}
    assert rows == HANDLER.INVARIANTS


# INV01: installing the pack creates no grant; the loader's closed manifest schema refuses a grant field.
def test_inv01_loader_refuses_a_manifest_grant_field(tmp_path: Path) -> None:
    copy_root = tmp_path / "banking"
    shutil.copytree(PACK_ROOT, copy_root)
    manifest = yaml.safe_load((copy_root / "pack.yaml").read_text(encoding="utf-8"))
    manifest["metadata"]["dataGrants"] = [{"synthetic": True}]
    (copy_root / "pack.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    with pytest.raises(PackValidationError) as caught:
        load_pack(copy_root, common_root=COMMON)
    assert caught.value.as_dict()["reason"] == "MANIFEST_SCHEMA_INVALID"


# INV03: permitted action, executor, approval and derived mode agree; a summary never broadens a child.
def test_inv03_derived_mode_must_equal_declared_mode(records) -> None:
    case = copy.deepcopy(_vector("ready-a3-task-update")["scenario"]["case"])
    case["declaredMode"] = "A2"
    case["effectiveMode"] = "A2"
    case["profiles"] = []
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_case(case, records)
    assert caught.value.code == "AGENT_EXECUTION_ABOVE_DECLARED_MODE"
    case = copy.deepcopy(_vector("ready-a2-human-submit")["scenario"]["case"])
    case["steps"] = case["steps"][:1] + case["steps"][2:]
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_case(case, records)
    assert caught.value.code == "DERIVED_MODE_MISMATCH"


def test_inv03_child_mode_is_never_inherited(records) -> None:
    case = copy.deepcopy(_vector("fail-summary-broadens-child")["scenario"]["case"])
    case["children"][0]["declaredMode"] = "A3"
    HANDLER.evaluate_case(case, records)
    del case["children"][0]["declaredMode"]
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_case(case, records)
    assert caught.value.code == "CHILD_MODE_MISSING"


def test_inv03_agent_never_submits_or_approves_payment_at_any_mode(records) -> None:
    for action, code in (("submit", "AGENT_SUBMIT_FORBIDDEN"), ("approve_payment", "AGENT_APPROVES_PAYMENT")):
        case = copy.deepcopy(_vector("ready-a2-human-submit")["scenario"]["case"])
        case["steps"][2]["actionClass"] = action
        case["steps"][2]["executor"] = "AGENT"
        with pytest.raises(HANDLER.Decision) as caught:
            HANDLER.evaluate_case(case, records)
        assert caught.value.code == code


# INV18: a failed check drops the effective mode to the preparation scope; it never rises.
def test_inv18_failed_check_downgrades_and_disables(records) -> None:
    case = copy.deepcopy(_vector("ready-downgrade-after-failed-check")["scenario"]["case"])
    HANDLER.evaluate_case(case, records)
    case["steps"][1]["enabled"] = True
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_case(case, records)
    assert caught.value.code == "EXECUTION_NOT_DISABLED_AFTER_FAILED_CHECK"


@pytest.mark.parametrize("check", ["compatibility", "capability", "protectedPolicy"])
def test_inv18_every_check_kind_triggers_the_downgrade(check: str, records) -> None:
    case = copy.deepcopy(_vector("ready-a3-task-update")["scenario"]["case"])
    case["checkResults"][check] = "FAIL"
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_case(case, records)
    assert caught.value.code == "EXECUTION_NOT_DISABLED_AFTER_FAILED_CHECK"
    case["effectiveMode"] = "A2"
    case["steps"][1]["enabled"] = False
    HANDLER.evaluate_case(case, records)


def test_inv18_effective_mode_never_rises(records) -> None:
    case = copy.deepcopy(_vector("ready-a1-read-only")["scenario"]["case"])
    case["effectiveMode"] = "A2"
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_case(case, records)
    assert caught.value.code == "EFFECTIVE_MODE_INVALID"
    case = copy.deepcopy(_vector("ready-a1-read-only")["scenario"]["case"])
    case["preparationScope"] = "A2"
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_case(case, records)
    assert caught.value.code == "PREPARATION_SCOPE_INVALID"


def test_profiles_never_raise_a_mode(records) -> None:
    case = copy.deepcopy(_vector("ready-a3-task-update")["scenario"]["case"])
    case["profiles"] = ["IP16"]
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_case(case, records)
    assert caught.value.code == "CASE_ABOVE_PROFILE"


def test_waiver_never_satisfies_promotion(records) -> None:
    scenario = _vector("fail-active-waiver-promotion-blocked")["scenario"]
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_waiver(copy.deepcopy(scenario), records)
    assert caught.value.code == "WAIVER_DOES_NOT_SATISFY_PROMOTION"


def test_outcome_states_need_their_evidence_in_order(records) -> None:
    claims = _vector("ready-outcome-final")["scenario"]["claims"]
    HANDLER.evaluate_claims(copy.deepcopy(claims), records)
    with pytest.raises(HANDLER.Decision) as caught:
        HANDLER.evaluate_claims([claims[0], claims[2]], records)
    assert caught.value.code == "OUTCOME_ORDER_INVALID"


def test_governance_rule_is_a_plain_pack_rule(pack) -> None:
    rule = json.loads(pack.files["rules/governance.json"])
    assert set(rule) == {"apiVersion", "kind", "id", "stage", "when", "action"}
    assert (rule["id"], rule["stage"]) == ("banking.governance.block-unsafe-action", "governance-and-regulation")


def test_descriptor_is_the_contract_block() -> None:
    descriptor = json.loads((ROOT / "ci/targets/ind-bank-003.json").read_text(encoding="utf-8"))
    assert descriptor["packetId"] == "IND-BANK-003"
    assert [target["name"] for target in descriptor["targets"]] == ["governance-integrations", "readiness-evaluate"]
    assert all(target["acceptedVariables"] == {"PACK": {"const": "banking"}} for target in descriptor["targets"])
