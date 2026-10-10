"""Scaffold lines are display-only: saving must not add them to a file."""

from __future__ import annotations

from vimtg.services.deck_service import (
    NO_SCAFFOLD,
    needs_new_deck_prompt,
    scaffold_deck_body,
    scaffold_metadata,
    set_deck_identity,
    strip_unused_scaffold,
)


def _roundtrip(original: str) -> str:
    text, added = scaffold_metadata(original)
    return strip_unused_scaffold(text, added)


class TestStripUnusedScaffold:
    def test_hand_written_list_saves_unchanged(self) -> None:
        original = "4 Lightning Bolt\n4 Goblin Guide\n"
        assert _roundtrip(original) == original

    def test_partial_metadata_saves_unchanged(self) -> None:
        original = "// Deck: Burn\n4 Lightning Bolt\n"
        assert _roundtrip(original) == original

    def test_partial_metadata_with_blank_saves_unchanged(self) -> None:
        original = "// Deck: Burn\n\n4 Lightning Bolt\n"
        assert _roundtrip(original) == original

    def test_leading_blank_line_round_trips(self) -> None:
        original = "\n4 Lightning Bolt\n"
        assert _roundtrip(original) == original

    def test_existing_empty_metadata_round_trips(self) -> None:
        original = "// Deck: Burn\n// Format:\n// Tags:\n\n4 Lightning Bolt\n"
        assert _roundtrip(original) == original

    def test_filled_scaffold_line_is_kept(self) -> None:
        text, added = scaffold_metadata("4 Lightning Bolt\n")
        filled = text.replace("// Format:", "// Format: modern")
        assert strip_unused_scaffold(filled, added) == (
            "// Format: modern\n\n4 Lightning Bolt\n"
        )

    def test_new_deck_keeps_only_answered_keys(self) -> None:
        text, added = scaffold_metadata("")
        text = set_deck_identity(text, "Burn", "modern")
        out = strip_unused_scaffold(scaffold_deck_body(text), added)
        assert out.startswith("// Deck: Burn\n// Format: modern\n")
        assert "// Tags:" not in out

    def test_unnamed_new_deck_has_no_leading_blank(self) -> None:
        text, added = scaffold_metadata("")
        out = strip_unused_scaffold(scaffold_deck_body(text), added)
        assert out == "DCK:\n"

    def test_no_scaffold_is_identity(self) -> None:
        text = "// Deck:\n\n4 Bolt\n"
        assert strip_unused_scaffold(text, NO_SCAFFOLD) is text


class TestNewDeckPrompt:
    def test_blank_new_deck_needs_prompt(self) -> None:
        assert needs_new_deck_prompt("// Deck:\n// Format:\n\nDCK:\n")

    def test_missing_format_needs_prompt(self) -> None:
        assert needs_new_deck_prompt("// Deck: Burn\n\nDCK:\n")

    def test_named_and_formatted_does_not(self) -> None:
        assert not needs_new_deck_prompt("// Deck: Burn\n// Format: modern\n")

    def test_deck_with_cards_never_prompts(self) -> None:
        assert not needs_new_deck_prompt("4 Lightning Bolt\n")


class TestSetDeckIdentity:
    def test_fills_existing_lines(self) -> None:
        out = set_deck_identity("// Deck:\n// Format:\n// Tags:\n", "Burn", "modern")
        assert out == "// Deck: Burn\n// Format: modern\n// Tags:\n"

    def test_blank_answer_leaves_line(self) -> None:
        out = set_deck_identity("// Deck: Old\n// Format:\n", "", "pauper")
        assert out == "// Deck: Old\n// Format: pauper\n"

    def test_adds_missing_line_to_metadata_block(self) -> None:
        out = set_deck_identity("// Deck: Burn\n\nDCK:\n", "", "modern")
        assert out == "// Deck: Burn\n// Format: modern\n\nDCK:\n"

    def test_commander_gains_cmd_block(self) -> None:
        out = set_deck_identity("// Deck:\n// Format:\n\nDCK:\n", "Atraxa", "commander")
        assert out.splitlines()[3:6] == ["CMD:", "", "DCK:"]

    def test_existing_cmd_block_not_duplicated(self) -> None:
        text = "// Format:\n\nCMD:\n\nDCK:\n"
        assert set_deck_identity(text, "", "commander").count("CMD:") == 1
