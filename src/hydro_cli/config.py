from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .utils import normalize_base_url


APP_NAME = "hydro-cli"


def default_config_dir() -> Path:
    override = os.environ.get("HYDRO_CLI_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / APP_NAME
    return Path.home() / ".config" / APP_NAME


@dataclass(slots=True)
class CookieRecord:
    name: str
    value: str
    domain: str = ""
    path: str = "/"
    secure: bool = False
    expires: int | None = None


@dataclass(slots=True)
class Config:
    base_url: str = "http://localhost:8888"
    default_language: str = ""
    current_contest_id: str = ""
    username: str = ""
    uid: str = ""
    cookies: list[CookieRecord] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        cookies = [
            CookieRecord(**item)
            for item in data.get("cookies", [])
            if isinstance(item, dict) and item.get("name")
        ]
        return cls(
            base_url=normalize_base_url(str(data.get("base_url") or "http://localhost:8888")),
            default_language=str(data.get("default_language") or ""),
            current_contest_id=str(data.get("current_contest_id") or ""),
            username=str(data.get("username") or ""),
            uid=str(data.get("uid") or ""),
            cookies=cookies,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["base_url"] = normalize_base_url(self.base_url)
        return data

    @property
    def is_logged_in(self) -> bool:
        return any(cookie.name == "sid" and cookie.value for cookie in self.cookies)


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_dir() / "config.json"

    def load(self) -> Config:
        if not self.path.exists():
            return Config()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return Config()
        return Config.from_dict(data)

    def save(self, config: Config) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def clear_session(self) -> Config:
        config = self.load()
        config.username = ""
        config.uid = ""
        config.cookies.clear()
        self.save(config)
        return config
