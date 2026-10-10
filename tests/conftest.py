import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolate_xdg_dirs(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redirect all XDG base dirs into a temp location for every test.

    Without this, instantiating ``VimTGApp`` (or anything that calls
    ``config.paths``) reads and writes the *real* user database, config, and
    cache under ``~``. Isolating per test keeps the suite deterministic and
    prevents tests from clobbering real user data.
    """
    base = tmp_path_factory.mktemp("xdg")
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(var, str(base / var.lower()))
    # Keep app tests off the network: VimTGApp auto-syncs card data on
    # mount unless this guard is set.
    monkeypatch.setenv("VIMTG_NO_AUTOSYNC", "1")
    # pytest-socket allows loopback, so a local HTTP(S) proxy would be a
    # way out to the internet. Tests never need one: drop proxy settings.
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(var.lower(), raising=False)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test_cards.db"


@pytest.fixture
def db_factory(tmp_path: Path) -> Iterator[Callable[..., Database]]:
    """Create initialized Databases and guarantee they are closed at teardown.

    Avoids leaking sqlite connections (and the ResourceWarning flood that
    accompanies GC-time closes) when a fixture returns a repository/service
    that owns a Database but the test never closes it explicitly.
    """
    created: list[Database] = []

    def _make(path: Path | None = None) -> Database:
        db = Database(path or tmp_path / "factory.db")
        db.initialize()
        created.append(db)
        return db

    yield _make

    for db in created:
        db.close()


@pytest.fixture
def sample_deck_path() -> Path:
    return FIXTURES_DIR / "sample_burn.deck"


@pytest.fixture
def scryfall_sample_path() -> Path:
    return FIXTURES_DIR / "scryfall_sample.json"


@pytest.fixture
def real_shape_cards() -> list[dict[str, Any]]:
    """Scryfall oracle_cards entries in the feed's real shape.

    Covers transform, modal DFC (spell and land backs), split, adventure,
    companion, partner, any-number, game changers, mana producers, and
    accented / ligature names. Multi-face cards carry their colours and
    costs on the faces exactly as Scryfall serves them.
    """
    path = FIXTURES_DIR / "scryfall_real_shape.json"
    cards: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return cards


@pytest.fixture
def real_shape_repo(
    db_factory: Callable[..., Database], real_shape_cards: list[dict[str, Any]]
) -> CardRepository:
    """A card repository loaded from the real-shape fixture set."""
    repo = CardRepository(db_factory())
    repo.replace_all([Card.from_scryfall(d) for d in real_shape_cards])
    return repo


@pytest.fixture
def sample_deck_text(sample_deck_path: Path) -> str:
    return sample_deck_path.read_text()
