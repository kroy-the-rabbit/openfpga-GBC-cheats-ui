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

dist:                     ## build the binary for this platform
	$(PY) -m pip install --quiet --upgrade pyinstaller
	$(PY) -m PyInstaller --clean --noconfirm \
		--distpath dist --workpath build/pyi packaging/pocket-cheats.spec
	@ls -l dist/

clean:                    ## remove build output
	rm -rf build dist
