"""Scryfall-style card search syntax: tokenizer, parser and query tree.

Pure domain code — no SQL here. :func:`parse_search` turns a query such
as ``-t:creature (c:r or c:g) mv<=2 "lightning bolt"`` into a tree of
frozen nodes that the data layer compiles to parameterised SQL.

Grammar (``or`` binds looser than the implicit ``and``)::

    query   := or_expr
    or_expr := and_expr ("or" and_expr)*
    and_expr:= unary ("and"? unary)*
    unary   := "-" unary | primary
    primary := "(" query ")" | term

A term is a bare word, a ``"quoted phrase"``, an exact name
(``!"Lightning Bolt"``), a bare ``/regex/`` (matched against the name)
or ``key<op>value`` where ``<op>`` is one of ``: = != < <= > >=``.

Every value is validated here, so an unknown key, a misspelled colour
or format, or a bad regex is reported by name instead of being
silently ignored. Syntax that is merely unfinished at the end of the
query (an open quote or parenthesis, a trailing ``-`` or ``or``, an
empty ``t:``) is tolerated so live, as-you-type search keeps working.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from vimtg.domain.card import Color
from vimtg.domain.formats import SCRYFALL_FORMATS, normalize_format
from vimtg.domain.oracle_tags import normalize_tag

# Limits on a query's size: far above anything typed, well inside
# SQLite's expression-depth and LIKE-pattern limits
MAX_QUERY_LENGTH = 1000
MAX_QUERY_TERMS = 200
MAX_QUERY_DEPTH = 32


class SearchSyntaxError(ValueError):
    """A query that can't be run, with a message naming the culprit."""


Op = Literal[":", "=", "!=", "<", "<=", ">", ">="]
_OPS: tuple[Op, ...] = ("!=", "<=", ">=", ":", "=", "<", ">")

# ── Query tree ────────────────────────────────────────────────────


@dataclass(frozen=True)
class NameWords:
    """A bare word or quoted phrase: word-prefix match on the card name
    (any face). Also drives result ranking."""

    text: str


@dataclass(frozen=True)
class ExactName:
    """``!name`` — the full card name or any one face, exactly."""

    name: str


TextField = Literal["name", "type", "oracle", "keyword", "mana"]


@dataclass(frozen=True)
class TextMatch:
    """Case-insensitive substring (or ``/regex/``) match on a text field.
    Multi-face cards match on any face."""

    field: TextField
    text: str
    regex: bool = False


ColorField = Literal["colors", "identity"]


@dataclass(frozen=True)
class ColorMatch:
    """Compare a card's colours (or colour identity) with a colour set,
    a colour count, or "multicolour" (two or more)."""

    field: ColorField
    op: Op
    colors: frozenset[Color] = frozenset()
    count: int | None = None


NumberField = Literal["cmc", "power", "toughness", "usd", "eur", "tix"]


@dataclass(frozen=True)
class NumberMatch:
    field: NumberField
    op: Op
    value: float


StatField = Literal["cmc", "power", "toughness"]


@dataclass(frozen=True)
class FieldCompare:
    """``pow>tou``, ``tou<=mv``: compare two of a card's numbers.
    Power and toughness are read per face, so a back face can match."""

    left: StatField
    op: Op
    right: StatField


@dataclass(frozen=True)
class ProducesMatch:
    """``produces:`` — mana symbols the card can produce (Scryfall
    ``produced_mana``), as a set of ``W U B R G C``; ':' means at least
    these, like ``c:``."""

    op: Op
    symbols: frozenset[str]


@dataclass(frozen=True)
class RarityMatch:
    op: Op
    rank: int


@dataclass(frozen=True)
class SetMatch:
    code: str


LegalityStatus = Literal["legal", "banned", "restricted"]


@dataclass(frozen=True)
class LegalityMatch:
    """``f:``/``legal:`` (playable: legal or restricted), ``banned:``,
    ``restricted:``."""

    format: str
    status: LegalityStatus


