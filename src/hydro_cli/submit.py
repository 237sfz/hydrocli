from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from .client import HydroClient
from .errors import HydroCliError
from .parsing import extract_ui_context
from .utils import quote_path_part


EXTENSION_LANGS = {
    ".c": "c",
    ".cc": "cc.cc20o2",
    ".cpp": "cc.cc20o2",
    ".cxx": "cc.cc20o2",
    ".py": "py.py3",
    ".rs": "rs",
    ".go": "go",
    ".java": "java",
    ".js": "js",
    ".kt": "kt.jvm",
}


class SubmitService:
    def __init__(self, client: HydroClient) -> None:
        self.client = client

    def languages(self, pid: str) -> list[str]:
        html = self.client.get_text(f"/p/{quote_path_part(pid)}/submit")
        langs = _languages_from_context(html)
        if langs:
            return langs
        return _languages_from_select(html)

    def submit(self, pid: str, source_path: Path, lang: str = "") -> str:
        return self.submit_to_path(f"/p/{quote_path_part(pid)}/submit", source_path, lang)

    def submit_to_path(self, submit_path: str, source_path: Path, lang: str = "") -> str:
        source = source_path.read_text(encoding="utf-8")
        chosen_lang = lang or infer_language(source_path)
        if not chosen_lang:
            raise HydroCliError("language is required; pass --lang")

        response = self.client.raw_request(
            "POST",
            submit_path,
            files={
                "lang": (None, chosen_lang),
                "code": (None, source),
            },
            follow_redirects=False,
        )
        location = response.headers.get("location", "")
        match = re.search(r"/record/([^/?#]+)", location or response.text)
        if not match:
            raise HydroCliError("submission did not return a record id")
        return match.group(1)


def infer_language(source_path: Path) -> str:
    return EXTENSION_LANGS.get(source_path.suffix.lower(), "")


def _languages_from_context(html: str) -> list[str]:
    try:
        ui = extract_ui_context(html)
    except Exception:
        return []
    pdoc = ui.get("pdoc") if isinstance(ui, dict) else None
    config = pdoc.get("config") if isinstance(pdoc, dict) else None
    langs = config.get("langs") if isinstance(config, dict) else None
    if not isinstance(langs, list):
        return []
    return [str(item) for item in langs]


def _languages_from_select(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    values: list[str] = []
    for option in soup.select('select[name="lang"] option[value]'):
        value = str(option.get("value") or "")
        if value:
            values.append(value)
    return values
