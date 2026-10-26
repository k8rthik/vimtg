"""Import, export, clipboard, validate, collection and sync primitives.

Expected outputs come from docs/commands.md (Import / export, Collection,
Analytics) and the README's "Import, export, and clipboard" section. The
`clipboard` fixture is an in-memory clipboard, never the real one.
"""

from __future__ import annotations

import csv
import io
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.conftest import FakeClipboard
from tests.primitives.harness import DECK, Ed, editor
from tests.primitives.test_files_and_panes_helpers import (
    LEGAL_MODERN,
    ex,
    in_editor,
    settle,
    shown,
)
from vimtg.config.paths import config_dir

pytestmark = pytest.mark.asyncio

EDITED = DECK.replace("    4 Goblin Guide\n", "")
DELETE_GUIDE = "8Gdd"
NO_COLLECTION = "No collection loaded (:collection path.csv)"
ZONES = ("CMD:", "DCK:", "SB:", "MB:")


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _zone_of(text: str, card_line: str) -> str:
    """The zone header ('DCK:', 'SB:', ...) a card line sits under."""
    lines = [line.strip() for line in text.splitlines()]
    zone = ""
    for line in lines:
        if line in ZONES:
            zone = line
        if line == card_line:
            return zone
    raise AssertionError(f"{card_line!r} not in deck:\n{text}")


def _rows(text: str) -> list[dict[str, str]]:
    """CSV rows keyed by lower-cased header."""
    reader = csv.DictReader(io.StringIO(text))
    return [{k.lower(): v for k, v in row.items()} for row in reader]


def _read(tmp_path: Path, name: str) -> str:
    """The file's text exactly as written (no newline translation)."""
    return (tmp_path / name).read_bytes().decode("utf-8")


# ── :export, one format at a time ───────────────────────────────────


@pytest.mark.primitive(":export")
async def test_export_arena_writes_client_names_with_a_sideboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export arena out.txt"))
        assert ed.is_error is False
    lines = _read(tmp_path, "out.txt").splitlines()
    # the adventure card by its front face, the split card by both halves
    for line in ("4 Goblin Guide", "3 Bonecrusher Giant", "1 Fire // Ice", "16 Mountain"):
        assert line in lines
    assert not any("Stomp" in line for line in lines)
    assert not any("(" in line for line in lines)  # no set codes
    side = next(i for i, line in enumerate(lines) if line.lower() == "sideboard")
    assert lines.index("2 Rest in Peace") > side
    assert lines.index("4 Lightning Bolt") < side


@pytest.mark.primitive(":export")
async def test_export_mtgo_writes_the_sideboard_after_the_main_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export mtgo out.txt"))
        assert ed.is_error is False
    main, _, side = _read(tmp_path, "out.txt").partition("\n\n")
    assert "3 Bonecrusher Giant" in main.splitlines()
    assert "4 Lightning Bolt" in main.splitlines()
    assert "Rest in Peace" not in main
    assert "2 Rest in Peace" in side.splitlines()


