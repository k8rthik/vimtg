"""Tests for the deck-line grammar helpers in domain/deck_lines.py."""

import pytest

from vimtg.domain.deck_lines import (
    METADATA_PATTERN,
    CardLine,
    PlanLine,
    format_inline_comment,
    is_bare_card_line,
    is_mtgo_sideboard_header,
    match_metadata,
    parse_card_line,
    parse_card_suffix,
    parse_plan_line,
    split_inline_comment,
    split_metadata_prefix,
    strip_printing_suffix,
    zone_block_contexts,
    zone_context_at,
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


class TestParseCardLine:
    """One parse for every card-shaped line — the buffer, the deck
    parser, :sort and the layout all read cards through it."""

    def test_zone_prefixes(self):
        assert parse_card_line("4 Lightning Bolt") == CardLine("DCK", 4, "Lightning Bolt")
        assert parse_card_line("SB: 2 Duress") == CardLine("SB", 2, "Duress")
        assert parse_card_line("MB: 1 Opt") == CardLine("MB", 1, "Opt")
        assert parse_card_line("CMD: 1 Tymna the Weaver") == CardLine("CMD", 1, "Tymna the Weaver")
        assert parse_card_line("CMP: 1 Lurrus") == CardLine("CMP", 1, "Lurrus")

    def test_whitespace_and_suffix_tokens(self):
        assert parse_card_line("   \t4   Opt  @draw  #core #flex  // note  ") == CardLine(
            "DCK", 4, "Opt", "draw", frozenset({"core", "flex"}), "note"
        )

    def test_printing_suffix_is_not_part_of_the_name(self):
        assert parse_card_line("4 Goblin Guide (ZEN) 126 *F*  #haste") == CardLine(
            "DCK", 4, "Goblin Guide", tags=frozenset({"haste"})
        )

    def test_quantity_is_clamped(self):
        assert parse_card_line("1000000 Opt").quantity == 999
        assert parse_card_line("0 Opt").quantity == 0

    @pytest.mark.parametrize("text", [
        "3  #tag",            # tags but no name
        "2  @cat",            # category but no name
        "MB: 0   // only a comment",  # a comment after the quantity, no name
        "4   // note",
        "sb: 1 X",            # prefixes are uppercase
        "Lightning Bolt",     # no quantity
        "// 4 Opt",
        "SB:",
        "VS: Tron",
        "",
    ])
    def test_non_card_lines(self, text: str):
        assert parse_card_line(text) is None

    def test_is_bare_card_line(self):
        assert is_bare_card_line("    4 Opt")
        assert not is_bare_card_line("SB: 4 Opt")
        assert not is_bare_card_line("    4  #tag")


class TestParsePlanLine:
    def test_signs(self):
        assert parse_plan_line("    -4 Lightning Bolt  // keep 2") == PlanLine(
            "-", 4, "Lightning Bolt", "keep 2"
        )
        assert parse_plan_line("+ 3 Alpine Moon") == PlanLine("+", 3, "Alpine Moon")
        assert parse_plan_line("    2 Rest in Peace") == PlanLine("", 2, "Rest in Peace")

    @pytest.mark.parametrize("text", [
        "SB: 1 Duress",  # an explicit zone prefix is a zone card, never an entry
        "-1 #tag",       # no card name
        "-1   // note",
        "VS: Tron",
        "-Bolt",
        "// note",
    ])
    def test_non_entries(self, text: str):
        assert parse_plan_line(text) is None


class TestStripPrintingSuffix:
    def test_set_codes_in_one_case(self):
        assert strip_printing_suffix("Goblin Guide (ZEN) 126") == "Goblin Guide"
        assert strip_printing_suffix("Goblin Guide (zen) 126") == "Goblin Guide"
        assert strip_printing_suffix("Bonecrusher Giant (PLST) ELD-115") == "Bonecrusher Giant"

    def test_parenthesised_name_parts_survive(self):
        # Real card names: mixed case or spaces inside the parentheses
        assert strip_printing_suffix("Hazmat Suit (Used)") == "Hazmat Suit (Used)"
        assert strip_printing_suffix("B.F.M. (Big Furry Monster)") == "B.F.M. (Big Furry Monster)"
        assert (
            strip_printing_suffix("Erase (Not the Urza's Legacy One)")
            == "Erase (Not the Urza's Legacy One)"
        )


class TestMtgoSideboardHeader:
    def test_header_shapes(self):
        assert is_mtgo_sideboard_header("Sideboard")
        assert is_mtgo_sideboard_header("  sideboard:  ")
        assert is_mtgo_sideboard_header("SIDEBOARD")
        assert not is_mtgo_sideboard_header("// Sideboard")
        assert not is_mtgo_sideboard_header("Sideboard (15)")
        assert not is_mtgo_sideboard_header("SB:")

    def test_contexts_after_the_header(self):
        lines = [
            "4 Opt", "Sideboard", "2 Duress", "    1 Negate", "", "CMD:", "    1 Tymna", "3 Bolt",
        ]
        assert zone_block_contexts(lines) == [
            None, None, "SB", "SB", None, None, "CMD", "SB"
        ]
        assert [zone_context_at(lines, i) for i in range(len(lines))] == zone_block_contexts(lines)

    def test_plan_block_inside_mtgo_sideboard(self):
        lines = ["Sideboard", "2 Duress", "VS: Tron", "    -1 Opt", "1 Negate"]
        assert zone_block_contexts(lines) == [None, "SB", None, "VS", "SB"]
