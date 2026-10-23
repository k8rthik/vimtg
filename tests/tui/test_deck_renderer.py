"""Tests for deck_renderer — pure rendering logic, no Textual required."""

from vimtg.domain.card import Card, Color, Prices, Rarity
from vimtg.editor.buffer import Buffer
from vimtg.editor.header_counts import HeaderCount
from vimtg.tui.deck_renderer import format_mana, render_line


def _make_card(**overrides: object) -> Card:
    """Create a test Card with sensible defaults."""
    # Extract price_usd shorthand and convert to Prices
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


def test_render_card_line_without_resolved() -> None:
    buf = Buffer.from_text("4 Lightning Bolt\n")
    lines = render_line(0, buf, cursor_row=0, resolved={})
    assert len(lines) >= 1
    assert "Lightning Bolt" in lines[0].plain


def test_render_card_line_with_resolved_shows_expansion() -> None:
    buf = Buffer.from_text("4 Lightning Bolt\n")
    card = _make_card()
    lines = render_line(0, buf, cursor_row=0, resolved={"Lightning Bolt": card})
    # Should have main line + expansion lines (type, oracle, meta)
    assert len(lines) >= 3
    assert "Lightning Bolt" in lines[0].plain
    assert "Instant" in lines[1].plain
    assert "3 damage" in lines[2].plain


def test_render_no_expansion_when_not_cursor() -> None:
    buf = Buffer.from_text("4 Lightning Bolt\n4 Lava Spike\n")
    card = _make_card()
    lines = render_line(0, buf, cursor_row=1, resolved={"Lightning Bolt": card})
    # Not on cursor, so no expansion
    assert len(lines) == 1


def test_render_comment() -> None:
    buf = Buffer.from_text("// Creature\n")
    lines = render_line(0, buf, cursor_row=1, resolved={})
    assert len(lines) == 1
    assert "Creature" in lines[0].plain


def test_render_blank_line() -> None:
    buf = Buffer.from_text("\n4 Lightning Bolt\n")
    lines = render_line(0, buf, cursor_row=1, resolved={})
    assert len(lines) == 1
    # Blank line has only the line number gutter
    text = lines[0].plain.strip()
    assert text == "" or text.isdigit()  # just gutter number or empty


def test_render_cursor_no_indicator() -> None:
    """Cursor line should NOT have a '>' prefix — background highlight is enough."""
    buf = Buffer.from_text("4 Lightning Bolt\n4 Lava Spike\n")
    cursor_lines = render_line(0, buf, cursor_row=0, resolved={})
    non_cursor_lines = render_line(1, buf, cursor_row=0, resolved={})
    assert ">" not in cursor_lines[0].plain
    assert ">" not in non_cursor_lines[0].plain


def test_render_sideboard_entry() -> None:
    buf = Buffer.from_text("SB: 2 Rest in Peace\n")
    lines = render_line(0, buf, cursor_row=0, resolved={})
    assert "SB:" in lines[0].plain
    assert "Rest in Peace" in lines[0].plain


def test_format_mana_single_color() -> None:
    result = format_mana("{R}")
    assert "{R}" in result.plain


def test_format_mana_multi_color() -> None:
    result = format_mana("{1}{W}{U}")
    assert "{1}" in result.plain
    assert "{W}" in result.plain
    assert "{U}" in result.plain


def test_format_mana_empty() -> None:
    result = format_mana("")
    assert result.plain.strip() == ""


def test_render_expansion_creature_with_power() -> None:
    buf = Buffer.from_text("4 Goblin Guide\n")
    card = _make_card(
        name="Goblin Guide",
        type_line="Creature \u2014 Goblin Scout",
        power="2",
        toughness="2",
        oracle_text="Haste",
    )
    lines = render_line(0, buf, cursor_row=0, resolved={"Goblin Guide": card})
    # Should show power/toughness in expansion
    expansion_text = " ".join(line.plain for line in lines[1:])
    assert "2/2" in expansion_text


def test_render_expansion_shows_set_and_rarity() -> None:
    buf = Buffer.from_text("4 Lightning Bolt\n")
    card = _make_card(price_usd=1.50)
    lines = render_line(0, buf, cursor_row=0, resolved={"Lightning Bolt": card})
    meta_line = lines[-1].plain
    assert "STA" in meta_line
    assert "Uncommon" in meta_line
    assert "$1.50" in meta_line


