"""Configuration management for ytdl."""

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "ytdl"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "download_dir": str(Path.home() / "Downloads" / "ytdl"),
    "output_template": "%(title)s [%(id)s].%(ext)s",
    "format": "bestvideo+bestaudio/best",
    "audio_format": "mp3",
    "audio_quality": 0,
    "subtitles": False,
    "subtitles_lang": "en",
    "thumbnails": False,
    "embed_metadata": True,
    "embed_thumbnail": False,
    "concurrent_fragments": 5,
    "retries": 10,
    "limit_rate": None,
    "proxy": None,
    "cookies_file": None,
    "shortcuts": {},
}


def ensure_config_dir() -> None:
    """Create config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load config from file, merging with defaults."""
    ensure_config_dir()
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                user_config = json.load(f)
            config.update(user_config)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load config: {e}")
    return config


def save_config(config: dict[str, Any]) -> None:
    """Save config to file."""
    ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def get_config_path() -> Path:
    """Return the path to the config file."""
    return CONFIG_FILE


def config_set(key: str, value: Any) -> dict[str, Any]:
    """Set a config value and save. Returns the updated config."""
    config = load_config()
    # Try to parse value as JSON for proper types
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            config[key] = parsed
        except (json.JSONDecodeError, TypeError):
            config[key] = value
    else:
        config[key] = value
    save_config(config)
    return config


def config_get(key: str) -> Any:
    """Get a specific config value."""
    config = load_config()
    return config.get(key)


def get_download_dir() -> Path:
    """Get the download directory, expanding ~."""
    config = load_config()
    return Path(config["download_dir"]).expanduser().resolve()
