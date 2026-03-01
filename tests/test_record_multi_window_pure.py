"""Tests for multi-window recording via process_raw_events_multi_window."""

from __future__ import annotations

from uitrace.core.models import Rect
from uitrace.platform.base import WindowRef
from uitrace.recorder.recorder import process_raw_events_multi_window


def _make_win(
    *,
    title: str,
    pid: int,
    owner_name: str,
    bounds: Rect,
    window_number: int | None = None,
) -> WindowRef:
    """Helper to create a WindowRef for testing."""
    return WindowRef(
        handle=f"handle-{pid}-{title}",
        title=title,
        pid=pid,
        owner_name=owner_name,
        bounds=bounds,
        window_number=window_number,
    )


# Three windows for testing
WIN_A = _make_win(
    title="Window A",
    pid=100,
    owner_name="AppA",
    bounds=Rect(x=0, y=0, w=800, h=600),
    window_number=1,
)
WIN_B = _make_win(
    title="Window B",
    pid=200,
    owner_name="AppB",
    bounds=Rect(x=100, y=100, w=600, h=400),
    window_number=2,
)
WIN_C = _make_win(
    title="Window C",
    pid=300,
    owner_name="AppC",
    bounds=Rect(x=200, y=200, w=500, h=300),
    window_number=3,
)


def test_three_windows_abc_inserts_two_wait_until():
    """Click in A, then B, then C. Expect two wait_until inserts (for B and C)."""
    raw_events = [
        {"kind": "mouse_down", "x": 400, "y": 300, "ts": 1.0, "button": "left"},
        {"kind": "mouse_down", "x": 350, "y": 250, "ts": 2.0, "button": "left"},
        {"kind": "mouse_down", "x": 450, "y": 350, "ts": 3.0, "button": "left"},
    ]

    # Map coordinates to windows
    coord_to_win = {
        (400, 300): WIN_A,
        (350, 250): WIN_B,
        (450, 350): WIN_C,
    }

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return coord_to_win.get((x, y))

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    # Extract event types
    types = [ev["type"] for ev in result]

    # Expected sequence:
    # 1. window_selector (A - first window, no wait_until)
    # 2. window_bounds (A)
    # 3. click (A)
    # 4. wait_until (B - window switch)
    # 5. window_selector (B)
    # 6. window_bounds (B)
    # 7. click (B)
    # 8. wait_until (C - window switch)
    # 9. window_selector (C)
    # 10. window_bounds (C)
    # 11. click (C)
    assert types == [
        "window_selector",
        "window_bounds",
        "click",
        "wait_until",
        "window_selector",
        "window_bounds",
        "click",
        "wait_until",
        "window_selector",
        "window_bounds",
        "click",
    ]

    # Verify wait_until events have kind=window_found
    wait_events = [ev for ev in result if ev["type"] == "wait_until"]
    assert len(wait_events) == 2
    for w in wait_events:
        assert w["kind"] == "window_found"
        assert "selector" in w
        assert "timeout_ms" in w

    # Verify wait_until for B has AppB selector
    assert wait_events[0]["selector"]["app"] == "AppB"
    assert wait_events[0]["selector"]["pid"] == 200
    assert wait_events[0]["selector"]["title"] == "Window B"

    # Verify wait_until for C has AppC selector
    assert wait_events[1]["selector"]["app"] == "AppC"
    assert wait_events[1]["selector"]["pid"] == 300
    assert wait_events[1]["selector"]["title"] == "Window C"

    # Verify three window contexts total
    selector_events = [ev for ev in result if ev["type"] == "window_selector"]
    assert len(selector_events) == 3

    # Verify three click events
    click_events = [ev for ev in result if ev["type"] == "click"]
    assert len(click_events) == 3


def test_same_window_no_wait_until():
    """All clicks in same window should produce no wait_until events."""
    raw_events = [
        {"kind": "mouse_down", "x": 100, "y": 100, "ts": 1.0, "button": "left"},
        {"kind": "mouse_down", "x": 200, "y": 200, "ts": 2.0, "button": "left"},
        {"kind": "mouse_down", "x": 300, "y": 300, "ts": 3.0, "button": "left"},
    ]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return WIN_A

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    types = [ev["type"] for ev in result]

    # No wait_until events
    wait_events = [ev for ev in result if ev["type"] == "wait_until"]
    assert len(wait_events) == 0

    # One initial window_selector + window_bounds, three clicks
    assert types == [
        "window_selector",
        "window_bounds",
        "click",
        "click",
        "click",
    ]


