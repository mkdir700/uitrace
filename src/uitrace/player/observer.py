"""Observation and assertion support for player."""

from __future__ import annotations

import time
from typing import Any, Callable

from uitrace.core.models import Rect
from uitrace.player.executor import window_rel_to_screen


def check_window_title_contains(platform: Any, window_ref: Any, expected: str) -> dict[str, Any]:
    """Check if window title contains expected string.

    Returns:
        dict with keys: ok (bool), observed (dict with title)
    """
    if window_ref is None:
        return {"ok": False, "observed": {"title": None, "error": "no window located"}}

    # Re-read window list to get current title
    windows = platform.list_windows()
    current_title = None
    for w in windows:
        if w.window_number == window_ref.window_number:
            current_title = w.title
            break

    if current_title is None:
        return {
            "ok": False,
            "observed": {"title": None, "error": "window not found or title not readable"},
        }

    ok = expected in current_title
    return {"ok": ok, "observed": {"title": current_title, "expected_contains": expected}}


def check_pixel(
    platform: Any,
    bounds: Rect,
    pos_rx: float,
    pos_ry: float,
    expected_rgb: tuple[int, int, int],
    tolerance: int = 0,
) -> dict[str, Any]:
    """Check pixel color at relative position.

    Returns:
        dict with keys: ok (bool), observed (dict with rgb, expected_rgb)
    """
    x, y = window_rel_to_screen(bounds, pos_rx, pos_ry)
    actual = platform.get_pixel(x, y)

    if actual is None:
        return {
            "ok": False,
            "observed": {
                "x": x,
                "y": y,
                "rgb": None,
                "error": "Screen Recording permission required",
            },
        }

    # Check if within tolerance
    dr = abs(actual[0] - expected_rgb[0])
    dg = abs(actual[1] - expected_rgb[1])
    db = abs(actual[2] - expected_rgb[2])
    ok = dr <= tolerance and dg <= tolerance and db <= tolerance

    return {
        "ok": ok,
        "observed": {
            "x": x,
            "y": y,
            "rgb": list(actual),
            "expected_rgb": list(expected_rgb),
            "tolerance": tolerance,
            "max_delta": max(dr, dg, db),
        },
    }


def wait_until_pixel(
    platform: Any,
    bounds: Rect,
    pos_rx: float,
    pos_ry: float,
    expected_rgb: tuple[int, int, int],
    tolerance: int = 0,
    timeout_ms: int = 5000,
    poll_interval_ms: int = 50,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Poll pixel color until it matches or timeout.

    Returns:
        dict with keys: ok (bool), elapsed_ms (int), observed (dict)
    """
    _clock = clock or time.monotonic
    _sleep = sleep or time.sleep
    start = _clock()
    deadline = start + timeout_ms / 1000.0
    last_result: dict[str, Any] | None = None

    while _clock() < deadline:
        result = check_pixel(platform, bounds, pos_rx, pos_ry, expected_rgb, tolerance)
        last_result = result
        if result["ok"]:
            elapsed_ms = round((_clock() - start) * 1000)
            result["elapsed_ms"] = elapsed_ms
            return result
        _sleep(poll_interval_ms / 1000.0)

    elapsed_ms = round((_clock() - start) * 1000)
    if last_result is None:
        last_result = {"ok": False, "observed": {"error": "timeout with no check"}}
    last_result["ok"] = False
    last_result["elapsed_ms"] = elapsed_ms
    last_result["observed"]["timeout_ms"] = timeout_ms
    return last_result