@dataclass(frozen=True)
class IsMatch:
    flag: str


@dataclass(frozen=True)
class TagMatch:
    """``otag:`` / ``oracletag:`` / ``function:``: a Scryfall oracle tag
    in slug form. A card matches a tag it carries or any descendant of
    it (``otag:removal`` finds ``removal-burn`` cards), and an alias
    (``otag:acceleration``) resolves to its tag."""

    slug: str


@dataclass(frozen=True)
class Not:
    child: Node


@dataclass(frozen=True)
class And:
    children: tuple[Node, ...]


@dataclass(frozen=True)
class Or:
    children: tuple[Node, ...]


Node = (
    NameWords | ExactName | TextMatch | ColorMatch | NumberMatch | RarityMatch
    | SetMatch | LegalityMatch | IsMatch | FieldCompare | ProducesMatch | TagMatch
    | Not | And | Or
)


OrderKey = Literal[
    "name", "cmc", "power", "toughness", "rarity", "usd", "eur", "tix", "set",
]


@dataclass(frozen=True)
class SearchOrder:
    """``order:`` / ``direction:`` — how to sort results instead of by
    name-match rank."""

    key: OrderKey = "name"
    descending: bool = False


def uses_tags(node: Node) -> bool:
    """True when any term of the query is an oracle tag (so an empty
    result may mean the tags were never synced)."""
    if isinstance(node, TagMatch):
        return True
    if isinstance(node, Not):
        return uses_tags(node.child)
    if isinstance(node, And | Or):
        return any(uses_tags(child) for child in node.children)
    return False


def ranking_words(node: Node | None) -> list[str]:
    """Bare name words a match should be ranked by: the ones that are
    not negated (negated words exclude, they don't rank)."""
    if isinstance(node, NameWords):
        return [node.text]
    if isinstance(node, And | Or):
        return [w for child in node.children for w in ranking_words(child)]
    return []


# ── Vocabulary ────────────────────────────────────────────────────

_KEYS: dict[str, str] = {
    "name": "name",
    "t": "type", "type": "type",
    "o": "oracle", "oracle": "oracle", "fo": "oracle",
    "kw": "keyword", "keyword": "keyword",
    "m": "mana", "mana": "mana",
    "c": "colors", "color": "colors", "colour": "colors",
    "id": "identity", "identity": "identity", "ci": "identity",
    "mv": "cmc", "cmc": "cmc", "manavalue": "cmc",
    "pow": "power", "power": "power",
    "tou": "toughness", "toughness": "toughness",
    "r": "rarity", "rarity": "rarity",
    "s": "set", "set": "set", "e": "set", "edition": "set",
    "f": "legal", "format": "legal", "legal": "legal",
    "banned": "banned", "restricted": "restricted",
    "is": "is", "not": "not",
    "usd": "usd", "eur": "eur", "tix": "tix",
    "produces": "produces",
    "otag": "tag", "oracletag": "tag", "function": "tag",
}

# Scryfall keys vimtg knows but cannot answer, and why. Anything else
# unknown is reported as an unknown key.
_UNSUPPORTED_KEYS: dict[str, str] = {
    "year": "only one printing per card is stored",
    "date": "only one printing per card is stored",
}

_ORDER_KEYS: dict[str, OrderKey] = {
    "name": "name", "cmc": "cmc", "mv": "cmc", "manavalue": "cmc",
    "power": "power", "pow": "power", "toughness": "toughness",
    "tou": "toughness", "rarity": "rarity", "usd": "usd", "eur": "eur",
    "tix": "tix", "set": "set",
}
_DIRECTIONS = {"asc": False, "ascending": False, "desc": True, "descending": True}
_STAT_FIELDS: dict[str, StatField] = {
    "cmc": "cmc", "mv": "cmc", "manavalue": "cmc",
    "pow": "power", "power": "power", "tou": "toughness", "toughness": "toughness",
}

