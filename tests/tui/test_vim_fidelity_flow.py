"""Vim operator and motion fidelity, driven key by key through MainScreen.

Each test replays the exact key sequence from the audit that found the
bug, with the crash net disabled so a regression fails loudly. Line
numbers refer to the sample deck below (1-based, as G counts them).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.editor.cmdline_history import CommandHistory, history_path
from vimtg.editor.modes import Mode
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.deck_view import DeckView
from vimtg.tui.widgets.help_panel import HelpPanel
from vimtg.tui.widgets.search_results import SearchResults

FIXTURES = Path(__file__).parent.parent / "fixtures"

# Canonical layout (opening it changes nothing). Lines:
#  1 // Deck: Burn      6 4 Goblin Guide          11 4 Lightning Bolt
#  2 // Format: modern  7 4 Monastery Swiftspear  12 4 Searing Blaze
#  3 // Tags:           8 2 Eidolon of the...     13 4 Skullcrack
#  4                    9                         14
#  5 // Creature       10 // Instant              15 // Land
#                                                 16 20 Mountain
DECK = (
    "// Deck: Burn\n// Format: modern\n// Tags:\n\n"
    "// Creature\n4 Goblin Guide\n4 Monastery Swiftspear\n"
    "2 Eidolon of the Great Revel\n\n"
    "// Instant\n4 Lightning Bolt\n4 Searing Blaze\n4 Skullcrack\n\n"
    "// Land\n20 Mountain\n"
)


def _keys(seq: str) -> list[str]:
    """'12G d8G' -> ['1', '2', 'G', 'd', '8', 'G']. Spaces only separate;
    <Space> types one. <CR> <Esc> <BS> <Up> <Down> <C-w> <C-u> <C-b>
    <C-e> <C-a> <C-x> <C-o> <Tab> <Left> name the other named keys."""
    named = {
        "<CR>": "enter", "<Esc>": "escape", "<BS>": "backspace",
        "<Up>": "up", "<Down>": "down", "<Left>": "left", "<Right>": "right",
        "<C-w>": "ctrl_w", "<C-u>": "ctrl_u", "<C-b>": "ctrl_b", "<C-e>": "ctrl_e",
        "<Space>": " ", "<C-a>": "ctrl_a", "<C-x>": "ctrl_x", "<C-o>": "ctrl_o",
        "<Tab>": "tab", "<C-r>": "ctrl_r",
    }
    out: list[str] = []
    i = 0
    while i < len(seq):
        if seq[i] == "<":
            end = seq.index(">", i)
            out.append(named[seq[i:end + 1]])
            i = end + 1
            continue
        if seq[i] != " ":
            out.append(seq[i])
        i += 1
    return out


def _reraise(exc: Exception) -> None:
    raise exc


def _feed(scr: MainScreen, seq: str) -> None:
    scr.recover_from_crash = _reraise  # type: ignore[method-assign]
    for key in _keys(seq):
        scr._process_key(key)


def _lines(scr: MainScreen) -> list[str]:
    buf = scr._state.buffer
    return [buf.get_line(i).text for i in range(buf.line_count())]


def _cards(scr: MainScreen) -> list[str]:
    buf = scr._state.buffer
    return [buf.get_line(i).text for i in range(buf.line_count()) if buf.is_card_line(i)]


def _deck(tmp_path: Path, text: str = DECK) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(text, encoding="utf-8")
    return path


def _screen(app: VimTGApp) -> MainScreen:
    scr = app.screen
    assert isinstance(scr, MainScreen)
    return scr


def _message(scr: MainScreen) -> str:
    return scr.query_one("#command-line", CommandLine).message


# ── (a) counted G after an operator ───────────────────────────────


class TestCountedGOperator:
    @pytest.mark.asyncio
    async def test_d8g_from_line_12_stops_at_line_8(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "12G d8G")
            cards = _cards(scr)
            # Lines 8-12 went (Eidolon .. Searing Blaze); the rest stays
            assert "4 Skullcrack" in cards
            assert "20 Mountain" in cards
            assert not any("Eidolon" in c or "Searing" in c for c in cards)
            assert "4 Monastery Swiftspear" in cards

    @pytest.mark.asyncio
    async def test_y5g_yanks_through_line_5_and_dg_runs_to_the_end(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "7G y5G")
            assert scr._state.registers.unnamed.content == (
                "// Creature", "4 Goblin Guide", "4 Monastery Swiftspear",
            )
            _feed(scr, "13G dG")
            assert _cards(scr)[-1] == "4 Searing Blaze"
            assert "20 Mountain" not in _cards(scr)

    @pytest.mark.asyncio
    async def test_d3gg_counts_like_d3g(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "7G d6gg")
            assert "4 Goblin Guide" not in _cards(scr)
            assert "4 Monastery Swiftspear" not in _cards(scr)
            assert _lines(scr)[0] == "// Deck: Burn"


# ── (b) exclusive motions ─────────────────────────────────────────


class TestExclusiveMotions:
    @pytest.mark.asyncio
    async def test_dw_deletes_one_card(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G dw")
            assert "4 Goblin Guide" not in _cards(scr)
            assert "4 Monastery Swiftspear" in _cards(scr)

    @pytest.mark.asyncio
    async def test_dw_on_last_card_of_section_keeps_next_header(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "8G dw")
            assert "// Instant" in _lines(scr)
            assert "4 Lightning Bolt" in _cards(scr)
            assert not any("Eidolon" in c for c in _cards(scr))

    @pytest.mark.asyncio
    async def test_cw_changes_one_card(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G cw")
            assert scr._state.mode_mgr.current == Mode.INSERT
            assert "4 Monastery Swiftspear" in _cards(scr)
            assert "4 Goblin Guide" not in _cards(scr)

    @pytest.mark.asyncio
    async def test_d_brace_stops_at_the_section_boundary(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "7G d}")
            lines = _lines(scr)
            assert "// Instant" in lines
            assert "4 Lightning Bolt" in _cards(scr)
            assert "4 Goblin Guide" in _cards(scr)
            assert "4 Monastery Swiftspear" not in _cards(scr)
            assert not any("Eidolon" in c for c in _cards(scr))

    @pytest.mark.asyncio
    async def test_d_open_brace_deletes_the_cards_above_in_the_section(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "13G d{")
            assert _cards(scr)[3:] == ["4 Skullcrack", "20 Mountain"]
            assert "// Instant" in _lines(scr)


# ── (c) dot-repeat ────────────────────────────────────────────────


class TestDotRepeat:
    @pytest.mark.asyncio
    async def test_visual_line_delete_repeats_two_lines(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "11G Vjd")
            assert _cards(scr)[3] == "4 Skullcrack"
            _feed(scr, "6G .")
            assert _cards(scr)[:2] == ["2 Eidolon of the Great Revel", "4 Skullcrack"]

    @pytest.mark.asyncio
    async def test_put_repeats(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G yy p .")
            assert _cards(scr)[:3] == ["4 Goblin Guide"] * 3

    @pytest.mark.asyncio
    async def test_category_and_comment_repeat(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "11G A burn<CR> j .")
            buf = scr._state.buffer
            assert buf.comment_at(10) == "burn"
            assert buf.comment_at(11) == "burn"
            _feed(scr, "j gc removal<CR>")
            row = scr._state.cursor.row
            _feed(scr, "k .")
            buf = scr._state.buffer
            assert buf.category_at(row) == "removal"
            assert buf.category_at(scr._state.cursor.row) == "removal"

    @pytest.mark.asyncio
    async def test_line_edit_repeats(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            # i opens with the whole line; Ctrl-U clears it, then retype
            _feed(scr, "6G i <C-u>1<Space>Goblin<Space>Guide<CR>")
            assert _cards(scr)[0] == "1 Goblin Guide"
            _feed(scr, "j .")
            assert _cards(scr)[1] == "1 Goblin Guide"

    @pytest.mark.asyncio
    async def test_substitute_repeats_on_the_cursor_line(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "11G :s/^4/3/<CR> j .")
            assert _cards(scr)[3:5] == ["3 Lightning Bolt", "3 Searing Blaze"]


@pytest.fixture
def card_repo(db_factory):  # type: ignore[no-untyped-def]
    repo = CardRepository(db_factory())
    data = json.loads((FIXTURES / "scryfall_sample.json").read_text(encoding="utf-8"))
    repo.bulk_insert([Card.from_scryfall(d) for d in data])
    return repo


def _pick(scr: MainScreen, repo: CardRepository, name: str) -> None:
    """Stand in for the async search: offer `name` and press Enter."""
    card = repo.get_by_name(name)
    assert card is not None
    scr._update_search_results([card])
    _feed(scr, "<CR>")
    assert scr.query_one("#search-results", SearchResults).display is False


class TestDotRepeatInserts:
    @pytest.mark.asyncio
    async def test_open_line_card_repeats_not_the_older_dd(
        self, tmp_path: Path, card_repo: CardRepository
    ) -> None:
        """9Gdd o eidolon<CR> j . used to replay the old dd."""
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            scr.card_repo = card_repo
            _feed(scr, "8G dd")
            before = len(_cards(scr))
            _feed(scr, "o")
            _pick(scr, card_repo, "Eidolon of the Great Revel")
            assert len(_cards(scr)) == before + 1
            _feed(scr, "j .")
            assert len(_cards(scr)) == before + 1  # no second dd
            eidolon = [c for c in _cards(scr) if "Eidolon" in c]
            assert eidolon == ["2 Eidolon of the Great Revel"]  # added twice

    @pytest.mark.asyncio
    async def test_counted_open_repeats_its_copies(
        self, tmp_path: Path, card_repo: CardRepository
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            scr.card_repo = card_repo
            _feed(scr, "6G 2o")
            _pick(scr, card_repo, "Rest in Peace")
            _feed(scr, ".")
            assert "4 Rest in Peace" in _cards(scr)

    @pytest.mark.asyncio
    async def test_cc_with_card_repeats_delete_and_insert(
        self, tmp_path: Path, card_repo: CardRepository
    ) -> None:
        """cc fire<CR> 12G . used to delete without re-inserting."""
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            scr.card_repo = card_repo
            _feed(scr, "11G cc")
            _pick(scr, card_repo, "Fire // Ice")
            assert "4 Lightning Bolt" not in _cards(scr)
            assert "1 Fire // Ice" in _cards(scr)
            _feed(scr, "11G .")  # now Searing Blaze
            cards = _cards(scr)
            assert "4 Searing Blaze" not in cards
            assert "2 Fire // Ice" in cards


# ── (d) visual keys act on the selection ──────────────────────────


class TestVisualSelection:
    @pytest.mark.asyncio
    async def test_vjzs_moves_both_cards_and_exits_visual(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "11G Vjzs")
            s = scr._state
            assert s.mode_mgr.current == Mode.NORMAL
            assert s.visual_anchor is None
            text = s.buffer.to_text()
            assert "SB:\n    4 Lightning Bolt\n    4 Searing Blaze" in text
            assert "\n4 Skullcrack" in text
            _feed(scr, "u")
            assert s.buffer.to_text() == DECK  # one undo step

    @pytest.mark.asyncio
    async def test_vj_plus_increments_both(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G Vj3+")
            assert scr._state.mode_mgr.current == Mode.NORMAL
            assert _cards(scr)[:3] == [
                "7 Goblin Guide", "7 Monastery Swiftspear", "2 Eidolon of the Great Revel",
            ]
            _feed(scr, "11G .")  # repeats on two lines from the cursor
            assert _cards(scr)[3:5] == ["7 Lightning Bolt", "7 Searing Blaze"]

    @pytest.mark.asyncio
    async def test_vj_minus_deletes_cards_reaching_zero(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "7G Vj2-")
            assert _cards(scr)[:2] == ["4 Goblin Guide", "2 Monastery Swiftspear"]
            assert not any("Eidolon" in c for c in _cards(scr))

    @pytest.mark.asyncio
    async def test_vjx_deletes_the_selection(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G Vjx")
            assert scr._state.mode_mgr.current == Mode.NORMAL
            assert _cards(scr)[0] == "2 Eidolon of the Great Revel"

    @pytest.mark.asyncio
    async def test_visual_board_out_boards_every_card(self, tmp_path: Path) -> None:
        text = DECK + "\nSB: 2 Rest in Peace\n\nVS: Tron\n"
        app = VimTGApp(deck_path=_deck(tmp_path, text))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "11G Vjzo")
            assert scr._state.mode_mgr.current == Mode.NORMAL
            lines = _lines(scr)
            assert "    -4 Lightning Bolt" in lines
            assert "    -4 Searing Blaze" in lines


# ── (e) command-line editing and history ──────────────────────────


class TestCommandLine:
    @pytest.mark.asyncio
    async def test_up_recalls_history_and_down_restores_typed(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            cl = scr.query_one("#command-line", CommandLine)
            _feed(scr, ":sort<CR> :cats<CR> :")
            _feed(scr, "<Up>")
            assert cl.text == "cats"
            _feed(scr, "<Up>")
            assert cl.text == "sort"
            _feed(scr, "<Down> <Down>")
            assert cl.text == ""
            _feed(scr, "so<Up>")
            assert cl.text == "sort"  # prefix match skips :cats
            _feed(scr, "<CR>")
            assert scr._state.mode_mgr.current == Mode.NORMAL
            _feed(scr, "<Space>a")  # runs :analytics for you: not history
            assert scr._state.cmd_history.entries("cmd") == ("cats", "sort")

    @pytest.mark.asyncio
    async def test_history_persists_across_sessions(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            _feed(_screen(app), ":cats<CR> /bolt<CR>")
        assert history_path().exists()
        loaded = CommandHistory.load()
        assert loaded.entries("cmd")[-1] == "cats"
        assert loaded.entries("search")[-1] == "bolt"
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, ":<Up>")
            assert scr.query_one("#command-line", CommandLine).text == "cats"

    @pytest.mark.asyncio
    async def test_line_editing_keys(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            cl = scr.query_one("#command-line", CommandLine)
            _feed(scr, ":set<Space>foo<Space>bar<C-w>")
            assert cl.text == "set foo "
            _feed(scr, "<C-b>")
            assert cl.cursor_pos == 0
            _feed(scr, "<C-e>")
            assert cl.cursor_pos == len("set foo ")
            _feed(scr, "<Left><Left><C-u>")
            assert cl.text == "o "
            _feed(scr, "<Esc>")

    @pytest.mark.asyncio
    async def test_backspace_on_empty_line_leaves_command_mode(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, ":w<BS>")
            assert scr._state.mode_mgr.current == Mode.COMMAND
            _feed(scr, "<BS>")
            assert scr._state.mode_mgr.current == Mode.NORMAL
            _feed(scr, "/<BS>")
            assert scr._state.mode_mgr.current == Mode.NORMAL

    @pytest.mark.asyncio
    async def test_card_search_prompt_has_line_editing(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G o lightning<Space>bolt<C-w>")
            assert scr._state.search_query == "lightning "
            _feed(scr, "<C-u>")
            assert scr._state.search_query == ""
            _feed(scr, "<Esc>")


# ── (f) ex commands ───────────────────────────────────────────────


class TestExCommands:
    @pytest.mark.asyncio
    async def test_colon_number_goes_to_line(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, ":12<CR>")
            assert scr._state.cursor.row == 11
            assert not scr.query_one("#command-line", CommandLine).error
            _feed(scr, ":$<CR>")
            assert scr._state.cursor.row == len(_lines(scr)) - 1

    @pytest.mark.asyncio
    async def test_edit_opens_another_deck_and_keeps_registers(
        self, tmp_path: Path
    ) -> None:
        other = tmp_path / "other.deck"
        other.write_text(
            "// Deck: Other\n// Format: modern\n// Tags:\n\n// Land\n4 Island\n",
            encoding="utf-8",
        )
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            # Spaces only separate in _keys: type them as <Space>, so a
            # Windows path (C:\...) is not glued onto the command name
            target = str(other).replace(" ", "<Space>")
            _feed(scr, f"6G yy dd :e<Space>{target}<CR>")
            assert _screen(app) is scr  # refused: unsaved changes
            assert "E37" in _message(scr)
            _feed(scr, f":e!<Space>{target}<CR>")
            await pilot.pause()
            new = _screen(app)
            assert new is not scr
            assert new.file_path == other
            assert "4 Island" in _cards(new)
            assert new._state.modified is False
            _feed(new, "p")
            assert "4 Goblin Guide" in _cards(new)

    @pytest.mark.asyncio
    async def test_edit_bang_reloads_from_disk(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            _feed(_screen(app), "6G dd :e!<CR>")
            await pilot.pause()
            assert "4 Goblin Guide" in _cards(_screen(app))

    @pytest.mark.asyncio
    async def test_undo_redo_registers_and_marks(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G dd u")
            assert "4 Goblin Guide" in _cards(scr)
            _feed(scr, "<C-r>")
            assert "4 Goblin Guide" not in _cards(scr)
            _feed(scr, "ma :marks<CR>")
            assert "'a 6 4 Monastery Swiftspear" in _message(scr)
            _feed(scr, ":reg<CR>")
            assert '"" 4 Goblin Guide' in _message(scr)


# ── (g) z scroll, zone checks, registers ──────────────────────────


class TestZAndRegisters:
    @pytest.mark.asyncio
    async def test_zz_zt_zb_scroll_without_moving_the_cursor(
        self, tmp_path: Path
    ) -> None:
        many = DECK + "".join(f"1 Card {i}\n" for i in range(60))
        app = VimTGApp(deck_path=_deck(tmp_path, many))
        async with app.run_test(size=(100, 20)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            dv = scr.query_one("#deck-view", DeckView)
            _feed(scr, "40G zt")
            await pilot.pause()
            assert scr._state.cursor.row == 39
            top = dv._scroll_offset
            _feed(scr, "zb")
            await pilot.pause()
            bottom = dv._scroll_offset
            _feed(scr, "zz")
            await pilot.pause()
            center = dv._scroll_offset
            assert bottom < center < top
            assert scr._state.cursor.row == 39
            assert scr._state.buffer.to_text() == many  # zones untouched

    @pytest.mark.asyncio
    async def test_zc_refused_outside_commander(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "11G zc")
            assert "no command zone" in _message(scr)
            assert scr._state.buffer.to_text() == DECK

    @pytest.mark.asyncio
    async def test_black_hole_delete_keeps_the_unnamed_register(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, '6G yy 11G "_dd')
            assert "4 Lightning Bolt" not in _cards(scr)
            assert scr._state.registers.unnamed.content == ("4 Goblin Guide",)
            _feed(scr, "dd")  # a plain dd afterwards fills it as usual
            assert scr._state.registers.unnamed.content == ("4 Searing Blaze",)

    @pytest.mark.asyncio
    async def test_clipboard_register_copies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The copy goes through the TUI's clipboard path (native tool,
        else OSC 52 via Textual), the same one :clipboard uses."""
        from vimtg.services.clipboard import CopyResult

        copied: list[str] = []

        def fake_copy(text: str, **_: object) -> CopyResult:
            copied.append(text)
            return CopyResult(True, "xclip")

        monkeypatch.setattr("vimtg.tui.screens.main_screen.copy_to_clipboard", fake_copy)
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, '6G "+yy')
            assert copied == ["4 Goblin Guide\n"]
            _feed(scr, '11G "*p')  # * and + are one register
            assert _cards(scr).count("4 Goblin Guide") == 2
            _feed(scr, "yy")  # other registers never touch the clipboard
            assert len(copied) == 1
            _feed(scr, ":6,7g/./y<Space>+<CR>")
            assert copied[-1] == "4 Goblin Guide\n4 Monastery Swiftspear\n"
            _feed(scr, ":g/swiftspear/y<Space>*<CR>")
            assert copied[-1] == "4 Monastery Swiftspear\n"


