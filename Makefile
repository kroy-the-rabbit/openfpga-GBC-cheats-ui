# SPDX-License-Identifier: GPL-3.0-or-later
PY  ?= python3
VENV = cheatgui/.venv/bin/python

.PHONY: gui list cheatdb sync-check test dist clean help

help:                     ## this list
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

gui:                      ## the picker
	cheatgui/run.sh

list:                     ## same data, printed, no window
	cheatgui/run.sh --list $(ARGS)

cheatdb:                  ## the cheat database as a git submodule
	cheats/init-db.sh

sync-check:               ## are the shared parsers still in step with the core?
	@cheats/sync-check.sh

# The GUI tests drive real widgets, so they need a display. Under a headless
# session, run them as: xvfb-run -a make test
test: sync-check          ## parser self-test and the GUI tests
	$(PY) -m compileall -q cheatgui cheats tests
	$(PY) cheats/ggdecode.py --test
	$(PY) -W ignore::ResourceWarning -m unittest discover -s tests -v

# PyInstaller is the one thing the app itself does not need, so it goes in a
# venv of its own rather than into the system Python, which on most
# distributions now refuses to be written to at all.
BUILDVENV = build/venv

dist: $(BUILDVENV)/bin/pyinstaller   ## build the binary for this platform
	$(BUILDVENV)/bin/pyinstaller --clean --noconfirm \
		--distpath dist --workpath build/pyi packaging/pocket-cheats.spec
	@ls -l dist/

$(BUILDVENV)/bin/pyinstaller:
	$(PY) -m venv $(BUILDVENV)
	$(BUILDVENV)/bin/pip install --quiet --upgrade pip pyinstaller

clean:                    ## remove build output
	rm -rf build dist
