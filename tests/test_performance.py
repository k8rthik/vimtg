"""Performance regression tests.

These run as part of the regular suite but with generous thresholds — they
catch order-of-magnitude regressions, not microbenchmark drift. Tighten the
budgets locally if you're profiling.

Every test here is marked ``perf``. Shared CI runners (especially macOS and
Windows) are noisy, so budgets are multiplied by ``VIMTG_PERF_BUDGET_SCALE``
(default 1); deselect them entirely with ``-m "not perf"``.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer

FIXTURES_DIR = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.perf


def budget(seconds: float) -> float:
    """Scale a time budget by ``VIMTG_PERF_BUDGET_SCALE`` for slow runners."""
    return seconds * float(os.environ.get("VIMTG_PERF_BUDGET_SCALE", "1"))


@pytest.fixture
def card_repo_loaded(db_factory: Callable[..., Database]) -> CardRepository:
    repo = CardRepository(db_factory())
    with open(FIXTURES_DIR / "scryfall_sample.json", encoding="utf-8") as f:
        cards_data = json.load(f)
    cards = [Card.from_scryfall(d) for d in cards_data]
    repo.bulk_insert(cards)
    return repo


def _large_deck_text(line_count: int = 200) -> str:
    head = "// Deck: Perf\n// Format: modern\n\n"
    body = "\n".join(f"4 Card Number {i}" for i in range(line_count))
    return head + body + "\n"


class TestSearchPerformance:
    """FTS5-backed search must stay sub-100ms even with relaxed CI budgets."""

    def test_exact_search_under_100ms(self, card_repo_loaded: CardRepository) -> None:
        start = time.perf_counter()
        card_repo_loaded.search("lightning bolt", limit=50)
        elapsed = time.perf_counter() - start
        assert elapsed < budget(0.1), f"search took {elapsed * 1000:.1f}ms"

    def test_repeated_search_amortizes(self, card_repo_loaded: CardRepository) -> None:
        # Warm-up + 50 iterations should still average well under the budget.
        card_repo_loaded.search("a", limit=50)
        start = time.perf_counter()
        for _ in range(50):
            card_repo_loaded.search("a", limit=50)
        avg = (time.perf_counter() - start) / 50
        assert avg < budget(0.05), f"avg search {avg * 1000:.1f}ms over 50 iters"


class TestBufferPerformance:
    """Buffer ops are immutable but should stay cheap on realistic deck sizes."""

    def test_set_line_under_10ms(self) -> None:
        buf = Buffer.from_text(_large_deck_text(500))
        start = time.perf_counter()
        for _ in range(100):
            buf = buf.set_line(50, "4 Replacement Card")
        avg = (time.perf_counter() - start) / 100
        assert avg < budget(0.01), f"set_line avg {avg * 1000:.2f}ms"

    def test_insert_line_under_10ms(self) -> None:
        buf = Buffer.from_text(_large_deck_text(500))
        start = time.perf_counter()
        for i in range(100):
            buf = buf.insert_line(10 + i, f"1 Inserted {i}")
        avg = (time.perf_counter() - start) / 100
        assert avg < budget(0.01), f"insert_line avg {avg * 1000:.2f}ms"

    def test_from_text_under_50ms(self) -> None:
        text = _large_deck_text(500)
        start = time.perf_counter()
        Buffer.from_text(text)
        elapsed = time.perf_counter() - start
        assert elapsed < budget(0.05), f"from_text took {elapsed * 1000:.1f}ms for 500 lines"

    def test_to_text_roundtrip_under_50ms(self) -> None:
        buf = Buffer.from_text(_large_deck_text(500))
        start = time.perf_counter()
        buf.to_text()
        elapsed = time.perf_counter() - start
        assert elapsed < budget(0.05), f"to_text took {elapsed * 1000:.1f}ms"


class TestBudgetScale:
    def test_default_scale_is_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VIMTG_PERF_BUDGET_SCALE", raising=False)
        assert budget(0.05) == pytest.approx(0.05)

    def test_env_scales_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VIMTG_PERF_BUDGET_SCALE", "4")
        assert budget(0.05) == pytest.approx(0.2)


_COLOURS = ("W", "U", "B", "R", "G")
_TYPES = (
    "Creature — Elf Druid", "Legendary Creature — Human Wizard", "Instant",
    "Sorcery", "Artifact", "Enchantment — Aura", "Land", "Planeswalker — Jace",
)
_RARITY = ("common", "uncommon", "rare", "mythic")


def _generated_card(i: int) -> dict[str, object]:
    """One synthetic card in Scryfall's oracle_cards shape; every 10th
    is a transform DFC so face handling is exercised at scale."""
    colours = [c for b, c in enumerate(_COLOURS) if (i >> b) % 3 == 0]
    card: dict[str, object] = {
        "object": "card",
        "id": f"perf-{i:05d}",
        "oracle_id": f"oracle-{i:05d}",
        "name": f"Generated Card {i}",
        "layout": "normal",
        "cmc": float(i % 9),
        "mana_cost": "{1}" * (i % 9),
        "type_line": _TYPES[i % len(_TYPES)],
        "oracle_text": f"When this enters, draw {i % 4} cards. Deals {i % 7} damage.",
        "colors": colours,
        "color_identity": colours,
        "power": str(i % 6) if i % 8 < 2 else None,
        "toughness": str(i % 5) if i % 8 < 2 else None,
        "keywords": ["Flying"] if i % 5 == 0 else [],
        "legalities": {"modern": "legal" if i % 3 else "not_legal",
                       "commander": "legal", "vintage": "legal"},
        "set": f"s{i % 50:02d}",
        "rarity": _RARITY[i % 4],
        "prices": {"usd": f"{(i % 400) / 10:.2f}" if i % 7 else None},
    }
    if i % 10 == 0:
        card["layout"] = "transform"
        card["name"] = f"Front Face {i} // Back Face {i}"
        card["type_line"] = "Creature — Human // Creature — Werewolf"
        card["card_faces"] = [
            {"name": f"Front Face {i}", "mana_cost": "{G}", "oracle_text": "Front.",
             "type_line": "Creature — Human", "colors": ["G"]},
            {"name": f"Back Face {i}", "mana_cost": "", "oracle_text": "Trample.",
             "type_line": "Creature — Werewolf", "colors": ["G"]},
        ]
        del card["oracle_text"], card["mana_cost"], card["colors"]
    return card


@pytest.fixture(scope="module")
def large_search(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    from vimtg.services.search_service import SearchService

    db = Database(tmp_path_factory.mktemp("perf") / "large.db")
    db.initialize()
    repo = CardRepository(db)
    repo.replace_all(Card.from_scryfall(_generated_card(i)) for i in range(25_000))
    yield SearchService(repo)
    db.close()


class TestLargeSearchPerformance:
    """Search v2 on a 25k-card database: generous budgets, catching
    full-table-per-row blowups rather than drift."""

    @pytest.mark.parametrize(
        "query",
        [
            "generated card 12345",
            "t:creature c:g mv<=3",
            "-t:land (c:boros or id:esper) r>=rare",
            'o:"draw 2 cards" f:modern usd<5',
            r"o:/deals [3-5] damage/ pow>=2",
            "is:dfc o:trample",
            '!"Back Face 120"',
            "id<=wu -c:c kw:flying",
        ],
    )
    def test_query_under_budget(self, large_search, query: str) -> None:  # type: ignore[no-untyped-def]
        large_search.search(query, limit=50)  # warm caches
        start = time.perf_counter()
        results = large_search.search(query, limit=50)
        elapsed = time.perf_counter() - start
        assert results, query
        assert elapsed < budget(0.5), f"{query!r} took {elapsed * 1000:.1f}ms"

    def test_exact_back_face_found(self, large_search) -> None:  # type: ignore[no-untyped-def]
        assert [c.name for c in large_search.search('!"Back Face 120"')] == [
            "Front Face 120 // Back Face 120"
        ]
