"""Tests for tag domain model — parsing, filtering, formatting."""

from vimtg.domain.tags import (
    TagFilter,
    format_inline_tags,
    matches_filter,
    parse_inline_tags,
    parse_tag_filter,
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


class TestParseTagFilter:
    def test_single_include(self):
        filt = parse_tag_filter("core")
        assert filt == TagFilter(include=frozenset({"core"}))

    def test_multiple_include_spaces(self):
        filt = parse_tag_filter("core burn")
        assert filt.include == frozenset({"core", "burn"})

    def test_and_syntax(self):
        filt = parse_tag_filter("core+flex")
        assert filt.include == frozenset({"core", "flex"})

    def test_or_syntax(self):
        filt = parse_tag_filter("core|flex")
        assert filt.any_of == frozenset({"core", "flex"})

    def test_exclude(self):
        filt = parse_tag_filter("-flex")
        assert filt.exclude == frozenset({"flex"})

    def test_mixed(self):
        filt = parse_tag_filter("core -flex")
        assert filt.include == frozenset({"core"})
        assert filt.exclude == frozenset({"flex"})

    def test_hash_prefix_stripped(self):
        filt = parse_tag_filter("#core #-flex")
        assert filt.include == frozenset({"core"})
        assert filt.exclude == frozenset({"flex"})

    def test_case_insensitive(self):
        filt = parse_tag_filter("CORE")
        assert filt.include == frozenset({"core"})


class TestMatchesFilter:
    def test_include_match(self):
        tags = frozenset({"core", "burn"})
        filt = TagFilter(include=frozenset({"core"}))
        assert matches_filter(tags, filt) is True

    def test_include_no_match(self):
        tags = frozenset({"burn"})
        filt = TagFilter(include=frozenset({"core"}))
        assert matches_filter(tags, filt) is False

    def test_include_all_required(self):
        tags = frozenset({"core"})
        filt = TagFilter(include=frozenset({"core", "burn"}))
        assert matches_filter(tags, filt) is False

    def test_exclude_blocks(self):
        tags = frozenset({"core", "flex"})
        filt = TagFilter(exclude=frozenset({"flex"}))
        assert matches_filter(tags, filt) is False

    def test_exclude_passes(self):
        tags = frozenset({"core"})
        filt = TagFilter(exclude=frozenset({"flex"}))
        assert matches_filter(tags, filt) is True

    def test_any_of_match(self):
        tags = frozenset({"burn"})
        filt = TagFilter(any_of=frozenset({"core", "burn"}))
        assert matches_filter(tags, filt) is True

    def test_any_of_no_match(self):
        tags = frozenset({"flex"})
        filt = TagFilter(any_of=frozenset({"core", "burn"}))
        assert matches_filter(tags, filt) is False

    def test_empty_filter_matches_all(self):
        assert matches_filter(frozenset(), TagFilter()) is True
        assert matches_filter(frozenset({"anything"}), TagFilter()) is True

    def test_empty_tags_with_include_fails(self):
        filt = TagFilter(include=frozenset({"core"}))
        assert matches_filter(frozenset(), filt) is False

    def test_combined_filter(self):
        tags = frozenset({"core", "burn"})
        filt = TagFilter(
            include=frozenset({"core"}),
            exclude=frozenset({"flex"}),
        )
        assert matches_filter(tags, filt) is True

    def test_combined_filter_blocked(self):
        tags = frozenset({"core", "flex"})
        filt = TagFilter(
            include=frozenset({"core"}),
            exclude=frozenset({"flex"}),
        )
        assert matches_filter(tags, filt) is False
