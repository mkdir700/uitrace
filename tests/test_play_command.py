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


def test_play_dry_run_emits_step_results_and_returns_0():
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_valid.jsonl")

    result = runner.invoke(app, ["play", "--dry-run", str(p)])

    assert result.exit_code == 0
    rows = _json_lines(result.stdout)
    assert [row["event_type"] for row in rows] == ["window_bounds", "assert", "click", "scroll"]
    assert [row["step"] for row in rows] == [1, 2, 3, 4]
    assert all(row["type"] == "step_result" for row in rows)
    assert all(row["dry_run"] is True for row in rows)
    assert all(row["status"] == "ok" for row in rows)
    assert all(row["ok"] is True for row in rows)


def test_play_non_dry_run_emits_permission_denied_and_returns_11():
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_valid.jsonl")

    result = runner.invoke(app, ["play", str(p)])

    assert result.exit_code == 11
    rows = _json_lines(result.stdout)
    assert len(rows) >= 1
    assert any(
        row["type"] == "step_result"
        and row["status"] == "error"
        and row["error_code"] == "PERMISSION_DENIED"
        for row in rows
    )
