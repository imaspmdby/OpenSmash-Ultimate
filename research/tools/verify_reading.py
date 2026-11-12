"""verify_reading: the game checks the code reading of the modules (research/map/code_reading/modules/<Module>.json).

    deps/python/python.exe research/tools/verify_reading.py <write watch file>... [--out research/map/code_reading/verified_fields.json]

The code reading (read-only subagents over the generated C, 2026-11-12) proposes, for each module, fields: offset,
size, type, name, the getter or setter that uses them, the functions that show it. Nothing of it enters the map
without one of these checks by the game:
  W  the game's own writes (SSBU_WRITE_WATCH, build-trace, hle_memtrace.c): during real fights, the game's code wrote
     exactly this span (same offset, same size) of the fighter's module object; and when the reading names the
     functions it read (f_<address>), whether one of them is among the writers (W+: the writer too);
  R  the game's getter probe (research/map/getter_regions.json, SSBU_PROBE_FIELDS): the getter the reading names reads
     these bytes;
  V  the automatic check of the series (fields.json's plain loads, compared with the game's getters every 20 frames):
     the dictionary already holds this offset for this module's class.
A field with none of them stays a proposal (in the reading's file, not in the map). Only the fighter's class of each
module (the reading's class_vptr) and the module's own object (or a block behind its first pointers: path [p, o]).
"""
import argparse
import collections
import glob
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memtrace  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAP = os.path.join(ROOT, "research", "map")
WIDTH = {"f32": 4, "u32": 4, "i32": 4, "u8": 1, "i8": 1, "bool": 1, "u16": 2, "i16": 2, "u64": 8, "i64": 8, "ptr": 8,
         "hash40": 8, "f64": 8}


def num(x):
    if isinstance(x, int):
        return x
    if isinstance(x, str) and re.fullmatch(r"\s*(0x[0-9a-fA-F]+|\d+)\s*", x):
        return int(x, 0)
    return None


def fields_of(d):
    """(block offset or 0, offset, size, field) for the fields with a plain place."""
    for f in d.get("fields", []):
        size = num(f.get("size"))
        if not size:
            size = WIDTH.get(str(f.get("type", "")).lower())
        path = f.get("path")
        off = num(f.get("off"))
        if path:
            p = [num(x) for x in path]
            st = re.search(r"[a-z_]\s*\*\s*(0x[0-9a-fA-F]+)", str(f.get("off", "")))
            if len(p) == 2 and None not in p and st and size:
                # (an array of records written [pointer, offset] with the stride in "off": "0x68+id*0x130+0x20")
                stride = int(st.group(1), 16)
                for k in range(0, 64):
                    o = p[1] + k * stride
                    if o + size > 0x900 or not stride:
                        break
                    yield p[0], o, size, dict(f, name="%s[%d]" % (f.get("name", "?"), k))
            elif len(p) == 2 and None not in p:
                yield p[0], p[1], size, f
            elif len(p) == 3 and p[0] is not None and p[2] is not None and size:
                # [pointer, "<index>*<stride>", offset]: an array of records behind the pointer; each record of the
                # first 0x900 bytes (the most the dump and the write watch hold of a block) is a field of its own
                m = re.fullmatch(r"\s*\(?\s*[a-z_]+\s*\)?\s*\*\s*(0x[0-9a-fA-F]+|\d+)\s*", str(path[1]))
                if m:
                    stride = int(m.group(1), 0)
                    for k in range(0, 64):
                        o = p[2] + k * stride
                        if o + size > 0x900 or not stride:
                            break
                        yield p[0], o, size, dict(f, name="%s[%d]" % (f.get("name", "?"), k))
            continue
        if off is not None and size:
            yield 0, off, size, f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("watch", nargs="+")
    ap.add_argument("--readings", default=os.path.join(MAP, "code_reading", "modules"))
    ap.add_argument("--exe-map", default=os.path.join(ROOT, "build-trace", "ssbu.map"))
    ap.add_argument("--out", default=os.path.join(MAP, "code_reading", "verified_fields.json"))
    a = ap.parse_args()
    boma_off = json.load(open(os.path.join(MAP, "fields.json")))["boma_offsets"]
    regions = json.load(open(os.path.join(MAP, "getter_regions.json")))
    dic = json.load(open(os.path.join(MAP, "fields.json")))
    em = memtrace.ExeMap(a.exe_map)
    # the writes: (category, boma offset, block offset) -> {(offset, size): {writer functions}}
    writes = collections.defaultdict(lambda: collections.defaultdict(set))
    for w in a.watch:
        for ln in open(w):
            p = ln.split()
            if len(p) != 6:
                continue
            cat, bo, blk, off, size, rva = (int(x, 16) for x in p)
            writes[(cat, bo, blk)][(off, size)].add(em.name(rva))
    # the dictionary's plain loads, by module and class: offsets (fields.json)
    import fields as fields_mod
    fd = fields_mod.Dictionary()
    known = {}
    def known_offs(mod, vptr):
        if (mod, vptr) not in known:
            known[(mod, vptr)] = {fo for _m, fo, _k in fd.fields_for(vptr, mod)}
        return known[(mod, vptr)]
    out, stats = {}, collections.Counter()
    per_mod = {}
    for path in sorted(glob.glob(os.path.join(a.readings, "*.json"))):
        d = json.load(open(path))
        mod = d.get("module") or os.path.basename(path)[:-5]
        if mod not in boma_off:
            continue
        vptr = num(d.get("class_vptr")) or 0
        bo = boma_off[mod]
        size = num(d.get("size")) or 0
        ok_fields = []
        c = collections.Counter()
        for blk, off, fsz, f in fields_of(d):
            if blk == 0 and size and off >= size:
                continue
            c["proposed"] += 1
            how = []
            wr = writes.get((0, bo, blk), {})
            if (off, fsz) in wr:
                fns = set(re.findall(r"f_71[0-9a-f]{8}", json.dumps(f).lower()))
                how.append("W+" if fns & wr[(off, fsz)] else "W")
            g = str(f.get("getter") or "")
            meth = re.sub(r"_impl$", "", g.split("__")[-1].split("::")[-1]) if g else ""
            if blk == 0 and meth and all(mod + "." + meth in regions.get(mod, {}).get(str(b), []) for b in range(off, off + fsz)):
                how.append("R")
            if blk == 0 and off in known_offs(mod, vptr):
                how.append("V")
            for h in how:
                c[h] += 1
            if how:
                c["confirmed"] += 1
                ok_fields.append([off, fsz, f.get("name", "?"), blk, "+".join(how), f.get("confidence", "")])
        per_mod[mod] = dict(c)
        stats.update(c)
        if ok_fields:
            out.setdefault(mod, {})["%#x" % vptr] = [x for x in ok_fields if x[3] == 0]
            out[mod]["%#x/behind" % vptr] = [x for x in ok_fields if x[3] != 0]
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"{'module':24} {'proposed':>8} {'confirmed':>9} {'W':>5} {'W+':>5} {'R':>5} {'V':>5}")
    for mod, c in sorted(per_mod.items()):
        print(f"{mod:24} {c.get('proposed', 0):8} {c.get('confirmed', 0):9} {c.get('W', 0):5} {c.get('W+', 0):5} {c.get('R', 0):5} {c.get('V', 0):5}")
    print(f"{'all':24} {stats['proposed']:8} {stats['confirmed']:9} {stats['W']:5} {stats['W+']:5} {stats['R']:5} {stats['V']:5}")
    print("->", a.out)


if __name__ == "__main__":
    main()
