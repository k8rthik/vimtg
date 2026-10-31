"""Tests for the tag token grammar: parsing and formatting the #tag suffix."""

from vimtg.domain.tags import (
    format_inline_tags,
    parse_inline_tags,
    strip_inline_tags,
)


class TestParseInlineTags:
    def test_single_tag(self):
        assert parse_inline_tags("#core") == frozenset({"core"})

    def test_multiple_tags(self):
        assert parse_inline_tags("#burn-package #core") == frozenset(
            {"burn-package", "core"}
        )

    def test_tags_in_card_line(self):
        result = parse_inline_tags("4 Goblin Guide  #burn-package #core")
        assert result == frozenset({"burn-package", "core"})

    def test_no_tags(self):
        assert parse_inline_tags("4 Goblin Guide") == frozenset()

    def test_case_insensitive(self):
        assert parse_inline_tags("#Core #BURN") == frozenset({"core", "burn"})

    def test_invalid_tag_ignored(self):
        # Tags must start with a letter
        assert parse_inline_tags("#123bad") == frozenset()

    def test_empty_string(self):
        assert parse_inline_tags("") == frozenset()

    def test_sideboard_line(self):
        result = parse_inline_tags("SB: 2 Rest in Peace  #graveyard-hate")
        assert result == frozenset({"graveyard-hate"})


class TestStripInlineTags:
    def test_strips_tags(self):
        assert strip_inline_tags("4 Goblin Guide  #core #burn") == "4 Goblin Guide"

    def test_no_tags(self):
        assert strip_inline_tags("4 Goblin Guide") == "4 Goblin Guide"

    def test_single_tag(self):
        assert strip_inline_tags("4 Lightning Bolt  #core") == "4 Lightning Bolt"

    def test_preserves_single_space(self):
        # Single space before # is NOT a tag delimiter
        assert strip_inline_tags("4 Card Name #notag") == "4 Card Name #notag"

    def test_sideboard_with_tags(self):
        assert (
            strip_inline_tags("SB: 2 Rest in Peace  #hate")
            == "SB: 2 Rest in Peace"
        )


class TestFormatInlineTags:
    def test_empty(self):
        assert format_inline_tags(frozenset()) == ""

    def test_single(self):
        assert format_inline_tags(frozenset({"core"})) == "  #core"

    def test_multiple_sorted(self):
        result = format_inline_tags(frozenset({"flex", "burn", "core"}))
        assert result == "  #burn #core #flex"

    def test_deterministic(self):
        tags = frozenset({"z-tag", "a-tag", "m-tag"})
        assert format_inline_tags(tags) == format_inline_tags(tags)
