from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.cookiejar import Cookie
from typing import Any

import httpx

from .config import Config, CookieRecord
from .errors import HydroAuthError, HydroParseError, HydroRequestError
from .parsing import extract_ui_context, extract_user_context
from .utils import absolute_url, normalize_base_url


DEFAULT_TIMEOUT = 30.0


def _cookie_from_record(record: CookieRecord) -> Cookie:
    return Cookie(
        version=0,
        name=record.name,
        value=record.value,
        port=None,
        port_specified=False,
        domain=record.domain,
        domain_specified=bool(record.domain),
        domain_initial_dot=record.domain.startswith("."),
        path=record.path or "/",
        path_specified=True,
        secure=record.secure,
        expires=record.expires,
        discard=record.expires is None,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


def dump_cookies(client: httpx.Client) -> list[CookieRecord]:
    records: list[CookieRecord] = []
    for cookie in client.cookies.jar:
        records.append(
            CookieRecord(
                name=cookie.name,
                value=cookie.value,
                domain=cookie.domain,
                path=cookie.path,
                secure=cookie.secure,
                expires=cookie.expires,
            )
        )
    return records


def _is_retryable_request_error(exc: HydroRequestError) -> bool:
    status_code = exc.status_code
    if status_code == 429 or (status_code is not None and 500 <= status_code < 600):
        return True
    return status_code == 403 and _is_rate_limit_response(exc.response_text)


def _is_rate_limit_response(response_text: str) -> bool:
    normalized = response_text.lower()
    return "too frequent operations" in normalized or "rate limit" in normalized


class HydroClient:
    def __init__(self, config: Config, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = normalize_base_url(config.base_url)
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "hydro-cli/0.1"},
        )
        for record in config.cookies:
            self.client.cookies.jar.set_cookie(_cookie_from_record(record))

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "HydroClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @contextmanager
    def stream(self, path: str) -> Iterator[httpx.Response]:
        url = absolute_url(self.base_url, path)
        try:
            with self.client.stream("GET", url) as response:
                self._ensure_success(response)
                yield response
        except HydroRequestError:
            raise
        except httpx.HTTPError as exc:
            raise HydroRequestError(str(exc)) from exc

    def request(
        self,
        method: str,
        path: str,
        *,
        follow_redirects: bool | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        url = absolute_url(self.base_url, path)
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                request_kwargs = dict(kwargs)
                if follow_redirects is not None:
                    request_kwargs["follow_redirects"] = follow_redirects
                response = self.client.request(method, url, **request_kwargs)
                self._ensure_success(response)
                return response
            except HydroRequestError as exc:
                last_exc = exc
                if attempt == 3 or not _is_retryable_request_error(exc):
                    break
                time.sleep(0.4 * attempt)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == 3:
                    break
                time.sleep(0.4 * attempt)
        if isinstance(last_exc, HydroRequestError):
            raise last_exc
        raise HydroRequestError(str(last_exc) if last_exc else "request failed") from last_exc

    def raw_request(
        self,
        method: str,
        path: str,
        *,
        follow_redirects: bool | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        url = absolute_url(self.base_url, path)
        request_kwargs = dict(kwargs)
        if follow_redirects is not None:
            request_kwargs["follow_redirects"] = follow_redirects
        try:
            response = self.client.request(method, url, **request_kwargs)
        except httpx.HTTPError as exc:
            raise HydroRequestError(str(exc)) from exc
        if response.status_code >= 400:
            raise HydroRequestError(
                f"{response.request.method} {response.url} failed: {response.status_code}",
                status_code=response.status_code,
                response_text=response.text,
            )
        return response

    def get_text(self, path: str, **kwargs: Any) -> str:
        return self.request("GET", path, **kwargs).text

    def get_json(self, path: str, **kwargs: Any) -> Any:
        response = self.request("GET", path, **kwargs)
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise HydroParseError(f"expected JSON from {path}") from exc

    def login(self, username: str, password: str) -> dict[str, str]:
        response = self.request(
            "POST",
            "/login",
            data={
                "uname": username,
                "password": password,
                "rememberme": "on",
                "tfa": "",
                "authnChallenge": "",
                "login_submit": "submit",
            },
            follow_redirects=False,
        )
        if response.status_code not in {302, 303}:
            message = _extract_error_message(response.text)
            raise HydroAuthError(message or f"login failed with status {response.status_code}")
        if not self.client.cookies.get("sid"):
            raise HydroAuthError("login failed: sid cookie missing")
        user = self.whoami()
        if not user.get("username"):
            raise HydroAuthError("login succeeded but current user could not be detected")
        return user

    def logout(self) -> None:
        try:
            self.request("GET", "/logout")
        finally:
            self.client.cookies.clear()

    def whoami(self) -> dict[str, str]:
        html = self.get_text("/")
        user = _find_user_context(html)
        if not user.get("username"):
            return {"username": "", "uid": ""}
        return user

    def _ensure_success(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise HydroRequestError(
                f"{response.request.method} {response.url} failed: {response.status_code}",
                status_code=response.status_code,
                response_text=_response_text(response),
            )
        if "/login" in str(response.url) and 'name="uname"' in _response_text(response):
            raise HydroAuthError("login required")


def _response_text(response: httpx.Response) -> str:
    try:
        return response.text
    except httpx.ResponseNotRead:
        response.read()
        return response.text


def _find_user_context(html: str) -> dict[str, str]:
    try:
        user_context = extract_user_context(html)
    except HydroParseError:
        user_context = {}
    user = _normalize_user(user_context)
    if user.get("username"):
        return user

    try:
        ui = extract_ui_context(html)
    except HydroParseError:
        return {"username": "", "uid": ""}
    return _find_user(ui)


def _find_user(ui: dict[str, Any]) -> dict[str, str]:
    candidates: list[Any] = []
    for key in ("user", "udoc", "UserContext", "currentUser"):
        candidates.append(ui.get(key))
    if isinstance(ui.get("UiContext"), dict):
        candidates.append(ui["UiContext"].get("user"))
    if isinstance(ui.get("payload"), dict):
        candidates.extend([ui["payload"].get("user"), ui["payload"].get("udoc")])

    for item in candidates:
        if not isinstance(item, dict):
            continue
        user = _normalize_user(item)
        if user.get("username"):
            return user
    return {"username": "", "uid": ""}


def _normalize_user(item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        return {"username": "", "uid": ""}
    username = (
        item.get("uname")
        or item.get("username")
        or item.get("name")
        or item.get("displayName")
        or ""
    )
    uid = item.get("_id") or item.get("uid") or item.get("id") or ""
    if username:
        return {"username": str(username), "uid": str(uid)}
    return {"username": "", "uid": ""}


def _extract_error_message(html: str) -> str:
    markers = ("error", "Invalid", "incorrect", "failed")
    for line in html.splitlines():
        clean = " ".join(line.strip().split())
        if clean and any(marker.lower() in clean.lower() for marker in markers):
            return clean
    return ""
