"""Onboarding through the real app: the new-deck wizard, saving without
scaffold noise, first-run tips, :messages, sticky errors, recent decks."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.config import app_state
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.greeter import GreeterScreen, GreeterView
from vimtg.tui.screens.help_screen import HelpScreen
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.screens.new_deck import NewDeckInfo, NewDeckScreen, format_matches
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.status_line import StatusLine
from vimtg.tui.widgets.tips_panel import TipsPanel


def _main(app: VimTGApp) -> MainScreen:
    for screen in reversed(app.screen_stack):
        if isinstance(screen, MainScreen):
            return screen
    raise AssertionError("no MainScreen")


async def _type(pilot, text: str) -> None:  # type: ignore[no-untyped-def]
    for ch in text:
        await pilot.press("space" if ch == " " else ch)


def _cl(screen: MainScreen) -> CommandLine:
    return screen.query_one("#command-line", CommandLine)


# ── New-deck wizard ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_greeter_new_prompts_then_w_names_file_after_deck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    app = VimTGApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, NewDeckScreen)
        await _type(pilot, "Mono Red")
        await pilot.press("enter")
        await _type(pilot, "mod")
        await pilot.press("tab")  # completes to "modern"
        await pilot.press("enter")
        await pilot.pause()
        screen = _main(app)
        assert app.screen is screen
        text = screen._state.buffer.to_text()
        assert "// Deck: Mono Red" in text
        assert "// Format: modern" in text
        # The answers only fill in the scaffold: nothing is unsaved yet
        assert screen._state.modified is False

        await _type(pilot, ":w")
        await pilot.press("enter")
        await pilot.pause()
        saved = tmp_path / "mono-red.deck"
        assert screen.file_path == saved
        written = saved.read_text(encoding="utf-8")
        assert written.startswith("// Deck: Mono Red\n// Format: modern\n")
        # The empty // Tags: scaffold is display-only
        assert "// Tags:" not in written


@pytest.mark.asyncio
async def test_q_after_the_wizard_quits_without_unsaved_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deck made from the greeter and never edited holds only its
    scaffold (name, format, empty zone blocks): :q quits, as vim's :q
    on an untouched :enew buffer does."""
    monkeypatch.chdir(tmp_path)
    app = VimTGApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        await _type(pilot, "Mono Red")
        await pilot.press("enter")
        await _type(pilot, "modern")
        await pilot.press("enter")
        await pilot.pause()
        screen = _main(app)
        await _type(pilot, ":q")
        await pilot.press("enter")
        await pilot.pause()
        assert "Unsaved" not in _cl(screen).message
        assert app._exit
    assert list(tmp_path.glob("*.deck")) == []


@pytest.mark.asyncio
async def test_undoing_the_wizard_answers_is_a_change(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=tmp_path / "new.deck")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _type(pilot, "burn")
        await pilot.press("enter")
        await pilot.press("enter")
        await pilot.pause()
        screen = _main(app)
        assert screen._state.modified is False
        await pilot.press("u")
        await pilot.pause()
        assert screen._state.modified is True


@pytest.mark.asyncio
async def test_wizard_escape_skips_and_leaves_buffer(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=tmp_path / "new.deck")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, NewDeckScreen)
        await pilot.press("escape")
        await pilot.pause()
        screen = _main(app)
        assert app.screen is screen
        assert screen._state.modified is False
        assert "// Deck:\n" in screen._state.buffer.to_text()


@pytest.mark.asyncio
async def test_missing_file_suggests_its_name_and_asks_format(tmp_path: Path) -> None:
    """`vimtg burn.deck` (new file) prefills "burn"; Enter accepts it."""
    app = VimTGApp(deck_path=tmp_path / "burn.deck")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, NewDeckScreen)
        assert wizard.name_text == "burn"
        await pilot.press("enter")
        await _type(pilot, "pauper")
        await pilot.press("enter")
        await pilot.pause()
        text = _main(app)._state.buffer.to_text()
        assert "// Deck: burn" in text
        assert "// Format: pauper" in text


