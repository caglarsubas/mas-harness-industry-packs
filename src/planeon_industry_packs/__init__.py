"""Deterministic, offline industry-pack framework with lazy runtime imports."""

from __future__ import annotations

from typing import Any

__all__ = ["PackValidationError", "ValidationReport", "ValidatedPack", "validate_pack"]
__version__ = "0.1.1"


def __getattr__(name: str) -> Any:
    if name == "PackValidationError":
        from .errors import PackValidationError

        return PackValidationError
    if name in {"ValidationReport", "ValidatedPack", "validate_pack"}:
        from .loader import ValidationReport, ValidatedPack, validate_pack

        return {"ValidationReport": ValidationReport, "ValidatedPack": ValidatedPack, "validate_pack": validate_pack}[name]
    raise AttributeError(name)
