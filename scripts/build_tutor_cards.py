"""Rebuild src/vimtg/tutor/cards.jsonl.gz from a Scryfall oracle_cards bulk file.

The tutor runs offline against this bundle, so it holds every card named in
tutor.deck plus the cards its lessons ask you to search for (TUTOR_EXTRA_CARDS).
Prices are dropped: they go stale and the tutor never shows them.

    uv run python scripts/build_tutor_cards.py ~/.cache/vimtg/oracle_cards.jsonl.gz
"""

from __future__ import annotations

import gzip
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from vimtg.tutor import CARDS_PATH, TUTOR_EXTRA_CARDS, lesson_card_names

KEPT_FIELDS = (
    "id", "oracle_id", "name", "layout", "mana_cost", "cmc", "type_line",
    "oracle_text", "colors", "color_identity", "keywords", "legalities",
    "power", "toughness", "produced_mana", "rarity", "set", "game_changer",
    "card_faces",
)


def _iter_bulk(path: Path) -> Iterator[dict[str, Any]]:
    if path.name.endswith((".jsonl.gz", ".jsonl")):
        opener = gzip.open if path.name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)
    else:
        yield from json.loads(path.read_text(encoding="utf-8"))


def main(bulk: Path) -> None:
    wanted = lesson_card_names() | set(TUTOR_EXTRA_CARDS)
    found: dict[str, dict[str, Any]] = {}
    for item in _iter_bulk(bulk):
        if item.get("name") in wanted and item["name"] not in found:
            kept = {k: item[k] for k in KEPT_FIELDS if k in item}
            found[item["name"]] = {**kept, "prices": {}}
    missing = sorted(wanted - found.keys())
    if missing:
        sys.exit(f"not in {bulk}: {', '.join(missing)}")
    lines = (json.dumps(found[name], sort_keys=True) for name in sorted(found))
    # mtime=0 keeps the archive byte-identical across rebuilds
    with open(CARDS_PATH, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(("\n".join(lines) + "\n").encode())
    print(f"wrote {len(found)} cards to {CARDS_PATH}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
