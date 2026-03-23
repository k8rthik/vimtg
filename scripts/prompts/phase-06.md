You are building vimtg — a TUI-based MTG deck builder. This is Phase 6: Snapshot-based undo tree with branches and checkpoints.

Read `PROGRESS.md` and existing source files for context.

## Core Concept

Every buffer-modifying operation creates an immutable snapshot. Undo/redo navigates a TREE (not a linear stack) — branching happens naturally when you undo then make a different change. Named checkpoints and branches let you experiment with deck variations.

## 1. Snapshot Model — `src/vimtg/domain/snapshot.py`

```python
@dataclass(frozen=True)
class Snapshot:
    id: str                  # UUID4
    parent_id: str | None    # None for root
    deck_state: str          # Serialized buffer text
    timestamp: datetime
    description: str         # Human-readable change description
    branch: str              # Branch name (default: "main")
    tag: str | None          # Named checkpoint (e.g., "pre-sideboard")

@dataclass(frozen=True)
class SnapshotTree:
    """Tree of snapshots with navigation."""
    nodes: dict[str, Snapshot]
    current_id: str
    branches: dict[str, str]  # branch_name → tip snapshot_id

    @property
    def current(self) -> Snapshot: ...

    def parent(self) -> Snapshot | None:
        """Get parent of current snapshot (for undo)."""

    def children(self) -> list[Snapshot]:
        """Get children of current (for redo). Sorted by timestamp, most recent first."""

    def undo(self) -> "SnapshotTree | None":
        """Return new tree with current moved to parent. None if at root."""

    def redo(self) -> "SnapshotTree | None":
        """Return new tree with current moved to most recent child. None if no children."""

    def add_snapshot(self, deck_state: str, description: str) -> "SnapshotTree":
        """Create new snapshot as child of current. Returns new tree."""

    def checkpoint(self, name: str) -> "SnapshotTree":
        """Tag current snapshot with a name."""

    def create_branch(self, name: str) -> "SnapshotTree":
        """Create new branch at current snapshot."""

    def switch_branch(self, name: str) -> "SnapshotTree":
        """Move current to tip of named branch."""

    def find_by_tag(self, tag: str) -> Snapshot | None: ...

    @staticmethod
    def new(initial_state: str) -> "SnapshotTree":
        """Create new tree with a single root snapshot."""
```

## 2. Snapshot Repository — `src/vimtg/data/snapshot_repository.py`

SQLite storage for persistence across sessions.

```python
class SnapshotRepository:
    def __init__(self, db: Database) -> None: ...

    def save(self, snapshot: Snapshot, deck_path: str) -> None: ...
    def get(self, snapshot_id: str) -> Snapshot | None: ...
    def get_children(self, snapshot_id: str) -> list[Snapshot]: ...
    def get_tree(self, deck_path: str) -> SnapshotTree | None: ...
    def save_tree_state(self, deck_path: str, current_id: str, branches: dict[str, str]) -> None: ...
    def prune(self, deck_path: str, max_snapshots: int = 1000) -> int:
        """Remove oldest snapshots beyond max. Returns count removed."""
```

Schema (add to `schema.py`):
```sql
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    deck_path TEXT NOT NULL,
    parent_id TEXT,
    deck_state TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    description TEXT DEFAULT '',
    branch TEXT DEFAULT 'main',
    tag TEXT,
    FOREIGN KEY (parent_id) REFERENCES snapshots(id)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_deck ON snapshots(deck_path);

CREATE TABLE IF NOT EXISTS snapshot_state (
    deck_path TEXT PRIMARY KEY,
    current_id TEXT NOT NULL,
    branches TEXT DEFAULT '{}',
    FOREIGN KEY (current_id) REFERENCES snapshots(id)
);
```

## 3. History Service — `src/vimtg/services/history_service.py`

