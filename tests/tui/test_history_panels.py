"""Tests for BranchesPanel, SnapshotsPanel, and HelpPanel render output."""

from __future__ import annotations

from datetime import datetime

from vimtg.domain.vcs import VCSBranch, VCSSnapshot
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.branches_panel import BranchesPanel
from vimtg.tui.widgets.help_panel import HelpPanel
from vimtg.tui.widgets.snapshots_panel import SnapshotsPanel


def _styles_at(label: str, text) -> str:
    start = text.plain.index(label)
    styles: list[str] = []
    for span in text.spans:
        if span.start <= start < span.end:
            styles.append(str(span.style))
    return " ".join(styles)


def _branch(name: str, deck_path: str = "/d.deck") -> VCSBranch:
    return VCSBranch(
        name=name,
        deck_path=deck_path,
        tip_id="abc1234",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )


def _snapshot(
    sid: str = "abc1234def5678", description: str = "init", tag: str | None = None,
) -> VCSSnapshot:
    return VCSSnapshot(
        id=sid,
        deck_path="/d.deck",
        parent_id=None,
        deck_state="",
        timestamp=datetime(2026, 1, 2, 15, 30, 0),
        description=description,
        branch="main",
        tag=tag,
    )


# ── BranchesPanel ──────────────────────────────────────────────────


class TestBranchesPanel:
    def test_empty_state_shows_message(self) -> None:
        p = BranchesPanel()
        assert "(no branches)" in p.render().plain

    def test_branch_count_in_header(self) -> None:
        p = BranchesPanel()
        p.branches = [_branch("main"), _branch("dev")]
        plain = p.render().plain
        assert "(2)" in plain
        assert "main" in plain
        assert "dev" in plain

    def test_current_branch_marked_with_asterisk(self) -> None:
        p = BranchesPanel()
        p.branches = [_branch("main"), _branch("dev")]
        p.current_branch = "main"
        plain = p.render().plain
        # The current-branch line should have " * " prefix; the other should not
        lines = [ln for ln in plain.split("\n") if "main" in ln or "dev" in ln]
        main_line = next(ln for ln in lines if "main" in ln)
        dev_line = next(ln for ln in lines if "dev" in ln)
        assert "*" in main_line
        assert "*" not in dev_line

    def test_current_branch_styled_green(self) -> None:
        p = BranchesPanel()
        p.branches = [_branch("main")]
        p.current_branch = "main"
        p.focused_panel = False  # selected styling only applies when focused
        text = p.render()
        assert COLORS["mana_green"] in _styles_at("main", text)

    def test_selected_only_styled_when_focused(self) -> None:
        p = BranchesPanel()
        p.branches = [_branch("main"), _branch("dev")]
        p.current_branch = "main"
        p.selected = 1
        p.focused_panel = False
        text = p.render()
        # When unfocused, the selected branch should NOT get the cursor_bg
        assert COLORS["cursor_bg"] not in _styles_at("dev", text)

    def test_selected_highlighted_when_focused(self) -> None:
        p = BranchesPanel()
        p.branches = [_branch("main"), _branch("dev")]
        p.current_branch = "main"
        p.selected = 1
        p.focused_panel = True
        text = p.render()
        assert COLORS["cursor_bg"] in _styles_at("dev", text)


# ── SnapshotsPanel ─────────────────────────────────────────────────


class TestSnapshotsPanel:
    def test_empty_state_shows_commit_hint(self) -> None:
        p = SnapshotsPanel()
        plain = p.render().plain
        assert "(no snapshots)" in plain
        assert "Press c to commit" in plain

    def test_snapshot_count_in_header(self) -> None:
        p = SnapshotsPanel()
        p.snapshots = [_snapshot("a" * 40, "first"), _snapshot("b" * 40, "second")]
        plain = p.render().plain
        assert "(2)" in plain

    def test_hash_truncated_to_seven_chars(self) -> None:
        p = SnapshotsPanel()
        sid = "abcdef1234567890" + ("x" * 20)
        p.snapshots = [_snapshot(sid, "first")]
        plain = p.render().plain
        # The first 7 chars should appear
        assert sid[:7] in plain
        # But not the full id
        assert sid not in plain

    def test_tag_displayed_in_parentheses(self) -> None:
        p = SnapshotsPanel()
        p.snapshots = [_snapshot("a" * 40, "release", tag="v1.0")]
        plain = p.render().plain
        assert "(v1.0)" in plain

    def test_no_tag_no_parentheses(self) -> None:
        p = SnapshotsPanel()
        p.snapshots = [_snapshot("a" * 40, "wip", tag=None)]
        plain = p.render().plain
        # No spurious tag-style segment
        assert "(v" not in plain

    def test_description_appears(self) -> None:
        p = SnapshotsPanel()
        p.snapshots = [_snapshot("a" * 40, "Add burn package")]
        plain = p.render().plain
        assert "Add burn package" in plain

    def test_description_truncated_at_35_chars(self) -> None:
        p = SnapshotsPanel()
        long_desc = "A" * 50
        p.snapshots = [_snapshot("a" * 40, long_desc)]
        plain = p.render().plain
        # 35 As should appear but not 36
        assert "A" * 35 in plain
        assert "A" * 36 not in plain

    def test_selected_only_highlighted_when_focused(self) -> None:
        p = SnapshotsPanel()
        p.snapshots = [_snapshot("a" * 40, "first"), _snapshot("b" * 40, "second")]
        p.selected = 1
        p.focused_panel = False
        # Render should not contain the cursor_bg on second hash when unfocused
        text = p.render()
        assert ">" not in text.plain.split("second")[0]  # no selection indicator

    def test_selected_indicator_visible_when_focused(self) -> None:
        p = SnapshotsPanel()
        p.snapshots = [_snapshot("a" * 40, "first")]
        p.selected = 0
        p.focused_panel = True
        plain = p.render().plain
        assert "> " in plain  # selection indicator prefix

    def test_scroll_offset_window(self) -> None:
        """Snapshots before scroll_offset should be hidden."""
        p = SnapshotsPanel()
        p.snapshots = [_snapshot("a" * 40, f"snap{i}") for i in range(25)]
        p.scroll_offset = 5
        plain = p.render().plain
        # snap0..snap4 hidden, snap5 visible
        assert "snap0\n" not in plain
        assert "snap5" in plain


# ── HelpPanel ──────────────────────────────────────────────────────


class TestHelpPanel:
    def test_header_present(self) -> None:
        p = HelpPanel()
        plain = p.render().plain
        assert "Help" in plain
        assert "Press ? or Escape to close" in plain

    def test_help_content_not_empty(self) -> None:
        p = HelpPanel()
        plain = p.render().plain
        # The overview should produce many lines of help text
        assert len(plain.split("\n")) > 5