def test_none_window_skipped():
    """Events where platform returns None should be skipped."""
    raw_events = [
        {"kind": "mouse_down", "x": 100, "y": 100, "ts": 1.0, "button": "left"},
        {"kind": "mouse_down", "x": 999, "y": 999, "ts": 2.0, "button": "left"},
        {"kind": "mouse_down", "x": 200, "y": 200, "ts": 3.0, "button": "left"},
    ]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        if x == 999:
            return None
        return WIN_A

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    # Only two clicks (the None one is skipped), no window switch
    click_events = [ev for ev in result if ev["type"] == "click"]
    assert len(click_events) == 2

    wait_events = [ev for ev in result if ev["type"] == "wait_until"]
    assert len(wait_events) == 0


def test_scroll_event_in_multi_window():
    """Scroll events should also be captured in multi-window mode."""
    raw_events = [
        {"kind": "mouse_down", "x": 400, "y": 300, "ts": 1.0, "button": "left"},
        {"kind": "scroll", "x": 350, "y": 250, "ts": 2.0, "delta_y": -3},
    ]

    coord_to_win = {
        (400, 300): WIN_A,
        (350, 250): WIN_B,
    }

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return coord_to_win.get((x, y))

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    types = [ev["type"] for ev in result]
    assert types == [
        "window_selector",
        "window_bounds",
        "click",
        "wait_until",
        "window_selector",
        "window_bounds",
        "scroll",
    ]

    scroll_events = [ev for ev in result if ev["type"] == "scroll"]
    assert len(scroll_events) == 1
    assert scroll_events[0]["delta"]["y"] == -3


def test_mouse_up_ignored():
    """mouse_up events should be ignored (only mouse_down produces clicks)."""
    raw_events = [
        {"kind": "mouse_down", "x": 400, "y": 300, "ts": 1.0, "button": "left"},
        {"kind": "mouse_up", "x": 400, "y": 300, "ts": 1.1, "button": "left"},
    ]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return WIN_A

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    click_events = [ev for ev in result if ev["type"] == "click"]
    assert len(click_events) == 1


def test_no_pid_window_skipped():
    """Events with a window that has no pid should be skipped."""
    win_no_pid = _make_win(
        title="No PID",
        pid=None,  # type: ignore[arg-type]
        owner_name="SomeApp",
        bounds=Rect(x=0, y=0, w=800, h=600),
    )

    raw_events = [
        {"kind": "mouse_down", "x": 100, "y": 100, "ts": 1.0, "button": "left"},
    ]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return win_no_pid

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)
    assert len(result) == 0


def test_no_owner_name_window_skipped():
    """Events with a window that has no owner_name should be skipped."""
    win_no_owner = _make_win(
        title="No Owner",
        pid=100,
        owner_name=None,  # type: ignore[arg-type]
        bounds=Rect(x=0, y=0, w=800, h=600),
    )

    raw_events = [
        {"kind": "mouse_down", "x": 100, "y": 100, "ts": 1.0, "button": "left"},
    ]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return win_no_owner

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)
    assert len(result) == 0


def test_window_identity_uses_window_number():
    """When window_number is set, identity uses it; same number = same window."""
    win_a1 = _make_win(
        title="Title Changed",
        pid=100,
        owner_name="AppA",
        bounds=Rect(x=0, y=0, w=800, h=600),
        window_number=1,  # same as WIN_A
    )

    raw_events = [
        {"kind": "mouse_down", "x": 100, "y": 100, "ts": 1.0, "button": "left"},
        {"kind": "mouse_down", "x": 200, "y": 200, "ts": 2.0, "button": "left"},
    ]

    call_count = [0]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        call_count[0] += 1
        # First call returns WIN_A, second returns win_a1 (same window_number)
        if call_count[0] == 1:
            return WIN_A
        return win_a1

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    # Same window_number, so no switch
    wait_events = [ev for ev in result if ev["type"] == "wait_until"]
    assert len(wait_events) == 0


def test_window_identity_fallback_without_window_number():
    """Without window_number, identity uses (pid, owner_name, title)."""
    win_no_num_a = _make_win(
        title="Win",
        pid=100,
        owner_name="App",
        bounds=Rect(x=0, y=0, w=800, h=600),
        window_number=None,
    )
    win_no_num_b = _make_win(
        title="Win",
        pid=200,  # different pid
        owner_name="App",
        bounds=Rect(x=100, y=100, w=600, h=400),
        window_number=None,
    )

    raw_events = [
        {"kind": "mouse_down", "x": 100, "y": 100, "ts": 1.0, "button": "left"},
        {"kind": "mouse_down", "x": 200, "y": 200, "ts": 2.0, "button": "left"},
    ]

    call_count = [0]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        call_count[0] += 1
        if call_count[0] == 1:
            return win_no_num_a
        return win_no_num_b

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    # Different pid -> different identity -> wait_until inserted
    wait_events = [ev for ev in result if ev["type"] == "wait_until"]
    assert len(wait_events) == 1