# Typographic quotes typed or pasted into a query mean the ASCII ones
# Scryfall's rules text uses: o:"can’t" finds "can't".
_QUOTE_FOLDS = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})

_COLOR_WORDS: dict[str, str] = {
    "white": "W", "blue": "U", "black": "B", "red": "R", "green": "G",
    # Guilds
    "azorius": "WU", "dimir": "UB", "rakdos": "BR", "gruul": "RG",
    "selesnya": "GW", "orzhov": "WB", "izzet": "UR", "golgari": "BG",
    "boros": "RW", "simic": "GU",
    # Shards
    "bant": "GWU", "esper": "WUB", "grixis": "UBR", "jund": "BRG",
    "naya": "RGW",
    # Wedges
    "abzan": "WBG", "jeskai": "URW", "sultai": "BGU", "mardu": "RWB",
    "temur": "GUR",
}
_COLORLESS_WORDS = frozenset({"c", "colorless", "colourless"})
_MULTI_WORDS = frozenset({"m", "multicolor", "multicolour"})

_RARITIES: dict[str, int] = {
    "common": 0, "uncommon": 1, "rare": 2, "special": 3, "mythic": 4, "bonus": 5,
}
_RARITY_ABBREV = {"c": "common", "u": "uncommon", "r": "rare", "m": "mythic",
                  "s": "special", "b": "bonus"}


_IS_FLAGS: dict[str, str] = {
    "commander": "commander",
    "dfc": "dfc", "mdfc": "mdfc", "tdfc": "transform", "transform": "transform",
    "split": "split", "adventure": "adventure", "flip": "flip", "meld": "meld",
    "gamechanger": "gamechanger", "gc": "gamechanger",
    "permanent": "permanent", "spell": "spell",
    "hybrid": "hybrid", "phyrexian": "phyrexian",
}

_ORDERED_ONLY = {"cmc", "power", "toughness", "usd", "eur", "tix", "rarity",
                 "colors", "identity", "produces"}

_KEY_RE = re.compile(r"([A-Za-z]+)(!=|<=|>=|:|=|<|>)")


# ── Tokenizer ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Tok:
    kind: Literal["(", ")", "-", "or", "and", "word", "exact", "kv"]
    text: str = ""
    key: str = ""
    op: str = ""
    quoted: bool = False
    regex: bool = False


def _read_quoted(raw: str, i: int) -> tuple[str, int]:
    """Read a "quoted" string starting at raw[i] == '"'. An unclosed
    quote runs to the end (the user is still typing)."""
    end = raw.find('"', i + 1)
    if end < 0:
        return raw[i + 1 :], len(raw)
    return raw[i + 1 : end], end + 1


def _read_regex(raw: str, i: int) -> tuple[str, int]:
    """Read a /regex/ starting at raw[i] == '/'; ``\\/`` escapes a slash."""
    j = i + 1
    out: list[str] = []
    while j < len(raw):
        ch = raw[j]
        if ch == "\\" and j + 1 < len(raw) and raw[j + 1] == "/":
            out.append("/")
            j += 2
            continue
        if ch == "/":
            return "".join(out), j + 1
        out.append(ch)
        j += 1
    return "".join(out), j


def _read_word(raw: str, i: int) -> tuple[str, int]:
    j = i
    while j < len(raw) and not raw[j].isspace() and raw[j] not in "()":
        j += 1
    return raw[i:j], j


