## What

<!-- One or two sentences on what this PR changes. -->

## Why

<!-- The problem, bug, or issue this addresses (link it: Fixes #123). -->

## Test evidence

<!-- New/updated tests, and what you ran. A regression test should fail
     before the change and pass after it. -->

- [ ] `uv run pytest` passes (coverage not lower)
- [ ] `uv run ruff check src/ tests/` is clean
- [ ] `uv run mypy --strict src/` is clean

## User-visible changes

<!-- Keys, commands, deck-file format, CLI output, or config that behave
     differently. "None" is a fine answer. -->

- [ ] README / `docs/` updated for any behaviour change
- [ ] `CHANGELOG.md` entry under **Unreleased**
