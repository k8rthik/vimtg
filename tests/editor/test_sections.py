"""Tests for section normalization (empty-header removal, blank collapsing)."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.sections import normalize_sections


class TestNormalizeSections:
    def test_clean_buffer_returns_same_object(self) -> None:
        buf = Buffer.from_text("// Creatures\n4 Goblin Guide\n\n// Lands\n20 Mountain\n")
        assert normalize_sections(buf) is buf

    def test_removes_empty_section_header(self) -> None:
        buf = Buffer.from_text("// Creatures\n\n// Lands\n20 Mountain\n")
        cleaned = normalize_sections(buf)
        assert cleaned.to_text() == "// Lands\n20 Mountain\n"

    def test_keeps_section_with_cards_after_blank(self) -> None:
        buf = Buffer.from_text("// Creatures\n\n4 Goblin Guide\n")
        cleaned = normalize_sections(buf)
        assert "// Creatures" in cleaned.to_text()

    def test_collapses_consecutive_blanks(self) -> None:
        buf = Buffer.from_text("4 Goblin Guide\n\n\n\n4 Lightning Bolt\n")
        cleaned = normalize_sections(buf)
        assert cleaned.to_text() == "4 Goblin Guide\n\n4 Lightning Bolt\n"

    def test_pads_blank_before_header(self) -> None:
        buf = Buffer.from_text("4 Goblin Guide\n// Lands\n20 Mountain\n")
        cleaned = normalize_sections(buf)
        assert cleaned.to_text() == "4 Goblin Guide\n\n// Lands\n20 Mountain\n"

    def test_no_padding_after_metadata(self) -> None:
        buf = Buffer.from_text("// Deck: Burn\n// Creatures\n4 Goblin Guide\n")
        cleaned = normalize_sections(buf)
        assert cleaned.to_text() == "// Deck: Burn\n// Creatures\n4 Goblin Guide\n"

    def test_empty_buffer_unchanged(self) -> None:
        buf = Buffer.from_text("\n")
        assert normalize_sections(buf) is buf

    def test_idempotent(self) -> None:
        buf = Buffer.from_text("// Creatures\n\n// Lands\n\n\n20 Mountain\n// Spells\n")
        once = normalize_sections(buf)
        assert normalize_sections(once) is once


class TestMaybeboardSections:
    def test_header_with_only_maybeboard_cards_survives(self) -> None:
        """A section whose cards are all MB: lines is not empty (regression:
        the card-type set was a stale copy missing MAYBEBOARD_ENTRY)."""
        buf = Buffer.from_text("// Maybeboard\nMB: 2 Opt\nMB: 1 Shock\n")
        cleaned = normalize_sections(buf)
        assert "// Maybeboard" in cleaned.to_text()
        assert "MB: 2 Opt" in cleaned.to_text()


class TestTypeSectionInsertRow:
    """Type-section lookup must speak one vocabulary: singular, plural,
    and case variants of a type header are the same section, and a new
    header is written in the canonical plural form the regroup uses."""

    def _buf(self, *lines: str) -> Buffer:
        return Buffer.from_text("\n".join(lines) + "\n")

    def test_sorcery_joins_existing_sorceries_header(self) -> None:
        from vimtg.editor.sections import type_section_insert_row

        buf = self._buf("// Sorceries", "4 Ponder", "", "// Lands", "20 Island")
        new_buf, row = type_section_insert_row(buf, "Sorcery")
        assert new_buf is buf
        assert row == 2

    def test_sorceries_joins_existing_sorcery_header(self) -> None:
        from vimtg.editor.sections import type_section_insert_row

        buf = self._buf("// Sorcery", "4 Ponder")
        new_buf, row = type_section_insert_row(buf, "Sorceries")
        assert new_buf is buf
        assert row == 2

    def test_indented_header_inside_dck_block_matches(self) -> None:
        from vimtg.editor.sections import type_section_insert_row

        buf = self._buf("DCK:", "    // Sorceries", "    4 Ponder")
        new_buf, row = type_section_insert_row(buf, "Sorcery")
        assert new_buf is buf
        assert row == 3

    def test_new_header_uses_canonical_plural(self) -> None:
        from vimtg.editor.sections import type_section_insert_row

        buf = self._buf("// Creatures", "4 Llanowar Elves")
        new_buf, row = type_section_insert_row(buf, "Sorcery")
        assert new_buf.get_line(row - 1).text == "// Sorceries"

    def test_compound_header_is_not_the_type_section(self) -> None:
        from vimtg.editor.sections import type_section_insert_row

        # Substring matching used to drop artifacts under '// Artifact Lands'
        buf = self._buf("// Artifact Lands", "4 Seat of the Synod")
        new_buf, row = type_section_insert_row(buf, "Artifact")
        assert new_buf is not buf
        assert new_buf.get_line(row - 1).text == "// Artifacts"

    def test_category_header_is_not_the_type_section(self) -> None:
        from vimtg.editor.sections import type_section_insert_row

        buf = self._buf("// @Sorceries", "4 Ponder")
        new_buf, row = type_section_insert_row(buf, "Sorcery")
        assert new_buf is not buf
        assert new_buf.get_line(row - 1).text == "// Sorceries"

    def test_other_section_matches_exactly(self) -> None:
        from vimtg.editor.sections import type_section_insert_row

        buf = self._buf("// Other", "1 Conspiracy Card")
        new_buf, row = type_section_insert_row(buf, "Other")
        assert new_buf is buf
        assert row == 2


class TestNormalizeMergesDuplicateSections:
    """Two headers with the same key are one section: the later one's
    cards fold into the earlier, and the emptied header is dropped."""

    def test_sorcery_folds_into_sorceries(self) -> None:
        buf = Buffer.from_text(
            "// Sorceries\n4 Ponder\n\n// Lands\n20 Island\n\n// Sorcery\n2 Preordain\n"
        )
        out = normalize_sections(buf).to_text().splitlines()
        assert out == [
            "// Sorceries", "4 Ponder", "2 Preordain", "", "// Lands", "20 Island",
        ]

    def test_category_duplicates_merge(self) -> None:
        buf = Buffer.from_text(
            "// @ramp\n1 Cultivate\n\n// @draw\n1 Opt\n\n// @ramp\n1 Farseek\n"
        )
        out = normalize_sections(buf).to_text().splitlines()
        assert out == ["// @ramp", "1 Cultivate", "1 Farseek", "", "// @draw", "1 Opt"]

    def test_indented_block_sections_merge_within_block(self) -> None:
        buf = Buffer.from_text(
            "DCK:\n    // Creatures\n    4 Elves\n\n    // Lands\n    20 Forest\n\n"
            "    // Creature\n    2 Goyf\n"
        )
        out = normalize_sections(buf).to_text().splitlines()
        assert out == [
            "DCK:", "", "    // Creatures", "    4 Elves", "    2 Goyf", "",
            "    // Lands", "    20 Forest",
        ]

    def test_different_depths_are_not_merged(self) -> None:
        # A top-level header and one inside the DCK: block are different
        # sections — moving lines across the block boundary would rezone
        buf = Buffer.from_text(
            "// Sorcery\n2 Preordain\n\nDCK:\n\n    // Sorceries\n    4 Ponder\n"
        )
        assert normalize_sections(buf) is buf

    def test_fixed_labels_are_not_merged(self) -> None:
        buf = Buffer.from_text("// Other\n1 A\n\n// Lands\n1 Forest\n\n// Other\n1 B\n")
        assert normalize_sections(buf) is buf

    def test_zone_headers_are_not_merged(self) -> None:
        buf = Buffer.from_text(
            "// Sideboard\nSB: 1 A\n\n// Lands\n1 Forest\n\n// Sideboard\nSB: 1 B\n"
        )
        assert normalize_sections(buf) is buf


class TestExtentAgreement:
    """The counts, cleanup, and insert paths read one section model, so
    the same buffer can never be 'occupied' to one and 'empty' to another."""

    def test_counts_and_cleanup_agree_on_foreign_line(self) -> None:
        from vimtg.editor.header_counts import header_counts

        buf = Buffer.from_text("// Creatures\n\nSB: 1 Duress\n4 Elves\n")
        assert header_counts(buf)[0].main == 4
        assert "// Creatures" in normalize_sections(buf).to_text()

    def test_counts_and_cleanup_agree_on_empty(self) -> None:
        from vimtg.editor.header_counts import header_counts

        buf = Buffer.from_text("// Creatures\n\nSB: 1 Duress\n\n// Lands\n4 Forest\n")
        assert 0 not in header_counts(buf)
        assert "// Creatures" not in normalize_sections(buf).to_text()

    def test_insert_row_skips_comment_under_header(self) -> None:
        from vimtg.editor.sections import type_section_insert_row

        buf = Buffer.from_text("// Creatures\n// keep these\n4 Elves\n")
        _, row = type_section_insert_row(buf, "Creature")
        assert row == 3
