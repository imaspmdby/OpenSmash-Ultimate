"""The judge against a reference with no rollback (2026-11-13): a run with loads is compared, logic frame by logic
frame, to another launch of the same match that never loaded anything. (The ring's own check compares a frame run
again with its first pass in the same launch: both sides ran after partial loads, so it shows the run agrees with
itself, not that it is the fight that would have been.)

    deps/python/python.exe research/tools/refjudge.py digest <run folder>
    deps/python/python.exe research/tools/refjudge.py compare <reference run folder> <test run folder> [--from F] [--to F]

digest: <run>/fight_hash.txt (SSBU_FIGHT_HASH with SSBU_FIGHT_HASH_LF=1: each line ends with "L <logic frame>") and
<run>/state.bin (SSBU_STATE_DUMP with SSBU_STATE_DUMP_LF=1) are reduced to <run>/digest.pkl: for each logic frame the
LAST line of each fighter and the LAST dump of each object (the state the fight went on from; a frame run again
appears several times), each module of each object as (number of values, hash of the values). The dump can then go.
compare: every logic frame both digests hold, between --from and --to. Prints the frames compared, the hash lines
equal and different, the reader's values equal and different (by module: a module that differs counts all its
values as different), the first difference of each. Exit 0 when nothing differs and something was compared.
"""
import hashlib
import os
import pickle
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def hash_lines(path):
    last, seen = {}, {}
    for line in open(path, errors="replace"):
        p = line.split()
        if len(p) < 4 or p[0] != "F" or "L" not in p:
            continue
        key = (int(p[p.index("L") + 1]), int(p[3]))
        last[key] = " ".join(p[4:20])   # (st mot mf x y dmg rngcalls rng: not F, which a load does not put back, nor H)
        seen[key] = seen.get(key, 0) + 1
    return last, sum(1 for n in seen.values() if n > 1)


def val(v):
    return struct.pack("<f", v) if isinstance(v, float) else repr(v).encode()


def dump_digest(path):
    import match
    import reader
    rd = reader.Reader()
    out, again = {}, 0
    for f, objs in match.by_frame(path, rd):
        if f in out:
            again += 1
        fr = {}
        for i, d in objs.items():
            for mod, vals in d["modules"].items():
                h = hashlib.md5()
                for k in sorted(vals, key=str):
                    h.update(str(k).encode() + b"=" + val(vals[k]) + b";")
                fr[(i, d["category"], mod)] = (len(vals), h.digest()[:8])
        out[f] = fr
    return out, again


def digest(run):
    lines, again_h = hash_lines(os.path.join(run, "fight_hash.txt"))
    dump = os.path.join(run, "state.bin")
    frames, again_d = dump_digest(dump) if os.path.exists(dump) else ({}, 0)
    d = {"lines": lines, "frames": frames, "again_hash": again_h, "again_dump": again_d}
    pickle.dump(d, open(os.path.join(run, "digest.pkl"), "wb"))
    lf = sorted({k[0] for k in lines})
    print(f"digest: {len(lines)} fighter-frames (logic frames {lf[0] if lf else '-'}-{lf[-1] if lf else '-'}, {again_h} run again); "
          f"dump: {len(frames)} frames ({min(frames) if frames else '-'}-{max(frames) if frames else '-'}), {again_d} frame dumps run again, "
          f"{sum(n for fr in frames.values() for n, _ in fr.values())} values")
    return d


def load(run):
    p = os.path.join(run, "digest.pkl")
    return pickle.load(open(p, "rb")) if os.path.exists(p) else digest(run)


def compare(ref, test, lo=0, hi=1 << 60):
    a, b = load(ref), load(test)
    keys = sorted(k for k in a["lines"] if k in b["lines"] and lo <= k[0] <= hi)
    bad = [k for k in keys if a["lines"][k] != b["lines"][k]]
    res = {"hash_frames": len(keys), "hash_different": len(bad), "hash_first": bad[0][0] if bad else None,
           "again_hash": b["again_hash"], "again_dump": b["again_dump"]}
    print(f"hash lines: logic frames {keys[0][0] if keys else '-'}-{keys[-1][0] if keys else '-'}, {len(keys)} fighter-frames compared; "
          f"different: {len(bad)}" + (f"; first at logic frame {bad[0][0]}, fighter {bad[0][1]}:\n    reference {a['lines'][bad[0]]}\n"
                                      f"    test      {b['lines'][bad[0]]}" if bad else ""))
    fr = sorted(f for f in a["frames"] if f in b["frames"] and lo <= f <= hi)
    eq = ne = only = 0
    first, mods = None, {}
    # (an object the dump saw in one run only, at no frame of the other, is not compared and is counted apart: the dump
    # finds stage objects when a script asks for them, and two launches of the same fight do not always catch them)
    ids_a = {k[0] for f in fr for k in a["frames"][f]}
    ids_b = {k[0] for f in fr for k in b["frames"][f]}
    skipped = ids_a ^ ids_b
    for f in fr:
        x, y = a["frames"][f], b["frames"][f]
        for k in set(x) | set(y):
            if k[0] in skipped:
                continue
            if k not in x or k not in y:
                only += 1
                first = first if first is not None else (f, k[1], k[2], "in one run only")
            elif x[k] == y[k]:
                eq += x[k][0]
            else:
                ne += max(x[k][0], y[k][0])
                mods[(k[1], k[2])] = mods.get((k[1], k[2]), 0) + 1
                first = first if first is not None else (f, k[1], k[2], "differs")
    res["objects_not_compared"] = len(skipped)
    # (only stage objects, category 3, may be missed by one dump: any other object in one run only is a difference)
    only += sum(1 for i in skipped if i >> 28 != 3)
    if any(i >> 28 != 3 for i in skipped):
        first = first if first is not None else (fr[0], "object", "id %#x" % min(i for i in skipped if i >> 28 != 3), "in one run only")
    if skipped:
        print(f"reader: {len(skipped)} objects seen by one run's dump only, not compared")
    res["differing_modules"] = [[c, m, n] for (c, m), n in sorted(mods.items(), key=lambda kv: -kv[1])]
    res.update(dump_frames=len(fr), values_equal=eq, values_different=ne, modules_one_run_only=only,
               dump_first=list(first) if first else None)
    print(f"reader: {len(fr)} frames compared ({fr[0] if fr else '-'}-{fr[-1] if fr else '-'}); values equal {eq}, in modules that differ {ne}, "
          f"modules in one run only {only}" + (f"; first: frame {first[0]}, {first[1]} {first[2]} ({first[3]})" if first else ""))
    for (cat, mod), n in sorted(mods.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {n:6} object-frames  {cat} {mod}")
    res["pass"] = bool(keys and fr and eq and not bad and not ne and not only)
    return res


def main():
    a = sys.argv[1:]
    if a[0] == "digest":
        digest(a[1])
        return 0
    lo = int(a[a.index("--from") + 1]) if "--from" in a else 0
    hi = int(a[a.index("--to") + 1]) if "--to" in a else 1 << 60
    return 0 if compare(a[1], a[2], lo, hi)["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
