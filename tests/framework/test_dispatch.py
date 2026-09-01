from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("run_make_target", ROOT / "ci/run_make_target.py")
assert SPEC and SPEC.loader
DISPATCH = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = DISPATCH
SPEC.loader.exec_module(DISPATCH)


def _descriptor(packet: str = "IND-001", target: str = "verify", command: list[str] | None = None, variables: dict | None = None) -> dict:
    return {
        "schemaVersion": DISPATCH.SCHEMA_VERSION,
        "packetId": packet,
        "targets": [{"name": target, "acceptedVariables": variables or {}, "argvTemplate": [command or ["python3", "-c", "pass"]]}],
    }


def _write(directory: Path, value: dict, name: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name or f"{value['packetId'].lower()}.json")
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_real_descriptor_inventory_is_closed() -> None:
    rules = DISPATCH.load_rules(ROOT / "ci/targets")
    assert {(rule.packet_id, rule.name) for rule in rules} == {
        ("IND-001", "help"),
        ("IND-001", "prefetch"),
        ("IND-001", "pack-framework-test"),
        ("IND-001", "build-reproducible"),
        ("IND-001", "zero-bill"),
        ("IND-WG-001", "pack"),
        ("IND-WG-002", "data-readiness"),
        ("IND-WG-003", "governance-integrations"),
        ("IND-WG-004", "provider-profiles"),
        ("IND-WG-005", "certification-fixtures"),
    }


def test_missing_unknown_and_duplicate_targets_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(DISPATCH.TargetDescriptorError, match="no Make target descriptors"):
        DISPATCH.load_rules(tmp_path)
    _write(tmp_path, _descriptor())
    with pytest.raises(DISPATCH.TargetDescriptorError, match="zero applicable"):
        DISPATCH.dispatch("unknown", {}, tmp_path)
    value = _descriptor()
    value["targets"].append(value["targets"][0])
    _write(tmp_path, value)
    with pytest.raises(DISPATCH.TargetDescriptorError, match="duplicate target rule"):
        DISPATCH.load_rules(tmp_path)


def test_owner_filename_undeclared_variable_and_shell_fail_closed(tmp_path: Path) -> None:
    _write(tmp_path / "owner", _descriptor(), "wrong.json")
    with pytest.raises(DISPATCH.TargetDescriptorError, match="owner or filename mismatch"):
        DISPATCH.load_rules(tmp_path / "owner")
    _write(tmp_path / "variable", _descriptor(variables={"TOKEN": {"const": "value"}}))
    with pytest.raises(DISPATCH.TargetDescriptorError, match="undeclared Make variable"):
        DISPATCH.load_rules(tmp_path / "variable")
    _write(tmp_path / "shell", _descriptor(command=["sh", "-c", "true"]))
    with pytest.raises(DISPATCH.TargetDescriptorError, match="shell transport"):
        DISPATCH.load_rules(tmp_path / "shell")


def test_ambiguous_applicable_handler_and_duplicate_variables_fail_closed(tmp_path: Path) -> None:
    _write(tmp_path, _descriptor(packet="IND-001"))
    _write(tmp_path, _descriptor(packet="IND-002"))
    with pytest.raises(DISPATCH.TargetDescriptorError, match="ambiguous applicable handlers"):
        DISPATCH.dispatch("verify", {}, tmp_path)
    with pytest.raises(DISPATCH.TargetDescriptorError, match="duplicate Make variable"):
        DISPATCH.parse_supplied_variables(("PACK=a", "PACK=b"))
    with pytest.raises(DISPATCH.TargetDescriptorError, match="undeclared or malformed"):
        DISPATCH.parse_supplied_variables(("TOKEN=value",))
