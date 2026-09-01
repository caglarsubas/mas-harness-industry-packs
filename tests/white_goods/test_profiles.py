from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = ROOT / "packs/white-goods"
SPEC = importlib.util.spec_from_file_location("ind_wg_004", ROOT / "ci/handlers/ind_wg_004.py")
assert SPEC and SPEC.loader
HANDLER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HANDLER
SPEC.loader.exec_module(HANDLER)


def _load(relative: str) -> dict:
    value = json.loads((PACK_ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _profiles() -> dict[str, dict]:
    return HANDLER.validate_profile_catalog(_load("provider-preferences/profiles.json"))


def test_exact_five_profile_matrix_and_demands() -> None:
    binding = _load("provider-preferences/contract-binding.json")
    HANDLER.validate_contract_binding(binding)
    profiles = _profiles()
    assert set(profiles) == {"minimal-arm64", "minimal-amd64", "regulated-openshift", "silo", "air-gap"}
    for slug, profile in profiles.items():
        fixture = _load(profile["demandPath"])
        HANDLER.validate_demand(slug, profile, HANDLER.compile_request_from_fixture(slug, fixture))
    assert "connectivity.connected" in profiles["silo"]["environment"]["capabilities"]
    assert "connectivity.silo" in profiles["silo"]["environment"]["capabilities"]
    assert profiles["air-gap"]["isolationRequirements"]["networkPolicy"] == "DENY_ALL_OUTBOUND"
    assert profiles["regulated-openshift"]["environment"]["kubernetesDistribution"] == "openshift"


def test_all_golden_outputs_reconstruct_twice_and_remain_planned() -> None:
    for slug, profile in _profiles().items():
        envelope = _load(profile["expectedOutputEnvelopePath"])
        digests = HANDLER.validate_golden(slug, profile, envelope)
        assert tuple(digests) == HANDLER.OUTPUT_NAMES
        assert all(value.startswith("sha256:") for value in digests.values())


def test_missing_and_ambiguous_selectors_fail_closed() -> None:
    catalog = _load("provider-preferences/profiles.json")
    missing = copy.deepcopy(catalog)
    missing["profiles"][0]["acceptedSelections"].pop()
    with pytest.raises(ValueError, match="profile contract differs"):
        HANDLER.validate_profile_catalog(missing)
    ambiguous = copy.deepcopy(catalog)
    ambiguous["profiles"][0]["recommendations"].append(copy.deepcopy(ambiguous["profiles"][0]["recommendations"][1]))
    with pytest.raises(ValueError, match="two provider recommendations"):
        HANDLER.validate_profile_catalog(ambiguous)


def test_demand_selector_and_attestation_mutations_fail_closed() -> None:
    profile = _profiles()["minimal-amd64"]
    demand = HANDLER.compile_request_from_fixture("minimal-amd64", _load(profile["demandPath"]))
    demand["demand"]["requestedCapabilities"].remove("provider.planeon.llamacpp")
    with pytest.raises(ValueError, match="demand selection"):
        HANDLER.validate_demand("minimal-amd64", profile, demand)
    demand = HANDLER.compile_request_from_fixture("minimal-amd64", _load(profile["demandPath"]))
    demand["demand"]["environment"]["attestationDigest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="attestation"):
        HANDLER.validate_demand("minimal-amd64", profile, demand)


def test_tampered_output_digest_bom_and_evidence_escalation_fail_closed() -> None:
    profile = _profiles()["air-gap"]
    envelope = _load(profile["expectedOutputEnvelopePath"])
    tampered = copy.deepcopy(envelope)
    tampered["outputs"]["profile.json"]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="golden digest differs"):
        HANDLER.validate_golden("air-gap", profile, tampered)
    tampered = copy.deepcopy(envelope)
    tampered["evidenceBoundary"]["runtime"] = True
    with pytest.raises(ValueError, match="escalates evidence"):
        HANDLER.validate_golden("air-gap", profile, tampered)
    tampered = copy.deepcopy(envelope)
    extra = copy.deepcopy(tampered["outputs"]["bom.json"]["value"]["spec"]["entries"][0])
    extra["resourceId"] = "module.unselected.synthetic"
    tampered["outputs"]["bom.json"]["value"]["spec"]["entries"].append(extra)
    content = HANDLER.compiler_json_bytes(tampered["outputs"]["bom.json"]["value"])
    tampered["outputs"]["bom.json"]["sha256"] = "sha256:" + HANDLER._sha256(content)
    with pytest.raises(ValueError, match="BOM contains"):
        HANDLER.validate_golden("air-gap", profile, tampered)


def test_handler_reports_separate_evidence_axes_and_reproducible_pack() -> None:
    completed = subprocess.run(
        [sys.executable, "ci/handlers/ind_wg_004.py", "white-goods"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(completed.stdout)
    assert output["packVersion"] == "0.4.0"
    assert output["profileCount"] == 5
    assert output["retainedArtifacts"] is False
    assert output["evidence"] == HANDLER.EVIDENCE_BOUNDARY
    assert output["archiveSha256"] and output["indexSha256"] and output["packDigest"]
