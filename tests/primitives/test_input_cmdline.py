"""Input slice: the : command line, its editing keys and its history.

Expected values come from docs/keybindings.md (Command mode). Editing
keys are checked through what the line then runs: `:12<CR>` goes to row
11 and `:21<CR>` to row 20, so where a key left the cursor shows up as
the line the command reaches.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, Ed, editor
from vimtg.editor.modes import Mode
from vimtg.tui.widgets.command_line import CommandLine


def line(ed: Ed) -> CommandLine:
    return ed.screen.query_one("#command-line", CommandLine)


# ── : and unknown commands ───────────────────────────────────────


@pytest.mark.primitive(":")
@pytest.mark.asyncio
async def test_colon_opens_the_command_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":")
        assert ed.mode is Mode.COMMAND
        assert line(ed).prefix == ":"
        assert line(ed).text == ""


@pytest.mark.primitive(":")
@pytest.mark.asyncio
async def test_colon_runs_the_typed_command(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":13<CR>")
        assert ed.mode is Mode.NORMAL
        assert ed.row == 12
        assert ed.text == DECK


@pytest.mark.primitive(":")
@pytest.mark.asyncio
async def test_escape_cancels_the_command_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G :13<Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.row == 7


@pytest.mark.primitive(":")
@pytest.mark.asyncio
async def test_unknown_command_is_e492_and_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G :frobnicate<CR>")
        assert ed.is_error
        assert ed.message.startswith("E492")
        assert ed.text == DECK
        assert ed.row == 7
        assert ed.mode is Mode.NORMAL
        assert ed.modified is False


@pytest.mark.primitive(":")
@pytest.mark.asyncio
@pytest.mark.parametrize("cmd", ["d", "y", "m", "t", "undo", "redo", "normal", "join"])
async def test_commands_the_docs_rule_out_are_e492(tmp_path: Path, cmd: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G :{cmd}<CR>")
        assert ed.is_error
        assert ed.message.startswith("E492")
        assert ed.text == DECK


# ── editing keys ─────────────────────────────────────────────────


@pytest.mark.primitive("cmdline:left")
@pytest.mark.asyncio
async def test_left_moves_the_cursor_back_one_character(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":1<Left>2")
        assert line(ed).text == "21"
        ed.press("<CR>")
        assert ed.row == 20


@pytest.mark.primitive("cmdline:right")
@pytest.mark.asyncio
async def test_right_moves_the_cursor_forward_one_character(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":1<Left><Right>2")
        assert line(ed).text == "12"
        ed.press("<CR>")
        assert ed.row == 11


@pytest.mark.primitive("cmdline:right")
@pytest.mark.asyncio
async def test_right_at_the_end_stays_at_the_end(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":1<Right><Right>2")
        assert line(ed).text == "12"


@pytest.mark.primitive("cmdline:left")
@pytest.mark.asyncio
async def test_left_at_the_start_stays_at_the_start(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":1<Left><Left><Left>2")
        assert line(ed).text == "21"
        assert ed.mode is Mode.COMMAND


@pytest.mark.primitive("cmdline:ctrl_b")
@pytest.mark.asyncio
async def test_ctrl_b_moves_to_the_start(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":2<C-b>1")
        assert line(ed).text == "12"
        ed.press("<CR>")
        assert ed.row == 11


@pytest.mark.primitive("cmdline:ctrl_e")
@pytest.mark.asyncio
async def test_ctrl_e_moves_to_the_end(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":2<C-b><C-e>1")
        assert line(ed).text == "21"
        ed.press("<CR>")
        assert ed.row == 20


@pytest.mark.primitive("cmdline:ctrl_w")
@pytest.mark.asyncio
async def test_ctrl_w_deletes_the_word_before_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":sort<Space>name<C-w>")
        assert line(ed).text == "sort "


@pytest.mark.primitive("cmdline:ctrl_w")
@pytest.mark.asyncio
async def test_ctrl_w_mid_line_keeps_the_text_after_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":aa<Space>bb<Space>cc<Left><Left><Left><C-w>")
        assert line(ed).text == "aa  cc"


@pytest.mark.primitive("cmdline:ctrl_u")
@pytest.mark.asyncio
async def test_ctrl_u_deletes_everything_before_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":junk12<Left><Left><C-u>")
        assert line(ed).text == "12"
        ed.press("<CR>")
        assert ed.row == 11
        assert not ed.is_error


@pytest.mark.primitive("cmdline:backspace")
@pytest.mark.asyncio
async def test_backspace_deletes_the_character_before_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":133<BS>")
        assert line(ed).text == "13"
        ed.press("<CR>")
        assert ed.row == 12


@pytest.mark.primitive("cmdline:backspace")
@pytest.mark.asyncio
async def test_backspace_mid_line_deletes_before_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":192<Left><BS>")
        assert line(ed).text == "12"


@pytest.mark.primitive("cmdline:backspace")
@pytest.mark.asyncio
async def test_backspace_on_an_empty_line_leaves_the_command_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G :a<BS>")
        assert ed.mode is Mode.COMMAND
        ed.press("<BS>")
        assert ed.mode is Mode.NORMAL
        assert ed.row == 7
        assert ed.text == DECK


@pytest.mark.primitive("cmdline:backspace", "/")
@pytest.mark.asyncio
async def test_the_search_prompt_shares_the_editing_keys(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("/xxbolx<BS>t<C-b><Right><Right><C-u><CR>")
        assert ed.row == 12


# ── history ──────────────────────────────────────────────────────


@pytest.mark.primitive("cmdline:up")
@pytest.mark.asyncio
async def test_up_recalls_the_previous_command(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":13<CR> :8<CR> :<Up>")
        assert line(ed).text == "8"
        ed.press("<Up>")
        assert line(ed).text == "13"


@pytest.mark.primitive("cmdline:up")
@pytest.mark.asyncio
async def test_up_recalls_only_entries_starting_with_the_typed_text(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":13<CR> :8<CR> :1<Up>")
        assert line(ed).text == "13"
        ed.press("<CR>")
        assert ed.row == 12


@pytest.mark.primitive("cmdline:up")
@pytest.mark.asyncio
async def test_up_collapses_duplicate_entries(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":13<CR> :8<CR> :13<CR> :<Up>")
        assert line(ed).text == "13"
        ed.press("<Up>")
        assert line(ed).text == "8"


@pytest.mark.primitive("cmdline:down")
@pytest.mark.asyncio
async def test_down_recalls_the_newer_entry(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":13<CR> :8<CR> :<Up><Up><Down>")
        assert line(ed).text == "8"


@pytest.mark.primitive("cmdline:down")
@pytest.mark.asyncio
async def test_down_keeps_the_prefix_match(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":13<CR> :8<CR> :12<CR> :1<Up><Up>")
        assert line(ed).text == "13"
        ed.press("<Down>")
        assert line(ed).text == "12"


@pytest.mark.primitive("cmdline:up", "/")
@pytest.mark.asyncio
async def test_search_and_command_histories_are_separate(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":13<CR> /bolt<CR> /<Up>")
        assert line(ed).text == "bolt"
        ed.press("<Esc> :<Up>")
        assert line(ed).text == "13"


@pytest.mark.primitive("cmdline:up")
@pytest.mark.asyncio
async def test_history_survives_a_restart(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":13<CR>")
    async with editor(tmp_path, cards=False) as ed:
        ed.press(":<Up>")
        assert line(ed).text == "13"
