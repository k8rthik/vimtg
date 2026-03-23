"""Immutable vim-style register storage for yank/delete/paste.

Supports named registers (a-z), numbered registers (0-9),
and uppercase-appends (A-Z append to a-z).

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass


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
        return self._registers.get(name, Register(content=()))

    def set(self, name: str, content: tuple[str, ...], linewise: bool = True) -> RegisterStore:
        """Return new RegisterStore with register set. Uppercase appends to lowercase."""
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
