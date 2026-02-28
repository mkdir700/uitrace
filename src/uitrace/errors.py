"""Error handling for uitrace."""
from enum import IntEnum


class ErrorCode(IntEnum):
    """Exit codes for uitrace CLI."""
    INVALID_USAGE = 2
    WINDOW_NOT_FOUND = 10
    PERMISSION_DENIED = 11
    ASSERTION_FAILED = 20
    INJECTION_FAILED = 30
    SCHEMA_INVALID = 40
    UNSUPPORTED_PLATFORM = 11
    INTERRUPTED = 130


class UitError(Exception):
    """Unified error for uitrace."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        hint: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details


def format_error(err: UitError) -> str:
    """Format error as a one-line summary."""
    parts = [f"[{err.code.name}] {err.message}"]
    if err.hint:
        parts.append(f"Hint: {err.hint}")
    return " ".join(parts)
