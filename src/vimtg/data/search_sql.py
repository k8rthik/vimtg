"""Compile a parsed search (vimtg.domain.search) to SQLite.

Every user-supplied value travels as a bound parameter; the only text
spliced into the SQL is fixed column names and operators chosen from
the closed vocabularies below, never anything typed by the user.
"""

from __future__ import annotations

import functools
import re
import sqlite3

from vimtg.domain.card import Color
from vimtg.domain.card_names import normalize_card_name
from vimtg.domain.search import (
    And,
    ColorMatch,
    ExactName,
    IsMatch,
    LegalityMatch,
    NameWords,
    Node,
    Not,
    NumberMatch,
    Or,
    RarityMatch,
    SetMatch,
    TextMatch,
)

REGEXP_FUNCTION = "vimtg_regexp"

_SQL_OPS = {":": "=", "=": "=", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}

# Rules text of every face (the column is filled by sync; older rows
# fall back to the front-face text).
_ORACLE = "COALESCE(c.full_oracle_text, c.oracle_text, '')"
_TEXT_COLUMNS = {
    "name": "c.name",
    "type": "COALESCE(c.type_line, '')",
    "oracle": _ORACLE,
    "keyword": "COALESCE(c.keywords, '')",
    "mana": "COALESCE(c.mana_cost, '')",
}
_NUMBER_COLUMNS = {
    "cmc": "c.cmc",
    "power": "c.power",
    "toughness": "c.toughness",
    "usd": "c.price_usd",
    "eur": "c.price_eur",
    "tix": "c.price_tix",
}
_COLOR_COLUMNS = {"colors": "COALESCE(c.colors, '[]')",
                  "identity": "COALESCE(c.color_identity, '[]')"}
_RARITY_RANK = (
    "CASE c.rarity WHEN 'common' THEN 0 WHEN 'uncommon' THEN 1 "
    "WHEN 'rare' THEN 2 WHEN 'special' THEN 3 WHEN 'mythic' THEN 4 "
    "WHEN 'bonus' THEN 5 ELSE 3 END"
)
_FRONT_TYPE = (
    "(CASE WHEN instr(c.type_line, '//') > 0 "
    "THEN substr(c.type_line, 1, instr(c.type_line, '//') - 1) "
    "ELSE c.type_line END)"
)
# Comprehensive Rules 903.3: a legendary creature (or Vehicle,
# Spacecraft with P/T, Background), or text saying it "can be your
# commander" — the same test deck validation uses for Commander.
_IS_SQL: dict[str, str] = {
    "commander": (
        f"(({_FRONT_TYPE} LIKE '%Legendary%' AND ("
        f"{_FRONT_TYPE} LIKE '%Creature%' OR {_FRONT_TYPE} LIKE '%Vehicle%' "
        f"OR {_FRONT_TYPE} LIKE '%Background%' "
        f"OR ({_FRONT_TYPE} LIKE '%Spacecraft%' AND c.power IS NOT NULL) "
        f"OR ({_ORACLE} LIKE '%isn''t on the battlefield, it''s a%creature%')))"
        f" OR {_ORACLE} LIKE '%can be your commander%')"
    ),
    "dfc": "c.layout IN ('transform', 'modal_dfc', 'meld', 'reversible_card')",
    "mdfc": "c.layout = 'modal_dfc'",
    "transform": "c.layout = 'transform'",
    "split": "c.layout = 'split'",
    "adventure": "c.layout = 'adventure'",
    "flip": "c.layout = 'flip'",
    "meld": "c.layout = 'meld'",
    "gamechanger": "COALESCE(c.game_changer, 0) = 1",
}


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# The FTS tokenizer strips accents but keeps ligatures as-is.
_FTS_FOLDS = str.maketrans({"Æ": "Ae", "æ": "ae", "Œ": "Oe", "œ": "oe"})


def fts_name_query(words: list[str]) -> str:
    """FTS5 query: each word/phrase a prefix match on the name column.
    Quoted, so punctuation in names is literal, never FTS syntax."""
    phrases = [
        '"' + w.translate(_FTS_FOLDS).replace('"', '""') + '"*' for w in words
    ]
    return "name : (" + " OR ".join(phrases) + ")"


