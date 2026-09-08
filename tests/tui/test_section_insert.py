"""Tests for section insertion and cleanup — pure logic, no Textual required."""

from vimtg.domain.card import Card, Color, Prices, Rarity
from vimtg.editor.buffer import Buffer, LineType
from vimtg.tui.screens.main_screen import MainScreen


def _make_card(**overrides: object) -> Card:
    defaults = {
        "scryfall_id": "test-id",
        "name": "Lightning Bolt",
        "mana_cost": "{R}",
        "cmc": 1.0,
        "type_line": "Instant",
        "oracle_text": "",
        "colors": (Color.RED,),
        "color_identity": (Color.RED,),
        "power": None,
        "toughness": None,
        "set_code": "sta",
        "rarity": Rarity.UNCOMMON,
        "prices": Prices(),
        "legalities": {},
        "image_uri": None,
        "layout": "normal",
        "keywords": (),
    }
    defaults.update(overrides)
    return Card(**defaults)  # type: ignore[arg-type]


def _buf_from_lines(*lines: str) -> Buffer:
    return Buffer.from_text("\n".join(lines))


class TestFindTypeSectionRow:
    """Tests for MainScreen._find_type_section_row (pure, no side effects)."""

    def test_existing_section_returns_unchanged_buffer(self) -> None:
        buf = _buf_from_lines(
            "// Instant",
            "1 Lightning Bolt",
        )
        card = _make_card(name="Counterspell", type_line="Instant")

        new_buf, row = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]

        assert new_buf is buf  # buffer unchanged
        assert row == 2  # after the last card in the section

    def test_existing_section_inserts_after_last_card(self) -> None:
        buf = _buf_from_lines(
            "// Creature",
            "4 Llanowar Elves",
            "2 Tarmogoyf",
            "",
            "// Instant",
            "4 Lightning Bolt",
        )
        card = _make_card(name="Birds of Paradise", type_line="Creature")

        new_buf, row = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]

        assert new_buf is buf
        assert row == 3  # after "2 Tarmogoyf", before blank line

    def test_new_section_creates_header_at_end(self) -> None:
        buf = _buf_from_lines(
            "// Instant",
            "4 Lightning Bolt",
        )
        card = _make_card(name="Llanowar Elves", type_line="Creature")

        new_buf, row = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]

        assert row is not None
        assert new_buf is not buf  # new buffer created
        assert "// Creature" in new_buf.get_line(row - 1).text
        assert row == new_buf.line_count()  # insert at end

    def test_new_section_created_before_sideboard(self) -> None:
        buf = _buf_from_lines(
            "// Instant",
            "4 Lightning Bolt",
            "",
            "SB: 1 Duress",
        )
        card = _make_card(name="Llanowar Elves", type_line="Creature")

        new_buf, row = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]

        assert row is not None
        assert new_buf is not buf
        # Section header should be before sideboard
        assert "// Creature" in new_buf.get_line(row - 1).text
        # Sideboard entry should still exist after the new section
        sb_found = any(
            "SB: 1 Duress" in new_buf.get_line(i).text
            for i in range(new_buf.line_count())
        )
        assert sb_found

    def test_new_section_adds_blank_separator(self) -> None:
        """When previous line is content, a blank separator is added."""
        buf = _buf_from_lines(
            "// Instant",
            "4 Lightning Bolt",
        )
        card = _make_card(name="Llanowar Elves", type_line="Creature")

        new_buf, row = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]

        assert row is not None
        # Line before section header should be blank separator
        header_row = row - 1
        assert new_buf.get_line(header_row - 1).text == ""

    def test_original_buffer_not_mutated(self) -> None:
        buf = _buf_from_lines(
            "// Instant",
            "4 Lightning Bolt",
        )
        original_count = buf.line_count()
        card = _make_card(name="Llanowar Elves", type_line="Creature")

        new_buf, _ = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]

        assert buf.line_count() == original_count  # original unchanged
        assert new_buf.line_count() > original_count  # new one has additions

    def test_no_blank_separator_when_previous_is_blank(self) -> None:
        """When the line before the insert point is already blank, no extra
        blank separator is added — only the section header."""
        buf = _buf_from_lines(
            "// Instant",
            "4 Lightning Bolt",
            "",
            "SB: 1 Duress",
        )
        card = _make_card(name="Llanowar Elves", type_line="Creature")
        original_count = buf.line_count()

        new_buf, row = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]

        assert row is not None
        # Only 1 line added (header), no extra blank since line before SB is blank
        assert new_buf.line_count() == original_count + 1
        assert "// Creature" in new_buf.get_line(row - 1).text

    def test_plural_section_header_matches(self) -> None:
        """Plural section headers (// Creatures) should be found for singular type."""
        buf = _buf_from_lines(
            "// Creatures",
            "4 Llanowar Elves",
        )
        card = _make_card(name="Birds of Paradise", type_line="Creature")

        new_buf, row = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]

        assert new_buf is buf  # no new section created
        assert row == 2  # after existing cards


