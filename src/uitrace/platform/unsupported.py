"""Unsupported platform stub that raises on every call."""
from __future__ import annotations

from uitrace.core.models import Rect, WindowSelector
from uitrace.errors import ErrorCode, UitError
from uitrace.platform.base import PermissionReport, WindowRef


def _unsupported() -> UitError:
    return UitError(
        code=ErrorCode.UNSUPPORTED_PLATFORM,
        message="This platform is not supported",
        hint="uitrace requires macOS",
    )


class UnsupportedPlatform:
    """Platform implementation that always raises UitError."""

    def list_windows(self) -> list[WindowRef]:
        raise _unsupported()

    def locate(self, selector: WindowSelector) -> WindowRef | None:
        raise _unsupported()

    def focus(self, win: WindowRef) -> bool:
        raise _unsupported()

    def get_bounds(self, win: WindowRef) -> Rect | None:
        raise _unsupported()

    def check_permissions(self) -> PermissionReport:
        raise _unsupported()

    def inject_click(self, x: int, y: int, button: str, count: int) -> None:
        raise _unsupported()

    def inject_scroll(self, x: int, y: int, delta_y: int) -> None:
        raise _unsupported()

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        raise _unsupported()
