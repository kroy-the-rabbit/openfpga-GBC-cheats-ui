"""Headless view of what the GUI would show, for checking without a screen."""
from __future__ import annotations

import os

import card as card_mod
import model


def main(argv: list[str]) -> int:
    cards = card_mod.find_cards()
    if not cards:
        print("no Pocket card found (needs Cores/ and Platforms/)")
        return 1
    c = cards[0]
    print(f"card: {c.root} [{c.label}]")
    want = [a for a in argv if not a.startswith("-")]
    for p in c.platforms():
        print(f"\n== {p.name} [{p.id}]  {len(p.games)} ROMs")
        for g in p.games:
            if want and not any(w.lower() in g.name.lower() for w in want):
                continue
            v = model.load(g)
            src = os.path.basename(v.source) if v.source else "NO MATCH"
            print(f"  {g.name[:52]:<54} {len(v.enabled):>2} on / "
                  f"{len(v.entries):>3} avail   {src[:46]}")
    return 0