@pytest.mark.primitive(":export")
async def test_export_dek_writes_mtgo_xml(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export dek out.dek"))
        assert ed.is_error is False
    root = ET.fromstring(_read(tmp_path, "out.dek"))
    cards = {
        (c.get("Name"), c.get("Quantity"), c.get("Sideboard"))
        for c in root.iter("Cards")
    }
    assert ("Bonecrusher Giant", "3", "false") in cards
    assert ("Fire // Ice", "1", "false") in cards
    assert ("Rest in Peace", "2", "true") in cards
    assert len(cards) == 8


@pytest.mark.primitive(":export")
async def test_export_moxfield_writes_csv_with_full_names(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export moxfield out.csv"))
        assert ed.is_error is False
    counts = {r["name"]: r["count"] for r in _rows(_read(tmp_path, "out.csv"))}
    assert counts["Bonecrusher Giant // Stomp"] == "3"
    assert counts["Mountain"] == "16"
    assert counts["Rest in Peace"] == "2"


@pytest.mark.primitive(":export")
async def test_export_archidekt_keeps_zones_in_categories(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export archidekt out.csv"))
        assert ed.is_error is False
    rows = {r["name"]: r for r in _rows(_read(tmp_path, "out.csv"))}
    assert rows["Bonecrusher Giant // Stomp"]["quantity"] == "3"
    assert rows["Rest in Peace"]["categories"] == "Sideboard"
    assert rows["Lightning Bolt"]["categories"] != "Sideboard"


LIST_DECK = (
    "// Deck: List\n// Format: modern\n\n"
    "DCK:\n    4 Lightning Bolt\n    3 Bonecrusher Giant // Stomp\n    16 Mountain\n\n"
    "SB:\n    1 Lightning Bolt\n    2 Rest in Peace\n\n"
    "MB:\n    1 Goblin Guide\n"
)


@pytest.mark.primitive(":export")
async def test_export_list_writes_bare_summed_lines_without_the_maybeboard(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, LIST_DECK) as ed:
        ed.press(ex("export list out.txt"))
        assert ed.is_error is False
    lines = _read(tmp_path, "out.txt").splitlines()
    assert sorted(lines) == sorted(
        ["5 Lightning Bolt", "3 Bonecrusher Giant", "16 Mountain", "2 Rest in Peace"]
    )
    assert lines[-1] == "2 Rest in Peace"


@pytest.mark.primitive(":export")
@pytest.mark.xfail(
    strict=True,
    reason="DOC: :export list writes '1 Fire' for the split card Fire // Ice; docs say "
    "'front faces only' yet promise a list that pastes into store mass entry, "
    "which needs 'Fire // Ice' (as Arena and .dek write it)",
)
async def test_export_list_names_a_split_card_by_both_halves(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export list out.txt"))
    assert "1 Fire // Ice" in _read(tmp_path, "out.txt").splitlines()


@pytest.mark.primitive(":export", ":w")
async def test_export_vimtg_is_the_text_w_writes(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE + ex("export vimtg copy.deck") + ex("w"))
        assert _read(tmp_path, "copy.deck") == ed.saved() == EDITED


@pytest.mark.primitive(":export")
async def test_export_guide_writes_the_plans_as_markdown(tmp_path: Path) -> None:
    deck = LEGAL_MODERN + "\nVS: Tron\n    -2 Lightning Bolt\n    +2 Rest in Peace\n"
    async with editor(tmp_path, deck) as ed:
        ed.press(ex("export guide guide.md"))
        assert ed.is_error is False
    guide = _read(tmp_path, "guide.md")
    assert any(line.startswith("#") and "Tron" in line for line in guide.splitlines())
    assert "Lightning Bolt" in guide
    assert "Rest in Peace" in guide


# ── :export, shared behaviour ───────────────────────────────────────


@pytest.mark.primitive(":export")
@pytest.mark.parametrize(
    "fmt", ["arena", "mtgo", "dek", "moxfield", "archidekt", "list", "vimtg"]
)
async def test_export_without_a_file_copies_the_same_text_to_the_clipboard(
    tmp_path: Path, clipboard: FakeClipboard, fmt: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex(f"export {fmt} out.txt") + ex(f"export {fmt}"))
        assert ed.is_error is False
        assert ed.text == DECK
    assert clipboard.text == _read(tmp_path, "out.txt")


@pytest.mark.primitive(":export")
async def test_export_refuses_an_existing_file_with_e13(tmp_path: Path) -> None:
    (tmp_path / "out.txt").write_text("keep me\n", encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(ex("export arena out.txt"))
        assert ed.is_error is True
        assert "E13" in ed.message
    assert _read(tmp_path, "out.txt") == "keep me\n"


@pytest.mark.primitive(":export")
async def test_export_bang_overwrites_an_existing_file(tmp_path: Path) -> None:
    (tmp_path / "out.txt").write_text("keep me\n", encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(ex("export! arena out.txt"))
        assert ed.is_error is False
    assert "4 Lightning Bolt" in _read(tmp_path, "out.txt").splitlines()


@pytest.mark.primitive(":export")
async def test_export_never_writes_over_the_open_deck_even_with_bang(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export! arena burn.deck"))
        assert ed.is_error is True
        assert ed.saved() == DECK


@pytest.mark.primitive(":export")
@pytest.mark.parametrize("args", ["", "nosuchformat out.txt"])
async def test_export_without_a_known_format_is_an_error(tmp_path: Path, args: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex(f"export {args}".strip()))
        assert ed.is_error is True
        assert ed.text == DECK
    assert not (tmp_path / "out.txt").exists()


@pytest.mark.primitive(":export", ":collection")
async def test_export_missing_lists_what_the_collection_lacks(tmp_path: Path) -> None:
    (tmp_path / "coll.csv").write_text(
        "Name,Count\nLightning Bolt,4\nMountain,10\n", encoding="utf-8"
    )
    async with editor(tmp_path) as ed:
        ed.press(ex("collection coll.csv") + ex("export missing need.txt"))
        assert ed.is_error is False
    main, _, side = _read(tmp_path, "need.txt").partition("\n\n")
    main_lines = main.splitlines()
    assert "4 Goblin Guide" in main_lines
    assert "6 Mountain" in main_lines
    assert "4 Sacred Foundry" in main_lines
    assert not any("Lightning Bolt" in line for line in main_lines)
    assert side.strip().splitlines() == ["2 Rest in Peace"]


@pytest.mark.primitive(":export")
async def test_export_missing_without_a_collection_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export missing need.txt"))
        assert ed.is_error is True
        assert NO_COLLECTION in ed.message
    assert not (tmp_path / "need.txt").exists()


# ── :clipboard ──────────────────────────────────────────────────────


@pytest.mark.primitive(":clipboard")
async def test_clipboard_copies_the_deck_as_arena_by_default(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export arena out.txt") + ex("clipboard"))
        assert ed.is_error is False
        assert "Copied" in ed.message
        assert ed.text == DECK
    assert clipboard.text == _read(tmp_path, "out.txt")


@pytest.mark.primitive(":clipboard")
async def test_clipboard_takes_any_export_format(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("export moxfield out.csv") + ex("clipboard moxfield"))
        assert ed.is_error is False
    assert clipboard.text == _read(tmp_path, "out.csv")


@pytest.mark.primitive(":clipboard")
async def test_clipboard_with_an_unknown_format_is_an_error(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("clipboard nosuchformat"))
        assert ed.is_error is True
        assert ed.text == DECK
    assert clipboard.text is None


# ── :import ─────────────────────────────────────────────────────────

MTGO_LIST = "4 Lightning Bolt\n2 Fire/Ice\n20 Mountain\n\n2 Rest in Peace\n"


async def _imported(ed: Ed, command: str) -> None:
    ed.press(ex(command))
    await settle(ed)
    assert in_editor(ed)


@pytest.mark.primitive(":import")
async def test_import_file_opens_it_as_a_new_unsaved_deck(tmp_path: Path) -> None:
    (tmp_path / "list.txt").write_text(MTGO_LIST, encoding="utf-8")
    async with editor(tmp_path) as ed:
        await _imported(ed, "import list.txt")
        text = ed.text
        assert _zone_of(text, "4 Lightning Bolt") == "DCK:"
        assert _zone_of(text, "2 Fire // Ice") == "DCK:"  # official name
        assert _zone_of(text, "20 Mountain") == "DCK:"
        assert _zone_of(text, "2 Rest in Peace") == "SB:"
        assert ed.modified is True
        assert ed.saved() == DECK  # the open deck is left as it is on disk


@pytest.mark.primitive(":import", ":q")
async def test_import_result_needs_a_write_before_q(tmp_path: Path) -> None:
    (tmp_path / "list.txt").write_text(MTGO_LIST, encoding="utf-8")
    async with editor(tmp_path) as ed:
        await _imported(ed, "import list.txt")
        ed.press(ex("q"))
        assert ed.message.startswith("E37")


@pytest.mark.primitive(":import")
async def test_import_with_unsaved_changes_is_refused_with_e37(tmp_path: Path) -> None:
    (tmp_path / "list.txt").write_text(MTGO_LIST, encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE)
        await _imported(ed, "import list.txt")
        assert ed.message.startswith("E37")
        assert ed.text == EDITED


@pytest.mark.primitive(":import")
async def test_import_bang_drops_changes_for_the_imported_deck(tmp_path: Path) -> None:
    (tmp_path / "list.txt").write_text(MTGO_LIST, encoding="utf-8")
    async with editor(tmp_path) as ed:
        ed.press(DELETE_GUIDE)
        await _imported(ed, "import! list.txt")
        assert "4 Lightning Bolt" in ed.cards
        assert "4 Goblin Guide" not in ed.cards
        assert ed.saved() == DECK


@pytest.mark.primitive(":import")
async def test_import_a_missing_file_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await _imported(ed, "import nosuch.txt")
        assert ed.is_error is True
        assert ed.text == DECK


@pytest.mark.primitive(":import")
async def test_import_alone_reads_the_clipboard_decklist(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    clipboard.text = "4 Goblin Guide\n16 Mountain\n"
    async with editor(tmp_path) as ed:
        await _imported(ed, "import")
        assert sorted(ed.cards) == ["16 Mountain", "4 Goblin Guide"]
        assert ed.modified is True
        assert ed.saved() == DECK


@pytest.mark.primitive(":import")
async def test_import_alone_with_an_empty_clipboard_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await _imported(ed, "import")
        assert ed.is_error is True
        assert ed.text == DECK


# ── :validate ───────────────────────────────────────────────────────


def _report(ed: Ed) -> str:
    """The validation report: the command line, or the pager when long."""
    return ed.message if in_editor(ed) else shown(ed, "#help-body")


@pytest.mark.primitive(":validate")
async def test_validate_a_legal_deck_reports_it_ok(tmp_path: Path) -> None:
    async with editor(tmp_path, LEGAL_MODERN) as ed:
        before = ed.text
        ed.press(ex("validate"))
        await settle(ed)
        assert ed.is_error is False
        assert "OK" in ed.message
        assert ed.text == before


@pytest.mark.primitive(":validate")
async def test_validate_flags_a_copy_limit_error(tmp_path: Path) -> None:
    deck = LEGAL_MODERN.replace("4 Lightning Bolt", "5 Lightning Bolt").replace(
        "32 Mountain", "31 Mountain"
    )
    async with editor(tmp_path, deck) as ed:
        ed.press(ex("validate"))
        await settle(ed)
        assert ed.is_error is True
        assert "Lightning Bolt" in _report(ed)


@pytest.mark.primitive(":validate")
async def test_validate_reports_a_short_deck_against_the_minimum(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:  # 34 mainboard cards
        ed.press(ex("validate"))
        await settle(ed)
        assert "60" in _report(ed)
        assert ed.text == DECK


@pytest.mark.primitive(":validate")
async def test_validate_without_card_data_says_legality_was_skipped(tmp_path: Path) -> None:
    async with editor(tmp_path, LEGAL_MODERN, cards=False) as ed:
        ed.press(ex("validate"))
        await settle(ed)
        report = _report(ed)
        assert "skipped" in report
        assert ":sync" in report


@pytest.mark.primitive(":validate")
async def test_validate_a_commander_deck_estimates_its_bracket(tmp_path: Path) -> None:
    from tests.primitives.test_files_and_panes_helpers import COMMANDER_DECK

    async with editor(tmp_path, COMMANDER_DECK) as ed:
        ed.press(ex("validate"))
        await settle(ed)
        assert "bracket" in _report(ed).lower()


# ── :collection ─────────────────────────────────────────────────────


COLLECTION_CSV = "Name,Count\nLightning Bolt,4\nMountain,10\n"


def _collection_csv(tmp_path: Path, body: str = COLLECTION_CSV) -> None:
    (tmp_path / "coll.csv").write_text(body, encoding="utf-8")


@pytest.mark.primitive(":collection")
async def test_collection_path_loads_and_reports_the_counts(tmp_path: Path) -> None:
    _collection_csv(tmp_path)
    async with editor(tmp_path) as ed:
        ed.press(ex("collection coll.csv"))
        assert ed.is_error is False
        assert ed.message.startswith("Collection: 14 cards (2 unique) from ")
        assert "coll.csv" in ed.message
        assert ed.text == DECK


@pytest.mark.primitive(":collection")
async def test_collection_sums_copies_across_printings(tmp_path: Path) -> None:
    _collection_csv(tmp_path, "Name,Count\nLightning Bolt,2\nlightning bolt,3\n")
    async with editor(tmp_path) as ed:
        ed.press(ex("collection coll.csv"))
        assert ed.message.startswith("Collection: 5 cards (1 unique) from ")


@pytest.mark.primitive(":collection")
async def test_collection_alone_reports_none_loaded(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("collection"))
        assert ed.message == NO_COLLECTION


@pytest.mark.primitive(":collection")
async def test_collection_alone_reports_the_loaded_collection(tmp_path: Path) -> None:
    _collection_csv(tmp_path)
    async with editor(tmp_path) as ed:
        ed.press(ex("collection coll.csv") + ex("collection"))
        assert ed.message.startswith("Collection: 14 cards (2 unique) from ")


@pytest.mark.primitive(":collection")
async def test_collection_path_is_saved_and_reloaded_on_the_next_open(tmp_path: Path) -> None:
    _collection_csv(tmp_path)
    async with editor(tmp_path) as ed:
        ed.press(ex("collection coll.csv"))
    config = tomllib.loads((config_dir() / "config.toml").read_text(encoding="utf-8"))
    assert Path(config["editor"]["collection"]) == (tmp_path / "coll.csv").resolve()
    async with editor(tmp_path) as ed:
        ed.press(ex("collection"))
        assert ed.message.startswith("Collection: 14 cards (2 unique) from ")


@pytest.mark.primitive(":collection")
async def test_collection_bang_forgets_the_collection(tmp_path: Path) -> None:
    _collection_csv(tmp_path)
    async with editor(tmp_path) as ed:
        ed.press(ex("collection coll.csv") + ex("collection!") + ex("collection"))
        assert ed.message == NO_COLLECTION
    async with editor(tmp_path) as ed:
        ed.press(ex("collection"))
        assert ed.message == NO_COLLECTION


@pytest.mark.primitive(":collection")
async def test_collection_without_name_and_count_columns_is_refused(tmp_path: Path) -> None:
    _collection_csv(tmp_path, "foo,bar\n1,2\n")
    async with editor(tmp_path) as ed:
        ed.press(ex("collection coll.csv"))
        assert ed.is_error is True
        assert "foo" in ed.message
        assert "bar" in ed.message
        ed.press(ex("collection"))
        assert ed.message == NO_COLLECTION


@pytest.mark.primitive(":collection")
async def test_collection_of_a_missing_file_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("collection nosuch.csv"))
        assert ed.is_error is True
        assert ed.text == DECK


# ── :sync ───────────────────────────────────────────────────────────


@pytest.mark.primitive(":sync")
@pytest.mark.filterwarnings("ignore:A test tried to use socket")
async def test_sync_reports_that_it_cannot_reach_scryfall(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("sync"))
        assert ed.is_error is False  # started in the background
        await ed.app.workers.wait_for_complete()
        await settle(ed)
        assert ed.is_error is True
        assert "sync failed" in ed.message.lower()
        assert ed.text == DECK


@pytest.mark.primitive(":sync")
async def test_sync_with_an_argument_is_an_error_and_starts_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(ex("sync now"))
        assert ed.is_error is True
        await ed.app.workers.wait_for_complete()
        await settle(ed)
        assert "sync failed" not in ed.message.lower()
