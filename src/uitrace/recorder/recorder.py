"""Record command runner: captures mouse events and writes trace JSONL."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, TextIO

from uitrace.core.models import (
    Click,
    Point,
    Pos,
    Rect,
    Scroll,
    SessionEnd,
    SessionStart,
    WaitUntil,
    WindowBounds,
    WindowSelector,
    WindowSelectorEvent,
)
from uitrace.errors import ErrorCode, UitError
from uitrace.platform.base import PermissionReport, PermissionStatus, WindowRef


def validate_record_permissions(perms: PermissionReport, *, require_screen_recording: bool) -> None:
    """Validate required permissions for recording.

    Raises UitError(PERMISSION_DENIED) with exact messages/hints.
    """
    if perms.accessibility != PermissionStatus.granted:
        raise UitError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Accessibility permission required for recording",
            hint="Open System Settings > Privacy & Security > Accessibility",
        )
    if perms.input_monitoring != PermissionStatus.granted:
        raise UitError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Input Monitoring permission required for recording",
            hint="Open System Settings > Privacy & Security > Input Monitoring",
        )
    if require_screen_recording and perms.screen_recording != PermissionStatus.granted:
        raise UitError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Screen Recording permission required for recording",
            hint="Open System Settings > Privacy & Security > Screen Recording",
        )


def _write_event(f: TextIO, event: Any) -> None:
    """Write a single event as JSON line."""
    data = event.model_dump()
    f.write(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    f.write("\n")
    f.flush()


def _in_bounds(x: int, y: int, bounds: Rect) -> bool:
    """Check if screen point is within window bounds."""
    return bounds.x <= x <= bounds.x + bounds.w and bounds.y <= y <= bounds.y + bounds.h


def _screen_to_relative(x: int, y: int, bounds: Rect) -> Pos:
    """Convert absolute screen coordinates to relative window position."""
    rx = (x - bounds.x) / bounds.w if bounds.w > 0 else 0.0
    ry = (y - bounds.y) / bounds.h if bounds.h > 0 else 0.0
    return Pos(rx=round(rx, 6), ry=round(ry, 6))


def _window_identity(win: WindowRef) -> Any:
    """Return an identity key for a window.

    Uses window_number when available; otherwise falls back to
    (pid, owner_name, title).
    """
    if win.window_number is not None:
        return win.window_number
    return (win.pid, win.owner_name, win.title)


def _selector_from_win(win: WindowRef) -> dict:
    """Build a selector dict from a WindowRef."""
    sel: dict[str, Any] = {"platform": "mac", "app": win.owner_name, "pid": win.pid}
    if win.title is not None:
        sel["title"] = win.title
    return sel


def process_raw_events_multi_window(
    raw_events: list[dict],
    platform_window_from_point: Callable[[int, int], WindowRef | None],
    window_wait_timeout_ms: int = 5000,
) -> list[dict]:
    """Process raw events for multi-window mode.

    Returns a list of trace event dicts (each suitable for model_validate).
    Inserts wait_until window_found + window_selector + window_bounds on window switches.
    """
    result: list[dict] = []
    current_identity: Any = None

    for raw in raw_events:
        kind = raw.get("kind")
        if kind not in ("mouse_down", "scroll"):
            continue

        x, y = raw.get("x", 0), raw.get("y", 0)
        ts = raw.get("ts", 0.0)

        win = platform_window_from_point(x, y)

        # Skip rule: no window, no pid, or no owner_name
        if win is None or win.pid is None or win.owner_name is None:
            continue

        identity = _window_identity(win)
        selector = _selector_from_win(win)
        bounds = win.bounds
        bounds_dict = {"x": bounds.x, "y": bounds.y, "w": bounds.w, "h": bounds.h}

        if current_identity is None:
            # First window context: emit window_selector + window_bounds, no wait_until
            current_identity = identity
            result.append(
                {
                    "v": 1,
                    "type": "window_selector",
                    "ts": ts,
                    "selector": selector,
                }
            )
            result.append(
                {
                    "v": 1,
                    "type": "window_bounds",
                    "ts": ts,
                    "bounds": bounds_dict,
                }
            )
        elif identity != current_identity:
            # Window switch: emit wait_until + window_selector + window_bounds
            current_identity = identity
            result.append(
                {
                    "v": 1,
                    "type": "wait_until",
                    "ts": ts,
                    "kind": "window_found",
                    "selector": selector,
                    "timeout_ms": window_wait_timeout_ms,
                }
            )
            result.append(
                {
                    "v": 1,
                    "type": "window_selector",
                    "ts": ts,
                    "selector": selector,
                }
            )
            result.append(
                {
                    "v": 1,
                    "type": "window_bounds",
                    "ts": ts,
                    "bounds": bounds_dict,
                }
            )

        # Compute relative position and emit the interaction event
        pos = _screen_to_relative(x, y, bounds)

        if kind == "mouse_down":
            result.append(
                {
                    "v": 1,
                    "type": "click",
                    "ts": round(ts, 6),
                    "pos": {"rx": pos.rx, "ry": pos.ry},
                    "screen": {"x": x, "y": y},
                    "button": raw.get("button", "left"),
                    "count": 1,
                }
            )
        elif kind == "scroll":
            scroll_ev: dict[str, Any] = {
                "v": 1,
                "type": "scroll",
                "ts": round(ts, 6),
                "pos": {"rx": pos.rx, "ry": pos.ry},
                "screen": {"x": x, "y": y},
                "delta": {"y": raw.get("delta_y", 0)},
            }
            # Add optional horizontal delta
            dx = raw.get("delta_x", 0)
            if dx != 0:
                scroll_ev["delta"]["x"] = dx
            # Add optional phase fields (only write non-zero values to keep JSONL compact)
            phase_val = raw.get("phase")
            if phase_val is not None and phase_val != 0:
                scroll_ev["phase"] = phase_val
            mp_val = raw.get("momentum_phase")
            if mp_val is not None and mp_val != 0:
                scroll_ev["momentum_phase"] = mp_val
            if raw.get("is_continuous") is not None:
                scroll_ev["is_continuous"] = raw["is_continuous"]
            result.append(scroll_ev)

    return result


class Recorder:
    """Records mouse events and writes trace JSONL."""

    def run(
        self,
        out_path: Path,
        platform: Any,
        window_ref: Any,
        selector_dict: dict,
        countdown: int = 0,
        sample_window_ms: int = 1000,
        merge: bool = True,
        follow: str = "single",
        window_wait_timeout_ms: int = 5000,
    ) -> None:
        """Run recording session.

        Args:
            out_path: Output JSONL file path
            platform: Platform instance (MacOSPlatform)
            window_ref: Target window (from platform.locate or list)
            selector_dict: Window selector data for the trace
            countdown: Seconds to wait before recording
            sample_window_ms: Interval to re-sample window bounds (ms)
            merge: Whether to merge mouse down/up into clicks
            follow: Window follow mode ('single' or 'any')
            window_wait_timeout_ms: Timeout for waiting on new windows (follow=any)
        """
        # Force merge=False for follow=any
        if follow == "any":
            merge = False

        # Countdown
        if countdown > 0:
            for i in range(countdown, 0, -1):
                print(f"Recording starts in {i}...", file=sys.stderr)
                time.sleep(1)
            print("Recording!", file=sys.stderr)

        if follow == "any":
            self._run_follow_any(
                out_path,
                platform,
                window_wait_timeout_ms=window_wait_timeout_ms,
            )
        else:
            self._run_follow_single(
                out_path,
                platform,
                window_ref,
                selector_dict,
                sample_window_ms=sample_window_ms,
                merge=merge,
            )

    def _run_follow_single(
        self,
        out_path: Path,
        platform: Any,
        window_ref: Any,
        selector_dict: dict,
        sample_window_ms: int = 1000,
        merge: bool = True,
    ) -> None:
        """Run recording session tracking a single window."""
        from uitrace.recorder.capture_macos import iter_raw_events

        # Get initial bounds
        current_bounds = platform.get_bounds(window_ref)
        if current_bounds is None:
            current_bounds = window_ref.bounds

        stop_event = threading.Event()
        ts_start = time.monotonic()

        with open(out_path, "w", encoding="utf-8") as f:
            # Write session_start
            _write_event(
                f,
                SessionStart(
                    v=1,
                    type="session_start",
                    ts=0.0,
                    meta={
                        "tool": "uitrace",
                        "os": sys.platform,
                        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                    },
                ),
            )

            # Write window_selector
            _write_event(
                f,
                WindowSelectorEvent(
                    v=1,
                    type="window_selector",
                    ts=0.0,
                    selector=WindowSelector(**selector_dict),
                ),
            )

            # Write initial window_bounds
            _write_event(
                f,
                WindowBounds(
                    v=1,
                    type="window_bounds",
                    ts=0.0,
                    bounds=current_bounds,
                ),
            )

            last_bounds_check = time.monotonic()
            raw_buffer: list[dict] = []
            _stat_total = 0
            _stat_oob = 0
            _stat_written = 0

            try:
                for raw in iter_raw_events(stop_event):
                    _stat_total += 1
                    ts = time.monotonic() - ts_start

                    # Periodically re-sample window bounds
                    now = time.monotonic()
                    if (now - last_bounds_check) * 1000 >= sample_window_ms:
                        new_bounds = platform.get_bounds(window_ref)
                        if new_bounds is not None and new_bounds != current_bounds:
                            current_bounds = new_bounds
                            _write_event(
                                f,
                                WindowBounds(
                                    v=1,
                                    type="window_bounds",
                                    ts=round(ts, 6),
                                    bounds=current_bounds,
                                ),
                            )
                        last_bounds_check = now

                    # Filter: only events within window bounds
                    ex, ey = raw.get("x", 0), raw.get("y", 0)
                    if not _in_bounds(ex, ey, current_bounds):
                        if _stat_oob == 0:
                            # Log first out-of-bounds event for diagnostics
                            b = current_bounds
                            print(
                                f"[debug] first out-of-bounds event: "
                                f"({ex},{ey}) not in window "
                                f"({b.x},{b.y})-({b.x + b.w},{b.y + b.h})",
                                file=sys.stderr,
                            )
                        _stat_oob += 1
                        continue

                    _stat_written += 1
                    if merge:
                        raw_buffer.append(raw)
                        # Flush merged events periodically
                        self._flush_merged(f, raw_buffer, current_bounds)
                    else:
                        self._write_raw_event(f, raw, current_bounds)

            except KeyboardInterrupt:
                pass
            finally:
                stop_event.set()
                # Flush remaining buffer
                if merge and raw_buffer:
                    self._flush_merged(f, raw_buffer, current_bounds, force=True)

                # Write session_end
                ts_end = time.monotonic() - ts_start
                _write_event(
                    f,
                    SessionEnd(
                        v=1,
                        type="session_end",
                        ts=round(ts_end, 6),
                    ),
                )

        print(
            f"Trace written to {out_path}"
            f"  (events: {_stat_total} captured, {_stat_oob} out-of-bounds,"
            f" {_stat_written} written)",
            file=sys.stderr,
        )

    def _run_follow_any(
        self,
        out_path: Path,
        platform: Any,
        window_wait_timeout_ms: int = 5000,
    ) -> None:
        """Run recording session following any window the user interacts with."""
        from uitrace.recorder.capture_macos import iter_raw_events

        stop_event = threading.Event()
        ts_start = time.monotonic()

        current_identity: Any = None
        current_bounds: Rect | None = None
        _stat_total = 0
        _stat_skipped = 0
        _stat_written = 0

        with open(out_path, "w", encoding="utf-8") as f:
            # Write session_start
            _write_event(
                f,
                SessionStart(
                    v=1,
                    type="session_start",
                    ts=0.0,
                    meta={
                        "tool": "uitrace",
                        "os": sys.platform,
                        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                    },
                ),
            )

            try:
                for raw in iter_raw_events(stop_event):
                    _stat_total += 1
                    kind = raw.get("kind")
                    if kind not in ("mouse_down", "scroll"):
                        continue

                    ts = time.monotonic() - ts_start
                    ex, ey = raw.get("x", 0), raw.get("y", 0)

                    win = platform.window_from_point(ex, ey)

                    # Skip rule
                    if win is None or win.pid is None or win.owner_name is None:
                        _stat_skipped += 1
                        continue

                    identity = _window_identity(win)
                    selector = _selector_from_win(win)
                    current_bounds = win.bounds

                    if current_identity is None:
                        # First window: emit window_selector + window_bounds
                        current_identity = identity
                        _write_event(
                            f,
                            WindowSelectorEvent(
                                v=1,
                                type="window_selector",
                                ts=round(ts, 6),
                                selector=WindowSelector(**selector),
                            ),
                        )
                        _write_event(
                            f,
                            WindowBounds(
                                v=1,
                                type="window_bounds",
                                ts=round(ts, 6),
                                bounds=current_bounds,
                            ),
                        )
                    elif identity != current_identity:
                        # Window switch: emit wait_until + window_selector + window_bounds
                        current_identity = identity
                        _write_event(
                            f,
                            WaitUntil(
                                v=1,
                                type="wait_until",
                                ts=round(ts, 6),
                                kind="window_found",
                                selector=WindowSelector(**selector),
                                timeout_ms=window_wait_timeout_ms,
                            ),
                        )
                        _write_event(
                            f,
                            WindowSelectorEvent(
                                v=1,
                                type="window_selector",
                                ts=round(ts, 6),
                                selector=WindowSelector(**selector),
                            ),
                        )
                        _write_event(
                            f,
                            WindowBounds(
                                v=1,
                                type="window_bounds",
                                ts=round(ts, 6),
                                bounds=current_bounds,
                            ),
                        )

                    # Write interaction event with ts relative to session start
                    _stat_written += 1
                    raw_with_ts = {**raw, "ts": ts}
                    self._write_raw_event(f, raw_with_ts, current_bounds)

            except KeyboardInterrupt:
                pass
            finally:
                stop_event.set()

                # Write session_end
                ts_end = time.monotonic() - ts_start
                _write_event(
                    f,
                    SessionEnd(
                        v=1,
                        type="session_end",
                        ts=round(ts_end, 6),
                    ),
                )

        print(
            f"Trace written to {out_path}"
            f"  (events: {_stat_total} captured, {_stat_skipped} skipped,"
            f" {_stat_written} written)",
            file=sys.stderr,
        )

    def _flush_merged(
        self,
        f: TextIO,
        buffer: list[dict],
        bounds: Rect,
        force: bool = False,
    ) -> None:
        """Flush merged events from buffer."""
        from uitrace.recorder.merge import merge_mouse_events

        if not buffer:
            return

        # Only flush if we have enough events or force
        if not force and len(buffer) < 2:
            return

        merged = list(merge_mouse_events(buffer))
        buffer.clear()

        for ev in merged:
            self._write_merged_event(f, ev, bounds)

    def _write_merged_event(self, f: TextIO, ev: dict, bounds: Rect) -> None:
        """Write a merged event dict as a trace event."""
        ts = ev["ts"]
        x, y = ev["x"], ev["y"]
        pos = _screen_to_relative(x, y, bounds)

        if ev["kind"] == "click":
            _write_event(
                f,
                Click(
                    v=1,
                    type="click",
                    ts=round(ts, 6),
                    pos=pos,
                    screen=Point(x=x, y=y),
                    button=ev.get("button", "left"),
                    count=ev.get("count", 1),
                ),
            )
        elif ev["kind"] == "scroll":
            scroll_kwargs: dict[str, Any] = {
                "v": 1,
                "type": "scroll",
                "ts": round(ts, 6),
                "pos": pos,
                "screen": Point(x=x, y=y),
                "delta": {"y": ev.get("delta_y", 0)},
            }
            # Add optional horizontal delta
            dx = ev.get("delta_x", 0)
            if dx != 0:
                scroll_kwargs["delta"]["x"] = dx
            # Add optional phase fields (only write non-zero values to keep JSONL compact)
            phase_val = ev.get("phase")
            if phase_val is not None and phase_val != 0:
                scroll_kwargs["phase"] = phase_val
            mp_val = ev.get("momentum_phase")
            if mp_val is not None and mp_val != 0:
                scroll_kwargs["momentum_phase"] = mp_val
            if ev.get("is_continuous") is not None:
                scroll_kwargs["is_continuous"] = ev["is_continuous"]
            _write_event(f, Scroll(**scroll_kwargs))

    def _write_raw_event(self, f: TextIO, raw: dict, bounds: Rect) -> None:
        """Write a raw event directly (no merge)."""
        ts = raw["ts"]
        x, y = raw.get("x", 0), raw.get("y", 0)
        pos = _screen_to_relative(x, y, bounds)

        if raw["kind"] in ("mouse_down", "mouse_up"):
            # Write as click with count=1 (down only)
            if raw["kind"] == "mouse_down":
                _write_event(
                    f,
                    Click(
                        v=1,
                        type="click",
                        ts=round(ts, 6),
                        pos=pos,
                        screen=Point(x=x, y=y),
                        button=raw.get("button", "left"),
                        count=1,
                    ),
                )
        elif raw["kind"] == "scroll":
            scroll_kwargs: dict[str, Any] = {
                "v": 1,
                "type": "scroll",
                "ts": round(ts, 6),
                "pos": pos,
                "screen": Point(x=x, y=y),
                "delta": {"y": raw.get("delta_y", 0)},
            }
            # Add optional horizontal delta
            dx = raw.get("delta_x", 0)
            if dx != 0:
                scroll_kwargs["delta"]["x"] = dx
            # Add optional phase fields (only write non-zero values to keep JSONL compact)
            phase_val = raw.get("phase")
            if phase_val is not None and phase_val != 0:
                scroll_kwargs["phase"] = phase_val
            mp_val = raw.get("momentum_phase")
            if mp_val is not None and mp_val != 0:
                scroll_kwargs["momentum_phase"] = mp_val
            if raw.get("is_continuous") is not None:
                scroll_kwargs["is_continuous"] = raw["is_continuous"]
            _write_event(f, Scroll(**scroll_kwargs))
