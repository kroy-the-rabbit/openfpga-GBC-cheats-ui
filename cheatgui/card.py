# SPDX-License-Identifier: GPL-3.0-or-later
"""Find and read an Analogue Pocket SD card.

The Pocket's layout is fixed: platforms live under /Assets/<platform id>/, cores
under /Cores/, and each platform's display name comes from
/Platforms/<platform id>.json. Nothing here writes; see writer.py for that.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field

# Pocket platform id -> the libretro cheat database directory for it. Only
# these have a core that reads cheat files, so the tool does not offer to write
# any for anything else on the card.
#
# The Game Boy Advance core does not read them yet. It is here so that the
# cartridges and cheat files can be prepared now and be in place when it does;
# see cheatfile.py for why its codes are carried rather than read.
SUPPORTED = {
    "gb":  "Nintendo - Game Boy",
    "gbc": "Nintendo - Game Boy Color",
    "gba": "Nintendo - Game Boy Advance",
}
ROM_EXT = {".gb", ".gbc", ".gba"}

# What to call each system before the card has been asked. The card carries
# its own names in /Platforms/<id>.json, and reading those three small files
# cost 2.6 seconds on a cold card, in front of an empty window, to arrive at
# the names below. So these are used immediately and the card's own are read
# afterwards, in the background, in case it disagrees.
DISPLAY = {
    "gb":  "Game Boy",
    "gbc": "Game Boy Color",
    "gba": "Game Boy Advance",
}

# Folders skipped when listing games. Romhacks are usually pre-patched variants
# of a ROM that is already in the list, and they do not match anything in the
# cheat database, so they only add noise. Nothing is hidden from the card, only
# from this tool.
SKIP_DIRS = {"romhacks"}


class EjectError(Exception):
    """The card could not be unmounted; the message says why."""


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
    # False until something has actually walked this system's directory. An
    # unscanned platform is not an empty one, and the difference matters:
    # empty means "no ROMs", unscanned means "nobody has looked yet".
    scanned: bool = False

    def has_cheats(self, game: "Game") -> bool:
        return game.cht_path in self.cheat_files


@dataclass
class Card:
    root: str
    label: str = ""

    def platforms(self) -> list[Platform]:
        """Which systems are on the card. Deliberately does not read them.

        Walking all three took 27 seconds on a real card that had just been
        mounted, and the window sat empty and unusable for every one of them.
        The tree is only a few hundred files; it is exFAT over USB with a cold
        cache, where each one costs tens of milliseconds however few of them
        there are.

        So this answers the cheap question, which systems exist, and the
        expensive one is asked per system by fill() when somebody actually
        looks at it. You then wait for the system you picked rather than for
        all of them, and only the first time.
        """
        out = []
        for pid in sorted(SUPPORTED):
            adir = os.path.join(self.root, "Assets", pid)
            if not os.path.isdir(adir):
                continue
            out.append(Platform(pid, DISPLAY.get(pid, pid.upper())))
        return out

    def fill(self, plat: Platform) -> Platform:
        """Read one system's ROMs and cheat files. Slow on a cold card.

        Never call this on the Tk thread. It is the same object back, so the
        caller can hand it straight to whatever draws it.
        """
        if not plat.scanned:
            # The card's own name for the system, now that we are reading it
            # anyway and not holding up the window.
            plat.name = self.platform_name(plat.id)
            plat.games, plat.cheat_files = self.scan(plat.id)
            plat.scanned = True
        return plat

    def platform_name(self, pid: str) -> str:
        """What this card calls a system. Reads a file, so not on first paint."""
        path = os.path.join(self.root, "Platforms", f"{pid}.json")
        try:
            with open(path) as f:
                return json.load(f)["platform"]["name"]
        except Exception:                                    # noqa: BLE001
            return DISPLAY.get(pid, pid.upper())

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
        """Push writes out of the page cache. Windows does this on close."""
        if os.name != "nt":
            subprocess.run(["sync"], check=False)

    def device(self) -> str | None:
        """The block device this card is mounted from, on Linux."""
        try:
            out = subprocess.run(
                ["findmnt", "-rn", "-o", "SOURCE", "--target", self.root],
                capture_output=True, text=True, timeout=5, check=True).stdout
        except Exception:                                    # noqa: BLE001
            return None
        return out.strip().splitlines()[0] if out.strip() else None

    def unmount(self) -> str:
        """Flush writes and unmount the card. Returns what to tell the user.

        Raises EjectError with the tool's own message if it could not be done,
        which is usually a file still open on the card, and that message names
        the process. Nothing here forces anything: a card yanked mid-write is
        the failure this whole tool exists to avoid.
        """
        self.sync()

        if sys.platform == "darwin":
            attempts = [["diskutil", "unmount", self.root]]
        elif os.name == "nt":
            drive = os.path.splitdrive(os.path.abspath(self.root))[0]
            if not drive:
                raise EjectError(f"{self.root} is not on a drive letter")
            # The shell's own Eject verb, the same one Explorer uses. There is
            # no supported command line equivalent.
            attempts = [["powershell", "-NoProfile", "-Command",
                         "$sh = New-Object -comObject Shell.Application; "
                         f"$sh.Namespace(17).ParseName('{drive}')"
                         ".InvokeVerb('Eject')"]]
        else:
            # udisks first: it is what the desktop uses, needs no privilege for
            # removable media, and powers down the reader afterwards. Plain
            # umount is the fallback for a card mounted by hand or in fstab.
            dev = self.device()
            attempts = []
            if dev:
                attempts.append(["udisksctl", "unmount", "-b", dev])
            attempts.append(["umount", self.root])

        problems = []
        for cmd in attempts:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=30)
            except FileNotFoundError:
                problems.append(f"{cmd[0]}: not installed")
                continue
            except subprocess.TimeoutExpired:
                problems.append(f"{cmd[0]}: timed out")
                continue
            if r.returncode == 0:
                return f"{self.root} unmounted, safe to remove"
            msg = (r.stderr or r.stdout or "").strip().splitlines()
            problems.append(f"{cmd[0]}: {msg[-1] if msg else 'failed'}")

        raise EjectError("; ".join(problems) or "could not unmount")


def looks_like_card(path: str) -> bool:
    """A Pocket card always has both of these; a muOS or plain ROM card does not."""
    return all(os.path.isdir(os.path.join(path, d)) for d in ("Cores", "Platforms"))


def _linux_mounts() -> list[tuple[str, str]]:
    """(mount point, label) for the places a card gets mounted on Linux."""
    try:
        # Timeout on purpose. This runs off the Tk thread but still blocks the
        # scan, and findmnt hangs on an unresponsive mount; without it the
        # pane sits empty with nothing on screen to say why.
        out = subprocess.run(["findmnt", "-rn", "-o", "TARGET,LABEL"],
                             capture_output=True, text=True, check=True,
                             timeout=5).stdout
    except Exception:                                        # noqa: BLE001
        return []
    found = []
    for line in out.splitlines():
        parts = line.split(" ", 1)
        target = parts[0]
        label = parts[1].strip() if len(parts) > 1 else ""
        if target.startswith(("/run/media/", "/media/", "/mnt/")):
            found.append((target, label))
    return found


def _macos_mounts() -> list[tuple[str, str]]:
    """Everything under /Volumes. The volume name is the label."""
    found = []
    try:
        names = os.listdir("/Volumes")
    except OSError:
        return found
    for name in sorted(names):
        path = os.path.join("/Volumes", name)
        if os.path.isdir(path):
            found.append((path, name))
    return found


def _windows_mounts() -> list[tuple[str, str]]:
    """Every drive letter that answers. The volume label needs no extra call.

    Reading the label is a best effort: a card with none is still a card, and
    on Windows the letter is what people recognize anyway.
    """
    import string
    found = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if not os.path.isdir(root):
            continue
        label = ""
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(261)
            if ctypes.windll.kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(root), buf, ctypes.sizeof(buf),
                    None, None, None, None, 0):
                label = buf.value
        except Exception:                                    # noqa: BLE001
            pass
        found.append((root, label or letter + ":"))
    return found


def mounts() -> list[tuple[str, str]]:
    """Candidate volumes for this platform, before any of them are inspected."""
    if sys.platform == "darwin":
        return _macos_mounts()
    if os.name == "nt":
        return _windows_mounts()
    return _linux_mounts()


def find_cards() -> list[Card]:
    """Mounted volumes that look like a Pocket card.

    POCKET_CARD overrides the search with an explicit path, for a card that
    mounts somewhere unusual and for testing against a fixture tree.

    Each platform is asked a different question, because the answer lives
    somewhere different: findmnt on Linux, /Volumes on macOS, drive letters on
    Windows. What makes a card a card is the same everywhere, and
    looks_like_card() is the only thing that decides it.
    """
    forced = os.environ.get("POCKET_CARD")
    if forced:
        return [Card(forced, "POCKET_CARD")] if looks_like_card(forced) else []
    return [Card(path, label) for path, label in mounts()
            if looks_like_card(path)]
