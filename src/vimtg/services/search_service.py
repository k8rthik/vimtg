"""Card search: one Scryfall-style parser for the TUI overlay and the CLI.

Syntax lives in :mod:`vimtg.domain.search`; SQL in
:mod:`vimtg.data.search_sql`. Invalid queries raise
:class:`~vimtg.domain.search.SearchSyntaxError` with a message naming
the unknown key or bad value.
"""

from vimtg.data.card_repository import CardRepository
from vimtg.data.tag_repository import TagRepository
from vimtg.domain.card import Card
from vimtg.domain.search import (
    And,
    LegalityMatch,
    SearchSyntaxError,
    parse_search_with_order,
    uses_tags,
)

__all__ = ["TAGS_NOT_SYNCED", "SearchService", "SearchSyntaxError"]

# Why an otag: search matched nothing on a database whose tags were
# never downloaded; each surface adds its own retry advice
TAGS_NOT_SYNCED = "oracle tags not synced"


class SearchService:
    def __init__(
        self, card_repo: CardRepository, tag_repo: TagRepository | None = None
    ) -> None:
        self._repo = card_repo
        self._tags = tag_repo or TagRepository(card_repo.database)

    def search(
        self, query: str, limit: int = 20, legal_in: str | None = None
    ) -> list[Card]:
        """Cards matching ``query``, best name match first (or as
        ``order:``/``direction:`` say), at most ``limit``.

        ``legal_in`` additionally keeps only cards playable (legal or
        restricted) in that Scryfall format, applied before the limit.
        """
        node, order = parse_search_with_order(query)
        if node is None:
            return []
        if legal_in:
            node = And((node, LegalityMatch(legal_in, "legal")))
        return self._repo.search_parsed(node, limit=limit, order=order)

    def tags_unsynced(self, query: str) -> bool:
        """True when ``query`` asks for an oracle tag but no tag sync has
        landed, so nothing can match it. A query that does not parse is
        not this method's business (it reports False).
        """
        try:
            node, _order = parse_search_with_order(query)
        except SearchSyntaxError:
            return False
        if node is None or not uses_tags(node):
            return False
        return not self._tags.has_tags()
