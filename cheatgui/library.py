# SPDX-License-Identifier: GPL-3.0-or-later
"""Index of the libretro cheat database, restricted to the systems we support."""
from __future__ import annotations

import os
from functools import lru_cache

import card as card_mod
import db

# Your own cheat files. The libretro database is replaced wholesale by an
# update, so anything added there is lost the next time you press Update; this
# lives outside it and is searched first, so a file you wrote wins ties against
# the stock one of the same name. Name it after the ROM, exactly as the ROM is
# named, and it will match: the picker compares filenames.
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
def _files_for(platform: str, db_dir: str, generation: int) -> tuple[str, ...]:
    """Cheat files for a Pocket platform id.

    Both Game Boy directories are searched for either platform: plenty of GBC
    releases are filed under Game Boy (and vice versa) because they are
    "GB Compatible", and the ROM on the card gives no hint which.

    `generation` is not read. It is in the key so that refresh() can retire the
    cache after an update, which replaces the files in place and so leaves the
    path, and every other part of the key, exactly as it was.
    """
    if not os.path.isdir(db_dir):
        raise MissingDatabase(
            f"{db_dir} not found. Press Update to fetch the cheat database.")
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
        full = os.path.join(db_dir, d)
        if not os.path.isdir(full):
            continue
        for f in sorted(os.listdir(full)):
            if f.endswith(".cht"):
                out.append(os.path.join(full, f))
    return tuple(out)


_generation = 0


def files_for(platform: str) -> tuple[str, ...]:
    return _files_for(platform, db.db_dir(), _generation)


def refresh() -> None:
    """Forget the index. Call after an update, or after adding a file of yours."""
    global _generation
    _generation += 1


def available() -> bool:
    return db.available()
