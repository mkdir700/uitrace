"""Error handling for uitrace."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    """Exit codes for uitrace CLI."""

    INVALID_USAGE = 2
    WINDOW_NOT_FOUND = 10
    PERMISSION_DENIED = 11
    UNSUPPORTED_PLATFORM = 12
    ASSERTION_FAILED = 20
    INJECTION_FAILED = 30
    SCHEMA_INVALID = 40
    INTERRUPTED = 130


@dataclass(slots=True)
class UitError(Exception):
    """Unified error for uitrace."""

    code: ErrorCode
    message: str
    hint: str | None = None
    details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


def format_error(err: UitError) -> str:
    """Format error as a one-line summary."""
    parts = [f"[{err.code.name}] {err.message}"]
    if err.hint:
        parts.append(f"Hint: {err.hint}")
    return " ".join(parts)