class TestNewSectionNormalizeStable:
    """A section created by an insert must already be in normalized form
    (blank-padded header), or the next normalize pass shifts every line
    below it and the cursor ends up on the header instead of the card."""

    def test_dck_block_new_section_is_normalize_stable(self) -> None:
        from vimtg.editor.sections import normalize_sections

        buf = _buf_from_lines(
            "DCK:",
            "",
            "    // Creature",
            "    1 Llanowar Elves",
            "",
            "SB: 1 Duress",
        )
        card = _make_card(name="Shock", type_line="Instant")
        new_buf, row = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]
        assert row is not None
        new_buf = new_buf.insert_line(row, "    1 Shock")
        assert normalize_sections(new_buf) is new_buf

    def test_legacy_new_section_is_normalize_stable(self) -> None:
        from vimtg.editor.sections import normalize_sections

        buf = _buf_from_lines(
            "// Creature",
            "1 Llanowar Elves",
        )
        card = _make_card(name="Shock", type_line="Instant")
        new_buf, row = MainScreen._find_type_section_row(None, card, buf)  # type: ignore[arg-type]
        assert row is not None
        new_buf = new_buf.insert_line(row, "1 Shock")
        assert normalize_sections(new_buf) is new_buf


def _find_empty_section_indices(buf: Buffer) -> list[int]:
    """Return indices of section headers the real normalizer would drop."""
    from vimtg.editor.sections import _drop_empty_headers

    kept = [text for text, _ in _drop_empty_headers(buf)]
    dropped: list[int] = []
    j = 0
    for i in range(buf.line_count()):
        bl = buf.get_line(i)
        if j < len(kept) and kept[j] == bl.text:
            j += 1
        elif bl.line_type == LineType.SECTION_HEADER:
            dropped.append(i)
    return dropped


class TestCleanupEmptySections:
    """Regression tests: blank lines between header and cards must not
    trick the cleanup into deleting the section header."""

    def test_section_with_blank_then_card_is_not_empty(self) -> None:
        """The exact bug scenario: 'o' on section header inserts blank
        between header and its cards — section must NOT be deleted."""
        buf = _buf_from_lines(
            "// New Deck",
            "",
            "// Creature",
            "",              # blank from 'o'
            "1 Phelddagrif",
        )

        empty = _find_empty_section_indices(buf)

        assert 2 not in empty  # // Creature must be kept

    def test_truly_empty_section_with_blanks_is_deleted(self) -> None:
        """Section header followed by blanks then another section = empty."""
        buf = _buf_from_lines(
            "// Creature",
            "",
            "// Instant",
            "4 Lightning Bolt",
        )

        empty = _find_empty_section_indices(buf)

        assert 0 in empty      # // Creature is empty
        assert 2 not in empty   # // Instant has cards

    def test_section_with_multiple_blanks_then_cards(self) -> None:
        """Multiple blanks between header and cards — still not empty."""
        buf = _buf_from_lines(
            "// Creature",
            "",
            "",
            "4 Llanowar Elves",
            "2 Tarmogoyf",
        )

        empty = _find_empty_section_indices(buf)

        assert empty == []

    def test_section_at_eof_with_no_cards(self) -> None:
        """Section header at end of buffer with only blanks = empty."""
        buf = _buf_from_lines(
            "// Instant",
            "4 Lightning Bolt",
            "",
            "// Creature",
            "",
        )

        empty = _find_empty_section_indices(buf)

        assert 3 in empty      # // Creature is empty
        assert 0 not in empty   # // Instant has cards

    def test_consecutive_empty_sections(self) -> None:
        """Two adjacent empty sections — both should be detected."""
        buf = _buf_from_lines(
            "// Creature",
            "",
            "// Instant",
            "",
            "// Sorcery",
            "4 Lightning Bolt",
        )

        empty = _find_empty_section_indices(buf)

        assert 0 in empty      # // Creature is empty
        assert 2 in empty      # // Instant is empty
        assert 4 not in empty   # // Sorcery has cards
