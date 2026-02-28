import json

from typer.testing import CliRunner

from uitrace.cli import app


def test_list_json_shape():
    runner = CliRunner()
    r = runner.invoke(app, ["list", "--json"])
    assert r.exit_code in (0, 11)
    data = json.loads(r.stdout)
    assert isinstance(data, list)
    if data:
        w = data[0]
        for k in ["id", "pid", "bounds"]:
            assert k in w


def test_list_default_exits_ok():
    runner = CliRunner()
    r = runner.invoke(app, ["list"])
    assert r.exit_code in (0, 11)
