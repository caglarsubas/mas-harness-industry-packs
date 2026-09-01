"""Canonical PackIndex production."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .canonical import canonical_json_bytes, sha256_bytes
from .errors import PackValidationError
from .loader import _schema, file_records, load_pack


def build_index(root: Path, *, common_root: Path | None = None) -> dict[str, Any]:
    pack = load_pack(root, common_root=common_root)
    metadata = pack.manifest["metadata"]
    payload: dict[str, Any] = {
        "apiVersion": "harness.planeon.ai/pack-index/v1alpha1",
        "kind": "PackIndex",
        "pack": {"id": metadata["id"], "version": metadata["version"]},
        "files": file_records(pack.files),
        "packDigest": pack.digest,
        "evidence": {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False},
    }
    payload["indexDigest"] = sha256_bytes(canonical_json_bytes(payload))
    errors = list(Draft202012Validator(_schema("pack-index.schema.json")).iter_errors(payload))
    if errors:
        raise PackValidationError("INDEX_SCHEMA_INVALID", errors[0].message)
    return payload


def write_index(root: Path, output: Path, *, common_root: Path | None = None) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise PackValidationError("OUTPUT_EXISTS", "index output must not already exist", path=str(output))
    if not output.parent.is_dir():
        raise PackValidationError("OUTPUT_PARENT_MISSING", "index output parent must already exist", path=str(output.parent))
    payload = build_index(root, common_root=common_root)
    data = canonical_json_bytes(payload) + b"\n"
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(descriptor, data)
    finally:
        os.close(descriptor)
    return payload

