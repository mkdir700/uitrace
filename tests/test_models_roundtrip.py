import pytest

from uitrace.core.models import Click, SessionEnd, TraceEvent


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
