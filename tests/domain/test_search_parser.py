"""Scryfall-style search syntax: tokenizer and parser (no database)."""

from __future__ import annotations

import pytest

from vimtg.domain.card import Color
from vimtg.domain.search import (
    And,
    ColorMatch,
    ExactName,
    IsMatch,
    LegalityMatch,
    NameWords,
    Not,
    NumberMatch,
    Or,
    RarityMatch,
    SearchSyntaxError,
    SetMatch,
    TextMatch,
    parse_search,
    ranking_words,
)

R, G, W, U, B = Color.RED, Color.GREEN, Color.WHITE, Color.BLUE, Color.BLACK


class TestTerms:
    def test_bare_words_are_name_words(self) -> None:
        assert parse_search("lightning bolt") == And(
            (NameWords("lightning"), NameWords("bolt"))
        )

    def test_quoted_phrase(self) -> None:
        assert parse_search('"lightning bolt"') == NameWords("lightning bolt")

    def test_exact_name_quoted(self) -> None:
        assert parse_search('!"Lightning Bolt"') == ExactName("Lightning Bolt")

    def test_exact_name_bare(self) -> None:
        assert parse_search("!fire") == ExactName("fire")

    def test_bare_regex_matches_name(self) -> None:
        assert parse_search("/^light/") == TextMatch("name", "^light", regex=True)

    @pytest.mark.parametrize("key", ["t", "type", "T"])
    def test_type(self, key: str) -> None:
        assert parse_search(f"{key}:creature") == TextMatch("type", "creature")

    @pytest.mark.parametrize("key", ["o", "oracle", "fo"])
    def test_oracle_quoted(self, key: str) -> None:
        assert parse_search(f'{key}:"draw a card"') == TextMatch("oracle", "draw a card")

    def test_oracle_regex(self) -> None:
        assert parse_search(r"o:/deals \d damage/") == TextMatch(
            "oracle", r"deals \d damage", regex=True
        )

    def test_regex_escaped_slash(self) -> None:
        assert parse_search(r"o:/a\/b/") == TextMatch("oracle", "a/b", regex=True)

    def test_name_key(self) -> None:
        assert parse_search("name:bolt") == TextMatch("name", "bolt")

    def test_keyword(self) -> None:
        assert parse_search("kw:flying") == TextMatch("keyword", "flying")

    def test_mana_letters_become_symbols(self) -> None:
        assert parse_search("m:rr") == TextMatch("mana", "{R}{R}")
        assert parse_search("m:{2}{u}") == TextMatch("mana", "{2}{U}")

    @pytest.mark.parametrize(
        ("query", "op", "value"),
        [
            ("mv=3", "=", 3.0),
            ("mv:3", "=", 3.0),
            ("cmc!=3", "!=", 3.0),
            ("mv<3", "<", 3.0),
            ("manavalue<=3", "<=", 3.0),
            ("cmc>3", ">", 3.0),
            ("mv>=2.5", ">=", 2.5),
        ],
    )
    def test_mana_value_operators(self, query: str, op: str, value: float) -> None:
        assert parse_search(query) == NumberMatch("cmc", op, value)  # type: ignore[arg-type]

    def test_power_toughness(self) -> None:
        assert parse_search("pow>=3") == NumberMatch("power", ">=", 3.0)
        assert parse_search("tou<2") == NumberMatch("toughness", "<", 2.0)

    def test_prices(self) -> None:
        assert parse_search("usd<1") == NumberMatch("usd", "<", 1.0)
        assert parse_search("eur>=10") == NumberMatch("eur", ">=", 10.0)
        assert parse_search("tix=0.5") == NumberMatch("tix", "=", 0.5)

    @pytest.mark.parametrize(
        ("query", "op", "rank"),
        [("r:mythic", "=", 4), ("r:c", "=", 0), ("rarity>=rare", ">=", 2),
         ("r<uncommon", "<", 1)],
    )
    def test_rarity(self, query: str, op: str, rank: int) -> None:
        assert parse_search(query) == RarityMatch(op, rank)  # type: ignore[arg-type]

    @pytest.mark.parametrize("key", ["set", "s", "e", "edition"])
    def test_set(self, key: str) -> None:
        assert parse_search(f"{key}:MH2") == SetMatch("mh2")

    def test_formats(self) -> None:
        assert parse_search("f:modern") == LegalityMatch("modern", "legal")
        assert parse_search("legal:EDH") == LegalityMatch("commander", "legal")
        assert parse_search("banned:legacy") == LegalityMatch("legacy", "banned")
        assert parse_search("restricted:vintage") == LegalityMatch(
            "vintage", "restricted"
        )

    @pytest.mark.parametrize(
        ("value", "flag"),
        [("commander", "commander"), ("dfc", "dfc"), ("mdfc", "mdfc"),
         ("tdfc", "transform"), ("split", "split"), ("adventure", "adventure"),
         ("gc", "gamechanger")],
    )
    def test_is(self, value: str, flag: str) -> None:
        assert parse_search(f"is:{value}") == IsMatch(flag)

    def test_not_is_negation(self) -> None:
        assert parse_search("not:dfc") == Not(IsMatch("dfc"))