def _tokenize(raw: str) -> list[_Tok]:
    toks: list[_Tok] = []
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch.isspace():
            i += 1
        elif ch in "()":
            toks.append(_Tok(ch))  # type: ignore[arg-type]
            i += 1
        elif ch == "-":
            toks.append(_Tok("-"))
            i += 1
        elif ch == "!":
            if i + 1 < n and raw[i + 1] == '"':
                text, i = _read_quoted(raw, i + 1)
            else:
                text, i = _read_word(raw, i + 1)
            toks.append(_Tok("exact", text=text))
        elif ch == '"':
            text, i = _read_quoted(raw, i)
            toks.append(_Tok("word", text=text, quoted=True))
        elif ch == "/":
            text, i = _read_regex(raw, i)
            toks.append(_Tok("word", text=text, regex=True))
        else:
            m = _KEY_RE.match(raw, i)
            if m:
                key, op = m.group(1), m.group(2)
                j = m.end()
                quoted = regex = False
                if j < n and raw[j] == '"':
                    value, i = _read_quoted(raw, j)
                    quoted = True
                elif j < n and raw[j] == "/":
                    value, i = _read_regex(raw, j)
                    regex = True
                else:
                    value, i = _read_word(raw, j)
                toks.append(_Tok("kv", text=value, key=key, op=op,
                                 quoted=quoted, regex=regex))
                continue
            word, i = _read_word(raw, i)
            lower = word.lower()
            if lower in ("or", "and"):
                toks.append(_Tok(lower))  # type: ignore[arg-type]
            else:
                toks.append(_Tok("word", text=word))
    return toks


# ── Parser ────────────────────────────────────────────────────────


class _Parser:
    def __init__(self, toks: list[_Tok]) -> None:
        self._toks = toks
        self._pos = 0
        self._depth = 0
        self.order: SearchOrder | None = None

    def _peek(self) -> _Tok | None:
        return self._toks[self._pos] if self._pos < len(self._toks) else None

    def parse(self) -> Node | None:
        node = self._or()
        tok = self._peek()
        if tok is not None:
            # Only a stray ')' can stop the top-level parse early.
            raise SearchSyntaxError("Unmatched ')' in search")
        return node

    def _or(self) -> Node | None:
        parts: list[Node] = []
        first = self._and()
        if first is not None:
            parts.append(first)
        while (tok := self._peek()) is not None and tok.kind == "or":
            self._pos += 1
            if not parts:
                raise SearchSyntaxError("'or' needs a search term before it")
            nxt = self._and()
            if nxt is None:
                if self._peek() is None:
                    break  # trailing 'or' while typing
                raise SearchSyntaxError("'or' needs a search term after it")
            parts.append(nxt)
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else Or(tuple(parts))

    def _and(self) -> Node | None:
        parts: list[Node] = []
        while (tok := self._peek()) is not None and tok.kind not in ("or", ")"):
            if tok.kind == "and":
                self._pos += 1
                continue
            node = self._unary()
            if node is not None:
                parts.append(node)
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else And(tuple(parts))

    def _unary(self) -> Node | None:
        tok = self._peek()
        assert tok is not None
        if tok.kind == "-":
            self._pos += 1
            nxt = self._peek()
            if nxt is None:
                return None  # trailing '-' while typing
            if nxt.kind in ("or", "and", ")"):
                raise SearchSyntaxError("'-' must be followed by a search term")
            child = self._unary()
            return None if child is None else Not(child)
        return self._primary()

    def _primary(self) -> Node | None:
        tok = self._peek()
        assert tok is not None
        self._pos += 1
        if tok.kind == "(":
            self._depth += 1
            if self._depth > MAX_QUERY_DEPTH:
                raise SearchSyntaxError("Search nested too deeply")
            inner = self._or()
            self._depth -= 1
            closing = self._peek()
            if closing is not None and closing.kind == ")":
                self._pos += 1
            elif closing is not None:  # pragma: no cover - _or stops only at ')'
                raise SearchSyntaxError("Unmatched '(' in search")
            if inner is None and closing is not None:
                raise SearchSyntaxError("Empty parentheses in search")
            return inner
        if tok.kind == "word":
            return _bare_term(tok)
        if tok.kind == "exact":
            return ExactName(tok.text) if tok.text.strip() else None
        if tok.kind == "kv":
            if tok.key.lower() in ("order", "direction", "dir"):
                self._sort_term(tok)
                return None
            return _key_term(tok)
        raise SearchSyntaxError(f"Unexpected '{tok.kind}' in search")


    def _sort_term(self, tok: _Tok) -> None:
        """Record order:/direction:; they sort, they don't filter."""
        value = tok.text.strip().lower()
        if not value:
            return
        if tok.op != ":":
            raise SearchSyntaxError(f"'{tok.key}' only supports ':' (got '{tok.op}')")
        if tok.key.lower() == "order":
            key = _ORDER_KEYS.get(value)
            if key is None:
                raise SearchSyntaxError(f"Unknown sort order '{tok.text.strip()}'")
            current = self.order or SearchOrder()
            self.order = SearchOrder(key, current.descending)
            return
        if value not in _DIRECTIONS:
            raise SearchSyntaxError(f"Unknown direction '{tok.text.strip()}'")
        self.order = SearchOrder((self.order or SearchOrder()).key, _DIRECTIONS[value])


