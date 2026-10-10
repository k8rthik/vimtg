"""Card data freshness readouts and friendly sync error messages."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import httpx
import pytest

from vimtg.data.scryfall_sync import (
    NO_CARD_DATA,
    card_data_age_days,
    card_data_badge,
    card_data_note,
    describe_sync_error,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
REQ = httpx.Request("GET", "https://api.scryfall.com/bulk-data")


class TestBadge:
    def test_no_cards(self) -> None:
        assert card_data_badge(0, None, NOW) == (NO_CARD_DATA, True)
        assert NO_CARD_DATA == "no card data - :sync to download"

    def test_fresh_data_shows_date_quietly(self) -> None:
        assert card_data_badge(30000, "2026-10-08T09:00:00+00:00", NOW) == (
            "card data as of 2026-10-08", False,
        )

    def test_stale_data_needs_attention(self) -> None:
        assert card_data_badge(30000, "2026-09-01T00:00:00+00:00", NOW) == (
            "card data as of 2026-09-01", True,
        )

    def test_unknown_date(self) -> None:
        text, attention = card_data_badge(10, "garbage", NOW)
        assert ":sync" in text and attention

    def test_naive_timestamp_is_utc(self) -> None:
        assert card_data_age_days("2026-10-03T12:00:00", NOW) == 7


class TestNote:
    def test_fresh_has_no_note(self) -> None:
        assert card_data_note(100, "2026-10-05T00:00:00+00:00", NOW) is None

    def test_exactly_seven_days_has_no_note(self) -> None:
        assert card_data_note(100, "2026-10-03T12:00:00+00:00", NOW) is None

    def test_stale_note(self) -> None:
        note = card_data_note(100, "2026-09-01T00:00:00+00:00", NOW)
        assert note == (
            "note: card data as of 2026-09-01 (39 days old) — "
            "run `vimtg sync` to refresh legality and new cards"
        )

    def test_no_cards_or_unknown_date(self) -> None:
        assert card_data_note(0, "2026-01-01T00:00:00+00:00", NOW) is None
        assert card_data_note(5, None, NOW) is None


class TestDescribeError:
    def test_offline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.delenv(var, raising=False)
        msg = describe_sync_error(
            httpx.ConnectError("[Errno -3] name resolution failed", request=REQ),
            retry="run :sync to retry",
        )
        assert msg == (
            "Could not reach api.scryfall.com — you seem to be offline; "
            "run :sync to retry once connected"
        )

    def test_proxy_refused_names_proxy_without_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "http://user:s3cret@proxy.corp:3128")
        msg = describe_sync_error(httpx.ProxyError("403 Forbidden", request=REQ))
        assert "proxy.corp:3128" in msg
        assert "s3cret" not in msg and "user" not in msg
        assert "HTTPS_PROXY" in msg
        assert msg.endswith("run `vimtg sync` to retry")

    def test_proxy_auth_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "proxy.corp:8080")
        resp = httpx.Response(407, request=REQ)
        msg = describe_sync_error(httpx.HTTPStatusError("407", request=REQ, response=resp))
        assert "proxy.corp:8080" in msg and "authentication" in msg

    def test_tls_interception(self) -> None:
        msg = describe_sync_error(httpx.ConnectError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed", request=REQ,
        ))
        assert "SSL_CERT_FILE" in msg

    def test_database_error(self) -> None:
        msg = describe_sync_error(sqlite3.DatabaseError("disk I/O error"), retry="x")
        assert msg == "Card database error (disk I/O error) — x"

    def test_existing_statuses_unchanged(self) -> None:
        resp = httpx.Response(503, request=REQ)
        msg = describe_sync_error(httpx.HTTPStatusError("503", request=REQ, response=resp))
        assert msg == "Scryfall is unavailable (HTTP 503) — run `vimtg sync` to retry later"
