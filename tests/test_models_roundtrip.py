import pytest
from pydantic import ValidationError

from uitrace.core.models import Click, SessionEnd, WaitUntil


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
