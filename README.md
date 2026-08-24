# Pocket cheat picker

A small desktop app for choosing which cheats go on an Analogue Pocket SD card,
for the Game Boy and Game Boy Color cores.

Three panes: the systems on the card, the games in each, and the cheats for the
selected game. Tick what you want and press **Send to Pocket**. The file next to
the ROM *is* the state, so what you see is what the handheld will do.

## Get it

Download a build from the
[releases page](https://github.com/kroy-the-rabbit/openfpga-GBC-cheats-ui/releases),
or run it from a checkout:

```sh
make cheatdb          # optional: the cheat database as a git submodule
make gui              # or: cheatgui/run.sh
make list ARGS=zelda  # same data, printed, no window
```

Full install notes, and how to check the signature on a download, are in
[docs/INSTALL.md](docs/INSTALL.md).

> **The macOS and Windows builds are untested.** They are built and signed by
> CI, and nobody has run either of them. Only the Linux build has been used.
> They are offered on that basis: if one does not start, that is a bug worth
> reporting, not something already known to work. The macOS build is also
> **not notarized** and needs one command to get past Gatekeeper.

Python 3.10 or newer with tkinter, if you are running from source. Everything
used is in the standard library, so the venv `run.sh` makes stays empty; it
exists so nothing is ever installed into the host Python.

Full guide: [docs/CHEATGUI.md](docs/CHEATGUI.md).

## The cheat database

The app needs the libretro cheat database, about 3000 files across the three
systems. It has none on first run: press **Update** in the bar along the
bottom and it fetches one, roughly 15 MB and a minute. It comes from
[libretro/libretro-database](https://github.com/libretro/libretro-database)
and is CC-BY-SA-4.0; none of it is shipped with this app.

That bar is also the version display. It says how many files you have and what
they are dated, and it checks upstream on startup, so you can see at a glance
whether there is anything newer:

```
cheat database: 2456 files, 2026-08-01  up to date
cheat database: 2456 files, 2026-03-14  update available: 2026-08-01
cheat database: not fetched yet, press Update
```

The comparison is against the newest upstream commit that touched the two Game
Boy directories, not the repository head, which moves several times a week for
systems this core cannot run. **Update** checks first and only downloads if
there is something to download. An update that fails or is stopped leaves the
database you already had exactly as it was.

Cheat files of your own go in `~/.local/share/pocket-cheats/cht/`, outside the
database, so an update cannot lose them. They are searched first.

## Ejecting

**Eject** flushes writes and unmounts the card. Writing already syncs, but a
sync is not an unmount, and a card pulled between the two can lose the write.
If something still has the card open the app says so and leaves it mounted; it
does not force anything.

---

# Cartridges: read this part

Cheats work on a real cartridge. Everything below is about what that costs you,
because the cartridge path is the one where this tool cannot check your work and
where getting it wrong has consequences a ROM does not.

**On a cartridge, identifying the right cheat file is your job, and nothing in
this tool or in the core can do it for you or tell you that you got it wrong.**

## Why the cartridge path is different

A cartridge is not a file on the card. The app never sees it, so:

* It **never appears in the game list.** You add it yourself: the **Cartridges**
  entry in the systems pane, **Add cartridge...**, then type the name and say
  which system it is for. Your cartridges are then listed under **Game Boy**
  and **Game Boy Color** headings, and **Move to...** refiles one that went in
  under the wrong heading.
* **The system is not cosmetic.** It decides which folder on the card the
  cheat file is written to, `Assets/<system>/common/Cartridges/`. Choose the
  wrong one and the core's **Load Cheats** browser will not be looking where
  the file is.

Game Boy Advance cartridges can be listed and prepared the same way, but the
[GBA core](https://github.com/mincer-ray/openfpga-GBA) does not read cheat
files yet, so nothing sent to one takes effect until it does. Its codes are
carried verbatim rather than decoded, so the **Applied** column is blank for
them and there is no store meter; [docs/CHEATGUI.md](docs/CHEATGUI.md) says
why.
* **The name you type is the whole of the matching.** The picker matches cheat
  files by filename. Type `Zelda` and you will be offered files for every Zelda
  ever released on the system. Nothing reads the cartridge.
* **The Pocket will not load the file by name either.** In Play Cartridge mode
  APF does not load a slot named after slot 0, so `<name>.cht` is not picked up
  automatically. Use **Load Cheats** in the core menu to browse for it once; the
  slot remembers it for later launches. The files go in their own folder,
  `/Assets/<platform>/common/Cartridges/`, so that browser opens on your
  cartridges instead of a few hundred ROMs.

With a ROM on the card, none of this applies. The app reads the actual file,
matches it, tells you which file it picked, and you can check a Game Genie
compare byte against the ROM itself. A cartridge gives you none of that.

## What goes wrong, and how

You cannot tell a cartridge's revision from the outside. The label does not say,
and two carts that look identical can hold different builds with different
memory layouts. A cheat published for one revision is aimed at an address that
means something else on another. The two kinds of code then fail in completely
different ways.

### Game Genie codes fail safely

A Game Genie code carries a **compare byte**, and the core only applies the
patch when the byte already at that address matches. On the wrong revision it
never matches, so the code loads, reads as enabled, and does nothing at all.
Disappointing, not dangerous.

### GameShark codes do not

A GameShark code is a **real write into work RAM**, made once a frame, with
nothing to check against. On the wrong revision that address holds some other
variable, and the core writes over it regardless. From there:

* **Crashes.** The byte you are overwriting may be a pointer, a counter the
  game's own logic depends on, or a state machine's state. Overwritten every
  frame, forever.
* **Corrupted saves.** This is the one worth being careful about. A game builds
  its save data out of the same work RAM the code is writing into. Corrupt the
  wrong byte and the game will happily write the result into your save at the
  next save point, and it is a real cartridge, so that is the only copy.

**There is no undo.** In Play Cartridge mode the save lives in the cartridge's
own battery-backed RAM. The core reads and writes it over the edge connector
and does not copy it to the SD card, so nothing on the card is a backup of it
and a savestate is not one either. If the save matters, dump the cartridge with
a dedicated cart reader before you put a GameShark code on it. This is not
advice about this app, it is advice about writing into the RAM of a game you
cannot restore.

The app marks this where it can. The status line warns when a cartridge
selection contains written codes, and the **Applied** column says `written` or
`patched` for every cheat, so you can see which kind you are about to send
before you send it. It cannot tell you whether the address is right, because it
cannot see the cartridge.

## Doing it properly

1. **Name the cartridge exactly as the ROM is named**, including the region and
   revision tags: `Legend of Zelda, The - Link's Awakening DX (USA, Europe) (Rev 2)`.
   That name is what the matching has to work with, and a name without a
   revision tag matches a file for some other revision just as readily.
2. **Prefer Game Genie codes.** They fail silently instead of destructively, and
   for a cartridge whose revision you are guessing at, that is the whole
   argument.
3. **Check the compare bytes if you have a dump of that exact cartridge:**

   ```sh
   cheats/cht check "Zelda (USA) (Rev 2)" --rom /path/to/dump.gbc
   ```

   This is the only real verification available. It says which Game Genie codes
   match the ROM, and in which bank. A code that matches nothing will never
   fire; a code that matches is aimed where its author meant.
4. **Back the save up first**, if the game has one you care about.
5. **Check it took.** In the core menu, **CL:** shows the bytes, cheats and
   codes parsed, and **CD:** shows what the engine is actually doing. All zeroes
   means the file never loaded, which is a different problem from a wrong code.

If a game misbehaves, turn the cheats off before assuming the cartridge is at
fault: **Cheats enabled** in the core menu is a single global switch.

---

## What it shows

Each cheat says how the core applies it, because the two ways do not behave the
same. A GameShark code is written into RAM once a frame; a Game Genie code
overrides the CPU's read, which is what a ROM patch needs. The core's own
`docs/CHEATS.md` has the detail.

That distinction is what the cartridge section above turns on, and it is worth
knowing for ROMs too: a written cheat puts the value where the game finds it by
any route, so the game's own logic still sees it and can clamp it.

## Why it is not in the core repo

The core lives in
[openfpga-GBC-cheats](https://github.com/kroy-the-rabbit/openfpga-GBC-cheats), a
fork of `budude2/openfpga-GBC` that may be PR'd upstream. A desktop app that reads SD
cards has no business in that diff. The two share a cheat file parser; see
[cheats/README.md](cheats/README.md) for how that copy is kept honest.

## Development

```sh
make test          # parser self-test and the GUI tests
make dist          # build the binary for this platform
make sync-check    # is the shared parser still in step with the core?
```

Releasing, signing and the state of macOS notarization:
[docs/RELEASING.md](docs/RELEASING.md).

## Credits

This app writes cheat files for other people's cores. It contains none of their
code, but it exists because of them.

| | |
|---|---|
| [budude2/openfpga-GBC](https://github.com/budude2/openfpga-GBC) | the Pocket Game Boy / Game Boy Color core this was written for |
| [MiSTer-devel/Gameboy_MiSTer](https://github.com/MiSTer-devel/Gameboy_MiSTer) | which that is a port of, carrying Till Harbaum's 2015 copyright and later contributors' |
| [mincer-ray/openfpga-GBA](https://github.com/mincer-ray/openfpga-GBA) | the Pocket Game Boy Advance core, GPL-2.0 |
| [MiSTer-devel/GBA_MiSTer](https://github.com/MiSTer-devel/GBA_MiSTer) | which that is a port of, GPL-2.0 |
| [SameBoy](https://github.com/LIJI32/SameBoy) | `Core/cheats.c`, the reference the Game Genie decoder follows. Expat (MIT) licence, copyright Lior Halphon |
| [libretro/libretro-database](https://github.com/libretro/libretro-database) | the cheat files themselves |
| [Analogue openFPGA](https://www.analogue.co/developer) | the Pocket framework the cores are built on |

## License

This app is GPL-3.0-or-later. The full text is in [LICENSE](LICENSE), and every
source file carries an SPDX header saying the same.

`cheats/chtparse.py` and `cheats/ggdecode.py` are copies, kept byte identical,
of the reference parser from
[openfpga-GBC-cheats](https://github.com/kroy-the-rabbit/openfpga-GBC-cheats),
which is GPL-3.0-or-later as part of that core; this app is built around them.
The Game Genie decoding in `ggdecode.py` follows the algorithm in SameBoy's
`Core/cheats.c` rather than copying its code. SameBoy is under the Expat (MIT)
licence, copyright Lior Halphon.

**The cheat database is not distributed here.**
[libretro/libretro-database](https://github.com/libretro/libretro-database) is
licensed **CC-BY-SA-4.0**, and no part of it is in this repository or in any
release of this app: it is fetched from upstream at run time, into your own
data directory. A cheat file this app writes to your card is a selection taken
from those files, so if you pass one on, CC-BY-SA-4.0 is the licence it came
under and attribution and share-alike are what it asks for.

The two Pocket cores are separate works under their own terms, GPL-2.0 for the
Game Boy Advance one and per-file notices for the Game Boy one. Nothing from
either is included here.
