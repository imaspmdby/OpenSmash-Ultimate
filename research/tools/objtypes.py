"""Name the game's classes and colour the hot pages by the objects in them.

    deps/python/python.exe research/tools/objtypes.py <run folder> <prefix>

1. The modules of a fighter's module accessor (boma): every exported app::lua_bind::<Module>__<method>_impl begins
   by loading the module from the boma (`ldr xN, [x0, #off]`), so its name gives the module at that offset.
2. <prefix>.boma (SSBU_BOMA_DUMP): each fighter's boma words and the first word of what they point to; the module
   at an offset is an object whose first word is its vptr: vptr -> "app::<Module>" (RTTI or not).
3. <prefix>.vptrs (SSBU_RB_SM_VPTRS): the words of each hot page that point into main's data. A candidate is a vptr
   when main's static image has a code address at it (the vtable's first entry) and, before it, 0 or a type_info.
   Each vptr is named by RTTI, else by step 2, else "vtable <address>".
Prints the module table, the named vptrs, the hot pages by the types of their objects, and writes types.json.
"""
import collections
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtti  # noqa: E402

TEXT_END = 0x39c8440
BASE = 0x7100000000


def module_offsets(names):
    """{offset in the boma: module name}, from the lua_bind getters' first loads."""
    m = names.m
    found = collections.defaultdict(collections.Counter)
    pat = re.compile(r"^_ZN3app8lua_bind\d+([A-Za-z0-9]+Module)__\w+_impl")
    for n, v, sz, _i, _sh in m.exports:
        k = pat.match(n)
        if not k or sz < 4:
            continue
        for i in range(min(6, sz // 4)):
            w = struct.unpack_from("<I", m.image, v + 4 * i)[0]
            if (w & 0xFFC003E0) == 0xF9400000:   # ldr xT, [x0, #imm12 * 8]
                found[(w >> 10 & 0xFFF) * 8][k.group(1)] += 1
                break
    return {off: c.most_common(1)[0][0] for off, c in found.items()}


def is_vtable(names, vptr):
    off = vptr - BASE
    first = names.word(off)
    if first is None or not (0 < first < TEXT_END):
        return False
    before = names.word(off - 8)
    return before == 0 or (before is not None and names.name(vptr) is not None)


def main():
    run, prefix = sys.argv[1], sys.argv[2]
    names = rtti.Names()
    offs = module_offsets(names)
    print(f"boma offsets of {len(offs)} modules (from the lua_bind getters):")
    print("  " + ", ".join(f"{o:#x} {n}" for o, n in sorted(offs.items())))

    vname = {}
    with open(prefix + ".boma") as f:
        cur = None
        for line in f:
            p = line.split()
            if p[0] == "boma":
                cur = p
                continue
            off, w, w0 = (int(x, 16) for x in p)
            if off in offs and w0:
                vname.setdefault(w0, f"app::{offs[off]}")
    print(f"module vptrs found in the bomas: {len(vname)}")
    for v, n in sorted(vname.items(), key=lambda x: x[1]):
        r = rtti.demangle_simple(names.name(v))
        print(f"  {v:#x} {n}{'  (RTTI: ' + r + ')' if r else ''}")

    pages = collections.defaultdict(collections.Counter)
    seen = {}
    with open(os.path.join(prefix + ".vptrs")) as f:
        for line in f:
            pg, _first, val, cnt = line.split()
            val = int(val, 16)
            if val not in seen:
                seen[val] = is_vtable(names, val)
            if seen[val]:
                pages[int(pg, 16)][val] += int(cnt)
    vt = [v for v, ok in seen.items() if ok]

    named = sorted((v, (rtti.demangle_simple(names.name(v)) or vname.get(v))) for v in set(vt) | set(vname))
    named = [(v, n) for v, n in named if n]
    nv = [v for v, _ in named]

    def near_ns(v):
        """Heuristic: the namespace of the nearest named vtables by address (vtables are laid out by translation
        unit and library), when both neighbours agree within 64 KB; marked with a leading '~'."""
        import bisect
        i = bisect.bisect_left(nv, v)
        cands = [named[j] for j in (i - 1, i) if 0 <= j < len(named) and abs(named[j][0] - v) < 0x10000]
        nss = {n.split("::")[0] for _, n in cands if "::" in n}
        return "~" + nss.pop() if len(nss) == 1 else None

    def label(v):
        r = rtti.demangle_simple(names.name(v))
        if r or v in vname:
            return r or vname[v]
        g = near_ns(v)
        return f"{g}::? (vtable {v:#x})" if g else f"vtable {v:#x}"

    def ns(lbl):
        return lbl.split("::")[0] if "::" in lbl else "(unnamed vtable)"

    objects, page_owner = collections.Counter(), collections.Counter()
    owner_ns = collections.Counter()
    for pg, c in pages.items():
        for v, n in c.items():
            objects[label(v)] += n
        top = label(c.most_common(1)[0][0])
        page_owner[top] += 1
        owner_ns[ns(top)] += 1
    hot_cpu = sum(1 for _ in open(os.path.join(run, "hot_runs.txt")))
    print(f"\n{len(vt)} distinct vtables in the hot pages; {len(pages)} hot pages hold at least one object")
    print("hot pages by the namespace of their most frequent object:")
    for k, n in owner_ns.most_common():
        print(f"  {n:6} pages  {k}")
    print("objects counted in hot pages, by type (top 50):")
    for k, n in objects.most_common(50):
        print(f"  {n:7}  {k}")
    with open(os.path.join(run, "types.json"), "w") as f:
        json.dump({"module_offsets": {hex(o): n for o, n in offs.items()}, "module_vptrs": {hex(v): n for v, n in vname.items()},
                   "objects": objects, "page_owner": page_owner, "owner_ns": owner_ns}, f, indent=1)


if __name__ == "__main__":
    main()
