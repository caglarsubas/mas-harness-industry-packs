#!/usr/bin/env python3
"""Verify the immutable local toolchain; never fetch or mutate it."""

from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path

EXPECTED = {"jsonschema": "4.24.0", "PyYAML": "6.0.2", "pytest": "8.4.2"}


def main() -> int:
    if sys.version_info[:3] != (3, 12, 14):
        raise SystemExit("Python 3.12.14 is required")
    for distribution, expected in EXPECTED.items():
        actual = importlib.metadata.version(distribution)
        if actual != expected:
            raise SystemExit(f"{distribution} must be {expected}, got {actual}")
    lock = Path("uv.lock").read_text(encoding="utf-8")
    for expected in EXPECTED.values():
        if f'version = "{expected}"' not in lock:
            raise SystemExit(f"uv.lock does not pin {expected}")
    print("prefetch: immutable local Python 3.12 dependency closure is present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
