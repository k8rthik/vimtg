"""Performance regression tests.

These run as part of the regular suite but with generous thresholds — they
catch order-of-magnitude regressions, not microbenchmark drift. Tighten the
budgets locally if you're profiling.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def card_repo_loaded(db_factory: Callable[..., Database]) -> CardRepository:
    repo = CardRepository(db_factory())
    with open(FIXTURES_DIR / "scryfall_sample.json") as f:
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
        assert elapsed < 0.1, f"search took {elapsed * 1000:.1f}ms"

    def test_repeated_search_amortizes(self, card_repo_loaded: CardRepository) -> None:
        # Warm-up + 50 iterations should still average well under the budget.
        card_repo_loaded.search("a", limit=50)
        start = time.perf_counter()
        for _ in range(50):
            card_repo_loaded.search("a", limit=50)
        avg = (time.perf_counter() - start) / 50
        assert avg < 0.05, f"avg search {avg * 1000:.1f}ms over 50 iters"


class TestBufferPerformance:
    """Buffer ops are immutable but should stay cheap on realistic deck sizes."""

    def test_set_line_under_10ms(self) -> None:
        buf = Buffer.from_text(_large_deck_text(500))
        start = time.perf_counter()
        for _ in range(100):
            buf = buf.set_line(50, "4 Replacement Card")
        avg = (time.perf_counter() - start) / 100
        assert avg < 0.01, f"set_line avg {avg * 1000:.2f}ms"

    def test_insert_line_under_10ms(self) -> None:
        buf = Buffer.from_text(_large_deck_text(500))
        start = time.perf_counter()
        for i in range(100):
            buf = buf.insert_line(10 + i, f"1 Inserted {i}")
        avg = (time.perf_counter() - start) / 100
        assert avg < 0.01, f"insert_line avg {avg * 1000:.2f}ms"

    def test_from_text_under_50ms(self) -> None:
        text = _large_deck_text(500)
        start = time.perf_counter()
        Buffer.from_text(text)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.05, f"from_text took {elapsed * 1000:.1f}ms for 500 lines"

    def test_to_text_roundtrip_under_50ms(self) -> None:
        buf = Buffer.from_text(_large_deck_text(500))
        start = time.perf_counter()
        buf.to_text()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.05, f"to_text took {elapsed * 1000:.1f}ms"
