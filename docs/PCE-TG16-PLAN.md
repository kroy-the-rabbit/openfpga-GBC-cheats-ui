# PC Engine / TurboGrafx-16: what to expect from the core

**Status: the core is in progress and there is nothing to write against yet.**
This document exists so the app can be shaped for it now rather than retrofitted
later, the way Game Boy Advance had to be. Core work lives in
`~/Desktop/repos/pocket-pcengine`, forked from `vanfanel/openfpga-pcengine`,
with its own plan in that repo's `docs/PLAN.md`.

## The short version, and the one surprise

PC Engine is the third system this app will write for and the least like the
first two. **Every published PC Engine cheat is a RAM poke. None is a ROM
patch.** There is no Game Genie for this machine in the libretro database.

That inverts the mental model the Game Boy work built. On GB/GBC the read
override is the primary mechanism and the poker is the addition; here the
override is nearly dead weight and the poker *is* the feature. Wherever the app
distinguishes the two, PC Engine has only one value.

Evidence: all 397 files in the libretro directory were listed, the format split
counted, and a dozen non-Rumbles files read in full. Every code address sampled
falls inside `0x1F0000`-`0x1F1FFF`, which is the 8KB work RAM at bank `$F8`. No
sampled address lands in ROM space. If a counterexample turns up, this section
is the one to revisit.

---

## 1. Platform contract (`card.py`)

```python
SUPPORTED = {
    "gb":  "Nintendo - Game Boy",
    "gbc": "Nintendo - Game Boy Color",
    "gba": "Nintendo - Game Boy Advance",
    "pce": "NEC - PC Engine - TurboGrafx 16",   # exact libretro directory name
}
ROM_EXT = {".gb", ".gbc", ".gba", ".pce"}
DISPLAY = {..., "pce": "PC Engine"}
```

`Game.cht_path` needs no change: the cheat slot's filename is cloned from slot 0
with the extension appended, so it is `<rom>.pce.cht` beside the ROM, exactly
the convention the Game Boy cores use.

**Three things deliberately absent:**

* **`.sgx` is not in `ROM_EXT`.** The core drops SuperGrafx entirely to buy the
  ALM headroom the cheat engine needs. A `.sgx` file on the card will not run
  correctly, so offering to write cheats for one would be a lie.
* **`NEC - PC Engine SuperGrafx`** is a real libretro directory. Do not map it.
* **`NEC - PC Engine CD - TurboGrafx-CD`** is also real. The core does not
  support CD, and CD support is not planned.

## 2. Database contract (`db.py`)

`DIRS` gains `"NEC - PC Engine - TurboGrafx 16"`. The directory holds **397
files**: 350 ordinary ones and 47 named `(Rumbles)`, which are duplicate entries
for the same games carrying rumble metadata (see §3, form B).

One incidental break: the missing-directory report trims names with
`d.replace("Nintendo - ", "")`. That leaves `NEC - PC Engine - TurboGrafx 16`
untouched and the line gets long. Generalise the trim to drop any
`"<manufacturer> - "` prefix rather than special-casing NEC.

## 3. Code format (`cheatfile.py`)

Two forms live in the same directory, and a file uses one or the other.

**Form A, 350 files.** The Beetle PCE style, a hex CPU address and a hex byte:

```
cheat0_desc = "Infinite Energy"
cheat0_code = "1f1548:64"
cheat0_enable = false
```

`1f1548` is a full 21-bit CPU address. `64` is the byte to write.

**Form B, 47 files, all named `(Rumbles)`.** RetroArch's native cheat-search
form, with no `_code` at all:

```
cheat0_address = "1412"
cheat0_value = "1"
cheat0_cheat_type = "1"
cheat0_memory_search_size = "3"
cheat0_big_endian = "false"
cheat0_handler = "1"
cheat0_rumble_type = "0"          # ... and eight more rumble_* keys
```

