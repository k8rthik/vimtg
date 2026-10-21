import tomllib
from dataclasses import dataclass, replace

from vimtg.config.paths import config_dir

VALID_PRICE_SOURCES = frozenset({"usd", "usd_foil", "eur", "eur_foil", "tix"})

VALID_FORMATS = frozenset({
    "", "standard", "pioneer", "modern", "legacy", "vintage",
    "commander", "pauper", "brawl", "historic", "timeless", "premodern",
    "penny", "standardbrawl", "oathbreaker", "paupercommander", "duel",
    "explorer", "alchemy", "gladiator",
})

# Default in-group ordering for :sort and layout regrouping. Mirrors
# editor.sort_keys.SORT_FIELDS (kept literal here so config stays
# import-light and dependency-free).
VALID_SORT_ORDERS = frozenset({
    "name", "qty", "cmc", "type", "color", "tag", "category",
    "power", "toughness", "rarity", "price",
})


@dataclass(frozen=True)
class Settings:
    # Display
    theme: str = "dark"
    show_line_numbers: bool = True
    show_which_key: bool = True
    auto_expand: bool = True
    # Pricing
    price_source: str = "usd"
    show_prices: bool = True
    # Search
    search_limit: int = 50
    default_format: str = ""
    # Editor
    auto_sort: bool = True
    confirm_quit: bool = True
    sort_order: str = "cmc"
    # VCS
    auto_snapshot: bool = True
    # Sync
    auto_sync_cards: bool = True


def validate_settings(settings: Settings) -> list[str]:
    """Return list of validation errors (empty means valid)."""
    errors: list[str] = []
    if settings.price_source not in VALID_PRICE_SOURCES:
        errors.append(f"Invalid price_source: {settings.price_source}")
    if settings.search_limit < 1 or settings.search_limit > 500:
        errors.append(f"search_limit must be 1-500, got {settings.search_limit}")
    if settings.default_format not in VALID_FORMATS:
        errors.append(f"Invalid default_format: {settings.default_format}")
    if settings.sort_order not in VALID_SORT_ORDERS:
        errors.append(f"Invalid sort_order: {settings.sort_order}")
    return errors


def load_settings() -> Settings:
    """Load settings from config.toml, falling back to defaults."""
    return load_settings_checked()[0]


def load_settings_checked() -> tuple[Settings, str | None]:
    """Load settings plus a warning when config.toml could not be read.

    A malformed or invalid config must never prevent the app from
    starting — bad files fall back to defaults, invalid values are
    replaced per-field — but an unparseable file must not go unnoticed
    either: the warning tells the user why their settings vanished.
    """
    try:
        config_path = config_dir() / "config.toml"
    except OSError as exc:  # e.g. $XDG_CONFIG_HOME/vimtg is a file
        return Settings(), f"Cannot use the config directory: {exc}; using default settings"
    if not config_path.exists():
        return Settings(), None

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return Settings(), (
            f"{config_path} is not valid TOML ({exc}); using default settings"
        )
    except OSError as exc:
        return Settings(), f"Cannot read {config_path}: {exc}; using default settings"

    editor = data.get("editor", {})
    if not isinstance(editor, dict):
        return Settings(), f"{config_path}: [editor] is not a table; using default settings"

    defaults = Settings()
    problems: list[str] = []

    def _get(key: str, expected: type) -> object:
        default = getattr(defaults, key)
        if key not in editor:
            return default
        value = editor[key]
        if isinstance(value, expected) and (expected is bool or not isinstance(value, bool)):
            return value
        problems.append(f"{key} must be {_TYPE_NAMES[expected]}")
        return default

    settings = Settings(
        theme=_get("theme", str),  # type: ignore[arg-type]
        show_line_numbers=_get("show_line_numbers", bool),  # type: ignore[arg-type]
        show_which_key=_get("show_which_key", bool),  # type: ignore[arg-type]
        auto_expand=_get("auto_expand", bool),  # type: ignore[arg-type]
        price_source=_get("price_source", str),  # type: ignore[arg-type]
        show_prices=_get("show_prices", bool),  # type: ignore[arg-type]
        search_limit=_get("search_limit", int),  # type: ignore[arg-type]
        default_format=_get("default_format", str),  # type: ignore[arg-type]
        auto_sort=_get("auto_sort", bool),  # type: ignore[arg-type]
        confirm_quit=_get("confirm_quit", bool),  # type: ignore[arg-type]
        sort_order=_get("sort_order", str),  # type: ignore[arg-type]
        auto_snapshot=_get("auto_snapshot", bool),  # type: ignore[arg-type]
        auto_sync_cards=_get("auto_sync_cards", bool),  # type: ignore[arg-type]
    )

    # Replace out-of-range values with defaults, field by field
    replacements: dict[str, object] = {}
    if settings.price_source not in VALID_PRICE_SOURCES:
        replacements["price_source"] = defaults.price_source
    if settings.search_limit < 1 or settings.search_limit > 500:
        replacements["search_limit"] = defaults.search_limit
    if settings.default_format not in VALID_FORMATS:
        replacements["default_format"] = defaults.default_format
    if settings.sort_order not in VALID_SORT_ORDERS:
        replacements["sort_order"] = defaults.sort_order
    for key in replacements:
        problems.append(f"{key} = {getattr(settings, key)!r} is not valid")
    if replacements:
        settings = replace(settings, **replacements)  # type: ignore[arg-type]

    problems.extend(keybinding_problems(data.get("keybindings")))
    if problems:
        return settings, (
            f"{config_path}: " + "; ".join(problems) + " (using defaults for these)"
        )
    return settings, None


_TYPE_NAMES: dict[type, str] = {bool: "true or false", int: "a number", str: "a string"}

# Mode tables allowed under [keybindings] (see editor.keymaps)
KEYBINDING_MODES = ("normal", "insert", "visual", "command")


def keybinding_problems(bindings: object) -> list[str]:
    """What is wrong with a [keybindings] table, entry by entry.

    The remapper skips exactly these entries; reporting them here lets
    startup say so instead of silently dropping a mapping.
    """
    if bindings is None:
        return []
    if not isinstance(bindings, dict):
        return ["[keybindings] must be a table"]
    problems: list[str] = []
    for key, value in bindings.items():
        if key in KEYBINDING_MODES:
            if not isinstance(value, dict):
                problems.append(f"[keybindings.{key}] must be a table")
                continue
            problems.extend(
                f"keybindings.{key}.{k} must be a string"
                for k, v in value.items() if not isinstance(v, str)
            )
        elif not isinstance(value, str):
            problems.append(f"keybindings.{key} must be a string")
    return problems
