You are building vimtg — a TUI-based Magic: The Gathering deck builder with vim-style editing. This is Phase 0: project scaffolding.

Your job: create a fully installable Python package skeleton with CI, tooling, and test infrastructure. Zero features — just the foundation.

## 1. pyproject.toml

Create `pyproject.toml` with:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vimtg"
version = "0.1.0"
description = "Vim-powered TUI Magic: The Gathering deck builder"
requires-python = ">=3.12"
license = "MIT"
dependencies = [
    "textual>=1.0.0",
    "click>=8.1",
    "httpx>=0.27",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
    "textual-dev>=1.0",
]

[project.scripts]
vimtg = "vimtg.cli:main"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "TCH"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.hatch.build.targets.wheel]
packages = ["src/vimtg"]
```

## 2. .gitignore

Standard Python gitignore: `__pycache__/`, `*.pyc`, `.mypy_cache/`, `dist/`, `*.egg-info/`, `.coverage`, `.pytest_cache/`, `*.db`, `.venv/`, `venv/`, `.dev-loop/`, `logs/`, `node_modules/`, `.env`

## 3. Package skeleton

Create these files with minimal content (empty `__init__.py` where noted):

```
src/vimtg/__init__.py          →  __version__ = "0.1.0"
src/vimtg/__main__.py          →  from vimtg.cli import main; main()
src/vimtg/cli.py               →  Click group with --version flag (see below)
src/vimtg/domain/__init__.py
src/vimtg/data/__init__.py
src/vimtg/services/__init__.py
src/vimtg/editor/__init__.py
src/vimtg/editor/command_handlers/__init__.py
src/vimtg/tui/__init__.py
src/vimtg/tui/screens/__init__.py
src/vimtg/tui/widgets/__init__.py
src/vimtg/config/__init__.py
```

The `cli.py` should be:
```python
import click
from vimtg import __version__

@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="vimtg")
@click.pass_context
def main(ctx: click.Context) -> None:
    """vimtg — Vim-powered MTG deck builder."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
```

## 4. Configuration system

`src/vimtg/config/paths.py`:
- `data_dir()` → `~/.local/share/vimtg` (XDG_DATA_HOME)
- `config_dir()` → `~/.config/vimtg` (XDG_CONFIG_HOME)
- `cache_dir()` → `~/.cache/vimtg` (XDG_CACHE_HOME)
- `db_path()` → `data_dir() / "cards.db"`
- Use `pathlib.Path`, respect XDG env vars, create dirs on access

`src/vimtg/config/settings.py`:
- Frozen dataclass `Settings` with defaults: `theme = "dark"`, `default_format = ""`, `search_limit = 50`, `auto_expand = True`
- `load_settings()` reads from `config_dir() / "config.toml"`, falls back to defaults

## 5. CI workflow

Create `.github/workflows/ci.yml`:
- Trigger: push to any branch, PR to main
- Matrix: Python 3.12, 3.13
- Steps: checkout, setup-python, `pip install -e ".[dev]"`, `ruff check src/ tests/`, `mypy src/`, `pytest --cov=vimtg --cov-report=term-missing`

## 6. Test infrastructure

```
tests/__init__.py
tests/conftest.py
tests/domain/__init__.py
tests/data/__init__.py
tests/services/__init__.py
tests/editor/__init__.py
tests/editor/command_handlers/__init__.py
tests/tui/__init__.py
tests/fixtures/sample_burn.deck
tests/fixtures/scryfall_sample.json
```

`tests/conftest.py` should have:
- `tmp_db` fixture: returns a temp SQLite database path (cleaned up after test)
- `sample_deck_path` fixture: returns path to `tests/fixtures/sample_burn.deck`
- `scryfall_sample_path` fixture: returns path to `tests/fixtures/scryfall_sample.json`
- `sample_deck_text` fixture: returns the raw text content of the sample deck

`tests/fixtures/sample_burn.deck`:
```
// Deck: Burn
// Format: modern
// Author: test

// Creatures
4 Goblin Guide
4 Monastery Swiftspear
4 Eidolon of the Great Revel

// Spells
4 Lightning Bolt
4 Lava Spike
4 Rift Bolt
4 Searing Blaze
4 Skullcrack

// Lands
4 Inspiring Vantage
4 Sacred Foundry
2 Fiery Islet
8 Mountain

// Sideboard
SB: 2 Rest in Peace
SB: 3 Kor Firewalker
SB: 2 Smash to Smithereens
SB: 2 Path to Exile
SB: 2 Deflecting Palm
SB: 2 Roiling Vortex
SB: 2 Sanctifier en-Vec
```

`tests/fixtures/scryfall_sample.json` — a JSON array of 10 card objects. Include variety:
- Normal creature: Goblin Guide
- Instant: Lightning Bolt
- Sorcery: Lava Spike
- Enchantment creature: Eidolon of the Great Revel
- Land: Sacred Foundry (with two-color identity)
- Transform card (double-faced): Delver of Secrets // Insectile Aberration
- Split card: Fire // Ice
- Adventure card: Bonecrusher Giant // Stomp
- Card with no price: any common
- Card with special characters: Jötun Grunt

Use realistic Scryfall JSON structure. Each card needs at minimum: `id`, `oracle_id`, `name`, `mana_cost`, `cmc`, `type_line`, `oracle_text`, `colors`, `color_identity`, `set`, `rarity`, `prices` (with `usd`), `legalities` (with at least `standard` and `modern`), `layout`, `image_uris`. For the transform card, use `card_faces` array instead of top-level oracle_text/mana_cost.

Write a basic smoke test `tests/test_smoke.py`:
```python
def test_version():
    from vimtg import __version__
    assert __version__ == "0.1.0"

def test_cli_help(tmp_path):
    from click.testing import CliRunner
    from vimtg.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
```

## Verification

After creating all files:
1. Run `pip install -e ".[dev]"` — must succeed
2. Run `vimtg --version` — must print "vimtg, version 0.1.0"
3. Run `ruff check src/ tests/` — must pass
4. Run `pytest --tb=short -q` — must pass
5. Verify the directory structure matches the plan

## IMPORTANT

- Use frozen dataclasses everywhere (immutable data)
- All files under 200 lines
- No placeholder "TODO" comments — if something isn't built yet, just don't include it
- No docstrings that restate the obvious
- The __init__.py files for subpackages should be empty (no imports, no comments)
