"""Tests for the deck layout regrouper."""

from __future__ import annotations

from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.layout import (
    LAYOUT_CATEGORY,
    LAYOUT_TYPE,
    detect_layout,
    enclosing_category,
    regroup_buffer,
)


def _card(name: str, type_line: str, cmc: float = 1.0) -> Card:
    return Card.from_scryfall({
        "id": "x", "name": name, "type_line": type_line, "cmc": cmc,
    })


RESOLVED = {
    "Cultivate": _card("Cultivate", "Sorcery", 3.0),
    "Opt": _card("Opt", "Instant", 1.0),
    "Llanowar Elves": _card("Llanowar Elves", "Creature — Elf Druid", 1.0),
    "Forest": _card("Forest", "Basic Land — Forest", 0.0),
}

CATEGORY_DECK = """// Deck: Test
// Format: commander

// @ramp
1 Cultivate  @ramp
1 Llanowar Elves  @ramp

// @draw
1 Opt  @draw

// Uncategorized
1 Forest
"""


class TestDetectLayout:
    def test_category_header_means_category(self) -> None:
        assert detect_layout(Buffer.from_text(CATEGORY_DECK)) == LAYOUT_CATEGORY

    def test_type_headers_mean_type(self) -> None:
        buf = Buffer.from_text("// Creatures\n1 Llanowar Elves\n")
        assert detect_layout(buf) == LAYOUT_TYPE

    def test_no_headers_default_type(self) -> None:
        assert detect_layout(Buffer.from_text("1 Opt\n")) == LAYOUT_TYPE


class TestEnclosingCategory:
    def test_inside_category_section(self) -> None:
        buf = Buffer.from_text(CATEGORY_DECK)
        for i in range(buf.line_count()):
            if "Cultivate" in buf.get_line(i).text:
                assert enclosing_category(buf, i) == "ramp"

    def test_under_type_header(self) -> None:
        buf = Buffer.from_text("// Creatures\n1 Llanowar Elves\n")
        assert enclosing_category(buf, 1) == ""

    def test_no_header_above(self) -> None:
        buf = Buffer.from_text("1 Opt\n")
        assert enclosing_category(buf, 0) == ""


class TestRegroupByCategory:
    def test_groups_under_category_headers(self) -> None:
        buf = Buffer.from_text(
            "1 Cultivate  @ramp\n1 Opt  @draw\n1 Llanowar Elves  @ramp\n"
        )
        out = regroup_buffer(buf, LAYOUT_CATEGORY).to_text()
        assert "// @ramp" in out
        assert "// @draw" in out
        # first-appearance order: ramp before draw
        assert out.index("// @ramp") < out.index("// @draw")

    def test_uncategorized_group_last(self) -> None:
        buf = Buffer.from_text("1 Forest\n1 Cultivate  @ramp\n")
        out = regroup_buffer(buf, LAYOUT_CATEGORY).to_text()
        assert "// Uncategorized" in out
        assert out.index("// @ramp") < out.index("// Uncategorized")

    def test_metadata_stays_on_top(self) -> None:
        buf = Buffer.from_text("// Deck: X\n1 Cultivate  @ramp\n")
        out = regroup_buffer(buf, LAYOUT_CATEGORY).to_text()
        assert out.startswith("// Deck: X")

    def test_freeform_comments_survive(self) -> None:
        buf = Buffer.from_text("// try more lands\n1 Cultivate  @ramp\n")
        out = regroup_buffer(buf, LAYOUT_CATEGORY).to_text()
        assert "// try more lands" in out

    def test_sideboard_kept_in_zone(self) -> None:
        buf = Buffer.from_text("1 Cultivate  @ramp\nSB: 1 Opt\n")
        out = regroup_buffer(buf, LAYOUT_CATEGORY).to_text()
        assert "// Sideboard" in out
        assert "SB: 1 Opt" in out

    def test_in_group_order_follows_field(self) -> None:
        buf = Buffer.from_text(
            "1 Cultivate  @ramp\n1 Llanowar Elves  @ramp\n"
        )
        out = regroup_buffer(
            buf, LAYOUT_CATEGORY, RESOLVED, order_field="cmc"
        ).to_text()
        assert out.index("Llanowar Elves") < out.index("Cultivate")


class TestRegroupByType:
    def test_groups_under_type_headers(self) -> None:
        buf = Buffer.from_text(CATEGORY_DECK)
        out = regroup_buffer(buf, LAYOUT_TYPE, RESOLVED).to_text()
        assert "// Creatures" in out
        assert "// Instants" in out
        assert "// Sorceries" in out
        assert "// Lands" in out
        # canonical type order
        assert out.index("// Creatures") < out.index("// Instants")
        assert out.index("// Instants") < out.index("// Sorceries")
        assert out.index("// Sorceries") < out.index("// Lands")

    def test_unresolved_cards_go_to_other(self) -> None:
        buf = Buffer.from_text("1 Mystery Card\n")
        out = regroup_buffer(buf, LAYOUT_TYPE, {}).to_text()
        assert "// Other" in out

    def test_categories_survive_type_regroup(self) -> None:
        buf = Buffer.from_text(CATEGORY_DECK)
        out = regroup_buffer(buf, LAYOUT_TYPE, RESOLVED).to_text()
        assert "1 Cultivate  @ramp" in out


class TestLosslessToggle:
    def test_category_groups_restored_after_roundtrip(self) -> None:
        original = Buffer.from_text(CATEGORY_DECK)
        typed = regroup_buffer(original, LAYOUT_TYPE, RESOLVED)
        back = regroup_buffer(typed, LAYOUT_CATEGORY, RESOLVED)
        text = back.to_text()
        assert "// @ramp" in text
        assert "// @draw" in text
        assert "1 Cultivate  @ramp" in text
        assert "1 Opt  @draw" in text
        assert "// Uncategorized" in text

    def test_rejects_unknown_mode(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Unknown layout mode"):
            regroup_buffer(Buffer.from_text("1 Opt\n"), "nope")
