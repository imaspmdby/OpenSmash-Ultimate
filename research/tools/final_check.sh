#!/usr/bin/env bash
# The checks of the end of a work session (2026-11-12): the normal build, the rollback oracles without pruning, and a
# determinism gate that does not depend on host timing (CPU against CPU) beside the repo's scripted gate.
#   research/tools/final_check.sh <out prefix>
set -u
here="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$here"
o="${1:-final}"
py=deps/python/python.exe
echo "== 1. normal build"
$py tools/build_game.py --game "C:/Users/Lucas/Documents/SSBU_bis" --keys "C:/Users/Lucas/Documents/prod_keys2" --firmware "C:/Users/Lucas/Downloads/Firmware.23.0.1_" 2>&1 | grep -E "linked .*ssbu.exe|error:" | grep -v "lld-link\|clang-cl"
echo "== 2. the repo's gate (scripted player 1) and the rollback oracle (ring 600,10,4,50, full savestate)"
bash research/tools/baseline.sh 2>&1 | grep -E "gate:|ring test done"
echo "== 3. the control without pruning (E0: ring 600,6,8,150 rotated, hidden, 60 s, stock 99), 3 matches"
$py research/tools/matrix.py research/matrix/v1.txt --only base_mario_dk,proj_link_samus,hazards_castle64 --out ${o}_e0 --jobs 2 --ring 600,6,8,150 --end 60s --override stock=99 --timeout 600 --env SSBU_RB_RING_HIDE=1 --env SSBU_RB_RING_ROTATE=1 | grep "^\["
echo "== 4. a determinism gate CPU against CPU (Castle 64, hazards): two runs, the same fight hash log"
for r in a b; do $py research/tools/matrix.py research/matrix/colour.txt --only castle_cpu --out ${o}_gate_$r --ring none --hash --end 30s --timeout 400 | grep "^\["; done
cmp research/runs/${o}_gate_a/castle_cpu/fight_hash.txt research/runs/${o}_gate_b/castle_cpu/fight_hash.txt && echo "CPU gate: identical ($(wc -l < research/runs/${o}_gate_a/castle_cpu/fight_hash.txt) lines)"
