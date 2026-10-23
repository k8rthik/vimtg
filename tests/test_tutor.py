"""vimtg tutor: the lesson deck, its bundled cards, and the offline sandbox."""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from vimtg.cli import main
from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.editor.buffer import LineType, classify_lines
from vimtg.tutor import (
    CARDS_PATH,
    TUTOR_EXTRA_CARDS,
    lesson_card_names,
    lesson_text,
    tutor_sandbox,
)

# The deck view shows a lesson line whole on an 80-column terminal
MAX_LESSON_LINE = 72


def _bundled_names() -> set[str]:
    with gzip.open(CARDS_PATH, "rt", encoding="utf-8") as f:
        return {json.loads(line)["name"] for line in f if line.strip()}


def test_bundle_holds_every_card_the_lessons_use() -> None:
    wanted = lesson_card_names() | set(TUTOR_EXTRA_CARDS)
    assert wanted - _bundled_names() == set(), "rerun scripts/build_tutor_cards.py"


def test_lesson_deck_parses_every_line() -> None:
    skipped: list[tuple[int, str]] = []
    from vimtg.data.deck_repository import parse_deck_text

    parse_deck_text(lesson_text(), on_skip=lambda n, text: skipped.append((n, text)))
    assert skipped == []


def test_lesson_text_never_reads_as_a_section_header() -> None:
    lines = classify_lines(lesson_text().splitlines())
    headers = [bl.text for bl in lines if bl.line_type == LineType.SECTION_HEADER]
    assert headers == ["// Sideboard"]


def test_lesson_lines_fit_the_deck_view() -> None:
    long = [line for line in lesson_text().splitlines() if len(line) > MAX_LESSON_LINE]
    assert long == []


def test_sandbox_isolates_and_loads_the_bundle(tmp_path: Path) -> None:
    before = {k: os.environ.get(k) for k in ("XDG_DATA_HOME", "VIMTG_NO_EDHREC")}
    with tutor_sandbox() as deck:
        assert deck.read_text(encoding="utf-8") == lesson_text()
        assert os.environ["VIMTG_NO_EDHREC"] == "1"
        assert not str(db_path()).startswith(str(before["XDG_DATA_HOME"]))
        db = Database(db_path())
        try:
            db.initialize()
            assert CardRepository(db).count() == len(_bundled_names())
        finally:
            db.close()
        sandbox_root = deck.parent
    assert not sandbox_root.exists(), "the sandbox is thrown away on exit"
    assert {k: os.environ.get(k) for k in before} == before


def test_sandbox_restores_env_after_an_error() -> None:
    before = os.environ.get("XDG_STATE_HOME")
    with pytest.raises(RuntimeError), tutor_sandbox():
        raise RuntimeError("editor crashed")
    assert os.environ.get("XDG_STATE_HOME") == before


def test_tutor_command_opens_the_lesson_deck(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    fake_app_cls = MagicMock()

    def fake_app(deck_path: Path | None = None) -> MagicMock:
        assert deck_path is not None
        opened.append(deck_path.read_text(encoding="utf-8"))
        return MagicMock()

    fake_app_cls.side_effect = fake_app
    import vimtg.tui.app as app_mod

    monkeypatch.setattr(app_mod, "VimTGApp", fake_app_cls)
    result = CliRunner().invoke(main, ["tutor"])
    assert result.exit_code == 0, result.output
    assert opened == [lesson_text()]