def _bare_term(tok: _Tok) -> Node | None:
    if tok.regex:
        return TextMatch("name", _check_regex(tok.text), regex=True) if tok.text else None
    text = tok.text.strip()
    # Pure punctuation ("//" typed in "Fire // Ice") names nothing.
    if not any(ch.isalnum() for ch in text):
        return None
    return NameWords(text)


def _check_regex(pattern: str) -> str:
    try:
        re.compile(pattern, re.IGNORECASE)
    except (re.error, OverflowError) as exc:  # a{99999999999} overflows
        raise SearchSyntaxError(f"Invalid regex /{pattern}/: {exc}") from exc
    return pattern


def _key_term(tok: _Tok) -> Node | None:
    key = _KEYS.get(tok.key.lower())
    if key is None:
        why = _UNSUPPORTED_KEYS.get(tok.key.lower())
        if why is not None:
            raise SearchSyntaxError(f"'{tok.key}' is not supported ({why})")
        raise SearchSyntaxError(f"Unknown search key '{tok.key}'")
    op: Op = tok.op  # type: ignore[assignment]
    value = tok.text if tok.quoted or tok.regex else tok.text.strip()
    if not value:
        return None  # 't:' still being typed
    if op not in (":", "=") and key not in _ORDERED_ONLY:
        raise SearchSyntaxError(f"'{tok.key}' only supports ':' (got '{op}')")
    if tok.regex and key not in ("name", "type", "oracle"):
        raise SearchSyntaxError(f"'{tok.key}' does not accept a /regex/")

    if key in ("name", "type", "oracle", "keyword"):
        if tok.regex:
            return TextMatch(key, _check_regex(value), regex=True)  # type: ignore[arg-type]
        return TextMatch(key, value)  # type: ignore[arg-type]
    if key == "mana":
        return TextMatch("mana", _mana_pattern(value))
    if key == "tag":
        return TagMatch(normalize_tag(value))
    if key in ("colors", "identity"):
        return _color_term(key, op, value)  # type: ignore[arg-type]
    if key == "produces":
        return _produces_term(op, value)
    if key in ("cmc", "power", "toughness") and value.lower() in _STAT_FIELDS:
        return FieldCompare(key, "=" if op == ":" else op, _STAT_FIELDS[value.lower()])  # type: ignore[arg-type]
    if key in ("cmc", "power", "toughness", "usd", "eur", "tix"):
        try:
            number = float(value)
        except ValueError:
            raise SearchSyntaxError(
                f"'{tok.key}' needs a number, got '{value}'"
            ) from None
        return NumberMatch(key, "=" if op == ":" else op, number)  # type: ignore[arg-type]
    if key == "rarity":
        name = _RARITY_ABBREV.get(value.lower(), value.lower())
        if name not in _RARITIES:
            raise SearchSyntaxError(f"Unknown rarity '{value}'")
        return RarityMatch("=" if op == ":" else op, _RARITIES[name])
    if key == "set":
        return SetMatch(value.lower())
    if key in ("legal", "banned", "restricted"):
        fmt = normalize_format(value)
        if fmt not in SCRYFALL_FORMATS:
            raise SearchSyntaxError(f"Unknown format '{value}'")
        return LegalityMatch(fmt, "legal" if key == "legal" else key)  # type: ignore[arg-type]
    # is: / not:
    flag = _IS_FLAGS.get(value.lower())
    if flag is None:
        raise SearchSyntaxError(f"Unknown value '{tok.key}:{value}'")
    return IsMatch(flag) if key == "is" else Not(IsMatch(flag))


