"""Tests for the category domain model."""

from __future__ import annotations

from vimtg.domain.categories import (
    PRESET_CATEGORIES,
    UNCATEGORIZED_LABEL,
    complete_category,
    completion_candidates,
    format_category_header,
    format_category_summary,
    format_inline_category,
    parse_category_header,
    parse_inline_category,
    strip_inline_category,
)
from vimtg.domain.deck_lines import parse_card_parts


class TestParseInlineCategory:
    def test_basic(self) -> None:
        assert parse_inline_category("4 Cultivate  @ramp") == "ramp"

    def test_lowercases(self) -> None:
        assert parse_inline_category("4 Cultivate  @Ramp") == "ramp"

    def test_requires_two_space_delimiter(self) -> None:
        assert parse_inline_category("4 Cultivate @ramp") == ""

    def test_no_category(self) -> None:
        assert parse_inline_category("4 Cultivate") == ""

    def test_with_tags_after(self) -> None:
        assert parse_inline_category("4 Cultivate  @ramp  #core") == "ramp"

    def test_hyphenated(self) -> None:
        assert (
            parse_inline_category("2 Wrath of God  @board-wipe") == "board-wipe"
        )

    def test_first_token_wins(self) -> None:
        assert parse_inline_category("1 X  @first  @second") == "first"


class TestStripInlineCategory:
    def test_strips_token(self) -> None:
        assert strip_inline_category("4 Cultivate  @ramp") == "4 Cultivate"

    def test_preserves_tags(self) -> None:
        assert (
            strip_inline_category("4 Cultivate  @ramp  #core")
            == "4 Cultivate  #core"
        )

    def test_no_category_unchanged(self) -> None:
        assert strip_inline_category("4 Cultivate") == "4 Cultivate"


class TestFormatInlineCategory:
    def test_format(self) -> None:
        assert format_inline_category("ramp") == "  @ramp"

    def test_empty(self) -> None:
        assert format_inline_category("") == ""


class TestCategoryHeaders:
    def test_format(self) -> None:
        assert format_category_header("ramp") == "// @ramp"

    def test_parse_roundtrip(self) -> None:
        assert parse_category_header(format_category_header("draw")) == "draw"

    def test_parse_with_whitespace(self) -> None:
        assert parse_category_header("//  @wincon ") == "wincon"

    def test_prose_comment_is_not_header(self) -> None:
        assert parse_category_header("// tweak the mana base") is None

    def test_metadata_is_not_header(self) -> None:
        assert parse_category_header("// Deck: Burn") is None

    def test_type_header_is_not_category(self) -> None:
        assert parse_category_header("// Creatures") is None


class TestParseCardParts:
    def test_canonical_order(self) -> None:
        name, category, tags, comment = parse_card_parts(
            "Cultivate  @ramp  #core  // best ramp"
        )
        assert name == "Cultivate"
        assert category == "ramp"
        assert tags == frozenset({"core"})
        assert comment == "best ramp"

    def test_at_word_in_comment_is_prose(self) -> None:
        name, category, _, comment = parse_card_parts(
            "Cultivate  // fetch  @basics"
        )
        assert name == "Cultivate"
        assert category == ""
        assert "@basics" in comment

    def test_non_canonical_order_parses(self) -> None:
        name, category, tags, _ = parse_card_parts("Cultivate  #core  @ramp")
        assert name == "Cultivate"
        assert category == "ramp"
        assert tags == frozenset({"core"})

    def test_double_faced_name_untouched(self) -> None:
        name, category, _, _ = parse_card_parts("Fire // Ice  @removal")
        assert name == "Fire // Ice"
        assert category == "removal"


class TestFormatCategorySummary:
    def test_empty(self) -> None:
        assert format_category_summary({}) == "No categories in deck"

    def test_sorted_with_counts(self) -> None:
        summary = format_category_summary({"wincon": 1, "ramp": 3})
        assert summary == "Categories: @ramp(3) @wincon(1)"


class TestCompletion:
    def test_deck_categories_rank_first(self) -> None:
        pool = completion_candidates({"zzz-custom": 5}, ("history-one",))
        assert pool[0] == "zzz-custom"
        assert pool[1] == "history-one"

    def test_deck_ordering_by_count_then_name(self) -> None:
        pool = completion_candidates({"draw": 2, "ramp": 2, "wincon": 9})
        assert pool[:3] == ("wincon", "draw", "ramp")

    def test_presets_included_and_deduplicated(self) -> None:
        pool = completion_candidates({"ramp": 1})
        assert pool.count("ramp") == 1
        for preset in PRESET_CATEGORIES:
            assert preset in pool

    def test_invalid_names_dropped(self) -> None:
        pool = completion_candidates({}, ("has space", "9starts-digit"))
        assert "has space" not in pool
        assert "9starts-digit" not in pool

    def test_complete_prefix_match(self) -> None:
        pool = completion_candidates({})
        assert complete_category("ra", pool) == "ramp"

    def test_complete_strips_at_prefix(self) -> None:
        pool = completion_candidates({})
        assert complete_category("@ra", pool) == "ramp"

    def test_complete_empty_prefix(self) -> None:
        assert complete_category("", ("ramp",)) == ""

    def test_complete_no_match(self) -> None:
        assert complete_category("xyz", ("ramp",)) == ""


def test_uncategorized_label_is_stable() -> None:
    assert UNCATEGORIZED_LABEL == "Uncategorized"
