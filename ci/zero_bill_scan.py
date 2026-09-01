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
    workflow = (root / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    for forbidden in ("ubuntu-latest", "macos-latest", "windows-latest", "upload-artifact", "schedule:", "workflow_dispatch:"):
        if forbidden in workflow:
            raise SystemExit(f"zero-bill workflow forbids {forbidden}")
    if "self-hosted" not in workflow or "/opt/planeon/bin/harness-offline-launch" not in workflow:
        raise SystemExit("workflow must use the trusted self-hosted offline launcher")
    uses = re.findall(r"uses:\s*([^\s]+)", workflow)
    if uses != ["actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"]:
        raise SystemExit("workflow may use only the pinned credential-free checkout action")
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
