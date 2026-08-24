# SPDX-License-Identifier: GPL-3.0-or-later
"""Read and write the cheat file that sits next to a ROM.

The file on the card *is* the state: it holds exactly the cheats the user chose,
each marked enabled. Nothing else is stored, so what the tool shows and what the
Pocket does cannot drift apart.

Only the chosen cheats are written. The core reads the first 32 cheats in a file
regardless of their enable flag, so handing it a 100-cheat libretro file would
truncate before reaching the one you wanted.
"""
from __future__ import annotations

import os
import shutil

import chtparse   # tools/cheats, put on the path by __main__.py

MAX_CHEATS = chtparse.MAX_GROUPS
MAX_CODES = chtparse.MAX_CODES


def key_of(group) -> tuple:
    """Identity of a cheat, stable across files: its codes."""
    return tuple(c.raw for c in group.codes)


# Reading a file to choose from is not the same as reading it to run. The core
# takes the first 32 codes; a libretro file often holds hundreds, and truncating
# here made everything past the first couple of dozen invisible and unpickable.
# check() still refuses a selection the core cannot hold.
NO_LIMIT = 1 << 30


def load_library(cht_path: str) -> list:
    return chtparse.parse(open(cht_path, "rb").read(),
                          max_codes=NO_LIMIT, max_groups=NO_LIMIT)


def load_installed(game_cht: str) -> set[tuple]:
    """Keys of the cheats currently installed for a game."""
    if not os.path.exists(game_cht):
        return set()
    try:
        return {key_of(g) for g in chtparse.parse(open(game_cht, "rb").read(),
                                                  max_codes=NO_LIMIT,
                                                  max_groups=NO_LIMIT)}
    except Exception:                                        # noqa: BLE001
        return set()


def render(groups: list) -> str:
    lines = [f"cheats = {len(groups)}", ""]
    for i, g in enumerate(groups):
        desc = (g.desc or f"Cheat {i + 1}").replace('"', "'")
        lines += [f'cheat{i}_desc = "{desc}"',
                  f'cheat{i}_code = "{"+".join(c.raw for c in g.codes)}"',
                  f"cheat{i}_enable = true", ""]
    return "\n".join(lines)


def check(groups: list) -> list[str]:
    """Problems that would stop these cheats working, worst first."""
    problems = []
    if len(groups) > MAX_CHEATS:
        problems.append(f"{len(groups)} cheats selected, the core reads {MAX_CHEATS}")
    codes = sum(len(g.codes) for g in groups)
    if codes > MAX_CODES:
        problems.append(f"{codes} codes selected, the core stores {MAX_CODES}")
    return problems


def write(game_cht: str, groups: list) -> tuple[int, int]:
    """Install a selection. Returns (cheats, codes) as the core will see them.

    The written file is parsed back before this returns, so a bad write is
    caught here rather than on the handheld.
    """
    if not groups:
        if os.path.exists(game_cht):
            backup(game_cht)
            os.remove(game_cht)
        return (0, 0)

    text = render(groups)
    # A cartridge's file goes in its own folder, which will not exist yet.
    os.makedirs(os.path.dirname(game_cht), exist_ok=True)
    if os.path.exists(game_cht):
        backup(game_cht)
    tmp = game_cht + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, game_cht)

    back = chtparse.parse(open(game_cht, "rb").read())
    want = [key_of(g) for g in groups]
    got = [key_of(g) for g in back]
    if got != want:
        raise IOError(f"{game_cht}: wrote {len(want)} cheats but read back {len(got)}")
    if not all(g.enabled for g in back):
        raise IOError(f"{game_cht}: some cheats did not read back as enabled")
    return (len(back), sum(len(g.codes) for g in back))


def backup(path: str) -> str:
    dst = path + ".bak"
    shutil.copyfile(path, dst)
    return dst
