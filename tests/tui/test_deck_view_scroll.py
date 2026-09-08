"""DeckView windows by rendered rows, so expansion never clips."""

from textual.geometry import Size

from vimtg.domain.card import Card, Color, Prices, Rarity
from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.tui.widgets.deck_view import DeckView


def _card(name: str) -> Card:
    return Card(
        scryfall_id=f"id-{name}", name=name, mana_cost="{1}{G}", cmc=2.0,
        type_line="Creature — Bear",
        oracle_text=(
            "Trample. When this creature enters, draw a card. "
            "Whenever another creature you control dies, put a +1/+1 "
            "counter on this creature. It can't be blocked by Wolves."
        ),
        colors=(Color.GREEN,), color_identity=(Color.GREEN,),
        power="2", toughness="2", set_code="tst", rarity=Rarity.COMMON,
        legalities={}, image_uri=None, prices=Prices(usd=1.0),
        layout="normal", keywords=(),
    )


def _view(lines: int, height: int, width: int = 40) -> DeckView:
    dv = DeckView()
    dv.buffer = Buffer.from_text("\n".join(f"1 Bear {i}" for i in range(lines)) + "\n")
    dv.resolved_cards = {f"Bear {i}": _card(f"Bear {i}") for i in range(lines)}
    dv._size_override = Size(width, height)  # type: ignore[attr-defined]
    return dv


def test_expansion_near_bottom_is_fully_rendered(monkeypatch) -> None:
    dv = _view(lines=20, height=25)
    monkeypatch.setattr(
        type(dv), "size", property(lambda self: self._size_override)  # type: ignore[attr-defined]
    )
    # Cursor on the second-to-last card: its rules text must stay on screen.
    dv.cursor = Cursor(row=18, col=0)
    plain = dv.render().plain
    rows = plain.rstrip("\n").split("\n")
    assert len(rows) <= 25
    cursor_idx = next(i for i, r in enumerate(rows) if "Bear 18" in r)
    expansion = rows[cursor_idx + 1:]
    assert any("Trample" in r for r in expansion)
    assert any("Wolves" in r for r in expansion)  # last wrapped line visible


def test_cursor_row_keeps_scrolloff_below(monkeypatch) -> None:
    dv = _view(lines=60, height=20)
    dv.auto_expand = False
    monkeypatch.setattr(
        type(dv), "size", property(lambda self: self._size_override)  # type: ignore[attr-defined]
    )
    dv.cursor = Cursor(row=17, col=0)
    rows = dv.render().plain.rstrip("\n").split("\n")
    cursor_idx = next(i for i, r in enumerate(rows) if "Bear 17" in r)
    assert cursor_idx <= 20 - 1 - 3
