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
    WindowBounds,
    WindowSelector,
    WindowSelectorEvent,
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


# ---------------------------------------------------------------------------
# FakePlatformWithBoundsDelay – get_bounds transitions after N calls
# ---------------------------------------------------------------------------


class FakePlatformWithBoundsDelay:
    """Platform where get_bounds returns old bounds for the first N calls,
    then switches to new bounds.  Used to simulate the delay between
    focus()+center and the OS actually moving the window."""

    def __init__(
        self,
        *,
        locate_result: WindowRef,
        old_bounds: Rect,
        new_bounds: Rect,
        switch_after: int = 2,
    ) -> None:
        self._locate_result = locate_result
        self._old_bounds = old_bounds
        self._new_bounds = new_bounds
        self._switch_after = switch_after
        self._get_bounds_calls = 0
        self.focused: list[WindowRef] = []
        self.clicked: list[tuple[int, int, str, int]] = []

    # -- permissions / window listing --

    def check_permissions(self) -> PermissionReport:
        return PermissionReport(
            accessibility=PermissionStatus.granted,
            input_monitoring=PermissionStatus.granted,
            screen_recording=PermissionStatus.granted,
        )

    def list_windows(self) -> list[WindowRef]:
        return []

    # -- locate / focus --

    def locate(self, selector: WindowSelector) -> WindowRef | None:
        return self._locate_result

    def focus(self, win: WindowRef) -> bool:
        self.focused.append(win)
        return True

    # -- stateful get_bounds --

    def get_bounds(self, win: WindowRef) -> Rect | None:
        self._get_bounds_calls += 1
        if self._get_bounds_calls <= self._switch_after:
            return self._old_bounds
        return self._new_bounds

    # -- pixel (not used but required by protocol) --

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        return (0, 0, 0)

    # -- injection --

    def inject_click(self, x: int, y: int, button: str, count: int) -> None:
        self.clicked.append((x, y, button, count))

    def inject_scroll(self, x: int, y: int, delta_y: int) -> None:
        pass

    def window_from_point(self, x: int, y: int) -> WindowRef | None:
        return None


# ---------------------------------------------------------------------------
# Test: wait_until(window_found) focus path uses post-center bounds
# ---------------------------------------------------------------------------


def test_window_found_focus_waits_for_bounds_change_before_click():
    """After wait_until(window_found) focuses a window the subsequent click
    must use the *new* (post-center) bounds, not the stale pre-center bounds.

    Sequence:
      1. wait_until(window_found) locates the window immediately.
      2. get_bounds returns old bounds (100,100,400,300) for the first 2 calls,
         then switches to new bounds (300,200,400,300) from call 3 onward.
      3. _wait_bounds_settle_after_focus detects the change and returns new bounds.
      4. WindowBounds event refreshes bounds (still new).
      5. Click at rx=0.5, ry=0.5 should resolve to (500, 350).
    """
    from uitrace.core.models import Click, Point, Pos

    old = Rect(x=100, y=100, w=400, h=300)
    new = Rect(x=300, y=200, w=400, h=300)

    fake_win = WindowRef(
        handle="h-delay",
        title="TestWindow",
        pid=999,
        owner_name="DelayApp",
        bounds=old,
        window_number=1,
    )

    platform = FakePlatformWithBoundsDelay(
        locate_result=fake_win,
        old_bounds=old,
        new_bounds=new,
        switch_after=2,
    )

    events = [
        SessionStart(v=1, type="session_start", ts=0.0, meta={}),
        WaitUntil(
            v=1,
            type="wait_until",
            ts=0.1,
            kind="window_found",
            selector=WindowSelector(title="TestWindow"),
            timeout_ms=5000,
        ),
        WindowBounds(
            v=1,
            type="window_bounds",
            ts=0.2,
            bounds=Rect(x=100, y=100, w=400, h=300),
        ),
        Click(
            v=1,
            type="click",
            ts=0.3,
            pos=Pos(rx=0.5, ry=0.5),
            screen=Point(x=300, y=250),
            button="left",
            count=1,
        ),
    ]

    player = Player(platform=platform, clock_ns=lambda: 0, sleep=lambda _: None)

    results: list[StepResult] = list(
        player.run(iter(events), dry_run=False)
    )

    # The click must have used the NEW bounds centre:
    #   x = 300 + round(400 * 0.5) = 500
    #   y = 200 + round(300 * 0.5) = 350
    assert len(platform.clicked) == 1
    assert platform.clicked[0][:2] == (500, 350)

    # All playable steps should have succeeded
    assert all(r.ok for r in results)
