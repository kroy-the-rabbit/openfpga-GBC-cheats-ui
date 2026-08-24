#!/usr/bin/env bash
# chtparse.py and ggdecode.py are copies. The originals live in the core repo,
# where chtparse is the reference model the RTL is verified against over the
# whole libretro database; this app is only a consumer of it. If the two drift,
# the picker will show something the core will not do.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CORE="${POCKET_CORE_REPO:-$HERE/../../pocket-gbc}"

if [[ ! -d "$CORE/tools/cheats" ]]; then
  echo "core repo not found at $CORE, skipping (set POCKET_CORE_REPO)"
  exit 0
fi
rc=0
for f in chtparse.py ggdecode.py; do
  if cmp -s "$HERE/$f" "$CORE/tools/cheats/$f"; then
    echo "  in step: $f"
  else
    echo "  DRIFTED: $f  (core copy is authoritative)"
    echo "           diff $HERE/$f $CORE/tools/cheats/$f"
    rc=1
  fi
done
exit $rc
