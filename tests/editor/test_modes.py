"""Tests for the Mode enum and ModeManager."""

import pytest

from vimtg.editor.modes import Mode, ModeManager


class TestModeEnum:
    def test_initial_mode_normal(self) -> None:
        manager = ModeManager()
        assert manager.current == Mode.NORMAL

    def test_all_modes_have_display_values(self) -> None:
        expected = {"NORMAL", "INSERT", "VISUAL", "V-LINE", "COMMAND", "SEARCH"}
        actual = {m.value for m in Mode}
        assert actual == expected


class TestModeTransitions:
    def test_valid_transition_normal_to_insert(self) -> None:
        manager = ModeManager()
        result = manager.transition(Mode.INSERT)
        assert result == Mode.INSERT
        assert manager.current == Mode.INSERT

    def test_valid_transition_normal_to_visual(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.VISUAL)
        assert manager.current == Mode.VISUAL

    def test_valid_transition_normal_to_command(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.COMMAND)
        assert manager.current == Mode.COMMAND

    def test_valid_transition_normal_to_search(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.SEARCH)
        assert manager.current == Mode.SEARCH

    def test_valid_transition_normal_to_visual_line(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.VISUAL_LINE)
        assert manager.current == Mode.VISUAL_LINE

    def test_valid_transition_insert_to_normal(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.INSERT)
        manager.transition(Mode.NORMAL)
        assert manager.current == Mode.NORMAL

    def test_invalid_transition_insert_to_visual(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.INSERT)
        with pytest.raises(ValueError, match="Invalid transition"):
            manager.transition(Mode.VISUAL)

    def test_invalid_transition_normal_to_normal(self) -> None:
        manager = ModeManager()
        with pytest.raises(ValueError, match="Invalid transition"):
            manager.transition(Mode.NORMAL)

    def test_invalid_transition_command_to_insert(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.COMMAND)
        with pytest.raises(ValueError, match="Invalid transition"):
            manager.transition(Mode.INSERT)


class TestModeCallbacks:
    def test_callback_fires(self) -> None:
        manager = ModeManager()
        received: list[tuple[Mode, Mode]] = []
        manager.on_mode_change(lambda old, new: received.append((old, new)))
        manager.transition(Mode.INSERT)
        assert received == [(Mode.NORMAL, Mode.INSERT)]

    def test_multiple_callbacks_fire(self) -> None:
        manager = ModeManager()
        results_a: list[Mode] = []
        results_b: list[Mode] = []
        manager.on_mode_change(lambda _old, new: results_a.append(new))
        manager.on_mode_change(lambda _old, new: results_b.append(new))
        manager.transition(Mode.INSERT)
        assert results_a == [Mode.INSERT]
        assert results_b == [Mode.INSERT]

    def test_callback_fires_on_force_normal(self) -> None:
        manager = ModeManager()
        received: list[tuple[Mode, Mode]] = []
        manager.on_mode_change(lambda old, new: received.append((old, new)))
        manager.transition(Mode.INSERT)
        received.clear()
        manager.force_normal()
        assert received == [(Mode.INSERT, Mode.NORMAL)]


class TestPreviousMode:
    def test_previous_mode_initially_none(self) -> None:
        manager = ModeManager()
        assert manager.previous is None

    def test_previous_mode_tracked(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.INSERT)
        assert manager.previous == Mode.NORMAL
        manager.transition(Mode.NORMAL)
        assert manager.previous == Mode.INSERT


class TestForceNormal:
    def test_force_normal_from_insert(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.INSERT)
        manager.force_normal()
        assert manager.current == Mode.NORMAL

    def test_force_normal_from_visual(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.VISUAL)
        manager.force_normal()
        assert manager.current == Mode.NORMAL

    def test_force_normal_from_command(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.COMMAND)
        manager.force_normal()
        assert manager.current == Mode.NORMAL

    def test_force_normal_from_search(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.SEARCH)
        manager.force_normal()
        assert manager.current == Mode.NORMAL

    def test_force_normal_from_normal_is_noop(self) -> None:
        manager = ModeManager()
        manager.force_normal()
        assert manager.current == Mode.NORMAL
        assert manager.previous is None  # no change occurred

    def test_force_normal_tracks_previous(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.VISUAL_LINE)
        manager.force_normal()
        assert manager.previous == Mode.VISUAL_LINE


class TestModeHelpers:
    def test_is_normal(self) -> None:
        manager = ModeManager()
        assert manager.is_normal() is True
        manager.transition(Mode.INSERT)
        assert manager.is_normal() is False

    def test_is_insert(self) -> None:
        manager = ModeManager()
        assert manager.is_insert() is False
        manager.transition(Mode.INSERT)
        assert manager.is_insert() is True

    def test_is_visual(self) -> None:
        manager = ModeManager()
        assert manager.is_visual() is False
        manager.transition(Mode.VISUAL)
        assert manager.is_visual() is True

    def test_is_visual_includes_visual_line(self) -> None:
        manager = ModeManager()
        manager.transition(Mode.VISUAL_LINE)
        assert manager.is_visual() is True

    def test_is_command(self) -> None:
        manager = ModeManager()
        assert manager.is_command() is False
        manager.transition(Mode.COMMAND)
        assert manager.is_command() is True
