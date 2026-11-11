"""The state the simulation's code reads outside the battle objects: by allocation site and reader.

    deps/python/python.exe research/tools/outside.py <run folder> [--frame N]

One run of build-trace with the access trace, the allocation trace and the state dump. Leaves out the battle objects'
modules and pools and the stage's presentation table (site 0x71026054bc); groups the rest by the block's site, size
and type, with when it was made (boot or match load) and the function that reads the most of it.
"""
import bisect
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memtrace  # noqa: E402
import reader  # noqa: E402
import rtti  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM = (1 << 1) | (1 << 8) | (1 << 10)
POOLS = {"0x71014f48c0", "0x71014f4dc4"}
TABLE = "0x71026054bc"


def main():
    run = sys.argv[1]
    frame = int(sys.argv[sys.argv.index("--frame") + 1]) if "--frame" in sys.argv else 480
    _f, _t, lines = memtrace.load(os.path.join(run, "mt.bin"))
    em = memtrace.ExeMap(os.path.join(ROOT, "build-trace", "ssbu.map"))
    names = rtti.Names()
    bl = []
    setup = -1
    for line in open(os.path.join(run, "alloc.live")):
        p = line.split()
        if p[0] == "#":
            setup = int(p[2])
            continue
        bl.append((int(p[0], 16), int(p[1]), p[5] if len(p) > 5 else "?", int(p[4], 16), int(p[2])))
    bl.sort()
    bs = [b[0] for b in bl]

    def block(a):
        i = bisect.bisect_right(bs, a) - 1
        return bl[i] if i >= 0 and bl[i][0] + bl[i][1] > a else None

    modb = set()
    for r in reader.records(os.path.join(run, "state.bin")):
        if r["kind"] == 2 or r["frame"] != frame:
            continue
        for _o, (addr, _b) in r["mods"].items():
            k = block(addr)
            if k:
                modb.add(k[0])
    agg = collections.defaultdict(lambda: [0, collections.Counter(), set()])
    for x in lines:
        if not x[4] or not (x[9] & SIM):
            continue
        k = block(x[0])
        if k and (k[0] in modb or k[2] in POOLS or k[2] == TABLE):
            continue
        if k:
            vt = 0x7104f17000 <= k[3] < 0x71052aa000
            t = rtti.demangle_simple(names.name(k[3])) if vt else None
            key = (k[2], k[1] if k[1] >= 4096 else "<4K", t or ("object" if vt else "data"), "match load" if k[4] >= setup else "boot")
        else:
            key = ("no traced block", "", "", "")
        e = agg[key]
        e[0] += 64
        e[1][em.name(x[6])] += 64
        e[2].add(k[0] if k else 0)
    tot = sum(e[0] for e in agg.values())
    print(f"state read by the simulation's code outside the battle objects and the stage table: {tot >> 10} KB in {len(agg)} groups")
    when = collections.Counter()
    for key, e in agg.items():
        when[key[3] or "no traced block"] += e[0]
    print("  by when the block was made:", {k: v >> 10 for k, v in when.items()}, "(KB)")
    acc = 0
    for key, e in sorted(agg.items(), key=lambda kv: -kv[1][0])[:20]:
        acc += e[0]
        print(f"  {e[0]:6} B ({100 * acc // max(1, tot):3}% cum) {len(e[2]):4} blocks  site {key[0]} size {key[1]} {key[2]} [{key[3]}]  "
              f"read by {e[1].most_common(1)[0][0]}")


if __name__ == "__main__":
    main()
