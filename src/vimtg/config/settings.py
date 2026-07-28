import tomllib
from dataclasses import dataclass, replace

from vimtg.config.paths import config_dir

VALID_PRICE_SOURCES = frozenset({"usd", "usd_foil", "eur", "eur_foil", "tix"})

VALID_FORMATS = frozenset({
    "", "standard", "pioneer", "modern", "legacy", "vintage",
    "commander", "pauper", "brawl", "historic",
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
    # VCS
    auto_snapshot: bool = True


def validate_settings(settings: Settings) -> list[str]:
    """Return list of validation errors (empty means valid)."""
    errors: list[str] = []
    if settings.price_source not in VALID_PRICE_SOURCES:
        errors.append(f"Invalid price_source: {settings.price_source}")
    if settings.search_limit < 1 or settings.search_limit > 500:
        errors.append(f"search_limit must be 1-500, got {settings.search_limit}")
    if settings.default_format not in VALID_FORMATS:
        errors.append(f"Invalid default_format: {settings.default_format}")
    return errors


def load_settings() -> Settings:
    """Load settings from config.toml, falling back to defaults.

    A malformed or invalid config must never prevent the app from
    starting — bad files fall back to defaults, invalid values are
    replaced per-field.
    """
    config_path = config_dir() / "config.toml"
    if not config_path.exists():
        return Settings()

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        return Settings()

    editor = data.get("editor", {})
    if not isinstance(editor, dict):
        return Settings()

    defaults = Settings()

    def _get(key: str, expected: type) -> object:
        value = editor.get(key, getattr(defaults, key))
        if expected is bool:
            return value if isinstance(value, bool) else getattr(defaults, key)
        if isinstance(value, expected) and not isinstance(value, bool):
            return value
        return getattr(defaults, key)

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
        auto_snapshot=_get("auto_snapshot", bool),  # type: ignore[arg-type]
    )

    # Replace out-of-range values with defaults, field by field
    replacements: dict[str, object] = {}
    if settings.price_source not in VALID_PRICE_SOURCES:
        replacements["price_source"] = defaults.price_source
    if settings.search_limit < 1 or settings.search_limit > 500:
        replacements["search_limit"] = defaults.search_limit
    if settings.default_format not in VALID_FORMATS:
        replacements["default_format"] = defaults.default_format
    if replacements:
        settings = replace(settings, **replacements)  # type: ignore[arg-type]
    return settings
