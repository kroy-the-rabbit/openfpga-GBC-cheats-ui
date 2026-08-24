# SPDX-License-Identifier: GPL-3.0-or-later
"""Cartridges you own, and the cheat file each one uses.

A cartridge is not a file on the card, so it never appears in the game list,
and in Play Cartridge mode the Pocket does not auto-load a cheat file named
after it either. You browse for one from the core menu instead, and the slot
remembers it. So the useful thing this can do is put a file where you can find
it, under a name you will recognise, and remember which cheats you chose.

The list lives in the same config directory as the other remembered choices,
outside the repo, so nothing here is lost when the checkout changes.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import prefs

LIST = os.path.join(os.path.dirname(prefs.CONFIG), "cartridges.json")

# Where the files go on the card. Its own folder so the core's file browser
# opens on your cartridges rather than on a few hundred ROMs.
CARD_DIR = "Cartridges"


@dataclass
class Cartridge:
    """Quacks like card.Game, so the rest of the app treats it as one."""
    name: str
    platform: str
    card_root: str = ""

    @property
    def path(self) -> str:
        """Identity for the remembered-source table. Not a real file."""
        return f"cart:{self.platform}:{self.name}"

    @property
    def cht_path(self) -> str:
        return os.path.join(self.card_root, "Assets", self.platform, "common",
                            CARD_DIR, self.name + ".cht")

    @property
    def subdir(self) -> str:
        return os.path.dirname(self.cht_path)


def _load() -> list[dict]:
    try:
        data = json.load(open(LIST))
        return data.get("cartridges", [])
    except Exception:                                        # noqa: BLE001
        return []


def _save(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(LIST), exist_ok=True)
    tmp = LIST + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"cartridges": rows}, f, indent=2)
    os.replace(tmp, LIST)


def all(card_root: str = "") -> list[Cartridge]:
    return [Cartridge(r["name"], r.get("platform", "gbc"), card_root)
            for r in sorted(_load(), key=lambda r: r["name"].lower())]


def add(name: str, platform: str = "gbc") -> bool:
    """False if that name is already listed."""
    name = name.strip()
    if not name:
        return False
    rows = _load()
    if any(r["name"].lower() == name.lower() for r in rows):
        return False
    rows.append({"name": name, "platform": platform})
    _save(rows)
    return True


def remove(name: str) -> bool:
    """Drop a cartridge from the list. False if it was not listed.

    Matched the way add() rejects duplicates, case insensitively, so the two
    cannot disagree about whether a name is already there.
    """
    rows = _load()
    keep = [r for r in rows if r["name"].lower() != name.lower()]
    if len(keep) == len(rows):
        return False
    _save(keep)
    prefs.set_source(f"cart:gbc:{name}", None)
    prefs.set_source(f"cart:gb:{name}", None)
    return True
