from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import quote, unquote

from .errors import HydroParseError
from .utils import quote_path_part


def extract_ui_context(html: str) -> dict[str, Any]:
    return extract_window_json_string(html, "UiContextNew")


def extract_window_json_string(html: str, variable_name: str) -> dict[str, Any]:
    marker = f"window.{variable_name} = '"
    start = html.find(marker)
    if start == -1:
        raise HydroParseError(f"window.{variable_name} not found")

    index = start + len(marker)
    escaped: list[str] = []
    in_escape = False
    while index < len(html):
        char = html[index]
        if in_escape:
            escaped.append(char)
            in_escape = False
        elif char == "\\":
            escaped.append(char)
            in_escape = True
        elif char == "'":
            break
        else:
            escaped.append(char)
        index += 1
    else:
        raise HydroParseError(f"unterminated window.{variable_name} payload")

    payload = bytes("".join(escaped), "utf-8").decode("unicode_escape")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HydroParseError(f"invalid window.{variable_name} JSON") from exc
    if not isinstance(data, dict):
        raise HydroParseError(f"window.{variable_name} payload is not an object")
    return data


def extract_user_context(html: str) -> dict[str, Any]:
    return extract_window_json_string(html, "UserContext")


def choose_markdown(content: Any) -> str:
    if isinstance(content, dict):
        blob = content
    elif isinstance(content, str):
        try:
            loaded = json.loads(content)
        except json.JSONDecodeError:
            return content
        if not isinstance(loaded, dict):
            return content
        blob = loaded
    else:
        return ""

    for key in ("zh", "en"):
        value = blob.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for value in blob.values():
        if isinstance(value, str) and value.strip():
            return value
    return ""


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def format_limit(minimum: Any, maximum: Any, unit: str) -> str:
    if minimum in (None, "") and maximum in (None, ""):
        return ""
    if minimum == maximum:
        return f"{minimum} {unit}"
    if minimum in (None, ""):
        return f"<= {maximum} {unit}"
    if maximum in (None, ""):
        return f">= {minimum} {unit}"
    return f"{minimum}-{maximum} {unit}"


def rewrite_attachment_links(
    markdown: str,
    base_url: str,
    pid: str,
    attachment_names: set[str],
) -> str:
    if not markdown or not attachment_names:
        return markdown
    base = re.escape(base_url.rstrip("/"))
    quoted_pid = re.escape(quote(str(pid), safe=""))
    pattern = re.compile(
        rf"\((?:file://|\./[^/)]+/file/|/p/{quoted_pid}/file/|{base}/p/{quoted_pid}/file/)"
        r"([^)\s?]+)(?:\?[^)]*)?\)"
    )

    def replace(match: re.Match[str]) -> str:
        filename = unquote(match.group(1))
        if filename not in attachment_names:
            return match.group(0)
        return f"(files/{quote_path_part(filename)})"

    return pattern.sub(replace, markdown)
