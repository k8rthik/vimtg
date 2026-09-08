"""Tests for the primary-type vocabulary: labels, aliases, and matching."""

from __future__ import annotations

import pytest

from vimtg.domain.card_types import (
    PRIMARY_TYPES,
    SECTION_LABELS,
    header_primary_type,
    primary_type,
    type_section_label,
)


class TestHeaderPrimaryType:
    @pytest.mark.parametrize("ptype", PRIMARY_TYPES)
    def test_singular_label_names_its_type(self, ptype: str) -> None:
        assert header_primary_type(ptype) == ptype

    @pytest.mark.parametrize("ptype", PRIMARY_TYPES)
    def test_plural_label_names_its_type(self, ptype: str) -> None:
        assert header_primary_type(SECTION_LABELS[ptype]) == ptype

    def test_sorcery_and_sorceries_are_one_type(self) -> None:
        # The one type whose singular is not a prefix of its plural —
        # substring matching used to split these into two sections.
        assert header_primary_type("Sorcery") == "Sorcery"
        assert header_primary_type("Sorceries") == "Sorcery"

    def test_case_and_whitespace_insensitive(self) -> None:
        assert header_primary_type("  sorceries ") == "Sorcery"
        assert header_primary_type("CREATURES") == "Creature"

    def test_compound_label_is_not_a_type(self) -> None:
        # '// Artifact Lands' is a user grouping, not the Artifact section
        assert header_primary_type("Artifact Lands") is None

    def test_category_and_other_labels_are_not_types(self) -> None:
        assert header_primary_type("@Sorceries") is None
        assert header_primary_type("Other") is None
        assert header_primary_type("Sideboard") is None


class TestTypeSectionLabel:
    def test_round_trips_through_header_primary_type(self) -> None:
        for ptype in PRIMARY_TYPES:
            assert header_primary_type(type_section_label(ptype)) == ptype

    def test_unknown_is_other(self) -> None:
        assert type_section_label(None) == "Other"
        assert primary_type("Conspiracy") is None
