# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's version.

Set here rather than derived from git, because a released binary has no
checkout to ask. The release workflow rewrites VERSION from the tag it is
building, so a downloaded build always names the tag it came from and a run
from a checkout says so instead.
"""
from __future__ import annotations

import os
import sys

VERSION = "0.0.0-dev"


def version() -> str:
    return os.environ.get("POCKET_CHEATS_VERSION") or VERSION


def frozen() -> bool:
    """True in a packaged build, where there is no repository alongside."""
    return bool(getattr(sys, "frozen", False))


def title() -> str:
    v = version()
    return "Pocket Cheats" + ("" if v.startswith("0.0.0") else f"  {v}")
