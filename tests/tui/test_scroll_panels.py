"""Scrolling history panels, currency-aware stats, and the working-copy panel."""

from __future__ import annotations

from datetime import datetime

from rich.text import Text

from vimtg.domain.deck_diff import StatsDelta
from vimtg.domain.vcs import VCSBranch, VCSSnapshot
from vimtg.services.deck_diff_service import DeckDiffService
from vimtg.tui.widgets.branches_panel import BranchesPanel
from vimtg.tui.widgets.diff_panel import DiffPanel
from vimtg.tui.widgets.scroll_panel import ScrollablePanel
from vimtg.tui.widgets.snapshots_panel import SnapshotsPanel
from vimtg.tui.widgets.stats_panel import StatsPanel, _price_delta_str
from vimtg.tui.widgets.working_copy_panel import WorkingCopyPanel


class _Lines(ScrollablePanel):
    title = "Lines"

    def __init__(self, n: int) -> None:
        super().__init__()
        self._n = n

    def body_lines(self) -> list[Text]:
        return [Text(f"line {i}") for i in range(self._n)]


class TestScrollablePanel:
    def test_windows_by_default_viewport(self) -> None:
        p = _Lines(30)
        p.default_viewport = 7  # 2 header rows + 5 body rows
        plain = p.render().plain
        assert "line 0" in plain
        assert "line 20" not in plain
        assert "more below" in plain
        # markers match the analytics / EDHREC panes
        assert "   ... 26 more below" in plain

    def test_scroll_by_clamps(self) -> None:
        p = _Lines(30)
        p.default_viewport = 7
        p.scroll_by(-5)
        assert p.scroll_pos == 0
        p.scroll_by(1000)
        assert p.scroll_pos == p.max_scroll
        assert p.max_scroll > 0

    def test_scrolled_render_shows_more_above(self) -> None:
        p = _Lines(30)
        p.default_viewport = 7
        p.scroll_by(3)
        plain = p.render().plain
        assert "more above" in plain
        assert "line 0" not in plain

    def test_top_bottom_and_half_page(self) -> None:
        p = _Lines(30)
        p.default_viewport = 12
        p.scroll_to_bottom()
        assert p.scroll_pos == p.max_scroll
        p.scroll_to_top()
        assert p.scroll_pos == 0
        p.scroll_half_page(1)
        assert p.scroll_pos == 5
        p.scroll_half_page(-1)
        assert p.scroll_pos == 0

    def test_every_line_is_reachable(self) -> None:
        p = _Lines(12)
        p.default_viewport = 12  # 10 body rows for 12 lines
        seen: set[str] = set()
        for pos in range(p.max_scroll + 1):
            p.scroll_pos = pos
            seen |= {ln.plain for ln in p.window() if ln.plain.startswith("line")}
            assert len(p.window()) <= p.viewport_rows()
        assert seen == {f"line {i}" for i in range(12)}

    def test_tiny_viewport_still_shows_content(self) -> None:
        p = _Lines(5)
        p.default_viewport = 4  # 2 body rows
        p.scroll_to_bottom()
        plain = [ln.plain for ln in p.window()]
        assert "line 4" in plain

    def test_short_content_has_no_markers(self) -> None:
        p = _Lines(3)
        p.default_viewport = 10
        plain = p.render().plain
        assert "more" not in plain
        assert p.max_scroll == 0


def _big_diff(n: int):
    before = "".join(f"1 Card {i}\n" for i in range(n))
    after = before + "".join(f"1 New {i}\n" for i in range(n))
    return DeckDiffService().diff_snapshot_parent(after, before)


class TestDiffPanelScrolls:
    def test_diff_panel_is_scrollable(self) -> None:
        dp = DiffPanel()
        dp.default_viewport = 8
        dp.diff = _big_diff(20)
        assert dp.max_scroll > 0
        dp.scroll_by(4)
        assert "more above" in dp.render().plain

    def test_new_diff_resets_scroll(self) -> None:
        dp = DiffPanel()
        dp.default_viewport = 8
        dp.diff = _big_diff(20)
        dp.scroll_by(4)
        dp.diff = _big_diff(21)
        assert dp.scroll_pos == 0

    def test_equal_diff_keeps_scroll(self) -> None:
        dp = DiffPanel()
        dp.default_viewport = 8
        dp.diff = _big_diff(20)
        dp.scroll_by(4)
        dp.diff = _big_diff(20)
        assert dp.scroll_pos == 4

    def test_wheel_scrolls(self) -> None:
        dp = DiffPanel()
        dp.default_viewport = 8
        dp.diff = _big_diff(20)
        dp.wheel(3)
        assert dp.scroll_pos == 3
        dp.wheel(-10)
        assert dp.scroll_pos == 0


def _delta(**overrides: object) -> StatsDelta:
    base: dict[str, object] = dict(
        old_total=60, new_total=60, old_avg_cmc=2.0, new_avg_cmc=2.0,
        old_price=10.0, new_price=12.5, curve_delta={},
    )
    base.update(overrides)
    return StatsDelta(**base)  # type: ignore[arg-type]


class TestStatsCurrency:
    def test_price_delta_uses_symbol(self) -> None:
        plain = _price_delta_str(10.0, 12.5, "€").plain
        assert "€10.00" in plain and "€12.50" in plain and "+€2.50" in plain
        assert "$" not in plain

    def test_default_symbol_is_dollar(self) -> None:
        assert "$10.00" in _price_delta_str(10.0, 10.0).plain

    def test_panel_renders_configured_currency(self) -> None:
        sp = StatsPanel()
        sp.currency = "tix "
        sp.stats_delta = _delta()
        assert "tix 12.50" in sp.render().plain


