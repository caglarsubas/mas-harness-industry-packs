#!/usr/bin/env python3
"""Deterministic, non-recursive white-goods payload-lock primitives."""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Mapping

from planeon_industry_packs.canonical import canonical_json_bytes
from planeon_industry_packs.io import media_type

PACK_ID = "white-goods.manufacturing"
PACK_VERSION = "0.5.0"
LOCK_PATH = "pack.lock.json"
MANIFEST_PATH = "manifest.json"
EXCLUDED_PATHS = (MANIFEST_PATH, LOCK_PATH)
ALGORITHM = "SHA-256"
CANONICALIZATION = "SORTED_UTF8_JSON_V1"
LICENSE = "Apache-2.0"
AUTHORITY_PACKETS = (
    "IND-001",
    "IND-WG-001",
    "IND-WG-002",
    "IND-WG-003",
    "IND-WG-004",
    "IND-WG-005",
)
EVIDENCE_BOUNDARY = {
    "source": True,
    "candidate": False,
    "ci": False,
    "merge": False,
    "artifact": False,
    "publication": False,
    "deployment": False,
    "runtime": False,
    "assurance": False,
    "crossRepositoryConformance": False,
    "tenantAcceptance": False,
}


class CertificationManifestError(ValueError):
    """Stable fail-closed validation error."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _refuse(reason: str) -> None:
    raise CertificationManifestError(reason)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def document_bytes(value: Any) -> bytes:
    """Return the committed canonical JSON representation."""

    return canonical_json_bytes(value) + b"\n"


def _payload_subject(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "algorithm": ALGORITHM,
        "canonicalization": CANONICALIZATION,
        "excludedPaths": list(EXCLUDED_PATHS),
        "entries": entries,
    }


def _entry(path: str, value: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "mediaType": media_type(path),
        "size": len(value),
        "sha256": _sha256(value),
        "license": LICENSE,
    }


def build_lock(files: Mapping[str, bytes]) -> dict[str, Any]:
    """Build a payload lock without binding the lock or manifest recursively."""

    entries = [_entry(path, value) for path, value in sorted(files.items()) if path not in EXCLUDED_PATHS]
    return {
        "apiVersion": "harness.planeon.ai/industry-pack-lock/v1alpha1",
        "kind": "IndustryPackLock",
        "id": "white-goods.certification.pack-lock",
        "stage": "evidence-and-acceptance",
        "pack": {"id": PACK_ID, "version": PACK_VERSION},
        "algorithm": ALGORITHM,
        "canonicalization": CANONICALIZATION,
        "excludedPaths": list(EXCLUDED_PATHS),
        "licenseDisposition": LICENSE,
        "entries": entries,
        "payloadDigest": _sha256(canonical_json_bytes(_payload_subject(entries))),
    }


def build_manifest(lock: Mapping[str, Any], lock_bytes: bytes) -> dict[str, Any]:
    """Build the unsigned source manifest that binds exact lock bytes."""

    entries = lock.get("entries")
    payload_digest = lock.get("payloadDigest")
    if not isinstance(entries, list) or not isinstance(payload_digest, str):
        _refuse("MANIFEST_LOCK_INVALID")
    return {
        "apiVersion": "harness.planeon.ai/industry-pack-artifact-manifest/v1alpha1",
        "kind": "IndustryPackArtifactManifest",
        "id": "white-goods.certification.artifact-manifest",
        "stage": "evidence-and-acceptance",
        "pack": {"id": PACK_ID, "version": PACK_VERSION},
        "packLock": {
            "path": LOCK_PATH,
            "sha256": _sha256(lock_bytes),
            "payloadDigest": payload_digest,
            "entryCount": len(entries),
        },
        "sourceProvenance": {
            "repository": "caglarsubas/mas-harness-industry-packs",
            "authorityPackets": list(AUTHORITY_PACKETS),
            "cleanRoom": True,
            "warmSourceBytesCopied": False,
        },
        "licenseDisposition": {
            "spdx": LICENSE,
            "redistributable": True,
            "thirdPartyFileCount": 0,
        },
        "artifact": {"state": "NOT_RETAINED", "archiveSha256": None},
        "releaseSigning": {
            "state": "MISSING_PLANNED",
            "algorithm": "ED25519",
            "signature": None,
            "signerId": None,
            "requiredBeforePublication": True,
        },
        "evidenceBoundary": dict(EVIDENCE_BOUNDARY),
    }


def validate_lock(files: Mapping[str, bytes], lock: Mapping[str, Any]) -> None:
    """Validate inventory and bytes with stable mutation denial reasons."""

    required_fields = {
        "apiVersion",
        "kind",
        "id",
        "stage",
        "pack",
        "algorithm",
        "canonicalization",
        "excludedPaths",
        "licenseDisposition",
        "entries",
        "payloadDigest",
    }
    if set(lock) != required_fields:
        _refuse("LOCK_FIELDS_MISMATCH")
    expected_header = {
        "apiVersion": "harness.planeon.ai/industry-pack-lock/v1alpha1",
        "kind": "IndustryPackLock",
        "id": "white-goods.certification.pack-lock",
        "stage": "evidence-and-acceptance",
        "pack": {"id": PACK_ID, "version": PACK_VERSION},
        "algorithm": ALGORITHM,
        "canonicalization": CANONICALIZATION,
        "excludedPaths": list(EXCLUDED_PATHS),
        "licenseDisposition": LICENSE,
    }
    if any(lock.get(field) != value for field, value in expected_header.items()):
        _refuse("LOCK_HEADER_MISMATCH")
    entries = lock.get("entries")
    if not isinstance(entries, list):
        _refuse("LOCK_ENTRIES_INVALID")
    entry_fields = {"path", "mediaType", "size", "sha256", "license"}
    if any(not isinstance(entry, dict) or set(entry) != entry_fields for entry in entries):
        _refuse("LOCK_ENTRIES_INVALID")
    paths = [entry["path"] for entry in entries]
    if not all(isinstance(path, str) for path in paths) or paths != sorted(paths) or len(paths) != len(set(paths)):
        _refuse("LOCK_ENTRY_ORDER_INVALID")
    actual_paths = set(files) - set(EXCLUDED_PATHS)
    entry_paths = set(paths)
    if entry_paths - actual_paths:
        _refuse("LOCK_MEMBER_MISSING")
    if actual_paths - entry_paths:
        _refuse("LOCK_UNDECLARED_MEMBER")
    for entry in entries:
        path = entry["path"]
        value = files[path]
        if entry["mediaType"] != media_type(path):
            _refuse("LOCK_MEMBER_MEDIA_TYPE_MISMATCH")
        if entry["size"] != len(value):
            _refuse("LOCK_MEMBER_SIZE_MISMATCH")
        if entry["sha256"] != _sha256(value):
            _refuse("LOCK_MEMBER_DIGEST_MISMATCH")
        if entry["license"] != LICENSE:
            _refuse("LOCK_MEMBER_LICENSE_MISMATCH")
    expected_payload = _sha256(canonical_json_bytes(_payload_subject(entries)))
    if lock.get("payloadDigest") != expected_payload:
        _refuse("LOCK_PAYLOAD_DIGEST_MISMATCH")


def validate_manifest(manifest: Mapping[str, Any], lock: Mapping[str, Any], lock_bytes: bytes) -> None:
    """Validate the unsigned manifest and its exact lock-file binding."""

    pack_lock = manifest.get("packLock")
    if not isinstance(pack_lock, dict):
        _refuse("MANIFEST_LOCK_INVALID")
    if pack_lock.get("sha256") != _sha256(lock_bytes):
        _refuse("MANIFEST_LOCK_BINDING_MISMATCH")
    if pack_lock.get("payloadDigest") != lock.get("payloadDigest") or pack_lock.get("entryCount") != len(lock.get("entries", [])):
        _refuse("MANIFEST_LOCK_SUMMARY_MISMATCH")
    if manifest != build_manifest(lock, lock_bytes):
        _refuse("MANIFEST_FIELDS_MISMATCH")


def verify_tamper_vectors(
    files: Mapping[str, bytes],
    lock: Mapping[str, Any],
    manifest: Mapping[str, Any],
    vectors: list[dict[str, Any]],
) -> dict[str, str]:
    """Apply declared mutations to in-memory copies and return denial reasons."""

    results: dict[str, str] = {}
    for vector in vectors:
        if not isinstance(vector, dict) or set(vector) != {"id", "mutationKind", "targetPath", "expectedReason"}:
            _refuse("TAMPER_VECTOR_FIELDS_MISMATCH")
        vector_id = vector["id"]
        if not isinstance(vector_id, str) or vector_id in results:
            _refuse("TAMPER_VECTOR_ID_INVALID")
        mutated_files = dict(files)
        mutated_lock = copy.deepcopy(lock)
        mutated_manifest = copy.deepcopy(manifest)
        mutation = vector["mutationKind"]
        target = vector["targetPath"]
        try:
            if mutation == "CONTENT_BYTES_CHANGED":
                value = mutated_files.get(target)
                if not isinstance(value, bytes) or b"SOURCE_CONTRACT_READY" not in value:
                    _refuse("TAMPER_VECTOR_TARGET_INVALID")
                mutated_files[target] = value.replace(b"SOURCE_CONTRACT_READY", b"SOURCE_CONTRACT_READX", 1)
                validate_lock(mutated_files, mutated_lock)
            elif mutation == "MEMBER_MISSING":
                if mutated_files.pop(target, None) is None:
                    _refuse("TAMPER_VECTOR_TARGET_INVALID")
                validate_lock(mutated_files, mutated_lock)
            elif mutation == "UNDECLARED_MEMBER":
                if target in mutated_files:
                    _refuse("TAMPER_VECTOR_TARGET_INVALID")
                mutated_files[target] = b"{}\n"
                validate_lock(mutated_files, mutated_lock)
            elif mutation == "LOCK_PAYLOAD_DIGEST_CHANGED":
                if target != LOCK_PATH:
                    _refuse("TAMPER_VECTOR_TARGET_INVALID")
                mutated_lock["payloadDigest"] = "0" * 64
                validate_lock(mutated_files, mutated_lock)
            elif mutation == "MANIFEST_LOCK_BINDING_CHANGED":
                if target != MANIFEST_PATH:
                    _refuse("TAMPER_VECTOR_TARGET_INVALID")
                mutated_manifest["packLock"]["sha256"] = "0" * 64
                validate_manifest(mutated_manifest, mutated_lock, document_bytes(mutated_lock))
            else:
                _refuse("TAMPER_MUTATION_UNKNOWN")
        except CertificationManifestError as exc:
            if exc.reason != vector["expectedReason"]:
                _refuse("TAMPER_REASON_MISMATCH")
            results[vector_id] = exc.reason
            continue
        _refuse("TAMPER_MUTATION_ACCEPTED")
    return results
