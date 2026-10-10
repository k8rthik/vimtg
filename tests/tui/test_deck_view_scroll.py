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


def test_wheel_moves_window_and_drags_cursor(monkeypatch) -> None:
    dv = _view(lines=60, height=20)
    dv.auto_expand = False
    monkeypatch.setattr(
        type(dv), "size", property(lambda self: self._size_override)  # type: ignore[attr-defined]
    )
    dv.cursor = Cursor(row=0, col=0)
    dv.render()
    requests: list[int] = []
    monkeypatch.setattr(dv, "post_message", lambda msg: requests.append(msg.row))
    dv.wheel(3)
    assert dv._scroll_offset == 3
    # Cursor row 0 fell out of the scrolloff band, so the view asks for row 6
    assert requests == [6]
    dv.wheel(-3)
    assert dv._scroll_offset == 0
    # The view reasons from its own outstanding request (row 6), which is
    # inside the band at offset 0 — no second request
    assert requests == [6]


def test_cursor_band_none_before_render() -> None:
    dv = _view(lines=10, height=5)
    assert dv.cursor_band() is None
    assert DeckView().cursor_band() is None


def test_cursor_band_respects_scrolloff_mid_buffer(monkeypatch) -> None:
    dv = _view(lines=60, height=20)
    dv.auto_expand = False
    monkeypatch.setattr(
        type(dv), "size", property(lambda self: self._size_override)  # type: ignore[attr-defined]
    )
    dv.cursor = Cursor(row=30, col=0)
    dv.render()
    start, end = dv._window  # type: ignore[misc]
    assert start > 0 and end < 60
    assert dv.cursor_band() == (start + 3, end - 1 - 3)


def test_cursor_band_reaches_buffer_ends(monkeypatch) -> None:
    dv = _view(lines=10, height=20)
    dv.auto_expand = False
    monkeypatch.setattr(
        type(dv), "size", property(lambda self: self._size_override)  # type: ignore[attr-defined]
    )
    dv.cursor = Cursor(row=4, col=0)
    dv.render()
    # The whole deck fits: no margin at either end
    assert dv.cursor_band() == (0, 9)