```python
class HistoryService:
    """Manages undo/redo tree for a deck buffer."""

    def __init__(self, snapshot_repo: SnapshotRepository | None = None) -> None: ...

    def initialize(self, buffer: Buffer, deck_path: str | None = None) -> None:
        """Create initial snapshot from current buffer state.
        Loads existing tree from repo if deck_path has history."""

    def record(self, buffer: Buffer, description: str) -> None:
        """Record a new snapshot. Auto-debounces: if last record was <2s ago
        and same description, update the existing snapshot instead of creating new."""

    def undo(self) -> Buffer | None:
        """Move to parent snapshot. Returns buffer state, or None if at root."""

    def redo(self) -> Buffer | None:
        """Move to most recent child. Returns buffer state, or None if no children."""

    def checkpoint(self, name: str) -> None:
        """Tag current snapshot."""

    def create_branch(self, name: str) -> None: ...
    def switch_branch(self, name: str) -> Buffer | None: ...
    def list_branches(self) -> list[str]: ...

    def diff(self, other_id: str | None = None) -> list[str]:
        """Compute unified diff between current and other (or parent if None).
        Returns list of diff lines with +/- prefixes."""

    @property
    def can_undo(self) -> bool: ...
    @property
    def can_redo(self) -> bool: ...
    @property
    def tree(self) -> SnapshotTree: ...
```

### Auto-snapshot debounce

Record changes with 2-second debounce: if two `record()` calls happen within 2 seconds with the same description, the second replaces the first (update deck_state, keep same snapshot ID). This prevents snapshot explosion during rapid editing.

## 4. History Commands — `src/vimtg/editor/command_handlers/history_cmds.py`

```python
def cmd_history(buffer, cursor, cmd, ctx):
    """:history — Show snapshot timeline as text (not a separate screen yet).
    Display last 20 snapshots:
      * abc123 [main] 2 min ago  — deleted 4 Goblin Guide
        def456 [main] 5 min ago  — added Lightning Bolt
        ghi789 [main] 10 min ago — initial
    * marks current position."""

def cmd_diff(buffer, cursor, cmd, ctx):
    """:diff [id] — Show unified diff between current and specified snapshot.
    If no id, diff against parent.
    Output:
      - 4 Lightning Bolt
      + 4 Chain Lightning
    """

def cmd_checkpoint(buffer, cursor, cmd, ctx):
    """:checkpoint "name" — Tag current snapshot."""

def cmd_branch(buffer, cursor, cmd, ctx):
    """:branch [name] — Create branch or list branches.
    :branch           → list all branches
    :branch sideboard → create 'sideboard' branch"""

def cmd_checkout(buffer, cursor, cmd, ctx):
    """:checkout name — Switch to branch tip."""
```

## 5. Wire undo/redo keybindings

In MainScreen:
- `u` → HistoryService.undo(), update buffer/cursor
- `Ctrl-R` → HistoryService.redo()
- After any buffer-modifying operation, call `history_service.record(buffer, description)`

Descriptions should be human-readable:
- "added 4 Lightning Bolt"
- "deleted 2 Rest in Peace"
- "sorted by cmc"
- "substituted Lightning Bolt → Chain Lightning"

## Tests — TDD

`tests/domain/test_snapshot.py`:
- `test_new_tree` — creates root snapshot
- `test_add_snapshot` — tree grows with new child
- `test_undo` — moves to parent
- `test_redo` — moves to most recent child
- `test_undo_at_root` — returns None
- `test_redo_at_leaf` — returns None
- `test_branch_after_undo` — undo then new change creates branch
- `test_checkpoint` — tags current snapshot
- `test_create_branch` — named branch created
- `test_switch_branch` — moves to branch tip
- `test_redo_chooses_most_recent` — with multiple children, redo picks newest

`tests/data/test_snapshot_repository.py`:
- `test_save_and_get` — round-trip persistence
- `test_get_tree` — reconstruct tree from DB
- `test_prune` — removes old snapshots

`tests/services/test_history_service.py`:
- `test_undo_redo_cycle` — make changes, undo, redo, verify states
- `test_debounce` — rapid changes within 2s coalesce
- `test_branch_on_diverge` — undo then change creates implicit branch
- `test_diff_output` — correct +/- format

## IMPORTANT

- The undo tree is the killer feature — it means you never lose a deck variation
- Debounce prevents snapshot explosion (thousands of snapshots for rapid typing)
- Persistence via SQLite means history survives across sessions
- Diff output uses the same text-column style as the rest of the tool
- All SnapshotTree operations return NEW trees (immutable)
- Prune at 1000 snapshots per deck to bound storage
