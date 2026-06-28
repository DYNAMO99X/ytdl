"""Custom shortcut management for ytdl."""

from typing import Optional

from ytdl.config import load_config, save_config


BUILTIN_COMMANDS = {
    "download",
    "audio",
    "playlist",
    "info",
    "formats",
    "search",
    "batch",
    "config",
    "shortcut",
    "tui",
    "help",
}


def list_shortcuts() -> dict[str, str]:
    """Get all configured shortcuts."""
    config = load_config()
    return config.get("shortcuts", {})


def add_shortcut(name: str, flags: str) -> None:
    """Add a new shortcut. Raises ValueError if name conflicts with built-in commands."""
    name = name.strip().lower()
    if not name:
        raise ValueError("Shortcut name cannot be empty")

    if name in BUILTIN_COMMANDS:
        raise ValueError(
            f"'{name}' is a built-in command and cannot be used as a shortcut name"
        )

    config = load_config()
    shortcuts = config.setdefault("shortcuts", {})
    shortcuts[name] = flags
    save_config(config)


def remove_shortcut(name: str) -> bool:
    """Remove a shortcut. Returns True if removed, False if not found."""
    config = load_config()
    shortcuts = config.get("shortcuts", {})
    if name in shortcuts:
        del shortcuts[name]
        save_config(config)
        return True
    return False


def get_shortcut_flags(name: str) -> Optional[str]:
    """Get the flags for a named shortcut. Returns None if not found."""
    config = load_config()
    shortcuts = config.get("shortcuts", {})
    return shortcuts.get(name)


def get_shortcut_names() -> list[str]:
    """Get all shortcut names."""
    config = load_config()
    return list(config.get("shortcuts", {}).keys())
