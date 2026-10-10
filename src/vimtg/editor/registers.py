"""Immutable vim-style register storage for yank/delete/paste.

Supports named registers (a-z), numbered registers (0-9),
uppercase-appends (A-Z append to a-z), the black hole register "_
(callers skip storing — see operators.store_lines), and the clipboard
register "+ ("* is the same register; the session mirrors writes to
the system clipboard).

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass

BLACK_HOLE = "_"
CLIPBOARD = "+"
# Every register name a '"x' prefix accepts besides letters and digits
SPECIAL_REGISTERS = frozenset({'"', BLACK_HOLE, CLIPBOARD, "*"})


def canonical_register(name: str) -> str:
    """The register `name` reads and writes: "* and "+ are one register."""
    return CLIPBOARD if name == "*" else name


def is_clipboard_register(name: str | None) -> bool:
    return name is not None and canonical_register(name) == CLIPBOARD


@dataclass(frozen=True)
class Register:
    content: tuple[str, ...]
    linewise: bool = True


class RegisterStore:
    """Immutable-style register storage. All mutations return new instances."""

    __slots__ = ("_registers",)

    def __init__(self) -> None:
        self._registers: dict[str, Register] = {}

    def get(self, name: str) -> Register:
        """Return register by name, or an empty register if unset."""
        return self._registers.get(canonical_register(name), Register(content=()))

    def set(self, name: str, content: tuple[str, ...], linewise: bool = True) -> RegisterStore:
        """Return new RegisterStore with register set. Uppercase appends to lowercase."""
        name = canonical_register(name)
        new = RegisterStore()
        new._registers = dict(self._registers)
        if name.isupper():
            lower = name.lower()
            existing = new._registers.get(lower, Register(content=()))
            new._registers[lower] = Register(
                content=existing.content + content, linewise=linewise
            )
        else:
            new._registers[name] = Register(content=content, linewise=linewise)
        return new

    def set_unnamed(
        self, content: tuple[str, ...], is_delete: bool = False
    ) -> RegisterStore:
        """Set unnamed register. If delete, shift numbered registers 1-9."""
        new = RegisterStore()
        new._registers = dict(self._registers)
        new._registers['"'] = Register(content=content)
        if is_delete:
            for i in range(9, 1, -1):
                prev = new._registers.get(str(i - 1))
                if prev:
                    new._registers[str(i)] = prev
            new._registers["1"] = Register(content=content)
        else:
            new._registers["0"] = Register(content=content)
        return new

    @property
    def unnamed(self) -> Register:
        """Return the unnamed register (")."""
        return self.get('"')

    def names(self) -> tuple[str, ...]:
        """Names of the registers holding something, in :registers order:
        unnamed, numbered, named, then the rest."""
        def order(name: str) -> tuple[int, str]:
            if name == '"':
                return (0, name)
            if name.isdigit():
                return (1, name)
            if name.isalpha():
                return (2, name)
            return (3, name)

        return tuple(
            sorted((n for n, r in self._registers.items() if r.content), key=order)
        )
