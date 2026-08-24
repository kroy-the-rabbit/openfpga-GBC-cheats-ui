# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading a .cht file for a particular system.

The file format is the same everywhere, libretro's `cheatN_desc/_code/_enable`.
What the codes inside it *mean* is not, and that is the whole of this module.

Game Boy and Game Boy Color codes are decoded by `chtparse`, which is the
reference model the core's RTL parser is verified against. Game Boy Advance
codes are a different language: CodeBreaker and Action Replay, written as an
eight digit address and a four digit value joined with `+`.

Handing a GBA file to the Game Boy parser does not fail, which is the reason
this module exists. `3300786D+00FF` is a CodeBreaker code; the Game Boy parser
sees eight hex digits, reads them as a GameShark code, and reports a write of
`0x00` to `$6D78`. The `+00FF` is four digits, matches nothing, and is dropped.
Every code in the file comes out looking plausible and meaning nothing, and a
file written back from that has lost half of itself.

So a system whose codes we cannot decode is carried verbatim instead. The
cheats are listed, picked and written back exactly as they came, and nothing
is claimed about what any of them does. When the GBA core defines its cheat
format, a decoder goes here and the display fills in; until then, refusing to
guess is the only honest thing this can do.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import chtparse

# Systems whose codes chtparse understands, because the core that runs them is
# the one chtparse is a model of.
DECODED = ("gb", "gbc")

# No limit is claimed for a system whose core does not exist yet. The Game Boy
# figures come from cheatcodes.sv; inventing GBA ones would put a number on
# screen that nothing checks.
LIMITS = {
    "gb":  (chtparse.MAX_GROUPS, chtparse.MAX_CODES),
    "gbc": (chtparse.MAX_GROUPS, chtparse.MAX_CODES),
}

# Reading a file to choose from is not reading it to run. The core takes the
# first 32 codes; a libretro file often holds hundreds, and truncating here
# made everything past the first couple of dozen invisible and unpickable.
NO_LIMIT = 1 << 30


def decoded(platform: str) -> bool:
    """True when the codes for this system can be read, not merely carried."""
    return platform in DECODED


def limits(platform: str) -> Optional[tuple[int, int]]:
    """(cheats, codes) the core can hold, or None if that is not known."""
    return LIMITS.get(platform)


# --------------------------------------------------------------- opaque form --
@dataclass
class OpaqueCode:
    """One code we can carry but not read.

    Shaped like `ggdecode.Cheat` so that everything downstream, which only ever
    wants `.raw`, does not have to know which kind it is holding. `address` and
    `value` are None rather than zero: a zero would be displayed.
    """
    raw: str
    kind: str = "opaque"
    address: Optional[int] = None
    value: Optional[int] = None
    compare: Optional[int] = None
    bank: Optional[int] = None


@dataclass
class OpaqueGroup:
    index: int
    codes: list = field(default_factory=list)
    desc: Optional[str] = None
    enabled: bool = True


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_opaque(data: bytes, max_groups: int = NO_LIMIT) -> list:
    """Read the file's structure without reading its codes.

    Same rules chtparse follows for which keys count: only `_desc`, `_code` and
    `_enable`, only when `=` follows, each `_code` starting a new cheat, and a
    cheat with no `_enable` key at all defaulting to on. The value of `_code` is
    kept as written, split on `+` into the pieces the file joined, so writing it
    back reproduces it character for character.
    """
    groups: list[OpaqueGroup] = []
    desc: Optional[str] = None

    for line in data.decode("utf-8", "replace").splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.endswith("_desc"):
            desc = _unquote(value)
        elif key.endswith("_code"):
            if len(groups) >= max_groups:
                break
            codes = [OpaqueCode(part.strip())
                     for part in _unquote(value).split("+") if part.strip()]
            if not codes:
                continue
            groups.append(OpaqueGroup(len(groups), codes, desc, True))
            desc = None
        elif key.endswith("_enable") and groups:
            groups[-1].enabled = _unquote(value).strip().lower() in ("true", "1")
    return groups


# ---------------------------------------------------------------- the reader --
def parse(data: bytes, platform: str, max_groups: int = NO_LIMIT) -> list:
    """Cheat groups from a file, read the way this system's codes work."""
    if decoded(platform):
        return chtparse.parse(data, max_codes=NO_LIMIT, max_groups=max_groups)
    return parse_opaque(data, max_groups=max_groups)


def applied_by(code, platform: str) -> str:
    """How the core makes one code take effect, or "" when that is not known."""
    if not decoded(platform):
        return ""
    return chtparse.applied_by(code)
