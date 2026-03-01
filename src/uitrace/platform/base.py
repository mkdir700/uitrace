"""Base platform abstractions for uitrace."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from uitrace.core.models import Rect, WindowSelector


@dataclass(slots=True)
class WindowRef:
    """Reference to a window on the current platform."""

    handle: str
    title: str | None
    pid: int | None
    owner_name: str | None
    bounds: Rect
    window_number: int | None = None


class PermissionStatus(Enum):
    """Status of a system permission."""

    granted = "granted"
    denied = "denied"
    unknown = "unknown"


@dataclass(slots=True)
class PermissionReport:
    """Report of required system permissions."""

    accessibility: PermissionStatus
    input_monitoring: PermissionStatus
    screen_recording: PermissionStatus
    hints: list[str] = field(default_factory=list)


@runtime_checkable
class Platform(Protocol):
    """Platform abstraction protocol.

    Each supported OS provides a concrete implementation.
    """

    def list_windows(self) -> list[WindowRef]:
        """Return all visible windows."""
        ...

    def locate(self, selector: WindowSelector) -> WindowRef | None:
        """Find a window matching *selector*, or None."""
        ...

    def focus(self, win: WindowRef) -> bool:
        """Bring *win* to the foreground. Return True on success."""
        ...

    def get_bounds(self, win: WindowRef) -> Rect | None:
        """Return current bounds of *win*, or None if unavailable."""
        ...

    def check_permissions(self) -> PermissionReport:
        """Check required OS permissions."""
        ...

    def inject_click(self, x: int, y: int, button: str, count: int) -> None:
        """Inject a mouse click at screen coordinates."""
        ...

    def inject_scroll(self, x: int, y: int, delta_y: int) -> None:
        """Inject a scroll event at screen coordinates."""
        ...

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        """Return (r, g, b) for the pixel at screen coordinates, or None."""
        ...

    def window_from_point(self, x: int, y: int) -> WindowRef | None:
        """Return the topmost window at screen coordinates (x, y), or None."""
        ...
