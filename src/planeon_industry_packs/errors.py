"""Stable validation errors exposed by the framework and CLI."""

from __future__ import annotations


class PackValidationError(ValueError):
    """A fail-closed pack rejection with a machine-stable reason code."""

    def __init__(self, reason: str, detail: str, *, path: str | None = None) -> None:
        self.reason = reason
        self.detail = detail
        self.path = path
        location = f" [{path}]" if path else ""
        super().__init__(f"{reason}{location}: {detail}")

    def as_dict(self) -> dict[str, str]:
        result = {"reason": self.reason, "detail": self.detail}
        if self.path is not None:
            result["path"] = self.path
        return result

