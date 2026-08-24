# Cheat picker

A small desktop app for choosing which cheats go on the Pocket card.

```sh
make gui                              # or: tools/cheatgui/run.sh
tools/cheatgui/run.sh --list          # same data, printed, no window
tools/cheatgui/run.sh --list zelda -v # filtered, and every cheat listed
```

Set `POCKET_CARD=/path/to/card` to point the tool at an explicit directory
instead of searching the mounted volumes.

`run.sh` creates `tools/cheatgui/.venv` on first run. Everything used is in the
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

## What it shows

Three panes: the systems on the card, the games in the selected system, and the
cheats for the selected game. Tick the ones you want and press **Send to
Pocket**.

Only **Game Boy** and **Game Boy Color** are listed, because they are the only
systems whose core reads cheat files. A GBA or NES core on the same card ignores
them entirely, so offering checkboxes there would be a lie.

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

A cartridge is not a file on the card, so it never shows up in the game list.
The **Cartridges** entry in the systems pane is a list you keep yourself:
**Add cartridge...**, name it as the ROM is named so cheat files match, and it
behaves like any other game from there. The list is
`~/.config/pocket-cheats/cartridges.json`, outside the repo; which cheat file
each one uses is remembered alongside everything else, and **Change source...**
repoints it.

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
written codes, and `tools/cheats/cht check --rom` verifies compare bytes
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

**Your own cheat files.** The libretro database is a git submodule, so anything
added to it is lost on the next update. Put yours in
`~/.local/share/pocket-cheats/cht/` instead, named after the ROM exactly as the
ROM is named, and the picker finds them. They are searched first, so a file you
wrote wins an otherwise exact tie, and the source line marks it *(yours)*.

```sh
tools/cheats/cht list
tools/cheats/cht new "Zelda (USA) (Rev 2)" --from "Zelda (USA)"   # start from a stock file
tools/cheats/cht add "Zelda (USA) (Rev 2)" "999 Rupees" 9199ADC6+9109AEC6
tools/cheats/cht check "Zelda (USA) (Rev 2)" --rom /path/to/rom.gbc
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
