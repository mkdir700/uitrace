import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from uitrace.cli import app
from uitrace.platform.base import PermissionReport, PermissionStatus


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
    assert [row["event_type"] for row in rows] == [
        "window_selector",
        "window_bounds",
        "assert",
        "click",
        "scroll",
    ]
    assert [row["step"] for row in rows] == [0, 1, 2, 3, 4]
    assert all(row["type"] == "step_result" for row in rows)
    assert all(row["dry_run"] is True for row in rows)
    assert all(row["status"] == "ok" for row in rows)
    assert all(row["ok"] is True for row in rows)


def test_play_non_dry_run_emits_permission_denied_and_returns_11():
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_valid.jsonl")

    denied_report = PermissionReport(
        accessibility=PermissionStatus.denied,
        input_monitoring=PermissionStatus.granted,
        screen_recording=PermissionStatus.granted,
    )

    with patch(
        "uitrace.platform.macos.MacOSPlatform.check_permissions",
        return_value=denied_report,
    ):
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


def test_play_dry_run_from_to_step_slicing():
    """--from-step and --to-step slice to the requested 0-based range."""
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_valid.jsonl")

    result = runner.invoke(app, ["play", "--dry-run", "--from-step", "1", "--to-step", "2", str(p)])

    assert result.exit_code == 0
    rows = _json_lines(result.stdout)
    # All 5 playable steps are emitted (steps 0..4) but only 1 and 2 are "ok"
    assert len(rows) == 5
    statuses = [(row["step"], row["status"]) for row in rows]
    assert statuses == [
        (0, "skipped"),
        (1, "ok"),
        (2, "ok"),
        (3, "skipped"),
        (4, "skipped"),
    ]


def test_play_dry_run_skipped_steps_have_event_idx():
    """Skipped steps still carry event_idx (0-based index in the original stream)."""
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_valid.jsonl")

    result = runner.invoke(app, ["play", "--dry-run", "--from-step", "3", "--to-step", "3", str(p)])

    assert result.exit_code == 0
    rows = _json_lines(result.stdout)
    assert len(rows) == 5
    # event_idx is 0-based index in the original event stream
    # session_start(0), window_selector(1), window_bounds(2), assert(3), click(4), scroll(5)
    assert [row["event_idx"] for row in rows] == [1, 2, 3, 4, 5]
    assert [row["step"] for row in rows] == [0, 1, 2, 3, 4]
    assert [row["status"] for row in rows] == [
        "skipped",
        "skipped",
        "skipped",
        "ok",
        "skipped",
    ]
