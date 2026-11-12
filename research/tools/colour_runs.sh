#!/usr/bin/env bash
# The colouring traces (build-trace): research/tools/colour_runs.sh <out> <first frame> <frames> <fight length> [--only a,b] [matrix args]
set -u
here="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$here"
out="$1"; first="$2"; n="$3"; len="$4"; shift 4
[ build-trace/ssbu.map -nt research/code_cats.bin ] && { echo "code_cats.bin is older than build-trace's map: run code_cats.py first"; exit 2; }
cats="$(cygpath -w research/code_cats.bin)"
deps/python/python.exe research/tools/matrix.py research/matrix/colour.txt --out "$out" --exe build-trace --probe --ring none \
    --hash --state 600 --timeout 2400 --end "$len" --override stock=99 \
    --env "SSBU_MEMTRACE=$first,$n,research/runs/$out/{name}/mt.bin" --env "SSBU_MEMTRACE_CATS=$cats" "$@"
