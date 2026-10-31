"""Tests for the history service: the session undo stack."""

from unittest.mock import patch

import pytest

from vimtg.editor.buffer import Buffer
from vimtg.services.history_service import HistoryService


def _buf(text: str) -> Buffer:
    return Buffer.from_text(text)


def _undo_text(svc: HistoryService) -> str | None:
    restored = svc.undo()
    return restored.to_text() if restored is not None else None


def _redo_text(svc: HistoryService) -> str | None:
    restored = svc.redo()
    return restored.to_text() if restored is not None else None


def _record_at(svc: HistoryService, t: float, text: str, description: str) -> None:
    with patch("vimtg.services.history_service.time") as mock_time:
        mock_time.monotonic.return_value = t
        svc.record(_buf(text), description)


def test_initialize_has_nothing_to_undo_or_redo() -> None:
    svc = HistoryService()
    svc.initialize(_buf("4 Lightning Bolt\n"))
    assert not svc.can_undo
    assert not svc.can_redo
    assert svc.undo() is None
    assert svc.redo() is None


def test_record_and_undo() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "edit")
    assert svc.can_undo
    assert _undo_text(svc) == "v0\n"


def test_undo_redo_cycle() -> None:
    """Make 3 changes, undo 2, redo 1."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "c1")
    svc.record(_buf("v2\n"), "c2")
    svc.record(_buf("v3\n"), "c3")
    assert _undo_text(svc) == "v2\n"
    assert _undo_text(svc) == "v1\n"
    assert _redo_text(svc) == "v2\n"
    assert _redo_text(svc) == "v3\n"
    assert svc.redo() is None


def test_redo_at_the_newest_entry_returns_none() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "edit")
    assert svc.redo() is None


def test_an_edit_after_undo_discards_the_redo_entries() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "c1")
    svc.record(_buf("v2\n"), "c2")
    assert _undo_text(svc) == "v1\n"
    svc.record(_buf("v2-alt\n"), "c2 alt")
    assert not svc.can_redo
    assert svc.redo() is None
    assert _undo_text(svc) == "v1\n"
    assert _redo_text(svc) == "v2-alt\n"  # v2 is gone for good
    assert svc.redo() is None


def test_undo_then_edit_then_redo_does_nothing() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "c1")
    svc.undo()
    svc.record(_buf("v1-alt\n"), "c1 alt")
    assert svc.redo() is None
    assert _undo_text(svc) == "v0\n"
    assert _redo_text(svc) == "v1-alt\n"


def test_debounce_coalesces_same_description() -> None:
    """A quantity burst (two increments within 2s) is one undo step."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    _record_at(svc, 100.0, "v1\n", "increment")
    _record_at(svc, 101.0, "v1-updated\n", "increment")
    assert _undo_text(svc) == "v0\n"
    assert _redo_text(svc) == "v1-updated\n"


def test_no_debounce_different_description() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    _record_at(svc, 100.0, "v1\n", "edit-a")
    _record_at(svc, 100.5, "v2\n", "edit-b")
    assert _undo_text(svc) == "v1\n"
    assert _undo_text(svc) == "v0\n"


def test_can_undo_redo_properties() -> None:
    svc = HistoryService()
    assert not svc.can_undo
    assert not svc.can_redo

    svc.initialize(_buf("v0\n"))
    assert not svc.can_undo
    assert not svc.can_redo

    svc.record(_buf("v1\n"), "edit")
    assert svc.can_undo
    assert not svc.can_redo

    svc.undo()
    assert not svc.can_undo
    assert svc.can_redo


def test_record_auto_initializes_when_empty() -> None:
    """Calling record without initialize starts the stack at that state."""
    svc = HistoryService()
    svc.record(_buf("v0\n"), "auto-init")
    assert not svc.can_undo
    svc.record(_buf("v1\n"), "edit")
    assert _undo_text(svc) == "v0\n"


def test_undo_redo_on_uninitialized_returns_none() -> None:
    svc = HistoryService()
    assert svc.undo() is None
    assert svc.redo() is None


def test_amend_that_restores_the_previous_text_drops_the_step() -> None:
    """Normalization that undoes the edit leaves nothing for u to undo."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "edit")
    svc.amend(_buf("v0\n"))
    assert not svc.can_undo
    assert svc.undo() is None


def test_amend_rewrites_the_current_step() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "edit")
    svc.amend(_buf("v1-cleaned\n"))
    assert _undo_text(svc) == "v0\n"
    assert _redo_text(svc) == "v1-cleaned\n"


@pytest.mark.parametrize(
    "description",
    ["dd operation", "delete card", "put", "dot repeat", ":s/a/b/", "edit line"],
)
def test_non_quantity_edits_never_coalesce(description: str) -> None:
    """Operators, x, put and dot-repeat are one change per u, however fast."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    _record_at(svc, 100.0, "v1\n", description)
    _record_at(svc, 100.1, "v2\n", description)
    assert _undo_text(svc) == "v1\n"
    assert _undo_text(svc) == "v0\n"


def test_no_coalesce_into_an_undone_state() -> None:
    """+ u + within 2s: the second + must not overwrite the start state."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    _record_at(svc, 100.0, "v1\n", "increment")
    assert _undo_text(svc) == "v0\n"
    _record_at(svc, 100.5, "v2\n", "increment")
    assert _undo_text(svc) == "v0\n"
    assert not svc.can_undo


def test_no_coalesce_after_redo() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    _record_at(svc, 100.0, "v1\n", "increment")
    svc.undo()
    svc.redo()
    _record_at(svc, 100.5, "v2\n", "increment")
    assert _undo_text(svc) == "v1\n"


def test_quantity_burst_outside_window_is_separate() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    _record_at(svc, 100.0, "v1\n", "increment")
    _record_at(svc, 103.0, "v2\n", "increment")
    assert _undo_text(svc) == "v1\n"


def test_current_id_follows_records_and_undo() -> None:
    history = HistoryService()
    assert history.current_id is None
    history.initialize(Buffer.from_text("a\n"))
    root = history.current_id
    history.record(Buffer.from_text("b\n"), "edit")
    assert history.current_id not in (None, root)
    history.undo()
    assert history.current_id == root


def test_quantity_burst_on_other_rows_is_separate() -> None:
    """+ j + : the second card's change is its own undo step."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    with patch("vimtg.services.history_service.time") as mock_time:
        mock_time.monotonic.return_value = 100.0
        svc.record(_buf("v1\n"), "increment", rows=(3, 3))
        mock_time.monotonic.return_value = 100.2
        svc.record(_buf("v1b\n"), "increment", rows=(3, 3))
        mock_time.monotonic.return_value = 100.4
        svc.record(_buf("v2\n"), "increment", rows=(4, 4))
    assert _undo_text(svc) == "v1b\n"
    assert _undo_text(svc) == "v0\n"
