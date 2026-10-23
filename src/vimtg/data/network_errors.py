"""One user-facing wording for failed requests to Scryfall, the deck
sites and EDHREC: what went wrong, in a sentence, and how to retry."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import httpx

_PROXY_ENV = ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")


def _proxy_hint() -> str:
    """' (via proxy <url>)' when a proxy is configured, else ''."""
    for var in _PROXY_ENV:
        raw = os.environ.get(var)
        if raw:
            # host[:port] only — the URL may carry credentials
            parsed = urlsplit(raw if "//" in raw else f"//{raw}")
            host = parsed.hostname or "?"
            port = f":{parsed.port}" if parsed.port else ""
            return f" (via proxy {host}{port})"
    return ""


def describe_network_error(
    exc: BaseException, *, service: str, retry: str, host: str = ""
) -> str:
    """A user-facing explanation of a failed request to `service`
    (reached at `host`), ending with `retry`, the advice for where the
    message shows ("run `vimtg sync` to retry", "try again")."""
    host = host or service
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return f"{service} is rate-limiting requests — wait a minute, then {retry}"
        if status == 407:
            return (
                f"The proxy{_proxy_hint()} wants authentication — put the "
                f"credentials in HTTPS_PROXY, then {retry}"
            )
        if status >= 500:
            return f"{service} is unavailable (HTTP {status}) — {retry} later"
        return f"{service} returned HTTP {status} — {retry}"
    if isinstance(exc, httpx.ProxyError):
        return (
            f"The proxy{_proxy_hint()} refused the connection ({exc}) — "
            f"check HTTPS_PROXY, then {retry}"
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"Timed out talking to {service} — check your connection and {retry}"
    if isinstance(exc, httpx.ConnectError):
        text = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in text or "certificate" in text.lower():
            return (
                f"Could not verify {service}'s TLS certificate — a proxy or "
                "firewall may be intercepting HTTPS (point SSL_CERT_FILE at "
                f"its CA bundle), then {retry}"
            )
        return (
            f"Could not reach {host}{_proxy_hint()} — you seem to "
            f"be offline; {retry} once connected"
        )
    if isinstance(exc, httpx.HTTPError):
        return f"Could not reach {service} ({exc}) — check your connection and {retry}"
    return f"{exc} — {retry}"
