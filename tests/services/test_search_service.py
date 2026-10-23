"""SearchService end to end: Scryfall-style queries against SQLite."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card, Color
from vimtg.services.search_service import SearchService, SearchSyntaxError

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def card_repo(db_factory: Callable[..., Database]) -> CardRepository:
    repo = CardRepository(db_factory())
    with open(FIXTURES_DIR / "scryfall_sample.json", encoding="utf-8") as f:
        cards_data = json.load(f)
    repo.bulk_insert([Card.from_scryfall(d) for d in cards_data])
    return repo


@pytest.fixture
def search_svc(card_repo: CardRepository) -> SearchService:
    return SearchService(card_repo=card_repo)


@pytest.fixture
def svc(real_shape_repo: CardRepository) -> SearchService:
    """Real Scryfall shape: DFCs, split, adventure, partners, prices."""
    return SearchService(card_repo=real_shape_repo)


def names(svc: SearchService, query: str, limit: int = 100) -> set[str]:
    return {c.name for c in svc.search(query, limit=limit)}


class TestNameSearch:
    def test_bolt(self, search_svc: SearchService) -> None:
        assert "Lightning Bolt" in names(search_svc, "bolt")

    def test_word_prefix(self, search_svc: SearchService) -> None:
        assert "Lightning Bolt" in names(search_svc, "light")

    def test_empty_returns_nothing(self, search_svc: SearchService) -> None:
        assert search_svc.search("") == []
        assert search_svc.search("t:") == []

    def test_bare_words_match_names_not_rules_text(self, svc: SearchService) -> None:
        # "damage" is in Lightning Bolt's text, not any name.
        assert names(svc, "damage") == set()
        assert "Lightning Bolt" in names(svc, "o:damage")

    def test_quoted_phrase(self, svc: SearchService) -> None:
        assert names(svc, '"lightning bolt"') == {"Lightning Bolt"}
        assert names(svc, '"bolt lightning"') == set()

    def test_either_face_name(self, svc: SearchService) -> None:
        assert "Delver of Secrets // Insectile Aberration" in names(svc, "insectile")
        assert "Bonecrusher Giant // Stomp" in names(svc, "stomp")

    def test_accents_and_ligatures(self, svc: SearchService) -> None:
        assert names(svc, "Æther vial") == {"Aether Vial"}
        assert names(svc, "lim-dul's") == {"Lim-Dûl's Vault"}

    def test_names_ranked_best_match_first(self, svc: SearchService) -> None:
        results = svc.search("bolt", limit=5)
        assert results[0].name == "Lightning Bolt"

    def test_name_key_substring(self, svc: SearchService) -> None:
        assert names(svc, "name:ightning") == {"Lightning Bolt"}

    def test_name_regex(self, svc: SearchService) -> None:
        assert names(svc, "/^t.*s, t/") == {"Thrasios, Triton Hero"}


class TestExactName:
    def test_full_name(self, svc: SearchService) -> None:
        assert names(svc, '!"Lightning Bolt"') == {"Lightning Bolt"}

    def test_exact_is_not_prefix(self, svc: SearchService) -> None:
        assert names(svc, '!"Lightning"') == set()

    def test_face_name(self, svc: SearchService) -> None:
        assert names(svc, "!stomp") == {"Bonecrusher Giant // Stomp"}
        assert names(svc, '!"insectile aberration"') == {
            "Delver of Secrets // Insectile Aberration"
        }

    def test_negated(self, svc: SearchService) -> None:
        got = names(svc, 'name:bolt -!"Lightning Bolt"')
        assert got == set()


class TestFaces:
    def test_back_face_rules_text(self, svc: SearchService) -> None:
        assert "Delver of Secrets // Insectile Aberration" in names(svc, "o:flying")
        assert "Valakut Awakening // Valakut Stoneforge" in names(
            svc, 'o:"pay 3 life"'
        )

    def test_back_face_type(self, svc: SearchService) -> None:
        got = names(svc, "t:land is:mdfc")
        assert got == {
            "Valakut Awakening // Valakut Stoneforge",
            "Emeria's Call // Emeria, Shattered Skyclave",
        }

    def test_full_text_survives_round_trip(self, real_shape_repo: CardRepository) -> None:
        delver = real_shape_repo.get_by_name("Delver of Secrets")
        assert delver is not None
        assert "Flying" in delver.full_oracle_text
        assert "Flying" not in delver.oracle_text  # front face stays front face

    def test_rows_without_full_text_fall_back(
        self, real_shape_repo: CardRepository, svc: SearchService
    ) -> None:
        # A database upgraded in place has NULL until the next sync.
        conn = real_shape_repo._db.connect()
        conn.execute("UPDATE cards SET full_oracle_text = NULL")
        conn.commit()
        assert "Lightning Bolt" in names(svc, "o:damage")


class TestFilters:
    def test_type(self, svc: SearchService) -> None:
        got = names(svc, "t:creature")
        assert "Tymna the Weaver" in got
        assert "Lightning Bolt" not in got

    def test_oracle_regex(self, svc: SearchService) -> None:
        assert names(svc, r"o:/deals \d damage to any/") == {
            "Lightning Bolt", "Bonecrusher Giant // Stomp"
        }

    def test_like_wildcards_are_literal(self, svc: SearchService) -> None:
        assert names(svc, "o:%") == set()
        assert names(svc, "o:_") == set()

    def test_keyword(self, svc: SearchService) -> None:
        assert names(svc, "kw:partner") == {"Thrasios, Triton Hero", "Tymna the Weaver"}
        assert names(svc, "kw:part") == set()  # whole keywords only

    def test_mana_cost(self, svc: SearchService) -> None:
        assert "Lightning Bolt" in names(svc, "m:r")
        assert "Lightning Bolt" in names(svc, "m:{R}")

    @pytest.mark.parametrize(
        ("query", "ok"),
        [
            ("mv=1", lambda v: v == 1), ("mv!=1", lambda v: v != 1),
            ("mv<3", lambda v: v < 3), ("mv<=3", lambda v: v <= 3),
            ("mv>3", lambda v: v > 3), ("mv>=3", lambda v: v >= 3),
            ("cmc:7", lambda v: v == 7),
        ],
    )
    def test_mana_value_operators(
        self, svc: SearchService, query: str, ok: Callable[[float], bool]
    ) -> None:
        results = svc.search(query, limit=100)
        assert results
        assert all(ok(c.cmc) for c in results)
        everything = svc.search("mv>=0", limit=100)
        assert len(results) == sum(1 for c in everything if ok(c.cmc))

    def test_power_toughness(self, svc: SearchService) -> None:
        assert names(svc, "pow>=4") == {"Bonecrusher Giant // Stomp"}
        assert names(svc, "tou>=3 t:legendary") == {"Thrasios, Triton Hero"}
        # Cards without P/T never match, negated or not
        assert "Lightning Bolt" not in names(svc, "pow<100")
        assert "Lightning Bolt" in names(svc, "-pow<100")

    def test_rarity(self, svc: SearchService) -> None:
        assert names(svc, "r:mythic") == {
            "Emeria's Call // Emeria, Shattered Skyclave", "Tymna the Weaver"
        }
        got = names(svc, "r>=rare")
        assert "Tymna the Weaver" in got and "Sol Ring" not in got
        assert all(c.rarity.value == "common" for c in svc.search("r<uncommon"))

    def test_set(self, svc: SearchService) -> None:
        assert names(svc, "set:C16") == {"Thrasios, Triton Hero", "Tymna the Weaver"}
        assert names(svc, "s:c16") == names(svc, "e:c16")

    def test_formats(self, svc: SearchService) -> None:
        assert "Lurrus of the Dream-Den" not in names(svc, "f:modern")
        assert names(svc, "banned:modern") == {"Lurrus of the Dream-Den"}
        assert names(svc, "restricted:vintage") == {"Sol Ring"}
        # f: means playable: restricted cards count
        assert "Sol Ring" in names(svc, "f:vintage")
        assert "Sol Ring" not in names(svc, "legal:legacy")
        assert names(svc, "-f:commander") == set()

    def test_missing_format_is_not_legal(self, svc: SearchService) -> None:
        assert names(svc, "f:alchemy") == set()
        assert len(names(svc, "-f:alchemy")) == len(names(svc, "mv>=0"))

    def test_usd(self, svc: SearchService) -> None:
        assert names(svc, "usd>10") == {
            "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
        }
        # No price → never matches a price comparison
        priced = "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
        assert names(svc, "eur>0") == {priced}
        assert priced not in names(svc, "-eur>0")
        assert "Fire // Ice" in names(svc, "-eur>0")

    def test_is_layouts(self, svc: SearchService) -> None:
        assert names(svc, "is:split") == {"Fire // Ice"}
        assert names(svc, "is:adventure") == {"Bonecrusher Giant // Stomp"}
        assert names(svc, "is:transform") == {
            "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
            "Delver of Secrets // Insectile Aberration",
        }
        assert names(svc, "is:dfc") == names(svc, "is:transform") | names(svc, "is:mdfc")
        assert "Fire // Ice" in names(svc, "not:dfc")

    def test_is_commander(self, svc: SearchService) -> None:
        assert names(svc, "is:commander") == {
            "Lurrus of the Dream-Den", "Thrasios, Triton Hero", "Tymna the Weaver"
        }

    def test_is_game_changer(self, svc: SearchService) -> None:
        assert names(svc, "is:gc") == {"Sol Ring", "Rhystic Study"}


class TestColours:
    def test_colour_at_least(self, svc: SearchService) -> None:
        got = names(svc, "c:r")
        assert "Fire // Ice" in got and "Lightning Bolt" in got
        assert "Mountain" not in got
        assert names(svc, "c:ur") == {"Fire // Ice"}

    def test_colour_exact(self, svc: SearchService) -> None:
        got = names(svc, "c=r")
        assert "Lightning Bolt" in got and "Fire // Ice" not in got

    def test_colour_word(self, svc: SearchService) -> None:
        assert names(svc, "c:orzhov") == {"Lurrus of the Dream-Den", "Tymna the Weaver"}
        assert names(svc, "c=izzet") == {"Fire // Ice"}
        assert names(svc, "c:green") == {"Thrasios, Triton Hero"}

    def test_face_colours(self, svc: SearchService) -> None:
        # Transform/MDFC colours live on the faces in Scryfall's data.
        assert "Delver of Secrets // Insectile Aberration" in names(svc, "c:u")

    def test_colourless(self, svc: SearchService) -> None:
        assert names(svc, "c:c") == {"Sol Ring", "Aether Vial", "Mountain"}
        assert names(svc, "id:c") == {"Sol Ring", "Aether Vial", "Mountain"}

    def test_multicolour(self, svc: SearchService) -> None:
        assert names(svc, "c:m") == {
            "Fire // Ice", "Lurrus of the Dream-Den", "Thrasios, Triton Hero",
            "Tymna the Weaver", "Lim-Dûl's Vault",
        }
        assert names(svc, "c>=2") == names(svc, "c:m")

    def test_identity_within(self, svc: SearchService) -> None:
        got = names(svc, "id:boros")
        assert {"Lightning Bolt", "Sol Ring", "Mountain"} <= got
        assert "Fire // Ice" not in got
        assert names(svc, "id<=rw") == got

    def test_identity_operators(self, svc: SearchService) -> None:
        assert names(svc, "id=simic") == {"Thrasios, Triton Hero"}
        assert names(svc, "id>=wb") == {"Lurrus of the Dream-Den", "Tymna the Weaver"}
        assert names(svc, "id>u") == {
            "Fire // Ice", "Thrasios, Triton Hero", "Lim-Dûl's Vault"
        }
        strict = names(svc, "id<ub")
        assert "Lim-Dûl's Vault" not in strict and "Rhystic Study" in strict
        assert "Sol Ring" in strict
        assert "Lim-Dûl's Vault" not in names(svc, "id!=ub")

    def test_identity_wubrg_is_everything(self, svc: SearchService) -> None:
        assert names(svc, "id:wubrg") == names(svc, "mv>=0")


class TestBoolean:
    def test_negation(self, svc: SearchService) -> None:
        got = names(svc, "-t:creature c:r")
        assert "Lightning Bolt" in got
        assert "Bonecrusher Giant // Stomp" not in got
        assert "Fire // Ice" not in names(svc, "c:u -c:r")

    def test_or_and_parentheses(self, svc: SearchService) -> None:
        got = names(svc, "(t:rat or t:cat) -o:companion")
        assert got == {"Relentless Rats"}
        assert names(svc, "t:rat or t:cat") == {
            "Relentless Rats", "Lurrus of the Dream-Den"
        }

    def test_or_ranks_name_matches(self, svc: SearchService) -> None:
        results = svc.search("bolt or is:split", limit=10)
        assert [c.name for c in results] == ["Lightning Bolt", "Fire // Ice"]

    def test_filter_only_results_sorted_by_name(self, svc: SearchService) -> None:
        results = [c.name for c in svc.search("t:creature", limit=100)]
        assert results == sorted(results)

    def test_word_combined_with_filter(self, search_svc: SearchService) -> None:
        assert names(search_svc, "c:u fire") == {"Fire // Ice"}


class TestLimit:
    def test_limit_honoured(self, search_svc: SearchService) -> None:
        assert len(search_svc.search("c:r", limit=2)) == 2

    def test_limit_above_fifty(self, db_factory: Callable[..., Database]) -> None:
        repo = CardRepository(db_factory())
        fixture = FIXTURES_DIR / "scryfall_sample.json"
        template = json.loads(fixture.read_text(encoding="utf-8"))[1]
        repo.bulk_insert([
            Card.from_scryfall({**template, "id": f"id-{i}", "name": f"Bolt {i}"})
            for i in range(80)
        ])
        svc = SearchService(card_repo=repo)
        assert len(svc.search("t:instant", limit=75)) == 75
        assert len(svc.search("bolt", limit=60)) == 60

    def test_legal_in_applies_before_limit(self, svc: SearchService) -> None:
        # Sorted by name the first card is Aether Vial (not pauper legal);
        # the format filter must not eat into the limit.
        got = svc.search("mv>=0", limit=2, legal_in="pauper")
        assert [c.name for c in got] == [
            "Delver of Secrets // Insectile Aberration", "Lightning Bolt"
        ]
        assert all(c.legalities.get("pauper") == "legal" for c in got)


class TestErrors:
    def test_unknown_key_is_reported(self, svc: SearchService) -> None:
        with pytest.raises(SearchSyntaxError, match="Unknown search key 'foo'"):
            svc.search("t:creature foo:bar")

    def test_bad_colour(self, svc: SearchService) -> None:
        with pytest.raises(SearchSyntaxError, match="Unknown colour 'purple'"):
            svc.search("c:purple")


class TestInjection:
    """User input is always bound, never spliced into SQL."""

    @pytest.mark.parametrize(
        "query",
        [
            "'; DROP TABLE cards; --",
            "o:\"'); DROP TABLE cards; --\"",
            "t:creature' OR '1'='1",
            "set:x' OR 1=1 --",
            '!"x\') OR 1=1 --"',
            "name:%' UNION SELECT * FROM sync_metadata --",
            '"bolt" OR name MATCH "*"',
            'NEAR(bolt fire) "a"*',
            "o:/.*'; DROP TABLE cards; --/",
            "kw:\"flying\\\" OR 1=1\"",
            'f:"modern\\")"',
        ],
    )
    def test_injection_attempts_are_inert(
        self, svc: SearchService, real_shape_repo: CardRepository, query: str
    ) -> None:
        before = real_shape_repo.count()
        try:
            results = svc.search(query, limit=100)
        except SearchSyntaxError:
            results = []
        assert len(results) < before  # nothing smuggled an always-true clause in
        assert real_shape_repo.count() == before

    def test_quote_in_value_matches_literally(self, svc: SearchService) -> None:
        assert names(svc, "o:\"isn't\"") == set()
        assert names(svc, "o:\"it's a land\"") == {"Thrasios, Triton Hero"}
        assert names(svc, "emeria's") == {"Emeria's Call // Emeria, Shattered Skyclave"}


def _join_all(threads: list[threading.Thread], budget: float = 30.0) -> None:
    """Join with one overall deadline; a wedged connection must fail
    the test, not hang the suite."""
    deadline = time.monotonic() + budget
    for t in threads:
        t.join(timeout=max(0.0, deadline - time.monotonic()))
    assert not any(t.is_alive() for t in threads), "search threads hung"


class TestConcurrency:
    def test_many_threads_search_at_once(self, svc: SearchService) -> None:
        """Regression: worker threads shared one sqlite connection, so
        fast typing raised sqlite3.InterfaceError / ProgrammingError."""
        errors: list[BaseException] = []
        start = threading.Barrier(16)
        queries = ["bolt", "t:creature c:w", "o:/draw/ -c:r", "(c:r or c:u) mv<=3",
                   "id:esper", "!stomp", "f:modern r>=rare", "light"]

        def hammer(i: int) -> None:
            try:
                start.wait()
                for n in range(60):
                    q = queries[(i + n) % len(queries)]
                    svc.search(q, limit=50)
            except BaseException as exc:  # noqa: BLE001 - report every failure
                errors.append(exc)

        threads = [
            threading.Thread(target=hammer, args=(i,), daemon=True) for i in range(16)
        ]
        for t in threads:
            t.start()
        _join_all(threads)
        assert not errors, errors[:3]

    def test_searches_alongside_main_connection_writes(
        self, svc: SearchService, real_shape_repo: CardRepository,
        real_shape_cards: list[dict[str, object]],
    ) -> None:
        errors: list[BaseException] = []
        stop = threading.Event()

        def searcher() -> None:
            try:
                while not stop.is_set():
                    assert svc.search("c:r", limit=50)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=searcher, daemon=True) for _ in range(4)]
        for t in threads:
            t.start()
        cards = [Card.from_scryfall(d) for d in real_shape_cards]  # type: ignore[arg-type]
        for _ in range(5):
            real_shape_repo.replace_all(cards)
        stop.set()
        _join_all(threads)
        assert not errors, errors[:3]

    def test_reader_pool_is_bounded_and_closed(
        self, db_factory: Callable[..., Database]
    ) -> None:
        db = db_factory()
        with db.reader() as a, db.reader() as b:
            assert a is not b
        with db.reader() as again:
            assert again in (a, b)  # reused, not a new connection per call
        db.close()
        with pytest.raises(Exception, match="closed"):
            a.execute("SELECT 1")


def test_colour_enum_letters_cover_parser() -> None:
    # The compiler matches JSON-quoted colour letters; keep them single.
    assert all(len(c.value) == 1 for c in Color)
