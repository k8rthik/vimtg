from dataclasses import dataclass

from vimtg.domain.card import Color, Rarity


@dataclass(frozen=True)
class SearchQuery:
    """Structured search criteria for card queries."""

    text: str = ""
    type_contains: str | None = None
    colors_include: tuple[Color, ...] = ()
    cmc_eq: float | None = None
    cmc_lte: float | None = None
    cmc_gte: float | None = None
    set_code: str | None = None
    rarity: Rarity | None = None
    oracle_contains: str | None = None
    name_exact: str | None = None

    def is_empty(self) -> bool:
        return not any([
            self.text,
            self.type_contains,
            self.colors_include,
            self.cmc_eq,
            self.cmc_lte,
            self.cmc_gte,
            self.set_code,
            self.rarity,
            self.oracle_contains,
            self.name_exact,
        ])
