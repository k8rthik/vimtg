"""Tests for the cross-deck category history store."""

from __future__ import annotations

from vimtg.config.category_history import (
    load_category_history,
    record_category,
)


class TestCategoryHistory:
    def test_empty_when_no_file(self) -> None:
        assert load_category_history() == ()

    def test_record_and_load(self) -> None:
        record_category("ramp")
        record_category("draw")
        assert load_category_history() == ("draw", "ramp")

    def test_reuse_moves_to_front(self) -> None:
        record_category("ramp")
        record_category("draw")
        record_category("ramp")
        assert load_category_history() == ("ramp", "draw")

    def test_normalizes_case_and_whitespace(self) -> None:
        record_category("  Ramp ")
        assert load_category_history() == ("ramp",)

    def test_empty_name_ignored(self) -> None:
        record_category("   ")
        assert load_category_history() == ()