def test_scroll_with_phase_in_multi_window():
    """Scroll events with phase data should pass through in multi-window mode."""
    raw_events = [
        {"kind": "mouse_down", "x": 400, "y": 300, "ts": 1.0, "button": "left"},
        {
            "kind": "scroll",
            "x": 400,
            "y": 300,
            "ts": 2.0,
            "delta_y": -5,
            "delta_x": 3,
            "phase": 2,
            "momentum_phase": 0,
            "is_continuous": True,
        },
    ]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return WIN_A

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    scroll_events = [ev for ev in result if ev["type"] == "scroll"]
    assert len(scroll_events) == 1
    assert scroll_events[0]["delta"]["y"] == -5
    assert scroll_events[0]["delta"]["x"] == 3
    # Verify phase fields are present (momentum_phase=0 is omitted for compactness)
    assert scroll_events[0].get("phase") == 2
    assert scroll_events[0].get("is_continuous") is True


def test_selector_platform_is_mac():
    """Selector should always have platform='mac'."""
    raw_events = [
        {"kind": "mouse_down", "x": 400, "y": 300, "ts": 1.0, "button": "left"},
    ]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return WIN_A

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    selector_events = [ev for ev in result if ev["type"] == "window_selector"]
    assert len(selector_events) == 1
    assert selector_events[0]["selector"]["platform"] == "mac"


def test_relative_position_computed_correctly():
    """Relative position should be computed from the target window bounds."""
    win = _make_win(
        title="Test",
        pid=100,
        owner_name="App",
        bounds=Rect(x=100, y=200, w=800, h=600),
        window_number=10,
    )

    raw_events = [
        {"kind": "mouse_down", "x": 500, "y": 500, "ts": 1.0, "button": "left"},
    ]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return win

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    click_events = [ev for ev in result if ev["type"] == "click"]
    assert len(click_events) == 1
    # rx = (500-100)/800 = 0.5, ry = (500-200)/600 = 0.5
    assert click_events[0]["pos"]["rx"] == 0.5
    assert click_events[0]["pos"]["ry"] == 0.5


def test_default_timeout_ms():
    """Default timeout should be 5000ms."""
    raw_events = [
        {"kind": "mouse_down", "x": 400, "y": 300, "ts": 1.0, "button": "left"},
        {"kind": "mouse_down", "x": 350, "y": 250, "ts": 2.0, "button": "left"},
    ]

    coord_to_win = {
        (400, 300): WIN_A,
        (350, 250): WIN_B,
    }

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return coord_to_win.get((x, y))

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    wait_events = [ev for ev in result if ev["type"] == "wait_until"]
    assert len(wait_events) == 1
    assert wait_events[0]["timeout_ms"] == 5000


def test_custom_timeout_ms():
    """Custom timeout should be used in wait_until events."""
    raw_events = [
        {"kind": "mouse_down", "x": 400, "y": 300, "ts": 1.0, "button": "left"},
        {"kind": "mouse_down", "x": 350, "y": 250, "ts": 2.0, "button": "left"},
    ]

    coord_to_win = {
        (400, 300): WIN_A,
        (350, 250): WIN_B,
    }

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return coord_to_win.get((x, y))

    result = process_raw_events_multi_window(
        raw_events, fake_window_from_point, window_wait_timeout_ms=10000
    )

    wait_events = [ev for ev in result if ev["type"] == "wait_until"]
    assert len(wait_events) == 1
    assert wait_events[0]["timeout_ms"] == 10000


def test_title_none_not_in_selector():
    """When window title is None, selector should not include title key."""
    win_no_title = _make_win(
        title=None,  # type: ignore[arg-type]
        pid=100,
        owner_name="AppX",
        bounds=Rect(x=0, y=0, w=800, h=600),
        window_number=99,
    )

    raw_events = [
        {"kind": "mouse_down", "x": 100, "y": 100, "ts": 1.0, "button": "left"},
    ]

    def fake_window_from_point(x: int, y: int) -> WindowRef | None:
        return win_no_title

    result = process_raw_events_multi_window(raw_events, fake_window_from_point)

    selector_events = [ev for ev in result if ev["type"] == "window_selector"]
    assert len(selector_events) == 1
    assert "title" not in selector_events[0]["selector"]
