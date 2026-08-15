"""Tests for domain error hierarchy."""

from __future__ import annotations

from vimtg.domain.errors import (
    CardsNotFoundWarning,
    DatabaseNotInitializedError,
    VimTGError,
)


def test_error_code_and_message() -> None:
    err = VimTGError("E999", "something broke")
    assert err.code == "E999"
    assert err.message == "something broke"
    assert str(err) == "E999: something broke"


def test_database_not_initialized() -> None:
    err = DatabaseNotInitializedError()
    assert err.code == "E100"
    assert "sync" in err.message


def test_vimtg_error_is_exception() -> None:
    err = DatabaseNotInitializedError()
    assert isinstance(err, Exception)
    assert isinstance(err, VimTGError)


def test_cards_not_found_warning() -> None:
    warn = CardsNotFoundWarning(3)
    assert warn.code == "W100"
    assert warn.message == "3 cards not found in database"
    assert str(warn) == "W100: 3 cards not found in database"
