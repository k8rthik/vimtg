"""SQL compilation of parsed searches (vimtg.data.search_sql)."""

from __future__ import annotations

from vimtg.data.search_sql import compile_search
from vimtg.domain.search import parse_search


class TestDoubleNegation:
    def test_not_not_x_compiles_to_x(self) -> None:
        node = parse_search("--bolt")
        assert node is not None
        sql, _ = compile_search(node)
        assert "NOT" not in sql

    def test_a_pile_of_minuses_never_nests_past_one_not(self) -> None:
        # 42 of them used to overflow SQLite's parser stack (a few
        # hundred now hit the term cap in the parser first)
        for n in (41, 42, 150):
            node = parse_search("-" * n + "bolt")
            assert node is not None
            sql, _ = compile_search(node)
            assert sql.count("NOT") == n % 2


class TestOracleTags:
    def test_tag_compiles_to_one_exists_over_card_tags(self) -> None:
        node = parse_search("otag:ramp")
        assert node is not None
        sql, params = compile_search(node)
        assert sql.count("EXISTS (SELECT 1 FROM card_tags") == 1
        assert "tag_aliases" in sql
        assert params == ["ramp", "ramp"]
