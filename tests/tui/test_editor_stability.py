"""Editor stability: visual toggles, undo/redo bounds, one change per u,
clean opens, ZZ/ZQ, and the crash safety net.

Key sequences run with the crash net disabled (_strict), so a regression
surfaces as the original exception instead of a status-line message.
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path

import pytest

from vimtg.config.paths import recovery_dir
from vimtg.editor.modes import Mode
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_burn.deck"

# Canonical-format deck: opening it changes nothing
CANONICAL = (
    "// Deck: Burn\n// Format: modern\n// Tags:\n\n"
    "// Creature\n4 Goblin Guide\n4 Monastery Swiftspear\n\n"
    "// Instant\n4 Lightning Bolt\n4 Searing Blaze\n4 Skullcrack\n\n"
    "// Land\n20 Mountain\n"
)


def _deck(tmp_path: Path, text: str = CANONICAL, name: str = "burn.deck") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def _keys(seq: str) -> list[str]:
    """'8G dd u' -> ['8', 'G', 'd', 'd', 'u'] (spaces are separators)."""
    return [c for c in seq if c != " "]


def _reraise(exc: Exception) -> None:
    raise exc


def _strict(scr: MainScreen) -> MainScreen:
    """Disable the crash net so a bug fails the test with its own error."""
    scr.recover_from_crash = _reraise  # type: ignore[method-assign]
    return scr


def _feed(scr: MainScreen, keys: list[str]) -> None:
    _strict(scr)
    for key in keys:
        scr._process_key(key)


def _screen(app: VimTGApp) -> MainScreen:
    scr = app.screen
    assert isinstance(scr, MainScreen)
    return scr


def _cards(scr: MainScreen) -> list[str]:
    buf = scr._state.buffer
    return [
        buf.get_line(i).text for i in range(buf.line_count()) if buf.is_card_line(i)
    ]


# ── (a) visual-mode toggles ────────────────────────────────────────


class TestVisualToggle:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("seq", "mode"),
        [
            ("vv", Mode.NORMAL),
            ("VV", Mode.NORMAL),
            ("jVjV", Mode.NORMAL),
            ("vV", Mode.VISUAL_LINE),
            ("Vv", Mode.VISUAL),
            ("vVv", Mode.VISUAL),
            ("vvv", Mode.VISUAL),
        ],
    )
    async def test_visual_keys_toggle_and_switch(
        self, tmp_path: Path, seq: str, mode: Mode
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys(seq))
            assert scr._state.mode_mgr.current == mode
            if mode == Mode.NORMAL:
                assert scr._state.visual_anchor is None

    @pytest.mark.asyncio
    async def test_switching_kind_keeps_the_anchor(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("6G v j V"))
            assert scr._state.visual_anchor == 5
            _feed(scr, ["d"])
            assert scr._state.mode_mgr.current == Mode.NORMAL
            assert "Goblin Guide" not in "".join(_cards(scr))
            assert "Monastery Swiftspear" not in "".join(_cards(scr))


    @pytest.mark.asyncio
    async def test_swap_ends_after_dot_shrinks_buffer(self, tmp_path: Path) -> None:
        """Found by the fuzz test: '.' inside a selection deletes the
        anchor row, and o then jumped past the end of the buffer."""
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("G dd G V . o"))
            assert scr._state.cursor.row < scr._state.buffer.line_count()


# ── (b) undo/redo restores a shorter buffer ────────────────────────


class TestUndoClampsCursor:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "seq",
        ["G yy p u o", "G yy 5p u o", "G yy 5p u j o", "G yy p u O", "G yy 3p 3u j j o"],
    )
    async def test_open_after_undo_does_not_crash(self, tmp_path: Path, seq: str) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys(seq))
            assert scr._state.mode_mgr.current == Mode.INSERT
            assert scr._state.cursor.row < scr._state.buffer.line_count()

    @pytest.mark.asyncio
    async def test_cursor_is_inside_buffer_after_undo_and_redo(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("G yy 5p"))
            _feed(scr, ["u"])
            assert scr._state.cursor.row < scr._state.buffer.line_count()
            _feed(scr, ["ctrl_r", "g", "g", "u"])
            assert scr._state.cursor.row < scr._state.buffer.line_count()


# ── (c) one change per u ───────────────────────────────────────────


class TestOneChangePerUndo:
    @pytest.mark.asyncio
    async def test_delete_after_undo_never_rewrites_the_original(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            original = scr._state.buffer.to_text()
            _feed(scr, _keys("10G dd u dd u u u"))
            assert scr._state.buffer.to_text() == original
            assert scr._state.modified is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("seq", ["10G dd dd", "10G x j .", "10G dd ."])
    async def test_each_delete_is_its_own_undo_step(
        self, tmp_path: Path, seq: str
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("10G"))
            assert scr._state.buffer.get_line(scr._state.cursor.row).text == (
                "4 Lightning Bolt"
            )
            _feed(scr, _keys(seq))
            after_two = len(_cards(scr))
            _feed(scr, ["u"])
            assert len(_cards(scr)) == after_two + 1
            _feed(scr, ["u"])
            assert len(_cards(scr)) == after_two + 2

    @pytest.mark.asyncio
    async def test_quantity_burst_is_still_one_step(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            original = scr._state.buffer.to_text()
            _feed(scr, _keys("6G + + +"))
            assert "7 Goblin Guide" in scr._state.buffer.to_text()
            _feed(scr, ["u"])
            assert scr._state.buffer.to_text() == original


# ── (d) opening a hand-written deck is not a modification ──────────


class TestCleanOpen:
    @pytest.mark.asyncio
    async def test_hand_written_deck_opens_unmodified_and_quits(
        self, tmp_path: Path
    ) -> None:
        # Empty section, doubled blanks, no blank before headers
        path = _deck(
            tmp_path,
            "// Deck: Messy\n// Creature\n4 Goblin Guide\n\n\n\n"
            "// Enchantment\n\n// Land\n20 Mountain\n// Sideboard\nSB: 2 Path to Exile\n",
        )
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            assert scr._state.modified is False
            await pilot.press("colon", "q", "enter")
            await pilot.pause()
        assert app.return_code == 0

    @pytest.mark.asyncio
    async def test_fixture_deck_opens_unmodified(self, tmp_path: Path) -> None:
        path = tmp_path / "burn.deck"
        shutil.copy(FIXTURE, path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            assert scr._state.modified is False
            # The first undo has nothing to step back into
            _feed(scr, ["u"])
            assert scr._state.modified is False

    @pytest.mark.asyncio
    async def test_undo_back_to_saved_state_is_unmodified(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, _keys("6G dd"))
            assert scr._state.modified is True
            _feed(scr, _keys(":w") + ["enter"])
            assert scr._state.modified is False
            _feed(scr, _keys("dd"))
            assert scr._state.modified is True
            _feed(scr, ["u"])
            assert scr._state.modified is False
            _feed(scr, ["u"])  # before the save: differs from disk
            assert scr._state.modified is True


# ── (e) ZZ / ZQ ────────────────────────────────────────────────────


class TestZZZQ:
    @pytest.mark.asyncio
    async def test_zz_writes_and_quits(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("6", "G", "d", "d", "Z", "Z")
            await pilot.pause()
        assert app.return_code == 0
        assert "Goblin Guide" not in path.read_text()

    @pytest.mark.asyncio
    async def test_zq_quits_discarding_changes(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("6", "G", "d", "d", "Z", "Q")
            await pilot.pause()
        assert app.return_code == 0
        assert path.read_text() == CANONICAL


# ── (f) crash safety net ───────────────────────────────────────────


def _explode(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("boom")


class TestCrashSafetyNet:
    @pytest.mark.asyncio
    async def test_crash_saves_buffer_and_keeps_running(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            await pilot.press("6", "G", "d", "d")
            await pilot.pause()
            monkeypatch.setattr(
                "vimtg.tui.screens.main_screen.handle_motion", _explode
            )
            await pilot.press("j")
            await pilot.pause()
            cl = scr.query_one("#command-line", CommandLine)
            assert "internal error" in cl.message and "boom" in cl.message
            recovery = recovery_dir() / "burn.deck"
            assert recovery.exists()
            assert "Goblin Guide" not in recovery.read_text()
            assert "RuntimeError: boom" in (recovery_dir() / "burn.log").read_text()
            monkeypatch.undo()
            # Still alive and editable
            await pilot.press("u")
            await pilot.pause()
            assert "Goblin Guide" in scr._state.buffer.to_text()
            assert app.is_running

    @pytest.mark.asyncio
    async def test_crash_mid_visual_returns_to_normal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            await pilot.press("V")
            monkeypatch.setattr(
                "vimtg.tui.screens.main_screen.handle_motion", _explode
            )
            await pilot.press("j")
            await pilot.pause()
            assert scr._state.mode_mgr.current == Mode.NORMAL
            assert scr._state.visual_anchor is None

    @pytest.mark.asyncio
    async def test_reopen_offers_recover_and_recover_loads_it(
        self, tmp_path: Path
    ) -> None:
        path = _deck(tmp_path)
        recovered_text = CANONICAL.replace("4 Goblin Guide\n", "")
        (recovery_dir() / "burn.deck").write_text(recovered_text)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            cl = scr.query_one("#command-line", CommandLine)
            assert ":recover" in cl.message
            assert scr._state.modified is False
            await pilot.press("colon", *"recover", "enter")
            await pilot.pause()
            assert scr._state.buffer.to_text() == recovered_text
            assert scr._state.modified is True
            # u brings back the on-disk deck
            await pilot.press("u")
            await pilot.pause()
            assert scr._state.buffer.to_text() == CANONICAL
            # A successful :w removes the recovery copy
            await pilot.press("ctrl+r", "colon", "w", "enter")
            await pilot.pause()
        assert not (recovery_dir() / "burn.deck").exists()
        assert path.read_text() == recovered_text

    @pytest.mark.asyncio
    async def test_recover_bang_discards(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        (recovery_dir() / "burn.deck").write_text("4 Island\n")
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("colon", *"recover!", "enter")
            await pilot.pause()
            assert not (recovery_dir() / "burn.deck").exists()
            await pilot.press("colon", *"recover", "enter")
            await pilot.pause()
            cl = _screen(app).query_one("#command-line", CommandLine)
            assert "No recovery file" in cl.message
            assert _screen(app)._state.buffer.to_text() == CANONICAL

    @pytest.mark.asyncio
    async def test_identical_recovery_copy_is_not_offered(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        (recovery_dir() / "burn.deck").write_text(CANONICAL)
        app = VimTGApp(deck_path=path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            cl = _screen(app).query_one("#command-line", CommandLine)
            assert ":recover" not in cl.message
        assert not (recovery_dir() / "burn.deck").exists()

    @pytest.mark.asyncio
    async def test_app_level_handler_writes_recovery(self, tmp_path: Path) -> None:
        path = _deck(tmp_path)
        app = VimTGApp(deck_path=path)
        with pytest.raises(RuntimeError, match="outside keys"):
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                await pilot.press("6", "G", "d", "d")
                await pilot.pause()
                scr = _screen(app)

                def _bad() -> None:
                    raise RuntimeError("outside keys")

                scr.call_later(_bad)
                await pilot.pause()
        text = (recovery_dir() / "burn.deck").read_text()
        assert "Goblin Guide" not in text


# ── Random-key fuzz ────────────────────────────────────────────────

# Normal/visual-mode vocabulary. Left out: keys that leave the editor or
# touch the outside world (':' '/' 'S' 'Z' 'gh' '?' F1) — the ex line is
# covered by its own tests, and random :w would write files.
_FUZZ_KEYS = (
    list("jjkkwb{}GgHMLnN")
    + list("ddyycxpPuu+-.")
    + ["ctrl_r", "ctrl_d", "ctrl_u", "escape", "escape", "enter", "backspace"]
    + list("vVvVoOiA")
    + list("12345")
    + list("zsmdcpio")
    + list("tarlcnp")
    + list("'qa@\"")
    + list("CelBo")
)
_FUZZ_SEEDS = range(8)
_FUZZ_LENGTH = 250


@pytest.mark.asyncio
async def test_random_keys_never_raise(tmp_path: Path) -> None:
    """Seeded random key sequences (plus the known crash repros) run
    through the unguarded key path without an unhandled exception."""
    path = tmp_path / "burn.deck"
    shutil.copy(FIXTURE, path)
    repros = [
        "vv", "VV", "jVjV", "G yy p u o", "G yy 5p u o", "G yy 5p u j o",
        "8G dd u dd u u u", "8G dd dd u", "x j . u",
    ]
    sequences = [_keys(r) + ["escape"] for r in repros]
    for seed in _FUZZ_SEEDS:
        rng = random.Random(seed)
        sequences.append([rng.choice(_FUZZ_KEYS) for _ in range(_FUZZ_LENGTH)])

    app = VimTGApp(deck_path=path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        scr = _strict(_screen(app))
        for i, keys in enumerate(sequences):
            for n, key in enumerate(keys):
                try:
                    scr._process_key(key)
                except Exception as exc:  # pragma: no cover - failure report
                    raise AssertionError(
                        f"sequence {i} crashed at key {n} ({key!r}): "
                        f"{''.join(keys[: n + 1])!r}"
                    ) from exc
                s = scr._state
                assert 0 <= s.cursor.row < max(1, s.buffer.line_count())
            # Reset between sequences: back to normal, undo all the way
            if scr._state.macros.is_recording:
                scr._process_key("q")
            scr._process_key("escape")
            scr._process_key("escape")
            for _ in range(400):
                if not scr._state.history.can_undo:
                    break
                scr._process_key("u")
