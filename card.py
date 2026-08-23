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
    # Absolute paths of the .cht files found beside those ROMs, from the same
    # directory walk. Asking the filesystem per game instead is one stat each,
    # and on a card over USB that is slow enough to freeze the window.
    cheat_files: frozenset[str] = frozenset()

    def has_cheats(self, game: "Game") -> bool:
        return game.cht_path in self.cheat_files


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
            games, chts = self.scan(pid)
            out.append(Platform(pid, self.platform_name(pid), games, chts))
        return out

    def platform_name(self, pid: str) -> str:
        path = os.path.join(self.root, "Platforms", f"{pid}.json")
        try:
            return json.load(open(path))["platform"]["name"]
        except Exception:                                    # noqa: BLE001
            return pid.upper()

    def scan(self, pid: str) -> tuple[list[Game], frozenset[str]]:
        """ROMs and the cheat files beside them, from one walk of the tree.

        Both come out of the same os.walk deliberately. The directory listing
        already names every file, so asking the filesystem again whether each
        ROM has a .cht costs one stat per game and tells us nothing new. On a
        card read over USB with a cold cache that is hundreds of blocking calls
        on the UI thread, which is exactly what it looks like: a dead window.
        """
        adir = os.path.join(self.root, "Assets", pid)
        found: list[Game] = []
        chts: set[str] = set()
        for dirpath, dirs, files in os.walk(adir):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in ROM_EXT:
                    found.append(Game(os.path.join(dirpath, f), pid))
                elif ext == ".cht":
                    chts.add(os.path.join(dirpath, f))
        found.sort(key=lambda g: g.name.lower())
        return found, frozenset(chts)

    def games(self, pid: str) -> list[Game]:
        return self.scan(pid)[0]

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
        # Timeout on purpose. This runs on the Tk thread, and findmnt can block
        # on an unresponsive mount; without it the whole window hangs with
        # nothing on screen to say why.
        out = subprocess.run(["findmnt", "-rn", "-o", "TARGET,LABEL"],
                             capture_output=True, text=True, check=True,
                             timeout=5).stdout
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
