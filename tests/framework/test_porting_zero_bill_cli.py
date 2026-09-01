from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from planeon_industry_packs.cli import main

ROOT = Path(__file__).resolve().parents[2]


def test_cli_validate_compile_and_package(tmp_path: Path, capsys) -> None:
    assert main(["validate", str(ROOT / "common")]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["accepted"] is True
    assert report["evidence"] == {
        "published": False,
        "runtimeEvidence": False,
        "assuranceEvidence": False,
        "tenantAcceptance": False,
    }
    index = tmp_path / "index.json"
    assert main(["compile-index", str(ROOT / "common"), "--output", str(index)]) == 0
    capsys.readouterr()
    artifact_dir = tmp_path / "artifact"
    assert main(["package", str(ROOT / "common"), "--output", str(artifact_dir)]) == 0
    capsys.readouterr()
    assert len(list(artifact_dir.iterdir())) == 1


def test_porting_is_exact_and_copy_claims_are_rejected(tmp_path: Path) -> None:
    completed = subprocess.run([sys.executable, str(ROOT / "ci/validate_porting.py"), str(ROOT / "PORTING.yaml")], check=False)
    assert completed.returncode == 0
    value = yaml.safe_load((ROOT / "PORTING.yaml").read_text(encoding="utf-8"))
    value["authorizations"] = [{"authorizationId": "not-authorized"}]
    invalid = tmp_path / "PORTING.yaml"
    invalid.write_text(yaml.safe_dump(value), encoding="utf-8")
    refused = subprocess.run([sys.executable, str(ROOT / "ci/validate_porting.py"), str(invalid)], check=False)
    assert refused.returncode != 0


def test_zero_bill_contract_passes() -> None:
    completed = subprocess.run([sys.executable, str(ROOT / "ci/zero_bill_scan.py"), str(ROOT)], check=False)
    assert completed.returncode == 0
