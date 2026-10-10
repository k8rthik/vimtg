"""Tests for the system clipboard helper (native tools, OSC 52 fallback)."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from vimtg.services.clipboard import (
    OSC52,
    CopyResult,
    copy_message,
    copy_to_clipboard,
    read_clipboard,
)


class FakeRunner:
    """Records subprocess.run calls; returncode/stdout per program name."""

    def __init__(
        self,
        codes: dict[str, int] | None = None,
        stdout: dict[str, bytes] | None = None,
        raises: dict[str, BaseException] | None = None,
    ) -> None:
        self.codes = codes or {}
        self.stdout = stdout or {}
        self.raises = raises or {}
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((args, kwargs))
        prog = args[0]
        if prog in self.raises:
            raise self.raises[prog]
        return subprocess.CompletedProcess(
            args, self.codes.get(prog, 0), self.stdout.get(prog, b""), b""
        )


def which_of(*available: str):  # noqa: ANN201
    return lambda name: f"/usr/bin/{name}" if name in available else None


class TestCopy:
    def test_wayland_uses_wl_copy(self) -> None:
        run = FakeRunner()
        result = copy_to_clipboard(
            "4 Lightning Bolt", env={"WAYLAND_DISPLAY": "wayland-0"},
            platform="linux", which=which_of("wl-copy"), run=run,
        )
        assert result == CopyResult(True, "wl-copy")
        assert result.confirmed
        args, kwargs = run.calls[0]
        assert args == ["wl-copy"]
        assert kwargs["input"] == b"4 Lightning Bolt"
        # never a captured pipe: forked clipboard daemons would hang run()
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["timeout"] > 0

    def test_macos_uses_pbcopy(self) -> None:
        run = FakeRunner()
        result = copy_to_clipboard(
            "x", env={}, platform="darwin", which=which_of("pbcopy"), run=run,
        )
        assert result.method == "pbcopy"

    def test_x11_falls_back_from_failing_xclip_to_xsel(self) -> None:
        run = FakeRunner(codes={"xclip": 1})
        result = copy_to_clipboard(
            "x", env={"DISPLAY": ":0"}, platform="linux",
            which=which_of("xclip", "xsel"), run=run,
        )
        assert result.method == "xsel"
        assert [c[0][0] for c in run.calls] == ["xclip", "xsel"]

    def test_clip_exe_gets_utf16(self) -> None:
        run = FakeRunner()
        result = copy_to_clipboard(
            "Æther Vial", env={}, platform="win32", which=which_of("clip.exe"), run=run,
        )
        assert result.method == "clip.exe"
        assert run.calls[0][1]["input"] == "Æther Vial".encode("utf-16")

    def test_tool_timeout_falls_through_to_osc52(self) -> None:
        sent: list[str] = []
        run = FakeRunner(raises={"xclip": subprocess.TimeoutExpired("xclip", 3)})
        result = copy_to_clipboard(
            "x", osc52=sent.append, env={"DISPLAY": ":0"}, platform="linux",
            which=which_of("xclip"), run=run,
        )
        assert result == CopyResult(True, OSC52)
        assert not result.confirmed
        assert sent == ["x"]

    def test_no_tool_uses_osc52(self) -> None:
        sent: list[str] = []
        result = copy_to_clipboard(
            "deck", osc52=sent.append, env={}, platform="linux",
            which=which_of(), run=FakeRunner(),
        )
        assert result.method == OSC52
        assert sent == ["deck"]

    def test_ssh_prefers_osc52_over_remote_tools(self) -> None:
        sent: list[str] = []
        run = FakeRunner()
        result = copy_to_clipboard(
            "deck", osc52=sent.append,
            env={"SSH_TTY": "/dev/pts/1", "DISPLAY": ":0"}, platform="linux",
            which=which_of("xclip"), run=run,
        )
        assert result.method == OSC52
        assert run.calls == []

    def test_nothing_works_is_reported_not_claimed(self) -> None:
        result = copy_to_clipboard(
            "deck", osc52=None, env={}, platform="linux",
            which=which_of(), run=FakeRunner(),
        )
        assert result == CopyResult(False)

    def test_osc52_writer_error_is_a_failure(self) -> None:
        def broken(_text: str) -> None:
            raise OSError("terminal gone")

        result = copy_to_clipboard(
            "deck", osc52=broken, env={}, platform="linux",
            which=which_of(), run=FakeRunner(),
        )
        assert result.ok is False

    def test_never_writes_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Regression: the old helper wrote OSC 52 bytes straight to
        stdout, under Textual's feet."""
        copy_to_clipboard(
            "deck", osc52=lambda _t: None, env={}, platform="linux",
            which=which_of(), run=FakeRunner(),
        )
        assert capsys.readouterr().out == ""


class TestRead:
    def test_reads_wl_paste(self) -> None:
        run = FakeRunner(stdout={"wl-paste": b"4 Lightning Bolt\r\n2 Shock\r\n"})
        text = read_clipboard(
            env={"WAYLAND_DISPLAY": "w"}, platform="linux",
            which=which_of("wl-paste"), run=run,
        )
        assert text == "4 Lightning Bolt\n2 Shock\n"

    def test_failing_reader_falls_through(self) -> None:
        run = FakeRunner(codes={"xclip": 1}, stdout={"xsel": b"1 Ponder"})
        text = read_clipboard(
            env={"DISPLAY": ":0"}, platform="linux",
            which=which_of("xclip", "xsel"), run=run,
        )
        assert text == "1 Ponder"

    def test_no_reader_returns_none(self) -> None:
        assert read_clipboard(
            env={}, platform="linux", which=which_of(), run=FakeRunner()
        ) is None

    def test_reader_oserror_returns_none(self) -> None:
        run = FakeRunner(raises={"pbpaste": OSError("boom")})
        assert read_clipboard(
            env={}, platform="darwin", which=which_of("pbpaste"), run=run
        ) is None


class TestMessage:
    def test_confirmed(self) -> None:
        msg, err = copy_message(CopyResult(True, "pbcopy"), "arena (3 lines)")
        assert msg == "Copied arena (3 lines) to clipboard"
        assert not err

    def test_osc52_is_honest(self) -> None:
        msg, err = copy_message(CopyResult(True, OSC52), "arena (3 lines)")
        assert msg.startswith("Sent arena (3 lines) to the terminal clipboard")
        assert "Copied" not in msg
        assert not err

    def test_failure(self) -> None:
        msg, err = copy_message(CopyResult(False), "arena")
        assert msg.startswith("E: No clipboard available")
        assert err
