"""CLI: card data freshness in `validate`, `sync` on a damaged or
unreachable database/network."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from click.testing import CliRunner

from vimtg import cli
from vimtg.cli import main
from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text("// Deck: Burn\n\n4 Lightning Bolt\n", encoding="utf-8")
    return path


def _with_sync_time(repo: CardRepository, when: datetime) -> CardRepository:
    repo.set_last_sync(when.isoformat())
    return repo


def test_validate_notes_stale_card_data(
    tmp_path: Path, real_shape_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = datetime.now(UTC) - timedelta(days=30)
    _with_sync_time(real_shape_repo, old)
    monkeypatch.setattr(cli, "_try_card_repo", lambda: real_shape_repo)
    result = CliRunner().invoke(main, ["validate", str(_deck(tmp_path))])
    assert result.exit_code == 0  # informational only
    assert (
        f"note: card data as of {old.date().isoformat()} (30 days old)" in result.output
    )


def test_validate_fresh_card_data_has_no_note(
    tmp_path: Path, real_shape_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_sync_time(real_shape_repo, datetime.now(UTC) - timedelta(days=2))
    monkeypatch.setattr(cli, "_try_card_repo", lambda: real_shape_repo)
    result = CliRunner().invoke(main, ["validate", str(_deck(tmp_path))])
    assert result.exit_code == 0
    assert "note:" not in result.output


def test_sync_rebuilds_damaged_database(monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_file.write_bytes(b"not a database at all " * 300)

    def fake_sync(self: Any, force: bool = False, progress: Any = None) -> int:
        return self._repo.count() + 3

    monkeypatch.setattr(cli.ScryfallSync, "sync", fake_sync)
    result = CliRunner().invoke(main, ["sync"])
    assert result.exit_code == 0, result.output
    assert "damaged and has been rebuilt" in result.output
    assert "downloading it now" in result.output
    assert "Synced 3 cards" in result.output
    assert len(list(db_file.parent.glob("cards.db.corrupt-*"))) == 1


def test_sync_offline_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def offline(self: Any, force: bool = False, progress: Any = None) -> int:
        raise httpx.ConnectError(
            "[Errno 101] Network is unreachable",
            request=httpx.Request("GET", "https://api.scryfall.com/bulk-data"),
        )

    for var in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli.ScryfallSync, "sync", offline)
    result = CliRunner().invoke(main, ["sync"])
    assert result.exit_code == 1
    assert "you seem to be offline" in result.output
    assert "run `vimtg sync` to retry once connected" in result.output
