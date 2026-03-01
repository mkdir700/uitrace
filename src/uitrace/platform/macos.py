"""macOS platform implementation using Quartz."""

from __future__ import annotations

import re
import time

from uitrace.core.models import Rect, WindowSelector
from uitrace.platform.base import (
    PermissionReport,
    PermissionStatus,
    WindowRef,
)


def _rect_contains_point(bounds: Rect, x: int, y: int) -> bool:
    """Return True if (x, y) is within *bounds* (inclusive edges)."""
    return (
        bounds.x <= x <= bounds.x + bounds.w
        and bounds.y <= y <= bounds.y + bounds.h
    )


class MacOSPlatform:
    """macOS implementation of Platform using Quartz/CoreGraphics."""

    def __init__(self) -> None:
        self._wfp_cache: tuple[float, list] | None = None

    def list_windows(self) -> list[WindowRef]:
        """List on-screen windows using CGWindowListCopyWindowInfo."""
        from Quartz import (  # type: ignore[import-untyped]
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
            # Skip system decoration windows (shadows, rounded corners).
            if info.get("kCGWindowOwnerName") == "WindowManager":
                continue

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

    def window_from_point(self, x: int, y: int) -> WindowRef | None:
        """Return the topmost window whose bounds contain *(x, y)*.

        Uses a short-lived cache (50 ms TTL) for the window list to
        avoid repeated CGWindowListCopyWindowInfo calls during
        high-frequency hit-testing (e.g. mouse-move recording).
        """
        from Quartz import (  # type: ignore[import-untyped]
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )

        _WFP_TTL = 0.05  # 50 ms

        now = time.monotonic()
        if self._wfp_cache is not None and (now - self._wfp_cache[0]) < _WFP_TTL:
            window_info = self._wfp_cache[1]
        else:
            window_info = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID
            )
            if window_info is None:
                window_info = []
            self._wfp_cache = (now, window_info)

        for info in window_info:
            # Only consider normal-layer windows (layer 0).
            if int(info.get("kCGWindowLayer", -1)) != 0:
                continue

            bounds_dict = info.get("kCGWindowBounds")
            if bounds_dict is None:
                continue

            bounds = Rect(
                x=int(bounds_dict.get("X", 0)),
                y=int(bounds_dict.get("Y", 0)),
                w=int(bounds_dict.get("Width", 0)),
                h=int(bounds_dict.get("Height", 0)),
            )

            if bounds.w <= 1 or bounds.h <= 1:
                continue

            if not _rect_contains_point(bounds, x, y):
                continue

            window_number = int(info.get("kCGWindowNumber", 0))
            owner_name = info.get("kCGWindowOwnerName")
            pid = int(info.get("kCGWindowOwnerPID", 0)) or None
            title = info.get("kCGWindowName")

            return WindowRef(
                handle=str(window_number),
                title=title,
                pid=pid,
                owner_name=owner_name,
                bounds=bounds,
                window_number=window_number,
            )

        return None

    def locate(self, selector: WindowSelector) -> WindowRef | None:
        """Locate a window matching the selector."""
        if not isinstance(selector, WindowSelector):
            selector = WindowSelector.model_validate(selector)
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
        """Focus a window's application and raise the specific window."""
        if win.pid is None:
            return False
        try:
            from AppKit import NSRunningApplication  # type: ignore[import-untyped]

            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(win.pid)
            if app is None:
                return False
            # NSApplicationActivateIgnoringOtherApps
            activated = bool(app.activateWithOptions_(1 << 1))
            if activated:
                self._raise_window(win)
            return activated
        except Exception:
            return False

    def _raise_window(self, win: WindowRef) -> None:
        """Raise a specific window to front and center it on screen."""
        if win.pid is None:
            return
        try:
            from ApplicationServices import (  # type: ignore[import-untyped]
                AXUIElementCopyAttributeValue,
                AXUIElementCreateApplication,
                AXUIElementPerformAction,
            )
        except ImportError:
            return
        try:
            app_ref = AXUIElementCreateApplication(win.pid)
            err, ax_windows = AXUIElementCopyAttributeValue(
                app_ref, "AXWindows", None
            )
            if err != 0 or not ax_windows:
                return
            target = None
            if win.title:
                for ax_win in ax_windows:
                    err2, title = AXUIElementCopyAttributeValue(
                        ax_win, "AXTitle", None
                    )
                    if err2 == 0 and title == win.title:
                        target = ax_win
                        break
            if target is None:
                target = ax_windows[0]
            AXUIElementPerformAction(target, "AXRaise")
            # Center the window on screen
            self._center_ax_window(target, win, AXUIElementCopyAttributeValue)
        except Exception:
            pass

    @staticmethod
    def _center_ax_window(
        ax_win: object,
        win: WindowRef,
        copy_attr: object,
    ) -> None:
        """Move a window to the center of the main screen."""
        try:
            from AppKit import NSScreen  # type: ignore[import-untyped]
            from ApplicationServices import (  # type: ignore[import-untyped]
                AXUIElementSetAttributeValue,
                AXValueCreate,
                AXValueGetValue,
                kAXValueTypeCGPoint,
                kAXValueTypeCGSize,
            )
            from CoreFoundation import CGPoint  # type: ignore[import-untyped]

            screen = NSScreen.mainScreen()
            if screen is None:
                return
            frame = screen.frame()

            # Get window size from AX
            win_w = float(win.bounds.w)
            win_h = float(win.bounds.h)
            err, ax_size = copy_attr(ax_win, "AXSize", None)  # type: ignore[operator]
            if err == 0 and ax_size is not None:
                if hasattr(ax_size, "width") and hasattr(ax_size, "height"):
                    win_w = float(ax_size.width)  # type: ignore[union-attr]
                    win_h = float(ax_size.height)  # type: ignore[union-attr]
                else:
                    ok, size = AXValueGetValue(ax_size, kAXValueTypeCGSize, None)
                    if ok and size is not None:
                        win_w = float(size.width)  # type: ignore[union-attr]
                        win_h = float(size.height)  # type: ignore[union-attr]

            cx = frame.origin.x + (frame.size.width - win_w) / 2
            cy = frame.origin.y + (frame.size.height - win_h) / 2
            pos = AXValueCreate(kAXValueTypeCGPoint, CGPoint(cx, cy))
            AXUIElementSetAttributeValue(ax_win, "AXPosition", pos)
        except Exception:
            pass

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
        """Inject click event via Quartz."""
        from uitrace.player.executor import MacOSExecutor

        MacOSExecutor().click(x, y, button, count)

    def inject_scroll(self, x: int, y: int, delta_y: int) -> None:
        """Inject scroll event via Quartz."""
        from uitrace.player.executor import MacOSExecutor

        MacOSExecutor().scroll(x, y, delta_y)

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        """Get pixel color at screen coordinates (points).

        Uses CGDisplayCreateImageForRect to capture a 1x1 area.
        Requires Screen Recording permission.
        """
        try:
            from AppKit import NSBitmapImageRep, NSScreen  # type: ignore[import-untyped]
            from Quartz import (  # type: ignore[import-untyped]
                CGDisplayCreateImageForRect,
                CGMainDisplayID,
                CGRectMake,
            )

            # Convert points to pixels using main screen scale factor
            screen = NSScreen.mainScreen()
            if screen is None:
                return None
            scale = screen.backingScaleFactor()
            px = int(round(x * scale))
            py = int(round(y * scale))

            # Capture 1x1 pixel
            display_id = CGMainDisplayID()
            image = CGDisplayCreateImageForRect(display_id, CGRectMake(px, py, 1, 1))
            if image is None:
                return None

            bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image)
            if bitmap is None:
                return None

            color = bitmap.colorAtX_y_(0, 0)
            if color is None:
                return None

            r = int(round(color.redComponent() * 255))
            g = int(round(color.greenComponent() * 255))
            b = int(round(color.blueComponent() * 255))
            return (r, g, b)
        except Exception:
            return None
