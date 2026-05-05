"""Tests for :stats and :validate command handlers."""

from __future__ import annotations

from vimtg.domain.card import Card, Color, Rarity
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.deck_cmds import cmd_stats, cmd_validate
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _make_card(
    name: str,
    cmc: float = 0.0,
    type_line: str = "Instant",
    colors: tuple[Color, ...] = (),
    prices: dict | None = None,
) -> Card:
    return Card(
        scryfall_id="test",
        name=name,
        mana_cost="{R}" if Color.RED in colors else "",
        cmc=cmc,
        type_line=type_line,
        oracle_text="",
        colors=colors,
        color_identity=(),
        power=None,
        toughness=None,
        set_code="tst",
        rarity=Rarity.COMMON,
        prices=prices or {},
        legalities={},
        image_uri=None,
        layout="normal",
        keywords=(),
    )


def _deck_text() -> str:
    return (
        "// Deck: Test\n"
        "\n"
        "4 Lightning Bolt\n"
        "2 Counterspell\n"
        "1 Abrade\n"
        "\n"
        "SB: 1 Mystical Dispute\n"
    )


class TestStatsBasic:
    def test_stats_without_resolved_cards(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="stats")

        cmd_stats(buffer, cursor, cmd, ctx)
        assert "Cards:" in ctx.message
        assert "main: 3" in ctx.message
        assert "sideboard: 1" in ctx.message

    def test_stats_with_resolved_cards(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        resolved = {
            "Lightning Bolt": _make_card(
                "Lightning Bolt", cmc=1.0, type_line="Instant", colors=(Color.RED,),
            ),
            "Counterspell": _make_card(
                "Counterspell", cmc=2.0, type_line="Instant", colors=(Color.BLUE,),
            ),
            "Abrade": _make_card(
                "Abrade", cmc=2.0, type_line="Instant", colors=(Color.RED,),
            ),
            "Mystical Dispute": _make_card(
                "Mystical Dispute", cmc=3.0, type_line="Instant", colors=(Color.BLUE,),
            ),
        }
        ctx = EditorContext(resolved_cards=resolved)
        cmd = ParsedCommand(name="stats")

        cmd_stats(buffer, cursor, cmd, ctx)
        # Rich stats with analytics
        assert "cards" in ctx.message
        assert "Avg CMC" in ctx.message

    def test_stats_with_prices(self) -> None:
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        resolved = {
            "Lightning Bolt": _make_card(
                "Lightning Bolt", cmc=1.0, type_line="Instant",
                prices={"usd": 1.50},
            ),
        }
        ctx = EditorContext(resolved_cards=resolved)
        cmd = ParsedCommand(name="stats")

        cmd_stats(buffer, cursor, cmd, ctx)
        assert "$6.00" in ctx.message  # 4 copies * $1.50


class TestValidateBasic:
    def test_validate_ok(self) -> None:
        # 60 cards mainboard
        lines = [f"1 Card{i}" for i in range(60)]
        text = "\n".join(lines) + "\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="validate")

        cmd_validate(buffer, cursor, cmd, ctx)
        assert "Deck OK" in ctx.message

    def test_validate_no_mainboard(self) -> None:
        buffer = Buffer.from_text("// Empty deck\n")
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="validate")

        cmd_validate(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "No mainboard cards" in ctx.message

    def test_validate_under_60(self) -> None:
        text = "4 Lightning Bolt\n2 Counterspell\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="validate")

        cmd_validate(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "min 60" in ctx.message

    def test_validate_over_4_copies(self) -> None:
        text = "5 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="validate")

        cmd_validate(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert ">4 copies" in ctx.message

    def test_validate_basic_lands_exempt(self) -> None:
        lines = ["20 Island"] + [f"1 Card{i}" for i in range(40)]
        text = "\n".join(lines) + "\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="validate")

        cmd_validate(buffer, cursor, cmd, ctx)
        assert "Deck OK" in ctx.message

    def test_validate_sideboard_over_15(self) -> None:
        main_lines = [f"1 Card{i}" for i in range(60)]
        sb_lines = [f"SB: 1 SBCard{i}" for i in range(16)]
        text = "\n".join(main_lines + sb_lines) + "\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="validate")

        cmd_validate(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "max 15" in ctx.message

    def test_validate_with_unresolved_cards(self) -> None:
        text = "4 Lightning Bolt\n2 FakeCard\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        resolved = {
            "Lightning Bolt": _make_card("Lightning Bolt"),
        }
        ctx = EditorContext(resolved_cards=resolved)
        cmd = ParsedCommand(name="validate")

        cmd_validate(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "Card not found: FakeCard" in ctx.message
