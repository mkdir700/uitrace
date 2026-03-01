"""macOS Quartz executor for click/scroll injection."""

from __future__ import annotations

from uitrace.core.models import Rect


def window_rel_to_screen(bounds: Rect, rx: float, ry: float) -> tuple[int, int]:
    """Convert relative window coordinates to absolute screen coordinates.

    Args:
        bounds: Window bounds (x, y, w, h)
        rx: Relative x (0.0-1.0), clamped to [0, 1]
        ry: Relative y (0.0-1.0), clamped to [0, 1]

    Returns:
        Tuple of (screen_x, screen_y) in points
    """
    rx = max(0.0, min(1.0, rx))
    ry = max(0.0, min(1.0, ry))
    x = bounds.x + round(bounds.w * rx)
    y = bounds.y + round(bounds.h * ry)
    return x, y


class MacOSExecutor:
    """Inject mouse events using Quartz/CoreGraphics."""

    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> None:
        """Inject a click at screen coordinates (points)."""
        from Quartz import (  # type: ignore[import-untyped]
            CGEventCreateMouseEvent,
            CGEventPost,
            CGEventSetIntegerValueField,
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGEventOtherMouseDown,
            kCGEventOtherMouseUp,
            kCGEventRightMouseDown,
            kCGEventRightMouseUp,
            kCGHIDEventTap,
            kCGMouseButtonCenter,
            kCGMouseButtonLeft,
            kCGMouseButtonRight,
            kCGMouseEventClickState,
        )

        button_map = {
            "left": (kCGMouseButtonLeft, kCGEventLeftMouseDown, kCGEventLeftMouseUp),
            "right": (kCGMouseButtonRight, kCGEventRightMouseDown, kCGEventRightMouseUp),
            "middle": (kCGMouseButtonCenter, kCGEventOtherMouseDown, kCGEventOtherMouseUp),
        }

        if button not in button_map:
            raise ValueError(f"Unknown button: {button}")

        cg_button, down_type, up_type = button_map[button]
        point = (x, y)

        for click_num in range(1, count + 1):
            down_event = CGEventCreateMouseEvent(None, down_type, point, cg_button)
            if down_event is None:
                from uitrace.errors import ErrorCode, UitError

                raise UitError(
                    code=ErrorCode.INJECTION_FAILED,
                    message=f"Failed to create mouse down event at ({x}, {y})",
                )
            CGEventSetIntegerValueField(down_event, kCGMouseEventClickState, click_num)
            CGEventPost(kCGHIDEventTap, down_event)

            up_event = CGEventCreateMouseEvent(None, up_type, point, cg_button)
            if up_event is None:
                from uitrace.errors import ErrorCode, UitError

                raise UitError(
                    code=ErrorCode.INJECTION_FAILED,
                    message=f"Failed to create mouse up event at ({x}, {y})",
                )
            CGEventSetIntegerValueField(up_event, kCGMouseEventClickState, click_num)
            CGEventPost(kCGHIDEventTap, up_event)

    def scroll(self, x: int, y: int, delta_y: int) -> None:
        """Inject a scroll event at screen coordinates (points)."""
        from Quartz import (  # type: ignore[import-untyped]
            CGEventCreateScrollWheelEvent,
            CGEventPost,
            CGEventSetLocation,
            kCGHIDEventTap,
            kCGScrollEventUnitPixel,
        )

        event = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitPixel, 1, delta_y)
        if event is None:
            from uitrace.errors import ErrorCode, UitError

            raise UitError(
                code=ErrorCode.INJECTION_FAILED,
                message=f"Failed to create scroll event at ({x}, {y})",
            )
        CGEventSetLocation(event, (x, y))
        CGEventPost(kCGHIDEventTap, event)
