import json
from pathlib import Path

from typer.testing import CliRunner

from uitrace.cli import app


def test_show_json_outputs_summary_object_and_returns_0():
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_valid.jsonl")

    result = runner.invoke(app, ["show", "--json", str(p)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["events_total"] == 7
    assert payload["steps_total"] == 4
    assert payload["ts_max"] == 1.0
    assert payload["types"] == {
        "session_start": 1,
        "window_selector": 1,
        "window_bounds": 1,
        "assert": 1,
        "click": 1,
        "scroll": 1,
        "session_end": 1,
    }


def test_show_default_outputs_human_readable_summary_and_returns_0():
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_valid.jsonl")

    result = runner.invoke(app, ["show", str(p)])

    assert result.exit_code == 0
    assert "Trace Summary" in result.stdout
    assert "events_total" in result.stdout
    assert "steps_total" in result.stdout
    assert "ts_max" in result.stdout
    assert "types" in result.stdout
