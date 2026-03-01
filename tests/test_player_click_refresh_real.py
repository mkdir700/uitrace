"""Tests for refreshing bounds before click/scroll injection."""

from __future__ import annotations

from uitrace.core.models import (
    Click,
    Point,
    Pos,
    Rect,
    SessionStart,
    WindowBounds,
    WindowSelector,
    WindowSelectorEvent,
)
from uitrace.platform.base import PermissionReport, PermissionStatus, WindowRef
from uitrace.player.player import Player


class DelayedMovePlatform:
    """Platform where window bounds update one call after focus."""

    def __init__(self) -> None:
        self._loc_win = WindowRef(
            handle="h1",
            title="T",
            pid=123,
            owner_name="App",
            bounds=Rect(x=100, y=100, w=400, h=300),
            window_number=1,
        )
        self._updated_bounds = Rect(x=300, y=200, w=400, h=300)
        self._get_bounds_calls = 0
        self.clicked: list[tuple[int, int, str, int]] = []

    def check_permissions(self) -> PermissionReport:
        return PermissionReport(
            accessibility=PermissionStatus.granted,
            input_monitoring=PermissionStatus.granted,
            screen_recording=PermissionStatus.granted,
        )

    def list_windows(self) -> list[WindowRef]:
        return [self._loc_win]

    def locate(self, selector: WindowSelector) -> WindowRef | None:
        return self._loc_win

    def focus(self, win: WindowRef) -> bool:
        return True

    def get_bounds(self, win: WindowRef) -> Rect | None:
        self._get_bounds_calls += 1
        if self._get_bounds_calls == 1:
            return Rect(x=100, y=100, w=400, h=300)
        return self._updated_bounds

    def inject_click(self, x: int, y: int, button: str, count: int) -> None:
        self.clicked.append((x, y, button, count))

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

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        return (0, 0, 0)

    def window_from_point(self, x: int, y: int) -> WindowRef | None:
        return None


def test_click_uses_latest_bounds_before_injection() -> None:
    """Click should use refreshed bounds, not stale pre-center bounds."""
    platform = DelayedMovePlatform()
    player = Player(platform=platform, clock_ns=lambda: 0, sleep=lambda _: None)

    events = [
        SessionStart(v=1, type="session_start", ts=0.0, meta={}),
        WindowSelectorEvent(
            v=1,
            type="window_selector",
            ts=0.0,
            selector=WindowSelector(title="T"),
        ),
        WindowBounds(
            v=1,
            type="window_bounds",
            ts=0.0,
            bounds=Rect(x=100, y=100, w=400, h=300),
        ),
        Click(
            v=1,
            type="click",
            ts=0.1,
            pos=Pos(rx=0.5, ry=0.5),
            screen=Point(x=300, y=250),
            button="left",
            count=1,
        ),
    ]

    list(player.run(iter(events), dry_run=False))

    assert len(platform.clicked) == 1
    # Updated bounds center: (300+200, 200+150)
    assert platform.clicked[0][:2] == (500, 350)


class StaleThenJumpPlatform:
    """Platform where get_bounds() returns stale bounds for the first 3 calls,
    then jumps to new bounds from call 4 onward.

    This simulates a scenario where the OS reports old window position for
    several frames after focus before suddenly reflecting the new position.
    """

    def __init__(self) -> None:
        self._loc_win = WindowRef(
            handle="h1",
            title="T",
            pid=123,
            owner_name="App",
            bounds=Rect(x=100, y=100, w=400, h=300),
            window_number=1,
        )
        self._old_bounds = Rect(x=100, y=100, w=400, h=300)
        self._new_bounds = Rect(x=300, y=200, w=400, h=300)
        self._get_bounds_calls = 0
        self.clicked: list[tuple[int, int, str, int]] = []

    def check_permissions(self) -> PermissionReport:
        return PermissionReport(
            accessibility=PermissionStatus.granted,
            input_monitoring=PermissionStatus.granted,
            screen_recording=PermissionStatus.granted,
        )

    def list_windows(self) -> list[WindowRef]:
        return [self._loc_win]

    def locate(self, selector: WindowSelector) -> WindowRef | None:
        return self._loc_win

    def focus(self, win: WindowRef) -> bool:
        return True

    def get_bounds(self, win: WindowRef) -> Rect | None:
        self._get_bounds_calls += 1
        if self._get_bounds_calls <= 3:
            return self._old_bounds
        return self._new_bounds

    def inject_click(self, x: int, y: int, button: str, count: int) -> None:
        self.clicked.append((x, y, button, count))

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

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        return (0, 0, 0)

    def window_from_point(self, x: int, y: int) -> WindowRef | None:
        return None


def test_click_waits_for_bounds_change_after_focus() -> None:
    """Click should use new bounds even when get_bounds() is stale for
    the first few calls after focus, then suddenly jumps."""
    platform = StaleThenJumpPlatform()
    player = Player(platform=platform, clock_ns=lambda: 0, sleep=lambda _: None)

    events = [
        SessionStart(v=1, type="session_start", ts=0.0, meta={}),
        WindowSelectorEvent(
            v=1,
            type="window_selector",
            ts=0.0,
            selector=WindowSelector(title="T"),
        ),
        WindowBounds(
            v=1,
            type="window_bounds",
            ts=0.0,
            bounds=Rect(x=100, y=100, w=400, h=300),
        ),
        Click(
            v=1,
            type="click",
            ts=0.1,
            pos=Pos(rx=0.5, ry=0.5),
            screen=Point(x=300, y=250),
            button="left",
            count=1,
        ),
    ]

    list(player.run(iter(events), dry_run=False))

    assert len(platform.clicked) == 1
    # New bounds center: (300+200, 200+150) = (500, 350)
    assert platform.clicked[0][:2] == (500, 350)
