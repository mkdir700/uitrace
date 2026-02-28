from pathlib import Path

from typer.testing import CliRunner

from uitrace.cli import app


def test_validate_ok(tmp_path: Path):
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_valid.jsonl")
    r = runner.invoke(app, ["validate", str(p)])
    assert r.exit_code == 0


def test_validate_bad_returns_40():
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_invalid.jsonl")
    r = runner.invoke(app, ["validate", str(p)])
    assert r.exit_code == 40
