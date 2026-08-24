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


def ui_group(pid: str) -> str:
    """The iid of a system heading in the cartridge pane."""
    import ui
    return ui.GROUP + pid


def build_db(root_dir: str, names: list[str]) -> str:
    """A cheat database just big enough for matching to have something to do.

    Without one, opening any game raises MissingDatabase, the app reports it
    with a modal dialog, and under a headless X server that dialog waits
    forever for a click nobody is going to make. That is not something to
    leave to chance in a test suite: see the dialog stubs in setUp.
    """
    import db as db_mod
    for d in db_mod.DIRS:
        full = os.path.join(root_dir, d)
        os.makedirs(full, exist_ok=True)
        for name in names:
            with open(os.path.join(full, name + ".cht"), "w") as f:
                f.write('cheats = 1\n\n'
                        'cheat0_desc = "Infinite Hearts (3)"\n'
                        'cheat0_code = "010CAAC6"\n'
                        'cheat0_enable = false\n')
    return root_dir


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
        os.environ["POCKET_CHEAT_DB"] = build_db(
            os.path.join(cls.tmp.name, "cht"),
            [f"Game {i}" for i in range(cls.ROMS)])
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
        # Every dialog, not just the one a test means to answer. A modal
        # dialog under a headless X server blocks the whole suite until the
        # job times out, and that failure looks like a hang rather than like a
        # test that opened a dialog. These record instead, so a test can
        # assert what was shown.
        self.dialogs: list[tuple[str, tuple]] = []
        self._boxes = {name: getattr(messagebox, name) for name in
                       ("askyesno", "showerror", "showwarning", "showinfo")}
        for name in self._boxes:
            def stub(*a, _n=name, **k):
                self.dialogs.append((_n, a))
                return True if _n == "askyesno" else "ok"
            setattr(messagebox, name, stub)

    def tearDown(self) -> None:
        for name, fn in self._boxes.items():
            setattr(messagebox, name, fn)
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

        # The cartridge pane is system headings with cartridges under them.
        # The platform pane is a flat list of ROMs. Anything at the top level
        # that is not a heading means the stale read landed here.
        rows = self.app.gamelist.get_children()
        self.assertTrue(rows, "the cartridge pane is empty")
        for iid in rows:
            self.assertTrue(iid.startswith(ui_group("")),
                            "the cartridge pane was repainted by a stale read")
        leaves = [self.app.gamelist.item(c, "text")
                  for iid in rows for c in self.app.gamelist.get_children(iid)]
        self.assertEqual(sorted(leaves),
                         sorted(g.name for g in self.app.games))

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


