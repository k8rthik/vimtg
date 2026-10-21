"""Cross-layer consistency of the deck-line grammar.

The editor buffer (vimtg.editor.buffer) and the deck file parser
(vimtg.data.deck_repository) read the same text, and every card must be
the same card to both: the cursor's name, quantity and zone are what
validation, analytics and export see. These tests generate decks from a
vocabulary of awkward line shapes with a seeded generator (no hypothesis
dependency; the seeds make every failure reproducible) and check:

- buffer and parser agree, line by line, on cards, plan entries and
  plan headers;
- the buffer's incremental reclassification (set_line / insert_line /
  delete_lines) equals a full classify_lines of the same text;
- parse -> serialize -> parse is a fixed point and serialize is
  idempotent;
- the lossless export formats import back to the same deck.
"""

from __future__ import annotations

import random
from collections.abc import Iterator

import pytest

from vimtg.data.deck_repository import parse_deck_text, serialize_deck
from vimtg.domain.deck import Deck, DeckSection
from vimtg.domain.deck_lines import parse_plan_header_parts
from vimtg.editor.buffer import CARD_LINE_TYPES, Buffer, LineType, classify_lines
from vimtg.services.import_export_service import DeckFormat, ImportExportService

# Card names with every character class the grammar has to leave alone:
# split/DFC slashes, parentheses, quotes, commas, non-ASCII, digits,
# a printing suffix, and suffix tokens in canonical and odd orders.
NAMES = (
    "Lightning Bolt",
    "Fire // Ice",
    "B.F.M. (Big Furry Monster)",
    "Hazmat Suit (Used)",
    "_____",
    "Who / What / When / Where / Why",
    "Lim-Dûl's Vault",
    "Æther Vial",
    "\"Ach! Hans, Run!\"",
    "Kongming, \"Sleeping Dragon\"",
    "+2 Mace",
    "7 Wonders",
    "Goblin Guide (ZEN) 126",
    "Goblin Guide (ZEN) 126 *F*",
    "Bonecrusher Giant (PLST) ELD-115",
    "Opt  #core",
    "Opt  @draw",
    "Opt  // keep",
    "Opt #notatag",
    "Opt  @draw  #core #flex  // note #prose @prose",
    "Opt  #core  @draw",
    "Opt  //",
    "Opt  #",
    "  #tag",
    "  @cat",
    "  // only a comment",
    "\tTabbed  ",
    "Sideboard",
)
PREFIXES = (
    "", "", "", "SB: ", "MB: ", "CMD: ", "CMP: ", "sb: ", "  ", "\t", "    ", "-", "+", "  - ",
)
OTHER_LINES = (
    "",
    "",
    "   ",
    "// Deck: Test",
    "// Format: modern",
    "// Tags: a, B",
    "// Format:",
    "// a prose comment",
    "//",
    "// Creatures",
    "// Sideboard",
    "// @ramp",
    "SB:",
    "MB:",
    "CMD:",
    "CMP:",
    "DCK:",
    "sb:",
    "Sideboard",
    "sideboard:",
    "SIDEBOARD",
    "VS: Tron",
    "VS: Tron  // mull hard",
    "VS:",
    "VS: A  // ",
    "some prose",
)


def _random_line(rng: random.Random) -> str:
    if rng.random() < 0.45:
        return rng.choice(OTHER_LINES)
    return f"{rng.choice(PREFIXES)}{rng.randint(0, 5)} {rng.choice(NAMES)}"


def _random_lines(rng: random.Random, max_lines: int = 9) -> list[str]:
    return [_random_line(rng) for _ in range(rng.randint(1, max_lines))]


def _texts(seed: int, count: int) -> Iterator[tuple[int, list[str]]]:
    rng = random.Random(seed)
    for case in range(count):
        yield case, _random_lines(rng)


_SECTION_OF = {
    LineType.CARD_ENTRY: DeckSection.MAIN,
    LineType.SIDEBOARD_ENTRY: DeckSection.SIDEBOARD,
    LineType.MAYBEBOARD_ENTRY: DeckSection.MAYBEBOARD,
    LineType.COMMANDER_ENTRY: DeckSection.COMMANDER,
    LineType.COMPANION_ENTRY: DeckSection.COMPANION,
}


