You are building vimtg — a TUI-based MTG deck builder. This is Phase 7: Deck analytics with mana curve and stats.

Read `PROGRESS.md` and existing source files for context.

## 1. Analytics Model — `src/vimtg/domain/analytics.py`

```python
@dataclass(frozen=True)
class ManaCurve:
    buckets: dict[int, int]  # CMC → count. Key 7 means "7+"

    def max_count(self) -> int: ...
    def total(self) -> int: ...

@dataclass(frozen=True)
class ColorDistribution:
    pips: dict[Color, int]        # Mana pips in casting costs
    cards: dict[Color, int]       # Cards of each color
    colorless_count: int

@dataclass(frozen=True)
class TypeBreakdown:
    counts: dict[str, int]  # "Creature" → 24, "Instant" → 8, etc.

    def total_nonland(self) -> int: ...

@dataclass(frozen=True)
class DeckStats:
    total_cards: int
    mainboard_count: int
    sideboard_count: int
    unique_cards: int
    average_cmc: float
    median_cmc: float
    land_count: int
    nonland_count: int
    mana_curve: ManaCurve
    color_distribution: ColorDistribution
    type_breakdown: TypeBreakdown
    total_price_usd: float | None
    recommended_lands: int

def compute_stats(deck: Deck, resolved_cards: dict[str, Card]) -> DeckStats:
    """Compute all deck statistics from deck entries and resolved card data.

    - CMC buckets: 0,1,2,3,4,5,6,7+ (only count nonland cards)
    - Color pips: parse mana_cost strings, count {W},{U},{B},{R},{G} symbols
    - Type breakdown: extract primary type from type_line (before ' — ')
    - Average/median CMC: of nonland cards only
    - Price: sum of (quantity * price_usd) for resolved cards
    - Recommended lands: Frank Karsten formula approximation:
      lands = round(17.5 + 0.5 * average_cmc * nonland_count / total_cards * 2.5)
      Clamped to [20, 28] for 60-card decks.
    """
```

## 2. Analytics Service — `src/vimtg/services/analytics_service.py`

```python
class AnalyticsService:
    def __init__(self, card_repo: CardRepository) -> None: ...

    def compute(self, deck: Deck) -> DeckStats:
        """Resolve cards and compute stats. Caches by deck content hash."""

    def invalidate_cache(self) -> None: ...
```

Cache: hash the deck's card names + quantities. If unchanged, return cached stats.

## 3. Mana Curve Widget — `src/vimtg/tui/widgets/mana_curve.py`

ASCII horizontal bar chart:

```
Mana Curve
0: ██                (4)
1: ████████████      (12)
2: ██████████████    (14)
3: ████████          (8)
4: ████              (4)
5: ██                (2)
6:                   (0)
7+:█                 (1)
   └──────────────────
   Avg: 2.1  Med: 2.0
```

- Bars scale to terminal width
- Mana symbols colored: each bar colored by most common color at that CMC
- Empty buckets shown but with no bar
- Clean text art — no box-drawing for the chart itself, just unicode block chars

## 4. Analytics Panel — `src/vimtg/tui/widgets/analytics_panel.py`

Composes mana curve + stats into a single view:

```
═══ Deck Statistics ════════════════════════

  Cards:    60 main / 15 side / 75 total
  Unique:   28 cards
  Avg CMC:  2.14
  Lands:    24 (recommended: 24)
  Price:    $142.50

  Mana Curve
  0: ██                (4)
  1: ████████████      (12)
  2: ██████████████    (14)
  3: ████████          (8)
  4: ████              (4)
  5: ██                (2)
  6+:                  (0)

  Colors         Types
  W: 12 pips     Creature:    24
  U:  0 pips     Instant:      8
  B:  0 pips     Sorcery:      8
  R: 28 pips     Enchantment:  4
  G:  0 pips     Land:        24
                 Artifact:     0
```

## 5. Integration — `:stats` command

`:stats` opens the analytics panel as a bottom split overlay:
- Takes up bottom 40% of screen
- Deck view shrinks to top 60%
- Dismissible with `q` or `:stats` again (toggle)
- Live-updates when buffer changes (via reactive properties)

In MainScreen, toggle the panel:
```python
def _toggle_stats(self) -> None:
    if self.stats_panel.display:
        self.stats_panel.display = False
    else:
        stats = self.analytics_service.compute(self.buffer.to_deck())
        self.stats_panel.update(stats)
        self.stats_panel.display = True
```

## Tests — TDD

`tests/domain/test_analytics.py`:
- `test_mana_curve_basic` — correct bucket counts
- `test_mana_curve_empty_deck` — all zeros
- `test_color_distribution_mono_red` — only red pips
- `test_color_distribution_multicolor` — multiple colors
- `test_type_breakdown` — correct counts per type
- `test_compute_stats_total` — total cards correct
- `test_compute_stats_average_cmc` — correct average (nonland only)
- `test_compute_stats_median_cmc` — correct median
- `test_compute_stats_price` — sum of prices
- `test_recommended_lands` — reasonable recommendation
- `test_compute_stats_with_unresolved` — handles missing cards gracefully

`tests/services/test_analytics_service.py`:
- `test_compute_returns_stats` — non-None result
- `test_cache_hit` — same deck returns cached stats
- `test_cache_invalidation` — different deck recomputes

## IMPORTANT

- Analytics is ALL TEXT — ASCII bar charts, no Rich graphs or sparklines
- The panel is a bottom overlay, not a side panel (text-first vision)
- Stats update live as the buffer changes — reactive to buffer modifications
- Color distribution counts MANA PIPS, not just card colors (important for mana base)
- Recommended land count uses established MTG math (Frank Karsten formula)
- Keep files under 200 lines
