"""Config option metadata and pure manipulation functions.

Defines the available settings, their types, valid values, and display names.
Used by both the :set command and the config screen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from vimtg.config.settings import Settings

_CURRENCY_SYMBOLS: dict[str, str] = {
    "usd": "$",
    "usd_foil": "$",
    "eur": "\u20ac",
    "eur_foil": "\u20ac",
    "tix": "tix ",
}


def currency_symbol_for(price_source: str) -> str:
    """Return the currency symbol for a given price source."""
    return _CURRENCY_SYMBOLS.get(price_source, "$")


@dataclass(frozen=True)
class ConfigOption:
    """Metadata for a single config setting."""

    key: str
    display_name: str
    description: str
    option_type: str  # "bool" | "choice" | "int"
    choices: tuple[str, ...] = ()
    min_val: int | None = None
    max_val: int | None = None
    group: str = ""


CONFIG_OPTIONS: tuple[ConfigOption, ...] = (
    # Pricing
    ConfigOption(
        "price_source", "Price Source", "Which Scryfall price to display",
        "choice", ("usd", "usd_foil", "eur", "eur_foil", "tix"), group="Pricing",
    ),
    ConfigOption(
        "show_prices", "Show Prices", "Display prices in card views",
        "bool", group="Pricing",
    ),
    # Display
    ConfigOption(
        "show_line_numbers", "Line Numbers", "Show relative line numbers",
        "bool", group="Display",
    ),
    ConfigOption(
        "show_which_key", "Which Key", "Show keybinding tooltips",
        "bool", group="Display",
    ),
    ConfigOption(
        "auto_expand", "Auto Expand", "Expand card details on cursor",
        "bool", group="Display",
    ),
    # Editor
    ConfigOption(
        "auto_sort", "Auto Sort", "Sort cards by type on insert",
        "bool", group="Editor",
    ),
    ConfigOption(
        "search_limit", "Search Limit", "Max search results",
        "int", min_val=10, max_val=500, group="Editor",
    ),
    ConfigOption(
        "default_format", "Default Format", "Filter by format legality",
        "choice", (
            "", "standard", "pioneer", "modern", "legacy",
            "vintage", "commander", "pauper",
        ),
        group="Editor",
    ),
    ConfigOption(
        "confirm_quit", "Confirm Quit", "Require :q! if modified",
        "bool", group="Editor",
    ),
    ConfigOption(
        "theme", "Theme", "Color theme",
        "choice", ("dark",), group="Display",
    ),
)

_OPTIONS_BY_KEY: dict[str, ConfigOption] = {o.key: o for o in CONFIG_OPTIONS}


def get_option(key: str) -> ConfigOption | None:
    """Look up a config option by key name."""
    return _OPTIONS_BY_KEY.get(key)


def get_setting_value(settings: Settings, key: str) -> str:
    """Get current value of a setting as a display string."""
    value = getattr(settings, key, None)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def get_setting_display(settings: Settings, key: str) -> str:
    """Get formatted display like 'Price Source: usd'."""
    opt = _OPTIONS_BY_KEY.get(key)
    if opt is None:
        return f"{key}: {getattr(settings, key, '?')}"
    value = get_setting_value(settings, key)
    label = value if value else "none"
    return f"{opt.display_name}: {label}"


def apply_setting(settings: Settings, key: str, value: str) -> Settings:
    """Return new Settings with one field changed. Raises ValueError on invalid."""
    opt = _OPTIONS_BY_KEY.get(key)
    if opt is None:
        raise ValueError(f"Unknown setting: {key}")

    if opt.option_type == "bool":
        if value.lower() in ("on", "true", "yes", "1"):
            return replace(settings, **{key: True})
        if value.lower() in ("off", "false", "no", "0"):
            return replace(settings, **{key: False})
        raise ValueError(f"{key} must be on/off, got: {value}")

    if opt.option_type == "choice":
        if value not in opt.choices:
            valid = ", ".join(opt.choices)
            raise ValueError(f"{key} must be one of: {valid}")
        return replace(settings, **{key: value})

    if opt.option_type == "int":
        try:
            int_val = int(value)
        except ValueError:
            raise ValueError(f"{key} must be an integer, got: {value}") from None
        if opt.min_val is not None and int_val < opt.min_val:
            raise ValueError(f"{key} minimum is {opt.min_val}")
        if opt.max_val is not None and int_val > opt.max_val:
            raise ValueError(f"{key} maximum is {opt.max_val}")
        return replace(settings, **{key: int_val})

    raise ValueError(f"Unknown option type: {opt.option_type}")


def cycle_setting(settings: Settings, key: str, direction: int = 1) -> Settings:
    """Cycle a setting to its next/prev valid value. For config screen navigation."""
    opt = _OPTIONS_BY_KEY.get(key)
    if opt is None:
        return settings

    if opt.option_type == "bool":
        current = getattr(settings, key)
        return replace(settings, **{key: not current})

    if opt.option_type == "choice" and opt.choices:
        current = str(getattr(settings, key))
        try:
            idx = opt.choices.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(opt.choices)
        return replace(settings, **{key: opt.choices[new_idx]})

    if opt.option_type == "int":
        current = getattr(settings, key)
        step = 10 * direction
        new_val = current + step
        if opt.min_val is not None:
            new_val = max(opt.min_val, new_val)
        if opt.max_val is not None:
            new_val = min(opt.max_val, new_val)
        return replace(settings, **{key: new_val})

    return settings


def groups() -> list[str]:
    """Return ordered list of unique group names."""
    seen: set[str] = set()
    result: list[str] = []
    for opt in CONFIG_OPTIONS:
        if opt.group not in seen:
            seen.add(opt.group)
            result.append(opt.group)
    return result


def options_for_group(group: str) -> list[ConfigOption]:
    """Return options belonging to a group, in definition order."""
    return [o for o in CONFIG_OPTIONS if o.group == group]


def navigable_options() -> list[ConfigOption]:
    """Return all options in display order (grouped)."""
    result: list[ConfigOption] = []
    for group in groups():
        result.extend(options_for_group(group))
    return result
