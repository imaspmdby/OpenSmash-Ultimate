#!/usr/bin/env bash
# The map's sufficiency test (2026-11-12): the replay check (save at fight frame 600, 60 frames, 3 replays) on a CPU
# against CPU match, a load putting back only what SSBU_RB_ONLY_SITES names (or everything without it); judged by the
# fight hash of every replayed frame and by the reader (a dump numbered by logic frame, each replay against the first
# pass: match.py passes).   research/tools/suffice.sh <out> <match in research/matrix/colour.txt> [VAR=value ...]
set -u
here="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$here"
out="$1"; m="$2"; shift 2
envs=(--env SSBU_RB=1 --env SSBU_RB_VERIFY=600,60,3 --env SSBU_STATE_DUMP_LF=1); for e in "$@"; do envs+=(--env "$e"); done
deps/python/python.exe research/tools/matrix.py research/matrix/colour.txt --only "$m" --out "$out" --ring none --hash --state 1,590,670 \
    --timeout 600 --end 25s "${envs[@]}" | grep -E "^\["
r="research/runs/$out/$m"
grep -hE "fight hash: (replay|FIRST)|ONLY_SITES|host exception|watchdog" "$r/run.log" | head -8 | cut -c1-200
deps/python/python.exe research/tools/match.py passes "$r/state.bin"
rm -f "$r/state.bin"
