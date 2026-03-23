from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test_cards.db"


@pytest.fixture
def sample_deck_path() -> Path:
    return FIXTURES_DIR / "sample_burn.deck"


@pytest.fixture
def scryfall_sample_path() -> Path:
    return FIXTURES_DIR / "scryfall_sample.json"


@pytest.fixture
def sample_deck_text(sample_deck_path: Path) -> str:
    return sample_deck_path.read_text()
