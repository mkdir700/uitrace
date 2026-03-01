import re

from typer.testing import CliRunner

from uitrace.cli import app


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _clean_help_output(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def test_cli_help_lists_commands():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["list", "record", "play", "show", "validate", "doctor"]:
        assert cmd in result.stdout


def test_record_help_shows_follow_option():
    runner = CliRunner()
    result = runner.invoke(app, ["record", "--help"])
    assert result.exit_code == 0
    output = _clean_help_output(result.stdout)
    assert "--follow" in output
    assert "single or any" in output


def test_record_help_shows_window_wait_timeout_option():
    runner = CliRunner()
    result = runner.invoke(app, ["record", "--help"])
    assert result.exit_code == 0
    output = _clean_help_output(result.stdout)
    assert "--window-wait-timeout-ms" in output