class TestColours:
    def test_colour_colon_means_at_least(self) -> None:
        assert parse_search("c:rg") == ColorMatch("colors", ">=", frozenset({R, G}))

    def test_identity_colon_means_within(self) -> None:
        assert parse_search("id:rg") == ColorMatch("identity", "<=", frozenset({R, G}))
        assert parse_search("ci:w") == ColorMatch("identity", "<=", frozenset({W}))

    @pytest.mark.parametrize("op", ["=", "!=", "<", "<=", ">", ">="])
    def test_explicit_operators(self, op: str) -> None:
        assert parse_search(f"id{op}wu") == ColorMatch(
            "identity", op, frozenset({W, U})  # type: ignore[arg-type]
        )

    @pytest.mark.parametrize(
        ("word", "colors"),
        [("red", {R}), ("boros", {R, W}), ("azorius", {W, U}), ("esper", {W, U, B}),
         ("wubrg", {W, U, B, R, G}), ("Temur", {G, U, R})],
    )
    def test_colour_words(self, word: str, colors: set[Color]) -> None:
        assert parse_search(f"c:{word}") == ColorMatch("colors", ">=", frozenset(colors))

    def test_colourless(self) -> None:
        assert parse_search("c:c") == ColorMatch("colors", "=", frozenset())
        assert parse_search("id:colorless") == ColorMatch("identity", "=", frozenset())

    def test_multicolour(self) -> None:
        assert parse_search("c:m") == ColorMatch("colors", ">=", count=2)

    def test_count(self) -> None:
        assert parse_search("c>=2") == ColorMatch("colors", ">=", count=2)
        assert parse_search("id:3") == ColorMatch("identity", "=", count=3)


class TestBoolean:
    def test_negation(self) -> None:
        assert parse_search("-t:creature") == Not(TextMatch("type", "creature"))
        assert parse_search("-c:r") == Not(ColorMatch("colors", ">=", frozenset({R})))

    def test_double_negation(self) -> None:
        assert parse_search("--bolt") == Not(Not(NameWords("bolt")))

    def test_or(self) -> None:
        assert parse_search("t:elf or t:goblin") == Or(
            (TextMatch("type", "elf"), TextMatch("type", "goblin"))
        )

    def test_and_binds_tighter_than_or(self) -> None:
        assert parse_search("c:r t:elf OR t:goblin") == Or(
            (
                And((ColorMatch("colors", ">=", frozenset({R})),
                     TextMatch("type", "elf"))),
                TextMatch("type", "goblin"),
            )
        )

    def test_parentheses(self) -> None:
        assert parse_search("c:r (t:elf or t:goblin)") == And(
            (
                ColorMatch("colors", ">=", frozenset({R})),
                Or((TextMatch("type", "elf"), TextMatch("type", "goblin"))),
            )
        )

    def test_negated_group(self) -> None:
        assert parse_search("-(t:elf or t:goblin)") == Not(
            Or((TextMatch("type", "elf"), TextMatch("type", "goblin")))
        )

    def test_explicit_and_is_noise(self) -> None:
        assert parse_search("t:elf and c:g") == parse_search("t:elf c:g")

    def test_quoted_or_is_a_word(self) -> None:
        assert parse_search('"or"') == NameWords("or")


class TestLenientWhileTyping:
    @pytest.mark.parametrize("query", ["", "   ", "t:", "t: c: set: r: mv= o:", "-", "("])
    def test_nothing_to_search(self, query: str) -> None:
        assert parse_search(query) is None

    def test_unclosed_quote(self) -> None:
        assert parse_search('o:"draw a card') == TextMatch("oracle", "draw a card")

    def test_unclosed_paren(self) -> None:
        assert parse_search("(t:elf or t:goblin") == Or(
            (TextMatch("type", "elf"), TextMatch("type", "goblin"))
        )

    def test_trailing_or_and_dash(self) -> None:
        assert parse_search("t:elf or") == TextMatch("type", "elf")
        assert parse_search("t:elf -") == TextMatch("type", "elf")

    def test_punctuation_only_word_dropped(self) -> None:
        assert parse_search("fire // ice") == And((NameWords("fire"), NameWords("ice")))

    def test_names_with_punctuation_stay_words(self) -> None:
        assert parse_search("lim-dûl's") == NameWords("lim-dûl's")
        assert parse_search("Fire/Ice") == NameWords("Fire/Ice")


class TestErrors:
    @pytest.mark.parametrize(
        ("query", "message"),
        [
            ("foo:bar", "Unknown search key 'foo'"),
            ("t:elf zzz>3", "Unknown search key 'zzz'"),
            ("c:xyz", "Unknown colour 'xyz'"),
            ("mv<=abc", "'mv' needs a number, got 'abc'"),
            ("r:legendary", "Unknown rarity 'legendary'"),
            ("f:notaformat", "Unknown format 'notaformat'"),
            ("is:banana", "Unknown value 'is:banana'"),
            ("t>creature", "'t' only supports ':'"),
            ("o:/(unclosed/", "Invalid regex"),
            ("c:/r/", "does not accept a /regex/"),
            ("t:elf)", "Unmatched ')'"),
            ("()", "Empty parentheses"),
            ("or t:elf", "'or' needs a search term before it"),
            ("t:elf or or t:goblin", "'or' needs a search term after it"),
            ("- or t:elf", "'-' must be followed by a search term"),
            ("c>m", "only supports ':'"),
        ],
    )
    def test_error_names_the_problem(self, query: str, message: str) -> None:
        with pytest.raises(SearchSyntaxError, match=message.replace("(", r"\(")
                           .replace(")", r"\)")):
            parse_search(query)


class TestRankingWords:
    def test_negated_words_do_not_rank(self) -> None:
        node = parse_search("bolt -lightning (fire or ice) t:instant")
        assert ranking_words(node) == ["bolt", "fire", "ice"]

    def test_none(self) -> None:
        assert ranking_words(None) == []
