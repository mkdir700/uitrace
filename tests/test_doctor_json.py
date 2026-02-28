"""Tests for the doctor command."""

import json

from typer.testing import CliRunner

from uitrace.cli import app


def test_doctor_json_is_parseable():
    runner = CliRunner()
    r = runner.invoke(app, ["doctor", "--json"])
    assert r.exit_code in (0, 11)
    data = json.loads(r.stdout)
    assert "platform" in data
    assert "permissions" in data
    assert "executable" in data
    assert "hints" in data


def test_doctor_json_permissions_have_status():
    runner = CliRunner()
    r = runner.invoke(app, ["doctor", "--json"])
    data = json.loads(r.stdout)
    for perm_name in ["accessibility", "input_monitoring", "screen_recording"]:
        assert perm_name in data["permissions"]
        assert "status" in data["permissions"][perm_name]
        assert data["permissions"][perm_name]["status"] in (
            "granted",
            "denied",
            "unknown",
        )


def test_doctor_non_json_exits_without_crash():
    runner = CliRunner()
    r = runner.invoke(app, ["doctor"])
    assert r.exit_code in (0, 11)