class _Compiler:
    def __init__(self) -> None:
        self.params: list[object] = []

    def bind(self, value: object) -> str:
        self.params.append(value)
        return "?"

    def compile(self, node: Node) -> str:  # noqa: C901 - one branch per node kind
        if isinstance(node, And):
            return "(" + " AND ".join(self.compile(n) for n in node.children) + ")"
        if isinstance(node, Or):
            return "(" + " OR ".join(self.compile(n) for n in node.children) + ")"
        if isinstance(node, Not):
            return f"(NOT {self.compile(node.child)})"
        if isinstance(node, NameWords):
            return (
                "c.rowid IN (SELECT rowid FROM cards_fts WHERE cards_fts MATCH "
                f"{self.bind(fts_name_query([node.text]))})"
            )
        if isinstance(node, ExactName):
            return (
                "c.scryfall_id IN (SELECT scryfall_id FROM card_names "
                f"WHERE name_key = {self.bind(normalize_card_name(node.name))})"
            )
        if isinstance(node, TextMatch):
            return self._text(node)
        if isinstance(node, ColorMatch):
            return self._color(node)
        if isinstance(node, NumberMatch):
            column = _NUMBER_COLUMNS[node.field]
            cast = (
                f"CAST({column} AS REAL)"
                if node.field in ("power", "toughness")
                else column
            )
            return (
                f"({column} IS NOT NULL AND {cast} {_SQL_OPS[node.op]} "
                f"{self.bind(node.value)})"
            )
        if isinstance(node, RarityMatch):
            return f"({_RARITY_RANK} {_SQL_OPS[node.op]} {self.bind(node.rank)})"
        if isinstance(node, SetMatch):
            return f"(lower(c.set_code) = {self.bind(node.code)})"
        if isinstance(node, LegalityMatch):
            path = self.bind(f'$."{node.format}"')
            status = (
                "IN ('legal', 'restricted')" if node.status == "legal"
                else f"= {self.bind(node.status)}"
            )
            return f"(COALESCE(json_extract(c.legalities, {path}), '') {status})"
        if isinstance(node, IsMatch):
            return f"({_IS_SQL[node.flag]})"
        raise TypeError(f"unknown search node {node!r}")  # pragma: no cover

    def _text(self, node: TextMatch) -> str:
        column = _TEXT_COLUMNS[node.field]
        if node.regex:
            return f"({REGEXP_FUNCTION}({self.bind(node.text)}, {column}))"
        if node.field == "keyword":
            # Keywords are a JSON list; match a whole keyword.
            return (
                f"(instr(lower({column}), {self.bind(_json_str(node.text.lower()))}) > 0)"
            )
        return f"({column} LIKE {self.bind(_like(node.text))} ESCAPE '\\')"

    def _color(self, node: ColorMatch) -> str:
        column = _COLOR_COLUMNS[node.field]

        def has(color: Color) -> str:
            return f"(instr({column}, {self.bind(_json_str(color.value))}) > 0)"

        if node.count is not None:
            count = " + ".join(has(c) for c in Color)
            return f"(({count}) {_SQL_OPS[node.op]} {self.bind(node.count)})"
        wanted = [c for c in Color if c in node.colors]
        others = [c for c in Color if c not in node.colors]

        def all_of(colors: list[Color]) -> str:
            return "(" + " AND ".join(has(c) for c in colors) + ")" if colors else "1"

        def none_of(colors: list[Color]) -> str:
            return "(NOT (" + " OR ".join(has(c) for c in colors) + "))" if colors else "1"

        def any_of(colors: list[Color]) -> str:
            return "(" + " OR ".join(has(c) for c in colors) + ")" if colors else "0"

        if node.op == ">=":
            return all_of(wanted)
        if node.op == "<=":
            return none_of(others)
        if node.op in ("=", ":"):
            return f"({all_of(wanted)} AND {none_of(others)})"
        if node.op == "!=":
            return f"(NOT ({all_of(wanted)} AND {none_of(others)}))"
        if node.op == ">":
            return f"({all_of(wanted)} AND {any_of(others)})"
        # "<": a proper subset — within the set, missing at least one.
        return f"({none_of(others)} AND NOT {all_of(wanted)})"


def _json_str(value: str) -> str:
    return '"' + value + '"'


def compile_search(node: Node) -> tuple[str, list[object]]:
    """SQL WHERE clause (over ``cards c``) and its parameters."""
    compiler = _Compiler()
    sql = compiler.compile(node)
    return sql, compiler.params


@functools.lru_cache(maxsize=64)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _regexp(pattern: object, text: object) -> int:
    if not isinstance(pattern, str) or not isinstance(text, str):
        return 0
    return 1 if _compiled(pattern).search(text) else 0


def register_functions(conn: sqlite3.Connection) -> None:
    """Install the functions compiled searches call (``/regex/``)."""
    conn.create_function(REGEXP_FUNCTION, 2, _regexp, deterministic=True)
