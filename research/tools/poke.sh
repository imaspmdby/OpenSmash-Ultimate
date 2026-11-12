#!/usr/bin/env bash
# A sustained perturbation test: research/tools/poke.sh <out> <match> <fight length> [VAR=value ...]
# One run of research/matrix/colour.txt's <match> on the normal build with the state dump every 10 frames and the fight
# hash; judge it against a control run of the same match with match.py compare and the fight hash log.
set -u
here="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$here"
out="$1"; m="$2"; len="$3"; shift 3
envs=(); for e in "$@"; do envs+=(--env "$e"); done
deps/python/python.exe research/tools/matrix.py research/matrix/colour.txt --only "$m" --out "$out" --ring none --hash --state 10 \
    --timeout 900 --end "$len" --override stock=99 "${envs[@]}" | grep -E "^\["