Here `cheat0_address` is a **decimal offset into work RAM**, not a CPU address,
and `memory_search_size = 3` means one byte. The conversion is:

    cpu_address = 0x1F0000 + int(cheat0_address)

Checked: `1412` decimal is `0x584`, giving `0x1F0584`, inside work RAM. The
`rumble_*` keys are meaningless to a Pocket and should be dropped, not carried.

**So PC Engine is decodable**, unlike Game Boy Advance. `DECODED` gains `"pce"`
once a decoder exists. Until then it must be carried verbatim under the same
rule GBA follows, because form B handed to the Game Boy parser would produce
plausible nonsense in exactly the way `cheatfile.py`'s docstring warns about.

**`LIMITS` stays absent for now.** The Game Boy figures come from
`cheatcodes.sv`. The PC Engine ceiling depends on a poker table that has not
been written, and putting a number on screen that nothing checks is the thing
that module explicitly refuses to do.

## 4. The consequence for the UI

The **Applied** column exists to separate Game Genie codes from GameShark ones,
because on a cartridge that distinction is the difference between safe and
dangerous. On PC Engine every code is the dangerous kind, and there is no
cartridge to make it worse.

Do not render a two-valued column with one value in it. Either collapse the
column for `pce` or state the single fact once, above the list. The
save-corruption warning in the README still applies in full and arguably more
so, since a RAM poke is precisely the failure mode it describes.

## 5. Core install contract (`core.py`)

```python
Core("kroy.PCE", "pce", "PC Engine", "kroy.PCE_", bios=())
```

Two changes this needs from the current code:

* **`REPO` has to move onto `Core`.** It is a module-level constant today,
  correct while one release covered both Game Boy systems. PC Engine ships from
  its own repository. Game Boy Advance will need the same change, so doing it
  here unblocks both.
* **`bios` is empty, and that has to be a supported state.** The PC Engine has
  no boot ROM. The path that names missing ROMs must treat an empty tuple as
  "nothing required" rather than "nothing found", and the core bar must not
  report a card as incomplete because of it.

**Directory naming.** Upstream ships as `agg23.PC Engine`, with a space in the
directory name. The fork renames to `kroy.PCE`, both to match `kroy.GBC` and so
the app never handles the space. A card may still carry the upstream core
alongside the fork; `installed()` looks for known ids, so it will simply not see
it, which is the right behaviour.

## 6. What the core will and will not do

| | |
|---|---|
| ROM source | **SD card only** |
| Cartridge | **never.** `cartridge_adapter` stays `-1` |
| SuperGrafx | removed |
| CD | not supported upstream either |
| Cheat file | `<rom>.pce.cht` beside the ROM |
| Mechanism | RAM poke into 8KB work RAM at `0x1F0000` |
| On-screen cheat list | planned, but explicitly optional |

The cartridge point matters more than it looks. Analogue does ship a
TurboGrafx-16 adapter and openFPGA cores genuinely can read physical carts, as
this app's own Game Boy support proves. The PC Engine core still will not: the
adapter's signalling is undocumented and a HuCard needs more lines than the
Game Boy scheme spends. So for `pce`, every cartridge path in this app is dead
code, not merely unused. The red status line, the revision warnings and the
bit-9 browsed-filename fallback should be **skipped for this platform**, not
left to evaluate to nothing.

## 7. Open items

1. Are there PC Engine cheats in the wild, outside the libretro database, that
   patch ROM rather than RAM? If not, the core's existing Game Genie block
   could be dropped for the ALMs, and this app never needs the distinction.
2. What poker table size will the core carry? That fixes `LIMITS`.
3. Do any form B files disagree with their form A twin for the same game? The
   47 `(Rumbles)` files look like derived duplicates; if they are, the app
   should prefer one and not show both.
4. Does the Pocket's own PC Engine platform JSON name the system "PC Engine" or
   "TurboGrafx-16"? `DISPLAY` is only the pre-card guess, but it should match
   what the card says for the common case. Upstream's `pkg/Platforms/pce.json`
   says `"PC Engine"`.
