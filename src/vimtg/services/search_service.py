"""Card search: one Scryfall-style parser for the TUI overlay and the CLI.

Syntax lives in :mod:`vimtg.domain.search`; SQL in
:mod:`vimtg.data.search_sql`. Invalid queries raise
:class:`~vimtg.domain.search.SearchSyntaxError` with a message naming
the unknown key or bad value.
"""

from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.domain.search import (
    And,
    LegalityMatch,
    Node,
    SearchSyntaxError,
    parse_search,
)

__all__ = ["SearchService", "SearchSyntaxError"]


class SearchService:
    def __init__(self, card_repo: CardRepository) -> None:
        self._repo = card_repo

    def parse_query(self, raw: str) -> Node | None:
        """Parse without running; ``None`` for a query with no terms."""
        return parse_search(raw)

    def search(
        self, query: str, limit: int = 20, legal_in: str | None = None
    ) -> list[Card]:
        """Cards matching ``query``, best name match first, at most ``limit``.

        ``legal_in`` additionally keeps only cards playable (legal or
        restricted) in that Scryfall format, applied before the limit.
        """
        node = parse_search(query)
        if node is None:
            return []
        if legal_in:
            node = And((node, LegalityMatch(legal_in, "legal")))
        return self._repo.search_parsed(node, limit=limit)

    def autocomplete(self, prefix: str) -> list[str]:
        return self._repo.autocomplete(prefix)
