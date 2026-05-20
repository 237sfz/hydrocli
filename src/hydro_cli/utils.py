from __future__ import annotations

from urllib.parse import quote, urljoin


def normalize_base_url(base_url: str) -> str:
    value = base_url.strip()
    if not value:
        raise ValueError("base URL cannot be empty")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value.rstrip("/")


def absolute_url(base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


def quote_path_part(value: object) -> str:
    return quote(str(value), safe="")