class CartGroupingTest(CartPaneTest):
    """Cartridges are filed under the system each is for.

    A cartridge's system decides which folder on the card its cheat file goes
    in, so it has to be visible and correctable rather than assumed.
    """

    def stock(self) -> None:
        for name, plat in (("Zelda DX (USA) (Rev 2)", "gbc"),
                           ("Pokemon Red (USA)", "gb"),
                           ("Aladdin (USA)", "gb")):
            self.carts.add(name, plat)
        self.show_carts()

    def headings(self) -> list[str]:
        return list(self.app.gamelist.get_children())

    def under(self, pid: str) -> list[str]:
        return [self.app.gamelist.item(i, "text")
                for i in self.app.gamelist.get_children(ui_group(pid))]

    def test_each_cartridge_sits_under_its_system(self):
        self.stock()
        self.assertEqual(self.headings(), [ui_group("gbc"), ui_group("gb")])
        self.assertEqual(self.under("gbc"), ["Zelda DX (USA) (Rev 2)"])
        self.assertEqual(self.under("gb"), ["Aladdin (USA)", "Pokemon Red (USA)"])

    def test_a_heading_says_how_many_are_under_it(self):
        self.stock()
        self.assertIn("(2)", self.app.gamelist.item(ui_group("gb"), "text"))
        self.assertIn("Game Boy", self.app.gamelist.item(ui_group("gb"), "text"))

    def test_a_system_with_none_is_not_shown(self):
        self.carts.add("Zelda DX (USA) (Rev 2)", "gbc")
        self.show_carts()
        self.assertEqual(self.headings(), [ui_group("gbc")])

    def test_rows_still_address_the_right_cartridge(self):
        """The pane is a tree now; the flat list it indexes into is not."""
        self.stock()
        for pid in ("gbc", "gb"):
            for iid in self.app.gamelist.get_children(ui_group(pid)):
                cart = self.app.games[int(iid)]
                self.assertEqual(cart.name, self.app.gamelist.item(iid, "text"))
                self.assertEqual(cart.platform, pid)

    def test_a_heading_is_not_a_cartridge(self):
        """Selecting one must not arm Remove, or index into the game list."""
        self.stock()
        self.app.gamelist.selection_set(ui_group("gb"))
        self.pump(0.5)
        self.assertIsNone(self.app.selected_game())
        self.assertIn("disabled", self.app.del_btn.state())
        self.assertIn("disabled", self.app.move_btn.state())
        self.app.remove_cart()
        self.app.move_cart()
        self.pump(0.3)
        self.assertEqual(len(self.carts.all()), 3)

    def test_moving_refiles_it_and_keeps_it_selected(self):
        self.stock()
        target = self.app.gamelist.get_children(ui_group("gb"))[0]
        name = self.app.gamelist.item(target, "text")
        self.app.gamelist.selection_set(target)
        self.pump(0.5)
        self.assertIn("Game Boy Color", self.app.move_btn.cget("text"))

        self.app.move_cart()
        self.pump(0.5)
        self.assertIn(name, self.under("gbc"))
        self.assertNotIn(name, self.under("gb"))
        self.assertEqual(self.app.selected_game().name, name)

    def test_removing_the_last_of_a_system_drops_the_heading(self):
        self.stock()
        target = self.app.gamelist.get_children(ui_group("gbc"))[0]
        self.app.gamelist.selection_set(target)
        self.pump(0.5)
        self.app.remove_cart()
        self.pump(0.5)
        self.assertEqual(self.headings(), [ui_group("gb")])


class NoDatabaseTest(CartPaneTest):
    """The state a downloaded build starts in: no cheat database at all.

    This is what hung CI. Opening any game raised MissingDatabase, which the
    app reports with a modal dialog, and under xvfb that dialog waits for a
    click that never comes. The card panes must still work, because the
    database has nothing to do with reading the card, and the report must not
    be something that can block.
    """

    def setUp(self) -> None:
        super().setUp()
        self.saved_db = os.environ.get("POCKET_CHEAT_DB")
        os.environ["POCKET_CHEAT_DB"] = os.path.join(
            self.tmp.name, "no-such-database")
        import library
        library.refresh()

    def tearDown(self) -> None:
        if self.saved_db is None:
            os.environ.pop("POCKET_CHEAT_DB", None)
        else:
            os.environ["POCKET_CHEAT_DB"] = self.saved_db
        import library
        library.refresh()
        super().tearDown()

    def test_the_card_still_lists(self):
        self.assertTrue(self.app.systems.get_children())
        gbc = [i for i in self.app.systems.get_children()
               if self.app.systems.item(i, "text") == "Game Boy Color"][0]
        self.app.systems.selection_set(gbc)
        self.pump(2.0)
        self.assertEqual(len(self.app.gamelist.get_children()), self.ROMS)

    def test_opening_a_game_says_so_without_a_dialog(self):
        """It says what to do, in the status line, and opens nothing modal."""
        gbc = [i for i in self.app.systems.get_children()
               if self.app.systems.item(i, "text") == "Game Boy Color"][0]
        self.app.systems.selection_set(gbc)
        self.pump(2.0)
        self.app.gamelist.selection_set("0")
        self.pump(2.0)
        self.assertIn("no cheat database", self.app.status.cget("text"))
        self.assertIn("Update", self.app.status.cget("text"))
        self.assertEqual([d for d in self.dialogs if d[0] != "askyesno"], [],
                         "a missing database is not worth a dialog")


if __name__ == "__main__":
    unittest.main()
