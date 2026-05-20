from __future__ import annotations

from hydro_cli.config import Config, ConfigStore, CookieRecord


def test_config_roundtrip(tmp_path) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    config = Config(
        base_url="localhost:8888/",
        username="alice",
        uid="3",
        cookies=[CookieRecord(name="sid", value="abc")],
    )

    store.save(config)
    loaded = store.load()

    assert loaded.base_url == "http://localhost:8888"
    assert loaded.username == "alice"
    assert loaded.uid == "3"
    assert loaded.is_logged_in
