You are performing a cleanup pass on the vimtg project — a TUI-based MTG deck builder using Python 3.12+ and Textual.

Review ALL files that have been modified or created recently (check `git diff --name-only` and `git diff --cached --name-only`).

## Remove

1. **Tests that verify language/framework behavior** rather than business logic:
   - Testing that Python dataclasses are frozen (the `@dataclass(frozen=True)` decorator guarantees this)
   - Testing that type annotations work
   - Testing that SQLite connections can be opened
   - Testing that Textual widgets render (unless testing specific rendering logic)

2. **Over-defensive runtime checks** for things the type system guarantees:
   - `isinstance` checks on typed parameters
   - Redundant None checks after guaranteed initialization
   - Try/except around operations that can't fail

3. **Dead code and leftovers**:
   - Commented-out code
   - `print()` / `logging.debug()` statements used during development
   - Unused imports
   - Unused variables (prefix with `_` only if the assignment is required)
   - Empty `__init__.py` files that only contain comments

4. **Docstrings and comments that restate the obvious**:
   - `"""Initialize the class."""` on `__init__`
   - `# Increment counter` above `counter += 1`
   - Module-level docstrings that just restate the filename
   - Keep only comments that explain WHY, not WHAT

5. **Over-engineering**:
   - Abstract base classes with only one implementation
   - Factory functions that just call a constructor
   - Wrapper functions that add no logic
   - Generic type parameters used in only one place

## Keep

- All business logic tests (card parsing, deck operations, search, etc.)
- Error handling at system boundaries (file I/O, network, user input)
- Validation logic
- Type annotations on public APIs
- Comments explaining non-obvious design decisions

## Process

1. Review each changed file
2. Make targeted removals (don't rewrite working code)
3. Run `ruff check --fix src/ tests/` to clean up imports
4. Run `python -m pytest --tb=short -q` to verify nothing broke
5. If tests fail after cleanup, revert the specific change that caused it

Do NOT add new features, refactor working code, or change public APIs. This is strictly a cleanup pass.
