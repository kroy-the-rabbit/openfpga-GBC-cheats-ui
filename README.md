# Pocket cheat picker

A small desktop app for choosing which cheats go on an Analogue Pocket SD card,
for the Game Boy and Game Boy Color cores.

```sh
make cheatdb          # once: fetch the libretro cheat database
make gui              # or: cheatgui/run.sh
make list ARGS=zelda  # same data, printed, no window
```

`run.sh` creates `cheatgui/.venv` on first run. Everything used is in the
Python standard library, so the venv stays empty; it exists so nothing is ever
installed into the host Python.

Full guide: [docs/CHEATGUI.md](docs/CHEATGUI.md).

## What it does

Three panes: the systems on the card, the games in each, and the cheats for the
selected game. Tick what you want and press **Send to Pocket**. The file next to
the ROM *is* the state, so what you see is what the handheld will do.

Cartridges get their own pane, since they are not files on the card: keep a list
of the ones you own and prepare a cheat file for each.

Each cheat also shows how the core applies it, because the two ways differ. A
GameShark code is written into RAM once a frame; a Game Genie code overrides the
CPU's read, which is what a ROM patch needs. That distinction decides which
codes are safe on a cartridge whose revision you cannot check.

## Why it is not in the core repo

The core lives in [`pocket-gbc`](../pocket-gbc), a fork of
`budude2/openfpga-GBC` that may be PR'd upstream. A desktop app that reads SD
cards has no business in that diff. The two share a cheat file parser; see
[cheats/README.md](cheats/README.md) for how that copy is kept honest.

## Requires

Python 3.10 or newer with tkinter (`sudo dnf install python3-tkinter` on
Fedora), and a Pocket SD card with `Cores/` and `Platforms/` on it.
