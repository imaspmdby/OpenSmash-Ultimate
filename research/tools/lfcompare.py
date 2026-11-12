"""Two fight hash logs compared by logic frame: a run with rollbacks that replayed corrected inputs against a run without.

    deps/python/python.exe research/tools/lfcompare.py <reference fight_hash.txt> <test fight_hash.txt>

The logs of SSBU_RB_LF_INPUT runs (SSBU_FIGHT_HASH, hle_fight_test.c): each line "F <frame> e <fighter> st .. mot .. mf ..
x .. y .. dmg .. rngcalls .. rng .. H <running hash> (...) L <logic frame from the fight's first read of player 1>". A frame run again appears more than once; its last line is the one that counts (the
state the fight went on from). Compared: every (logic frame, fighter) of both logs, up to the last logic frame the
test log ran again (frames after the ring's last load kept their wrong first-pass input). Prints the frames compared,
how many differ, the first difference, and the frames the test ran again.
"""
import sys


def load(path):
    last, seen = {}, {}
    for line in open(path, errors="replace"):
        p = line.split()
        if len(p) < 4 or p[0] != "F" or "L" not in p:
            continue
        rel = int(p[p.index("L") + 1])
        if rel < 0:
            continue
        key = (rel, int(p[3]))   # (logic frame, fighter entry)
        # (the frame's own values: e st mot mf x y dmg rngcalls rng; not the fight frame count, which a load does not
        # put back, nor H, which hle_fight_test.c's log runs over the whole file, frames run again included)
        last[key] = " ".join(p[2:20])
        seen[key] = seen.get(key, 0) + 1
    return last, seen


def main():
    ref, _ = load(sys.argv[1])
    test, seen = load(sys.argv[2])
    rerun = sorted({k[0] for k, n in seen.items() if n > 1})
    if not rerun:
        print("the test log ran no frame again")
        return 2
    end = rerun[-1]
    keys = sorted(k for k in ref if k in test and k[0] <= end)
    diff = [k for k in keys if ref[k] != test[k]]
    print(f"logic frames 0-{end} compared ({len(keys)} fighter-frames); frames run again in the test: {len(rerun)} "
          f"(from {rerun[0]} to {end}); different: {len(diff)}")
    if diff:
        k = diff[0]
        print(f"  first difference at logic frame {k[0]}, fighter {k[1]}:\n    reference {ref[k][:160]}\n    test      {test[k][:160]}")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
