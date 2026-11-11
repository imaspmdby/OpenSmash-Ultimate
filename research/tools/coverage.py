"""How much of the state the simulation reads does the reader name?

    deps/python/python.exe research/tools/coverage.py <run folder> [--frame N]

One run of build-trace with the probes, the access trace and the state dump (mt.bin, alloc.live, state.bin). Each
64-byte line of state read by the simulation's code (a value carried between frames, read by app / app? / lua2cpp
code) is placed: in a module of a battle object (which module, which offset: named by the field dictionary or
not), elsewhere in a battle object's pool slot, or outside the battle objects (by allocation site). Prints the
split and the largest unnamed places, with the code that reads them.
"""
import bisect
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fields  # noqa: E402
import memtrace  # noqa: E402
import reader  # noqa: E402
import rtti  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM = (1 << 1) | (1 << 8) | (1 << 10)
POOL_SITES = {"0x71014f48c0": "fighters' pool", "0x71014f4dc4": "weapons' pool"}


def main():
    run = sys.argv[1]
    want = int(sys.argv[sys.argv.index("--frame") + 1]) if "--frame" in sys.argv else None
    _fr, _th, lines = memtrace.load(os.path.join(run, "mt.bin"))
    em = memtrace.ExeMap(os.path.join(ROOT, "build-trace", "ssbu.map"))
    names = rtti.Names()
    dic = fields.Dictionary(names)
    exported = {0x7100000000 + v: n for n, v, _s, _i, _sh in names.m.exports}
    blocks = []
    for line in open(os.path.join(run, "alloc.live")):
        if line[0] == "#":
            continue
        p = line.split()
        blocks.append((int(p[0], 16), int(p[1]), p[5] if len(p) > 5 else "?"))
    blocks.sort()
    bs = [b[0] for b in blocks]

    def block(a):
        i = bisect.bisect_right(bs, a) - 1
        return blocks[i] if i >= 0 and blocks[i][0] + blocks[i][1] > a else None

    # the modules of every battle object, from the dump's frame nearest the trace window's end
    recs = [r for r in reader.records(os.path.join(run, "state.bin")) if r["kind"] != 2]
    frames = sorted({r["frame"] for r in recs})
    f = want if want is not None else frames[len(frames) // 2]
    mods = []   # (start, end, object id, module name, vptr)
    for r in recs:
        if r["frame"] != f:
            continue
        for o, (addr, b) in r["mods"].items():
            name = dic.off_name.get(o)
            if not name:
                continue
            blk = block(addr)
            end = blk[0] + blk[1] if blk else addr + 0x900
            mods.append((addr, end, r["id"], name, struct.unpack_from("<Q", b, 0)[0]))
    mods.sort()
    ms = [m[0] for m in mods]

    def module(a):
        i = bisect.bisect_right(ms, a) - 1
        return mods[i] if i >= 0 and mods[i][1] > a else None

    def fn(off):
        if off in (0, 0xFFFFFFFF):
            return "-"
        n = em.name(off)
        if n.startswith("f_"):
            try:
                g = int(n[2:].split("_")[0], 16)
                return exported.get(g, n)[:60]
            except ValueError:
                pass
        return n

    tot = 0
    where = collections.Counter()
    by_mod = collections.defaultdict(lambda: [0, 0])
    unnamed = collections.Counter()
    unnamed_reader = {}
    outside = collections.Counter()
    for x in lines:
        if not x[4] or not (x[9] & SIM):
            continue
        a = x[0]
        tot += 64
        m = module(a)
        if m:
            off = a - m[0]
            fs = dic.fields_for(m[4], m[3]) + reader.SPECIAL.get(m[3], [])
            named = any(off <= fo < off + 64 for _n, fo, _k in fs)
            cat = reader.CATEGORY.get(m[2] >> 28, "?")
            where[f"{cat} module, named field"] += 64 if named else 0
            where[f"{cat} module, unnamed"] += 0 if named else 64
            by_mod[(cat, m[3])][0 if named else 1] += 64
            if not named:
                unnamed[(cat, m[3], off)] += 64
                unnamed_reader[(cat, m[3], off)] = (fn(x[6]), fn(x[7]))
            continue
        b = block(a)
        if b and b[2] in POOL_SITES:
            where[f"{POOL_SITES[b[2]]}, outside the modules"] += 64
            continue
        where["outside the battle objects"] += 64
        outside[(b[2], b[1]) if b else ("no traced block", 0)] += 64
    print(f"state read by the simulation's code: {tot >> 10} KB (modules of frame {f})")
    for k, v in where.most_common():
        if v:
            print(f"  {v >> 10:5} KB  {k}")
    print("by module (named KB / unnamed KB), top 20:")
    for (cat, mod), (n, u) in sorted(by_mod.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))[:20]:
        print(f"  {cat:8} {mod:22} {n / 1024:6.1f} / {u / 1024:6.1f}")
    print("largest unnamed places (object, module, line offset; read by <- written by), top 20:")
    agg = collections.Counter()
    for (cat, mod, off), v in unnamed.items():
        agg[(cat, mod, off)] += v
    for (cat, mod, off), v in agg.most_common(20):
        r, w = unnamed_reader[(cat, mod, off)]
        print(f"  {v:5} B  {cat} {mod}+{off:#x}  {r} <- {w}")
    print("outside the battle objects, by allocation site and block size, top 12:")
    for (s, sz), v in outside.most_common(12):
        print(f"  {v >> 10:5} KB  site {s}  block {sz} B")


if __name__ == "__main__":
    main()
