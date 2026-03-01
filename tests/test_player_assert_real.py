"""Tests for real (non-dry-run) assert execution in the Player."""

import pytest

from uitrace.core.models import (
    Assert,
    Pos,
    Rect,
    SessionEnd,
    SessionStart,
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


class FakePlatform:
    """Fake platform that satisfies the Platform protocol for testing."""

    def __init__(
        self,
        pixel_map: dict | None = None,
        windows: list | None = None,
    ):
        self._pixel_map = pixel_map or {}
        self._windows = windows or []

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        return self._pixel_map.get((x, y))

    def list_windows(self) -> list:
        return self._windows

    def check_permissions(self) -> PermissionReport:
        return PermissionReport(
            accessibility=PermissionStatus.granted,
            input_monitoring=PermissionStatus.granted,
            screen_recording=PermissionStatus.granted,
        )

    def locate(self, selector) -> WindowRef | None:
        return self._windows[0] if self._windows else None

    def focus(self, win) -> bool:
        return True

    def get_bounds(self, win) -> Rect | None:
        return win.bounds if hasattr(win, "bounds") else None

    def inject_click(self, x: int, y: int, button: str, count: int) -> None:
        pass

    def inject_scroll(
        self,
        x: int,
        y: int,
        delta_y: int,
        *,
        delta_x: int = 0,
        phase: int | None = None,
        momentum_phase: int | None = None,
        is_continuous: bool | None = None,
    ) -> None:
        pass

    def window_from_point(self, x: int, y: int) -> None:
        return None


def _make_window(
    title: str = "My App",
    bounds: Rect | None = None,
    window_number: int = 1,
) -> WindowRef:
    if bounds is None:
        bounds = Rect(x=100, y=200, w=1000, h=500)
    return WindowRef(
        handle="fake",
        title=title,
        pid=123,
        owner_name="FakeApp",
        bounds=bounds,
        window_number=window_number,
    )


def _base_events(win_title: str = "My App", bounds: Rect | None = None):
    """Return the standard prefix events: session_start, window_selector, window_bounds."""
    if bounds is None:
        bounds = Rect(x=100, y=200, w=1000, h=500)
    return [
        SessionStart(v=1, type="session_start", ts=0.0, meta={}),
        WindowSelectorEvent(
            v=1,
            type="window_selector",
            ts=0.1,
            selector=WindowSelector(title=win_title),
        ),
        WindowBounds(v=1, type="window_bounds", ts=0.2, bounds=bounds),
    ]


def _collect_results(player: Player, events: list) -> list:
    """Run player and collect all StepResults into a list."""
    return list(player.run(iter(events), dry_run=False, speed=0))


# ---------------------------------------------------------------------------
# window_title_contains
# ---------------------------------------------------------------------------


def test_assert_window_title_contains_pass():
    """Assert window_title_contains passes when title matches."""
    win = _make_window(title="My TextEdit Document")
    platform = FakePlatform(windows=[win])
    player = Player(platform=platform, sleep=lambda _: None)

    events = _base_events(win_title="My TextEdit Document") + [
        Assert(
            v=1,
            type="assert",
            ts=0.3,
            kind="window_title_contains",
            value="TextEdit",
        ),
        SessionEnd(v=1, type="session_end", ts=0.4),
    ]

    results = _collect_results(player, events)
    assert_results = [r for r in results if r.event_type == "assert"]
    assert len(assert_results) == 1
    assert assert_results[0].ok is True
    assert assert_results[0].status == "ok"


def test_assert_window_title_contains_fail():
    """Assert window_title_contains fails with ASSERTION_FAILED when title does not match."""
    win = _make_window(title="Safari Browser")
    platform = FakePlatform(windows=[win])
    player = Player(platform=platform, sleep=lambda _: None)

    events = _base_events(win_title="Safari Browser") + [
        Assert(
            v=1,
            type="assert",
            ts=0.3,
            kind="window_title_contains",
            value="TextEdit",
        ),
        SessionEnd(v=1, type="session_end", ts=0.4),
    ]

    with pytest.raises(UitError) as exc_info:
        _collect_results(player, events)

    assert exc_info.value.code == ErrorCode.ASSERTION_FAILED


# ---------------------------------------------------------------------------
# pixel
# ---------------------------------------------------------------------------


def test_assert_pixel_pass():
    """Assert pixel passes when pixel color matches within tolerance."""
    bounds = Rect(x=100, y=200, w=1000, h=500)
    # rx=0.5, ry=0.5 => screen x=600, y=450
    win = _make_window(bounds=bounds)
    platform = FakePlatform(
        pixel_map={(600, 450): (255, 0, 0)},
        windows=[win],
    )
    player = Player(platform=platform, sleep=lambda _: None)

    events = _base_events(bounds=bounds) + [
        Assert(
            v=1,
            type="assert",
            ts=0.3,
            kind="pixel",
            pos=Pos(rx=0.5, ry=0.5),
            rgb=(255, 0, 0),
            tolerance=0,
        ),
        SessionEnd(v=1, type="session_end", ts=0.4),
    ]

    results = _collect_results(player, events)
    assert_results = [r for r in results if r.event_type == "assert"]
    assert len(assert_results) == 1
    assert assert_results[0].ok is True
    assert assert_results[0].status == "ok"


def test_assert_pixel_fail():
    """Assert pixel fails with ASSERTION_FAILED when pixel color does not match."""
    bounds = Rect(x=100, y=200, w=1000, h=500)
    win = _make_window(bounds=bounds)
    platform = FakePlatform(
        pixel_map={(600, 450): (0, 255, 0)},
        windows=[win],
    )
    player = Player(platform=platform, sleep=lambda _: None)

    events = _base_events(bounds=bounds) + [
        Assert(
            v=1,
            type="assert",
            ts=0.3,
            kind="pixel",
            pos=Pos(rx=0.5, ry=0.5),
            rgb=(255, 0, 0),
            tolerance=5,
        ),
        SessionEnd(v=1, type="session_end", ts=0.4),
    ]

    with pytest.raises(UitError) as exc_info:
        _collect_results(player, events)

    assert exc_info.value.code == ErrorCode.ASSERTION_FAILED
