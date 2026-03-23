"""Search service with Scryfall-like syntax parsing."""

import contextlib

from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card, Color, Rarity
from vimtg.domain.search import SearchQuery

COLOR_MAP: dict[str, Color] = {
    "w": Color.WHITE,
    "u": Color.BLUE,
    "b": Color.BLACK,
    "r": Color.RED,
    "g": Color.GREEN,
}

_FILTER_FIELDS = (
    "type_contains",
    "colors_include",
    "cmc_eq",
    "cmc_lte",
    "cmc_gte",
    "set_code",
    "rarity",
    "oracle_contains",
)


class SearchService:
    def __init__(self, card_repo: CardRepository) -> None:
        self._repo = card_repo

    def fuzzy_search(self, query: str, limit: int = 20) -> list[Card]:
        return self._repo.search(query, limit=limit)

    def advanced_search(self, query: str) -> list[Card]:
        sq = self.parse_query(query)
        if sq.is_empty():
            return []
        has_filters = any(getattr(sq, f) for f in _FILTER_FIELDS)
        if sq.text and not has_filters:
            return self._repo.search(sq.text)
        return self._repo.search_advanced(sq)

    def autocomplete(self, prefix: str) -> list[str]:
        return self._repo.autocomplete(prefix)

    def parse_query(self, raw: str) -> SearchQuery:
        """Parse Scryfall-like syntax into SearchQuery.

        Tokens: t:creature, c:red, cmc<=3, o:"draw a card", set:mh2, r:mythic
        Everything else becomes free text.
        """
        text_parts: list[str] = []
        type_contains: str | None = None
        colors: list[Color] = []
        cmc_eq: float | None = None
        cmc_lte: float | None = None
        cmc_gte: float | None = None
        set_code: str | None = None
        rarity: Rarity | None = None
        oracle_contains: str | None = None

        tokens = _tokenize(raw)
        for token in tokens:
            if token.startswith(("t:", "type:")):
                type_contains = token.split(":", 1)[1]
            elif token.startswith(("c:", "color:")):
                color_str = token.split(":", 1)[1].lower()
                for ch in color_str:
                    if ch in COLOR_MAP:
                        colors.append(COLOR_MAP[ch])
            elif token.startswith("cmc"):
                result = _parse_cmc(token)
                if result is not None:
                    op, val = result
                    if op == "<=":
                        cmc_lte = val
                    elif op == ">=":
                        cmc_gte = val
                    elif op == "=":
                        cmc_eq = val
            elif token.startswith(("o:", "oracle:")):
                oracle_contains = token.split(":", 1)[1].strip('"')
            elif token.startswith("set:"):
                set_code = token.split(":", 1)[1]
            elif token.startswith(("r:", "rarity:")):
                r_val = token.split(":", 1)[1].lower()
                with contextlib.suppress(ValueError):
                    rarity = Rarity(r_val)
            else:
                text_parts.append(token)

        return SearchQuery(
            text=" ".join(text_parts),
            type_contains=type_contains,
            colors_include=tuple(colors),
            cmc_eq=cmc_eq,
            cmc_lte=cmc_lte,
            cmc_gte=cmc_gte,
            set_code=set_code,
            rarity=rarity,
            oracle_contains=oracle_contains,
        )


def _parse_cmc(token: str) -> tuple[str, float] | None:
    """Extract operator and value from cmc token (e.g. 'cmc<=3')."""
    rest = token[3:]  # strip "cmc"
    if rest.startswith("<="):
        op, val_str = "<=", rest[2:]
    elif rest.startswith(">="):
        op, val_str = ">=", rest[2:]
    elif rest.startswith("="):
        op, val_str = "=", rest[1:]
    else:
        return None
    try:
        return (op, float(val_str))
    except ValueError:
        return None


def _tokenize(raw: str) -> list[str]:
    """Split on spaces, respecting quoted strings."""
    tokens: list[str] = []
    current = ""
    in_quotes = False
    for ch in raw:
        if ch == '"':
            in_quotes = not in_quotes
            current += ch
        elif ch == " " and not in_quotes:
            if current:
                tokens.append(current)
                current = ""
        else:
            current += ch
    if current:
        tokens.append(current)
    return tokens
