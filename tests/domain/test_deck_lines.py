"""Tests for the deck-line grammar helpers in domain/deck_lines.py."""

from vimtg.domain.deck_lines import (
    METADATA_PATTERN,
    format_inline_comment,
    match_metadata,
    parse_card_suffix,
    split_inline_comment,
    split_metadata_prefix,
)


class TestMetadataPattern:
    def test_matches_value(self):
        m = METADATA_PATTERN.match("// Format: modern")
        assert m and m.group(1) == "Format" and m.group(2) == "modern"

    def test_matches_empty_value(self):
        m = METADATA_PATTERN.match("// Format:")
        assert m and m.group(1) == "Format" and m.group(2) == ""

    def test_matches_space_before_colon(self):
        m = METADATA_PATTERN.match("// Format : modern")
        assert m and m.group(1) == "Format" and m.group(2) == "modern"

    def test_matches_source_key(self):
        m = METADATA_PATTERN.match("// Source: https://example.com/deck")
        assert m and m.group(1) == "Source"
        assert m.group(2) == "https://example.com/deck"

    def test_unknown_key_not_metadata(self):
        assert METADATA_PATTERN.match("// Wincons: storm") is None


class TestMatchMetadata:
    def test_key_value(self):
        assert match_metadata("// Deck: Burn") == ("Deck", "Burn")

    def test_empty_value(self):
        assert match_metadata("// Tags:") == ("Tags", "")

    def test_non_metadata_comment(self):
        assert match_metadata("// just a comment") is None

    def test_card_line(self):
        assert match_metadata("4 Lightning Bolt") is None


class TestSplitMetadataPrefix:
    def test_value_present(self):
        assert split_metadata_prefix("// Deck: Burn") == ("// Deck: ", "Burn")

    def test_empty_value_no_trailing_space(self):
        # Prefix gains a trailing space so typed text lands as '// Format: x'
        assert split_metadata_prefix("// Format:") == ("// Format: ", "")

    def test_empty_value_with_trailing_space(self):
        assert split_metadata_prefix("// Format: ") == ("// Format: ", "")

    def test_extra_spaces_preserved_verbatim(self):
        assert split_metadata_prefix("//  Author:  Kee") == ("//  Author:  ", "Kee")

    def test_non_metadata_returns_none(self):
        assert split_metadata_prefix("// notes here") is None


class TestSplitInlineComment:
    def test_no_comment(self):
        assert split_inline_comment("4 Lightning Bolt") == ("4 Lightning Bolt", "")

    def test_comment_present(self):
        assert split_inline_comment("4 Lightning Bolt  // best burn spell") == (
            "4 Lightning Bolt",
            "best burn spell",
        )

    def test_dfc_name_single_spaces_untouched(self):
        assert split_inline_comment("1 Fire // Ice") == ("1 Fire // Ice", "")

    def test_first_delimiter_wins(self):
        assert split_inline_comment("1 Bolt  // a  // b") == ("1 Bolt", "a  // b")

    def test_no_space_after_slashes(self):
        assert split_inline_comment("1 Bolt  //note") == ("1 Bolt", "note")


class TestFormatInlineComment:
    def test_empty(self):
        assert format_inline_comment("") == ""
        assert format_inline_comment("   ") == ""

    def test_nonempty(self):
        assert format_inline_comment("wincon") == "  // wincon"


class TestParseCardSuffix:
    def test_plain_name(self):
        assert parse_card_suffix("Lightning Bolt") == (
            "Lightning Bolt",
            frozenset(),
            "",
        )

    def test_tags_and_comment(self):
        name, tags, comment = parse_card_suffix(
            "Lightning Bolt  #burn #core  // cut for meta?"
        )
        assert name == "Lightning Bolt"
        assert tags == frozenset({"burn", "core"})
        assert comment == "cut for meta?"

    def test_hash_word_in_comment_is_not_a_tag(self):
        name, tags, comment = parse_card_suffix("Bolt  // see #discussion thread")
        assert name == "Bolt"
        assert tags == frozenset()
        assert comment == "see #discussion thread"

    def test_comment_only(self):
        assert parse_card_suffix("Bolt  // wincon") == ("Bolt", frozenset(), "wincon")
