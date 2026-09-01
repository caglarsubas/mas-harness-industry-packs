from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from planeon_industry_packs import build_backend
from planeon_industry_packs.canonical import canonical_json_bytes, sha256_bytes
from planeon_industry_packs.errors import PackValidationError
from planeon_industry_packs.index import build_index, write_index
from planeon_industry_packs.loader import load_pack, validate_pack
from planeon_industry_packs.package import FIXED_EPOCH, archive_bytes, package_pack

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common"
SECTOR = ROOT / "tests/fixtures/framework/sector-valid"


def _copy_sector(tmp_path: Path) -> Path:
    target = tmp_path / "sector"
    shutil.copytree(SECTOR, target)
    return target


def _manifest(path: Path) -> dict:
    return yaml.safe_load((path / "pack.yaml").read_text(encoding="utf-8"))


def _write_manifest(path: Path, value: dict) -> None:
    (path / "pack.yaml").write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _reason(path: Path) -> str:
    report = validate_pack(path, common_root=COMMON)
    assert not report.accepted
    return report.errors[0]["reason"]


def test_common_and_sector_are_valid_and_evidence_stays_closed() -> None:
    common = validate_pack(COMMON)
    sector = validate_pack(SECTOR, common_root=COMMON)
    assert common.accepted and sector.accepted
    assert common.pack_id == "common.foundation"
    assert sector.pack_id == "manufacturing.example"
    assert common.pack_digest == "3cfea19e6e0a4a653d63622e250f40001b4f8221ebab18fa5bfc1601b8eddea3"
    assert common.evidence == {
        "published": False,
        "runtimeEvidence": False,
        "assuranceEvidence": False,
        "tenantAcceptance": False,
    }


