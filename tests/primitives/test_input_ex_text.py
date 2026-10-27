"""Input slice: the text-processing ex commands :s, :g and :v.

Expected values come from docs/commands.md (Editing). Patterns are
case-insensitive regexes; :g and :v only ever touch card lines, in any
zone. Every change is one undo step.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, editor


def deck_with(*pairs: tuple[str, str]) -> str:
    text = DECK
    for old, new in pairs:
        assert old in text
        text = text.replace(old, new)
    return text


ALL_CARDS = [
    "4 Goblin Guide", "2 Eidolon of the Great Revel", "3 Bonecrusher Giant // Stomp",
    "4 Lightning Bolt", "1 Fire // Ice", "4 Sacred Foundry", "16 Mountain",
    "2 Rest in Peace",
]


# ── :s ───────────────────────────────────────────────────────────


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_substitutes_on_the_cursor_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13G").ex("s/bolt/Helix/")
        assert ed.text == deck_with(("Lightning Bolt", "Lightning Helix"))
        assert ed.modified is True


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_takes_a_line_number_range(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("13s/bolt/Helix/")
        assert ed.text == deck_with(("Lightning Bolt", "Lightning Helix"))


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_replaces_only_the_first_match_without_g(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("8s/g/X/")
        assert ed.lines[7] == "    4 Xoblin Guide"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_g_flag_replaces_every_match_on_the_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("8s/g/X/g")
        assert ed.lines[7] == "    4 Xoblin Xuide"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_cap_i_flag_matches_case(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("13s/bolt/Helix/I")
        assert ed.text == DECK
        ed.ex("13s/Bolt/Helix/I")
        assert ed.lines[12] == "    4 Lightning Helix"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_i_flag_ignores_case(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("13s/BOLT/Helix/i")
        assert ed.lines[12] == "    4 Lightning Helix"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_percent_s_substitutes_across_the_deck(tmp_path: Path) -> None:
    deck = DECK + "    1 Lightning Bolt\n"
    async with editor(tmp_path, deck) as ed:
        ed.ex("%s/Bolt/Helix/g")
        assert ed.text == deck.replace("Lightning Bolt", "Lightning Helix")


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_range_stops_at_its_last_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("8,9s/o/0/")
        assert ed.text == deck_with(
            ("4 Goblin Guide", "4 G0blin Guide"),
            ("2 Eidolon of", "2 Eid0lon of"),
        )


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_takes_a_mark_range(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G ma 9G mb")
        ed.ex(r"'a,'bs/\d+/9/")
        assert ed.cards[:3] == [
            "9 Goblin Guide", "9 Eidolon of the Great Revel", "3 Bonecrusher Giant // Stomp",
        ]


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_takes_an_offset_range(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G").ex(r".,+1s/\d+/9/")
        assert ed.cards[:3] == [
            "9 Goblin Guide", "9 Eidolon of the Great Revel", "3 Bonecrusher Giant // Stomp",
        ]


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_ampersand_is_the_whole_match(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("13s/bolt/[&]/")
        assert ed.lines[12] == "    4 Lightning [Bolt]"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_backslash_zero_is_the_whole_match(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(r"13s/bolt/<\0>/".replace("<", "(").replace(">", ")"))
        assert ed.lines[12] == "    4 Lightning (Bolt)"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_groups_rewrite_the_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(r"13s/(\d+) (.*)$/\2 x\1/")
        assert ed.lines[12] == "    Lightning Bolt x4"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_escaped_ampersand_is_literal(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(r"13s/bolt/a\&b/")
        assert ed.lines[12] == "    4 Lightning a&b"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_escaped_delimiter_is_literal(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(r"14s/ \/\/ / \/ /")
        assert ed.lines[13] == "    1 Fire / Ice"


@pytest.mark.primitive(":s", "/")
@pytest.mark.asyncio
async def test_s_empty_pattern_reuses_the_last_search(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("/bolt<CR>")
        ed.ex("s//Helix/")
        assert ed.lines[12] == "    4 Lightning Helix"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_with_no_match_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("13s/zzz/Helix/")
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_s_with_a_bad_regex_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("13s/(/x/")
        assert ed.is_error
        assert ed.text == DECK


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
async def test_dot_repeats_s_on_the_cursor_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13G").ex(r"s/\d+/9/")
        ed.press("8G .")
        assert ed.lines[7] == "    9 Goblin Guide"
        assert ed.lines[12] == "    9 Lightning Bolt"


@pytest.mark.primitive(":s")
@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["13s/bolt/Helix/", "%s/o/0/g", r"8,17s/\d+/1/"])
async def test_one_undo_reverts_a_substitution(tmp_path: Path, command: str) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(command)
        assert ed.text != DECK
        ed.press("u")
        assert ed.text == DECK


# ── :g ───────────────────────────────────────────────────────────


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_d_deletes_every_matching_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("g/goblin|bonecrusher/d")
        assert ed.cards == [c for c in ALL_CARDS if c not in (
            "4 Goblin Guide", "3 Bonecrusher Giant // Stomp")]


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_reaches_every_zone(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("g/guide|peace/d")
        assert ed.cards == [c for c in ALL_CARDS if c not in (
            "4 Goblin Guide", "2 Rest in Peace")]


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_reaches_prefix_style_zones(tmp_path: Path) -> None:
    deck = DECK + "SB: 1 Lava Spike\n"
    async with editor(tmp_path, deck) as ed:
        ed.ex("g/^SB:/d")
        assert "SB: 1 Lava Spike" not in ed.lines
        assert ed.cards == ALL_CARDS


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
@pytest.mark.parametrize("pattern", ["creature", "burn", "modern", "DCK"])
async def test_g_never_matches_headers_or_metadata(tmp_path: Path, pattern: str) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(f"g/{pattern}/d")
        assert ed.text == DECK


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_with_a_range_only_looks_inside_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("1,10g/o/d")
        assert ed.cards == [
            "4 Lightning Bolt", "1 Fire // Ice", "4 Sacred Foundry", "16 Mountain",
            "2 Rest in Peace",
        ]


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_from_visual_mode_uses_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G V j :")
        ed.press("g/./d<CR>")
        assert ed.cards == ALL_CARDS[2:]


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_p_lists_the_matches_without_editing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("g/bolt|ice/p")
        assert "Lightning Bolt" in ed.message
        assert "Fire // Ice" in ed.message
        assert "Goblin" not in ed.message
        assert ed.text == DECK


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_y_yanks_the_matches_into_a_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("g/bolt|ice/y a")
        assert [line.strip() for line in ed.register("a")] == [
            "4 Lightning Bolt", "1 Fire // Ice",
        ]
        assert ed.text == DECK


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_y_uppercase_register_appends(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("g/bolt/y a")
        ed.ex("g/peace/y A")
        assert [line.strip() for line in ed.register("a")] == [
            "4 Lightning Bolt", "2 Rest in Peace",
        ]


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_s_substitutes_on_the_matches(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(r"g/bolt|ice/s/\d+/9/")
        assert ed.text == deck_with(
            ("4 Lightning Bolt", "9 Lightning Bolt"), ("1 Fire // Ice", "9 Fire // Ice"),
        )


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_s_empty_pattern_is_the_g_pattern(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("g/bolt/s//Helix/")
        assert ed.text == deck_with(("Lightning Bolt", "Lightning Helix"))


FLAT_DECK = (
    "// Deck: Flat\n// Format: modern\n// Tags:\n\n"
    "// Land\n4 Sacred Foundry  @ramp\n16 Mountain\n"
)


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_s_docs_example_on_an_unindented_deck(tmp_path: Path) -> None:
    # docs/commands.md: ":g/@ramp/s/^4/3/   cut every @ramp card to three copies"
    async with editor(tmp_path, FLAT_DECK) as ed:
        ed.ex("g/@ramp/s/^4/3/")
        assert ed.cards == ["3 Sacred Foundry  @ramp", "16 Mountain"]


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_s_docs_example_on_a_block_deck(tmp_path: Path) -> None:
    deck = deck_with(("4 Sacred Foundry", "4 Sacred Foundry  @ramp"))
    async with editor(tmp_path, deck) as ed:
        ed.ex("g/@ramp/s/^4/3/")
        assert "3 Sacred Foundry  @ramp" in ed.cards


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_with_an_unsupported_command_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("g/bolt/x")
        assert ed.is_error
        assert ed.text == DECK


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
async def test_g_with_a_bad_regex_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("g/(/d")
        assert ed.is_error
        assert ed.text == DECK


@pytest.mark.primitive(":g")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command", ["g/goblin|bonecrusher/d", r"g/bolt|ice/s/\d+/9/", "g/./d"],
)
async def test_one_undo_reverts_a_global_command(tmp_path: Path, command: str) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(command)
        assert ed.text != DECK
        ed.press("u")
        assert ed.text == DECK


# ── :v and :g! ───────────────────────────────────────────────────


@pytest.mark.primitive(":v")
@pytest.mark.asyncio
async def test_v_d_deletes_every_card_not_matching(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("v/bolt|ice/d")
        assert ed.cards == ["4 Lightning Bolt", "1 Fire // Ice"]


@pytest.mark.primitive(":v")
@pytest.mark.asyncio
async def test_v_never_touches_headers_or_metadata(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("v/zzz/d")
        assert ed.cards == []
        assert ed.lines[:3] == ["// Deck: Burn", "// Format: modern", "// Tags:"]
        assert "DCK:" in ed.lines
        assert "SB:" in ed.lines


@pytest.mark.primitive(":v")
@pytest.mark.asyncio
async def test_v_p_lists_the_cards_not_matching(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("v/o/p")
        assert "Fire // Ice" in ed.message
        assert "Rest in Peace" in ed.message
        assert "Bolt" not in ed.message
        assert ed.text == DECK


@pytest.mark.primitive(":v")
@pytest.mark.asyncio
async def test_v_y_yanks_the_cards_not_matching(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("v/o/y a")
        assert [line.strip() for line in ed.register("a")] == [
            "1 Fire // Ice", "2 Rest in Peace",
        ]


@pytest.mark.primitive(":v")
@pytest.mark.asyncio
async def test_v_s_substitutes_on_the_cards_not_matching(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(r"v/o/s/\d+/7/")
        assert ed.text == deck_with(
            ("1 Fire // Ice", "7 Fire // Ice"), ("2 Rest in Peace", "7 Rest in Peace"),
        )


@pytest.mark.primitive(":v", ":g")
@pytest.mark.asyncio
async def test_g_bang_is_the_same_as_v(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("g!/bolt|ice/d")
        assert ed.cards == ["4 Lightning Bolt", "1 Fire // Ice"]


@pytest.mark.primitive(":v")
@pytest.mark.asyncio
async def test_v_with_a_range_only_looks_inside_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.ex("1,10v/goblin/d")
        assert ed.cards == ["4 Goblin Guide", *ALL_CARDS[3:]]


@pytest.mark.primitive(":v")
@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["v/bolt|ice/d", r"v/o/s/\d+/7/"])
async def test_one_undo_reverts_an_inverse_global(tmp_path: Path, command: str) -> None:
    async with editor(tmp_path) as ed:
        ed.ex(command)
        assert ed.text != DECK
        ed.press("u")
        assert ed.text == DECK
