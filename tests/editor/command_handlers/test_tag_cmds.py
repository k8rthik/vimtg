"""Tests for tag commands: :tag, :untag, :tags, :dtag, :duntag, :filter, :retag."""

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.tag_cmds import (
    cmd_dtag,
    cmd_duntag,
    cmd_filter,
    cmd_retag,
    cmd_tag,
    cmd_tags,
    cmd_untag,
)
from vimtg.editor.commands import CommandRange, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _buf(text: str) -> Buffer:
    return Buffer.from_text(text)


def _ctx() -> EditorContext:
    return EditorContext()


def _cmd(
    name: str, args: str = "", bang: bool = False, cmd_range: CommandRange | None = None,
) -> ParsedCommand:
    return ParsedCommand(name=name, args=args, bang=bang, cmd_range=cmd_range)


SAMPLE_DECK = """\
// Deck: Test
// Format: modern

4 Goblin Guide
4 Lightning Bolt
2 Skullcrack
SB: 2 Rest in Peace"""


class TestCmdTag:
    def test_tag_single_card(self):
        buf = _buf(SAMPLE_DECK)
        cursor = Cursor(row=3, col=0)  # Goblin Guide
        ctx = _ctx()
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", "core"), ctx)
        assert buf.tags_at(3) == frozenset({"core"})
        assert "Tagged 1" in ctx.message

    def test_tag_multiple_names(self):
        buf = _buf(SAMPLE_DECK)
        cursor = Cursor(row=3, col=0)
        ctx = _ctx()
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", "core burn-pkg"), ctx)
        assert buf.tags_at(3) == frozenset({"core", "burn-pkg"})

    def test_tag_range(self):
        buf = _buf(SAMPLE_DECK)
        cursor = Cursor(row=3, col=0)
        ctx = _ctx()
        rng = CommandRange(start=3, end=5)
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", "flex", cmd_range=rng), ctx)
        assert buf.tags_at(3) == frozenset({"flex"})
        assert buf.tags_at(4) == frozenset({"flex"})
        assert buf.tags_at(5) == frozenset({"flex"})

    def test_tag_reversed_range_normalized(self):
        # :5,3tag should behave the same as :3,5tag (vim normalizes).
        buf = _buf(SAMPLE_DECK)
        cursor = Cursor(row=3, col=0)
        ctx = _ctx()
        rng = CommandRange(start=5, end=3)
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", "flex", cmd_range=rng), ctx)
        assert buf.tags_at(3) == frozenset({"flex"})
        assert buf.tags_at(4) == frozenset({"flex"})
        assert buf.tags_at(5) == frozenset({"flex"})
        assert "Tagged 3" in ctx.message

    def test_tag_range_start_zero(self):
        # end=0 must be preserved (line 0), not coerced to start via falsy `or`.
        buf = _buf("4 Goblin Guide\n4 Lightning Bolt\n")
        ctx = _ctx()
        rng = CommandRange(start=0, end=0)
        buf, _ = cmd_tag(buf, Cursor(0, 0), _cmd("tag", "core", cmd_range=rng), ctx)
        assert buf.tags_at(0) == frozenset({"core"})

    def test_tag_non_card_line_skipped(self):
        buf = _buf(SAMPLE_DECK)
        cursor = Cursor(row=0, col=0)  # metadata line
        ctx = _ctx()
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", "core"), ctx)
        assert "No card lines" in ctx.message

    def test_tag_no_name(self):
        buf = _buf(SAMPLE_DECK)
        cursor = Cursor(row=3, col=0)
        ctx = _ctx()
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", ""), ctx)
        assert ctx.error

    def test_tag_invalid_name(self):
        buf = _buf(SAMPLE_DECK)
        cursor = Cursor(row=3, col=0)
        ctx = _ctx()
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", "123bad"), ctx)
        assert ctx.error

    def test_tag_idempotent(self):
        buf = _buf(SAMPLE_DECK)
        cursor = Cursor(row=3, col=0)
        ctx = _ctx()
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", "core"), ctx)
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", "core"), _ctx())
        assert buf.tags_at(3) == frozenset({"core"})

    def test_tag_preserves_card_name(self):
        buf = _buf(SAMPLE_DECK)
        cursor = Cursor(row=3, col=0)
        ctx = _ctx()
        buf, _ = cmd_tag(buf, cursor, _cmd("tag", "core"), ctx)
        assert buf.card_name_at(3) == "Goblin Guide"


class TestCmdUntag:
    def test_untag_specific(self):
        buf = _buf("4 Goblin Guide  #core #burn\n")
        cursor = Cursor(row=0, col=0)
        ctx = _ctx()
        buf, _ = cmd_untag(buf, cursor, _cmd("untag", "burn"), ctx)
        assert buf.tags_at(0) == frozenset({"core"})

    def test_untag_bang_clears_all(self):
        buf = _buf("4 Goblin Guide  #core #burn\n")
        cursor = Cursor(row=0, col=0)
        ctx = _ctx()
        buf, _ = cmd_untag(buf, cursor, _cmd("untag", bang=True), ctx)
        assert buf.tags_at(0) == frozenset()

    def test_untag_nonexistent(self):
        buf = _buf("4 Goblin Guide\n")
        cursor = Cursor(row=0, col=0)
        ctx = _ctx()
        buf, _ = cmd_untag(buf, cursor, _cmd("untag", "core"), ctx)
        assert "No matching" in ctx.message


