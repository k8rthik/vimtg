"""Loading a collection CSV from disk: errors a user can act on, and a
cache that reloads only when the file changes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vimtg.domain.collection import CollectionError
from vimtg.services.collection_service import load_collection


def test_loads_a_csv_and_records_its_source(tmp_path: Path) -> None:
    path = tmp_path / "manabox.csv"
    path.write_text("Quantity,Name\n4,Lightning Bolt\n", encoding="utf-8")
    collection = load_collection(path)
    assert collection.owned_count("Lightning Bolt") == 4
    assert collection.source == path
    assert collection.status() == "Collection: 4 cards (1 unique) from manabox.csv"


def test_missing_file_is_a_collection_error(tmp_path: Path) -> None:
    with pytest.raises(CollectionError, match="not found"):
        load_collection(tmp_path / "nope.csv")


def test_directory_is_a_collection_error(tmp_path: Path) -> None:
    with pytest.raises(CollectionError):
        load_collection(tmp_path)


def test_same_file_is_served_from_the_cache_until_it_changes(tmp_path: Path) -> None:
    path = tmp_path / "c.csv"
    path.write_text("Count,Name\n1,Lightning Bolt\n", encoding="utf-8")
    first = load_collection(path)
    assert load_collection(path) is first
    path.write_text("Count,Name\n2,Lightning Bolt\n", encoding="utf-8")
    # A rewrite inside the same mtime tick must still count as a change
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    second = load_collection(path)
    assert second is not first
    assert second.owned_count("Lightning Bolt") == 2
