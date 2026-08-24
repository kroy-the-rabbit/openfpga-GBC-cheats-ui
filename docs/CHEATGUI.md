# Cheat picker

A small desktop app for choosing which cheats go on the Pocket card.

```sh
make gui                              # or: cheatgui/run.sh
cheatgui/run.sh --list          # same data, printed, no window
cheatgui/run.sh --list zelda -v # filtered, and every cheat listed
```

Set `POCKET_CARD=/path/to/card` to point the tool at an explicit directory
instead of searching the mounted volumes. What gets searched depends on the
platform, because the answer lives somewhere different on each: `findmnt` on
Linux, `/Volumes` on macOS, drive letters on Windows. What makes a card a card
is the same everywhere, a directory holding both `Cores/` and `Platforms/`.

`run.sh` creates `cheatgui/.venv` on first run. Everything used is in the
Python standard library, so the venv stays empty; it exists so nothing is ever
installed into the host Python.

Only one window runs at a time; a second launch is refused and names the one
that is already open. Two windows on the same card each hold their own idea of
what is installed, and since **Send to Pocket** writes exactly what is ticked,
whichever saved last would silently win while the other still showed its stale
ticks. `--list` is exempt, being read only, so you can query the card from a
terminal with the window open.

Reading the card happens off the Tk thread. A cold walk of `/Assets` over USB
takes seconds, and doing it inline froze the window mid-click, which is
indistinguishable from a crash even though it recovers. Scanning, listing a
system, loading a game and writing all run in a worker; the newest request
wins, so clicking through the game list faster than the card can answer leaves
the pane showing what you asked for last rather than whichever read finished
last.

If the window ever stops responding, `kill -USR1 <pid>` prints the stack of
whatever it is blocked on to its stderr. That is how both of these were
found.

## The cheat database

The picker needs the libretro cheat database and does not ship with one. The bar
along the bottom says what it has and what upstream has:

```
cheat database: 2456 files, 2026-08-01  up to date
cheat database: 2456 files, 2026-03-14  update available: 2026-08-01
cheat database: not fetched yet, press Update
```

**Update** checks upstream first and downloads only if there is something to
download, so pressing it when you are current costs two API calls rather than
2456 files. The download runs on its own thread with the count on screen, so
the panes stay usable while it goes; **Stop** aborts it. A fetch that fails or
is stopped changes nothing, because the files land in a temporary directory and
are only swapped in once every one of them has arrived.

The comparison is against the newest upstream commit that touched the two Game
Boy directories, not the repository head. The head moves several times a week
for systems the Pocket has no core for, and comparing against it would report an
update every time somebody edited a PlayStation cheat file.

Three places are searched, in order: `POCKET_CHEAT_DB` if it is set, the copy
the app fetched into `~/.local/share/pocket-cheats/libretro/`, and the
`external/libretro-database` submodule in a checkout. A submodule is a shallow
clone, and in one of those every path looks as though HEAD introduced it, so its
version cannot be compared with upstream; the bar says so rather than inventing
an answer.

## Ejecting the card

**Eject** syncs and then unmounts. Writing to the card already syncs, but a sync
is not an unmount: the filesystem is still mounted and the kernel may still have
metadata to write back, and a card pulled between the two can lose the write
that the sync was for.

It uses `udisksctl` on Linux and falls back to `umount`, `diskutil unmount` on
macOS, and the shell's own Eject verb on Windows, which is what Explorer uses.
If something still has the card open it says so and leaves the card mounted.
Nothing is forced: a card yanked mid-write is the failure this whole tool exists
to avoid.

## What it shows

Three panes: the systems on the card, the games in the selected system, and the
cheats for the selected game. Tick the ones you want and press **Send to
Pocket**.

**Game Boy**, **Game Boy Color** and **Game Boy Advance** are listed. An NES or
SNES core on the same card ignores cheat files entirely, so offering checkboxes
there would be a lie.

