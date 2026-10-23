"""Vim-style macro recording and playback.

Supports q{register} to record, q to stop, @{register} to play,
and @@ to replay the last-played macro. As in vim, an uppercase
register names its lowercase one: qA appends to macro a, @A plays it.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass

# A terminal paste is one event, not keys: a recording stores it as a
# single pseudo-key carrying the text, and replay pastes it again
_PASTE_PREFIX = "\x00paste:"


def paste_key(text: str) -> str:
    """The pseudo-key that records a paste of `text` in a macro."""
    return _PASTE_PREFIX + text


def pasted_text(key: str) -> str | None:
    """The text a paste pseudo-key carries; None for an ordinary key."""
    return key[len(_PASTE_PREFIX):] if key.startswith(_PASTE_PREFIX) else None


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
        """Begin recording keys into the given register; an uppercase
        register appends to the lowercase macro."""
        name = register.lower()
        existing = self._macros.get(name) if register.isupper() else None
        self._recording = name
        self._buffer = list(existing.keys) if existing else []

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
        return self._macros.get(register.lower())

    def play(self, register: str) -> tuple[str, ...] | None:
        """Return keys for the given register, or None if empty.

        Special: register '@' replays the last-played macro.
        """
        if register == "@" and self._last_played:
            register = self._last_played
        register = register.lower()
        macro = self._macros.get(register)
        if macro is not None:
            self._last_played = register
            return macro.keys
        return None
