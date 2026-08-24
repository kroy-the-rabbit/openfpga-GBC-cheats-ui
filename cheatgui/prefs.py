"""Remembered choices, kept off the SD card so it stays clean."""
from __future__ import annotations

import json
import os

CONFIG = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "pocket-cheats", "prefs.json")


def _load() -> dict:
    try:
        return json.load(open(CONFIG))
    except Exception:                                        # noqa: BLE001
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    tmp = CONFIG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CONFIG)


def get_source(rom_path: str) -> str | None:
    """The cheat file the user pinned for this ROM, if any."""
    return _load().get("sources", {}).get(os.path.basename(rom_path))


def set_source(rom_path: str, cht_path: str | None) -> None:
    data = _load()
    sources = data.setdefault("sources", {})
    key = os.path.basename(rom_path)
    if cht_path is None:
        sources.pop(key, None)
    else:
        sources[key] = cht_path
    _save(data)
