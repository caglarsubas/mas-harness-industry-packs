from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = ROOT / "packs/white-goods"
SPEC = importlib.util.spec_from_file_location("ind_wg_005", ROOT / "ci/handlers/ind_wg_005.py")
assert SPEC and SPEC.loader
HANDLER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HANDLER
SPEC.loader.exec_module(HANDLER)


def _pack():
    return HANDLER.load_pack(PACK_ROOT, common_root=ROOT / "common")


def _json(path: str) -> dict:
    value = json.loads((PACK_ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_exact_five_source_contract_scenarios_bind_ready_predecessor_bytes() -> None:
    pack = _pack()
    scenarios = HANDLER.validate_scenarios(pack.files)
    assert tuple(scenarios) == HANDLER.SCENARIOS
    assert scenarios["regulated-openshift"]["bindings"]["governanceDecision"]["path"].endswith("ready-reversible-write.json")
    for slug in set(HANDLER.SCENARIOS) - {"regulated-openshift"}:
        assert scenarios[slug]["bindings"]["governanceDecision"]["path"].endswith("ready-read-only.json")
    assert all(scenario["expectedOutcome"] == "SOURCE_CONTRACT_READY" for scenario in scenarios.values())
    assert all(scenario["evidenceBoundary"] == HANDLER.EVIDENCE_BOUNDARY for scenario in scenarios.values())


def test_payload_lock_is_exact_non_recursive_and_canonical() -> None:
    pack = _pack()
    lock = _json(HANDLER.LOCK_PATH)
    HANDLER.validate_lock(pack.files, lock)
    assert lock == HANDLER.build_lock(pack.files)
    assert pack.files[HANDLER.LOCK_PATH] == HANDLER.document_bytes(lock)
    assert lock["excludedPaths"] == list(HANDLER.EXCLUDED_PATHS)
    assert len(lock["entries"]) == 70
    assert [entry["path"] for entry in lock["entries"]] == sorted(entry["path"] for entry in lock["entries"])
    assert {entry["license"] for entry in lock["entries"]} == {"Apache-2.0"}
    assert not (set(lock["excludedPaths"]) & {entry["path"] for entry in lock["entries"]})


def test_manifest_is_unsigned_not_retained_and_source_only() -> None:
    pack = _pack()
    lock = _json(HANDLER.LOCK_PATH)
    manifest = _json(HANDLER.MANIFEST_PATH)
    HANDLER.validate_manifest(manifest, lock, pack.files[HANDLER.LOCK_PATH])
    assert manifest == HANDLER.build_manifest(lock, pack.files[HANDLER.LOCK_PATH])
    assert pack.files[HANDLER.MANIFEST_PATH] == HANDLER.document_bytes(manifest)
    assert manifest["artifact"] == {"state": "NOT_RETAINED", "archiveSha256": None}
    assert manifest["releaseSigning"] == {
        "state": "MISSING_PLANNED",
        "algorithm": "ED25519",
        "signature": None,
        "signerId": None,
        "requiredBeforePublication": True,
    }
    assert manifest["evidenceBoundary"] == HANDLER.EVIDENCE_BOUNDARY


def test_exact_five_in_memory_tamper_vectors_fail_closed() -> None:
    pack = _pack()
    lock = _json(HANDLER.LOCK_PATH)
    manifest = _json(HANDLER.MANIFEST_PATH)
    catalog = HANDLER.validate_tamper_catalog(pack.files)
    results = HANDLER.verify_tamper_vectors(pack.files, lock, manifest, catalog["vectors"])
    assert results == {
        "white-goods.certification.tamper.content": "LOCK_MEMBER_DIGEST_MISMATCH",
        "white-goods.certification.tamper.missing": "LOCK_MEMBER_MISSING",
        "white-goods.certification.tamper.extra": "LOCK_UNDECLARED_MEMBER",
        "white-goods.certification.tamper.payload": "LOCK_PAYLOAD_DIGEST_MISMATCH",
        "white-goods.certification.tamper.manifest": "MANIFEST_LOCK_BINDING_MISMATCH",
    }


def test_handler_reports_reproducible_pack_and_separate_evidence_axes() -> None:
    completed = subprocess.run(
        [sys.executable, "ci/handlers/ind_wg_005.py", "white-goods"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(completed.stdout)
    assert output["packVersion"] == "0.5.0"
    assert output["scenarioCount"] == 5
    assert output["payloadEntryCount"] == 70
    assert output["retainedArtifacts"] is False
    assert output["evidence"] == HANDLER.EVIDENCE_BOUNDARY
    assert output["archiveSha256"] and output["indexSha256"] and output["manifestSha256"] and output["packDigest"]