Game Boy Advance is listed ahead of the core being able to use it. The
[GBA core](https://github.com/mincer-ray/openfpga-GBA) has no cheat data slot
yet, so a file sent to a GBA game sits on the card doing nothing until it
does. It is here so the cartridges and the files can be prepared now.

## Game Boy Advance codes are carried, not read

GBA cheats are a different language from Game Boy ones. A CodeBreaker code is
an eight digit address and a four digit value joined with `+`, like
`3300786D+00FF`; a Game Boy GameShark code is eight digits meaning something
else entirely.

Handing a GBA file to the Game Boy parser does not fail, which is the whole
problem. It sees eight hex digits, reads them as a GameShark code, and reports
a write of `0x00` to `$6D78`, an address that is not in the code at all. The
`+00FF` is four digits, matches nothing, and is dropped. Every cheat in the
file comes out looking plausible and meaning nothing, and a file written back
from that has lost half of itself.

So GBA files are carried verbatim instead. You can list, pick and send them,
and the file written to the card is character for character what the database
had. What you do not get is anything this app would have to invent:

* the **Applied** column is blank, because whether a code is a write or a patch
  is a property of a core that does not exist yet
* there is no code store meter, only a count, since no limit has been published
  to measure against
* GBA cheat files are matched only against GBA ROMs. Game Boy and Game Boy
  Color share a search, because a GBC release filed under Game Boy is a near
  miss worth catching; a Game Boy file matched to a GBA ROM would not be a near
  miss, it would be nonsense.

When the GBA core defines its cheat format, the decoder goes in
`cheatgui/cheatfile.py` and the display fills itself in. Until then, refusing
to guess is the only honest thing this can do.

The **Applied** column says how the core makes each cheat take effect, because
the two ways do not behave the same:

| | |
|---|---|
| `written` | a GameShark code: the value is written into RAM once a frame, so the game's own logic still sees it and can clamp it |
| `patched` | the CPU's read is overridden. Right for Game Genie, which patches ROM, and the fallback for a GameShark code aimed somewhere the core cannot write |
| `mixed` | one cheat holding both |

A written cheat puts the value where the game would find it by any route, not
just on the one read the core can see, which is what the codes were written
against. `docs/CHEATS.md` has the detail, and the status line totals the codes
each way for the current selection.

This says nothing about whether a cheat's *value* suits your save. A code that
sets health to sixteen hearts draws sixteen hearts either way.

## Cartridges

**The full warning is in the [README](../README.md#cartridges-read-this-part),
and it is worth reading before you send anything to a cartridge.** The short of
it: identifying the right cheat file for a cartridge is your job, nothing here
can check it, and a GameShark code aimed at the wrong revision is a real write
into work RAM that can crash the game or end up in its save.

A cartridge is not a file on the card, so it never shows up in the game list.
The **Cartridges** entry in the systems pane is a list you keep yourself:
**Add cartridge...**, name it as the ROM is named so cheat files match, say
which system it is for, and it behaves like any other game from there.

Your cartridges are filed under **Game Boy** and **Game Boy Color** headings,
each showing how many are under it; a system you own nothing for is not shown
at all. The heading is a heading, not a game: selecting one leaves **Remove**
and **Move** greyed out, because there is nothing there to act on.

The system a cartridge is filed under is not cosmetic. It decides which folder
on the card the cheat file goes in, and the core's **Load Cheats** browser
opens on that folder, so a cartridge under the wrong heading writes its file
where nothing will look for it. It used to be assumed to be Game Boy Color,
which was right often enough to be quietly wrong the rest of the time, so the
Add dialog asks. **Move to...** refiles one afterwards and carries the
remembered cheat source with it, since correcting the system should not also
lose the file you picked. The file already written under the old system is left
where it is, exactly as **Remove** leaves it. The list is
`~/.config/pocket-cheats/cartridges.json`, outside the repo; which cheat file
each one uses is remembered alongside everything else, and **Change source...**
repoints it. **Remove** drops a cartridge from the list and forgets which file
it used, and leaves any cheat file already on the card alone.

**Send to Pocket** writes to `/Assets/<platform>/common/Cartridges/<name>.cht`.
It goes in its own folder so that the core's file browser opens on your
cartridges instead of a few hundred ROMs: in Play Cartridge mode the Pocket does
not auto-load a cheat file named after the cartridge, so you browse for it once
from the core menu and the slot remembers it.

Be careful which codes you send. You cannot check which revision a cartridge is
from the outside, and the two kinds of code fail differently when you guess
wrong. A Game Genie code carries a compare byte, so on the wrong revision it
never fires. A GameShark code has no such check: it is a real write to an
address that may hold something else entirely on that revision, and it can
corrupt a save. The status line warns when a cartridge selection contains
written codes, and `cheats/cht check --rom` verifies compare bytes
against a dump if you have one.

## How it decides things

**The file on the card is the state.** There is no separate database. Opening a
game reads the `.cht` already sitting next to the ROM and ticks those cheats, so
what you see is what the Pocket will do.

**Only ticked cheats are written.** The core reads the first 32 cheats in a file
whatever their enable flag says, so handing it a 100-cheat libretro file would
truncate before reaching the one you wanted. Writing just the selection avoids
the limit, and the bar above the status line shows how much of the store the
selection uses: it fills as you tick, ambers near 32 and turns red past it,
saying how many codes will not fit. It counts codes rather than cheats because
every cheat carries at least one code, so the code store always fills first.
Going over is otherwise silent: the core parses until the store is full and
ignores the rest, so the cheats past the limit load, read as enabled, and do
nothing.

**Cheats it does not recognise are kept.** If the card holds a cheat that is not
in the matched libretro file (hand-written, or from another source), it is shown
in green marked *already installed* and starts ticked, so saving cannot quietly
throw away work.

**Your own cheat files.** An update replaces the libretro database wholesale, so
anything added inside it is lost the next time you press Update. Put yours in
`~/.local/share/pocket-cheats/cht/` instead, which is outside it, named after
the ROM exactly as the ROM is named, and the picker finds them. They are searched first, so a file you
wrote wins an otherwise exact tie, and the source line marks it *(yours)*.

```sh
cheats/cht list
cheats/cht new "Zelda (USA) (Rev 2)" --from "Zelda (USA)"   # start from a stock file
cheats/cht add "Zelda (USA) (Rev 2)" "999 Rupees" 9199ADC6+9109AEC6
cheats/cht check "Zelda (USA) (Rev 2)" --rom /path/to/rom.gbc
```

`check --rom` is the one worth using on anything hand-entered: it verifies each
Game Genie compare byte against that ROM and says which bank it matches, so a
code copied from a site that targets a different revision is caught before it
reaches the card rather than silently never firing.

A remembered choice beats matching, so if a file of yours is not being picked
up, the source line will say *(pinned)*; **Change source...** repoints it.

**Matching prefers the same release.** Titles alone decide the match, which
leaves dozens of files tied for a popular game, so the region and variant tags
break the tie: a ROM tagged `(USA, Australia)` lands on the cheat file with the
same tags rather than on whichever name is shortest. **Change source...** picks a
different file and remembers it in `~/.config/pocket-cheats/prefs.json`.

Cheats whose codes are `XX`-style placeholders are greyed out and cannot be
ticked: they carry no usable value, and the core drops them.

**The whole file is listed, not the part the core would read.** The core takes
the first 32 codes, but that is a limit on what you can send, not on what you
can choose between: a libretro file may hold hundreds of cheats, and Pokemon
Red's holds 518. Reading the file through the core's own limits, which is what
this did at first, showed 3 of them. The status line warns if a selection
exceeds what the core can hold.

`romhacks/` folders are skipped. They hold pre-patched variants of a ROM that is
already in the list and match nothing in the cheat database, so they only add
duplicates. Nothing is hidden from the card, only from this tool; change
`SKIP_DIRS` in `card.py` to list them again.

## Safety

Writes go only to a directory that has both `Cores/` and `Platforms/`, so a muOS
or plain ROM card cannot be mistaken for a Pocket card. An existing cheat file is
copied to `.cht.bak` before being replaced, the new file is parsed back and
checked before the call returns, and the card is synced afterwards. Eject it
normally when you are done.
