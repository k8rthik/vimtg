import tomllib
from dataclasses import dataclass

from vimtg.config.paths import config_dir


@dataclass(frozen=True)
class Settings:
    theme: str = "dark"
    default_format: str = ""
    search_limit: int = 50
    auto_expand: bool = True


def load_settings() -> Settings:
    config_path = config_dir() / "config.toml"
    if not config_path.exists():
        return Settings()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    editor = data.get("editor", {})
    return Settings(
        theme=editor.get("theme", "dark"),
        default_format=editor.get("default_format", ""),
        search_limit=editor.get("search_limit", 50),
        auto_expand=editor.get("auto_expand", True),
    )
