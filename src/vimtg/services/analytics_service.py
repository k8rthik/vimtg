"""Analytics service — compute and cache deck statistics."""

from __future__ import annotations

from vimtg.data.card_repository import CardRepository
from vimtg.domain.analytics import DeckStats, compute_stats
from vimtg.domain.deck import Deck


class AnalyticsService:
    """Computes deck statistics with caching based on deck contents."""

    def __init__(self, card_repo: CardRepository) -> None:
        self._repo = card_repo
        self._cache: tuple[frozenset[tuple[str, int, str]], DeckStats] | None = None

    def compute(self, deck: Deck) -> DeckStats:
        """Compute stats for a deck. Returns cached result if deck unchanged."""
        key = frozenset(
            (e.card_name, e.quantity, e.section.value) for e in deck.entries
        )
        if self._cache is not None and self._cache[0] == key:
            return self._cache[1]

        names = list(deck.unique_card_names())
        resolved = self._repo.get_by_names(names)
        stats = compute_stats(deck, resolved)
        self._cache = (key, stats)
        return stats

    def invalidate(self) -> None:
        """Clear the stats cache."""
        self._cache = None
