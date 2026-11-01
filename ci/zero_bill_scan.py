#!/usr/bin/env python3
"""Enforce credential-free, self-hosted, non-publishing defaults."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

EXPECTED_DEPENDENCIES = {"jsonschema==4.24.0", "PyYAML==6.0.2"}


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) == 2 else ".").resolve()
    workflows = root / ".github" / "workflows"
    if workflows.is_symlink() or (workflows.exists() and not workflows.is_dir()) or (
        workflows.is_dir() and any(entry.is_symlink() or not entry.is_dir() for entry in workflows.rglob("*"))
    ):
        raise SystemExit("zero-bill forbids repository workflow files: verification runs only through the hosted verifier")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    if set(project["project"]["dependencies"]) != EXPECTED_DEPENDENCIES:
        raise SystemExit("runtime dependency surface is not closed")
    if set(project["dependency-groups"]["dev"]) != {"pytest==8.4.2", "rdflib==7.6.0", "pyshacl==0.40.1"}:
        raise SystemExit("development dependency surface is not closed")
    if any((root / name).exists() for name in ("Dockerfile", "docker-compose.yml", "compose.yaml")):
        raise SystemExit("IND-001 does not authorize container or cloud provisioning")
    print("zero-bill validation: self-hosted, credential-free, no publication or remote storage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
