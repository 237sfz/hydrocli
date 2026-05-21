from __future__ import annotations

import httpx
import pytest

from hydro_cli.client import HydroClient
from hydro_cli.config import Config
from hydro_cli.errors import HydroRequestError


def test_client_retries_hydro_403_rate_limit(monkeypatch) -> None:
    client = HydroClient(Config(base_url="http://localhost:8888"))
    calls = 0

    def fake_request(method: str, url: str, **_kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        request = httpx.Request(method, url)
        if calls == 1:
            return httpx.Response(
                403,
                request=request,
                text="Too frequent operations of global (limit: 100 operations in 5 seconds).",
            )
        return httpx.Response(200, request=request, text="ok")

    monkeypatch.setattr(client.client, "request", fake_request)
    monkeypatch.setattr("hydro_cli.client.time.sleep", lambda _seconds: None)

    try:
        response = client.request("GET", "/p/B5300")
    finally:
        client.close()

    assert response.text == "ok"
    assert calls == 2


def test_client_does_not_retry_normal_403(monkeypatch) -> None:
    client = HydroClient(Config(base_url="http://localhost:8888"))
    calls = 0

    def fake_request(method: str, url: str, **_kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        request = httpx.Request(method, url)
        return httpx.Response(403, request=request, text="permission denied")

    monkeypatch.setattr(client.client, "request", fake_request)
    monkeypatch.setattr("hydro_cli.client.time.sleep", lambda _seconds: None)

    try:
        try:
            client.request("GET", "/p/private")
        except Exception as exc:
            assert "failed: 403" in str(exc)
        else:
            raise AssertionError("request unexpectedly succeeded")
    finally:
        client.close()

    assert calls == 1


def test_client_stream_reads_error_body_before_classifying_rate_limit(monkeypatch) -> None:
    client = HydroClient(Config(base_url="http://localhost:8888"))
    calls = 0

    class FakeStream:
        def __init__(self, response: httpx.Response) -> None:
            self.response = response

        def __enter__(self) -> httpx.Response:
            return self.response

        def __exit__(self, *_exc: object) -> None:
            return None

    def fake_stream(method: str, url: str) -> FakeStream:
        nonlocal calls
        calls += 1
        request = httpx.Request(method, url)
        response = httpx.Response(
            403,
            request=request,
            stream=httpx.ByteStream(
                b"Too frequent operations of global (limit: 100 operations in 5 seconds)."
            ),
        )
        return FakeStream(response)

    monkeypatch.setattr(client.client, "stream", fake_stream)

    try:
        with pytest.raises(HydroRequestError) as exc_info:
            with client.stream("/p/B5300/file/data.zip"):
                pass
    finally:
        client.close()

    assert calls == 1
    assert exc_info.value.status_code == 403
    assert "Too frequent operations" in exc_info.value.response_text
