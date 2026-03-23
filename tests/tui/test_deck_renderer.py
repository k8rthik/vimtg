"""Tests for deck_renderer — pure rendering logic, no Textual required."""

from vimtg.domain.card import Card, Color, Rarity
from vimtg.editor.buffer import Buffer
from vimtg.tui.deck_renderer import format_mana, render_line


def _make_card(**overrides: object) -> Card:
    """Create a test Card with sensible defaults."""
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
        "price_usd": 1.50,
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
    buf = Buffer.from_text("// Creatures\n")
    lines = render_line(0, buf, cursor_row=1, resolved={})
    assert len(lines) == 1
    assert "Creatures" in lines[0].plain


def test_render_blank_line() -> None:
    buf = Buffer.from_text("\n4 Lightning Bolt\n")
    lines = render_line(0, buf, cursor_row=1, resolved={})
    assert len(lines) == 1
    # Blank line has only the line number gutter
    text = lines[0].plain.strip()
    assert text == "" or text.isdigit()  # just gutter number or empty


def test_render_cursor_indicator() -> None:
    buf = Buffer.from_text("4 Lightning Bolt\n4 Lava Spike\n")
    cursor_lines = render_line(0, buf, cursor_row=0, resolved={})
    non_cursor_lines = render_line(1, buf, cursor_row=0, resolved={})
    assert ">" in cursor_lines[0].plain
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
