# SPDX-License-Identifier: GPL-3.0-or-later
"""Match a ROM filename to its entry in the libretro cheat database.

Names differ in region tags, revision markers and punctuation, so compare a
normalized form and rank by similarity. The caller can always override, and an
override is remembered (see prefs.py).
"""
from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass

import library

# Tags that say nothing about which game this is.
_PAREN = re.compile(r"\([^)]*\)|\[[^]]*\]")
_JUNK = re.compile(r"[^a-z0-9]+")


def _stem(name: str) -> str:
    name = os.path.splitext(os.path.basename(name))[0]
    if name.endswith(".gb") or name.endswith(".gbc"):        # "x.gbc.cht" stems
        name = os.path.splitext(name)[0]
    return name


def normalize(name: str) -> str:
    """Title only: region and dump tags removed."""
    return " ".join(_JUNK.sub(" ", _PAREN.sub(" ", _stem(name)).lower()).split())


def normalize_full(name: str) -> str:
    """Title plus the tags, so variants of one game can be told apart."""
    return " ".join(_JUNK.sub(" ", _stem(name).lower()).split())


@dataclass
class Candidate:
    score: float          # similarity of the titles alone
    detail: float         # similarity including region and variant tags
    path: str

    @property
    def local(self) -> bool:
        """One of yours, rather than from the libretro database."""
        return library.is_local(self.path)

    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0]


def rank(rom_name: str, platform: str, limit: int = 8) -> list[Candidate]:
    """Best cheat files for a ROM, most likely first.

    Titles alone decide the primary score, because that is what identifies the
    game. Dozens of files then tie at 1.0 for a popular title (a Game Genie set,
    a GameShark set, one per region), so the tags break the tie: a ROM tagged
    "(USA, Australia)" should land on the cheat file with the same tags rather
    than on whichever name happens to be shortest.
    """
    target = normalize(rom_name)
    target_full = normalize_full(rom_name)
    scored: list[Candidate] = []
    for p in library.files_for(platform):
        cand = normalize(p)
        score = difflib.SequenceMatcher(None, target, cand).ratio()
        if cand == target:
            score = 1.0
        elif cand.startswith(target) or target.startswith(cand):
            score = max(score, 0.95)
        detail = difflib.SequenceMatcher(None, target_full, normalize_full(p)).ratio()
        scored.append(Candidate(score, detail, p))
    # Yours wins an otherwise exact tie: if you wrote a file for this ROM, that
    # is the one you meant, whatever the database also happens to have.
    scored.sort(key=lambda c: (-c.score, -c.detail, not c.local, len(c.name)))
    return scored[:limit]


def best(rom_name: str, platform: str, threshold: float = 0.72) -> Candidate | None:
    top = rank(rom_name, platform, limit=1)
    if top and top[0].score >= threshold:
        return top[0]
    return None
