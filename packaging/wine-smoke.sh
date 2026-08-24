#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Start the Windows build under Wine on a virtual display, give it time to draw,
# and report whether it is still alive with a window. Screenshots land in /out.
#
#   wine-smoke <exe> [seconds]
set -uo pipefail
EXE="${1:?usage: wine-smoke <exe> [seconds]}"
WAIT="${2:-25}"
OUT=/out

Xvfb :99 -screen 0 1600x900x24 >/tmp/xvfb.log 2>&1 &
sleep 3
export DISPLAY=:99

echo "wine:  $(wine --version)"
echo "exe:   $EXE"
echo "--- starting ---"
wine "$EXE" >/tmp/wine.log 2>&1 &
WINEPID=$!

for i in $(seq 1 "$WAIT"); do
  sleep 1
  if ! kill -0 "$WINEPID" 2>/dev/null; then
    echo "the launcher exited after ${i}s"
    break
  fi
done

# Wine's own process tree is what matters: the launcher can return while the
# app keeps running under wineserver.
echo "--- processes ---"
ps -eo comm | grep -iE "pocket|wine" | sort | uniq -c | sed 's/^/  /'

RUNNING=no
if pgrep -f "pocket-cheats" >/dev/null 2>&1; then RUNNING=yes; fi

mkdir -p "$OUT"
if import -window root -display :99 "$OUT/wine-screenshot.png" 2>/dev/null; then
  echo "--- screenshot: $OUT/wine-screenshot.png ---"
  identify "$OUT/wine-screenshot.png" 2>/dev/null | sed 's/^/  /'
  # A window that drew something is not a uniform field of the root colour.
  COLOURS=$(convert "$OUT/wine-screenshot.png" -format %k info: 2>/dev/null || echo 0)
  echo "  distinct colours: $COLOURS"
fi

echo "--- wine output ---"
sed 's/^/  /' /tmp/wine.log | head -40
echo "--- verdict ---"
echo "app process alive: $RUNNING"
[ "$RUNNING" = "yes" ]