def test_all_published_schemas_are_valid_draft_2020_12() -> None:
    names = {
        "industry-pack.schema.json",
        "industry-journey.schema.json",
        "pack-rule.schema.json",
        "pack-contracts-lock.schema.json",
        "pack-index.schema.json",
    }
    assert {path.name for path in (ROOT / "schemas").glob("*.json")} == names
    for path in (ROOT / "schemas").glob("*.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_contract_lock_pins_exact_con_007_authority_without_schema_bytes() -> None:
    value = json.loads((COMMON / "contracts.lock.json").read_text(encoding="utf-8"))
    assert value["commit"] == "2146278a95344cd2a8e22596b2f315b46edffc88"
    assert value["releaseManifestSha256"] == "c5dd4c39d1c69d07f8d8de3d1a09584bb906172fee2d5ac20ad25ff344b0db79"
    assert value["catalogDigest"] == "sha256:26d442c4e90a19d767d32e80ef9df3d154b3146d3238dc0eecf29ee773913a26"
    assert not any((COMMON / entry["path"]).exists() for entry in value["schemas"])


def test_common_journey_is_exact_and_contiguous() -> None:
    pack = load_pack(COMMON)
    assert [(stage["id"], stage["ordinal"]) for stage in pack.journey["stages"]] == [
        ("business-context", 1),
        ("domain-and-outcomes", 2),
        ("data-readiness", 3),
        ("governance-and-regulation", 4),
        ("integration-readiness", 5),
        ("harness-demand", 6),
        ("environment-and-provider-fit", 7),
        ("evidence-and-acceptance", 8),
    ]


def test_index_is_canonical_closed_and_self_digest_is_recomputed() -> None:
    index = build_index(COMMON)
    assert [record["path"] for record in index["files"]] == sorted(record["path"] for record in index["files"])
    assert "pack.index.json" not in {record["path"] for record in index["files"]}
    unsigned = dict(index)
    digest = unsigned.pop("indexDigest")
    assert digest == sha256_bytes(canonical_json_bytes(unsigned))
    assert index["packDigest"] == sha256_bytes(canonical_json_bytes(index["files"]))


def test_index_creation_is_exclusive(tmp_path: Path) -> None:
    output = tmp_path / "index.json"
    first = write_index(COMMON, output)
    assert json.loads(output.read_text(encoding="utf-8")) == first
    with pytest.raises(PackValidationError, match="OUTPUT_EXISTS"):
        write_index(COMMON, output)


def test_archive_is_byte_identical_sorted_fixed_and_data_only() -> None:
    name_a, first = archive_bytes(COMMON)
    name_b, second = archive_bytes(COMMON)
    assert name_a == name_b == "common.foundation-1.0.0.tar.gz"
    assert first == second
    with gzip.GzipFile(fileobj=io.BytesIO(first), mode="rb") as compressed:
        with tarfile.open(fileobj=io.BytesIO(compressed.read()), mode="r:") as archive:
            members = archive.getmembers()
            assert [member.name for member in members] == sorted(member.name for member in members)
            assert all(member.isfile() and member.mode == 0o644 and member.mtime == FIXED_EPOCH for member in members)
            assert "pack.index.json" in {member.name for member in members}


def test_package_directory_is_exclusive(tmp_path: Path) -> None:
    output = tmp_path / "artifact"
    artifact = package_pack(COMMON, output)
    assert artifact.is_file()
    with pytest.raises(PackValidationError, match="OUTPUT_EXISTS"):
        package_pack(COMMON, output)


def test_framework_wheel_sdist_and_record_are_reproducible(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    wheel_a = first / build_backend.build_wheel(str(first))
    wheel_b = second / build_backend.build_wheel(str(second))
    sdist_a = first / build_backend.build_sdist(str(first))
    sdist_b = second / build_backend.build_sdist(str(second))
    assert wheel_a.read_bytes() == wheel_b.read_bytes()
    assert sdist_a.read_bytes() == sdist_b.read_bytes()
    with zipfile.ZipFile(wheel_a) as wheel:
        record_name = next(name for name in wheel.namelist() if name.endswith(".dist-info/RECORD"))
        rows = list(csv.reader(io.StringIO(wheel.read(record_name).decode("utf-8"))))
        for name, digest, size in rows:
            if name == record_name:
                assert digest == size == ""
                continue
            data = wheel.read(name)
            encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
            assert digest == f"sha256={encoded}"
            assert size == str(len(data))


@pytest.mark.parametrize("suffix", [".py", ".sh", ".js", ".wasm"])
def test_executable_suffixes_are_rejected(tmp_path: Path, suffix: str) -> None:
    pack = _copy_sector(tmp_path)
    (pack / f"payload{suffix}").write_text("not executable", encoding="utf-8")
    assert _reason(pack) == "EXECUTABLE_CONTENT"


def test_executable_mode_is_rejected(tmp_path: Path) -> None:
    pack = _copy_sector(tmp_path)
    resource = pack / "questionnaires/quality.yaml"
    resource.chmod(0o755)
    assert _reason(pack) == "EXECUTABLE_MODE"


def test_link_and_linked_root_are_rejected(tmp_path: Path) -> None:
    pack = _copy_sector(tmp_path)
    os.symlink(pack / "journey.yaml", pack / "linked.yaml")
    assert _reason(pack) == "LINK_FORBIDDEN"
    linked_root = tmp_path / "linked-root"
    os.symlink(pack, linked_root)
    assert _reason(linked_root) == "PACK_ROOT_INVALID"


def test_hidden_and_unlisted_files_are_rejected(tmp_path: Path) -> None:
    pack = _copy_sector(tmp_path)
    (pack / ".concealed.json").write_text("{}", encoding="utf-8")
    assert _reason(pack) == "HIDDEN_PATH"
    (pack / ".concealed.json").unlink()
    (pack / "extra.json").write_text("{}", encoding="utf-8")
    assert _reason(pack) == "UNLISTED_FILE"


def test_duplicate_yaml_and_json_keys_are_rejected(tmp_path: Path) -> None:
    pack = _copy_sector(tmp_path)
    (pack / "pack.yaml").write_text("apiVersion: one\napiVersion: two\n", encoding="utf-8")
    assert _reason(pack) == "DUPLICATE_KEY"
    pack = _copy_sector(tmp_path / "json-case")
    manifest = _manifest(pack)
    manifest["content"]["fixtures"] = [{"id": "manufacturing.fixture.duplicate", "stage": "evidence-and-acceptance", "path": "duplicate.json"}]
    _write_manifest(pack, manifest)
    (pack / "duplicate.json").write_text('{"id":"manufacturing.fixture.duplicate","id":"again","stage":"evidence-and-acceptance"}', encoding="utf-8")
    assert _reason(pack) == "DUPLICATE_KEY"


def test_custom_yaml_tag_is_rejected(tmp_path: Path) -> None:
    pack = _copy_sector(tmp_path)
    (pack / "pack.yaml").write_text("!unsafe {}\n", encoding="utf-8")
    assert _reason(pack) == "STRUCTURED_DATA_INVALID"


def test_manifest_is_closed_and_paths_cannot_traverse(tmp_path: Path) -> None:
    pack = _copy_sector(tmp_path)
    manifest = _manifest(pack)
    manifest["unexpected"] = True
    _write_manifest(pack, manifest)
    assert _reason(pack) == "MANIFEST_SCHEMA_INVALID"
    pack = _copy_sector(tmp_path / "traversal")
    manifest = _manifest(pack)
    manifest["journey"]["path"] = "../journey.yaml"
    _write_manifest(pack, manifest)
    assert _reason(pack) == "MANIFEST_SCHEMA_INVALID"


def test_rule_operator_action_template_network_and_identity_fail_closed(tmp_path: Path) -> None:
    mutations = [
        ("when", {"eval": "answers.value"}, "RULE_INVALID"),
        ("action", {"type": "DELETE_DATA", "target": "manufacturing.target", "message": "blocked"}, "RULE_INVALID"),
        ("message", "{{ answers.value }}", "TEMPLATE_FORBIDDEN"),
        ("message", "See https://example.invalid", "NETWORK_TARGET_FORBIDDEN"),
        ("id", "manufacturing.different", "RESOURCE_ID_MISMATCH"),
    ]
    for index, (field, value, expected) in enumerate(mutations):
        pack = _copy_sector(tmp_path / str(index))
        rule_path = pack / "rules/require-evidence.yaml"
        rule = yaml.safe_load(rule_path.read_text(encoding="utf-8"))
        if field == "message":
            rule["action"]["message"] = value
        else:
            rule[field] = value
        rule_path.write_text(yaml.safe_dump(rule, sort_keys=False), encoding="utf-8")
        assert _reason(pack) == expected


def test_stale_parent_journey_override_contract_override_and_collision_are_rejected(tmp_path: Path) -> None:
    pack = _copy_sector(tmp_path / "stale")
    manifest = _manifest(pack)
    manifest["extends"]["packDigest"] = "0" * 64
    _write_manifest(pack, manifest)
    assert _reason(pack) == "STALE_PARENT_DIGEST"

    pack = _copy_sector(tmp_path / "journey")
    journey_path = pack / "journey.yaml"
    journey = yaml.safe_load(journey_path.read_text(encoding="utf-8"))
    journey["stages"][0]["title"] = "Replacement"
    journey_path.write_text(yaml.safe_dump(journey, sort_keys=False), encoding="utf-8")
    manifest = _manifest(pack)
    manifest["journey"]["sha256"] = hashlib.sha256(journey_path.read_bytes()).hexdigest()
    _write_manifest(pack, manifest)
    assert _reason(pack) == "JOURNEY_OVERRIDE_FORBIDDEN"

    pack = _copy_sector(tmp_path / "lock")
    lock_path = pack / "contracts.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["catalogDigest"] = "sha256:" + "0" * 64
    lock_path.write_bytes(canonical_json_bytes(lock) + b"\n")
    manifest = _manifest(pack)
    manifest["compatibility"]["contractsLock"]["sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    _write_manifest(pack, manifest)
    assert _reason(pack) == "CONTRACTS_LOCK_OVERRIDE_FORBIDDEN"

    pack = _copy_sector(tmp_path / "collision")
    manifest = _manifest(pack)
    manifest["content"]["questionnaires"][0]["id"] = "common.business-context.owner"
    questionnaire = yaml.safe_load((pack / "questionnaires/quality.yaml").read_text(encoding="utf-8"))
    questionnaire["id"] = "common.business-context.owner"
    (pack / "questionnaires/quality.yaml").write_text(yaml.safe_dump(questionnaire, sort_keys=False), encoding="utf-8")
    _write_manifest(pack, manifest)
    assert _reason(pack) == "COMMON_RESOURCE_COLLISION"


def test_duplicate_resource_ids_and_oversize_files_are_rejected(tmp_path: Path) -> None:
    pack = _copy_sector(tmp_path / "collision")
    manifest = _manifest(pack)
    manifest["content"]["fixtures"] = [{"id": "manufacturing.quality.objective", "stage": "evidence-and-acceptance", "path": "fixture.json"}]
    _write_manifest(pack, manifest)
    (pack / "fixture.json").write_text('{"id":"manufacturing.quality.objective","stage":"evidence-and-acceptance"}', encoding="utf-8")
    assert _reason(pack) == "RESOURCE_ID_COLLISION"

    pack = _copy_sector(tmp_path / "large")
    (pack / "extra.txt").write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    assert _reason(pack) == "FILE_TOO_LARGE"
