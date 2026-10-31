""":collection — the owned-cards CSV the deck is compared against.

TUI-agnostic. Loading happens here (a file read, like :import) so the
command can report the result at once; the TUI keeps the Collection in
its state and re-reads the configured file on each deck open.
"""

from __future__ import annotations

from dataclasses import replace

from vimtg.domain.collection import Collection, CollectionError
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor
from vimtg.services.collection_service import collection_path, load_collection

NO_COLLECTION = "No collection loaded (:collection path.csv)"


def collection_status(collection: Collection | None) -> str:
    """What :collection reports: the loaded file's summary, or how to load one."""
    return collection.status() if collection is not None else NO_COLLECTION


def cmd_collection(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:collection [path] — Load the collection CSV at `path` and remember
    it in settings; bare, report the loaded collection. :collection!
    forgets it (the setting is cleared too)."""
    if ctx.settings is None:
        ctx.fail("Settings not available")
        return buffer, cursor
    arg = cmd.args.strip()
    if cmd.bang and not arg:
        ctx.settings = replace(ctx.settings, collection="")
        ctx.settings_changed = True
        ctx.collection = None
        ctx.collection_set = True
        ctx.message = "Collection cleared"
        return buffer, cursor
    if not arg:
        ctx.message = collection_status(ctx.collection)
        return buffer, cursor
    path = collection_path(arg)
    try:
        collection = load_collection(path)
    except CollectionError as exc:
        ctx.fail(str(exc))
        return buffer, cursor
    ctx.settings = replace(ctx.settings, collection=str(path))
    ctx.settings_changed = True
    ctx.collection = collection
    ctx.collection_set = True
    ctx.message = collection.status()
    return buffer, cursor


def register_collection_commands(registry: CommandRegistry) -> None:
    """Register :collection (alias :coll)."""
    registry.register("collection", cmd_collection, aliases=["coll"])
