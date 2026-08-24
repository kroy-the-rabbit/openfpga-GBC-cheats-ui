# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading a cheat file for the right system.

The Game Boy Advance tests are the point of this file. GBA codes are a
different language from Game Boy ones, and the Game Boy parser does not reject
them, it misreads them: every code comes out looking plausible and meaning
something else. These pin the fact that the two are kept apart.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cheatgui"))
sys.path.insert(1, os.path.join(ROOT, "cheats"))

import cheatfile                                             # noqa: E402
import chtparse                                              # noqa: E402
import writer                                                # noqa: E402

# A real CodeBreaker file, from the libretro database. Two of these codes carry
# a second half after the '+', which is where the Game Boy parser loses half
# the file.
GBA_FILE = b'''cheats = 3

cheat0_desc = "Enable Code (Must Be On)"
cheat0_code = "00004E72+000A+100010E4+0007"
cheat0_enable = false

cheat1_desc = "Infinite Money"
cheat1_code = "3300786D+00FF"
cheat1_enable = true

cheat2_desc = "Max Hearts"
cheat2_code = "3300786F+00FF"
cheat2_enable = false
'''

GB_FILE = b'''cheats = 2

cheat0_desc = "Infinite Health"
cheat0_code = "0140AAC6"
cheat0_enable = true

cheat1_desc = "999 Rupees"
cheat1_code = "9199ADC6+9109AEC6"
cheat1_enable = false
'''


class GameBoyStillDecodes(unittest.TestCase):
    def test_codes_are_decoded(self):
        groups = cheatfile.parse(GB_FILE, "gbc")
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].codes[0].address, 0xC6AA)
        self.assertEqual(groups[0].codes[0].value, 0x40)
        self.assertEqual(len(groups[1].codes), 2)

    def test_the_core_has_limits_and_they_are_the_rtl_s(self):
        self.assertEqual(cheatfile.limits("gbc"),
                         (chtparse.MAX_GROUPS, chtparse.MAX_CODES))
        self.assertTrue(cheatfile.decoded("gb"))
        self.assertTrue(cheatfile.decoded("gbc"))

    def test_how_a_code_applies_is_known(self):
        groups = cheatfile.parse(GB_FILE, "gbc")
        self.assertEqual(cheatfile.applied_by(groups[0].codes[0], "gbc"), "poke")


class GameBoyAdvanceIsCarriedNotRead(unittest.TestCase):
    def test_the_game_boy_parser_misreads_gba_codes(self):
        """Why this module exists. Not a rejection: a wrong answer.

        `3300786D+00FF` is a CodeBreaker code. The Game Boy parser sees eight
        hex digits, reads them as a GameShark code, and reports a write to an
        address that is not in the code at all. The `+00FF` is four digits,
        matches nothing, and vanishes.
        """
        wrong = chtparse.parse(GBA_FILE, max_codes=1 << 30, max_groups=1 << 30)
        money = [g for g in wrong if g.desc == "Infinite Money"][0]
        self.assertEqual(len(money.codes), 1)          # the +00FF is gone
        self.assertEqual(money.codes[0].address, 0x6D78)   # invented
        self.assertEqual(money.codes[0].value, 0x00)       # invented

        # And what this module does instead.
        right = cheatfile.parse(GBA_FILE, "gba")
        money = [g for g in right if g.desc == "Infinite Money"][0]
        self.assertEqual([c.raw for c in money.codes], ["3300786D", "00FF"])
        self.assertIsNone(money.codes[0].address)
        self.assertIsNone(money.codes[0].value)

    def test_nothing_is_claimed_about_a_gba_code(self):
        self.assertFalse(cheatfile.decoded("gba"))
        self.assertIsNone(cheatfile.limits("gba"))
        groups = cheatfile.parse(GBA_FILE, "gba")
        self.assertEqual(cheatfile.applied_by(groups[0].codes[0], "gba"), "")

    def test_descriptions_and_enable_flags_are_read(self):
        groups = cheatfile.parse(GBA_FILE, "gba")
        self.assertEqual([g.desc for g in groups],
                         ["Enable Code (Must Be On)", "Infinite Money",
                          "Max Hearts"])
        self.assertEqual([g.enabled for g in groups], [False, True, False])

    def test_a_multi_part_code_keeps_every_part(self):
        groups = cheatfile.parse(GBA_FILE, "gba")
        self.assertEqual([c.raw for c in groups[0].codes],
                         ["00004E72", "000A", "100010E4", "0007"])

    def test_a_gba_file_written_back_is_the_same_file(self):
        """The whole point of carrying them: nothing is lost in the round trip."""
        groups = cheatfile.parse(GBA_FILE, "gba")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "game.gba.cht")
            cheats, codes, removed = writer.write(path, groups, "gba")
            self.assertFalse(removed)
            self.assertEqual(cheats, 3)
            self.assertEqual(codes, sum(len(g.codes) for g in groups))
            back = writer.load_library(path, "gba")
            self.assertEqual(["+".join(c.raw for c in g.codes) for g in back],
                             ["+".join(c.raw for c in g.codes) for g in groups])
            self.assertEqual([g.desc for g in back], [g.desc for g in groups])
            # Everything written is written enabled: the file is the selection.
            self.assertTrue(all(g.enabled for g in back))

    def test_no_limit_is_invented_for_a_core_that_does_not_exist(self):
        groups = cheatfile.parse(GBA_FILE, "gba")
        self.assertEqual(writer.check(groups * 50, "gba"), [])
        # while the Game Boy core's limits are still enforced
        gb = cheatfile.parse(GB_FILE, "gbc")
        self.assertTrue(writer.check(gb * 40, "gbc"))


class SearchDirectories(unittest.TestCase):
    def test_gba_never_matches_a_game_boy_file(self):
        """A near miss between GB and GBC is useful. GB against GBA is not."""
        import library
        self.assertEqual(library.SEARCH["gba"], ("gba",))
        self.assertIn("gb", library.SEARCH["gbc"])
        self.assertIn("gbc", library.SEARCH["gb"])
        self.assertNotIn("gba", library.SEARCH["gb"])
        self.assertNotIn("gba", library.SEARCH["gbc"])


if __name__ == "__main__":
    unittest.main()
