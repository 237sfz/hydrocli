from __future__ import annotations

from typer.testing import CliRunner

from hydro_cli.cli import app
from hydro_cli.config import Config, ConfigStore


def test_config_set_url_clears_current_contest(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HYDRO_CLI_CONFIG_DIR", str(tmp_path))
    store = ConfigStore()
    store.save(Config(base_url="http://localhost:8888", current_contest_id="abc123"))
    runner = CliRunner()

    result = runner.invoke(app, ["config", "set-url", "http://example.com"])

    assert result.exit_code == 0
    assert store.load().base_url == "http://example.com"
    assert store.load().current_contest_id == ""


def test_config_set_url_keeps_current_contest_when_url_unchanged(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HYDRO_CLI_CONFIG_DIR", str(tmp_path))
    store = ConfigStore()
    store.save(Config(base_url="http://localhost:8888", current_contest_id="abc123"))
    runner = CliRunner()

    result = runner.invoke(app, ["config", "set-url", "localhost:8888/"])

    assert result.exit_code == 0
    assert store.load().base_url == "http://localhost:8888"
    assert store.load().current_contest_id == "abc123"
