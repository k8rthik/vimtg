"""Tests for domain error hierarchy."""

from __future__ import annotations

from vimtg.domain.errors import (
    CardNotFoundError,
    DatabaseNotInitializedError,
    DeckParseError,
    UnsavedChangesError,
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


def test_card_not_found_without_suggestion() -> None:
    err = CardNotFoundError("Lightnig Bolt")
    assert err.code == "E101"
    assert "Lightnig Bolt" in err.message
    assert "did you mean" not in err.message


def test_card_not_found_with_suggestion() -> None:
    err = CardNotFoundError("Lightnig Bolt", suggestion="Lightning Bolt")
    assert "did you mean 'Lightning Bolt'" in err.message


def test_deck_parse_error() -> None:
    err = DeckParseError(line=7, detail="expected quantity")
    assert err.code == "E102"
    assert "line 7" in err.message
    assert "expected quantity" in err.message


def test_unsaved_changes_error() -> None:
    err = UnsavedChangesError()
    assert err.code == "E37"
    assert "!" in err.message


def test_vimtg_error_is_exception() -> None:
    err = DatabaseNotInitializedError()
    assert isinstance(err, Exception)
    assert isinstance(err, VimTGError)
