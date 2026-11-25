"""IND-BANK-003 readiness evaluator tests (`harness-pack readiness-evaluate <pack_root> --input <dir>`)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

from planeon_industry_packs import cli
from planeon_industry_packs.canonical import canonical_json_bytes
from planeon_industry_packs.loader import load_pack
from planeon_industry_packs.readiness import ReadinessInputError, evaluate, evaluate_readiness_fixture, luhn_run, personal_data_hits

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common"
PACK_ROOT = ROOT / "packs/banking"
INPUT = ROOT / "tests/fixtures/banking/evaluator/input"
EXPECTED = ROOT / "tests/fixtures/banking/evaluator/expected.json"
MEMBERS = (
    "data/api/product-catalogue.json", "data/events/transactions.jsonl", "data/files/product-terms.md",
    "data/postgresql/accounts.csv", "data/postgresql/parties.csv",
)


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def tenant_input(tmp_path: Path) -> Path:
    target = tmp_path / "input"
    shutil.copytree(INPUT, target)
    return target


def test_input_files_are_byte_equal_to_their_pack_counterparts() -> None:
    assert (INPUT / "source-inventory.json").read_bytes() == (PACK_ROOT / "fixtures/sources/source-inventory.json").read_bytes()
    for member in MEMBERS:
        assert (INPUT / member).read_bytes() == (PACK_ROOT / member).read_bytes()
    assert sorted(str(path.relative_to(INPUT)) for path in INPUT.rglob("*") if path.is_file()) == sorted(["source-inventory.json", *MEMBERS])


def test_verdict_equals_expected_byte_for_byte() -> None:
    verdict = evaluate(PACK_ROOT, INPUT)
    assert canonical_json_bytes(verdict) == EXPECTED.read_bytes()
    assert verdict["overallStatus"] == "READY"
    assert all(source["status"] == "PASS" for source in verdict["sources"])


def test_handler_readiness_form_matches_expected() -> None:
    handler = _load("ind_bank_003_handler_for_evaluator", "ci/handlers/ind_bank_003.py")
    verdict, accepted = handler.run_readiness()
    assert accepted is True and verdict == EXPECTED.read_bytes()


def test_cli_prints_the_canonical_verdict_and_exits_zero_on_ready(capsysbinary: pytest.CaptureFixture[bytes]) -> None:
    assert cli.main(["readiness-evaluate", str(PACK_ROOT), "--input", str(INPUT)]) == 0
    assert capsysbinary.readouterr().out == EXPECTED.read_bytes() + b"\n"


def test_cli_requires_input(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["readiness-evaluate", str(PACK_ROOT)])


def test_blocked_input_exits_one(tenant_input: Path, capsysbinary: pytest.CaptureFixture[bytes]) -> None:
    (tenant_input / "data/postgresql/parties.csv").unlink()
    verdict = evaluate(PACK_ROOT, tenant_input)
    assert verdict["overallStatus"] == "BLOCKED"
    postgresql = [source for source in verdict["sources"] if source["sourceClass"] == "postgresql"][0]
    assert postgresql["reasonCodes"] == ["DATA_RECONCILIATION_MISMATCH"]
    assert cli.main(["readiness-evaluate", str(PACK_ROOT), "--input", str(tenant_input)]) == 1


def test_personal_data_in_input_blocks(tenant_input: Path) -> None:
    path = tenant_input / "data/api/product-catalogue.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["records"][0]["productFamily"] = luhn_run()
    path.write_text(json.dumps(value), encoding="utf-8")
    verdict = evaluate(PACK_ROOT, tenant_input)
    api = [source for source in verdict["sources"] if source["sourceClass"] == "api"][0]
    assert api["reasonCodes"] == ["PERSONAL_DATA_FORBIDDEN"] and verdict["overallStatus"] == "BLOCKED"


def test_fails_closed_on_a_symlink(tenant_input: Path, capsys: pytest.CaptureFixture[str]) -> None:
    member = tenant_input / "data/postgresql/parties.csv"
    outside = tenant_input.parent / "outside.csv"
    shutil.copyfile(member, outside)
    member.unlink()
    os.symlink(outside, member)
    with pytest.raises(ReadinessInputError, match="symbolic link"):
        evaluate(PACK_ROOT, tenant_input)
    assert cli.main(["readiness-evaluate", str(PACK_ROOT), "--input", str(tenant_input)]) == 1
    assert json.loads(capsys.readouterr().out)["errors"][0]["reason"] == "READINESS_INPUT_REFUSED"


def test_fails_closed_on_a_symlinked_input_directory(tenant_input: Path) -> None:
    link = tenant_input.parent / "linked-input"
    os.symlink(tenant_input, link)
    with pytest.raises(ReadinessInputError):
        evaluate(PACK_ROOT, link)


def test_fails_closed_on_a_non_regular_file(tenant_input: Path) -> None:
    member = tenant_input / "data/files/product-terms.md"
    member.unlink()
    member.mkdir()
    with pytest.raises(ReadinessInputError, match="not a regular file"):
        evaluate(PACK_ROOT, tenant_input)


@pytest.mark.parametrize("escape", ["../outside.csv", "data/../../outside.csv", "/data/postgresql/parties.csv"])
def test_fails_closed_on_a_path_escaping_the_input(tenant_input: Path, escape: str) -> None:
    shutil.copyfile(tenant_input / "data/postgresql/parties.csv", tenant_input.parent / "outside.csv")
    inventory_path = tenant_input / "source-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    for source in inventory["sources"]:
        if source["sourceClass"] == "postgresql":
            source["dataPaths"] = ["data/postgresql/accounts.csv", escape]
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(ReadinessInputError, match="escapes"):
        evaluate(PACK_ROOT, tenant_input)


def test_evaluator_agrees_with_ind_bank_002_on_the_nine_readiness_fixtures() -> None:
    ib2 = _load("ind_bank_002_handler_for_evaluator", "ci/handlers/ind_bank_002.py")
    pack = load_pack(PACK_ROOT, common_root=COMMON)
    sources = ib2.check_source_inventory(json.loads(pack.files["fixtures/sources/source-inventory.json"]), pack.files["ontology/banking.ttl"].decode("utf-8"))
    policy = json.loads(pack.files["data/readiness-policy.json"])
    names = sorted(path for path in pack.files if path.startswith("fixtures/readiness/"))
    assert len(names) == 9
    for name in names:
        value = json.loads(pack.files[name])
        expected, _ = ib2.evaluate_fixture(value, sources, pack.files)
        assert evaluate_readiness_fixture(policy, value, pack.files) == expected, name
        assert expected == value["expectedDecision"], name


def test_the_evaluator_scanner_agrees_with_the_handler_scanner() -> None:
    ib2 = _load("ind_bank_002_handler_for_scanner", "ci/handlers/ind_bank_002.py")
    probe = luhn_run()
    assert personal_data_hits(f"ref {probe} end") == ib2.find_disallowed(f"ref {probe} end") == [probe]
    assert personal_data_hits("synthetic-evidence") == ib2.find_disallowed("synthetic-evidence") == []
