from __future__ import annotations

from hydro_cli.config import Config, ConfigStore, CookieRecord


def test_config_roundtrip(tmp_path) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    config = Config(
        base_url="localhost:8888/",
        current_contest_id="abc123",
        username="alice",
        uid="3",
        cookies=[CookieRecord(name="sid", value="abc")],
    )

    store.save(config)
    loaded = store.load()

    assert loaded.base_url == "http://localhost:8888"
    assert loaded.current_contest_id == "abc123"
    assert loaded.username == "alice"
    assert loaded.uid == "3"
    assert loaded.is_logged_in


def test_config_loads_old_file_without_current_contest(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"base_url": "localhost:8888"}\n', encoding="utf-8")

    loaded = ConfigStore(path).load()

    assert loaded.base_url == "http://localhost:8888"
    assert loaded.current_contest_id == ""
