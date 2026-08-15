"""Tests for buffer linting (validation mapped to buffer rows)."""

from vimtg.data.deck_repository import parse_deck_text
from vimtg.editor.buffer import Buffer
from vimtg.editor.lint import EMPTY_LINT, effective_format, lint_buffer


class TestEffectiveFormat:
    def test_deck_format_wins(self):
        deck = parse_deck_text("// Format: commander\n")
        assert effective_format(deck, "modern") == "commander"

    def test_falls_back_to_default(self):
        deck = parse_deck_text("// Format:\n")
        assert effective_format(deck, "modern") == "modern"

    def test_empty_everywhere(self):
        deck = parse_deck_text("4 Bolt\n")
        assert effective_format(deck, "") == ""


class TestLintBuffer:
    def test_row_mapping_is_zero_based(self):
        text = "// Deck: X\n0 Bolt\n"
        result = lint_buffer(Buffer.from_text(text), {})
        assert 1 in result.line_errors
        assert "Invalid quantity" in result.line_errors[1].message

    def test_deck_level_errors_split_out(self):
        text = "// Format: commander\n99 Island\n"
        result = lint_buffer(Buffer.from_text(text), {})
        assert any("No commander" in e.message for e in result.deck_errors)
        assert any("100" in e.message for e in result.deck_errors)

    def test_counts(self):
        text = "// Format: commander\n0 Bolt\n"
        result = lint_buffer(Buffer.from_text(text), {})
        assert result.error_count >= 1
        assert result.error_count + result.warning_count == len(
            result.deck_errors
        ) + len(result.line_errors)

    def test_error_beats_warning_per_row(self):
        # Row has both an invalid quantity (error) and unknown name (warning)
        text = "0 Xyzzy\n"
        from vimtg.domain.card import Card

        bolt = Card.from_scryfall({"id": "x", "name": "Bolt"})
        result = lint_buffer(Buffer.from_text(text), {"Bolt": bolt})
        assert result.line_errors[0].level == "error"

    def test_clean_buffer(self):
        result = lint_buffer(Buffer.from_text("60 Mountain\n"), {})
        assert result.line_errors == {}
        assert result.error_count == 0

    def test_empty_lint_constant(self):
        assert EMPTY_LINT.line_errors == {}
        assert EMPTY_LINT.error_count == 0

    def test_default_format_applies(self):
        text = "5 Bolt\n55 Mountain\n"
        result = lint_buffer(
            Buffer.from_text(text), {}, default_format="modern"
        )
        assert 0 in result.line_errors
        assert result.line_errors[0].level == "error"
