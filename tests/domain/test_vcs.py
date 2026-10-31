"""Tests for the VCS domain dataclasses."""

from datetime import UTC, datetime

from vimtg.domain.vcs import VCSSnapshot, VCSStatus


class TestVCSSnapshot:
    def test_creation(self) -> None:
        snap = VCSSnapshot(
            id="abc123",
            deck_path="/tmp/test.deck",
            parent_id=None,
            deck_state="4 Lightning Bolt\n",
            timestamp=datetime(2025, 3, 15, 14, 30, tzinfo=UTC),
            description="initial build",
            tag=None,
            deck_hash="sha256abc",
        )
        assert snap.id == "abc123"
        assert snap.deck_path == "/tmp/test.deck"
        assert snap.parent_id is None
        assert snap.deck_hash == "sha256abc"

    def test_frozen(self) -> None:
        snap = VCSSnapshot(
            id="x",
            deck_path="/tmp/test.deck",
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

    def test_defaults(self) -> None:
        snap = VCSSnapshot(
            id="x",
            deck_path="/tmp/test.deck",
            parent_id=None,
            deck_state="test\n",
            timestamp=datetime.now(UTC),
            description="test",
        )
        assert snap.tag is None
        assert snap.deck_hash == ""


class TestVCSStatus:
    def test_creation(self) -> None:
        status = VCSStatus(
            snapshot_count=12,
            has_uncommitted_changes=True,
            last_snapshot_description="added burn spells",
        )
        assert status.snapshot_count == 12
        assert status.has_uncommitted_changes is True

    def test_defaults(self) -> None:
        status = VCSStatus(
            snapshot_count=0,
            has_uncommitted_changes=False,
        )
        assert status.last_snapshot_description == ""
