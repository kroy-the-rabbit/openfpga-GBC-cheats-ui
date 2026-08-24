# Shared with the core

`chtparse.py` and `ggdecode.py` are **copies, kept byte-identical**. The
originals live in the `pocket-gbc` core repo, where `chtparse.py` is the
reference model that the RTL cheat parser is checked against over all 2456
Game Boy and Game Boy Color files in the libretro database. This app is only a
consumer of it.

So: fix a parser bug in the core repo, run its test suite, then copy the file
here. `make sync-check` compares the two byte for byte and says which have
drifted. It looks for the core repo at `../pocket-gbc`; `POCKET_CORE_REPO`
points it elsewhere.

They are copied rather than imported because the core repo is a fork of
`budude2/openfpga-GBC` and may be PR'd upstream, so this app cannot be a
dependency of it, and a checkout of one should not require the other.

Drift matters in one specific way: the picker decides what to show, and what
each cheat will do, by parsing files exactly as the core does. If the two
disagree, the app confidently shows something the hardware will not do.

The rest of this directory is host tooling that belongs with the app:

| | |
|---|---|
| `cht` | front end for your own cheat files (`list`, `new`, `add`, `check`) |
| `checkrom.py` | verify Game Genie compare bytes against a real ROM |
| `install.py` | the original command line installer, before the GUI existed |
| `init-db.sh` | fetch the libretro cheat database |
