# SPDX-License-Identifier: GPL-3.0-or-later
"""The per-game view the UI edits: library cheats plus whatever is installed.

A cheat file on the card may hold cheats that are not in the matched libretro
entry, because it was hand-written, taken from another source, or matched to a
different file last time. Those are shown too, already ticked, so that saving a
selection can never quietly discard cheats the user put there.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import chtparse
import match
import prefs
import writer


@dataclass
class Entry:
    group: object            # chtparse.Group
    enabled: bool
    in_library: bool         # False = only present in the installed file

    @property
    def desc(self) -> str:
        return self.group.desc or "(no description)"

    @property
    def codes(self) -> str:
        return "+".join(c.raw for c in self.group.codes)

    @property
    def summary(self) -> str:
        return " ".join(f"{c.address:04X}={c.value:02X}" for c in self.group.codes)

    @property
    def placeholder(self) -> bool:
        """Nothing decoded: the libretro entry was a XX-style modifier."""
        return not self.group.codes

    @property
    def applied(self) -> str:
        """How the core makes this cheat take effect, for the whole group.

        The two mechanisms behave differently enough to be worth showing. A
        written cheat puts the value where the game finds it by any route; an
        overridden read only satisfies reads the core can see, so a DMA copy or
        a cached value misses it.
        """
        kinds = {chtparse.applied_by(c) for c in self.group.codes}
        if not kinds:
            return ""
        if kinds == {"poke"}:
            return "written"
        if kinds == {"patch"}:
            return "patched"
        return "mixed"


@dataclass
class GameView:
    game: object             # card.Game
    source: str | None       # cheat file the entries came from
    entries: list[Entry]
    alternates: list         # match.Candidate
    pinned: bool = False     # source came from a remembered choice, not matching

    @property
    def enabled(self) -> list[Entry]:
        return [e for e in self.entries if e.enabled]

    @property
    def applied_counts(self) -> tuple[int, int]:
        """(codes written into RAM, codes applied as a read override)."""
        written = patched = 0
        for e in self.enabled:
            for c in e.group.codes:
                if chtparse.applied_by(c) == "poke":
                    written += 1
                else:
                    patched += 1
        return written, patched

    @property
    def problems(self) -> list[str]:
        return writer.check([e.group for e in self.enabled])

    def save(self) -> tuple[int, int]:
        return writer.write(self.game.cht_path, [e.group for e in self.enabled])


def load(game, source: str | None = None) -> GameView:
    """Build the view for one game, honouring a pinned source if there is one."""
    alternates = match.rank(game.name, game.platform)
    pinned = False
    if source is None:
        source = prefs.get_source(game.path)
        if source and not os.path.exists(source):
            source = None
        pinned = source is not None
    if source is None:
        top = alternates[0] if alternates else None
        source = top.path if top and top.score >= 0.72 else None

    lib = writer.load_library(source) if source else []
    installed_groups = []
    if os.path.exists(game.cht_path):
        try:
            installed_groups = writer.load_library(game.cht_path)
        except Exception:                                    # noqa: BLE001
            installed_groups = []
    installed_keys = {writer.key_of(g) for g in installed_groups}

    entries = [Entry(g, writer.key_of(g) in installed_keys, True) for g in lib]
    lib_keys = {writer.key_of(g) for g in lib}
    # anything installed that the library file does not know about
    extra = [Entry(g, True, False) for g in installed_groups
             if writer.key_of(g) not in lib_keys]
    return GameView(game, source, extra + entries, alternates, pinned)


def pin(game, cht_path: str | None) -> None:
    prefs.set_source(game.path, cht_path)
