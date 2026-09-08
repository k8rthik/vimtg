"""Tests for the section-header vocabulary: one table, one identity."""

from __future__ import annotations

import pytest

from vimtg.domain.section_keys import (
    SectionKey,
    SectionKind,
    parse_section_key,
    section_key_for_label,
)


class TestParseSectionKey:
    @pytest.mark.parametrize(
        "text",
        ["// Sorcery", "// Sorceries", "//Sorceries", "    // sorceries"],
    )
    def test_type_header_spellings_share_one_key(self, text: str) -> None:
        assert parse_section_key(text) == SectionKey(SectionKind.TYPE, "Sorcery")

    def test_category_header(self) -> None:
        assert parse_section_key("// @Ramp") == SectionKey(
            SectionKind.CATEGORY, "ramp"
        )

    def test_zone_label_header(self) -> None:
        assert parse_section_key("// Sideboard") == SectionKey(
            SectionKind.ZONE_LABEL, "SB"
        )

    def test_zone_block_header(self) -> None:
        assert parse_section_key("dck:") == SectionKey(SectionKind.ZONE_BLOCK, "DCK")

    @pytest.mark.parametrize("label", ["Other", "Uncategorized", "Spells", "Mainboard"])
    def test_other_labels_are_exact(self, label: str) -> None:
        assert parse_section_key(f"// {label}") == SectionKey(SectionKind.OTHER, label)

    @pytest.mark.parametrize(
        "text",
        ["// tweak the mana base", "// Artifact Lands", "// Deck: Burn",
         "4 Lightning Bolt", "", "VS: Tron", "// Format: modern"],
    )
    def test_non_headers_are_none(self, text: str) -> None:
        assert parse_section_key(text) is None


class TestSectionKeyRendering:
    def test_type_key_renders_canonical_plural(self) -> None:
        assert SectionKey(SectionKind.TYPE, "Sorcery").header_text() == "// Sorceries"

    def test_category_key_renders_at_form(self) -> None:
        assert SectionKey(SectionKind.CATEGORY, "ramp").header_text() == "// @ramp"

    def test_zone_label_renders_label(self) -> None:
        assert SectionKey(SectionKind.ZONE_LABEL, "SB").header_text() == "// Sideboard"

    def test_zone_block_renders_tag(self) -> None:
        assert SectionKey(SectionKind.ZONE_BLOCK, "CMD").header_text() == "CMD:"

    def test_indent_is_applied(self) -> None:
        assert SectionKey(SectionKind.OTHER, "Other").header_text("    ") == "    // Other"

    def test_round_trip(self) -> None:
        for key in (
            SectionKey(SectionKind.TYPE, "Creature"),
            SectionKey(SectionKind.CATEGORY, "draw"),
            SectionKey(SectionKind.ZONE_LABEL, "MB"),
            SectionKey(SectionKind.ZONE_BLOCK, "SB"),
            SectionKey(SectionKind.OTHER, "Uncategorized"),
        ):
            assert parse_section_key(key.header_text()) == key


class TestZoneTag:
    def test_mainboard_kinds_are_dck(self) -> None:
        assert SectionKey(SectionKind.TYPE, "Land").zone_tag == "DCK"
        assert SectionKey(SectionKind.CATEGORY, "ramp").zone_tag == "DCK"
        assert SectionKey(SectionKind.OTHER, "Other").zone_tag == "DCK"

    def test_zone_kinds_carry_their_tag(self) -> None:
        assert SectionKey(SectionKind.ZONE_LABEL, "SB").zone_tag == "SB"
        assert SectionKey(SectionKind.ZONE_BLOCK, "CMD").zone_tag == "CMD"


class TestSectionKeyForLabel:
    def test_type_labels(self) -> None:
        assert section_key_for_label("Sorcery") == SectionKey(SectionKind.TYPE, "Sorcery")
        assert section_key_for_label("Sorceries") == SectionKey(SectionKind.TYPE, "Sorcery")

    def test_other_label(self) -> None:
        assert section_key_for_label("Other") == SectionKey(SectionKind.OTHER, "Other")

    def test_unknown_label_is_other_verbatim(self) -> None:
        # A caller-invented label still yields a usable key
        assert section_key_for_label("Ramp Pieces") == SectionKey(
            SectionKind.OTHER, "Ramp Pieces"
        )
