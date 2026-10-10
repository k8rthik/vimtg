# Contributing to vimtg

Thanks for helping! This guide covers the development setup, the checks CI
runs, and how the code is laid out. For security issues, follow
[SECURITY.md](SECURITY.md) instead of opening a public issue.

## Development setup

vimtg uses [uv](https://docs.astral.sh/uv/) and targets Python 3.12+.

```bash
git clone https://github.com/k8rthik/vimtg.git
cd vimtg
uv sync --extra dev          # creates .venv from uv.lock
uv run vimtg --version       # run the app from the checkout
```

(`pip install -e ".[dev]"` in a virtualenv also works.)

## Checks

Run these before opening a pull request; CI runs the same commands on Linux,
macOS, and Windows with Python 3.12, 3.13, and 3.14.

```bash
uv run pytest --cov=vimtg --cov-fail-under=92   # tests + coverage gate
uv run ruff check src/ tests/                   # lint
uv run mypy --strict src/                       # types
```

CI type-checks `src/` only, and nothing runs a formatter: `tests/` is
linted by ruff but is not type-checked, and no `ruff format` check runs.
Type hints in tests are welcome but not enforced; match the surrounding
style.

Notes on the test suite:

- **No network.** [pytest-socket](https://github.com/miketheman/pytest-socket)
  blocks every connection except loopback, and proxy variables are cleared,
  so a test that forgets to mock Scryfall, EDHREC, or a deck site fails
  instead of reaching the internet. Use the fixtures in `tests/fixtures/`
  (real Scryfall response shapes) or mock `httpx`.
- **Isolated user data.** An autouse fixture points the XDG directories at a
  temp dir and sets `VIMTG_NO_AUTOSYNC`, so no test touches your real config,
  card database, or cache. Use the `db_factory` fixture for databases.
- **`ResourceWarning` is an error**, to catch leaked SQLite connections.
- **Perf tests** (`tests/test_performance.py`, marker `perf`) assert generous
  time budgets. Scale them with `VIMTG_PERF_BUDGET_SCALE=5` on a slow
  machine, or skip them with `-m "not perf"`.
- TUI screens are tested headlessly through Textual's `run_test` pilot and
  the editor session; tests mirror the source tree under `tests/`.

CI also resolves every direct dependency to its declared minimum
(`uv sync --resolution lowest-direct`) and builds, `twine check`s, and
smoke-tests the wheel in a clean virtualenv. If you raise a dependency
floor, update `pyproject.toml` and run `uv lock`.

## Pull requests

- Keep each PR focused on one change, with tests. Bug fixes should include a
  regression test that fails before the fix and passes after it.
- Update the README or `docs/` for any user-visible behaviour change, and add
  a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
- vimtg follows vim conventions where they exist; when in doubt, do what vim
  (or MTG deckbuilding convention) does.

## Releases

The version lives only in `src/vimtg/__init__.py` (`__version__`);
`pyproject.toml` reads it from there. Releases are tagged `vX.Y.Z`, and the
tag must match `__version__`. `.github/workflows/release.yml` (PyPI trusted
publishing) runs the full CI workflow as a gate before it publishes; it is a
draft and stays inert until the maintainer enables it.

## Architecture

```
src/vimtg/
  domain/      Pure data and rules: Card, Deck, zones, sections, categories,
               tags, sideboard plans, formats, validation, diff, merge,
               analytics, probabilities, snapshot tree (frozen dataclasses, no I/O)
  editor/      Vim engine: buffer, cursor, modes, keymap, motions, operators,
               registers, marks, macros, dot repeat, layout, placement, lint,
               sort, splits, plans, config options, help text
    command_handlers/   One module per ex-command family
  data/        SQLite schema, FTS5 card repository, Scryfall sync, deck file
               parser/serializer, snapshot repository
  services/    Search, deck, import/export, deck-site URL importers, EDHREC,
               history, VCS, diff, clipboard
  config/      XDG paths, config.toml reader/writer, category history
  tui/         Textual layer: app, deck renderer, key translator, theme
    screens/   Main, greeter, help, history, merge, config
    widgets/   Deck view, search results, command line, status line, which-key,
               help panel, analytics, EDHREC, stats, diff, branches, snapshots,
               conflicts, scrolling math
```

The editor and domain layers never import Textual. The TUI translates key events into editor calls and renders the result.

## Tech stack

| | |
|:--|:--|
| **Python** | 3.12+, strict mypy |
| **TUI** | Textual + Rich |
| **CLI** | Click |
| **HTTP** | httpx |
| **Search** | SQLite FTS5 |
| **Cards** | Scryfall bulk data (offline) |
| **Theme** | Catppuccin Mocha |
| **Build** | Hatchling |
| **Tests** | pytest, pytest-cov, pytest-asyncio, pytest-socket |
| **Lint** | Ruff |
