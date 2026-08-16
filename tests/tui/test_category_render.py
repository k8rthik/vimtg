"""Category rendering in the deck view."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.tui.deck_renderer import render_line


class TestCategoryBadge:
    def test_category_shown_on_card_line(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n")
        lines = render_line(0, buf, 99, {})
        assert "@ramp" in lines[0].plain

    def test_category_not_duplicated_in_name(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp\n")
        lines = render_line(0, buf, 99, {})
        assert lines[0].plain.count("@ramp") == 1
        assert "Cultivate" in lines[0].plain

    def test_category_header_renders(self) -> None:
        buf = Buffer.from_text("// @ramp\n4 Cultivate  @ramp\n")
        lines = render_line(0, buf, 99, {})
        assert "// @ramp" in lines[0].plain

    def test_category_before_tags(self) -> None:
        buf = Buffer.from_text("4 Cultivate  @ramp  #core\n")
        plain = render_line(0, buf, 99, {})[0].plain
        assert plain.index("@ramp") < plain.index("#core")
