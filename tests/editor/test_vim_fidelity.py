"""Engine-level tests for vim operator, register, ex-command, and
command-line fidelity (the key-by-key flows live in
tests/tui/test_vim_fidelity_flow.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.cmdline_history import CommandHistory
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.command_handlers.global_cmd import cmd_global
from vimtg.editor.command_handlers.line_cmds import cmd_edit
from vimtg.editor.command_handlers.substitute import cmd_substitute, split_delimited
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand, parse_command
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult, ParsedAction
from vimtg.editor.line_buffer import LineBuffer
from vimtg.editor.marks import MarkStore
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.operators import execute_operator, resolve_line_range
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    confirm_card_search,
    handle_command,
    handle_command_special,
    handle_mode_switch,
    handle_normal_special,
    handle_operator,
)
from vimtg.services.history_service import HistoryService

# Rows (0-based):
#  0 // Creature   4 // Instant         8 // Land
#  1 4 Goblin      5 4 Lightning Bolt   9 20 Mountain
#  2 4 Swiftspear  6 4 Searing Blaze
#  3 (blank)       7 (blank)
DECK = (
    "// Creature\n4 Goblin Guide\n4 Monastery Swiftspear\n\n"
    "// Instant\n4 Lightning Bolt\n4 Searing Blaze\n\n"
    "// Land\n20 Mountain\n"
)


def _buf(text: str = DECK) -> Buffer:
    return Buffer.from_text(text)


def _state(text: str = DECK, row: int = 1) -> EditorState:
    buf = Buffer.from_text(text)
    history = HistoryService()
    history.initialize(buf)
    return EditorState(
        buffer=buf, cursor=Cursor(row=row), mode_mgr=ModeManager(),
        registers=RegisterStore(), history=history, modified=False,
        resolved_cards={}, cmd_history=CommandHistory(),
    )


def _registry() -> CommandRegistry:
    registry = CommandRegistry()
    register_all_commands(registry)
    return registry


def _ex(state: EditorState, text: str) -> str:
    hr = handle_command(
        state, ParsedAction("command_submit", "enter", text=text), _registry(), None,
    )
    return hr.command_message


def _texts(buf: Buffer) -> list[str]:
    return [buf.get_line(i).text for i in range(buf.line_count())]


# ── Operator ranges ───────────────────────────────────────────────


class TestOperatorRanges:
    @pytest.mark.parametrize(
        ("motion", "row", "count", "expected"),
        [
            ("w", 1, 1, (1, 1)),        # this card only
            ("w", 2, 1, (2, 2)),        # last of section: not the blank/header
            ("w", 1, 2, (1, 2)),
            ("w", 9, 1, (9, 9)),        # last card in the deck
            ("w", 6, 5, (6, 9)),        # fewer cards left: through the last
            ("b", 5, 1, (2, 2)),        # the card above, not the cursor's
            ("b", 1, 1, (1, 0)),        # nothing above: empty
            ("}", 1, 1, (1, 2)),        # to the end of the section
            ("}", 5, 2, (5, 9)),
            ("}", 9, 1, (9, 9)),
            ("{", 6, 1, (5, 5)),        # cards above in the section
            ("{", 5, 1, (1, 2)),        # at the start: the previous section
            ("{", 1, 1, (1, 0)),
            ("]]", 1, 1, (1, 2)),       # up to the next header, minus the blank
            ("]]", 9, 1, (9, 9)),
            ("[[", 6, 1, (4, 5)),
            ("[[", 0, 1, (0, -1)),
            ("G", 6, 0, (6, 9)),        # bare G: to the end
            ("G", 6, 3, (2, 6)),        # 3G: through line 3
            ("gg", 6, 2, (1, 6)),       # 2gg
            ("j", 1, 2, (1, 3)),
        ],
    )
    def test_ranges(
        self, motion: str, row: int, count: int, expected: tuple[int, int]
    ) -> None:
        assert resolve_line_range("d", motion, Cursor(row=row), _buf(), count) == expected

    def test_empty_range_changes_nothing_but_c_still_inserts(self) -> None:
        regs = RegisterStore()
        result = execute_operator("d", "b", Cursor(row=1), _buf(), 1, regs)
        assert result.buffer.to_text() == DECK
        assert result.registers is regs
        assert execute_operator("c", "b", Cursor(row=1), _buf(), 1, regs).enter_insert

    def test_empty_range_is_not_an_undo_step(self) -> None:
        st = _state(row=1)
        handle_operator(st, ParsedAction("operator", "d", motion="b"))
        assert st.modified is False
        assert not st.history.can_undo


class TestKeymap:
    def _feed(self, keys: list[str], mode: Mode = Mode.NORMAL) -> ParsedAction | None:
        km = KeyMap(mode=mode)
        action = None
        for key in keys:
            _, action = km.feed(key)
        return action

    def test_operator_g_without_count_sends_zero(self) -> None:
        action = self._feed(["d", "G"])
        assert action is not None and action.count == 0
        assert self._feed(["d", "8", "G"]).count == 8  # type: ignore[union-attr]
        assert self._feed(["8", "d", "G"]).count == 8  # type: ignore[union-attr]

    @pytest.mark.parametrize("reg", ["_", "+", "*", '"'])
    def test_symbol_registers(self, reg: str) -> None:
        action = self._feed(['"', reg, "d", "d"])
        assert action is not None and action.register == reg

    def test_unknown_register_is_dropped(self) -> None:
        km = KeyMap()
        km.feed('"')
        assert km.feed("!")[0] == KeyResult.NO_MATCH

    def test_question_mark_and_star(self) -> None:
        assert self._feed(["?"]) == ParsedAction("mode_switch", "?")
        assert self._feed(["*"]).action == "*"  # type: ignore[union-attr]
        assert self._feed(["#"]).action == "#"  # type: ignore[union-attr]
        assert self._feed(["g", "?"]).action == "g?"  # type: ignore[union-attr]

    @pytest.mark.parametrize("key", ["z", "t", "b"])
    def test_z_scroll_keys(self, key: str) -> None:
        assert self._feed(["z", key]).action == "z" + key  # type: ignore[union-attr]

    def test_visual_x_is_d_with_register(self) -> None:
        action = self._feed(['"', "a", "x"], mode=Mode.VISUAL_LINE)
        assert action == ParsedAction("operator", "d", register="a")

    def test_command_line_keys(self) -> None:
        km = KeyMap(mode=Mode.COMMAND)
        assert km.feed("backspace")[1] == ParsedAction("mode_switch", "escape")
        for ch in "ab cd":
            km.feed(ch)
        assert km.feed("up")[1] == ParsedAction("special", "up", text="ab cd", cursor_pos=5)
        assert km.feed("ctrl_w")[1].text == "ab "  # type: ignore[union-attr]
        assert km.feed("ctrl_b")[1].cursor_pos == 0  # type: ignore[union-attr]
        assert km.feed("ctrl_e")[1].cursor_pos == 3  # type: ignore[union-attr]
        assert km.feed("ctrl_u")[1].text == ""  # type: ignore[union-attr]


class TestLineBuffer:
    def test_delete_word_backward(self) -> None:
        buf = LineBuffer.from_text("sort  cmc  ")
        assert buf.delete_word_backward() == LineBuffer("sort  ", 6)
        assert LineBuffer("", 0).delete_word_backward() == LineBuffer("", 0)

    def test_delete_to_start(self) -> None:
        assert LineBuffer("abcdef", 4).delete_to_start() == LineBuffer("ef", 0)


# ── Registers ─────────────────────────────────────────────────────


class TestRegisters:
    def test_star_and_plus_are_one_register(self) -> None:
        regs = RegisterStore().set("*", ("x",))
        assert regs.get("+").content == ("x",)

    def test_names_order(self) -> None:
        regs = (
            RegisterStore().set("b", ("1",)).set("+", ("2",))
            .set_unnamed(("3",), is_delete=True)
        )
        assert regs.names() == ('"', "1", "b", "+")

    def test_black_hole_x(self) -> None:
        st = _state(row=1)
        st.registers = st.registers.set_unnamed(("keep",))
        handle_normal_special(st, ParsedAction("special", "x", register="_"))
        assert "4 Goblin Guide" not in st.buffer.to_text()
        assert st.registers.unnamed.content == ("keep",)


# ── Dot-repeat replays ────────────────────────────────────────────


class TestDotReplays:
    def test_yank_is_not_a_change(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, ParsedAction("special", "+"))
        handle_operator(st, ParsedAction("operator", "yy"))
        handle_normal_special(st, ParsedAction("special", "."))
        assert st.buffer.quantity_at(1) == 6

    def test_count_to_dot_sticks(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, ParsedAction("special", "+"))
        handle_normal_special(st, ParsedAction("special", ".", count=3))
        handle_normal_special(st, ParsedAction("special", "."))
        assert st.buffer.quantity_at(1) == 4 + 1 + 3 + 3

    def test_tag_and_category_clear_repeat(self) -> None:
        text = "4 A  @r  #x\n4 B  @s  #y\n"
        st = _state(text, row=0)
        handle_normal_special(st, ParsedAction("special", "tc"))
        handle_normal_special(st, ParsedAction("special", "gC"))
        st.cursor = Cursor(row=1)
        handle_normal_special(st, ParsedAction("special", "."))
        assert st.buffer.category_at(1) == ""
        assert st.buffer.tags_at(1) == frozenset({"y"})  # gC was the last change

    def test_insert_without_a_card_is_not_recorded(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, ParsedAction("special", "+"))
        handle_mode_switch(st, ParsedAction("mode_switch", "o"))
        from vimtg.editor.card_insert import discard_pending_insert

        discard_pending_insert(st)  # Esc
        assert st.pending_change is None
        assert st.dot_repeat.last_action is not None
        assert st.dot_repeat.last_action.action_type == "quantity"

    def test_open_line_confirm_records_card_and_copies(self) -> None:
        st = _state(row=5)
        handle_mode_switch(st, ParsedAction("mode_switch", "o", count=3))
        card = Card.from_scryfall({"id": "x", "name": "Opt", "type_line": "Instant"})
        message = confirm_card_search(st, card)
        assert "3x Opt" in message
        last = st.dot_repeat.last_action
        assert last is not None
        assert (last.action_type, last.card_name, last.quantity) == ("insert", "Opt", 3)
        st.cursor = Cursor(row=9)
        handle_normal_special(st, ParsedAction("special", "."))
        assert "6 Opt" in st.buffer.to_text()


# ── Search ────────────────────────────────────────────────────────


class TestSearch:
    def _search(self, st: EditorState, key: str, text: str) -> str:
        handle_mode_switch(st, ParsedAction("mode_switch", key))
        st.mode_mgr.transition(Mode.SEARCH)
        hr = handle_command(
            st, ParsedAction("command_submit", "enter", text=text), _registry(), None,
        )
        st.mode_mgr.force_normal()
        return hr.command_message

    def test_empty_pattern_reuses_last_and_errors_without_one(self) -> None:
        st = _state(row=1)
        assert "E35" in self._search(st, "/", "")
        self._search(st, "/", "bolt")
        assert st.cursor.row == 5
        st.cursor = Cursor(row=1)
        assert self._search(st, "/", "") == "/bolt"
        assert st.cursor.row == 5

    def test_invalid_pattern(self) -> None:
        st = _state(row=1)
        assert "Invalid pattern" in self._search(st, "?", "(")

    def test_star_on_a_non_card_line(self) -> None:
        st = _state(row=0)
        hr = handle_normal_special(st, ParsedAction("special", "*"))
        assert hr.error and "E348" in hr.command_message


# ── Ex commands ───────────────────────────────────────────────────


class TestSubstitute:
    def _sub(self, args: str, text: str = "4 Lightning Bolt\n", last: str = "") -> str:
        ctx = EditorContext(last_pattern=last)
        buf, _ = cmd_substitute(
            Buffer.from_text(text), Cursor(), ParsedCommand(name="s", args=args), ctx,
        )
        return buf.get_line(0).text

    def test_regex_like_slash_and_g(self) -> None:
        assert self._sub(r"/^\d+/2/") == "2 Lightning Bolt"
        assert self._sub("/bolt/Strike/") == "4 Lightning Strike"  # ignores case

    def test_capital_i_matches_case(self) -> None:
        assert self._sub("/bolt/Strike/I") == "4 Lightning Bolt"

    def test_ampersand_and_backrefs(self) -> None:
        assert self._sub("/Bolt/[&]/") == "4 Lightning [Bolt]"
        assert self._sub(r"/(\w+) (\w+)$/\2 \1/") == "4 Bolt Lightning"
        assert self._sub(r"/Bolt/\&/") == "4 Lightning &"

    def test_empty_pattern_uses_last_search(self) -> None:
        assert self._sub("//Strike/", last="bolt") == "4 Lightning Strike"
        ctx = EditorContext()
        cmd_substitute(Buffer.from_text("x\n"), Cursor(), ParsedCommand("s", "//y/"), ctx)
        assert ctx.error and "E35" in ctx.message

    def test_escaped_delimiter(self) -> None:
        assert split_delimited(r"/a\/b/c/", 3) == ["a/b", "c", ""]
        assert self._sub(r"/Bolt/a\/b/") == "4 Lightning a/b"

    def test_invalid_regex(self) -> None:
        ctx = EditorContext()
        cmd_substitute(Buffer.from_text("x\n"), Cursor(), ParsedCommand("s", "/(/y/"), ctx)
        assert ctx.error


class TestGlobal:
    def _g(
        self, args: str, *, bang: bool = False, name: str = "g", last: str = ""
    ) -> tuple[Buffer, EditorContext]:
        ctx = EditorContext(registers=RegisterStore(), last_pattern=last)
        buf, _ = cmd_global(_buf(), Cursor(), ParsedCommand(name, args, bang=bang), ctx)
        return buf, ctx

    def test_print(self) -> None:
        buf, ctx = self._g("/^4/p")
        assert buf.to_text() == DECK
        assert ctx.message.startswith("4 match(es): 4 Goblin Guide")

    def test_substitute_with_the_g_pattern(self) -> None:
        buf, ctx = self._g("/bolt/s//Strike/")
        assert "4 Lightning Strike" in buf.to_text()
        assert ctx.modified

    def test_substitute_with_its_own_pattern(self) -> None:
        buf, _ = self._g("/^4/s/^4/3/")
        assert "3 Goblin Guide" in buf.to_text()
        assert "20 Mountain" in buf.to_text()

    def test_yank_appends_to_register(self) -> None:
        _, ctx = self._g("/guide/y a")
        assert ctx.registers.get("a").content == ("4 Goblin Guide",)

    def test_bang_inverts(self) -> None:
        buf, _ = self._g("/^4/d", bang=True)
        assert "20 Mountain" not in buf.to_text()
        assert "4 Goblin Guide" in buf.to_text()

    def test_empty_pattern_and_bad_subcommand(self) -> None:
        buf, _ = self._g("//d", last="mountain")
        assert "Mountain" not in buf.to_text()
        _, ctx = self._g("//d")
        assert ctx.error
        _, ctx = self._g("/x/normal dd")
        assert ctx.message.startswith("Pattern not found")
        _, ctx = self._g("/bolt/normal dd")
        assert ctx.error and "supported" in ctx.message


class TestLineCommands:
    def test_goto(self) -> None:
        st = _state(row=0)
        _ex(st, "7")
        assert st.cursor.row == 6
        _ex(st, "0")
        assert st.cursor.row == 0
        _ex(st, "99")
        assert st.cursor.row == st.buffer.line_count() - 1

    def test_delete_and_yank_into_registers(self) -> None:
        st = _state(row=1)
        st.marks = MarkStore().set("a", 9)
        assert _ex(st, "2,3d a") == "2 lines deleted"
        assert st.registers.get("a").content == ("4 Goblin Guide", "4 Monastery Swiftspear")
        assert st.marks.get("a").row == 7  # type: ignore[union-attr]
        _ex(st, "1y b")
        assert st.registers.get("b").content == ("// Creature",)
        assert "E488" in _ex(st, "d foo")
        assert st.history.can_undo

    def test_move(self) -> None:
        st = _state(row=0)
        _ex(st, "2m$")
        assert _texts(st.buffer)[-1] == "4 Goblin Guide"
        assert st.cursor.row == st.buffer.line_count() - 1
        _ex(st, "$m0")
        assert _texts(st.buffer)[0] == "4 Goblin Guide"
        assert "E134" in _ex(st, "1,3m2")
        assert "E14" in _ex(st, "m")
        before = st.buffer
        _ex(st, "2m1")  # already below line 1: nothing moves
        assert st.buffer is before

    def test_copy(self) -> None:
        st = _state(row=0)
        _ex(st, "2co0")
        assert _texts(st.buffer)[:2] == ["4 Goblin Guide", "// Creature"]
        _ex(st, "t.")
        assert _texts(st.buffer)[:2] == ["4 Goblin Guide", "4 Goblin Guide"]

    def test_registers_and_marks_listings(self) -> None:
        st = _state(row=1)
        assert _ex(st, "reg") == "No registers set"
        assert _ex(st, "marks") == "No marks set"
        st.registers = st.registers.set("a", ("x" * 40, "y")).set("b", ("z",))
        listing = _ex(st, "reg a")
        assert listing.startswith('"a xxxx') and "(+1)" in listing and '"b' not in listing


class TestEdit:
    def _edit(
        self, args: str, *, bang: bool = False, modified: bool = False,
        file_path: Path | None = None,
    ) -> EditorContext:
        ctx = EditorContext(modified=modified, file_path=file_path)
        cmd_edit(_buf(), Cursor(), ParsedCommand("e", args, bang=bang), ctx)
        return ctx

    def test_no_file_name(self) -> None:
        assert "E32" in self._edit("").message

    def test_unsaved_changes_need_bang(self, tmp_path: Path) -> None:
        target = tmp_path / "a.deck"
        assert "E37" in self._edit(str(target), modified=True).message
        assert self._edit(str(target), modified=True, bang=True).edit_path == target

    def test_reload_and_suffix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mine = tmp_path / "mine.deck"
        assert self._edit("", file_path=mine).edit_path == mine
        (tmp_path / "other.deck").write_text("1 Opt\n")
        monkeypatch.chdir(tmp_path)
        assert self._edit("other").edit_path == tmp_path / "other.deck"
        assert self._edit("new").edit_path == tmp_path / "new"  # a new deck

    def test_directory_and_unreadable(self, tmp_path: Path) -> None:
        assert "directory" in self._edit(str(tmp_path)).message
        binary = tmp_path / "x.deck"
        binary.write_bytes(b"\xff\xfe\xfa")
        ctx = self._edit(str(binary))
        assert ctx.error and ctx.edit_path is None


class TestParse:
    def test_new_commands_parse(self) -> None:
        cmd = parse_command("m0", 0, 10)
        assert (cmd.name, cmd.args) == ("m", "0")
        cmd = parse_command("e!", 0, 10)
        assert (cmd.name, cmd.bang) == ("e", True)


# ── Zones in the deck's format ────────────────────────────────────


class TestZoneFormat:
    def test_zs_in_commander_warns_but_moves(self) -> None:
        st = _state("// Format: commander\n\n// Creature\n1 Goblin Guide\n", row=3)
        hr = handle_normal_special(st, ParsedAction("special", "zs"))
        assert "warning: commander has no sideboard" in hr.command_message
        assert "Goblin Guide" in st.buffer.to_text().split("SB:")[1]

    def test_zc_in_commander_is_allowed(self) -> None:
        st = _state("// Format: commander\n\n// Creature\n1 Goblin Guide\n", row=3)
        hr = handle_normal_special(st, ParsedAction("special", "zc"))
        assert not hr.error
        assert "CMD:" in st.buffer.to_text()

    def test_unknown_format_checks_nothing(self) -> None:
        st = _state("// Format: homebrew\n\n// Creature\n1 Goblin Guide\n", row=3)
        assert not handle_normal_special(st, ParsedAction("special", "zc")).error

    def test_visual_zone_move_with_no_cards(self) -> None:
        st = _state(row=0)
        st.visual_anchor = 0
        hr = handle_normal_special(st, ParsedAction("special", "zs"))
        assert hr.command_message == "No card lines selected"
        assert hr.exit_to_normal


# ── Command-line history ──────────────────────────────────────────


class TestCommandHistory:
    def test_dedupes_caps_and_persists(self, tmp_path: Path) -> None:
        path = tmp_path / "h.json"
        history = CommandHistory(path, limit=3)
        for text in ("a", "b", "a", "c", "d", ""):
            history.add("cmd", text)
        assert history.entries("cmd") == ("a", "c", "d")
        assert CommandHistory.load(path).entries("cmd") == ("a", "c", "d")

    def test_corrupt_or_missing_file_is_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "h.json"
        assert CommandHistory.load(path).entries("cmd") == ()
        path.write_text("{not json")
        assert CommandHistory.load(path).entries("search") == ()
        path.write_text('{"cmd": ["ok", 3, ""], "search": "x"}')
        loaded = CommandHistory.load(path)
        assert loaded.entries("cmd") == ("ok",)
        assert loaded.entries("search") == ()

    def test_unwritable_path_is_ignored(self, tmp_path: Path) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("")
        history = CommandHistory(blocker / "h.json")
        history.add("cmd", "w")  # no exception
        assert history.entries("cmd") == ("w",)

    def test_browse(self) -> None:
        history = CommandHistory()
        for text in ("sort", "stats", "tags"):
            history.add("cmd", text)
        assert history.newer("cmd") is None  # not browsing
        assert history.older("cmd", "s") == "stats"
        assert history.older("cmd", "ignored") == "sort"
        assert history.older("cmd", "") is None  # no older match
        assert history.newer("cmd") == "stats"
        assert history.newer("cmd") == "s"  # back to what was typed

    def test_editing_resets_the_browse(self) -> None:
        st = _state()
        st.mode_mgr.transition(Mode.COMMAND)
        st.cmd_history.add("cmd", "tags")
        st.cmd_history.add("cmd", "stats")
        hr = handle_command_special(st, ParsedAction("special", "up", text=""))
        assert hr.command_replace == "stats"
        handle_command_special(st, ParsedAction("special", "char", text="t"))
        hr = handle_command_special(st, ParsedAction("special", "up", text="t"))
        assert hr.command_replace == "tags"
        hr = handle_command_special(st, ParsedAction("special", "up", text="t"))
        assert hr.command_replace is None


@pytest.mark.parametrize(
    "line",
    ["e!", "edit!", "d", "delete", "y", "yank", "m0", "move 0", "t0", "co0", "copy 0",
     "undo", "u", "redo", "red", "reg", "registers", "di", "marks", "12", "$"],
)
def test_new_ex_commands_are_registered(line: str) -> None:
    """:e was documented but unregistered; every new command must resolve."""
    ctx = EditorContext(file_path=Path("x.deck"))
    buf = _buf()
    cmd = parse_command(line, 1, buf.line_count())
    _registry().execute(cmd, buf, Cursor(row=1), ctx)
    assert not ctx.message.startswith("E: Unknown command")
