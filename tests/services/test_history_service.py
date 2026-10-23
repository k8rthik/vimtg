"""Tests for the history service wrapping the snapshot undo tree."""

from unittest.mock import patch

import pytest

from vimtg.editor.buffer import Buffer
from vimtg.services.history_service import HistoryService


def _buf(text: str) -> Buffer:
    return Buffer.from_text(text)


def test_initialize() -> None:
    svc = HistoryService()
    svc.initialize(_buf("4 Lightning Bolt\n"))
    assert svc.tree is not None
    assert svc.tree.current.deck_state == "4 Lightning Bolt\n"
    assert not svc.can_undo
    assert not svc.can_redo


def test_record_and_undo() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "edit")
    assert svc.can_undo
    result = svc.undo()
    assert result is not None
    assert result.to_text() == "v0\n"


def test_undo_redo_cycle() -> None:
    """Make 3 changes, undo 2, redo 1."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "c1")
    svc.record(_buf("v2\n"), "c2")
    svc.record(_buf("v3\n"), "c3")

    # Undo twice (v3 -> v2 -> v1)
    buf = svc.undo()
    assert buf is not None
    assert buf.to_text() == "v2\n"
    buf = svc.undo()
    assert buf is not None
    assert buf.to_text() == "v1\n"

    # Redo once (v1 -> v2)
    buf = svc.redo()
    assert buf is not None
    assert buf.to_text() == "v2\n"


def test_undo_at_root_returns_none() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    assert svc.undo() is None


def test_redo_at_leaf_returns_none() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "edit")
    assert svc.redo() is None


def _undo_text(svc: HistoryService) -> str | None:
    restored = svc.undo()
    return restored.to_text() if restored is not None else None


def _record_at(svc: HistoryService, t: float, text: str, description: str) -> None:
    with patch("vimtg.services.history_service.time") as mock_time:
        mock_time.monotonic.return_value = t
        svc.record(_buf(text), description)


def test_debounce_coalesces_same_description() -> None:
    """A quantity burst (two increments within 2s) coalesces."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))

    # First record at t=100
    with patch("vimtg.services.history_service.time") as mock_time:
        mock_time.monotonic.return_value = 100.0
        svc.record(_buf("v1\n"), "increment")

    # Second record at t=101 (within 2s, same description)
    with patch("vimtg.services.history_service.time") as mock_time:
        mock_time.monotonic.return_value = 101.0
        svc.record(_buf("v1-updated\n"), "increment")

    # Should have only 2 nodes: initial + one coalesced record
    assert svc.tree is not None
    assert len(svc.tree.nodes) == 2
    assert svc.tree.current.deck_state == "v1-updated\n"


def test_no_debounce_different_description() -> None:
    """Different descriptions should not be coalesced."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))

    with patch("vimtg.services.history_service.time") as mock_time:
        mock_time.monotonic.return_value = 100.0
        svc.record(_buf("v1\n"), "edit-a")

    with patch("vimtg.services.history_service.time") as mock_time:
        mock_time.monotonic.return_value = 100.5
        svc.record(_buf("v2\n"), "edit-b")

    assert svc.tree is not None
    assert len(svc.tree.nodes) == 3  # initial + edit-a + edit-b




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


def test_record_auto_initializes_when_no_tree() -> None:
    """Calling record without initialize creates the tree."""
    svc = HistoryService()
    svc.record(_buf("v0\n"), "auto-init")
    assert svc.tree is not None
    assert svc.tree.current.deck_state == "v0\n"


def test_undo_redo_on_uninitialized_returns_none() -> None:
    svc = HistoryService()
    assert svc.undo() is None
    assert svc.redo() is None




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
    """dd u dd within 2s: the second dd must not overwrite the root."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    _record_at(svc, 100.0, "v1\n", "increment")
    assert _undo_text(svc) == "v0\n"
    _record_at(svc, 100.5, "v2\n", "increment")
    assert _undo_text(svc) == "v0\n"
    assert svc.tree is not None
    root = [n for n in svc.tree.nodes.values() if n.parent_id is None]
    assert root[0].deck_state == "v0\n"


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
    from vimtg.editor.buffer import Buffer
    from vimtg.services.history_service import HistoryService

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