class TestCmdTags:
    def test_list_all_tags(self):
        buf = _buf("4 Goblin Guide  #core\n4 Lightning Bolt  #core #burn\n")
        ctx = _ctx()
        buf, _ = cmd_tags(buf, Cursor(0, 0), _cmd("tags"), ctx)
        assert "#burn(1)" in ctx.message
        assert "#core(2)" in ctx.message

    def test_list_cards_with_tag(self):
        buf = _buf("4 Goblin Guide  #core\n4 Lightning Bolt  #burn\n")
        ctx = _ctx()
        buf, _ = cmd_tags(buf, Cursor(0, 0), _cmd("tags", "core"), ctx)
        assert "Goblin Guide" in ctx.message

    def test_no_tags(self):
        buf = _buf("4 Goblin Guide\n")
        ctx = _ctx()
        buf, _ = cmd_tags(buf, Cursor(0, 0), _cmd("tags"), ctx)
        assert "No tags" in ctx.message


class TestCmdDtag:
    def test_add_deck_tag(self):
        buf = _buf("// Deck: Test\n\n4 Goblin Guide\n")
        ctx = _ctx()
        buf, _ = cmd_dtag(buf, Cursor(0, 0), _cmd("dtag", "aggro"), ctx)
        # Should have a // Tags: aggro line
        found = False
        for i in range(buf.line_count()):
            if "// Tags:" in buf.get_line(i).text:
                assert "aggro" in buf.get_line(i).text
                found = True
        assert found

    def test_add_to_existing_deck_tags(self):
        buf = _buf("// Deck: Test\n// Tags: aggro\n\n4 Goblin Guide\n")
        ctx = _ctx()
        buf, _ = cmd_dtag(buf, Cursor(0, 0), _cmd("dtag", "budget"), ctx)
        for i in range(buf.line_count()):
            text = buf.get_line(i).text
            if "// Tags:" in text:
                assert "aggro" in text
                assert "budget" in text


class TestCmdDuntag:
    def test_remove_deck_tag(self):
        buf = _buf("// Deck: Test\n// Tags: aggro, budget\n\n4 Goblin Guide\n")
        ctx = _ctx()
        buf, _ = cmd_duntag(buf, Cursor(0, 0), _cmd("duntag", "aggro"), ctx)
        for i in range(buf.line_count()):
            text = buf.get_line(i).text
            if "// Tags:" in text:
                assert "aggro" not in text
                assert "budget" in text

    def test_remove_last_deck_tag_removes_line(self):
        buf = _buf("// Deck: Test\n// Tags: aggro\n\n4 Goblin Guide\n")
        ctx = _ctx()
        initial_count = buf.line_count()
        buf, _ = cmd_duntag(buf, Cursor(0, 0), _cmd("duntag", "aggro"), ctx)
        assert buf.line_count() < initial_count


class TestCmdFilter:
    def test_filter_counts(self):
        buf = _buf("4 Goblin Guide  #core\n4 Lightning Bolt  #flex\n4 Lava Spike\n")
        ctx = _ctx()
        buf, _ = cmd_filter(buf, Cursor(0, 0), _cmd("filter", "core"), ctx)
        assert "1/3" in ctx.message

    def test_filter_bang_clears(self):
        ctx = _ctx()
        buf = _buf("4 Goblin Guide\n")
        buf, _ = cmd_filter(buf, Cursor(0, 0), _cmd("filter", bang=True), ctx)
        assert "cleared" in ctx.message.lower()

    def test_filter_no_args(self):
        ctx = _ctx()
        buf = _buf("4 Goblin Guide\n")
        buf, _ = cmd_filter(buf, Cursor(0, 0), _cmd("filter"), ctx)
        assert ctx.error


class TestCmdRetag:
    def test_rename_tag(self):
        buf = _buf("4 Goblin Guide  #old-tag\n4 Lightning Bolt  #old-tag\n")
        ctx = _ctx()
        buf, _ = cmd_retag(buf, Cursor(0, 0), _cmd("retag", "/old-tag/new-tag/"), ctx)
        assert buf.tags_at(0) == frozenset({"new-tag"})
        assert buf.tags_at(1) == frozenset({"new-tag"})
        assert "2 card" in ctx.message

    def test_rename_nonexistent(self):
        buf = _buf("4 Goblin Guide  #core\n")
        ctx = _ctx()
        buf, _ = cmd_retag(buf, Cursor(0, 0), _cmd("retag", "/missing/new/"), ctx)
        assert "No cards" in ctx.message

    def test_rename_bad_syntax(self):
        buf = _buf("4 Goblin Guide\n")
        ctx = _ctx()
        buf, _ = cmd_retag(buf, Cursor(0, 0), _cmd("retag", "bad"), ctx)
        assert ctx.error
