import pytest
from pydantic import ValidationError

from uitrace.core.models import Click, Scroll, SessionEnd, WaitUntil


def test_parse_valid_click_event():
    raw = {
        "v": 1,
        "type": "click",
        "ts": 1.0,
        "pos": {"rx": 0.5, "ry": 0.5},
        "screen": {"x": 100, "y": 200},
        "button": "left",
        "count": 1,
    }
    ev = Click.model_validate(raw)
    assert ev.type == "click"


def test_extra_fields_forbidden():
    raw = {"v": 1, "type": "session_end", "ts": 0.0, "nope": 1}
    with pytest.raises(Exception):
        SessionEnd.model_validate(raw)


# --- wait_until window_found tests ---


def test_parse_wait_until_window_found():
    raw = {
        "v": 1,
        "type": "wait_until",
        "ts": 5.0,
        "kind": "window_found",
        "selector": {"title_regex": ".*Calculator.*"},
        "timeout_ms": 3000,
    }
    ev = WaitUntil.model_validate(raw)
    assert ev.kind == "window_found"
    assert ev.selector is not None
    assert ev.selector.title_regex == ".*Calculator.*"
    assert ev.timeout_ms == 3000
    assert ev.pos is None
    assert ev.rgb is None
    assert ev.tolerance is None


def test_wait_until_window_found_missing_selector():
    raw = {
        "v": 1,
        "type": "wait_until",
        "ts": 5.0,
        "kind": "window_found",
        "timeout_ms": 3000,
    }
    with pytest.raises(ValidationError):
        WaitUntil.model_validate(raw)


def test_wait_until_pixel_with_selector_rejected():
    raw = {
        "v": 1,
        "type": "wait_until",
        "ts": 5.0,
        "kind": "pixel",
        "pos": {"rx": 0.5, "ry": 0.5},
        "rgb": [255, 0, 0],
        "tolerance": 5,
        "timeout_ms": 1000,
        "selector": {"title": "Calc"},
    }
    with pytest.raises(ValidationError):
        WaitUntil.model_validate(raw)


def test_wait_until_window_found_with_pos_rejected():
    raw = {
        "v": 1,
        "type": "wait_until",
        "ts": 5.0,
        "kind": "window_found",
        "selector": {"title": "Calc"},
        "pos": {"rx": 0.5, "ry": 0.5},
        "rgb": [255, 0, 0],
        "timeout_ms": 1000,
    }
    with pytest.raises(ValidationError):
        WaitUntil.model_validate(raw)


def test_wait_until_window_found_extra_fields_rejected():
    raw = {
        "v": 1,
        "type": "wait_until",
        "ts": 5.0,
        "kind": "window_found",
        "selector": {"title": "Calc"},
        "timeout_ms": 1000,
        "bogus_field": 42,
    }
    with pytest.raises(ValidationError):
        WaitUntil.model_validate(raw)


# --- Scroll roundtrip tests ---


def test_scroll_roundtrip_with_all_new_fields():
    """Scroll with phase, momentum_phase, is_continuous roundtrips correctly."""
    raw = {
        "v": 1,
        "type": "scroll",
        "ts": 1.0,
        "pos": {"rx": 0.5, "ry": 0.9},
        "screen": {"x": 500, "y": 640},
        "delta": {"x": 5, "y": -10},
        "phase": 2,
        "momentum_phase": 3,
        "is_continuous": True,
    }
    ev = Scroll.model_validate(raw)
    assert ev.phase == 2
    assert ev.momentum_phase == 3
    assert ev.is_continuous is True
    assert ev.delta == {"x": 5, "y": -10}
    # Roundtrip: dump and re-parse
    dumped = ev.model_dump()
    ev2 = Scroll.model_validate(dumped)
    assert ev2.phase == ev.phase
    assert ev2.momentum_phase == ev.momentum_phase
    assert ev2.is_continuous == ev.is_continuous
    assert ev2.delta == ev.delta


def test_scroll_roundtrip_backward_compat_delta_y_only():
    """Scroll with only delta: {"y": -10} (backward compat, no new fields)."""
    raw = {
        "v": 1,
        "type": "scroll",
        "ts": 0.8,
        "pos": {"rx": 0.5, "ry": 0.9},
        "screen": {"x": 500, "y": 640},
        "delta": {"y": -10},
    }
    ev = Scroll.model_validate(raw)
    assert ev.delta == {"y": -10}
    assert ev.phase is None
    assert ev.momentum_phase is None
    assert ev.is_continuous is None
    # Roundtrip
    dumped = ev.model_dump()
    ev2 = Scroll.model_validate(dumped)
    assert ev2.delta == {"y": -10}
    assert ev2.phase is None


def test_scroll_roundtrip_horizontal_delta():
    """Scroll with delta: {"x": 5, "y": -10} (horizontal + vertical)."""
    raw = {
        "v": 1,
        "type": "scroll",
        "ts": 0.8,
        "pos": {"rx": 0.3, "ry": 0.7},
        "screen": {"x": 300, "y": 500},
        "delta": {"x": 5, "y": -10},
    }
    ev = Scroll.model_validate(raw)
    assert ev.delta == {"x": 5, "y": -10}
    # Roundtrip
    dumped = ev.model_dump()
    ev2 = Scroll.model_validate(dumped)
    assert ev2.delta == {"x": 5, "y": -10}
