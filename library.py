"""Index of the libretro cheat database, restricted to the systems we support."""
from __future__ import annotations

import os
from functools import lru_cache

import card as card_mod

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "external", "libretro-database", "cht")


class MissingDatabase(Exception):
    pass


@lru_cache(maxsize=None)
def files_for(platform: str) -> tuple[str, ...]:
    """Cheat files for a Pocket platform id.

    Both Game Boy directories are searched for either platform: plenty of GBC
    releases are filed under Game Boy (and vice versa) because they are
    "GB Compatible", and the ROM on the card gives no hint which.
    """
    if not os.path.isdir(DB):
        raise MissingDatabase(
            f"{DB} not found. Run tools/cheats/init-db.sh to fetch it.")
    dirs = [card_mod.SUPPORTED[p] for p in ("gbc", "gb") if p in card_mod.SUPPORTED]
    # search this platform's own directory first, so an exact-name tie prefers it
    own = card_mod.SUPPORTED.get(platform)
    if own in dirs:
        dirs.remove(own)
        dirs.insert(0, own)
    out: list[str] = []
    for d in dirs:
        full = os.path.join(DB, d)
        if not os.path.isdir(full):
            continue
        for f in sorted(os.listdir(full)):
            if f.endswith(".cht"):
                out.append(os.path.join(full, f))
    return tuple(out)


def available() -> bool:
    return os.path.isdir(DB)
