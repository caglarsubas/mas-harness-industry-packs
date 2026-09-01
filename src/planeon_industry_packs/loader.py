"""IndustryPack loading, closure, binding, and overlay enforcement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .canonical import canonical_json_bytes, sha256_bytes
from .errors import PackValidationError
from .io import inventory, load_structured, media_type, normalize_relative, sha256_file_bytes
from .rules import is_structured, validate_resource_identity, validate_rule, validate_static_data

CONTENT_KEYS = ("questionnaires", "rules", "readiness", "ontologies", "controls", "providerPreferences", "fixtures")
STAGES = (
    "business-context", "domain-and-outcomes", "data-readiness", "governance-and-regulation",
    "integration-readiness", "harness-demand", "environment-and-provider-fit", "evidence-and-acceptance",
)


def _repository_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / "schemas").is_dir() else None


def _schema(name: str) -> dict[str, Any]:
    root = _repository_root()
    if root is not None:
        path = root / "schemas" / name
        return json.loads(path.read_text(encoding="utf-8"))
    package_path = resources.files("planeon_industry_packs").joinpath("data", "schemas", name)
    return json.loads(package_path.read_text(encoding="utf-8"))


def _validate_schema(value: Any, schema_name: str, *, reason: str, path: str) -> None:
    errors = sorted(
        Draft202012Validator(_schema(schema_name)).iter_errors(value),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        raise PackValidationError(reason, f"{location}: {error.message}", path=path)


def file_records(files: dict[str, bytes]) -> list[dict[str, Any]]:
    return [
        {"path": path, "mediaType": media_type(path), "size": len(data), "sha256": sha256_bytes(data)}
        for path, data in sorted(files.items())
        if path != "pack.index.json"
    ]


def pack_digest(files: dict[str, bytes]) -> str:
    return sha256_bytes(canonical_json_bytes(file_records(files)))


@dataclass(frozen=True, slots=True)
class ValidatedPack:
    root: Path
    manifest: dict[str, Any]
    journey: dict[str, Any]
    files: dict[str, bytes]
    digest: str
    resource_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    accepted: bool
    pack_id: str | None
    pack_version: str | None
    pack_digest: str | None
    errors: tuple[dict[str, str], ...]
    evidence: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "errors": list(self.errors),
            "evidence": self.evidence,
            "packDigest": self.pack_digest,
            "packId": self.pack_id,
            "packVersion": self.pack_version,
        }


def _closed_evidence() -> dict[str, bool]:
    return {"published": False, "runtimeEvidence": False, "assuranceEvidence": False, "tenantAcceptance": False}


def _default_common_root() -> Path:
    root = _repository_root()
    if root is not None:
        return root / "common"
    packaged = resources.files("planeon_industry_packs").joinpath("data", "common")
    candidate = Path(str(packaged))
    if not candidate.is_dir():
        raise PackValidationError("COMMON_ROOT_REQUIRED", "installed common.foundation data is unavailable")
    return candidate


def load_pack(root: Path, *, common_root: Path | None = None, _as_common: bool = False) -> ValidatedPack:
    files = inventory(root)
    if "pack.yaml" not in files:
        raise PackValidationError("MANIFEST_MISSING", "pack.yaml is required")
    manifest = load_structured(files["pack.yaml"], "pack.yaml")
    _validate_schema(manifest, "industry-pack.schema.json", reason="MANIFEST_SCHEMA_INVALID", path="pack.yaml")

    declared_paths = {"pack.yaml"}
    bindings = (manifest["compatibility"]["contractsLock"], manifest["journey"])
    for binding in bindings:
        normalized = normalize_relative(binding["path"])
        if normalized in declared_paths:
            raise PackValidationError("DUPLICATE_PATH", "a bound path is declared more than once", path=normalized)
        declared_paths.add(normalized)
        actual = sha256_file_bytes(files, normalized)
        if actual != binding["sha256"]:
            raise PackValidationError("BINDING_DIGEST_MISMATCH", f"expected {binding['sha256']}, got {actual}", path=normalized)

    contracts_path = manifest["compatibility"]["contractsLock"]["path"]
    contracts = load_structured(files[contracts_path], contracts_path)
    _validate_schema(contracts, "pack-contracts-lock.schema.json", reason="CONTRACTS_LOCK_INVALID", path=contracts_path)
    schema_paths = [entry["path"] for entry in contracts["schemas"]]
    if schema_paths != sorted(schema_paths) or len(set(schema_paths)) != 4:
        raise PackValidationError("CONTRACTS_LOCK_INVALID", "schema locks must be four unique lexically sorted records", path=contracts_path)

    journey_path = manifest["journey"]["path"]
    journey = load_structured(files[journey_path], journey_path)
    _validate_schema(journey, "industry-journey.schema.json", reason="JOURNEY_INVALID", path=journey_path)
    if tuple(stage["id"] for stage in journey["stages"]) != STAGES:
        raise PackValidationError("JOURNEY_ORDER_INVALID", "the eight foundational stages are immutable", path=journey_path)

    resource_ids: set[str] = set()
    rule_schema = _schema("pack-rule.schema.json")
    for category in CONTENT_KEYS:
        for resource in manifest["content"][category]:
            relative = normalize_relative(resource["path"])
            if relative in declared_paths:
                raise PackValidationError("DUPLICATE_PATH", "a content path is declared more than once", path=relative)
            declared_paths.add(relative)
            resource_id = resource["id"]
            if resource_id in resource_ids:
                raise PackValidationError("RESOURCE_ID_COLLISION", "resource ids must be globally unique within a pack", path=relative)
            resource_ids.add(resource_id)
            if relative not in files:
                raise PackValidationError("CONTENT_MISSING", "declared content file is absent", path=relative)
            suffix = Path(relative).suffix.casefold()
            if category == "rules":
                rule = validate_rule(files[relative], relative, rule_schema)
                validate_resource_identity(rule, declared_id=resource_id, declared_stage=resource["stage"], path=relative)
            elif is_structured(relative):
                value = load_structured(files[relative], relative)
                validate_resource_identity(value, declared_id=resource_id, declared_stage=resource["stage"], path=relative)
            else:
                try:
                    text = files[relative].decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise PackValidationError("UTF8_REQUIRED", "content must be UTF-8", path=relative) from exc
                validate_static_data(text, path=relative)
            if suffix in {".yaml", ".yml", ".json"} and files[relative].strip() == b"":
                raise PackValidationError("RESOURCE_INVALID", "structured content cannot be empty", path=relative)

    actual_paths = set(files)
    unlisted = sorted(actual_paths - declared_paths)
    missing = sorted(declared_paths - actual_paths)
    if missing:
        raise PackValidationError("CONTENT_MISSING", "declared file is absent", path=missing[0])
    if unlisted:
        raise PackValidationError("UNLISTED_FILE", "every pack file must be declared", path=unlisted[0])

    metadata = manifest["metadata"]
    if metadata["packKind"] == "COMMON":
        if metadata["id"] != "common.foundation" or metadata["version"] != "1.0.0" or metadata["industry"] != "all":
            raise PackValidationError("COMMON_IDENTITY_INVALID", "the common pack identity is fixed")
        if manifest["extends"] is not None:
            raise PackValidationError("COMMON_PARENT_FORBIDDEN", "the common pack cannot have a parent")
        if any(not item.startswith("common.") for item in resource_ids):
            raise PackValidationError("COMMON_RESOURCE_ID_INVALID", "common resource ids must use the common namespace")
    else:
        if _as_common:
            raise PackValidationError("COMMON_KIND_INVALID", "the overlay parent must be the common pack")
        if metadata["industry"] == "all" or metadata["id"] == "common.foundation":
            raise PackValidationError("SECTOR_IDENTITY_INVALID", "sector identity must be industry-specific")
        parent = load_pack(common_root or _default_common_root(), _as_common=True)
        expected_parent = manifest["extends"]
        if expected_parent is None or expected_parent["packDigest"] != parent.digest:
            raise PackValidationError("STALE_PARENT_DIGEST", "sector overlay must bind the computed common.foundation digest")
        if canonical_json_bytes(journey) != canonical_json_bytes(parent.journey):
            raise PackValidationError("JOURNEY_OVERRIDE_FORBIDDEN", "sector overlays cannot replace or reorder the common journey")
        if files[contracts_path] != parent.files[parent.manifest["compatibility"]["contractsLock"]["path"]]:
            raise PackValidationError("CONTRACTS_LOCK_OVERRIDE_FORBIDDEN", "sector overlays must retain the exact common contract lock")
        collision = sorted(resource_ids & parent.resource_ids)
        if collision:
            raise PackValidationError("COMMON_RESOURCE_COLLISION", f"sector resource shadows {collision[0]}")
        if any(item.startswith("common.") for item in resource_ids):
            raise PackValidationError("COMMON_NAMESPACE_RESERVED", "sector resources cannot use the common namespace")

    return ValidatedPack(root=root.resolve(), manifest=manifest, journey=journey, files=files, digest=pack_digest(files), resource_ids=frozenset(resource_ids))


def validate_pack(root: Path, *, common_root: Path | None = None) -> ValidationReport:
    try:
        pack = load_pack(root, common_root=common_root)
    except PackValidationError as exc:
        return ValidationReport(False, None, None, None, (exc.as_dict(),), _closed_evidence())
    metadata = pack.manifest["metadata"]
    return ValidationReport(True, metadata["id"], metadata["version"], pack.digest, (), _closed_evidence())
