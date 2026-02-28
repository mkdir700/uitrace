"""Unit tests for the Player class dry-run scheduler."""

from __future__ import annotations

from uitrace.core.models import (
    Assert,
    Click,
    Inset,
    Point,
    Pos,
    Rect,
    Scroll,
    SessionEnd,
    SessionStart,
    StepResult,
    WindowBounds,
    WindowSelector,
    WindowSelectorEvent,
)
from uitrace.player.player import Player


def _sample_events():
    """Return a list of events matching tests/fixtures/trace_v1_valid.jsonl."""
    return [
        SessionStart(v=1, type="session_start", ts=0.0, meta={"tool": "uitrace"}),
        WindowSelectorEvent(
            v=1,
            type="window_selector",
            ts=0.0,
            selector=WindowSelector(title_regex=".*TextEdit.*", app="TextEdit", platform="mac"),
        ),
        WindowBounds(
            v=1,
            type="window_bounds",
            ts=0.0,
            bounds=Rect(x=100, y=100, w=800, h=600),
            client_inset=Inset(l=0, t=0, r=0, b=0),
        ),
        Assert(v=1, type="assert", ts=0.1, kind="window_title_contains", value="TextEdit"),
        Click(
            v=1,
            type="click",
            ts=0.5,
            pos=Pos(rx=0.5, ry=0.5),
            screen=Point(x=500, y=400),
            button="left",
            count=1,
        ),
        Scroll(
            v=1,
            type="scroll",
            ts=0.8,
            pos=Pos(rx=0.5, ry=0.9),
            screen=Point(x=500, y=640),
            delta={"y": -240},
        ),
        SessionEnd(v=1, type="session_end", ts=1.0),
    ]


def test_dry_run_yields_all_playable_steps_0_based():
    player = Player(clock_ns=lambda: 0, sleep=lambda _s: None)
    results = list(player.run(iter(_sample_events()), dry_run=True))

    assert len(results) == 5
    assert [r.step for r in results] == [0, 1, 2, 3, 4]
    assert [r.event_type for r in results] == [
        "window_selector", "window_bounds", "assert", "click", "scroll",
    ]
    assert all(r.status == "ok" for r in results)
    assert all(r.dry_run is True for r in results)
    assert all(r.ok is True for r in results)


def test_dry_run_event_idx_is_0_based_stream_index():
    player = Player(clock_ns=lambda: 0, sleep=lambda _s: None)
    results = list(player.run(iter(_sample_events()), dry_run=True))

    # session_start=0, window_selector=1, window_bounds=2, assert=3, click=4, scroll=5
    assert [r.event_idx for r in results] == [1, 2, 3, 4, 5]


def test_from_to_step_yields_skipped_outside_range():
    player = Player(clock_ns=lambda: 0, sleep=lambda _s: None)
    results = list(
        player.run(iter(_sample_events()), dry_run=True, from_step=1, to_step=2)
    )

    assert len(results) == 5
    assert [(r.step, r.status) for r in results] == [
        (0, "skipped"),
        (1, "ok"),
        (2, "ok"),
        (3, "skipped"),
        (4, "skipped"),
    ]


def test_from_step_only():
    player = Player(clock_ns=lambda: 0, sleep=lambda _s: None)
    results = list(
        player.run(iter(_sample_events()), dry_run=True, from_step=2)
    )

    assert [(r.step, r.status) for r in results] == [
        (0, "skipped"),
        (1, "skipped"),
        (2, "ok"),
        (3, "ok"),
        (4, "ok"),
    ]


def test_to_step_only():
    player = Player(clock_ns=lambda: 0, sleep=lambda _s: None)
    results = list(
        player.run(iter(_sample_events()), dry_run=True, to_step=1)
    )

    assert [(r.step, r.status) for r in results] == [
        (0, "ok"),
        (1, "ok"),
        (2, "skipped"),
        (3, "skipped"),
        (4, "skipped"),
    ]


def test_speed_affects_sleep_duration():
    slept: list[float] = []
    player = Player(clock_ns=lambda: 0, sleep=slept.append)

    # Playable events: window_selector ts=0.0, window_bounds ts=0.0, assert ts=0.1,
    # click ts=0.5, scroll ts=0.8
    # Deltas between consecutive in-range: 0 (no sleep), 0.1, 0.4, 0.3
    # At speed=2.0 => 0.05, 0.2, 0.15
    list(player.run(iter(_sample_events()), dry_run=True, speed=2.0))

    assert len(slept) == 3
    assert abs(slept[0] - 0.05) < 1e-9
    assert abs(slept[1] - 0.20) < 1e-9
    assert abs(slept[2] - 0.15) < 1e-9


def test_speed_with_slicing_only_sleeps_for_in_range():
    """Sleep only happens between consecutive *in-range* steps."""
    slept: list[float] = []
    player = Player(clock_ns=lambda: 0, sleep=slept.append)

    # from_step=3 (click ts=0.5) to to_step=4 (scroll ts=0.8)
    list(
        player.run(
            iter(_sample_events()), dry_run=True, speed=1.0, from_step=3, to_step=4
        )
    )

    # Only one sleep between the two in-range steps: 0.8 - 0.5 = 0.3
    assert len(slept) == 1
    assert abs(slept[0] - 0.3) < 1e-9


def test_non_dry_run_without_platform_raises_permission_denied():
    """Without a platform, real playback fails with PERMISSION_DENIED."""
    player = Player(clock_ns=lambda: 0, sleep=lambda _s: None)
    results: list[StepResult] = []
    raised = False

    try:
        for r in player.run(iter(_sample_events()), dry_run=False):
            results.append(r)
    except Exception as e:
        raised = True
        assert "platform" in str(e).lower() or "permission" in str(e).lower()

    assert raised
    # No step_result emitted because the error is pre-flight (no platform at all)
    assert len(results) == 0


def test_session_events_are_not_steps():
    """session_start and session_end do not count as steps."""
    player = Player(clock_ns=lambda: 0, sleep=lambda _s: None)
    results = list(player.run(iter(_sample_events()), dry_run=True))

    event_types = {r.event_type for r in results}
    assert "session_start" not in event_types
    assert "session_end" not in event_types
    # window_selector IS a playable step (used for window locate)
    assert "window_selector" in event_types
