"""Tests for the OSC52 clipboard helper."""

from __future__ import annotations

import base64
import io

from vimtg.services.clipboard import copy_to_clipboard


class TestCopyToClipboard:
    def test_writes_osc52_envelope(self) -> None:
        stream = io.StringIO()
        ok = copy_to_clipboard("hello", stream=stream)
        assert ok is True
        out = stream.getvalue()
        assert out.startswith("\033]52;c;")
        assert out.endswith("\007")

    def test_payload_is_base64_utf8(self) -> None:
        stream = io.StringIO()
        copy_to_clipboard("4 Lightning Bolt", stream=stream)
        payload = stream.getvalue()[len("\033]52;c;") : -1]
        assert base64.b64decode(payload).decode("utf-8") == "4 Lightning Bolt"

    def test_unicode_roundtrip(self) -> None:
        stream = io.StringIO()
        copy_to_clipboard("Æther — ⚡", stream=stream)
        payload = stream.getvalue()[len("\033]52;c;") : -1]
        assert base64.b64decode(payload).decode("utf-8") == "Æther — ⚡"

    def test_empty_string(self) -> None:
        stream = io.StringIO()
        assert copy_to_clipboard("", stream=stream) is True
        # Envelope present, payload empty
        assert stream.getvalue() == "\033]52;c;\007"

    def test_write_failure_returns_false(self) -> None:
        class BrokenStream:
            def write(self, _: str) -> int:
                raise OSError("nope")

            def flush(self) -> None:
                pass

        assert copy_to_clipboard("data", stream=BrokenStream()) is False
