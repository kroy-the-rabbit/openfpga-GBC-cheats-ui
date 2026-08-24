# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for the cartridge pane, driven through the real widgets.

These need a display; run them under xvfb-run in CI. They exist because the
bug they cover was invisible from the outside: removing a cartridge silently
did nothing, and the IndexError behind it went to Tk's callback log rather
than to the window.
"""
from __future__ import annotations

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cheatgui"))
sys.path.insert(1, os.path.join(ROOT, "cheats"))

import tkinter as tk                                         # noqa: E402
from tkinter import messagebox                               # noqa: E402


def build_card(root_dir: str, roms: int) -> str:
    """A directory that card.looks_like_card() accepts."""
    for d in ("Cores", "Platforms", "Assets/gb/common", "Assets/gbc/common"):
        os.makedirs(os.path.join(root_dir, d), exist_ok=True)
    for pid, name in (("gb", "Game Boy"), ("gbc", "Game Boy Color")):
        with open(os.path.join(root_dir, "Platforms", f"{pid}.json"), "w") as f:
            f.write('{"platform": {"name": "%s"}}' % name)
    for i in range(roms):
        with open(os.path.join(root_dir, "Assets/gbc/common", f"Game {i}.gbc"),
                  "wb") as f:
            f.write(b"\0" * 64)
    return root_dir


class CartPaneTest(unittest.TestCase):
    ROMS = 40

    @classmethod
    def setUpClass(cls) -> None:
        import tempfile
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["XDG_CONFIG_HOME"] = os.path.join(cls.tmp.name, "config")
        os.environ["XDG_DATA_HOME"] = os.path.join(cls.tmp.name, "data")
        os.environ["POCKET_CARD"] = build_card(
            os.path.join(cls.tmp.name, "card"), cls.ROMS)
        # One interpreter, one Tk. Creating and destroying a root per test
        # while worker threads are still live is what makes Tcl abort the run
        # with "async handler deleted by the wrong thread"; only the App frame
        # is rebuilt between tests.
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()
        cls.tmp.cleanup()

    def setUp(self) -> None:
        import carts
        import db
        self.carts = carts
        # No network in the tests. The app checks the database version on the
        # way up, and a real check would make these depend on GitHub being
        # reachable and on how fast it answers.
        self._remote_state = db.remote_state
        db.remote_state = lambda timeout=None: {
            "sha": "0" * 40, "date": "2026-01-01T00:00:00Z"}
        self.db = db
        for c in carts.all():
            carts.remove(c.name)
        import ui
        self.ui = ui
        self.app = ui.App(self.root)
        self.pump(2.0)
        self._askyesno = messagebox.askyesno
        messagebox.askyesno = lambda *a, **k: True

    def tearDown(self) -> None:
        messagebox.askyesno = self._askyesno
        self.db.remote_state = self._remote_state
        # Let the version check finish before the interpreter tears Tk down.
        # Destroying the root while a worker thread is still live is what
        # Tcl_AsyncDelete complains about, and it aborts the whole run.
        # Drain both runners before the widgets they will write to go away.
        end = time.time() + 15
        while time.time() < end and (self.app.dbjob.busy()
                                     or self.app.worker.busy):
            self.root.update()
            time.sleep(0.01)
        self.app.destroy()
        self.root.update()

    def pump(self, secs: float = 1.0) -> None:
        end = time.time() + secs
        while time.time() < end:
            self.root.update()
            time.sleep(0.01)

    def show_carts(self) -> None:
        self.app.systems.selection_set(self.ui.CARTS)
        self.pump(0.5)

    # ------------------------------------------------------------------------
    def test_remove_cartridge(self):
        self.carts.add("Zelda DX (USA)", "gbc")
        self.carts.add("Pokemon Red (USA)", "gb")
        self.show_carts()
        self.app.gamelist.selection_set("0")
        self.pump(0.5)
        target = self.app.games[0].name
        self.app.remove_cart()
        self.pump(0.5)
        self.assertNotIn(target, [c.name for c in self.carts.all()])

    def test_remove_after_switching_from_a_platform(self):
        """The pane must not be repainted by the read the user moved away from.

        Selecting a system starts an off-thread read of its ROMs. Clicking
        Cartridges before it answers used to let that answer land anyway: the
        pane filled with the platform's ROMs while self.games still held the
        cartridges, so every row indexed the wrong object and Remove did
        nothing at all.
        """
        self.carts.add("Zelda DX (USA)", "gbc")
        self.carts.add("Pokemon Red (USA)", "gb")

        gbc = [i for i in self.app.systems.get_children()
               if self.app.systems.item(i, "text") == "Game Boy Color"][0]
        self.app.systems.selection_set(gbc)
        self.root.update()                    # submits the read, does not wait
        self.app.systems.selection_set(self.ui.CARTS)
        self.root.update()                    # show_carts() fills the pane now
        self.pump(2.0)                        # the stale read lands in here

        rows = self.app.gamelist.get_children()
        self.assertEqual(len(rows), len(self.app.games),
                         "the cartridge pane was repainted by a stale read")
        self.assertEqual([self.app.gamelist.item(i, "text") for i in rows],
                         [g.name for g in self.app.games])

        self.app.gamelist.selection_set("0")
        self.pump(0.5)
        target = self.app.games[0].name
        self.app.remove_cart()
        self.pump(0.5)
        self.assertNotIn(target, [c.name for c in self.carts.all()])

    def test_remove_needs_a_cartridge_selected(self):
        """Remove is inert on a ROM row, whatever the button state says."""
        self.carts.add("Zelda DX (USA)", "gbc")
        gbc = [i for i in self.app.systems.get_children()
               if self.app.systems.item(i, "text") == "Game Boy Color"][0]
        self.app.systems.selection_set(gbc)
        self.pump(2.0)
        self.app.gamelist.selection_set("0")
        self.pump(0.5)
        self.app.remove_cart()
        self.pump(0.3)
        self.assertEqual([c.name for c in self.carts.all()], ["Zelda DX (USA)"])

    def test_removing_the_last_cartridge_empties_the_pane(self):
        self.carts.add("Only One (USA)", "gbc")
        self.show_carts()
        self.app.gamelist.selection_set("0")
        self.pump(0.5)
        self.app.remove_cart()
        self.pump(0.5)
        self.assertEqual(self.carts.all(), [])
        self.assertEqual(self.app.gamelist.get_children(), ())
        self.assertIn("disabled", self.app.del_btn.state())


if __name__ == "__main__":
    unittest.main()
