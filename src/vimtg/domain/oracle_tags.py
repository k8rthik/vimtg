"""Scryfall oracle tags (``otag:`` on Scryfall): a tag hierarchy over
oracle ids.

Pure domain code. A tag record from Scryfall's ``oracle_tags`` bulk
file becomes an :class:`OracleTag`; :func:`card_tag_rows` expands the
taggings so that a card tagged ``tutor-creature-giant`` is also a
``tutor-creature`` and a ``tutor``, which is how ``otag:tutor`` finds
it on Scryfall.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

_SPACES = re.compile(r"\s+")


def normalize_tag(text: str) -> str:
    """The slug form of a tag as typed or aliased: lowercase, spaces
    to hyphens (``"Mana Ramp"`` is ``mana-ramp``)."""
    return _SPACES.sub("-", text.strip().lower())


@dataclass(frozen=True)
class OracleTag:
    id: str
    slug: str
    parent_ids: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    oracle_ids: tuple[str, ...] = ()

    @classmethod
    def from_scryfall(cls, data: dict[str, Any]) -> OracleTag:
        return cls(
            id=str(data["id"]),
            slug=normalize_tag(str(data["slug"])),
            parent_ids=tuple(str(p) for p in data.get("parent_ids") or ()),
            aliases=tuple(str(a) for a in data.get("aliases") or ()),
            oracle_ids=tuple(
                str(t["oracle_id"]) for t in data.get("taggings") or () if t.get("oracle_id")
            ),
        )


def implied_slugs(tags: Iterable[OracleTag]) -> dict[str, set[str]]:
    """Each tag id to the slugs a tagging with it implies: its own and
    every ancestor's. Parents not in ``tags`` are ignored; a cycle
    (never in Scryfall's data) is walked once."""
    by_id = {tag.id: tag for tag in tags}
    implied: dict[str, set[str]] = {}
    for tag in by_id.values():
        slugs = {tag.slug}
        seen = {tag.id}
        pending = list(tag.parent_ids)
        while pending:
            parent_id = pending.pop()
            parent = by_id.get(parent_id)
            if parent is None or parent_id in seen:
                continue
            seen.add(parent_id)
            slugs.add(parent.slug)
            pending.extend(parent.parent_ids)
        implied[tag.id] = slugs
    return implied


def card_tag_rows(tags: Iterable[OracleTag]) -> Iterator[tuple[str, str]]:
    """``(oracle_id, slug)`` for every tag a card carries, ancestors
    included, each pair once."""
    tags = list(tags)
    implied = implied_slugs(tags)
    seen: set[tuple[str, str]] = set()
    for tag in tags:
        for oracle_id in tag.oracle_ids:
            for slug in implied[tag.id]:
                row = (oracle_id, slug)
                if row not in seen:
                    seen.add(row)
                    yield row


def alias_rows(tags: Iterable[OracleTag]) -> Iterator[tuple[str, str]]:
    """``(alias, slug)`` with the alias in slug form, so a typed
    ``otag:"mana ramp"`` resolves to ``ramp``."""
    for tag in tags:
        for alias in tag.aliases:
            yield normalize_tag(alias), tag.slug
