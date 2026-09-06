"""Tests for header_counts — render-time card totals for header lines."""

from vimtg.editor.buffer import Buffer
from vimtg.editor.header_counts import HeaderCount, header_counts


def _row(buf: Buffer, needle: str) -> int:
    """Index of the first line containing `needle`."""
    for i in range(buf.line_count()):
        if needle in buf.get_line(i).text:
            return i
    raise AssertionError(f"no line contains {needle!r}")


class TestTypeSections:
    def test_section_sums_quantities_until_next_header(self) -> None:
        buf = Buffer.from_text(
            "// Creatures\n4 Bear\n2 Wolf\n\n// Lands\n20 Forest\n"
        )
        counts = header_counts(buf)
        assert counts[_row(buf, "Creatures")] == HeaderCount(6)
        assert counts[_row(buf, "Lands")] == HeaderCount(20)

    def test_category_header_counts_its_cards(self) -> None:
        buf = Buffer.from_text("// @ramp\n3 Rampant Growth\n1 Cultivate\n")
        counts = header_counts(buf)
        assert counts[_row(buf, "@ramp")] == HeaderCount(4)

    def test_blanks_and_comments_inside_section_are_skipped(self) -> None:
        buf = Buffer.from_text(
            "// Creatures\n4 Bear\n// just a note\n\n2 Wolf\n"
        )
        counts = header_counts(buf)
        assert counts[_row(buf, "Creatures")] == HeaderCount(6)

    def test_other_zone_lines_do_not_count_toward_type_section(self) -> None:
        buf = Buffer.from_text("// Creatures\n4 Bear\nSB: 2 Duress\n")
        counts = header_counts(buf)
        assert counts[_row(buf, "Creatures")] == HeaderCount(4)

    def test_sideboard_label_counts_sideboard_lines(self) -> None:
        buf = Buffer.from_text("4 Bear\n\n// Sideboard\nSB: 3 Duress\n")
        counts = header_counts(buf)
        assert counts[_row(buf, "Sideboard")] == HeaderCount(3)


class TestZoneBlocks:
    def test_zone_headers_show_zone_totals(self) -> None:
        buf = Buffer.from_text(
            "DCK:\n\n    // Creatures\n    4 Bear\n\n"
            "    // Lands\n    20 Forest\n\nSB:\n\n    3 Duress\n"
        )
        counts = header_counts(buf)
        assert counts[_row(buf, "DCK:")] == HeaderCount(24)
        assert counts[_row(buf, "SB:")] == HeaderCount(3)
        assert counts[_row(buf, "Creatures")] == HeaderCount(4)
        assert counts[_row(buf, "Lands")] == HeaderCount(20)

    def test_empty_zone_header_is_omitted(self) -> None:
        buf = Buffer.from_text("MB:\n\n4 Bear\n")
        counts = header_counts(buf)
        assert _row(buf, "MB:") not in counts


class TestDeckMetadata:
    def test_deck_line_shows_main_deck_total(self) -> None:
        buf = Buffer.from_text("// Deck: Test\n\n4 Bear\n2 Wolf\n")
        counts = header_counts(buf)
        assert counts[_row(buf, "Deck:")] == HeaderCount(6)

    def test_deck_total_includes_commander_and_companion(self) -> None:
        buf = Buffer.from_text(
            "// Deck: EDH\n\nCMD:\n\n    1 Atraxa, Praetors' Voice\n\n"
            "DCK:\n\n    99 Forest\n"
        )
        counts = header_counts(buf)
        assert counts[_row(buf, "// Deck:")] == HeaderCount(100)
        assert counts[_row(buf, "CMD:")] == HeaderCount(1)

    def test_deck_line_splits_main_and_sideboard(self) -> None:
        buf = Buffer.from_text(
            "// Deck: Test\n\n4 Bear\nSB: 3 Duress\nMB: 2 Opt\n"
        )
        counts = header_counts(buf)
        assert counts[_row(buf, "// Deck:")] == HeaderCount(4, side=3)

    def test_maybeboard_never_counts_toward_deck_line(self) -> None:
        buf = Buffer.from_text("// Deck: Test\n\n4 Bear\nMB: 2 Opt\n")
        counts = header_counts(buf)
        assert counts[_row(buf, "// Deck:")] == HeaderCount(4)

    def test_sideboard_only_deck_still_annotated(self) -> None:
        buf = Buffer.from_text("// Deck: Test\n\nSB: 3 Duress\n")
        counts = header_counts(buf)
        assert counts[_row(buf, "// Deck:")] == HeaderCount(0, side=3)

    def test_other_metadata_lines_are_not_annotated(self) -> None:
        buf = Buffer.from_text("// Deck: Test\n// Format: modern\n\n4 Bear\n")
        counts = header_counts(buf)
        assert _row(buf, "Format:") not in counts

    def test_empty_deck_omits_deck_line(self) -> None:
        buf = Buffer.from_text("// Deck: Test\n")
        counts = header_counts(buf)
        assert counts == {}


def test_plain_comment_is_not_annotated() -> None:
    buf = Buffer.from_text("// just prose\n4 Bear\n")
    assert _row(buf, "prose") not in header_counts(buf)
