"""Tests for the snapshot undo tree domain model."""

from datetime import UTC, datetime

from vimtg.domain.snapshot import Snapshot, SnapshotTree

SAMPLE_STATE = "4 Lightning Bolt\n2 Mountain\n"


def test_new_tree_single_root_node() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    assert len(tree.nodes) == 1
    assert tree.current.deck_state == SAMPLE_STATE
    assert tree.current.parent_id is None
    assert tree.current.branch == "main"
    assert tree.current.description == "initial"
    assert tree.branches == {"main": tree.current_id}


def test_add_snapshot_grows_tree() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    tree2 = tree.add_snapshot("4 Lightning Bolt\n3 Mountain\n", "add mountain")
    assert len(tree2.nodes) == 2
    assert tree2.current.description == "add mountain"
    assert tree2.current.parent_id == tree.current_id


def test_undo_moves_to_parent() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    tree2 = tree.add_snapshot("changed\n", "edit")
    tree3 = tree2.undo()
    assert tree3 is not None
    assert tree3.current_id == tree.current_id
    assert tree3.current.deck_state == SAMPLE_STATE


def test_redo_moves_to_most_recent_child() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    tree2 = tree.add_snapshot("changed\n", "edit")
    tree3 = tree2.undo()
    assert tree3 is not None
    tree4 = tree3.redo()
    assert tree4 is not None
    assert tree4.current_id == tree2.current_id


def test_undo_at_root_returns_none() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    assert tree.undo() is None


def test_redo_at_leaf_returns_none() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    assert tree.redo() is None

    tree2 = tree.add_snapshot("changed\n", "edit")
    assert tree2.redo() is None


def test_branch_after_undo_creates_fork() -> None:
    tree = SnapshotTree.new("v0\n")
    tree = tree.add_snapshot("v1\n", "first")
    tree = tree.add_snapshot("v2\n", "second")

    # Undo back to v1
    tree_at_v1 = tree.undo()
    assert tree_at_v1 is not None

    # Add a diverging snapshot
    forked = tree_at_v1.add_snapshot("v2-alt\n", "alt second")

    # v1 now has two children
    children = SnapshotTree(
        nodes=forked.nodes, current_id=tree_at_v1.current_id, branches=forked.branches
    ).children()
    assert len(children) == 2


def test_redo_picks_newest_among_multiple_children() -> None:
    tree = SnapshotTree.new("v0\n")

    # Manually create two children with controlled timestamps
    root_id = tree.current_id
    older_child = Snapshot(
        id="older",
        parent_id=root_id,
        deck_state="older\n",
        timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        description="older",
        branch="main",
    )
    newer_child = Snapshot(
        id="newer",
        parent_id=root_id,
        deck_state="newer\n",
        timestamp=datetime(2025, 6, 1, tzinfo=UTC),
        description="newer",
        branch="main",
    )
    nodes = {**tree.nodes, older_child.id: older_child, newer_child.id: newer_child}
    tree_with_fork = SnapshotTree(
        nodes=nodes, current_id=root_id, branches=tree.branches
    )

    # Redo should pick the most recent (newer)
    result = tree_with_fork.redo()
    assert result is not None
    assert result.current_id == "newer"


def test_checkpoint_stores_tag() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    tree2 = tree.add_snapshot("v1\n", "edit")
    tree3 = tree2.checkpoint("release-1")
    assert tree3.current.tag == "release-1"
    # Other fields unchanged
    assert tree3.current.deck_state == tree2.current.deck_state
    assert tree3.current.description == tree2.current.description


def test_create_branch_adds_pointer() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    tree2 = tree.create_branch("experiment")
    assert "experiment" in tree2.branches
    assert tree2.branches["experiment"] == tree.current_id
    # Current position unchanged
    assert tree2.current_id == tree.current_id


def test_switch_branch_moves_to_tip() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    tree = tree.add_snapshot("v1\n", "first")
    tip_id = tree.current_id

    # Create branch, then add more on main
    tree = tree.create_branch("side")
    tree = tree.add_snapshot("v2\n", "second on main")

    # Switch back to side branch
    switched = tree.switch_branch("side")
    assert switched is not None
    assert switched.current_id == tip_id


def test_switch_unknown_branch_returns_none() -> None:
    tree = SnapshotTree.new(SAMPLE_STATE)
    assert tree.switch_branch("nonexistent") is None


def test_original_tree_not_mutated_by_add() -> None:
    """Verify immutability: original tree unchanged after add_snapshot."""
    tree = SnapshotTree.new(SAMPLE_STATE)
    original_nodes_count = len(tree.nodes)
    original_id = tree.current_id

    _tree2 = tree.add_snapshot("v1\n", "edit")

    assert len(tree.nodes) == original_nodes_count
    assert tree.current_id == original_id


def test_snapshot_frozen() -> None:
    """Snapshot dataclass is truly frozen."""
    snap = Snapshot(
        id="x",
        parent_id=None,
        deck_state="test\n",
        timestamp=datetime.now(UTC),
        description="test",
    )
    try:
        snap.description = "mutated"  # type: ignore[misc]
        raise AssertionError("Expected FrozenInstanceError")
    except AttributeError:
        pass