def _mana_pattern(value: str) -> str:
    """``m:rr`` and ``m:{R}{R}`` both mean the symbols {R}{R}."""
    if "{" in value:
        return value.upper()
    return "".join(f"{{{ch}}}" for ch in value.upper())


def _color_term(field: ColorField, op: Op, value: str) -> ColorMatch:
    word = value.lower()
    # ':' means "at least these" for colours and "within these" for
    # identity, the way Scryfall reads c:rg and id:rg.
    set_op: Op = op if op != ":" else (">=" if field == "colors" else "<=")
    if word.isdecimal():  # not isdigit: '²' is a digit it cannot int()
        # Five colours at most; a larger count means the same (nothing)
        # and must not overflow the SQLite bind
        return ColorMatch(field, "=" if op == ":" else op, count=min(int(word), 6))
    if word in _MULTI_WORDS:
        if op not in (":", "="):
            raise SearchSyntaxError(f"'{value}' only supports ':'")
        return ColorMatch(field, ">=", count=2)
    if word in _COLORLESS_WORDS:
        return ColorMatch(field, "=" if op == ":" else op, colors=frozenset())
    letters = _COLOR_WORDS.get(word, word)
    colors: set[Color] = set()
    for ch in letters:
        color = _COLOR_LETTERS.get(ch.upper())
        if color is None:
            raise SearchSyntaxError(f"Unknown colour '{value}'")
        colors.add(color)
    return ColorMatch(field, set_op, colors=frozenset(colors))


_COLOR_LETTERS = {c.value: c for c in Color}


def _produces_term(op: Op, value: str) -> ProducesMatch:
    """produces:rg (at least red and green), produces=c (exactly
    colourless), produces:boros ..."""
    word = value.lower()
    set_op: Op = ">=" if op == ":" else op
    if word in _COLORLESS_WORDS:
        return ProducesMatch(set_op, frozenset({"C"}))
    letters = _COLOR_WORDS.get(word, word).upper()
    if not letters or any(ch not in "WUBRGC" for ch in letters):
        raise SearchSyntaxError(f"Unknown colour '{value}'")
    return ProducesMatch(set_op, frozenset(letters))


def parse_search(raw: str) -> Node | None:
    """Parse a search string; ``None`` when it holds no search terms.

    ``order:``/``direction:`` terms are accepted and dropped (see
    :func:`parse_search_with_order`). Raises :class:`SearchSyntaxError`
    for anything that can't be run.
    """
    return parse_search_with_order(raw)[0]


def parse_search_with_order(raw: str) -> tuple[Node | None, SearchOrder | None]:
    """Parse a search string and its ``order:``/``direction:`` terms.

    The order is ``None`` when the query names neither (rank by name
    match, then name).
    """
    # Bounds a typed query never reaches, but a pasted one might: past
    # them the SQL compiled from the tree overruns SQLite's own limits
    if len(raw) > MAX_QUERY_LENGTH:
        raise SearchSyntaxError(f"Search too long (max {MAX_QUERY_LENGTH} characters)")
    toks = _tokenize(raw.translate(_QUOTE_FOLDS))
    if len(toks) > MAX_QUERY_TERMS:
        raise SearchSyntaxError(f"Search has too many terms (max {MAX_QUERY_TERMS})")
    parser = _Parser(toks)
    node = parser.parse()
    return node, parser.order
