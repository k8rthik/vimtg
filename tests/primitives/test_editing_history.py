"""Editing slice: undo (u), redo (Ctrl-R), dot repeat (.), and macros
(q{a-z}, q, @{a-z}, @@, @:).

Spec: docs/keybindings.md (Editing; Marks, macros, registers) and the
README's Undo/redo, Dot repeat and Macros lines. Every change is one
undo step (only a quick burst of + or - on a card folds into one),
undoing back to the saved state clears the modified flag, and a new
edit after an undo drops the redo entries. `.` repeats every edit, a
count on it overriding the recorded one. Macros replay their keys
through the full pipeline; the status line shows "recording @a (q
stops)" while one records.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, Ed, editor

pytestmark = pytest.mark.asyncio

L = DECK.splitlines(keepends=True)

# Eight cards with distinct quantities, no sections: counts are easy to
# read and no section cleanup moves rows. Rows 4-11; card n is on line n + 4.
FLAT = (
    "// Deck: Flat\n// Format: modern\n// Tags:\n\n"
    "1 Goblin Guide\n"
    "2 Eidolon of the Great Revel\n"
    "3 Bonecrusher Giant // Stomp\n"
    "4 Lightning Bolt\n"
    "5 Fire // Ice\n"
    "6 Sacred Foundry\n"
    "7 Mountain\n"
    "8 Rest in Peace\n"
)
FLAT_CARDS = FLAT.splitlines()[4:]


def without(*rows: int) -> str:
    return "".join(text for i, text in enumerate(L) if i not in rows)


def copies(ed: Ed, name: str) -> int:
    """Total copies of `name` across the card lines."""
    total = 0
    for card in ed.cards:
        qty, _, rest = card.partition(" ")
        if rest.startswith(name):
            total += int(qty)
    return total


# ── u and Ctrl-R: one change per step, exactly ────────────────────────

# (keys, card search query) for every mutating editing primitive. The keys run
# on the canonical DECK; card search picks happen after the keys.
CHANGES = [
    ("9G dd", None),
    ("8G 3dd", None),
    ("13G 2dd", None),  # empties // Instant: cleanup is in the same step
    ("G dd", None),
    ("9G D", None),
    ("8G d2d", None),
    ("9G cc", "delver"),
    ("9G cc <Esc>", None),
    ("9G S", "delver"),
    ("9G C", "delver"),
    ("8G c2c <Esc>", None),
    ("9G x", None),
    ("13G 3x", None),
    ("8G yy 13G p", None),
    ("8G yy 13G 3p", None),
    ("8G yy 13G P", None),
    ("8G +", None),
    ("18G 100+", None),
    ("8G -", None),
    ("14G -", None),
    ("8G <C-a>", None),
    ("8G 3<C-x>", None),
    ("14G <C-x>", None),
    ('9G "_dd', None),
    ('9G "add', None),
]


@pytest.mark.primitive(
    "u", "ctrl_r", "dd", "D", "d", "cc", "S", "C", "c", "x", "p", "P",
    "+", "-", "ctrl_a", "ctrl_x",
)
@pytest.mark.parametrize(("keys", "query"), CHANGES, ids=[c[0] for c in CHANGES])
async def test_one_u_undoes_the_change_and_ctrl_r_redoes_it(
    tmp_path: Path, keys: str, query: str | None
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(keys)
        if query is not None:
            await ed.pick(query)
        changed = ed.text
        assert changed != DECK
        ed.press("u")
        assert ed.text == DECK
        assert ed.modified is False
        ed.press("<C-r>")
        assert ed.text == changed
        assert ed.modified is True


@pytest.mark.primitive("u")
async def test_u_walks_back_one_change_at_a_time(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G dd dd")
        ed.press("u")
        assert ed.text == without(7)
        ed.press("u")
        assert ed.text == DECK


@pytest.mark.primitive("u")
async def test_count_u_undoes_that_many_changes(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G dd dd 11G x 2u")
        assert ed.text == without(7)


@pytest.mark.primitive("ctrl_r")
async def test_count_ctrl_r_redoes_that_many_changes(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G dd dd 3u 2<C-r>")
        assert ed.text == without(7, 8)


@pytest.mark.primitive("u")
async def test_u_with_nothing_to_undo_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G u")
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive("ctrl_r")
async def test_ctrl_r_with_nothing_to_redo_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G dd <C-r>")
        assert ed.text == without(8)


@pytest.mark.primitive("ctrl_r")
async def test_a_new_change_after_undo_drops_the_redo(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G dd u 8G x <C-r>")
        assert ed.text == without(7)


@pytest.mark.primitive("u")
async def test_undo_back_to_the_saved_deck_clears_modified(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G dd :w<CR>")
        saved = ed.text
        assert ed.modified is False
        ed.press("8G dd")
        assert ed.modified is True
        ed.press("u")
        assert ed.text == saved
        assert ed.modified is False
        ed.press("u")
        assert ed.text == DECK
        assert ed.modified is True


@pytest.mark.primitive("u", "+")
async def test_a_quick_burst_of_plus_on_a_card_is_one_undo_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G + + +")
        assert ed.lines[7] == "    7 Goblin Guide"
        ed.press("u")
        assert ed.text == DECK


@pytest.mark.primitive("u", "-")
async def test_a_quick_burst_of_minus_on_a_card_is_one_undo_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("18G - - -")
        ed.press("u")
        assert ed.text == DECK


@pytest.mark.primitive("u", "+")
async def test_plus_on_two_cards_is_two_undo_steps(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G + 9G +")
        ed.press("u")
        assert ed.lines[7] == "    5 Goblin Guide"
        assert ed.lines[8] == "    2 Eidolon of the Great Revel"


@pytest.mark.primitive("u", "+")
async def test_an_undo_ends_a_burst(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G + u <C-r> + u")
        assert ed.lines[7] == "    5 Goblin Guide"


@pytest.mark.primitive("u", "yy")
async def test_a_yank_is_not_an_undo_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G dd 8G yy u")
        assert ed.text == DECK


# ── . ──────────────────────────────────────────────────────────────────


@pytest.mark.primitive(".", "dd")
async def test_dot_repeats_dd(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G dd .")
        assert ed.cards == FLAT_CARDS[2:]
        assert ed.modified is True


@pytest.mark.primitive(".", "dd")
async def test_dot_repeats_the_count_of_count_dd(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G 2dd .")
        assert ed.cards == FLAT_CARDS[4:]


@pytest.mark.primitive(".", "dd")
async def test_a_count_on_dot_replaces_the_recorded_count(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G 2dd 3.")
        assert ed.cards == FLAT_CARDS[5:]


@pytest.mark.primitive(".", "D")
async def test_dot_repeats_capital_d(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G D .")
        assert ed.cards == FLAT_CARDS[2:]


@pytest.mark.primitive(".", "d")
async def test_dot_repeats_a_count_after_d(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G d2d .")
        assert ed.cards == FLAT_CARDS[4:]


@pytest.mark.primitive(".", "x")
async def test_dot_repeats_x(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G x .")
        assert ed.cards == FLAT_CARDS[2:]


@pytest.mark.primitive(".", "x")
async def test_dot_repeats_count_x(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G 2x .")
        assert ed.cards == FLAT_CARDS[4:]


@pytest.mark.primitive(".", "p")
async def test_dot_repeats_p(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G yy p .")
        assert ed.cards == FLAT_CARDS[:1] * 3 + FLAT_CARDS[1:]


@pytest.mark.primitive(".", "p")
async def test_dot_repeats_count_p(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G yy 2p .")
        assert ed.cards == FLAT_CARDS[:1] * 5 + FLAT_CARDS[1:]


@pytest.mark.primitive(".", "P")
async def test_dot_repeats_capital_p(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("12G yy 5G P .")
        assert ed.cards == FLAT_CARDS[-1:] * 2 + FLAT_CARDS


@pytest.mark.primitive(".", "+")
async def test_dot_repeats_plus(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G + 6G .")
        assert ed.cards[:2] == ["2 Goblin Guide", "3 Eidolon of the Great Revel"]


@pytest.mark.primitive(".", "+")
async def test_dot_repeats_the_count_of_plus(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G 5+ .")
        assert ed.cards[0] == "11 Goblin Guide"


@pytest.mark.primitive(".", "+")
async def test_a_count_on_dot_replaces_the_count_of_plus(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G + 4.")
        assert ed.cards[0] == "6 Goblin Guide"


@pytest.mark.primitive(".", "-")
async def test_dot_repeats_minus(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("11G - .")
        assert ed.cards[6] == "5 Mountain"


@pytest.mark.primitive(".", "-")
async def test_dot_repeats_minus_down_to_deleting_the_line(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("6G - .")
        assert ed.cards == FLAT_CARDS[:1] + FLAT_CARDS[2:]


@pytest.mark.primitive(".", "ctrl_a")
async def test_dot_repeats_ctrl_a(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G 2<C-a> .")
        assert ed.cards[0] == "5 Goblin Guide"


@pytest.mark.primitive(".", "ctrl_x")
async def test_dot_repeats_ctrl_x(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("12G 2<C-x> .")
        assert ed.cards[7] == "4 Rest in Peace"


@pytest.mark.primitive(".", "cc")
async def test_dot_repeats_cc_with_the_card_it_added(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G cc")
        await ed.pick("lava")
        ed.press("/eidolon<CR> .")
        assert "2 Eidolon of the Great Revel" not in ed.cards
        assert "1 Goblin Guide" not in ed.cards
        assert copies(ed, "Lava Spike") == 2


@pytest.mark.primitive(".", "S")
async def test_dot_repeats_capital_s_with_the_card_it_added(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G S")
        await ed.pick("lava")
        ed.press("/eidolon<CR> .")
        assert "2 Eidolon of the Great Revel" not in ed.cards
        assert copies(ed, "Lava Spike") == 2


@pytest.mark.primitive(".", "yy")
async def test_dot_skips_a_yank_and_repeats_the_last_change(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G dd 8G yy .")
        assert ed.cards == FLAT_CARDS[1:4] + FLAT_CARDS[5:]


@pytest.mark.primitive(".")
async def test_dot_with_nothing_to_repeat_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G .")
        assert ed.text == FLAT
        assert ed.modified is False


@pytest.mark.primitive(".", "u")
async def test_a_repeat_is_its_own_undo_step(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G dd . u")
        assert ed.cards == FLAT_CARDS[1:]


@pytest.mark.primitive(".", '"{a-z}')
async def test_dot_after_a_named_delete_files_into_the_same_register(
    tmp_path: Path,
) -> None:
    # vim: "add. deletes into "a again (only numbered registers advance)
    async with editor(tmp_path, FLAT) as ed:
        ed.press('5G "add .')
        assert ed.register("a") == (FLAT_CARDS[1],)


# ── macros: q{a-z}, q, @{a-z}, @@ ─────────────────────────────────────


@pytest.mark.primitive("q{a-z}")
async def test_recording_shows_in_the_status_line(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("qa")
        assert "recording @a (q stops)" in ed.status


@pytest.mark.primitive("q{a-z}")
async def test_recording_runs_the_keys_as_typed(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + j")
        assert ed.cards[0] == "2 Goblin Guide"
        assert ed.row == 5


@pytest.mark.primitive("q")
async def test_q_stops_recording(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("qa + q")
        assert "recording" not in ed.status


@pytest.mark.primitive("q")
async def test_keys_after_q_are_not_recorded(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + q j @a")
        # @a is + alone: Eidolon gains one and the cursor stays on it
        assert ed.cards[:2] == ["2 Goblin Guide", "3 Eidolon of the Great Revel"]
        assert ed.row == 5


@pytest.mark.primitive("@{a-z}")
async def test_at_plays_the_macro(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + j q @a")
        assert ed.cards[:3] == [
            "2 Goblin Guide", "3 Eidolon of the Great Revel", "3 Bonecrusher Giant // Stomp",
        ]
        assert ed.row == 6


@pytest.mark.primitive("@{a-z}")
async def test_count_at_plays_the_macro_that_many_times(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + j q 3@a")
        assert ed.cards[:5] == [
            "2 Goblin Guide", "3 Eidolon of the Great Revel",
            "4 Bonecrusher Giant // Stomp", "5 Lightning Bolt", "5 Fire // Ice",
        ]
        assert ed.row == 8


@pytest.mark.primitive("@{a-z}", "q{a-z}")
async def test_a_macro_can_delete_several_cards(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa dd q 2@a")
        assert ed.cards == FLAT_CARDS[3:]


@pytest.mark.primitive("@{a-z}", "q{a-z}")
async def test_a_macro_spanning_several_edits_replays_all_of_them(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + j - j dd q @a")
        # Recording: Goblin 2, Eidolon 1, Bonecrusher deleted; cursor on
        # Bolt. Playing: Bolt 5, Fire 4, Sacred Foundry deleted.
        assert ed.cards == [
            "2 Goblin Guide", "1 Eidolon of the Great Revel",
            "5 Lightning Bolt", "4 Fire // Ice", "7 Mountain", "8 Rest in Peace",
        ]


@pytest.mark.primitive("@{a-z}")
async def test_playing_an_empty_macro_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G @b")
        assert ed.text == FLAT
        assert ed.modified is False


@pytest.mark.primitive("q{a-z}")
async def test_uppercase_q_appends_to_the_macro(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + q qA j q")
        assert ed.row == 5
        ed.press("@a")
        # @a is now + then j
        assert ed.cards[1] == "3 Eidolon of the Great Revel"
        assert ed.row == 6


@pytest.mark.primitive("q{a-z}")
async def test_recording_again_replaces_the_macro(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + q qa - q 6G @a")
        assert ed.cards[1] == "1 Eidolon of the Great Revel"


@pytest.mark.primitive("@@")
async def test_at_at_replays_the_last_macro(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + j q @a @@")
        assert ed.cards[:4] == [
            "2 Goblin Guide", "3 Eidolon of the Great Revel",
            "4 Bonecrusher Giant // Stomp", "4 Lightning Bolt",
        ]


@pytest.mark.primitive("@@")
async def test_count_at_at_replays_that_many_times(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + j q @a 2@@")
        assert ed.cards[:5] == [
            "2 Goblin Guide", "3 Eidolon of the Great Revel",
            "4 Bonecrusher Giant // Stomp", "5 Lightning Bolt", "5 Fire // Ice",
        ]
        assert ed.row == 8


@pytest.mark.primitive("@@")
async def test_at_at_replays_the_macro_played_last_not_recorded_last(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G qa + q qb - q 6G @a 7G @@")
        assert ed.cards[1:3] == [
            "3 Eidolon of the Great Revel", "4 Bonecrusher Giant // Stomp",
        ]


@pytest.mark.primitive("@@")
async def test_at_at_with_nothing_played_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G @@")
        assert ed.text == FLAT
        assert ed.modified is False


# ── @: ─────────────────────────────────────────────────────────────────


@pytest.mark.primitive("@:")
async def test_at_colon_runs_the_last_ex_command_again(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G :s/^1/9/<CR> 6G :s/$/!/<CR> 7G @:")
        assert ed.cards[:3] == [
            "9 Goblin Guide", "2 Eidolon of the Great Revel!",
            "3 Bonecrusher Giant // Stomp!",
        ]


@pytest.mark.primitive("@:")
async def test_count_at_colon_runs_it_that_many_times(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G :s/$/!/<CR> 3@:")
        assert ed.cards[0] == "1 Goblin Guide!!!!"


@pytest.mark.primitive("@:", "@@")
async def test_at_at_after_at_colon_repeats_the_ex_command(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G :s/$/!/<CR> 6G @: 7G @@")
        assert ed.cards[:3] == [
            "1 Goblin Guide!", "2 Eidolon of the Great Revel!",
            "3 Bonecrusher Giant // Stomp!",
        ]


@pytest.mark.primitive("@:")
async def test_at_colon_with_no_ex_command_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path, FLAT) as ed:
        ed.press("5G @:")
        assert ed.is_error
        assert ed.text == FLAT
