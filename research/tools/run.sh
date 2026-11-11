#!/usr/bin/env bash
# One test run of the game, isolated: research/tools/run.sh <name> <timeout seconds> [VAR=value ...]
# Each run gets a fresh copy of research/runs/save_template as its data root (the real save is never used),
# its own folder research/runs/<name>/ with the log (run.log) and whatever the switches write there.
# The game is headless (window off screen). Extra VAR=value arguments are exported for the game.
set -u
here="$(cd "$(dirname "$0")/../.." && pwd)"
name="$1"; limit="$2"; shift 2
run="$here/research/runs/$name"
rm -rf "$run" && mkdir -p "$run"
cp -R "$here/research/runs/save_template/save" "$run/save"
export SSBU_DATA_ROOT="$(cygpath -w "$run" 2>/dev/null || echo "$run")"
export SSBU_HEADLESS=1 SSBU_SKIP_MOVIES=1
for kv in "$@"; do export "$kv"; done
cd "$here"
start=$(date +%s)
timeout --kill-after=10 "$limit" ./build/ssbu.exe dump/modules > "$run/run.log" 2>&1
code=$?
echo "$name: exit code $code after $(( $(date +%s) - start )) s (124 = stopped at the time limit)" | tee "$run/exit.txt"
