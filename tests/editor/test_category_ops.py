"""Tests for Buffer category accessors and range-based category ops."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer, LineType, classify_line
from vimtg.editor.category_ops import (
    clear_category_in_range,
    set_category_in_range,
)


class TestClassifyCategoryHeader:
    def test_category_header_is_section(self) -> None:
        assert classify_line("// @ramp") == LineType.SECTION_HEADER

    def test_prose_comment_stays_comment(self) -> None:
        assert classify_line("// tweak mana base") == LineType.COMMENT

    def test_metadata_stays_metadata(self) -> None:
        assert classify_line("// Deck: Burn") == LineType.METADATA


class TestCategoryAt:
    def test_reads_category(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n")
        assert buf.category_at(0) == "ramp"

    def test_no_category(self) -> None:
        buf = Buffer.from_text("4 Cultivate\n")
        assert buf.category_at(0) == ""

    def test_non_card_line(self) -> None:
        buf = Buffer.from_text("// @ramp\n4 Cultivate\n")
        assert buf.category_at(0) == ""

    def test_at_in_comment_ignored(self) -> None:
        buf = Buffer.from_text("4 Cultivate  // fetch  @basics\n")
        assert buf.category_at(0) == ""

    def test_sideboard_line(self) -> None:
        buf = Buffer.from_text("SB: 2 Rest in Peace  @graveyard-hate\n")
        assert buf.category_at(0) == "graveyard-hate"


class TestSetCategory:
    def test_sets_on_bare_card(self) -> None:
        buf = Buffer.from_text("4 Cultivate\n").set_category(0, "ramp")
        assert buf.get_line(0).text == "4 Cultivate  @ramp"

    def test_canonical_order_with_tags_and_comment(self) -> None:
        buf = Buffer.from_text("4 Cultivate  #core  // good\n")
        buf = buf.set_category(0, "ramp")
        assert buf.get_line(0).text == "4 Cultivate  @ramp  #core  // good"

    def test_replaces_existing(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n").set_category(0, "lands")
        assert buf.get_line(0).text == "4 Cultivate  @lands"

    def test_clear_with_empty(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp  #core\n")
        buf = buf.set_category(0, "")
        assert buf.get_line(0).text == "4 Cultivate  #core"

    def test_lowercases(self) -> None:
        buf = Buffer.from_text("4 Cultivate\n").set_category(0, "Ramp")
        assert buf.category_at(0) == "ramp"

    def test_non_card_line_unchanged(self) -> None:
        buf = Buffer.from_text("// Creatures\n")
        assert buf.set_category(0, "ramp") is buf

    def test_normalizes_non_canonical_suffix(self) -> None:
        buf = Buffer.from_text("4 Cultivate  #core  @old\n")
        buf = buf.set_category(0, "new")
        assert buf.get_line(0).text == "4 Cultivate  @new  #core"

    def test_tags_survive_category_roundtrip(self) -> None:
        buf = Buffer.from_text("4 Cultivate  #core #flex\n")
        buf = buf.set_category(0, "ramp").set_category(0, "")
        assert buf.tags_at(0) == frozenset({"core", "flex"})


class TestSetTagsPreservesCategory:
    def test_add_tag_keeps_category(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n").add_tag(0, "core")
        assert buf.get_line(0).text == "4 Cultivate  @ramp  #core"
        assert buf.category_at(0) == "ramp"

    def test_card_name_ignores_category(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp  #core\n")
        assert buf.card_name_at(0) == "Cultivate"


class TestAggregates:
    def test_all_categories(self) -> None:
        buf = Buffer.from_text(
            "4 Cultivate  @ramp\n4 Opt  @draw\n4 Shock\n"
        )
        assert buf.all_categories() == frozenset({"ramp", "draw"})

    def test_category_counts(self) -> None:
        buf = Buffer.from_text(
            "4 Cultivate  @ramp\n2 Rampant Growth  @ramp\n4 Opt  @draw\n"
        )
        assert buf.category_counts() == {"ramp": 2, "draw": 1}


class TestRangeOps:
    def test_set_in_range(self) -> None:
        buf = Buffer.from_text("4 Cultivate\n// note\n4 Opt\n")
        buf, count = set_category_in_range(buf, 0, 2, "ramp")
        assert count == 2
        assert buf.category_at(0) == "ramp"
        assert buf.category_at(2) == "ramp"

    def test_clear_in_range_counts_only_categorized(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n4 Opt\n")
        buf, count = clear_category_in_range(buf, 0, 1)
        assert count == 1
        assert buf.category_at(0) == ""
