#!/usr/bin/env python3
"""Validate the inert destination porting ledger."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

EXPECTED = {
    "apiVersion": "harness.planeon.ai/porting-ledger/v1alpha1",
    "kind": "PortingLedger",
    "status": "NO_AUTHORIZATION",
    "authorizations": [],
    "appliedPorts": [],
}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_porting.py PORTING.yaml")
    value = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if value != EXPECTED:
        raise SystemExit("PORTING ledger must contain only the closed NO_AUTHORIZATION sentinel")
    serialized = str(value).casefold()
    for forbidden in ("sourcepath", "mapping", "copiedfile", "authorizationid"):
        if forbidden in serialized:
            raise SystemExit(f"PORTING ledger contains forbidden copy claim {forbidden}")
    print("PORTING validation: zero authorized source mappings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

