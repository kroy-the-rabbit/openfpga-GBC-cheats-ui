PY = cheatgui/.venv/bin/python

.PHONY: gui list cheatdb sync-check test

gui:                      ## the picker
	cheatgui/run.sh

list:                     ## same data, printed, no window
	cheatgui/run.sh --list $(ARGS)

cheatdb:                  ## fetch the libretro cheat database
	cheats/init-db.sh

sync-check:               ## are the shared parsers still in step with the core?
	@cheats/sync-check.sh

test: sync-check
	$(PY) cheats/ggdecode.py --test
