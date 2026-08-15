"""Tests for the per-format rule registry."""

from vimtg.config.settings import VALID_FORMATS
from vimtg.domain.formats import FORMAT_RULES, get_format_rules


class TestRegistry:
    def test_covers_all_valid_formats(self):
        assert set(FORMAT_RULES) == {f for f in VALID_FORMATS if f}

    def test_empty_and_unknown_return_none(self):
        assert get_format_rules("") is None
        assert get_format_rules("kitchen-table") is None

    def test_lookup_is_case_insensitive(self):
        assert get_format_rules("Commander") is FORMAT_RULES["commander"]

    def test_commander_rules(self):
        rules = get_format_rules("commander")
        assert rules.exact_deck_size == 100
        assert rules.copy_limit == 1
        assert rules.allows_sideboard is False
        assert rules.requires_commander is True

    def test_brawl_rules(self):
        rules = get_format_rules("brawl")
        assert rules.copy_limit == 1
        assert rules.requires_commander is True
        assert rules.allows_sideboard is False

    def test_modern_defaults(self):
        rules = get_format_rules("modern")
        assert rules.min_deck_size == 60
        assert rules.exact_deck_size is None
        assert rules.copy_limit == 4
        assert rules.max_sideboard == 15

    def test_name_doubles_as_legalities_key(self):
        for name, rules in FORMAT_RULES.items():
            assert rules.name == name
