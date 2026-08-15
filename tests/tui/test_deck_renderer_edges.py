"""Edge cases for deck_renderer — tags, filter collapse, long names, gutter, CMD entries.

Complements test_deck_renderer.py with regression coverage for less-common
buffer states that historically have produced subtle visual breakage.
"""

from __future__ import annotations

from vimtg.domain.card import Card, Color, Prices, Rarity
from vimtg.editor.buffer import Buffer
from vimtg.tui.deck_renderer import (
    _line_number_gutter,
    format_mana,
    render_line,
)
from vimtg.tui.theme import COLORS


def _make_card(**overrides: object) -> Card:
    price_usd = overrides.pop("price_usd", 1.50)
    if "prices" not in overrides:
        overrides["prices"] = Prices(usd=price_usd)
    defaults = {
        "scryfall_id": "test-id",
        "name": "Lightning Bolt",
        "mana_cost": "{R}",
        "cmc": 1.0,
        "type_line": "Instant",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        "colors": (Color.RED,),
        "color_identity": (Color.RED,),
        "power": None,
        "toughness": None,
        "set_code": "sta",
        "rarity": Rarity.UNCOMMON,
        "legalities": {},
        "image_uri": None,
        "layout": "normal",
        "keywords": (),
    }
    defaults.update(overrides)
    return Card(**defaults)  # type: ignore[arg-type]


# ── Line number gutter ─────────────────────────────────────────────


