"""The size of each module class's object, from the allocation trace: research/map/module_sizes.json.

    deps/python/python.exe research/tools/module_sizes.py <run folder> [<run folder>...]

Each run: alloc.live and state.bin of one probe run (matrix.py --probe --state). Every module of every dumped object
is looked up among the live blocks; its class (vptr) gets the block's size when the module starts its block. The state
dump copies 0x900 bytes from each module whatever its size: what lies past the size is another object's memory.
A class seen with two sizes is reported and left out.
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
OUT = os.path.join(ROOT, "research", "map", "module_sizes.json")


def main():
    dic = fields.Dictionary()
    sizes = collections.defaultdict(collections.Counter)
    names = {}
    for run in sys.argv[1:]:
        bl = []
        for line in open(os.path.join(run, "alloc.live")):
            p = line.split()
            if p[0] != "#":
                bl.append((int(p[0], 16), int(p[1])))
        bl.sort()
        st = [b[0] for b in bl]
        for r in reader.records(os.path.join(run, "state.bin")):
            if r["kind"] == 2:
                continue
            for o, (addr, b) in r["mods"].items():
                name = dic.off_name.get(o)
                if not name or len(b) < 8:
                    continue
                i = bisect.bisect_right(st, addr) - 1
                if i < 0 or bl[i][0] != addr:
                    continue
                v = struct.unpack_from("<Q", b, 0)[0]
                sizes[v][bl[i][1]] += 1
                names[v] = name
    out, bad = {}, 0
    for v, c in sizes.items():
        if len(c) == 1:
            out[f"{v:#x}"] = [names[v], next(iter(c))]
        else:
            bad += 1
            print(f"  {names[v]} {v:#x}: sizes {dict(c)}: left out")
    old = json.load(open(OUT)) if os.path.exists(OUT) else {}
    old.update(out)
    json.dump(dict(sorted(old.items())), open(OUT, "w"), indent=0)
    print(f"{len(out)} module classes sized ({bad} with two sizes); {len(old)} in {OUT}")


if __name__ == "__main__":
    main()
