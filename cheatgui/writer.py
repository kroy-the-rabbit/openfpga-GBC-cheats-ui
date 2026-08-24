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

import cheatfile
import chtparse   # tools/cheats, put on the path by __main__.py

# The Game Boy core's limits. A system whose core does not exist yet has none
# that anybody could check, so everything below asks cheatfile per platform
# rather than assuming these two.
MAX_CHEATS = chtparse.MAX_GROUPS
MAX_CODES = chtparse.MAX_CODES


def key_of(group) -> tuple:
    """Identity of a cheat, stable across files: its codes."""
    return tuple(c.raw for c in group.codes)


NO_LIMIT = cheatfile.NO_LIMIT


def load_library(cht_path: str, platform: str) -> list:
    return cheatfile.parse(open(cht_path, "rb").read(), platform)


def load_installed(game_cht: str, platform: str) -> set[tuple]:
    """Keys of the cheats currently installed for a game."""
    if not os.path.exists(game_cht):
        return set()
    try:
        return {key_of(g) for g in load_library(game_cht, platform)}
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


def check(groups: list, platform: str) -> list[str]:
    """Problems that would stop these cheats working, worst first.

    A system whose core does not exist yet has no limits to check against, so
    nothing is claimed. Making some up would put a number on screen that no
    hardware agrees with.
    """
    limits = cheatfile.limits(platform)
    if limits is None:
        return []
    max_cheats, max_codes = limits
    problems = []
    if len(groups) > max_cheats:
        problems.append(f"{len(groups)} cheats selected, the core reads {max_cheats}")
    codes = sum(len(g.codes) for g in groups)
    if codes > max_codes:
        problems.append(f"{codes} codes selected, the core stores {max_codes}")
    return problems


def write(game_cht: str, groups: list, platform: str) -> tuple[int, int, bool]:
    """Install a selection. Returns (cheats, codes, removed).

    `removed` says the file was deleted rather than written, which is what an
    empty selection means and is worth saying out loud.

    The written file is parsed back before this returns, so a bad write is
    caught here rather than on the handheld.
    """
    if not groups:
        # Removing the file *is* the right thing for an empty selection: the
        # file is the state, and no cheats means no file. It is still a
        # deletion, so it is backed up and the caller is told, because
        # "wrote 0 cheats" is not what happened.
        if os.path.exists(game_cht):
            backup(game_cht)
            os.remove(game_cht)
            return (0, 0, True)
        return (0, 0, False)

    text = render(groups)
    # A cartridge's file goes in its own folder, which will not exist yet.
    os.makedirs(os.path.dirname(game_cht), exist_ok=True)
    if os.path.exists(game_cht):
        backup(game_cht)
    tmp = game_cht + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, game_cht)

    back = load_library(game_cht, platform)
    want = [key_of(g) for g in groups]
    got = [key_of(g) for g in back]
    if got != want:
        raise IOError(f"{game_cht}: wrote {len(want)} cheats but read back {len(got)}")
    if not all(g.enabled for g in back):
        raise IOError(f"{game_cht}: some cheats did not read back as enabled")
    return (len(back), sum(len(g.codes) for g in back), False)


def backup(path: str) -> str:
    dst = path + ".bak"
    shutil.copyfile(path, dst)
    return dst
