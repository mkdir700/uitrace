from pathlib import Path

import pytest

from uitrace.core.jsonl import read_events
from uitrace.errors import ErrorCode, UitError


def test_read_events_reports_line_number(tmp_path: Path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"v":1,"type":"session_end","ts":0}\nnot-json\n', encoding="utf-8")
    with pytest.raises(UitError) as e:
        list(read_events(p))
    assert e.value.code == ErrorCode.SCHEMA_INVALID
    assert "line 2" in e.value.message