def _snap(i: int, branch: str = "main") -> VCSSnapshot:
    return VCSSnapshot(
        id=f"{i:07d}abcdef",
        deck_path="/d.deck",
        parent_id=None,
        deck_state="",
        timestamp=datetime(2026, 1, 2, 15, 30, 0),
        description=f"snap {i}",
        branch=branch,
        tag=None,
        deck_hash="",
        merge_parent_id=None,
    )


class TestSnapshotsPanelHeight:
    def test_visible_rows_follow_viewport(self) -> None:
        sp = SnapshotsPanel()
        sp.snapshots = [_snap(i) for i in range(40)]
        sp.default_viewport = 10  # 2 header rows + 4 snapshots of 2 rows
        assert sp.max_visible == 4
        plain = sp.render().plain
        assert "snap 3" in plain and "snap 4" not in plain

    def test_selection_scrolls_into_view(self) -> None:
        sp = SnapshotsPanel()
        sp.snapshots = [_snap(i) for i in range(40)]
        sp.default_viewport = 10
        for _ in range(10):
            sp.select_next()
        assert sp.selected == 10
        assert "snap 10" in sp.render().plain

    def test_clamp_after_list_shrinks(self) -> None:
        sp = SnapshotsPanel()
        sp.default_viewport = 10
        sp.snapshots = [_snap(i) for i in range(40)]
        for _ in range(30):
            sp.select_next()
        assert sp.scroll_pos > 0
        sp.snapshots = [_snap(i) for i in range(3)]
        sp.clamp_selection()
        assert sp.selected == 2
        assert sp.scroll_pos == 0
        assert "snap 0" in sp.render().plain

    def test_only_merged_in_snapshots_are_labelled(self) -> None:
        # A branch created from main inherits main's commits; they are not
        # foreign. Only ids off the first-parent chain get a label.
        sp = SnapshotsPanel()
        inherited, merged_in = _snap(0, branch="main"), _snap(1, branch="budget")
        sp.snapshots = [inherited, merged_in]
        sp.mainline_ids = frozenset({inherited.id})
        plain = sp.render().plain
        assert "[budget]" in plain
        assert "[main]" not in plain

    def test_no_labels_without_mainline(self) -> None:
        sp = SnapshotsPanel()
        sp.snapshots = [_snap(0, branch="main"), _snap(1, branch="budget")]
        assert "[" not in sp.render().plain.split("\n", 2)[2]

    def test_wheel_drags_selection_only_when_needed(self) -> None:
        sp = SnapshotsPanel()
        sp.snapshots = [_snap(i) for i in range(40)]
        sp.default_viewport = 10  # 4 visible
        sp.wheel(1)
        assert sp.scroll_pos == 1 and sp.selected == 1
        sp.select_by(2)  # selected 3, still visible in window 1..4
        sp.wheel(-1)
        assert sp.scroll_pos == 0 and sp.selected == 3


def _branch(name: str) -> VCSBranch:
    return VCSBranch(
        name=name, deck_path="/d.deck", tip_id="abc",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )


class TestBranchesPanelWindow:
    def test_selection_scrolls_into_view(self) -> None:
        bp = BranchesPanel()
        bp.branches = [_branch(f"b{i:02d}") for i in range(12)]
        bp.default_viewport = 6  # 4 visible
        assert "b04" not in bp.render().plain
        bp.select_last()
        assert bp.selected == 11
        assert "b11" in bp.render().plain
        bp.select_first()
        assert bp.scroll_pos == 0
        bp.select_by(0)
        assert "b00" in bp.render().plain

    def test_clamp_after_delete(self) -> None:
        bp = BranchesPanel()
        bp.branches = [_branch(f"b{i}") for i in range(9)]
        bp.default_viewport = 5
        bp.select_last()
        bp.branches = [_branch("b0")]
        bp.clamp_selection()
        assert bp.selected == 0 and bp.scroll_pos == 0


class TestWorkingCopyPanel:
    def test_clean_state(self) -> None:
        wp = WorkingCopyPanel()
        wp.diff = None
        plain = wp.render().plain
        assert "Working copy" in plain
        assert "clean" in plain

    def test_dirty_counts(self) -> None:
        wp = WorkingCopyPanel()
        wp.dirty = True
        wp.diff = DeckDiffService().diff_snapshot_parent(
            "4 Bolt\n2 Shock\n", "4 Bolt\n4 Guide\n",
        )
        plain = wp.render().plain
        assert "+1" in plain and "-1" in plain
        assert "clean" not in plain
        assert "c" in plain  # commit hint

    def test_dirty_without_card_changes_names_metadata(self) -> None:
        wp = WorkingCopyPanel()
        wp.dirty = True
        wp.diff = DeckDiffService().diff_snapshot_parent("4 Bolt\n", "4 Bolt\n")
        plain = wp.render().plain
        assert "metadata or plans" in plain
        assert "clean" not in plain

    def test_card_diff_alone_does_not_mean_dirty(self) -> None:
        # The VCS verdict wins: no verdict means clean, whatever the card diff says
        wp = WorkingCopyPanel()
        wp.dirty = False
        wp.diff = DeckDiffService().diff_snapshot_parent("4 Bolt\n", "")
        assert "clean" in wp.render().plain

    def test_no_snapshot_yet(self) -> None:
        wp = WorkingCopyPanel()
        wp.diff = None
        wp.has_tip = False
        assert "no snapshots" in wp.render().plain