# ── (h) ? search, * #, help keys ──────────────────────────────────


class TestSearchAndHelp:
    @pytest.mark.asyncio
    async def test_question_mark_searches_backward_and_n_follows(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "13G ?^4<CR>")
            assert scr._state.cursor.row == 11  # Searing Blaze, above
            _feed(scr, "n")
            assert scr._state.cursor.row == 10  # still backward
            _feed(scr, "N")
            assert scr._state.cursor.row == 11
            assert scr.query_one("#help-panel", HelpPanel).display is False

    @pytest.mark.asyncio
    async def test_star_and_hash_find_the_card_under_the_cursor(
        self, tmp_path: Path
    ) -> None:
        text = DECK + "\nSB: 2 Lightning Bolt\nSB: 1 Lightning Bolt Jr\n"
        app = VimTGApp(deck_path=_deck(tmp_path, text))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "11G *")
            row = scr._state.cursor.row
            assert scr._state.buffer.get_line(row).text == "SB: 2 Lightning Bolt"
            _feed(scr, "*")  # wraps, skipping the Jr card
            assert scr._state.cursor.row == 10
            _feed(scr, "#")
            assert scr._state.cursor.row == row

    @pytest.mark.asyncio
    async def test_f1_and_help_open_the_help_screen(self, tmp_path: Path) -> None:
        from vimtg.tui.screens.help_screen import HelpScreen

        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("f1")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("q")
            await pilot.pause()
            _feed(_screen(app), ":help<CR>")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
