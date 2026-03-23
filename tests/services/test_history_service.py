"""Tests for the history service wrapping the snapshot undo tree."""

from unittest.mock import patch

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


def test_debounce_coalesces_same_description() -> None:
    """Two records within 2s with same description should coalesce."""
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))

    # First record at t=100
    with patch("vimtg.services.history_service.time") as mock_time:
        mock_time.monotonic.return_value = 100.0
        svc.record(_buf("v1\n"), "typing")

    # Second record at t=101 (within 2s, same description)
    with patch("vimtg.services.history_service.time") as mock_time:
        mock_time.monotonic.return_value = 101.0
        svc.record(_buf("v1-updated\n"), "typing")

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


def test_checkpoint() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "edit")
    svc.checkpoint("milestone-1")
    assert svc.tree is not None
    assert svc.tree.current.tag == "milestone-1"


def test_branch_and_switch() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    svc.record(_buf("v1\n"), "edit")
    svc.create_branch("experiment")

    # Add more on main
    svc.record(_buf("v2\n"), "main-work")

    # Switch to experiment (should be at v1)
    buf = svc.switch_branch("experiment")
    assert buf is not None
    assert buf.to_text() == "v1\n"

    # List branches
    branches = svc.list_branches()
    assert "main" in branches
    assert "experiment" in branches


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


def test_switch_unknown_branch_returns_none() -> None:
    svc = HistoryService()
    svc.initialize(_buf("v0\n"))
    assert svc.switch_branch("nope") is None
