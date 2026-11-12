#!/usr/bin/env bash
# The automatic check of every named field: run it before and after any change to the field dictionary.
#   research/tools/verify_fields.sh [out name]
# 1. the getters' list from the current dictionary (fields.py --verify-list);
# 2. seven matches with the state dump and SSBU_VERIFY_FIELDS: fighters, weapons, Castle 64, four players, a
#    fighter's item (Diddy Kong's banana), a stage item handed to player 1 (SSBU_GIVE_ITEM) and items falling on the
#    stage by the rule (SSBU_RULE_POKE);
# 3. reader.py --verify --hash on each: every named field of every object against the game's own getter called at
#    the same moment, and the fighters' status / motion / position / damage against the fight hash log.
# Exit status 0 only when no value differs anywhere. The raw dumps are removed at the end (1-2 GB each).
set -u
here="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$here"
out="${1:-verify_fields}"
py=deps/python/python.exe
$py research/tools/fields.py research/map/reference_types.json --verify-list research/map/verify_getters.txt || exit 2
v="$(cygpath -w research/map/verify_getters.txt)"
sp="$(cygpath -w research/map/state_paths.txt)"   # (the blocks behind pointers that the fields of argprobe.py need)
common=(--out "$out" --ring none --hash --state 20 --timeout 900 --env "SSBU_VERIFY_FIELDS=$v" --env "SSBU_STATE_PATHS=$sp")
$py research/tools/matrix.py research/matrix/v1.txt --only base_mario_dk,proj_link_samus,hazards_castle64,four_players --jobs 2 "${common[@]}" | grep -E '^\['
$py research/tools/matrix.py research/matrix/items.txt --only diddy_banana --seq downb "${common[@]}" | grep -E '^\['
$py research/tools/matrix.py research/matrix/give.txt "${common[@]}" --env SSBU_GIVE_ITEM=600,5,240 | grep -E '^\['
# items that fall on the stage by the rule (the rule header's item list set: SSBU_RULE_POKE, hle_fight_test.c)
$py research/tools/matrix.py research/matrix/spawn.txt --only spawn_mario_dk "${common[@]}" --end 40s --env SSBU_RULE_POKE=58:ffffffffffffffffffffff | grep -E '^\['
bad=0
for n in base_mario_dk proj_link_samus hazards_castle64 four_players diddy_banana give_base spawn_mario_dk; do
    run="research/runs/$out/$n"
    echo "== $n"
    $py research/tools/reader.py "$run/state.bin" --hash "$run/fight_hash.txt" --verify research/map/verify_getters.txt.json \
        | grep -E 'automatic check|behind pointers|DIFFERENT|reader 0x|different +[1-9]' | cut -c1-230
    [ "${PIPESTATUS[0]}" = 0 ] || bad=1
    rm -f "$run/state.bin"
done
[ "$bad" = 0 ] && echo "verify_fields: PASS" || echo "verify_fields: FAIL"
exit "$bad"
