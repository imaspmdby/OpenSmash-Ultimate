#!/usr/bin/env bash
# Phase 0 baseline: (1) the repo's determinism gate (two identical runs, same fight hash log) and
# (2) the offline rollback oracle (SSBU_RB_RING: loads 4 frames back, every re-run frame's fight hash
# must equal its first pass). Usage: research/tools/baseline.sh [match settings for SSBU_DEBUG_MATCH]
set -u
here="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$here"
match="${1:-p1=mario,p2=donkey,p2=cpu,cpu=3,stage=end,form=normal,stock=3,items=off}"
seq="$(cat research/seq/gate.seq)"
common=(SSBU_SPEED=0 SSBU_FIXED_SEED=1 SSBU_DETERMINISTIC=1 SSBU_DEBUG_END=20s "SSBU_DEBUG_MATCH=$match" "SSBU_SEQ=$seq")
fh() { cygpath -w "research/runs/$1.fh.txt"; }
for r in gate1 gate2; do bash research/tools/run.sh "$r" 240 "${common[@]}" "SSBU_FIGHT_HASH=$(fh $r)"; done
deps/python/python.exe tools/dev/fight_hash_diff.py research/runs/gate1.fh.txt research/runs/gate2.fh.txt
echo "gate: fight_hash_diff exit $?"
bash research/tools/run.sh ring 300 "${common[@]}" SSBU_RB=1 SSBU_RB_RING=600,10,4,50
grep -E '\[rb\] (ring test done|state map: on)' research/runs/ring/run.log
