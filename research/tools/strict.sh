#!/usr/bin/env bash
# One strict-oracle experiment on one match: trace frames 300-539 in build-trace, then upstream's replay check at
# fight frame 600 (60 frames, 3 replays), then research/tools/oracle.py.
#   research/tools/strict.sh <out name> <match name in research/matrix/trace.txt> [VAR=value ...]
# e.g. research/tools/strict.sh e1_nonsim1 base_mario_dk SSBU_RB_SKIP_NONSIM=1
# One at a time: the replay check writes build\rb_verify_*.txt at a fixed path.
set -u
here="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$here"
out="$1"; match="$2"; shift 2
cats="$(cygpath -w research/code_cats.bin)"
envs=(--env "SSBU_MEMTRACE=300,240,research/runs/$out/{name}/mt.bin" --env "SSBU_MEMTRACE_CATS=$cats" --env SSBU_RB=1
      --env SSBU_RB_VERIFY=600,60,3)
for kv in "$@"; do envs+=(--env "$kv"); done
rm -f build/rb_verify_*.txt
deps/python/python.exe research/tools/matrix.py research/matrix/trace.txt --out "$out" --only "$match" --exe build-trace \
    --ring none --hash --probe --timeout 1500 "${envs[@]}" | head -1
run="research/runs/$out/$match"
mkdir -p "$run/verify" && mv build/rb_verify_*.txt "$run/verify/" 2>/dev/null
grep -E 'SKIP_NONSIM|fight hash: (replay|FIRST)' "$run/run.log" | cut -c1-200
deps/python/python.exe research/tools/oracle.py "$run" --show 8 | cut -c1-240
