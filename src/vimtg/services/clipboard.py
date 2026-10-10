"""System clipboard access: native tools first, OSC 52 as a fallback.

Copying tries, in order, the clipboard tools of the platform (pbcopy,
wl-copy, xclip, xsel, clip.exe) — their exit status says whether the
copy worked — and then OSC 52, an escape sequence asking the terminal
to set the clipboard. OSC 52 cannot be confirmed (the terminal may
ignore it), so callers word its result as "sent", not "copied". Over
SSH the native tools would fill the *remote* machine's clipboard, so
OSC 52 goes first there.

The OSC 52 writer is passed in: inside the TUI it must be Textual's
``App.copy_to_clipboard`` — writing escape bytes straight to stdout
while Textual owns the terminal interleaves them with its output.

Reading uses the matching paste tools (pbpaste, wl-paste, xclip -o,
xsel -o, PowerShell Get-Clipboard). There is no portable terminal read.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

# Seconds a clipboard tool may take before it counts as failed
_TOOL_TIMEOUT = 3.0

OSC52 = "osc52"

Which = Callable[[str], str | None]
Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


@dataclass(frozen=True)
class _Tool:
    name: str
    copy_args: tuple[str, ...]
    paste_args: tuple[str, ...]
    encoding: str = "utf-8"


def _tools(env: Mapping[str, str], platform: str) -> list[_Tool]:
    """Clipboard tools worth trying here, most specific first."""
    tools: list[_Tool] = []
    if platform == "darwin":
        tools.append(_Tool("pbcopy", ("pbcopy",), ("pbpaste",)))
    if env.get("WAYLAND_DISPLAY"):
        tools.append(_Tool("wl-copy", ("wl-copy",), ("wl-paste", "--no-newline")))
    if env.get("DISPLAY"):
        tools.append(_Tool(
            "xclip",
            ("xclip", "-selection", "clipboard"),
            ("xclip", "-selection", "clipboard", "-o"),
        ))
        tools.append(_Tool(
            "xsel", ("xsel", "--clipboard", "--input"), ("xsel", "--clipboard", "--output"),
        ))
    # Windows, and WSL where clip.exe is on PATH. clip reads UTF-16
    # (with BOM) correctly; other encodings mangle non-ASCII names.
    tools.append(_Tool(
        "clip.exe",
        ("clip.exe",),
        ("powershell.exe", "-NoProfile", "-Command", "Get-Clipboard"),
        encoding="utf-16",
    ))
    return tools


@dataclass(frozen=True)
class CopyResult:
    """How a copy went. `method` names the path that took the text
    ('' when none did); only a native tool's success is confirmed."""

    ok: bool
    method: str = ""

    @property
    def confirmed(self) -> bool:
        return self.ok and self.method != OSC52


def copy_to_clipboard(
    text: str,
    *,
    osc52: Callable[[str], None] | None = None,
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
    which: Which | None = None,
    run: Runner | None = None,
) -> CopyResult:
    """Put `text` on the system clipboard by the first path that works.

    `osc52` sends the OSC 52 sequence (Textual's App.copy_to_clipboard
    in the TUI); None skips that fallback. The remaining parameters
    exist for tests.
    """
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    which = which or shutil.which
    run = run or subprocess.run
    over_ssh = bool(env.get("SSH_TTY") or env.get("SSH_CONNECTION"))
    if over_ssh and _send_osc52(text, osc52):
        return CopyResult(True, OSC52)
    for tool in _tools(env, platform):
        if which(tool.copy_args[0]) is None:
            continue
        if _run_copy(tool, text, run):
            return CopyResult(True, tool.name)
    if not over_ssh and _send_osc52(text, osc52):
        return CopyResult(True, OSC52)
    return CopyResult(False)


def _send_osc52(text: str, osc52: Callable[[str], None] | None) -> bool:
    if osc52 is None:
        return False
    try:
        osc52(text)
    except (OSError, ValueError):
        return False
    return True


def _run_copy(tool: _Tool, text: str, run: Runner) -> bool:
    try:
        # Output goes to DEVNULL, not a pipe: xclip and wl-copy fork a
        # child that keeps serving the selection, and a captured pipe
        # would hold run() open until that child exits.
        done = run(
            list(tool.copy_args),
            input=text.encode(tool.encoding),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_TOOL_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def read_clipboard(
    *,
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
    which: Which | None = None,
    run: Runner | None = None,
) -> str | None:
    """The clipboard's text, or None when no paste tool could read it."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    which = which or shutil.which
    run = run or subprocess.run
    for tool in _tools(env, platform):
        if which(tool.paste_args[0]) is None:
            continue
        text = _run_paste(tool.paste_args, run)
        if text is not None:
            return text
    return None


def _run_paste(args: Sequence[str], run: Runner) -> str | None:
    try:
        done = run(
            list(args),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_TOOL_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")


def copy_message(result: CopyResult, what: str) -> tuple[str, bool]:
    """(status message, is_error) describing a copy of `what`."""
    if result.confirmed:
        return f"Copied {what} to clipboard", False
    if result.ok:
        return (
            f"Sent {what} to the terminal clipboard (OSC 52) — "
            "paste to check; some terminals block it",
            False,
        )
    return (
        "E: No clipboard available — install wl-clipboard, xclip or xsel, "
        "use a terminal with OSC 52, or :export to a file",
        True,
    )
