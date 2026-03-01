"""macOS event tap capture for recording raw mouse events."""

from __future__ import annotations

import logging
import threading
import time
from typing import Iterator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CGEvent scroll field IDs (used for recording and injection)
# NOTE: Integer fallback values need empirical verification on each macOS
# version; prefer the symbolic Quartz imports when available.
# ---------------------------------------------------------------------------
try:
    from Quartz import kCGScrollWheelEventScrollPhase as _SCROLL_PHASE_FIELD  # type: ignore[import-untyped]  # noqa: I001
except ImportError:
    _SCROLL_PHASE_FIELD = 99
try:
    from Quartz import kCGScrollWheelEventMomentumPhase as _MOMENTUM_PHASE_FIELD  # type: ignore[import-untyped]  # noqa: I001
except ImportError:
    _MOMENTUM_PHASE_FIELD = 123
try:
    from Quartz import kCGScrollWheelEventIsContinuous as _IS_CONTINUOUS_FIELD  # type: ignore[import-untyped]  # noqa: I001
except ImportError:
    _IS_CONTINUOUS_FIELD = 88
try:
    from Quartz import kCGScrollWheelEventPointDeltaAxis2 as _POINT_DELTA_AXIS2_FIELD  # type: ignore[import-untyped]  # noqa: I001
except ImportError:
    _POINT_DELTA_AXIS2_FIELD = 97

# Raw event dict format matches what merge.py expects:
# {"kind": "mouse_down"|"mouse_up"|"scroll", "ts": float,
#  "x": int, "y": int, "button": str, "delta_y"?: int}


