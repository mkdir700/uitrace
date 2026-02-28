import json
from pathlib import Path

from typer.testing import CliRunner

from uitrace.cli import app


def _json_lines(output: str) -> list[dict]:
    rows: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_play_multi_window_dry_run_emits_correct_sequence():
    """Dry-run of a multi-window trace produces the expected event sequence."""
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_multi_window.jsonl")

    result = runner.invoke(app, ["play", "--dry-run", str(p)])

    assert result.exit_code == 0
    rows = _json_lines(result.stdout)

    # Expected event_type sequence (session_start and session_end are not playable steps)
    assert [row["event_type"] for row in rows] == [
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

    # Step numbering is stable and 0-based
    assert [row["step"] for row in rows] == list(range(11))

    # All rows are step_result, dry_run, ok
    assert all(row["type"] == "step_result" for row in rows)
    assert all(row["dry_run"] is True for row in rows)
    assert all(row["status"] == "ok" for row in rows)
    assert all(row["ok"] is True for row in rows)
