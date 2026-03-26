"""Deck diff service — enriches raw diffs with optional card stats.

Thin wrapper around the pure domain diff engine that optionally computes
StatsDelta using resolved card data from the card repository.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.analytics import compute_stats
from vimtg.domain.deck_diff import DeckDiff, StatsDelta, compute_deck_diff

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository


class DeckDiffService:
    """Computes MTG-aware diffs between deck states, optionally with stats."""

    def __init__(self, card_repo: CardRepository | None = None) -> None:
        self._card_repo = card_repo

    def diff(
        self,
        old_state: str,
        new_state: str,
        price_source: str = "usd",
    ) -> DeckDiff:
        """Compute card-level diff, optionally enriched with stats delta."""
        base_diff = compute_deck_diff(old_state, new_state)

        if self._card_repo is None:
            return base_diff

        stats_delta = self._compute_stats_delta(
            old_state, new_state, price_source,
        )
        return DeckDiff(
            changes=base_diff.changes,
            stats_delta=stats_delta,
        )

    def diff_snapshot_parent(
        self,
        deck_state: str,
        parent_state: str | None,
        price_source: str = "usd",
    ) -> DeckDiff:
        """Diff a snapshot state against its parent (or empty if root)."""
        return self.diff(parent_state or "", deck_state, price_source)

    def _compute_stats_delta(
        self,
        old_state: str,
        new_state: str,
        price_source: str,
    ) -> StatsDelta | None:
        """Compute stats delta using resolved card data."""
        if self._card_repo is None:
            return None

        try:
            old_deck = parse_deck_text(old_state)
            new_deck = parse_deck_text(new_state)

            old_names = list(old_deck.unique_card_names())
            new_names = list(new_deck.unique_card_names())
            all_names = list(set(old_names) | set(new_names))

            resolved = self._card_repo.get_by_names(all_names)

            old_stats = compute_stats(old_deck, resolved, price_source)
            new_stats = compute_stats(new_deck, resolved, price_source)

            curve_delta: dict[int, int] = {}
            for bucket in range(8):
                old_count = old_stats.mana_curve.buckets.get(bucket, 0)
                new_count = new_stats.mana_curve.buckets.get(bucket, 0)
                delta = new_count - old_count
                if delta != 0:
                    curve_delta[bucket] = delta

            return StatsDelta(
                old_total=old_stats.total_cards,
                new_total=new_stats.total_cards,
                old_avg_cmc=old_stats.average_cmc,
                new_avg_cmc=new_stats.average_cmc,
                old_price=old_stats.total_price_usd,
                new_price=new_stats.total_price_usd,
                curve_delta=curve_delta,
            )
        except Exception:
            return None
