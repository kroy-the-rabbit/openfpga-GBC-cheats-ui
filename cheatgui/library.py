# SPDX-License-Identifier: GPL-3.0-or-later
"""Index of the libretro cheat database, restricted to the systems we support."""
from __future__ import annotations

import os
from functools import lru_cache

import card as card_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# POCKET_CHEAT_DB points this at an existing checkout, so a copy of the core
# repo alongside can share its submodule instead of cloning a second one.
DB = os.environ.get("POCKET_CHEAT_DB") or os.path.join(
    ROOT, "external", "libretro-database", "cht")

# Your own cheat files. The libretro database is a git submodule, so anything
# added there is lost on the next update and dirties the checkout meanwhile;
# this lives outside the repo and is searched first, so a file you wrote wins
# ties against the stock one of the same name. Name it after the ROM, exactly
# as the ROM is named, and it will match: the picker compares filenames.
LOCAL = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "pocket-cheats", "cht")


def local_dir() -> str:
    os.makedirs(LOCAL, exist_ok=True)
    return LOCAL


def is_local(path: str) -> bool:
    return os.path.abspath(path).startswith(os.path.abspath(LOCAL))


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
    # yours first: an exact-name tie should land on the file you wrote
    if os.path.isdir(LOCAL):
        for dirpath, _sub, files in os.walk(LOCAL):
            for f in sorted(files):
                if f.endswith(".cht"):
                    out.append(os.path.join(dirpath, f))
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
