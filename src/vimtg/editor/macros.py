"""Vim-style macro recording and playback.

Supports q{register} to record, q to stop, @{register} to play,
and @@ to replay the last-played macro.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Macro:
    """An immutable sequence of recorded key presses."""

    keys: tuple[str, ...]


class MacroRecorder:
    """Records and plays back named macros (a-z registers)."""

    def __init__(self) -> None:
        self._recording: str | None = None
        self._buffer: list[str] = []
        self._macros: dict[str, Macro] = {}
        self._last_played: str | None = None

    @property
    def is_recording(self) -> bool:
        """True when actively recording into a register."""
        return self._recording is not None

    @property
    def recording_register(self) -> str | None:
        """The register currently being recorded into, or None."""
        return self._recording

    def start_recording(self, register: str) -> None:
        """Begin recording keys into the given register."""
        self._recording = register
        self._buffer = []

    def stop_recording(self) -> Macro | None:
        """Stop recording and store the macro. Returns the macro or None."""
        if self._recording is None:
            return None
        macro = Macro(keys=tuple(self._buffer))
        self._macros[self._recording] = macro
        self._recording = None
        self._buffer = []
        return macro

    def record_key(self, key: str) -> None:
        """Append a key to the current recording buffer (no-op if not recording)."""
        if self._recording is not None:
            self._buffer.append(key)

    def get(self, register: str) -> Macro | None:
        """Look up a macro by register name."""
        return self._macros.get(register)

    def play(self, register: str) -> tuple[str, ...] | None:
        """Return keys for the given register, or None if empty.

        Special: register '@' replays the last-played macro.
        """
        if register == "@" and self._last_played:
            register = self._last_played
        macro = self._macros.get(register)
        if macro is not None:
            self._last_played = register
            return macro.keys
        return None
