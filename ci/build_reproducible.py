#!/usr/bin/env python3
"""Build each framework and common-pack artifact twice and compare bytes."""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from planeon_industry_packs import build_backend  # noqa: E402
from planeon_industry_packs.canonical import canonical_json_bytes  # noqa: E402
from planeon_industry_packs.index import build_index  # noqa: E402
from planeon_industry_packs.package import archive_bytes  # noqa: E402


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="industry-build-a-") as first, tempfile.TemporaryDirectory(prefix="industry-build-b-") as second:
        first_path, second_path = Path(first), Path(second)
        wheel_name_a = build_backend.build_wheel(str(first_path))
        wheel_name_b = build_backend.build_wheel(str(second_path))
        sdist_name_a = build_backend.build_sdist(str(first_path))
        sdist_name_b = build_backend.build_sdist(str(second_path))
        artifacts = {
            "wheel": ((first_path / wheel_name_a).read_bytes(), (second_path / wheel_name_b).read_bytes()),
            "sdist": ((first_path / sdist_name_a).read_bytes(), (second_path / sdist_name_b).read_bytes()),
            "index": (canonical_json_bytes(build_index(ROOT / "common")), canonical_json_bytes(build_index(ROOT / "common"))),
            "pack": (archive_bytes(ROOT / "common")[1], archive_bytes(ROOT / "common")[1]),
        }
        for name, (left, right) in artifacts.items():
            if left != right:
                raise SystemExit(f"{name} is not byte reproducible")
            print(f"reproducible {name} sha256={_digest(left)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

