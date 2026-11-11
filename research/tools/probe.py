"""What each getter reads (SSBU_PROBE_FIELDS in build-trace): fields found by observation, not by pattern.

    deps/python/python.exe research/tools/probe.py <run folder> [<run folder> ...] [--write research/map/probed_fields.json]

Each run: state.bin with PROB records (a fighter's getters called once inside a probe: every byte each one read) and
alloc.live (the blocks' bounds). A getter's reads are placed: the boma, one of the object's modules (offset in it),
another heap block, or ignored (code and read-only data, the module's vptr, thread stacks). A getter is a FIELD when
it reads one place of its own module only, and what it returned is what lies there. Prints the getters by shape and
the new fields (not in the static dictionary); --write keeps them by module class (vptr).
"""
import bisect
import collections
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fields  # noqa: E402
import reader  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STACK_SITES = {"0x710353cf48"}


def main():
    runs = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = sys.argv[sys.argv.index("--write") + 1] if "--write" in sys.argv else None
    if write and write in runs:
        runs.remove(write)
    index = {int(k): tuple(v) for k, v in json.load(open(os.path.join(ROOT, "research", "map", "probe_getters.txt.json"))).items()}
    dic = fields.Dictionary()
    shapes = collections.Counter()
    found = {}            # (vptr, module, method) -> (offset, kind) seen, with a count of agreeing objects
    agree = collections.Counter()
    clash = set()
    multi = collections.defaultdict(set)
    objects = 0
    for run in runs:
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

        for r in reader.records(os.path.join(run, "state.bin")):
            probe = r.get("probe")
            if not probe:
                continue
            objects += 1
            mods = {}   # module block start -> (name, vptr, bytes, module address)
            for o, (addr, b) in r["mods"].items():
                name = dic.off_name.get(o)
                if name and len(b) >= 8:
                    blk = block(addr)
                    mods[blk[0] if blk else addr] = (name, struct.unpack_from("<Q", b, 0)[0], b, addr, blk[1] if blk else 0x900)
            for idx, (x0, fb, reads) in probe.items():
                mod, meth = index[idx]
                places = []   # (where, offset, size)
                for addr, size, wr, *_val in reads:
                    if wr or 0x7100000000 <= addr < 0x7400000000:
                        continue
                    if 0x7700000000 <= addr < 0x7780000000:
                        continue
                    blk = block(addr)
                    if blk and blk[2] in STACK_SITES:
                        continue
                    if r["boma"] <= addr < r["boma"] + 0x400:
                        places.append(("boma", addr - r["boma"], size))
                        continue
                    m = mods.get(blk[0]) if blk else None
                    if m:
                        off = addr - m[3]
                        if off == 0 and size == 8:
                            continue   # the vptr
                        places.append((m[0], off, size))
                    else:
                        places.append(("other", addr, size))
                own = [p for p in places if p[0] == mod]
                rest = [p for p in places if p[0] not in (mod, "boma")]
                uniq = sorted(set(own))
                if not places:
                    shapes["reads nothing of the object"] += 1
                elif rest:
                    shapes["reads other blocks or modules"] += 1
                    multi[(mod, meth)].add("other")
                elif len(uniq) == 1:
                    _w, off, size = uniq[0]
                    m = next(v for v in mods.values() if v[0] == mod)
                    b = m[2]
                    kind = None
                    if off + size <= len(b):
                        raw = int.from_bytes(b[off:off + size], "little")
                        if size == 4 and raw == fb and (x0 & 0xFFFFFFFF) != raw:
                            kind = "f32"
                        elif size == 4 and raw == (x0 & 0xFFFFFFFF):
                            kind = "u32"
                        elif size == 1 and raw == (x0 & 0xFF):
                            kind = "u8"
                        elif size == 8 and raw == x0:
                            kind = "u64"
                        elif size == 2 and raw == (x0 & 0xFFFF):
                            kind = "u16"
                        elif size == 4 and raw == fb:
                            kind = "f32"   # (x0 happened to hold the same bits)
                    if kind:
                        shapes["FIELD: one place of its module, returned as it is"] += 1
                        key = (m[1], mod, meth)
                        if key in found and found[key] != (off, kind):
                            clash.add(key)
                        found[key] = (off, kind)
                        agree[key] += 1
                    else:
                        shapes["one place of its module, but the result is computed from it"] += 1
                elif uniq:
                    shapes["several places of its module"] += 1
                    multi[(mod, meth)].add(len(uniq))
                else:
                    shapes["reads the boma only"] += 1
    print(f"{objects} objects probed; getter calls by shape:")
    for k, v in shapes.most_common():
        print(f"  {v:5}  {k}")
    new = collections.defaultdict(list)
    known = 0
    for (vptr, mod, meth), (off, kind) in sorted(found.items(), key=lambda kv: (kv[0][1], kv[1][0])):
        if (vptr, mod, meth) in clash:
            continue
        static = {m: (o, k) for m, o, k in dic.fields_for(vptr, mod)}
        if meth in static:
            known += 1
            if static[meth][0] != off:
                print(f"  DISAGREES with the static dictionary: {mod}.{meth} probe +{off:#x} static +{static[meth][0]:#x}")
            continue
        new[(vptr, mod)].append((meth, off, kind))
    print(f"fields seen by the probe: {len(found)} (class, method) pairs; {known} already in the static dictionary (same offsets), "
          f"{sum(len(v) for v in new.values())} new, {len(clash)} with two answers (left out)")
    for (vptr, mod), fs in sorted(new.items(), key=lambda kv: kv[0][1]):
        print(f"  {mod} (vptr {vptr:#x}): " + ", ".join(f"{m}@{o:#x}:{k}" for m, o, k in fs))
    if write:
        out = collections.defaultdict(list)
        for (vptr, mod), fs in new.items():
            for m, o, k in fs:
                out[hex(vptr)].append([mod, m, o, k])
        with open(write, "w") as f:
            json.dump(out, f, indent=1)
        print("written:", write)


if __name__ == "__main__":
    main()
