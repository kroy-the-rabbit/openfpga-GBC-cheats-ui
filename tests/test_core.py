# SPDX-License-Identifier: GPL-3.0-or-later
"""The Pocket core: what is on the card, what is missing, and installing it.

No network and no widgets. Two things here are worth pinning down. The first
is that an archive naming a path outside the card is refused rather than
unpacked, because this is the one place in the app that writes files it did
not compose itself, onto the root of somebody's SD card. The second is that a
failed install leaves the core that was already there working: it swaps a
staged copy into place rather than unpacking over the live one.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cheatgui"))
sys.path.insert(1, os.path.join(ROOT, "cheats"))

import core                                                  # noqa: E402

GBC = core.CORES[0]
GB = core.CORES[1]


def core_json(cid: str, platform: str, version: str) -> str:
    return json.dumps({"core": {"metadata": {
        "platform_ids": [platform], "shortname": cid.split(".")[1],
        "author": cid.split(".")[0], "version": version}}})


def data_json(*slots) -> str:
    return json.dumps({"data": {"magic": "APF_VER_1", "data_slots": [
        # The browsable slots, which have no fixed filename and must never be
        # reported as something the user has to supply.
        {"name": "Cartridge", "id": 1, "required": True,
         "extensions": ["gbc"]},
        {"name": "Save", "id": 18, "required": False, "nonvolatile": True},
        *slots]}})


def write(path: str, text: str = "x") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def install_core(root: str, c: core.Core, version: str, *slots) -> None:
    d = os.path.join(root, "Cores", c.id)
    write(os.path.join(d, "core.json"), core_json(c.id, c.platform, version))
    write(os.path.join(d, "data.json"), data_json(*slots))


def release_zip(c: core.Core, version: str, extra=()) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"Cores/{c.id}/core.json",
                    core_json(c.id, c.platform, version))
        zf.writestr(f"Cores/{c.id}/data.json", data_json())
        zf.writestr(f"Cores/{c.id}/{c.platform}.rbf_r", "bitstream")
        zf.writestr(f"Platforms/{c.platform}.json", "{}")
        zf.writestr(f"Platforms/_images/{c.platform}.bin", "image")
        for name, text in extra:
            zf.writestr(name, text)
    return buf.getvalue()


class Env(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)


class Installed(Env):
    def test_absent_core_reads_as_none(self) -> None:
        self.assertEqual(core.installed(self.root),
                         {GBC.id: None, GB.id: None})

    def test_version_comes_from_the_cards_own_core_json(self) -> None:
        install_core(self.root, GBC, "1.4.0-cheats.9")
        self.assertEqual(core.installed(self.root)[GBC.id], "1.4.0-cheats.9")

    def test_unreadable_core_json_is_not_installed(self) -> None:
        write(os.path.join(self.root, "Cores", GBC.id, "core.json"), "{oops")
        self.assertIsNone(core.installed(self.root)[GBC.id])


class Wanted(Env):
    """Which files the core says you have to supply."""

    def test_the_cards_data_json_wins_over_the_table(self) -> None:
        install_core(self.root, GBC, "1.0", {
            "name": "Some Other BIOS", "filename": "other.bin",
            "required": True, "size_exact": 4096})
        got = core.wanted(self.root, GBC)
        self.assertEqual([r.filename for r in got], ["other.bin"])
        self.assertEqual(got[0].size, 4096)

    def test_browsable_slots_are_not_files_you_supply(self) -> None:
        # Cartridge and Save are required and have no fixed filename. Reporting
        # either as missing would tell every user their card is broken.
        install_core(self.root, GBC, "1.0")
        self.assertEqual(core.wanted(self.root, GBC), GBC.bios)

    def test_optional_fixed_files_are_not_demanded(self) -> None:
        install_core(self.root, GBC, "1.0", {
            "name": "Palette", "filename": "pal.bin", "required": False})
        self.assertEqual(core.wanted(self.root, GBC), GBC.bios)

    def test_an_uninstalled_core_falls_back_to_the_table(self) -> None:
        self.assertEqual(core.wanted(self.root, GB), GB.bios)


class BootRoms(Env):
    def test_only_installed_cores_are_reported(self) -> None:
        install_core(self.root, GBC, "1.0")
        got = core.boot_roms(self.root)
        self.assertEqual([r.core.id for r in got], [GBC.id])

    def test_a_missing_rom_names_where_it_goes(self) -> None:
        install_core(self.root, GBC, "1.0")
        bad = core.survey(self.root).problems()
        self.assertEqual([r.rom.filename for r in bad], ["gbc_bios.bin"])
        self.assertEqual(bad[0].where,
                         os.path.join("Assets", "gbc", "common",
                                      "gbc_bios.bin"))

    def test_a_present_rom_of_the_right_size_is_fine(self) -> None:
        install_core(self.root, GBC, "1.0")
        write(os.path.join(self.root, "Assets", "gbc", "common",
                           "gbc_bios.bin"), "z" * 2304)
        self.assertEqual(core.survey(self.root).problems(), [])

    def test_a_core_specific_directory_also_counts(self) -> None:
        install_core(self.root, GBC, "1.0")
        write(os.path.join(self.root, "Assets", "gbc", GBC.id,
                           "gbc_bios.bin"), "z" * 2304)
        self.assertEqual(core.survey(self.root).problems(), [])

    def test_the_wrong_size_is_reported_separately_from_missing(self) -> None:
        install_core(self.root, GBC, "1.0")
        write(os.path.join(self.root, "Assets", "gbc", "common",
                           "gbc_bios.bin"), "short")
        bad = core.survey(self.root).problems()
        self.assertTrue(bad[0].wrong_size)
        self.assertIsNotNone(bad[0].path)
        text, warn = core.describe_roms(core.survey(self.root))
        self.assertTrue(warn)
        self.assertIn("wrong size", text)


class Versions(unittest.TestCase):
    def remote(self, version: str) -> dict:
        return {"tag": "v" + version, "version": version, "page": "",
                "assets": {f"{c.asset}{version}.zip": "http://example/x.zip"
                           for c in core.CORES}}

    def test_the_released_version_is_up_to_date(self) -> None:
        rem = self.remote("1.4.0-cheats.9")
        have = {c.id: "1.4.0-cheats.9" for c in core.CORES}
        self.assertEqual(core.outdated(have, rem), [])
        self.assertNotIn("update available", core.describe(
            core.Survey("/card", have, []), rem)[0])

    def test_an_absent_core_is_outdated(self) -> None:
        rem = self.remote("1.4.0-cheats.9")
        have = {c.id: None for c in core.CORES}
        self.assertEqual([c.id for c in core.outdated(have, rem)],
                         [c.id for c in core.CORES])

    def test_no_core_at_all_says_so_loudly(self) -> None:
        sv = core.Survey("/card", {c.id: None for c in core.CORES}, [])
        text, bad = core.describe(sv, None)
        self.assertTrue(bad)
        self.assertIn("not installed", text)

    def test_only_the_core_that_differs_is_listed(self) -> None:
        rem = self.remote("2.0")
        have = {GBC.id: "1.0", GB.id: "2.0"}
        self.assertEqual([c.id for c in core.outdated(have, rem)], [GBC.id])

    def test_a_release_with_no_zip_for_a_core_cannot_update_it(self) -> None:
        rem = self.remote("2.0")
        del rem["assets"][f"{GB.asset}2.0.zip"]
        self.assertEqual([c.id for c in core.outdated({GBC.id: None,
                                                       GB.id: None}, rem)],
                         [GBC.id])


class Archive(Env):
    """What comes out of a zip before any of it touches the card."""

    def members(self, data: bytes, c: core.Core = GBC):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return core._members(zf, c)

    def test_a_real_release_lists_its_files(self) -> None:
        names = [m.filename for m in self.members(release_zip(GBC, "1.0"))]
        self.assertIn(f"Cores/{GBC.id}/core.json", names)
        self.assertIn("Platforms/gbc.json", names)

    def test_a_zip_for_another_core_is_refused(self) -> None:
        with self.assertRaises(RuntimeError):
            self.members(release_zip(GB, "1.0"), GBC)

    def test_a_parent_directory_escape_is_refused(self) -> None:
        bad = release_zip(GBC, "1.0", [("../../etc/passwd", "root")])
        with self.assertRaises(RuntimeError):
            self.members(bad)

    def test_an_absolute_path_is_refused(self) -> None:
        bad = release_zip(GBC, "1.0", [("/etc/passwd", "root")])
        with self.assertRaises(RuntimeError):
            self.members(bad)

    def test_a_drive_letter_is_refused(self) -> None:
        bad = release_zip(GBC, "1.0", [("C:/Windows/system32/x.dll", "x")])
        with self.assertRaises(RuntimeError):
            self.members(bad)

    def test_a_backslash_escape_is_refused(self) -> None:
        # Windows separators are normalised before the check, so an entry
        # spelled with them cannot slip past a check written for forward ones.
        bad = release_zip(GBC, "1.0", [("..\\\\..\\\\evil.txt", "x")])
        with self.assertRaises(RuntimeError):
            self.members(bad)


class Place(Env):
    """Moving an unpacked release onto the card."""

    def stage(self, c: core.Core, version: str) -> str:
        staged = os.path.join(self.root, "staging", c.id)
        with zipfile.ZipFile(io.BytesIO(release_zip(c, version))) as zf:
            zf.extractall(staged)
        return staged

    def test_the_core_directory_is_replaced_whole(self) -> None:
        install_core(self.root, GBC, "0.9")
        stale = os.path.join(self.root, "Cores", GBC.id, "leftover.json")
        write(stale, "{}")
        core._place(self.stage(GBC, "1.0"), self.root, GBC)
        self.assertEqual(core.installed(self.root)[GBC.id], "1.0")
        self.assertFalse(os.path.exists(stale))

    def test_shared_directories_are_merged_not_replaced(self) -> None:
        # Platforms/ belongs to every core on the card. Swapping it the way the
        # core's own directory is swapped would delete every other core's
        # entry, and the Pocket would stop listing them.
        other = os.path.join(self.root, "Platforms", "snes.json")
        write(other, "{}")
        core._place(self.stage(GBC, "1.0"), self.root, GBC)
        self.assertTrue(os.path.exists(other))
        self.assertTrue(os.path.exists(
            os.path.join(self.root, "Platforms", "gbc.json")))

    def test_installing_one_core_leaves_the_other_alone(self) -> None:
        install_core(self.root, GB, "0.9")
        core._place(self.stage(GBC, "1.0"), self.root, GBC)
        self.assertEqual(core.installed(self.root),
                         {GBC.id: "1.0", GB.id: "0.9"})

    def test_a_card_with_no_cores_directory_gets_one(self) -> None:
        core._place(self.stage(GBC, "1.0"), self.root, GBC)
        self.assertEqual(core.installed(self.root)[GBC.id], "1.0")


class InstallEnd(Env):
    """install(), with the download replaced but the card work real."""

    def remote(self, version: str) -> dict:
        return {"tag": "v" + version, "version": version, "page": "",
                "assets": {f"{c.asset}{version}.zip": "zip:" + c.id
                           for c in core.CORES}}

    def setUp(self) -> None:
        super().setUp()
        self.real = core._fetch
        self.version = "1.0"

        def fake(url, say, stop, timeout):
            cid = url.split(":", 1)[1]
            c = next(x for x in core.CORES if x.id == cid)
            data = release_zip(c, self.version)
            say(len(data), len(data))
            return data

        core._fetch = fake
        self.addCleanup(lambda: setattr(core, "_fetch", self.real))

    def test_a_bare_card_gets_both_cores(self) -> None:
        rem = self.remote("1.0")
        core.install(self.root, rem)
        self.assertEqual(core.installed(self.root),
                         {GBC.id: "1.0", GB.id: "1.0"})

    def test_nothing_to_do_writes_nothing(self) -> None:
        rem = self.remote("1.0")
        core.install(self.root, rem)
        self.assertEqual(core.install(self.root, rem), [])

    def test_the_staging_directory_does_not_survive(self) -> None:
        core.install(self.root, self.remote("1.0"))
        self.assertFalse(os.path.exists(os.path.join(self.root,
                                                     core.STAGING)))

    def test_a_stopped_install_leaves_the_old_core_running(self) -> None:
        install_core(self.root, GBC, "0.9")
        install_core(self.root, GB, "0.9")
        rem = self.remote("1.0")
        with self.assertRaises(core.Cancelled):
            core.install(self.root, rem, cancelled=lambda: True)
        self.assertEqual(core.installed(self.root),
                         {GBC.id: "0.9", GB.id: "0.9"})
        self.assertFalse(os.path.exists(os.path.join(self.root,
                                                     core.STAGING)))

    def test_a_failed_download_leaves_the_old_core_running(self) -> None:
        install_core(self.root, GBC, "0.9")

        def boom(url, say, stop, timeout):
            raise RuntimeError("connection reset")

        core._fetch = boom
        with self.assertRaises(RuntimeError):
            core.install(self.root, self.remote("1.0"))
        self.assertEqual(core.installed(self.root)[GBC.id], "0.9")

    def test_boot_roms_are_not_disturbed_by_an_install(self) -> None:
        rom = os.path.join(self.root, "Assets", "gbc", "common",
                           "gbc_bios.bin")
        write(rom, "z" * 2304)
        core.install(self.root, self.remote("1.0"), cores=[GBC])
        self.assertEqual(core.survey(self.root).problems(), [])
        self.assertEqual(os.path.getsize(rom), 2304)


if __name__ == "__main__":
    unittest.main()