class TestLineNumberGutter:
    def test_blank_line_has_empty_gutter(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n\n4 Lava Spike\n")
        gutter = _line_number_gutter(1, cursor_row=0, buf=buf)
        # Blank-line gutter is whitespace only
        assert gutter.plain.strip() == ""

    def test_cursor_line_shows_absolute_number(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n4 Lava Spike\n4 Rift Bolt\n")
        gutter = _line_number_gutter(1, cursor_row=1, buf=buf)
        assert "2" in gutter.plain

    def test_relative_numbers_for_non_cursor_lines(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n4 Lava Spike\n4 Rift Bolt\n")
        # cursor on line 0, line 2 is 2 non-blank lines away
        gutter = _line_number_gutter(2, cursor_row=0, buf=buf)
        assert "2" in gutter.plain

    def test_relative_count_skips_blank_lines(self) -> None:
        """A blank line between cursor and target should not contribute to count."""
        buf = Buffer.from_text("4 Lightning Bolt\n\n4 Lava Spike\n")
        # cursor on line 0, line 2 is 1 non-blank line away (the blank is skipped)
        gutter = _line_number_gutter(2, cursor_row=0, buf=buf)
        # Find the leading number
        num = gutter.plain.strip()
        assert num == "1"

    def test_gutter_width_scales_with_total_lines(self) -> None:
        """Gutter width must be wide enough to fit the largest line number."""
        # Build a buffer with 1000 lines
        text = "\n".join(f"1 Card{i:03}" for i in range(1000))
        buf = Buffer.from_text(text)
        gutter = _line_number_gutter(999, cursor_row=999, buf=buf)
        # Should accommodate 4-character number "1000" plus trailing space
        assert len(gutter.plain) >= 5


# ── Tag rendering ──────────────────────────────────────────────────


class TestTagRendering:
    """Tags use a two-space delimiter to separate from the card name."""

    def test_inline_tags_rendered_with_hash_prefix(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt  #burn #aggro\n")
        lines = render_line(0, buf, cursor_row=1, resolved={})
        plain = lines[0].plain
        assert "#aggro" in plain
        assert "#burn" in plain

    def test_tags_rendered_in_sorted_order(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt  #zebra #alpha #middle\n")
        lines = render_line(0, buf, cursor_row=1, resolved={})
        plain = lines[0].plain
        i_alpha = plain.index("#alpha")
        i_middle = plain.index("#middle")
        i_zebra = plain.index("#zebra")
        assert i_alpha < i_middle < i_zebra

    def test_tag_uses_tag_color(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt  #burn\n")
        lines = render_line(0, buf, cursor_row=1, resolved={})
        text = lines[0]
        start = text.plain.index("#burn")
        styles = " ".join(
            str(s.style) for s in text.spans if s.start <= start < s.end
        )
        assert COLORS["tag"] in styles

    def test_no_tags_no_hash_appears(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        lines = render_line(0, buf, cursor_row=1, resolved={})
        assert "#" not in lines[0].plain


# ── Long card names (alignment regression) ─────────────────────────


class TestLongCardNames:
    def test_long_card_name_not_truncated(self) -> None:
        """Card names wider than the 26-char column must still render in full."""
        long_name = "Asmoranomardicadaistinaculdacar"  # 31 chars
        buf = Buffer.from_text(f"1 {long_name}\n")
        lines = render_line(0, buf, cursor_row=0, resolved={})
        assert long_name in lines[0].plain

    def test_short_card_name_padded_to_column(self) -> None:
        """Short names get padded so the next column starts predictably."""
        buf = Buffer.from_text("4 Bolt\n")
        card = _make_card(name="Bolt", mana_cost="{R}")
        lines = render_line(0, buf, cursor_row=0, resolved={"Bolt": card})
        plain = lines[0].plain
        # The mana cost should appear after the name with at least one space
        i_name_end = plain.index("Bolt") + len("Bolt")
        i_mana = plain.index("{R}")
        assert i_mana > i_name_end


# ── Commander entries ──────────────────────────────────────────────


class TestCommanderEntry:
    def test_cmd_prefix_rendered(self) -> None:
        buf = Buffer.from_text("CMD: 1 Atraxa, Praetors' Voice\n")
        lines = render_line(0, buf, cursor_row=1, resolved={})
        plain = lines[0].plain
        assert "CMD:" in plain
        assert "Atraxa" in plain

    def test_cmd_uses_sideboard_color(self) -> None:
        """CMD: should be styled like SB: so the prefix stands out."""
        buf = Buffer.from_text("CMD: 1 Atraxa, Praetors' Voice\n")
        lines = render_line(0, buf, cursor_row=1, resolved={})
        text = lines[0]
        start = text.plain.index("CMD:")
        styles = " ".join(
            str(s.style) for s in text.spans if s.start <= start < s.end
        )
        assert COLORS["sideboard"] in styles


# ── Multi-line oracle expansion ────────────────────────────────────


class TestExpansionWrapping:
    def test_multi_paragraph_oracle_keeps_prefix(self) -> None:
        """Each oracle paragraph and wrapped line should share the same indent prefix."""
        oracle = "First ability line.\nSecond ability line that is also short."
        buf = Buffer.from_text("1 Multi Card\n")
        card = _make_card(name="Multi Card", oracle_text=oracle)
        lines = render_line(0, buf, cursor_row=0, resolved={"Multi Card": card})
        # Expansion lines (after the main line) all start with the box-drawing "│"
        expansion = lines[1:]
        assert len(expansion) >= 3  # type, line1, line2, meta (at least)
        oracle_lines = [ln for ln in expansion if "ability line" in ln.plain]
        assert len(oracle_lines) >= 2
        for ln in oracle_lines:
            assert "│" in ln.plain

    def test_expansion_includes_meta_with_set_rarity_price(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        card = _make_card(price_usd=2.99)
        lines = render_line(0, buf, cursor_row=0, resolved={"Lightning Bolt": card})
        meta = lines[-1].plain
        assert "Set: STA" in meta
        assert "Rarity: Uncommon" in meta
        assert "$2.99" in meta

    def test_show_prices_false_omits_price(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        card = _make_card(price_usd=2.99)
        lines = render_line(
            0, buf, cursor_row=0, resolved={"Lightning Bolt": card}, show_prices=False,
        )
        meta = lines[-1].plain
        assert "$" not in meta
        assert "Rarity:" in meta  # other meta still present

    def test_currency_symbol_override(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        card = _make_card(prices=Prices(eur=1.50), price_usd=None)
        lines = render_line(
            0, buf, cursor_row=0,
            resolved={"Lightning Bolt": card},
            price_source="eur",
            currency_symbol="€",
        )
        meta = lines[-1].plain
        assert "€1.50" in meta


# ── Filter collapse indicator ──────────────────────────────────────



class TestManaCostEdgeCases:
    def test_hybrid_mana_symbol(self) -> None:
        text = format_mana("{W/U}")
        assert "{W/U}" in text.plain

    def test_phyrexian_mana(self) -> None:
        text = format_mana("{W/P}")
        assert "{W/P}" in text.plain

    def test_generic_mana_styled_as_colorless(self) -> None:
        text = format_mana("{3}")
        styles = " ".join(str(s.style) for s in text.spans)
        assert COLORS["mana_colorless"] in styles

    def test_color_specific_styling_applied(self) -> None:
        text = format_mana("{R}")
        styles = " ".join(str(s.style) for s in text.spans)
        assert COLORS["mana_red"] in styles


# ── Cursor highlighting ────────────────────────────────────────────


class TestCursorHighlight:
    def test_cursor_line_has_cursor_bg_style(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n4 Lava Spike\n")
        lines = render_line(0, buf, cursor_row=0, resolved={})
        text = lines[0]
        # Some span must apply the cursor_bg style across the whole line
        styles = " ".join(str(s.style) for s in text.spans)
        assert COLORS["cursor_bg"] in styles

    def test_non_cursor_line_no_cursor_bg(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n4 Lava Spike\n")
        lines = render_line(1, buf, cursor_row=0, resolved={})
        styles = " ".join(str(s.style) for s in lines[0].spans)
        assert COLORS["cursor_bg"] not in styles

    def test_cursor_on_comment_still_highlights(self) -> None:
        buf = Buffer.from_text("// Section\n4 Lightning Bolt\n")
        lines = render_line(0, buf, cursor_row=0, resolved={})
        styles = " ".join(str(s.style) for s in lines[0].spans)
        assert COLORS["cursor_bg"] in styles


# ── show_line_numbers toggle ──────────────────────────────────────


class TestLineNumberToggle:
    def test_line_numbers_hidden_when_disabled(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n4 Lava Spike\n")
        lines = render_line(1, buf, cursor_row=0, resolved={}, show_line_numbers=False)
        # When numbers are off, the line shouldn't start with a digit
        plain = lines[0].plain.lstrip()
        assert not plain.split()[0].isdigit() or plain.split()[0] == "4"