def _parser_view(deck: Deck) -> tuple[dict[int, object], dict[int, object], dict[int, object]]:
    cards = {
        e.line_number: (e.section, e.quantity, e.card_name, e.category, e.tags, e.comment)
        for e in deck.entries
    }
    entries = {
        pe.line_number: (pe.sign, pe.quantity, pe.card_name, pe.comment)
        for plan in deck.plans
        for pe in plan.entries
    }
    headers = {plan.line_number: (plan.name, plan.note) for plan in deck.plans}
    return cards, entries, headers


def _buffer_view(buf: Buffer) -> tuple[dict[int, object], dict[int, object], dict[int, object]]:
    cards: dict[int, object] = {}
    entries: dict[int, object] = {}
    headers: dict[int, object] = {}
    for row in range(buf.line_count()):
        bl = buf.get_line(row)
        line = row + 1  # the parser numbers lines from 1
        if bl.line_type in CARD_LINE_TYPES:
            cards[line] = (
                _SECTION_OF[bl.line_type], buf.quantity_at(row), buf.card_name_at(row),
                buf.category_at(row), buf.tags_at(row), buf.comment_at(row),
            )
        elif bl.line_type == LineType.PLAN_ENTRY:
            entries[line] = (
                buf.plan_sign_at(row), buf.quantity_at(row), buf.card_name_at(row),
                buf.comment_at(row),
            )
        elif bl.line_type == LineType.PLAN_HEADER:
            headers[line] = parse_plan_header_parts(bl.text)
    return cards, entries, headers


class TestBufferAndParserAgree:
    @pytest.mark.parametrize("seed", range(4))
    def test_every_line_is_the_same_card_to_both(self, seed: int) -> None:
        for case, lines in _texts(seed, 400):
            text = "\n".join(lines) + "\n"
            parser = _parser_view(parse_deck_text(text))
            buffer = _buffer_view(Buffer.from_text(text))
            assert buffer == parser, f"seed {seed} case {case}: {text!r}"

    def test_mtgo_sideboard_header_zones_the_lines_after_it(self) -> None:
        text = "4 Opt\nSideboard\n2 Duress\n    1 Negate\nCMD:\n    1 Tymna\n3 Bolt\n"
        buf = Buffer.from_text(text)
        assert [bl.line_type for bl in buf.get_lines()] == [
            LineType.CARD_ENTRY, LineType.COMMENT, LineType.SIDEBOARD_ENTRY,
            LineType.SIDEBOARD_ENTRY, LineType.SECTION_HEADER,
            LineType.COMMANDER_ENTRY, LineType.SIDEBOARD_ENTRY,
        ]
        assert [(e.card_name, e.section) for e in parse_deck_text(text).entries] == [
            ("Opt", DeckSection.MAIN), ("Duress", DeckSection.SIDEBOARD),
            ("Negate", DeckSection.SIDEBOARD), ("Tymna", DeckSection.COMMANDER),
            ("Bolt", DeckSection.SIDEBOARD),
        ]

    def test_nameless_and_suffixed_lines(self) -> None:
        # Tags but no name is not a card to either; a pasted printing
        # suffix is not part of the name to either
        text = "3  #tag\n4 Goblin Guide (ZEN) 126 *F*  #haste\n"
        buf = Buffer.from_text(text)
        assert buf.get_line(0).line_type == LineType.COMMENT
        assert buf.card_name_at(1) == "Goblin Guide"
        assert buf.tags_at(1) == frozenset({"haste"})
        deck = parse_deck_text(text)
        assert [(e.card_name, e.tags) for e in deck.entries] == [
            ("Goblin Guide", frozenset({"haste"}))
        ]


