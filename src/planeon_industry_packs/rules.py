"""Closed pack-rule and resource static-safety validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from .errors import PackValidationError
from .io import load_structured

FORBIDDEN_KEYS = {
    "apikey", "api_key", "command", "credential", "credentials", "endpoint", "exec", "executable",
    "filesystem", "llm", "model", "network", "script", "secret", "secrets", "shell", "systemprompt",
    "system_prompt", "token", "toolcall", "tool_call", "url", "uri",
}
TEMPLATE_MARKERS = ("{{", "}}", "${", "{%", "%}")
REMOTE_PATTERN = re.compile(r"(?:https?|ftp)://", re.IGNORECASE)


def _schema_errors(schema: dict[str, Any], value: Any) -> Iterable[str]:
    for error in sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path)):
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        yield f"{location}: {error.message}"


def validate_static_data(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            folded = str(key).replace("-", "_").casefold()
            if folded in FORBIDDEN_KEYS:
                raise PackValidationError("UNSAFE_FIELD", f"field {key!r} is outside the data-only contract", path=path)
            validate_static_data(nested, path=path)
    elif isinstance(value, list):
        for nested in value:
            validate_static_data(nested, path=path)
    elif isinstance(value, str):
        if any(marker in value for marker in TEMPLATE_MARKERS):
            raise PackValidationError("TEMPLATE_FORBIDDEN", "template interpolation is forbidden", path=path)
        if REMOTE_PATTERN.search(value):
            raise PackValidationError("NETWORK_TARGET_FORBIDDEN", "remote targets are forbidden", path=path)


def validate_rule(data: bytes, path: str, schema: dict[str, Any]) -> dict[str, Any]:
    value = load_structured(data, path)
    if not isinstance(value, dict):
        raise PackValidationError("RULE_INVALID", "rule must be an object", path=path)
    errors = list(_schema_errors(schema, value))
    if errors:
        raise PackValidationError("RULE_INVALID", errors[0], path=path)
    validate_static_data(value, path=path)
    return value


def validate_resource_identity(value: Any, *, declared_id: str, declared_stage: str, path: str) -> None:
    if not isinstance(value, dict):
        raise PackValidationError("RESOURCE_INVALID", "structured resource must be an object", path=path)
    if value.get("id") != declared_id:
        raise PackValidationError("RESOURCE_ID_MISMATCH", "declared and file resource ids differ", path=path)
    if value.get("stage") != declared_stage:
        raise PackValidationError("RESOURCE_STAGE_MISMATCH", "declared and file stages differ", path=path)
    validate_static_data(value, path=path)


def is_structured(path: str) -> bool:
    return Path(path).suffix.casefold() in {".yaml", ".yml", ".json"}

