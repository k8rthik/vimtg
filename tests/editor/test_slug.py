"""Tests for slug generation utility."""

from __future__ import annotations

import re
from pathlib import Path

from vimtg.editor.slug import (
    generate_slug,
    generate_unique_path,
    slugify,
    unique_deck_path,
)


class TestGenerateSlug:
    def test_format_matches_pattern(self) -> None:
        slug = generate_slug()
        assert re.fullmatch(r"[a-z]+-[a-z]+-deck", slug), f"Bad slug format: {slug}"

    def test_produces_varying_results(self) -> None:
        slugs = {generate_slug() for _ in range(20)}
        assert len(slugs) > 1, "Expected multiple distinct slugs"


class TestGenerateUniquePath:
    def test_returns_deck_extension(self, tmp_path: Path) -> None:
        path = generate_unique_path(tmp_path)
        assert path.suffix == ".deck"

    def test_path_in_target_directory(self, tmp_path: Path) -> None:
        path = generate_unique_path(tmp_path)
        assert path.parent == tmp_path

    def test_avoids_existing_files(self, tmp_path: Path) -> None:
        # Create a file to potentially collide with
        existing = tmp_path / "arcane-bolt-deck.deck"
        existing.write_text("taken")
        path = generate_unique_path(tmp_path)
        assert path != existing

    def test_path_does_not_exist(self, tmp_path: Path) -> None:
        path = generate_unique_path(tmp_path)
        assert not path.exists()

    def test_raises_after_max_attempts(self, tmp_path: Path, monkeypatch) -> None:
        """If all generated slugs collide, raise RuntimeError."""
        monkeypatch.setattr(
            "vimtg.editor.slug.generate_slug", lambda: "always-same-deck"
        )
        (tmp_path / "always-same-deck.deck").write_text("taken")
        try:
            generate_unique_path(tmp_path, max_attempts=5)
            assert False, "Expected RuntimeError"  # noqa: B011
        except RuntimeError as exc:
            assert "5 attempts" in str(exc)


class TestSlugify:
    def test_lowercases_and_hyphenates(self) -> None:
        assert slugify("Mono-Red Burn!") == "mono-red-burn"

    def test_collapses_and_trims_separators(self) -> None:
        assert slugify("  Izzet   //  Phoenix  ") == "izzet-phoenix"

    def test_nothing_usable_is_empty(self) -> None:
        assert slugify("!!! ") == ""

    def test_caps_length(self) -> None:
        assert len(slugify("a" * 200)) <= 60


class TestUniqueDeckPath:
    def test_uses_slug(self, tmp_path: Path) -> None:
        assert unique_deck_path(tmp_path, "Burn") == tmp_path / "burn.deck"

    def test_numbers_collisions(self, tmp_path: Path) -> None:
        (tmp_path / "burn.deck").touch()
        (tmp_path / "burn-2.deck").touch()
        assert unique_deck_path(tmp_path, "Burn") == tmp_path / "burn-3.deck"

    def test_blank_name_gets_random_slug(self, tmp_path: Path) -> None:
        path = unique_deck_path(tmp_path, "")
        assert re.fullmatch(r"[a-z]+-[a-z]+-deck\.deck", path.name)