@pytest.mark.asyncio
async def test_vimtg_new_without_format_asks_only_format(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("// Deck: Burn\n\nDCK:\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, NewDeckScreen)
        assert wizard.field == "format"


@pytest.mark.asyncio
async def test_commander_answer_adds_cmd_block(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=tmp_path / "edh.deck")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await _type(pilot, "commander")
        await pilot.press("enter")
        await pilot.pause()
        lines = _main(app)._state.buffer.to_text().splitlines()
        assert "CMD:" in lines
        assert lines.index("CMD:") < lines.index("DCK:")


@pytest.mark.asyncio
async def test_deck_with_cards_or_identity_never_prompts(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)


class TestNewDeckScreenKeys:
    def test_unknown_format_is_refused(self) -> None:
        wizard = NewDeckScreen(name="X", fmt="")
        results: list[NewDeckInfo | None] = []
        wizard.dismiss = results.append  # type: ignore[assignment,method-assign]
        for ch in "zzz":
            wizard.feed(ch)
        wizard.feed("enter")
        assert results == []
        assert "Unknown format" in wizard.error

    def test_unique_prefix_is_accepted(self) -> None:
        wizard = NewDeckScreen(name="X", fmt="")
        results: list[NewDeckInfo | None] = []
        wizard.dismiss = results.append  # type: ignore[assignment,method-assign]
        for ch in "pione":
            wizard.feed(ch)
        wizard.feed("enter")
        assert results == [NewDeckInfo(name="X", fmt="pioneer")]

    def test_alias_is_saved_as_the_format_key(self) -> None:
        wizard = NewDeckScreen(name="X", fmt="")
        results: list[NewDeckInfo | None] = []
        wizard.dismiss = results.append  # type: ignore[assignment,method-assign]
        for ch in "EDH":
            wizard.feed(ch)
        wizard.feed("enter")
        assert results == [NewDeckInfo(name="X", fmt="commander")]

    def test_tab_cycles_matches(self) -> None:
        wizard = NewDeckScreen(name="X", fmt="")
        wizard.feed("p")
        wizard.feed("tab")
        first = wizard.fmt_text
        wizard.feed("tab")
        assert {first, wizard.fmt_text} <= set(format_matches("p"))
        assert first != wizard.fmt_text

    def test_blank_format_is_allowed(self) -> None:
        wizard = NewDeckScreen(name="", fmt="")
        results: list[NewDeckInfo | None] = []
        wizard.dismiss = results.append  # type: ignore[assignment,method-assign]
        wizard.feed("enter")  # name -> format
        wizard.feed("enter")
        assert results == [NewDeckInfo(name="", fmt="")]

    def test_ctrl_u_clears_the_prefilled_name(self) -> None:
        """`vimtg build.deck` prefills 'build': Ctrl-U clears it so the
        typed name replaces it instead of being appended."""
        wizard = NewDeckScreen(suggested_name="build")
        results: list[NewDeckInfo | None] = []
        wizard.dismiss = results.append  # type: ignore[assignment,method-assign]
        wizard.feed("ctrl_u")
        for ch in "Krenko Tokens":
            wizard.feed(ch)
        wizard.feed("enter")
        wizard.feed("enter")
        assert results == [NewDeckInfo(name="Krenko Tokens", fmt="")]

    def test_ctrl_w_deletes_the_last_word(self) -> None:
        wizard = NewDeckScreen(suggested_name="Krenko Tokens")
        wizard.feed("ctrl_w")
        assert wizard.name_text == "Krenko "
        wizard.feed("down")
        for ch in "pioneer":
            wizard.feed(ch)
        wizard.feed("ctrl_w")
        assert wizard.fmt_text == ""

    def test_common_formats_listed_first(self) -> None:
        assert format_matches("")[:3] == ["standard", "pioneer", "modern"]


# ── Saving hand-written files ───────────────────────────────────


@pytest.mark.asyncio
async def test_saving_hand_written_file_adds_no_metadata(tmp_path: Path) -> None:
    deck = tmp_path / "list.deck"
    original = "4 Lightning Bolt\n4 Goblin Guide\n"
    deck.write_text(original, encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = _main(app)
        assert "// Tags:" in screen._state.buffer.to_text()  # shown in the editor
        screen._execute_ex("w")
        await pilot.pause()
    assert deck.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_filled_scaffold_line_is_saved(tmp_path: Path) -> None:
    deck = tmp_path / "list.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = _main(app)
        screen._execute_ex("dtag burn")
        screen._execute_ex("w")
        await pilot.pause()
    written = deck.read_text(encoding="utf-8")
    assert "// Tags: burn" in written
    assert "// Deck:" not in written
    assert "// Format:" not in written


# ── Help and hints ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_help_opens_on_getting_started(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        _main(app)._execute_ex("help")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        body = str(app.screen.query_one("#help-body").render())
        assert body.index("GETTING STARTED") < body.index("COUNTS")


# ── First-run tips ──────────────────────────────────────────────


def _tips(screen: MainScreen) -> TipsPanel:
    return screen.query_one("#tips-panel", TipsPanel)


@pytest.mark.asyncio
async def test_tips_show_for_empty_deck_and_esc_hides(tmp_path: Path) -> None:
    deck = tmp_path / "empty.deck"
    deck.write_text("// Deck: E\n// Format: modern\n\nDCK:\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = _main(app)
        assert _tips(screen).display is True
        assert ":w" in str(_tips(screen).render())
        await pilot.press("escape")
        await pilot.pause()
        assert _tips(screen).display is False
        screen._execute_ex("tips")  # brings them back
        screen._sync_widgets()
        assert _tips(screen).display is True


@pytest.mark.asyncio
async def test_tips_stay_after_the_first_card_until_the_first_write(tmp_path: Path) -> None:
    """+/- and :w matter most right after the first card goes in, so
    the tips stay up until the deck is first written."""
    deck = tmp_path / "empty.deck"
    deck.write_text("// Deck: E\n// Format: modern\n\nDCK:\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = _main(app)
        from textual.events import Paste

        screen.post_message(Paste("4 Lightning Bolt\n"))
        await pilot.pause()
        assert "Lightning Bolt" in screen._state.buffer.to_text()
        assert _tips(screen).display is True
        screen._execute_ex("w")
        screen._sync_widgets()
        await pilot.pause()
        assert _tips(screen).display is False


@pytest.mark.asyncio
async def test_tips_hidden_once_deck_has_cards(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert _tips(_main(app)).display is False


@pytest.mark.asyncio
async def test_tips_off_is_remembered(tmp_path: Path) -> None:
    deck = tmp_path / "empty.deck"
    deck.write_text("// Deck: E\n// Format: modern\n\nDCK:\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        _main(app)._execute_ex("tips off")
        await pilot.pause()
        assert _tips(_main(app)).display is False
    assert app_state.tips_dismissed() is True

    again = VimTGApp(deck_path=deck)
    async with again.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert _tips(_main(again)).display is False
        _main(again)._execute_ex("tips on")
        _main(again)._sync_widgets()
        assert _tips(_main(again)).display is True
    assert app_state.tips_dismissed() is False


# ── Messages ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_error_survives_motion_and_goes_with_next_key(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("4 Lightning Bolt\n4 Goblin Guide\n4 Monastery Swiftspear\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = _main(app)
        await _type(pilot, ":nosuchcmd")
        await pilot.press("enter")
        await pilot.pause()
        assert "E492" in _cl(screen).message
        await pilot.press("j")
        await pilot.press("k")
        assert "E492" in _cl(screen).message
        await pilot.press("x")  # an edit, not a motion
        assert "E492" not in _cl(screen).message


@pytest.mark.asyncio
async def test_status_message_still_clears_on_next_key(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("4 Lightning Bolt\n4 Goblin Guide\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = _main(app)
        _cl(screen).set_message("Written: burn.deck")
        await pilot.press("j")
        assert _cl(screen).message == ""


@pytest.mark.asyncio
async def test_messages_lists_history(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = _main(app)
        _cl(screen).set_message("E: Write failed: disk full", error=True)
        await pilot.press("x")
        await _type(pilot, ":messages")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        body = str(app.screen.query_one("#help-body").render())
        assert "Write failed: disk full" in body
        await pilot.press("q")
        await pilot.pause()
        screen._execute_ex("messages clear")
        screen._execute_ex("messages")
        await pilot.pause()
        assert "(no messages)" in str(app.screen.query_one("#help-body").render())


# ── Macro recording indicator ───────────────────────────────────


@pytest.mark.asyncio
async def test_recording_shown_up_front_with_how_to_stop(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        screen = _main(app)
        await pilot.press("q")
        await pilot.press("a")
        await pilot.pause()
        status = screen.query_one("#status-line", StatusLine).render().plain
        # Near the front, so a narrow terminal cannot cut it off
        assert status.index("recording @a (q stops)") < status.index("burn.deck")
        await pilot.press("q")
        await pilot.pause()
        status = screen.query_one("#status-line", StatusLine).render().plain
        assert "recording" not in status


# ── Recent decks from any directory ─────────────────────────────


@pytest.mark.asyncio
async def test_greeter_lists_recent_decks_from_other_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    far = elsewhere / "far.deck"
    far.write_text("4 Lightning Bolt\n", encoding="utf-8")
    here = tmp_path / "here"
    here.mkdir()
    (here / "local.deck").write_text("4 Shock\n", encoding="utf-8")

    first = VimTGApp(deck_path=far)  # opening records it
    async with first.run_test(size=(100, 40)) as pilot:
        await pilot.pause()

    monkeypatch.chdir(here)
    app = VimTGApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, GreeterScreen)
        menu = app.screen.query_one(GreeterView).render().plain
        assert "far.deck" in menu
        assert "elsewhere" in menu  # where it lives
        assert "local.deck" in menu
        await pilot.press("1")
        await pilot.pause()
        assert _main(app).file_path == far
