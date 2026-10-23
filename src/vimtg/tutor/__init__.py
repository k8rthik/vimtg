"""vimtg tutor: a vimtutor-style lesson deck run in a throwaway sandbox.

The sandbox points every XDG directory at a temporary folder and loads the
bundled card set into it, so the tutor works offline, before the first sync,
with default settings, and never touches the user's decks, history, or card
database.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from vimtg.config.paths import cache_dir, db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.deck_repository import parse_deck_text
from vimtg.data.scryfall_sync import ScryfallSync

# What the app exits with when :Tutor or the greeter's t asks for the
# tutor; the CLI then opens the lesson deck in its sandbox
LAUNCH_TUTOR = "vimtg:tutor"

_HERE = Path(__file__).resolve().parent
LESSON_PATH = _HERE / "tutor.deck"
CARDS_PATH = _HERE / "cards.jsonl.gz"

# Cards a lesson asks you to find with card search, which the lesson deck
# does not already hold. scripts/build_tutor_cards.py bundles them too.
TUTOR_EXTRA_CARDS: tuple[str, ...] = (
    "Lightning Helix", "Skullcrack", "Boros Charm",
    "Smash to Smithereens", "Deflecting Palm", "Sacred Foundry",
    "Inspiring Vantage", "Plains",
)

_XDG_VARS = ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")
_SANDBOX_FLAGS = {"VIMTG_NO_AUTOSYNC": "1", "VIMTG_NO_EDHREC": "1"}


def lesson_text() -> str:
    return LESSON_PATH.read_text(encoding="utf-8")


def lesson_card_names() -> set[str]:
    deck = parse_deck_text(lesson_text())
    names = {e.card_name for e in deck.entries}
    names.update(e.card_name for plan in deck.plans for e in plan.entries)
    return names


@contextmanager
def tutor_sandbox() -> Iterator[Path]:
    """Yield a fresh lesson deck inside a temporary, offline vimtg sandbox."""
    touched = (*_XDG_VARS, *_SANDBOX_FLAGS)
    saved = {name: os.environ.get(name) for name in touched}
    with tempfile.TemporaryDirectory(prefix="vimtg-tutor-") as tmp:
        root = Path(tmp)
        try:
            for name in _XDG_VARS:
                os.environ[name] = str(root / name.removeprefix("XDG_").lower())
            os.environ.update(_SANDBOX_FLAGS)
            _load_bundled_cards()
            deck = root / LESSON_PATH.name
            deck.write_text(lesson_text(), encoding="utf-8")
            yield deck
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def _load_bundled_cards() -> None:
    # Load from a copy: a load that fails to parse deletes its input file
    cards = cache_dir() / CARDS_PATH.name
    shutil.copyfile(CARDS_PATH, cards)
    db = Database(db_path())
    try:
        db.initialize()
        ScryfallSync(CardRepository(db), cache_dir()).parse_and_load(cards)
    finally:
        db.close()
