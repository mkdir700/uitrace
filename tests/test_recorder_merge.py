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
