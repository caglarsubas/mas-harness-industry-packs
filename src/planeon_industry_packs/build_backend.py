"""Dependency-free deterministic PEP 517 backend for framework artifacts."""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import os
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable

NAME = "planeon-harness-industry-packs"
NORMALIZED = "planeon_harness_industry_packs"
VERSION = "0.1.0"
DIST_INFO = f"{NORMALIZED}-{VERSION}.dist-info"
FIXED_EPOCH = 946684800
ROOT = Path(__file__).resolve().parents[2]


def _project_files() -> list[tuple[str, bytes]]:
    members: list[tuple[str, bytes]] = []
    for path in sorted((ROOT / "src" / "planeon_industry_packs").glob("*.py")):
        members.append((f"planeon_industry_packs/{path.name}", path.read_bytes()))
    for path in sorted((ROOT / "schemas").glob("*.json")):
        members.append((f"planeon_industry_packs/data/schemas/{path.name}", path.read_bytes()))
    for path in sorted((ROOT / "common").rglob("*")):
        if path.is_file():
            relative = path.relative_to(ROOT / "common").as_posix()
            members.append((f"planeon_industry_packs/data/common/{relative}", path.read_bytes()))
    return members


def _metadata() -> bytes:
    return (
        "Metadata-Version: 2.3\n"
        f"Name: {NAME}\n"
        f"Version: {VERSION}\n"
        "Summary: Offline deterministic industry guidance pack framework\n"
        "License-Expression: Apache-2.0\n"
        "Requires-Python: >=3.12\n"
        "Requires-Dist: jsonschema==4.24.0\n"
        "Requires-Dist: PyYAML==6.0.2\n"
        "\n"
    ).encode("utf-8")


def _wheel_members() -> list[tuple[str, bytes]]:
    return _project_files() + [
        (f"{DIST_INFO}/METADATA", _metadata()),
        (f"{DIST_INFO}/WHEEL", b"Wheel-Version: 1.0\nGenerator: planeon-deterministic-backend\nRoot-Is-Purelib: true\nTag: py3-none-any\n"),
        (f"{DIST_INFO}/entry_points.txt", b"[console_scripts]\nharness-pack = planeon_industry_packs.cli:main\n"),
        (f"{DIST_INFO}/licenses/LICENSE", (ROOT / "LICENSE").read_bytes()),
    ]


def _record_row(name: str, data: bytes) -> tuple[str, str, str]:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return name, f"sha256={digest}", str(len(data))


def _wheel_bytes() -> bytes:
    members = sorted(_wheel_members())
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in members:
        writer.writerow(_record_row(name, data))
    writer.writerow((f"{DIST_INFO}/RECORD", "", ""))
    members.append((f"{DIST_INFO}/RECORD", record.getvalue().encode("utf-8")))
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def _sdist_source_files() -> Iterable[tuple[str, bytes]]:
    fixed = ("pyproject.toml", "README.md", "LICENSE", "NOTICE")
    for name in fixed:
        yield name, (ROOT / name).read_bytes()
    for directory in ("src", "schemas", "common"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                yield path.relative_to(ROOT).as_posix(), path.read_bytes()


def _sdist_bytes() -> bytes:
    prefix = f"{NAME}-{VERSION}"
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for relative, data in sorted(_sdist_source_files()):
            info = tarfile.TarInfo(f"{prefix}/{relative}")
            info.size = len(data)
            info.mode = 0o644
            info.mtime = FIXED_EPOCH
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data))
    output = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=output, mode="wb", compresslevel=9, mtime=0) as stream:
        stream.write(tar_buffer.getvalue())
    return output.getvalue()


def _exclusive_write(directory: str, name: str, data: bytes) -> str:
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target = target_directory / name
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(descriptor, data)
    finally:
        os.close(descriptor)
    return name


def build_wheel(wheel_directory: str, config_settings: object = None, metadata_directory: str | None = None) -> str:
    del config_settings, metadata_directory
    name = f"{NORMALIZED}-{VERSION}-py3-none-any.whl"
    return _exclusive_write(wheel_directory, name, _wheel_bytes())


def build_sdist(sdist_directory: str, config_settings: object = None) -> str:
    del config_settings
    name = f"{NAME}-{VERSION}.tar.gz"
    return _exclusive_write(sdist_directory, name, _sdist_bytes())


def get_requires_for_build_wheel(config_settings: object = None) -> list[str]:
    del config_settings
    return []


def get_requires_for_build_sdist(config_settings: object = None) -> list[str]:
    del config_settings
    return []

