from typer.testing import CliRunner

from uitrace.cli import app


def test_cli_help_lists_commands():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["list", "record", "play", "show", "validate", "doctor"]:
        assert cmd in result.stdout
