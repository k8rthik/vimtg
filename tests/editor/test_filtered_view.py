"""Tests for FilteredView — tag-based buffer visibility."""

from vimtg.domain.tags import TagFilter
from vimtg.editor.buffer import Buffer
from vimtg.editor.filtered_view import FilteredView

TAGGED_DECK = """\
// Deck: Test

// Creature
4 Goblin Guide  #core
4 Monastery Swiftspear  #core
2 Eidolon  #flex

// Instant
4 Lightning Bolt  #core
4 Skullcrack  #flex"""


def _buf(text: str = TAGGED_DECK) -> Buffer:
    return Buffer.from_text(text)


class TestNoFilter:
    def test_all_visible(self):
        fv = FilteredView(_buf(), None)
        assert fv.visible_count() == _buf().line_count()

    def test_is_visible_always_true(self):
        fv = FilteredView(_buf(), None)
        for i in range(_buf().line_count()):
            assert fv.is_visible(i) is True

    def test_hidden_card_count_zero(self):
        fv = FilteredView(_buf(), None)
        assert fv.hidden_card_count() == 0

    def test_hidden_ranges_empty(self):
        fv = FilteredView(_buf(), None)
        assert fv.hidden_ranges() == []


class TestIncludeFilter:
    def test_core_filter(self):
        fv = FilteredView(_buf(), TagFilter(include=frozenset({"core"})))
        # Card lines: Goblin Guide(3), Swiftspear(4), Eidolon(5), Bolt(8), Skullcrack(9)
        # Core: Goblin Guide, Swiftspear, Bolt
        # Flex (hidden): Eidolon, Skullcrack
        assert fv.is_visible(3) is True   # Goblin Guide #core
        assert fv.is_visible(4) is True   # Swiftspear #core
        assert fv.is_visible(5) is False  # Eidolon #flex
        assert fv.is_visible(8) is True   # Bolt #core
        assert fv.is_visible(9) is False  # Skullcrack #flex

    def test_non_card_lines_always_visible(self):
        fv = FilteredView(_buf(), TagFilter(include=frozenset({"core"})))
        assert fv.is_visible(0) is True  # metadata
        assert fv.is_visible(2) is True  # section header
        assert fv.is_visible(7) is True  # section header

    def test_hidden_card_count(self):
        fv = FilteredView(_buf(), TagFilter(include=frozenset({"core"})))
        assert fv.hidden_card_count() == 2


class TestExcludeFilter:
    def test_exclude_flex(self):
        fv = FilteredView(_buf(), TagFilter(exclude=frozenset({"flex"})))
        assert fv.is_visible(3) is True   # Goblin Guide #core
        assert fv.is_visible(5) is False  # Eidolon #flex
        assert fv.is_visible(9) is False  # Skullcrack #flex


class TestNavigation:
    def test_next_visible(self):
        fv = FilteredView(_buf(), TagFilter(include=frozenset({"core"})))
        # After Swiftspear(4), Eidolon(5) is hidden, next visible should be section header or Bolt
        nxt = fv.next_visible(4)
        assert nxt is not None
        assert fv.is_visible(nxt) is True

    def test_prev_visible(self):
        fv = FilteredView(_buf(), TagFilter(include=frozenset({"core"})))
        prv = fv.prev_visible(8)  # Before Bolt
        assert prv is not None
        assert fv.is_visible(prv) is True

    def test_next_visible_at_end(self):
        fv = FilteredView(_buf(), TagFilter(include=frozenset({"core"})))
        assert fv.next_visible(9) is None

    def test_prev_visible_at_start(self):
        fv = FilteredView(_buf(), TagFilter(include=frozenset({"core"})))
        assert fv.prev_visible(0) is None


class TestHiddenRanges:
    def test_hidden_ranges(self):
        fv = FilteredView(_buf(), TagFilter(include=frozenset({"core"})))
        ranges = fv.hidden_ranges()
        assert len(ranges) >= 1
        # Each range: (start, end, count)
        for start, end, count in ranges:
            assert count > 0
            assert start <= end
