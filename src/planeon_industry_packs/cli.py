"""Credential-free `harness-pack` command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .canonical import canonical_json_bytes
from .errors import PackValidationError
from .index import write_index
from .package import package_pack
from .loader import validate_pack

EVIDENCE = {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness-pack")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("pack_root", type=Path)
    compile_index = commands.add_parser("compile-index")
    compile_index.add_argument("pack_root", type=Path)
    compile_index.add_argument("--output", required=True, type=Path)
    package = commands.add_parser("package")
    package.add_argument("pack_root", type=Path)
    package.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "validate":
            report = validate_pack(arguments.pack_root)
            sys.stdout.buffer.write(canonical_json_bytes(report.as_dict()) + b"\n")
            return 0 if report.accepted else 1
        if arguments.command == "compile-index":
            payload = write_index(arguments.pack_root, arguments.output)
            print(json.dumps({"accepted": True, "evidence": EVIDENCE, "indexDigest": payload["indexDigest"], "output": str(arguments.output)}, sort_keys=True, separators=(",", ":")))
            return 0
        output = package_pack(arguments.pack_root, arguments.output)
        print(json.dumps({"accepted": True, "evidence": EVIDENCE, "output": str(output)}, sort_keys=True, separators=(",", ":")))
        return 0
    except PackValidationError as exc:
        print(json.dumps({"accepted": False, "errors": [exc.as_dict()], "evidence": EVIDENCE}, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
