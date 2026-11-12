#!/usr/bin/env bash
# A background series: long, varied matches through the reader and the automatic check, one dump on disk per game.
#   research/tools/series.sh <matrix> <out name> <fight length, e.g. 180s> [<jobs>] [matrix.py arguments...]
# Each match of the matrix runs alone (matrix.py --only), with the state dump every 20 frames, SSBU_VERIFY_FIELDS and
# the fight hash; then reader.py --verify --hash compares every named field with the game's getters and the fighters'
# values with the fight hash log, and the dump is removed. stock=99 (a fight that ends waits on the results screen).
# One line a match in research/runs/<out>/series.txt: name, verdict, values equal / different.
set -u
here="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$here"
matrix="$1"; out="$2"; len="$3"; jobs="${4:-2}"; shift 3; [ $# -gt 0 ] && shift
extra=("$@")
py=deps/python/python.exe
$py research/tools/fields.py research/map/reference_types.json --verify-list research/map/verify_getters.txt > /dev/null || exit 2
mkdir -p "research/runs/$out"
export here out len py matrix
export EXTRA="${extra[*]:-}"
one() {
    n="$1"; cd "$here"
    v="$(cygpath -w research/map/verify_getters.txt)"; sp="$(cygpath -w research/map/state_paths.txt)"
    $py research/tools/matrix.py "$matrix" --only "$n" --out "$out" --ring none --hash --state 20 --timeout 1800 \
        --end "$len" --override stock=99 --env "SSBU_VERIFY_FIELDS=$v" --env "SSBU_STATE_PATHS=$sp" $EXTRA > "research/runs/$out/$n.matrix.log" 2>&1
    run="research/runs/$out/$n"
    verdict="$(grep -oE '^\[1/1\] [^:]+: [A-Z/-]+' "research/runs/$out/$n.matrix.log" | awk '{print $3}')"
    if [ -f "$run/state.bin" ]; then
        $py research/tools/reader.py "$run/state.bin" --hash "$run/fight_hash.txt" --verify research/map/verify_getters.txt.json > "$run/reader.txt" 2>&1
        rc=$?
        rm -f "$run/state.bin"
        eq="$(grep -m1 'automatic check' "$run/reader.txt" | cut -c1-200)"
        hs="hash cross-check: $(grep -A8 'cross-check with the game' "$run/reader.txt" | grep -cE 'different *[1-9]|DIFFERENT') lines differing"
        echo "$n | $verdict | reader rc $rc | $eq | $hs" >> "research/runs/$out/series.txt"
    else
        echo "$n | $verdict | no dump" >> "research/runs/$out/series.txt"
    fi
}
export -f one
$py - "$matrix" <<'PY' | xargs -P "$jobs" -I{} bash -c 'one {}'
import sys
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.split("#", 1)[0].strip()
    if line:
        print(line.split("|")[0].strip())
PY
echo "series done: research/runs/$out/series.txt"
