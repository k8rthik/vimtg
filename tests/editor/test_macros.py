"""Tests for vimtg.editor.macros — macro recording and playback."""

from vimtg.editor.macros import Macro, MacroRecorder


class TestMacro:
    def test_frozen_dataclass(self) -> None:
        macro = Macro(keys=("d", "d", "j"))
        assert macro.keys == ("d", "d", "j")

    def test_empty_macro(self) -> None:
        macro = Macro(keys=())
        assert macro.keys == ()


class TestMacroRecorder:
    def test_not_recording_initially(self) -> None:
        rec = MacroRecorder()
        assert rec.is_recording is False
        assert rec.recording_register is None

    def test_start_stop(self) -> None:
        rec = MacroRecorder()
        rec.start_recording("a")
        assert rec.is_recording is True
        assert rec.recording_register == "a"
        rec.record_key("d")
        rec.record_key("d")
        rec.record_key("j")
        macro = rec.stop_recording()
        assert macro is not None
        assert macro.keys == ("d", "d", "j")
        assert rec.is_recording is False
        assert rec.recording_register is None

    def test_play(self) -> None:
        rec = MacroRecorder()
        rec.start_recording("a")
        rec.record_key("d")
        rec.record_key("w")
        rec.stop_recording()
        keys = rec.play("a")
        assert keys == ("d", "w")

    def test_play_last(self) -> None:
        rec = MacroRecorder()
        rec.start_recording("b")
        rec.record_key("y")
        rec.record_key("y")
        rec.stop_recording()
        # First play sets last_played
        rec.play("b")
        # @@ replays last
        keys = rec.play("@")
        assert keys == ("y", "y")

    def test_empty_register(self) -> None:
        rec = MacroRecorder()
        assert rec.get("z") is None
        assert rec.play("z") is None

    def test_is_recording(self) -> None:
        rec = MacroRecorder()
        assert rec.is_recording is False
        rec.start_recording("c")
        assert rec.is_recording is True
        rec.stop_recording()
        assert rec.is_recording is False

    def test_recording_register(self) -> None:
        rec = MacroRecorder()
        assert rec.recording_register is None
        rec.start_recording("x")
        assert rec.recording_register == "x"
        rec.stop_recording()
        assert rec.recording_register is None

    def test_record_key(self) -> None:
        rec = MacroRecorder()
        rec.start_recording("a")
        rec.record_key("j")
        rec.record_key("j")
        rec.record_key("d")
        rec.record_key("d")
        macro = rec.stop_recording()
        assert macro is not None
        assert macro.keys == ("j", "j", "d", "d")

    def test_record_key_noop_when_not_recording(self) -> None:
        rec = MacroRecorder()
        rec.record_key("j")
        # Should not raise; key is silently discarded
        rec.start_recording("a")
        macro = rec.stop_recording()
        assert macro is not None
        assert macro.keys == ()

    def test_stop_recording_when_not_recording(self) -> None:
        rec = MacroRecorder()
        result = rec.stop_recording()
        assert result is None

    def test_get_stored_macro(self) -> None:
        rec = MacroRecorder()
        rec.start_recording("a")
        rec.record_key("+")
        rec.stop_recording()
        macro = rec.get("a")
        assert macro is not None
        assert macro.keys == ("+",)

    def test_overwrite_macro(self) -> None:
        rec = MacroRecorder()
        rec.start_recording("a")
        rec.record_key("x")
        rec.stop_recording()
        rec.start_recording("a")
        rec.record_key("y")
        rec.record_key("y")
        rec.stop_recording()
        macro = rec.get("a")
        assert macro is not None
        assert macro.keys == ("y", "y")

    def test_play_at_with_no_last_played(self) -> None:
        rec = MacroRecorder()
        # @@ with no previous play should return None
        assert rec.play("@") is None
