"""vim's jumplist: the rows a jump left, walked by Ctrl-O and Ctrl-I.

TUI-agnostic, immutable. A jump (G, a search, a mark, ...) adds the row
it left as the newest entry, dropping an older entry for the same row;
`index` is where Ctrl-O / Ctrl-I stand while walking it, and equals
len(rows) when not walking. Rows are not shifted by edits: callers clamp
a row to the buffer before moving there.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_JUMPS = 100  # vim keeps a hundred


def _appended(rows: tuple[int, ...], row: int) -> tuple[int, ...]:
    return (*(r for r in rows if r != row), row)[-MAX_JUMPS:]


@dataclass(frozen=True)
class JumpList:
    rows: tuple[int, ...] = ()
    index: int = 0

    def jump(self, origin: int) -> JumpList:
        """A jump left `origin`: it is the newest entry, and walking
        starts again from the end."""
        rows = _appended(self.rows, origin)
        return JumpList(rows, len(rows))

    def back(self, current: int, count: int = 1) -> tuple[JumpList, int | None]:
        """Ctrl-O: `count` entries older. Leaving the end first records
        `current`, so Ctrl-I can come back to it. None: nothing older."""
        rows, index = self.rows, self.index
        if index >= len(rows):
            rows = _appended(rows, current)
            index = len(rows) - 1
        target = index - count
        if target < 0:
            return JumpList(rows, index), None
        return JumpList(rows, target), rows[target]

    def forward(self, count: int = 1) -> tuple[JumpList, int | None]:
        """Ctrl-I: `count` entries newer; None at the newest."""
        target = self.index + count
        if target >= len(self.rows):
            return self, None
        return JumpList(self.rows, target), self.rows[target]
