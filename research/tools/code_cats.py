"""Categories of ssbu.exe's code for the access trace (SSBU_MEMTRACE_CATS): which library each generated function is.

    deps/python/python.exe research/tools/code_cats.py <build folder> <out file> [<types.json>]

Reads <build>/ssbu.map; each generated function f_<guest address> gets a category from rtti.CodeMap (its class's
namespace, or its placed neighbours'): 1 app, 2 nn, 3 nu, 4 lib / other placed, 5 main's unplaced code (the main
loop, Lua?, allocator, libc), 6 the SDK (sdk, subsdk: 0x7108...-0x7200...), 7 the runtime (not f_*), 8 the scripts
(lua2cpp_common, the fighters', items': 0x7200000000-0x7262000000), 9 plugins (0x7262000000 on). Functions with no anchor near
take their region's category (10-13, REGIONS: a layout heuristic). Writes a binary file: u32 count, then count x (u32 exe offset, u32 category), sorted, one entry per change of category.
CATS lists the names, by number.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memtrace  # noqa: E402
import rtti  # noqa: E402

CATS = ["none", "app", "nn", "nu", "lib/other", "main unplaced", "sdk", "runtime", "lua2cpp scripts", "plugins",
        "app? (region)", "nn? (region)", "nu? (region)", "core libs? (region)",
        "logic phase", "outside logic"]   # (bits 14, 15 of the trace's masks: not code categories, hle_memtrace.c)
# main's code regions, read off the anchors' layout (research/RESEARCH.md): a function with no anchor near takes its
# region's category, marked "?". (start, end, category)
REGIONS = [(0x7100000000, 0x7100300000, 11), (0x7100300000, 0x7103600000, 10), (0x7103600000, 0x71038f0000, 12),
           (0x71038f0000, 0x71039c8440, 13)]


def category(fn, cm, exported):
    if not fn.startswith("f_"):
        return 7
    try:
        g = int(fn[2:].split("_")[0], 16)
    except ValueError:
        return 7
    if 0x7200000000 <= g < 0x7262000000:
        return 8
    if g >= 0x7262000000:
        return 9
    if not 0x7100000000 <= g < 0x71039c8440:
        return 6
    lab = exported.get(g) or cm.name(g)[0]
    lab = lab.lstrip("~")
    if lab.startswith("_ZN3app") or lab.startswith("app"):
        return 1
    if lab.startswith("_ZN2nn") or lab.startswith("nn"):
        return 2
    if lab.startswith("_ZN2nu") or lab.startswith("nu") or "N2nu" in lab:
        return 3
    if lab == "unknown":
        for lo, hi, c in REGIONS:
            if lo <= g < hi:
                return c
        return 5
    return 4


def main():
    build, out = sys.argv[1], sys.argv[2]
    names = rtti.Names()
    modv = {}
    if len(sys.argv) > 3:
        modv = {int(k, 16): v for k, v in json.load(open(sys.argv[3]))["module_vptrs"].items()}
    cm = rtti.CodeMap(names, modv)
    exported = {0x7100000000 + v: n for n, v, _s, _i, _sh in names.m.exports}
    em = memtrace.ExeMap(os.path.join(build, "ssbu.map"))
    rows, last = [], None
    counts = [0] * len(CATS)
    for off, fn in zip(em.starts, em.names):
        c = category(fn, cm, exported)
        counts[c] += 1
        if c != last:
            rows.append((off, c))
            last = c
    with open(out, "wb") as f:
        f.write(struct.pack("<I", len(rows)))
        for off, c in rows:
            f.write(struct.pack("<II", off, c))
    print(f"{len(rows)} ranges; functions by category: " + ", ".join(f"{CATS[i]} {n}" for i, n in enumerate(counts) if n))


if __name__ == "__main__":
    main()
