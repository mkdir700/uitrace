"""macOS platform implementation using Quartz."""

from __future__ import annotations

import re

from uitrace.core.models import Rect
from uitrace.errors import ErrorCode, UitError
from uitrace.platform.base import (
    PermissionReport,
    PermissionStatus,
    WindowRef,
)


class MacOSPlatform:
    """macOS implementation of Platform using Quartz/CoreGraphics."""

    def list_windows(self) -> list[WindowRef]:
        """List on-screen windows using CGWindowListCopyWindowInfo."""
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )

        window_info = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        )
        if window_info is None:
            return []

        windows: list[WindowRef] = []
        for info in window_info:
            bounds_dict = info.get("kCGWindowBounds")
            if bounds_dict is None:
                continue

            bounds = Rect(
                x=int(bounds_dict.get("X", 0)),
                y=int(bounds_dict.get("Y", 0)),
                w=int(bounds_dict.get("Width", 0)),
                h=int(bounds_dict.get("Height", 0)),
            )

            # Skip windows with zero size (menubar items, etc.)
            if bounds.w <= 1 or bounds.h <= 1:
                continue

            window_number = int(info.get("kCGWindowNumber", 0))
            owner_name = info.get("kCGWindowOwnerName")
            pid = int(info.get("kCGWindowOwnerPID", 0)) or None
            title = info.get("kCGWindowName")

            windows.append(
                WindowRef(
                    handle=str(window_number),
                    title=title,
                    pid=pid,
                    owner_name=owner_name,
                    bounds=bounds,
                    window_number=window_number,
                )
            )

        return windows

    def locate(self, selector) -> WindowRef | None:
        """Locate a window matching the selector."""
        windows = self.list_windows()
        for w in windows:
            if selector.pid is not None and w.pid != selector.pid:
                continue
            if selector.app is not None and w.owner_name != selector.app:
                continue
            if selector.title is not None and w.title != selector.title:
                continue
            if selector.title_regex is not None:
                if w.title is None or not re.search(selector.title_regex, w.title):
                    continue
            return w
        return None

    def focus(self, win: WindowRef) -> bool:
        """Focus a window's application."""
        if win.pid is None:
            return False
        try:
            from AppKit import NSRunningApplication

            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(win.pid)
            if app is None:
                return False
            # NSApplicationActivateIgnoringOtherApps
            return bool(app.activateWithOptions_(1 << 1))
        except Exception:
            return False

    def get_bounds(self, win: WindowRef) -> Rect | None:
        """Get current bounds for a window."""
        if win.window_number is None:
            return None
        windows = self.list_windows()
        for w in windows:
            if w.window_number == win.window_number:
                return w.bounds
        return None

    def check_permissions(self) -> PermissionReport:
        """Check macOS permissions."""
        from uitrace.tools.doctor import (
            _check_accessibility,
            _check_input_monitoring,
            _check_screen_recording,
        )

        acc = _check_accessibility()
        inp = _check_input_monitoring()
        scr = _check_screen_recording()

        def _to_status(d: dict) -> PermissionStatus:
            s = d.get("status", "unknown")
            if s == "granted":
                return PermissionStatus.granted
            if s == "denied":
                return PermissionStatus.denied
            return PermissionStatus.unknown

        hints: list[str] = []
        return PermissionReport(
            accessibility=_to_status(acc),
            input_monitoring=_to_status(inp),
            screen_recording=_to_status(scr),
            hints=hints,
        )

    def inject_click(self, x: int, y: int, button: str, count: int) -> None:
        """Inject click event. Implemented in Task 12."""
        raise UitError(
            code=ErrorCode.INJECTION_FAILED,
            message="Click injection not yet implemented",
        )

    def inject_scroll(self, x: int, y: int, delta_y: int) -> None:
        """Inject scroll event. Implemented in Task 12."""
        raise UitError(
            code=ErrorCode.INJECTION_FAILED,
            message="Scroll injection not yet implemented",
        )

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        """Get pixel color. Implemented in Task 17."""
        return None
