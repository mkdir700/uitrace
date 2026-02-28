"""Tests for real playback of wait_until steps (pixel + window_found)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from uitrace.core.models import (
    Pos,
    Rect,
    SessionStart,
    StepResult,
    WaitUntil,
    WindowSelector,
    WindowSelectorEvent,
    WindowBounds,
)
from uitrace.errors import ErrorCode, UitError
from uitrace.platform.base import (
    PermissionReport,
    PermissionStatus,
    WindowRef,
)
from uitrace.player.player import Player


# ---------------------------------------------------------------------------
# FakePlatform
# ---------------------------------------------------------------------------


class FakePlatform:
    """Minimal platform fake with stateful locate and controllable pixel."""

    def __init__(
        self,
        *,
        locate_sequence: list[WindowRef | None] | None = None,
        pixel: tuple[int, int, int] | None = (0, 0, 0),
        pixel_sequence: list[tuple[int, int, int] | None] | None = None,
    ) -> None:
        self._locate_calls = 0
        self._locate_sequence = locate_sequence or []
        self._pixel = pixel
        self._pixel_sequence = pixel_sequence or []
        self._pixel_calls = 0
        self.focused: list[WindowRef] = []

    def check_permissions(self) -> PermissionReport:
        return PermissionReport(
            accessibility=PermissionStatus.granted,
            input_monitoring=PermissionStatus.granted,
            screen_recording=PermissionStatus.granted,
        )

    def list_windows(self) -> list[WindowRef]:
        return []

    def locate(self, selector: WindowSelector) -> WindowRef | None:
        if self._locate_calls < len(self._locate_sequence):
            result = self._locate_sequence[self._locate_calls]
            self._locate_calls += 1
            return result
        return None

    def focus(self, win: WindowRef) -> bool:
        self.focused.append(win)
        return True

    def get_bounds(self, win: WindowRef) -> Rect | None:
        return win.bounds

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        if self._pixel_calls < len(self._pixel_sequence):
            result = self._pixel_sequence[self._pixel_calls]
            self._pixel_calls += 1
            return result
        return self._pixel

    def inject_click(self, x: int, y: int, button: str, count: int) -> None:
        pass

    def inject_scroll(self, x: int, y: int, delta_y: int) -> None:
        pass

    def window_from_point(self, x: int, y: int) -> WindowRef | None:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BOUNDS = Rect(x=0, y=0, w=100, h=100)

_FAKE_WIN = WindowRef(
    handle="h1",
    title="TestWindow",
    pid=123,
    owner_name="TestApp",
    bounds=_BOUNDS,
    window_number=1,
)


def _make_clock(step_ns: int = 1_000_000):
    """Return a clock that increments by step_ns on each call."""
    state = {"t": 0}

    def clock() -> int:
        val = state["t"]
        state["t"] += step_ns
        return val

    return clock


def _make_events_window_found(
    selector: WindowSelector | None = None,
    timeout_ms: int = 5000,
) -> list:
    """Build a minimal event list with a wait_until(window_found) step."""
    sel = selector or WindowSelector(title="TestWindow")
    return [
        SessionStart(v=1, type="session_start", ts=0.0, meta={}),
        WaitUntil(
            v=1,
            type="wait_until",
            ts=0.1,
            kind="window_found",
            selector=sel,
            timeout_ms=timeout_ms,
        ),
    ]


def _make_events_pixel(
    *,
    rgb: tuple[int, int, int] = (255, 0, 0),
    tolerance: int = 0,
    timeout_ms: int = 5000,
) -> list:
    """Build a minimal event list with window_bounds + wait_until(pixel)."""
    return [
        SessionStart(v=1, type="session_start", ts=0.0, meta={}),
        WindowSelectorEvent(
            v=1,
            type="window_selector",
            ts=0.0,
            selector=WindowSelector(title="TestWindow"),
        ),
        WindowBounds(
            v=1,
            type="window_bounds",
            ts=0.0,
            bounds=_BOUNDS,
        ),
        WaitUntil(
            v=1,
            type="wait_until",
            ts=0.1,
            kind="pixel",
            pos=Pos(rx=0.5, ry=0.5),
            rgb=rgb,
            tolerance=tolerance,
            timeout_ms=timeout_ms,
        ),
    ]


# ---------------------------------------------------------------------------
# Tests: wait_until window_found
# ---------------------------------------------------------------------------


def test_wait_until_window_found_immediate():
    """Platform returns window on first locate -> success."""
    platform = FakePlatform(locate_sequence=[_FAKE_WIN])
    clock = _make_clock()
    player = Player(platform=platform, clock_ns=clock, sleep=lambda _: None)

    results: list[StepResult] = []
    for r in player.run(iter(_make_events_window_found()), dry_run=False):
        results.append(r)

    # Should have one result for wait_until, and it should be ok
    wait_results = [r for r in results if r.event_type == "wait_until"]
    assert len(wait_results) == 1
    assert wait_results[0].status == "ok"
    assert wait_results[0].ok is True
    assert wait_results[0].dry_run is False

    # Window should have been focused
    assert len(platform.focused) >= 1


def test_wait_until_window_found_after_retries():
    """Returns None twice then window -> success."""
    platform = FakePlatform(locate_sequence=[None, None, _FAKE_WIN])
    clock = _make_clock()
    player = Player(platform=platform, clock_ns=clock, sleep=lambda _: None)

    results: list[StepResult] = []
    for r in player.run(iter(_make_events_window_found()), dry_run=False):
        results.append(r)

    wait_results = [r for r in results if r.event_type == "wait_until"]
    assert len(wait_results) == 1
    assert wait_results[0].status == "ok"
    assert wait_results[0].ok is True

    # locate was called 3 times (None, None, _FAKE_WIN)
    assert platform._locate_calls == 3


def test_wait_until_window_found_timeout():
    """Always returns None -> raises UitError(WINDOW_NOT_FOUND)."""
    platform = FakePlatform(locate_sequence=[])  # always returns None
    # Clock that expires quickly: timeout_ms=100, each clock call advances 50ms
    clock = _make_clock(step_ns=50_000_000)  # 50ms per call
    player = Player(platform=platform, clock_ns=clock, sleep=lambda _: None)

    results: list[StepResult] = []
    with pytest.raises(UitError) as exc_info:
        for r in player.run(
            iter(_make_events_window_found(timeout_ms=100)), dry_run=False
        ):
            results.append(r)

    assert exc_info.value.code == ErrorCode.WINDOW_NOT_FOUND

    # Should have yielded an error StepResult before raising
    wait_results = [r for r in results if r.event_type == "wait_until"]
    assert len(wait_results) == 1
    assert wait_results[0].status == "error"
    assert wait_results[0].error_code == "WINDOW_NOT_FOUND"
    assert "timed out" in wait_results[0].message


# ---------------------------------------------------------------------------
# Tests: wait_until pixel
# ---------------------------------------------------------------------------


def test_wait_until_pixel_pass():
    """Pixel matches immediately -> success."""
    # Platform returns pixel (255, 0, 0) which matches expected
    platform = FakePlatform(
        locate_sequence=[_FAKE_WIN],
        pixel=(255, 0, 0),
    )

    # Patch time.monotonic and time.sleep used inside wait_until_pixel
    fake_time = [0.0]

    def fake_monotonic():
        return fake_time[0]

    def fake_sleep(s):
        fake_time[0] += s

    clock = _make_clock()
    player = Player(platform=platform, clock_ns=clock, sleep=lambda _: None)

    with (
        patch("uitrace.player.observer.time.monotonic", side_effect=fake_monotonic),
        patch("uitrace.player.observer.time.sleep", side_effect=fake_sleep),
    ):
        results: list[StepResult] = list(
            player.run(
                iter(_make_events_pixel(rgb=(255, 0, 0))),
                dry_run=False,
            )
        )

    wait_results = [r for r in results if r.event_type == "wait_until"]
    assert len(wait_results) == 1
    assert wait_results[0].status == "ok"
    assert wait_results[0].ok is True


def test_wait_until_pixel_timeout():
    """Pixel never matches -> raises UitError(ASSERTION_FAILED)."""
    # Platform returns (0, 0, 0) but we expect (255, 0, 0)
    platform = FakePlatform(
        locate_sequence=[_FAKE_WIN],
        pixel=(0, 0, 0),
    )

    # Fake time that advances past the timeout
    fake_time = [0.0]

    def fake_monotonic():
        val = fake_time[0]
        fake_time[0] += 0.1  # advance 100ms each call
        return val

    def fake_sleep(s):
        fake_time[0] += s

    clock = _make_clock()
    player = Player(platform=platform, clock_ns=clock, sleep=lambda _: None)

    results: list[StepResult] = []
    with (
        patch("uitrace.player.observer.time.monotonic", side_effect=fake_monotonic),
        patch("uitrace.player.observer.time.sleep", side_effect=fake_sleep),
    ):
        with pytest.raises(UitError) as exc_info:
            for r in player.run(
                iter(_make_events_pixel(rgb=(255, 0, 0), timeout_ms=200)),
                dry_run=False,
            ):
                results.append(r)

    assert exc_info.value.code == ErrorCode.ASSERTION_FAILED

    wait_results = [r for r in results if r.event_type == "wait_until"]
    assert len(wait_results) == 1
    assert wait_results[0].status == "error"
    assert wait_results[0].error_code == "ASSERTION_FAILED"
    assert "timed out" in wait_results[0].message
