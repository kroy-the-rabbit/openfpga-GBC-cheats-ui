"""Find and read an Analogue Pocket SD card.

The Pocket's layout is fixed: platforms live under /Assets/<platform id>/, cores
under /Cores/, and each platform's display name comes from
/Platforms/<platform id>.json. Nothing here writes; see writer.py for that.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

# Only these two have a core that understands cheat files. Everything else on a
# Pocket card ignores them, so the tool does not offer to write any.
SUPPORTED = {
    "gb":  "Nintendo - Game Boy",
    "gbc": "Nintendo - Game Boy Color",
}
ROM_EXT = {".gb", ".gbc"}

# Folders skipped when listing games. Romhacks are usually pre-patched variants
# of a ROM that is already in the list, and they do not match anything in the
# cheat database, so they only add noise. Nothing is hidden from the card, only
# from this tool.
SKIP_DIRS = {"romhacks"}


@dataclass
class Game:
    path: str                 # absolute path to the ROM
    platform: str             # Pocket platform id, e.g. "gbc"

    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0]

    @property
    def cht_path(self) -> str:
        """Where APF looks for this ROM's cheat file.

        A data slot whose filename is cloned from slot 0 gets this slot's
        extension *appended*, so it is "<rom filename>.cht", not the ROM name
        with its extension swapped.
        """
        return self.path + ".cht"

    @property
    def subdir(self) -> str:
        """Folder below the platform's asset root, for display ("" at the top)."""
        root = os.path.join(os.path.dirname(self.path))
        return root


@dataclass
class Platform:
    id: str
    name: str
    games: list[Game] = field(default_factory=list)


@dataclass
class Card:
    root: str
    label: str = ""

    def platforms(self) -> list[Platform]:
        out = []
        for pid in sorted(SUPPORTED):
            adir = os.path.join(self.root, "Assets", pid)
            if not os.path.isdir(adir):
                continue
            out.append(Platform(pid, self.platform_name(pid), self.games(pid)))
        return out

    def platform_name(self, pid: str) -> str:
        path = os.path.join(self.root, "Platforms", f"{pid}.json")
        try:
            return json.load(open(path))["platform"]["name"]
        except Exception:                                    # noqa: BLE001
            return pid.upper()

    def games(self, pid: str) -> list[Game]:
        adir = os.path.join(self.root, "Assets", pid)
        found: list[Game] = []
        for dirpath, dirs, files in os.walk(adir):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
            for f in files:
                if os.path.splitext(f)[1].lower() in ROM_EXT:
                    found.append(Game(os.path.join(dirpath, f), pid))
        found.sort(key=lambda g: g.name.lower())
        return found

    def sync(self) -> None:
        subprocess.run(["sync"], check=False)


def looks_like_card(path: str) -> bool:
    """A Pocket card always has both of these; a muOS or plain ROM card does not."""
    return all(os.path.isdir(os.path.join(path, d)) for d in ("Cores", "Platforms"))


def find_cards() -> list[Card]:
    """Mounted removable volumes that look like a Pocket card.

    POCKET_CARD overrides the search with an explicit path, for a card that
    mounts somewhere unusual and for testing against a fixture tree.
    """
    cards = []
    forced = os.environ.get("POCKET_CARD")
    if forced:
        return [Card(forced, "POCKET_CARD")] if looks_like_card(forced) else []
    try:
        out = subprocess.run(["findmnt", "-rn", "-o", "TARGET,LABEL"],
                             capture_output=True, text=True, check=True).stdout
    except Exception:                                        # noqa: BLE001
        return cards
    for line in out.splitlines():
        parts = line.split(" ", 1)
        target = parts[0]
        label = parts[1].strip() if len(parts) > 1 else ""
        if not (target.startswith("/run/media/") or target.startswith("/media/")
                or target.startswith("/mnt/")):
            continue
        if looks_like_card(target):
            cards.append(Card(target, label))
    return cards
