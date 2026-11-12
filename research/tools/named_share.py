"""named_share: of the bytes that change during a fight, the share the map names, for each category of object.

    deps/python/python.exe research/tools/named_share.py <state.bin> [--extra research/map/code_reading/verified_fields.json]

A byte "changes" when it differs between two consecutive dumped frames of the same object (the module's own object, at
most its class's size, module_sizes.json; and the blocks the dump holds behind the module's pointers, by their pointer
path). Each byte is counted once per object (and region). Three columns:
  identified: covered by a field the game's getters give (fields.json plain loads, the special fields, argprobe.py's
              fields with arguments: work variables get_int(0x...), etc.)
  named before: of them, the fields whose name says what they are: every field but the work variables (whose name was
              only the getter and the id) - the map of the morning of 2026-11-12
  named after: + the work variables the community's constants name and the game confirmed (community.py), + the
              fields of the code reading the game confirmed (--extra, verify_reading.py's file: {module: {"<vptr>":
              [[off, size, name, 0, ...], ...], "<vptr>/behind": [[off, size, name, pointer's offset, ...], ...]}})
"""
import argparse
import collections
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reader  # noqa: E402

_SZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "map", "module_sizes.json")
SIZES = {int(k, 16): v[1] for k, v in json.load(open(_SZ)).items()} if os.path.exists(_SZ) else {}


def regions(rd, rec, dec, extra):
    """{region: (bytes, identified offsets, named-before offsets, named-after offsets)}; region = (module, path)."""
    out = {}
    names = dec.get("names", {})
    for o, (maddr, b) in rec["mods"].items():
        name = rd.off_name.get(o)
        if not name or len(b) < 8:
            continue
        vptr = struct.unpack_from("<Q", b, 0)[0]
        n = min(len(b), SIZES.get(vptr, 1 << 30))
        ide, bef, aft = set(), set(), set()
        for _m, fo, kind in rd.dic.fields_for(vptr, name) + reader.SPECIAL.get(name, []):
            r = range(fo, fo + struct.calcsize(reader.KIND[kind]))
            ide.update(r); bef.update(r); aft.update(r)
        for fo, size, _nm in extra.get(name, {}).get("%#x" % vptr, ()):
            aft.update(range(fo, fo + size))
        # the blocks behind the pointers: their paths
        path_of = {maddr: ()}
        blocks = {}
        todo = [maddr]
        mods_addrs = {m[0] for m in rec["mods"].values()}
        while todo:
            parent = todo.pop()
            for po, (addr, bx) in rec["behind"].get(parent, {}).items():
                if addr in path_of or addr in mods_addrs:
                    continue
                path_of[addr] = path_of[parent] + (po,)
                blocks[addr] = bx
                todo.append(addr)
        sets = collections.defaultdict(lambda: (set(), set(), set()))
        for fname, (_k, size, _v, blk, off) in rd.arg_values(rec, name, maddr, b).items():
            r = range(off, off + size)
            s = (ide, bef, aft) if blk == maddr else sets[blk]
            s[0].update(r)
            meaningful = name != "WorkModule"
            if meaningful:
                s[1].update(r)
            if meaningful or (name + "." + fname) in names and not names[name + "." + fname].startswith("one of"):
                s[2].update(r)
        out[(name, vptr, ())] = (b[:n], ide, bef, aft)
        beh = collections.defaultdict(set)   # (the code reading's fields one pointer down, path [p, o]: "<vptr>/behind")
        for x in extra.get(name, {}).get("%#x/behind" % vptr, ()):
            beh[(x[3],)].update(range(x[0], x[0] + x[1]))
        for addr, bx in blocks.items():
            i, be, af = sets.get(addr, (set(), set(), set()))
            af = af | beh.get(path_of[addr], set())
            out[(name, vptr, path_of[addr])] = (bx, i, be, af)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--extra")
    ap.add_argument("--json")
    a = ap.parse_args()
    extra = {}
    if a.extra:
        for mod, by in json.load(open(a.extra)).items():
            extra[mod] = {k: [tuple(x[:4]) if "behind" in k else tuple(x[:3]) for x in v] for k, v in by.items()}
    rd = reader.Reader()
    recs = [r for r in reader.records(a.dump) if r["kind"] != 2]
    decs = [rd.decode(r) for r in recs]
    rd.name_weapons(decs)
    prev = {}
    changed = collections.defaultdict(set)   # (object id, region) -> offsets that changed
    cover = {}                               # (object id, region) -> (identified, before, after): the union over frames
    cat = {}
    for r, d in sorted(zip(recs, decs), key=lambda x: x[0]["frame"]):
        if not d.get("active", True):
            prev.pop(r["id"], None)
            continue
        cat[r["id"]] = d["category"]
        cur = regions(rd, r, d, extra)
        old = prev.get(r["id"])
        if old:
            for key, (b, i, be, af) in cur.items():
                if key in old:
                    ob = old[key][0]
                    for j in range(min(len(b), len(ob))):
                        if b[j] != ob[j]:
                            changed[(r["id"], key)].add(j)
        for key, (_b, i, be, af) in cur.items():
            c = cover.setdefault((r["id"], key), (set(), set(), set()))
            c[0].update(i); c[1].update(be); c[2].update(af)
        prev[r["id"]] = cur
    tot = collections.defaultdict(lambda: [0, 0, 0, 0])
    per_obj = collections.defaultdict(lambda: [0, 0, 0, 0])
    by_mod = collections.defaultdict(lambda: [0, 0, 0, 0])
    for (oid, key), offs in changed.items():
        i, be, af = cover[(oid, key)]
        row = [len(offs), len(offs & i), len(offs & be), len(offs & af)]
        for t in (tot[cat[oid]], per_obj[(cat[oid], oid)], by_mod[(cat[oid], key[0])]):
            for q in range(4):
                t[q] += row[q]
    pc = lambda x, y: f"{100 * x / max(1, y):5.1f} %"
    print("bytes that changed during the fight (each once per object), by category:")
    print(f"  {'':10} {'changed':>9} {'identified':>18} {'named before':>18} {'named after':>18}")
    for c, (n, i, be, af) in sorted(tot.items()):
        print(f"  {c:10} {n:9} {i:9} {pc(i, n)} {be:9} {pc(be, n)} {af:9} {pc(af, n)}")
    print("one object of each category (the one with the most changed bytes):")
    for c in sorted(tot):
        (cc, oid), (n, i, be, af) = max(((k, v) for k, v in per_obj.items() if k[0] == c), key=lambda kv: kv[1][0])
        print(f"  {c:10} {oid:#010x} {n:9} {i:9} {pc(i, n)} {be:9} {pc(be, n)} {af:9} {pc(af, n)}")
    print("by module (all categories), the largest:")
    for (c, m), (n, i, be, af) in sorted(by_mod.items(), key=lambda kv: -kv[1][0])[:25]:
        print(f"  {c:8} {m:24} {n:8} {pc(i, n)} {pc(be, n)} {pc(af, n)}")
    if a.json:
        json.dump({"by_category": tot, "by_module": {f"{c}/{m}": v for (c, m), v in by_mod.items()}}, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