class TestLintSign:
    def _err(self, level="error"):
        from vimtg.domain.validation import ValidationError

        return ValidationError(level, "test issue", line_number=1)

    def test_error_sign_rendered(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        lines = render_line(0, buf, cursor_row=1, resolved={}, line_error=self._err())
        assert lines[0].plain.startswith("✗ ")

    def test_warning_sign_rendered(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        lines = render_line(
            0, buf, cursor_row=1, resolved={}, line_error=self._err("warning")
        )
        assert lines[0].plain.startswith("! ")

    def test_clean_line_reserves_sign_column(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        lines = render_line(0, buf, cursor_row=1, resolved={})
        assert lines[0].plain.startswith("  ")

    def test_sign_without_line_numbers(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        lines = render_line(
            0, buf, cursor_row=1, resolved={},
            show_line_numbers=False, line_error=self._err(),
        )
        assert lines[0].plain.startswith("✗ ")


class TestInlineCommentRender:
    def test_comment_rendered_dim(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt  #burn  // best burn spell\n")
        lines = render_line(0, buf, cursor_row=1, resolved={})
        assert "// best burn spell" in lines[0].plain
        assert "#burn" in lines[0].plain


class TestHeaderCountRender:
    def test_section_header_shows_count(self) -> None:
        buf = Buffer.from_text("// Creatures\n4 Bear\n")
        lines = render_line(
            0, buf, cursor_row=1, resolved={}, header_count=HeaderCount(4)
        )
        assert "(4)" in lines[0].plain

    def test_section_header_without_count_unannotated(self) -> None:
        buf = Buffer.from_text("// Creatures\n4 Bear\n")
        lines = render_line(0, buf, cursor_row=1, resolved={})
        assert "(" not in lines[0].plain

    def test_zone_header_shows_count(self) -> None:
        buf = Buffer.from_text("DCK:\n    4 Bear\n")
        lines = render_line(
            0, buf, cursor_row=1, resolved={}, header_count=HeaderCount(4)
        )
        assert "(4)" in lines[0].plain

    def test_deck_metadata_shows_cards_total(self) -> None:
        buf = Buffer.from_text("// Deck: Test\n4 Bear\n")
        lines = render_line(
            0, buf, cursor_row=1, resolved={}, header_count=HeaderCount(4)
        )
        assert "4 cards" in lines[0].plain

    def test_deck_metadata_shows_sideboard_split(self) -> None:
        buf = Buffer.from_text("// Deck: Test\n4 Bear\nSB: 3 Duress\n")
        lines = render_line(
            0, buf, cursor_row=1, resolved={},
            header_count=HeaderCount(4, side=3),
        )
        assert "4/3 cards" in lines[0].plain

    def test_card_line_ignores_header_count(self) -> None:
        buf = Buffer.from_text("4 Bear\n")
        lines = render_line(
            0, buf, cursor_row=1, resolved={}, header_count=HeaderCount(9)
        )
        assert "(9)" not in lines[0].plain


def test_long_card_name_truncated_with_gap_before_mana() -> None:
    """'Eidolon of the Great Revel{R}{R}' — a 26+ character name ran
    straight into the mana cost."""
    name = "Eidolon of the Great Revel"
    buf = Buffer.from_text(f"4 {name}\n4 Lightning Bolt\n")
    card = _make_card(name=name, mana_cost="{R}{R}", type_line="Enchantment Creature")
    line = render_line(0, buf, cursor_row=1, resolved={name: card})[0].plain
    assert "Eidolon of the Great Rev… {R}{R}" in line
    assert "Revel{R}" not in line


def test_name_one_short_of_the_column_keeps_its_gap() -> None:
    name = "A" * 25
    buf = Buffer.from_text(f"1 {name}\n")
    card = _make_card(name=name, mana_cost="{1}")
    line = render_line(0, buf, cursor_row=0, resolved={name: card})[0].plain
    assert f"{name} {{1}}" in line


def test_unresolved_long_name_is_shown_whole() -> None:
    """Nothing follows an unresolved card's name, and the whole name
    is what the user needs to spot the typo."""
    name = "Eidolon of the Great Revvel Typo"
    buf = Buffer.from_text(f"4 {name}\n")
    assert name in render_line(0, buf, cursor_row=0, resolved={})[0].plain


def test_long_type_line_ends_in_an_ellipsis() -> None:
    """The type column cuts like the name column: with a "…", not mid-word."""
    name = "Thassa, Deep-Dwelling"
    buf = Buffer.from_text(f"1 {name}\n")
    card = _make_card(
        name=name, mana_cost="{3}{U}", type_line="Legendary Enchantment Creature — God",
    )
    line = render_line(0, buf, cursor_row=1, resolved={name: card})[0].plain
    assert "Legendary Enchantme…" in line
    assert "Legendary Enchantmen " not in line + " "


def test_a_card_line_never_wraps_past_the_width() -> None:
    """In a narrow split the card line is cut at the pane's edge with a
    "…" instead of wrapping its tail to column 0."""
    name = "Thassa, Deep-Dwelling"
    buf = Buffer.from_text(f"1 {name}  #ramp #value\n")
    card = _make_card(
        name=name, mana_cost="{3}{U}", type_line="Legendary Enchantment Creature — God",
    )
    line = render_line(0, buf, cursor_row=1, resolved={name: card}, width=40)[0]
    assert len(line.plain) <= 40
    assert line.plain.endswith("…")