def iter_raw_events(stop_event: threading.Event) -> Iterator[dict]:
    """Yield raw mouse events from a macOS event tap.

    Runs a CFRunLoop to receive events. Call stop_event.set() to stop.

    Yields:
        dict with keys: kind, ts, x, y, button (for mouse), delta_y (for scroll)

    Raises:
        UitError: If permissions are insufficient
    """
    import queue

    from Quartz import (  # type: ignore[import-untyped]
        CFMachPortCreateRunLoopSource,
        CFRunLoopAddSource,
        CFRunLoopGetCurrent,
        CFRunLoopRunInMode,
        CFRunLoopStop,
        CGEventGetIntegerValueField,
        CGEventGetLocation,
        CGEventMaskBit,
        CGEventTapCreate,
        CGEventTapEnable,
        CGEventTapIsEnabled,
        kCFRunLoopCommonModes,
        kCFRunLoopDefaultMode,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGEventOtherMouseDown,
        kCGEventOtherMouseUp,
        kCGEventRightMouseDown,
        kCGEventRightMouseUp,
        kCGEventScrollWheel,
        kCGEventTapDisabledByTimeout,
        kCGEventTapDisabledByUserInput,
        kCGEventTapOptionListenOnly,
        kCGHeadInsertEventTap,
        kCGHIDEventTap,
        kCGMouseEventButtonNumber,
        kCGScrollWheelEventPointDeltaAxis1,
    )

    from uitrace.errors import ErrorCode, UitError

    event_queue: queue.Queue[dict | None] = queue.Queue()

    session_start_time = time.monotonic()
    tap_ref = None
    run_loop = None

    # Map event types to raw kinds and buttons
    _DOWN_TYPES = {
        kCGEventLeftMouseDown: "left",
        kCGEventRightMouseDown: "right",
        kCGEventOtherMouseDown: "other",
    }
    _UP_TYPES = {
        kCGEventLeftMouseUp: "left",
        kCGEventRightMouseUp: "right",
        kCGEventOtherMouseUp: "other",
    }

    _callback_count = 0

    def _callback(proxy, event_type, event, refcon):  # noqa: ARG001
        nonlocal tap_ref, _callback_count

        # Handle tap disabled events
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            if tap_ref is not None:
                CGEventTapEnable(tap_ref, True)
                logger.debug("Re-enabled event tap after disable event")
            return event

        _callback_count += 1
        ts = time.monotonic() - session_start_time
        loc = CGEventGetLocation(event)
        x = round(loc.x)
        y = round(loc.y)

        if _callback_count == 1:
            logger.warning("event tap active – first event: type=%s at (%s,%s)", event_type, x, y)

        if event_type in _DOWN_TYPES:
            button = _DOWN_TYPES[event_type]
            if button == "other":
                btn_num = CGEventGetIntegerValueField(event, kCGMouseEventButtonNumber)
                button = "middle" if btn_num == 2 else f"button{btn_num}"
            event_queue.put({"kind": "mouse_down", "ts": ts, "x": x, "y": y, "button": button})
        elif event_type in _UP_TYPES:
            button = _UP_TYPES[event_type]
            if button == "other":
                btn_num = CGEventGetIntegerValueField(event, kCGMouseEventButtonNumber)
                button = "middle" if btn_num == 2 else f"button{btn_num}"
            event_queue.put({"kind": "mouse_up", "ts": ts, "x": x, "y": y, "button": button})
        elif event_type == kCGEventScrollWheel:
            delta_y = CGEventGetIntegerValueField(event, kCGScrollWheelEventPointDeltaAxis1)
            delta_x = CGEventGetIntegerValueField(event, _POINT_DELTA_AXIS2_FIELD)
            phase = CGEventGetIntegerValueField(event, _SCROLL_PHASE_FIELD)
            momentum_phase = CGEventGetIntegerValueField(event, _MOMENTUM_PHASE_FIELD)
            is_continuous = CGEventGetIntegerValueField(event, _IS_CONTINUOUS_FIELD)
            event_queue.put(
                {
                    "kind": "scroll",
                    "ts": ts,
                    "x": x,
                    "y": y,
                    "delta_y": int(delta_y),
                    "delta_x": int(delta_x),
                    "phase": int(phase),
                    "momentum_phase": int(momentum_phase),
                    "is_continuous": bool(is_continuous),
                }
            )

        return event

    # Create event mask for all mouse events we care about
    mask = 0
    for evt in (
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGEventRightMouseDown,
        kCGEventRightMouseUp,
        kCGEventOtherMouseDown,
        kCGEventOtherMouseUp,
        kCGEventScrollWheel,
    ):
        mask |= CGEventMaskBit(evt)

    tap_ref = CGEventTapCreate(
        kCGHIDEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        mask,
        _callback,
        None,
    )

    if tap_ref is None:
        raise UitError(
            code=ErrorCode.PERMISSION_DENIED,
            message=(
                "Cannot create event tap. Check Accessibility and Input Monitoring permissions."
            ),
            hint=(
                "Open System Settings > Privacy & Security > Input Monitoring "
                "and grant access to your terminal app."
            ),
        )

    # Verify the tap can actually be enabled (macOS 15+ may create a tap
    # but silently refuse to enable it without proper Input Monitoring).
    CGEventTapEnable(tap_ref, True)
    if not CGEventTapIsEnabled(tap_ref):
        raise UitError(
            code=ErrorCode.PERMISSION_DENIED,
            message=(
                "Event tap created but cannot be enabled. "
                "Input Monitoring permission is not effective."
            ),
            hint=(
                "Open System Settings > Privacy & Security > Input Monitoring, "
                "toggle OFF then ON for your terminal app, then restart the terminal."
            ),
        )
    # Disable again; the run-loop thread will re-enable after setup.
    CGEventTapEnable(tap_ref, False)

    # Create run loop source and add to current run loop
    source = CFMachPortCreateRunLoopSource(None, tap_ref, 0)

    def _run_loop_thread():
        nonlocal run_loop
        run_loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(run_loop, source, kCFRunLoopCommonModes)
        CGEventTapEnable(tap_ref, True)

        # Run until stopped
        while not stop_event.is_set():
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, False)

        # Cleanup
        CGEventTapEnable(tap_ref, False)

    thread = threading.Thread(target=_run_loop_thread, daemon=True)
    thread.start()

    try:
        while not stop_event.is_set() or not event_queue.empty():
            try:
                raw = event_queue.get(timeout=0.1)
                if raw is None:
                    break
                yield raw
            except queue.Empty:
                continue
    finally:
        stop_event.set()
        if run_loop is not None:
            CFRunLoopStop(run_loop)
        thread.join(timeout=2.0)