class TestIncrementalReclassification:
    """set_line / insert_line / delete_lines take shortcuts when an edit
    cannot change the zone of any other line. Any shortcut that is
    wrong shows up as a buffer that disagrees with a fresh
    classification of its own text."""

    @pytest.mark.parametrize("seed", range(4))
    def test_edits_match_a_full_reclassification(self, seed: int) -> None:
        rng = random.Random(seed)
        for case in range(150):
            texts = _random_lines(rng)
            buf = Buffer.from_text("\n".join(texts) + "\n")
            assert buf.get_lines() == classify_lines(texts)
            for step in range(25):
                op = rng.choice(("set", "insert", "delete", "delete_range"))
                row = rng.randrange(len(texts))
                if op == "set":
                    texts[row] = _random_line(rng)
                    buf = buf.set_line(row, texts[row])
                elif op == "insert":
                    at = rng.randint(0, len(texts))
                    line = _random_line(rng)
                    texts.insert(at, line)
                    buf = buf.insert_line(at, line)
                else:
                    end = row if op == "delete" else min(len(texts) - 1, row + rng.randint(0, 3))
                    buf, deleted = buf.delete_lines(row, end)
                    assert deleted == tuple(texts[row:end + 1])
                    del texts[row:end + 1]
                    if not texts:
                        texts = [""]  # an emptied buffer keeps one blank line
                assert buf.get_lines() == classify_lines(texts), (
                    f"seed {seed} case {case} step {step} {op}@{row}: {texts!r}"
                )


def _structure(deck: Deck) -> object:
    """A deck without its line numbers, for comparing reparsed text."""
    return (
        deck.metadata,
        sorted(
            (e.section.value, e.quantity, e.card_name, e.category, tuple(sorted(e.tags)), e.comment)
            for e in deck.entries
        ),
        [c.text for c in deck.comments],
        [
            (p.name, p.note, [(pe.sign, pe.quantity, pe.card_name, pe.comment) for pe in p.entries])
            for p in deck.plans
        ],
    )


class TestSerializeRoundTrip:
    @pytest.mark.parametrize("seed", range(4))
    def test_parse_serialize_parse_is_a_fixed_point(self, seed: int) -> None:
        for case, lines in _texts(seed, 400):
            newline = "\r\n" if case % 7 == 0 else "\n"
            text = newline.join(lines)
            deck = parse_deck_text(text)
            out = serialize_deck(deck)
            assert _structure(parse_deck_text(out)) == _structure(deck), (
                f"seed {seed} case {case}: {text!r} -> {out!r}"
            )
            assert serialize_deck(parse_deck_text(out)) == out, (
                f"seed {seed} case {case}: {out!r}"
            )

    def test_skipped_lines_are_reported_not_dropped_silently(self) -> None:
        skipped: list[int] = []
        parse_deck_text(
            "4 Opt\n3  #tag\nsb: 1 X\nVS: Tron\n    -1 #t\nprose\n",
            on_skip=lambda n, line: skipped.append(n),
        )
        assert skipped == [2, 3, 5, 6]


def _copies(deck: Deck) -> dict[tuple[DeckSection, str], int]:
    copies: dict[tuple[DeckSection, str], int] = {}
    for e in deck.entries:
        key = (e.section, e.card_name)
        copies[key] = copies.get(key, 0) + e.quantity
    return copies


class TestExportImportRoundTrip:
    """The formats that carry every zone and the full card name (no
    front-face folding) must import back to the deck they came from;
    the others document what they drop."""

    @pytest.mark.parametrize("fmt", [DeckFormat.VIMTG, DeckFormat.MOXFIELD, DeckFormat.ARCHIDEKT])
    def test_lossless_formats(self, fmt: DeckFormat) -> None:
        svc = ImportExportService()
        rng = random.Random(fmt.value)
        for case in range(120):
            lines = [
                f"{rng.choice(('', 'SB: ', 'MB: ', 'CMD: ', 'CMP: '))}{rng.randint(1, 4)} "
                f"{rng.choice(NAMES)}"
                for _ in range(rng.randint(1, 8))
            ]
            deck = parse_deck_text("\n".join(lines) + "\n")
            out = svc.export_deck(deck, fmt)
            back = svc.import_deck(out, fmt)
            assert _copies(back) == _copies(deck), f"{fmt.value} case {case}: {lines!r}\n{out}"
            # Auto-detection must land on a format that reads it the same
            # way (a bare vimtg list without metadata detects as MTGO)
            assert _copies(svc.import_deck(out)) == _copies(deck), (
                f"{fmt.value} case {case} auto-detected as {svc.detect_format(out).value}:"
                f" {lines!r}\n{out}"
            )
