import json

import pytest

from garmin_mcp import cli_auth, cli_export
from garmin_mcp.config import Config

from . import fake


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("GARMIN_MCP_HOME", str(tmp_path))
    monkeypatch.setenv("GARMIN_MCP_FAKE", "tests.fake:FakeGarmin")
    return tmp_path


def test_login_asks_in_the_terminal_and_never_stores_the_password(home, monkeypatch, capsys):
    dumped = []
    monkeypatch.setattr(fake._Client, "dump", lambda self, path: dumped.append(path))
    monkeypatch.setattr("builtins.input", lambda prompt="": "me@example.com")
    monkeypatch.setattr(cli_auth.getpass, "getpass", lambda prompt="": "s3cret")
    assert cli_auth.login(Config(home=home)) == 0
    assert dumped == [str(home)]
    assert "Connected as Test Runner" in capsys.readouterr().out
    assert not any("s3cret" in p.read_text() for p in home.iterdir() if p.is_file())


def test_status(home, capsys):
    assert cli_auth.status(Config(home=home)) == 1
    assert "Not connected" in capsys.readouterr().out
    (home / "garmin_tokens.json").write_text("{}")
    assert cli_auth.status(Config(home=home)) == 0
    assert "Connected as Test Runner" in capsys.readouterr().out


def test_export_writes_daily_rows(home, tmp_path):
    (home / "garmin_tokens.json").write_text("{}")
    out = tmp_path / "out" / "garmin-daily.json"
    runs_out = tmp_path / "out" / "garmin-runs.json"
    cli_export.main(["--start", "2026-10-23", "--end", "2026-10-25", "--out", str(out),
                     "--runs-out", str(runs_out), "--pause", "0"])
    rows = json.loads(out.read_text())
    assert [r["date"] for r in rows] == ["2026-10-23", "2026-10-24", "2026-10-25"]
    assert rows[-1]["readiness"] == 72
    assert json.loads(runs_out.read_text())[0]["te_label"] == "aerobic base"
