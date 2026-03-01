from uitrace.recorder.merge import merge_mouse_events


def test_merge_down_up_to_click():
    raw = [
        {"kind": "mouse_down", "ts": 0.0, "x": 10, "y": 20, "button": "left"},
        {"kind": "mouse_up", "ts": 0.01, "x": 10, "y": 20, "button": "left"},
    ]
    out = list(merge_mouse_events(raw))
    assert len(out) == 1
    assert out[0]["kind"] == "click"
    assert out[0]["button"] == "left"
    assert out[0]["count"] == 1


def test_merge_scroll_coalesce():
    raw = [
        {"kind": "scroll", "ts": 0.0, "x": 100, "y": 200, "delta_y": -10},
        {"kind": "scroll", "ts": 0.03, "x": 100, "y": 200, "delta_y": -15},
        {"kind": "scroll", "ts": 0.04, "x": 100, "y": 200, "delta_y": -5},
    ]
    out = list(merge_mouse_events(raw))
    assert len(out) == 1
    assert out[0]["kind"] == "scroll"
    assert out[0]["delta_y"] == -30


def test_orphan_mouse_down_discarded():
    raw = [
        {"kind": "mouse_down", "ts": 0.0, "x": 10, "y": 20, "button": "left"},
        # no mouse_up within 500ms
        {"kind": "mouse_down", "ts": 0.6, "x": 30, "y": 40, "button": "left"},
        {"kind": "mouse_up", "ts": 0.61, "x": 30, "y": 40, "button": "left"},
    ]
    out = list(merge_mouse_events(raw))
    assert len(out) == 1
    assert out[0]["x"] == 30


def test_double_click_detection():
    raw = [
        {"kind": "mouse_down", "ts": 0.0, "x": 10, "y": 20, "button": "left"},
        {"kind": "mouse_up", "ts": 0.01, "x": 10, "y": 20, "button": "left"},
        {"kind": "mouse_down", "ts": 0.15, "x": 10, "y": 20, "button": "left"},
        {"kind": "mouse_up", "ts": 0.16, "x": 10, "y": 20, "button": "left"},
    ]
    out = list(merge_mouse_events(raw))
    assert len(out) == 1
    assert out[0]["kind"] == "click"
    assert out[0]["count"] == 2


def test_scroll_separate_windows():
    """Scrolls far apart in time should not coalesce."""
    raw = [
        {"kind": "scroll", "ts": 0.0, "x": 100, "y": 200, "delta_y": -10},
        {"kind": "scroll", "ts": 0.1, "x": 100, "y": 200, "delta_y": -5},
    ]
    out = list(merge_mouse_events(raw))
    assert len(out) == 2


def test_merge_scroll_phase_no_coalesce():
    """Scroll events with non-zero phase fields should NOT be coalesced."""
    raw = [
        {"kind": "scroll", "ts": 0.0, "x": 100, "y": 200, "delta_y": -10, "phase": 1},
        {"kind": "scroll", "ts": 0.01, "x": 100, "y": 200, "delta_y": -15, "phase": 2},
        {"kind": "scroll", "ts": 0.02, "x": 100, "y": 200, "delta_y": -5, "phase": 4},
    ]
    out = list(merge_mouse_events(raw))
    # All 3 events preserved individually (not coalesced)
    assert len(out) == 3
    assert out[0]["delta_y"] == -10
    assert out[0]["phase"] == 1
    assert out[1]["delta_y"] == -15
    assert out[1]["phase"] == 2
    assert out[2]["delta_y"] == -5
    assert out[2]["phase"] == 4


def test_merge_scroll_mixed_phase_legacy():
    """Mix of phased and legacy (no-phase) scroll events in sequence."""
    raw = [
        # Legacy group (no phase) — should coalesce
        {"kind": "scroll", "ts": 0.0, "x": 100, "y": 200, "delta_y": -10},
        {"kind": "scroll", "ts": 0.01, "x": 100, "y": 200, "delta_y": -5},
        # Gap > 50ms forces new group
        # Phased group — should NOT coalesce
        {"kind": "scroll", "ts": 0.1, "x": 100, "y": 200, "delta_y": -3, "phase": 1},
        {"kind": "scroll", "ts": 0.11, "x": 100, "y": 200, "delta_y": -7, "phase": 2},
    ]
    out = list(merge_mouse_events(raw))
    # First group: coalesced into 1 event, second group: 2 individual events
    assert len(out) == 3
    # Legacy coalesced
    assert out[0]["delta_y"] == -15
    # Phase events preserved individually
    assert out[1]["delta_y"] == -3
    assert out[1]["phase"] == 1
    assert out[2]["delta_y"] == -7
    assert out[2]["phase"] == 2


def test_merge_scroll_phase_fields_preserved():
    """Verify delta_x, phase, momentum_phase, is_continuous pass through merge."""
    raw = [
        {
            "kind": "scroll",
            "ts": 0.0,
            "x": 100,
            "y": 200,
            "delta_y": -10,
            "delta_x": 5,
            "phase": 1,
            "momentum_phase": 0,
            "is_continuous": True,
        },
        {
            "kind": "scroll",
            "ts": 0.01,
            "x": 100,
            "y": 200,
            "delta_y": -8,
            "delta_x": 3,
            "phase": 2,
            "momentum_phase": 0,
            "is_continuous": True,
        },
    ]
    out = list(merge_mouse_events(raw))
    # phase=1 and phase=2 are non-zero, so no coalescing
    assert len(out) == 2
    # First event
    assert out[0]["delta_y"] == -10
    assert out[0]["delta_x"] == 5
    assert out[0]["phase"] == 1
    assert out[0]["momentum_phase"] == 0
    assert out[0]["is_continuous"] is True
    # Second event
    assert out[1]["delta_y"] == -8
    assert out[1]["delta_x"] == 3
    assert out[1]["phase"] == 2
    assert out[1]["momentum_phase"] == 0
    assert out[1]["is_continuous"] is True
