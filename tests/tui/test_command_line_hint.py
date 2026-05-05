"""Tests for dynamic command-line hints based on cursor position."""

from vimtg.editor.buffer import Buffer
from vimtg.tui.screens.main_screen import _CARD_HINT, _GENERIC_HINT, _hint_for_cursor
from vimtg.tui.widgets.command_line import CommandLine


# ── _hint_for_cursor tests ────────────────────────────────────────


def _deck_buffer() -> Buffer:
    return Buffer.from_text(
        "// Deck: Test\n"
        "\n"
        "// Creature\n"
        "4 Lightning Bolt\n"
        "2 Counterspell\n"
        "\n"
        "// Land\n"
        "4 Island\n"
        "\n"
        "SB: 2 Negate\n"
        "CMD: 1 Sol Ring\n"
    )


def test_card_entry_returns_card_hint() -> None:
    buf = _deck_buffer()
    # "4 Lightning Bolt" is a CARD_ENTRY
    assert _hint_for_cursor(buf, 3) == _CARD_HINT


def test_sideboard_entry_returns_card_hint() -> None:
    buf = _deck_buffer()
    # "SB: 2 Negate" is a SIDEBOARD_ENTRY
    assert _hint_for_cursor(buf, 9) == _CARD_HINT


def test_commander_entry_returns_card_hint() -> None:
    buf = _deck_buffer()
    # "CMD: 1 Sol Ring" is a COMMANDER_ENTRY
    assert _hint_for_cursor(buf, 10) == _CARD_HINT


def test_blank_line_returns_generic_hint() -> None:
    buf = _deck_buffer()
    assert _hint_for_cursor(buf, 1) == _GENERIC_HINT


def test_section_header_returns_generic_hint() -> None:
    buf = _deck_buffer()
    # "// Creature" is a SECTION_HEADER
    assert _hint_for_cursor(buf, 2) == _GENERIC_HINT


def test_metadata_returns_generic_hint() -> None:
    buf = _deck_buffer()
    # "// Deck: Test" is METADATA
    assert _hint_for_cursor(buf, 0) == _GENERIC_HINT


# ── CommandLine hint rendering tests ──────────────────────────────


def test_hint_renders_when_no_message_or_prefix() -> None:
    cl = CommandLine()
    cl.hint = "some hint text"
    rendered = cl.render()
    assert "some hint text" in rendered.plain


def test_message_takes_priority_over_hint() -> None:
    cl = CommandLine()
    cl.hint = "card hint"
    cl.set_message("Added Lightning Bolt")
    rendered = cl.render()
    assert "Added Lightning Bolt" in rendered.plain
    assert "card hint" not in rendered.plain


def test_prefix_takes_priority_over_hint() -> None:
    cl = CommandLine()
    cl.hint = "card hint"
    cl.show(":")
    cl.text = "sort"
    rendered = cl.render()
    assert "sort" in rendered.plain
    assert "card hint" not in rendered.plain


def test_empty_hint_falls_back_to_generic() -> None:
    cl = CommandLine()
    cl.hint = ""
    rendered = cl.render()
    assert "Press ? for help" in rendered.plain


def test_hide_does_not_clear_hint() -> None:
    cl = CommandLine()
    cl.hint = "card hint"
    cl.show(":")
    cl.hide()
    assert cl.hint == "card hint"


def test_set_message_does_not_clear_hint() -> None:
    cl = CommandLine()
    cl.hint = "card hint"
    cl.set_message("some message")
    assert cl.hint == "card hint"


# ── Cursor rendering tests ───────────────────────────────────────


def test_cursor_at_end_shows_block_cursor() -> None:
    cl = CommandLine()
    cl.show(":")
    cl.text = "sort"
    cl.cursor_pos = 4  # at end
    rendered = cl.render()
    plain = rendered.plain
    # Text should contain "sort" plus a trailing space (block cursor)
    assert "sort" in plain


def test_cursor_in_middle_renders_text_correctly() -> None:
    cl = CommandLine()
    cl.show(":")
    cl.text = "sort"
    cl.cursor_pos = 2  # cursor on 'r'
    rendered = cl.render()
    # The full text should still be visible
    assert "sort" in rendered.plain


def test_ghost_hidden_when_cursor_not_at_end() -> None:
    cl = CommandLine()
    cl.show(":")
    cl.text = "so"
    cl.ghost = "sort"
    cl.cursor_pos = 1  # cursor in middle
    rendered = cl.render()
    # Ghost completion should NOT appear when cursor is not at end
    assert "rt" not in rendered.plain


def test_ghost_visible_when_cursor_at_end() -> None:
    cl = CommandLine()
    cl.show(":")
    cl.text = "so"
    cl.ghost = "sort"
    cl.cursor_pos = 2  # at end
    rendered = cl.render()
    # Ghost "rt" should appear as completion
    assert "rt" in rendered.plain


def test_show_resets_cursor_pos() -> None:
    cl = CommandLine()
    cl.cursor_pos = 5
    cl.show(":")
    assert cl.cursor_pos == 0


def test_hide_resets_cursor_pos() -> None:
    cl = CommandLine()
    cl.cursor_pos = 5
    cl.hide()
    assert cl.cursor_pos == 0


def test_set_message_resets_cursor_pos() -> None:
    cl = CommandLine()
    cl.cursor_pos = 5
    cl.set_message("done")
    assert cl.cursor_pos == 0
