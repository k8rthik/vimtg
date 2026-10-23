"""describe_network_error: one wording for every service vimtg talks to."""

from __future__ import annotations

import httpx
import pytest

from vimtg.data.network_errors import describe_network_error


def test_offline_names_the_host_and_the_retry() -> None:
    msg = describe_network_error(
        httpx.ConnectError("[Errno 8] nodename nor servname provided"),
        service="EDHREC", host="json.edhrec.com", retry="try again",
    )
    assert msg == (
        "Could not reach json.edhrec.com — you seem to be offline; "
        "try again once connected"
    )


def test_timeout_names_the_service() -> None:
    msg = describe_network_error(
        httpx.ReadTimeout("read timed out"), service="Moxfield", retry="try again",
    )
    assert msg == "Timed out talking to Moxfield — check your connection and try again"


def test_rate_limit_names_the_service() -> None:
    request = httpx.Request("GET", "https://json.edhrec.com/x")
    exc = httpx.HTTPStatusError(
        "x", request=request, response=httpx.Response(429, request=request),
    )
    msg = describe_network_error(exc, service="EDHREC", retry="try again")
    assert msg.startswith("EDHREC is rate-limiting requests")


def test_proxy_hint_hides_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@proxy.example:3128")
    msg = describe_network_error(
        httpx.ConnectError("refused"), service="Scryfall",
        host="api.scryfall.com", retry="run `vimtg sync` to retry",
    )
    assert "(via proxy proxy.example:3128)" in msg
    assert "secret" not in msg
