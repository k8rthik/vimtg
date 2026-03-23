"""Tests for vimtg.editor.dot_repeat — dot-repeat tracking."""

from vimtg.editor.dot_repeat import DotRepeat, RepeatableAction


class TestRepeatableAction:
    def test_frozen_dataclass(self) -> None:
        action = RepeatableAction(action_type="operator", operator="d", motion="j")
        assert action.action_type == "operator"
        assert action.operator == "d"
        assert action.motion == "j"
        assert action.count == 1
        assert action.register is None
        assert action.inserted_text is None

    def test_defaults(self) -> None:
        action = RepeatableAction(action_type="insert")
        assert action.operator is None
        assert action.motion is None
        assert action.count == 1
        assert action.register is None
        assert action.inserted_text is None


class TestDotRepeat:
    def test_no_action_initially(self) -> None:
        dr = DotRepeat()
        assert dr.last_action is None

    def test_record_and_get(self) -> None:
        dr = DotRepeat()
        action = RepeatableAction(
            action_type="operator", operator="d", motion="j", count=3
        )
        dr.record(action)
        assert dr.last_action is action

    def test_overwrite(self) -> None:
        dr = DotRepeat()
        first = RepeatableAction(action_type="operator", operator="d", motion="j")
        second = RepeatableAction(action_type="operator", operator="y", motion="k")
        dr.record(first)
        dr.record(second)
        assert dr.last_action is second

    def test_record_insert_action(self) -> None:
        dr = DotRepeat()
        action = RepeatableAction(
            action_type="insert", inserted_text="4 Lightning Bolt"
        )
        dr.record(action)
        assert dr.last_action is action
        assert dr.last_action.inserted_text == "4 Lightning Bolt"

    def test_record_quantity_action(self) -> None:
        dr = DotRepeat()
        action = RepeatableAction(action_type="quantity", operator="+")
        dr.record(action)
        assert dr.last_action is action

    def test_ignores_non_repeatable_type(self) -> None:
        dr = DotRepeat()
        good = RepeatableAction(action_type="operator", operator="d")
        bad = RepeatableAction(action_type="motion")
        dr.record(good)
        dr.record(bad)
        # Should still be the operator, since "motion" is not repeatable
        assert dr.last_action is good

    def test_clear(self) -> None:
        dr = DotRepeat()
        action = RepeatableAction(action_type="operator", operator="d")
        dr.record(action)
        dr.clear()
        assert dr.last_action is None

    def test_record_with_register(self) -> None:
        dr = DotRepeat()
        action = RepeatableAction(
            action_type="operator", operator="d", register="a", count=2
        )
        dr.record(action)
        assert dr.last_action.register == "a"
        assert dr.last_action.count == 2
