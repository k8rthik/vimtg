import tomllib
from dataclasses import dataclass

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
    config_path = config_dir() / "config.toml"
    if not config_path.exists():
        return Settings()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    editor = data.get("editor", {})
    return Settings(
        theme=editor.get("theme", "dark"),
        show_line_numbers=editor.get("show_line_numbers", True),
        show_which_key=editor.get("show_which_key", True),
        auto_expand=editor.get("auto_expand", True),
        price_source=editor.get("price_source", "usd"),
        show_prices=editor.get("show_prices", True),
        search_limit=editor.get("search_limit", 50),
        default_format=editor.get("default_format", ""),
        auto_sort=editor.get("auto_sort", True),
        confirm_quit=editor.get("confirm_quit", True),
    )
