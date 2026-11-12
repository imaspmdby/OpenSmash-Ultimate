"""The colouring by allocation site: one row per (site = first two return addresses of the allocation, block size), over several traced runs.

    deps/python/python.exe research/tools/sites.py <run folder> [<run folder>...] [--out research/map/sites]

Each run: one run of build-trace with the access trace (mt.bin) and the allocation trace (alloc.live), the same
build that wrote them. Each 64-byte line the game's code touched is placed in its live block, and the block's
(first two return addresses of the allocation, size) is the row. Per row and run: bytes of the touched lines by class
(state read by the simulation's code / state read in the logic phase by other code / other state / scratch / output
/ constant: memtrace.py's classes), blocks, when they were made (boot, match load, fight), the guest functions that
read and wrote the state (f_<guest address>: invariant across builds, unlike host offsets), and the code categories
that read it. Lines in no live block are grouped by memory area.

A row's label is the class that holds most of its touched bytes in every run where it appears; "mixed" when the
runs disagree or no class holds most. Limits: the trace keeps the last state reader and writer of each line only
(the category masks are complete); a pool or arena is one row whatever its slots hold; a block freed before the
report is not in alloc.live (its lines go to "no live block").

Writes <out>.json (every row) and <out>.md (the rows with state, and the largest others).
"""
import bisect
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import code_cats  # noqa: E402
import memtrace  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM = (1 << 1) | (1 << 8) | (1 << 10)   # app, lua2cpp scripts, app? (region)
CLASSES = ("sim state", "logic state", "other state", "scratch", "output", "constant")
CN = code_cats.CATS[:16]


def line_class(fr, fw, first_r, live, cr):
    k = memtrace.klass(fr, fw, first_r, live)
    if k != "state":
        return k
    if cr & SIM:
        return "sim state"
    if cr & ((1 << 16) | (1 << 17)):
        return "logic state"
    return "other state"


def load_blocks(run):
    bl, setup = [], -1
    for line in open(os.path.join(run, "alloc.live")):
        p = line.split()
        if p[0] == "#":
            setup = int(p[2])
            continue
        bl.append((int(p[0], 16), int(p[1]), int(p[2]), int(p[3]), " ".join(p[5:7]) if len(p) > 5 else "?"))
    bl.sort()
    return bl, setup


def guest_name(em, cache, off):
    if off == 0xFFFFFFFF:
        return None
    if off not in cache:
        n = em.name(off)
        if n.startswith("f_"):
            n = "f_" + n[2:].split("_")[0]
        cache[off] = n
    return cache[off]


def one_run(run, em):
    _frames, _threads, lines = memtrace.load(os.path.join(run, "mt.bin"))
    bl, setup = load_blocks(run)
    starts = [b[0] for b in bl]
    rows = collections.defaultdict(lambda: {"bytes": collections.Counter(), "blocks": set(), "made": collections.Counter(),
                                            "readers": collections.Counter(), "writers": collections.Counter(),
                                            "cats": collections.Counter()})
    cache = {}
    for a, fr, fw, first_r, live, _tm, ra_l, ra_w, _chain, cr, cw in lines:
        i = bisect.bisect_right(starts, a) - 1
        b = bl[i] if i >= 0 and bl[i][0] + bl[i][1] > a else None
        key = (b[4], b[1]) if b else ("no live block: " + memtrace.area(a), 0)
        r = rows[key]
        k = line_class(fr, fw, first_r, live, cr)
        r["bytes"][k] += 64
        if b and b[0] not in r["blocks"]:
            r["blocks"].add(b[0])
            r["made"]["fight" if b[3] else "match load" if setup >= 0 and b[2] >= setup else "boot / menus"] += 1
        if k.endswith("state"):
            g = guest_name(em, cache, ra_l)
            if g:
                r["readers"][g] += 64
            g = guest_name(em, cache, ra_w)
            if g:
                r["writers"][g] += 64
            for j in range(16):
                if cr >> j & 1:
                    r["cats"][CN[j]] += 64
    return rows


def label(byts):
    tot = sum(byts.values())
    if not tot:
        return "-"
    st = sum(v for k, v in byts.items() if k.endswith("state"))
    if st * 2 >= tot:
        return max(("sim state", "logic state", "other state"), key=lambda c: byts[c])
    k, v = byts.most_common(1)[0]
    return k if v * 2 >= tot else "mixed"


def main():
    args = list(sys.argv[1:])
    out = os.path.join(ROOT, "research", "map", "sites")
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1]
        del args[i:i + 2]
    em = memtrace.ExeMap(os.path.join(ROOT, "build-trace", "ssbu.map"))
    runs = {}
    for r in args:
        name = os.path.basename(os.path.normpath(r))
        if name in runs:
            name = os.path.basename(os.path.dirname(os.path.normpath(r))) + "/" + name
        runs[name] = one_run(r, em)
    keys = set()
    for rows in runs.values():
        keys |= set(rows)
    table = []
    for key in keys:
        per = {}
        for rn, rows in runs.items():
            if key in rows:
                r = rows[key]
                per[rn] = {"KB": {c: round(r["bytes"][c] / 1024, 1) for c in CLASSES if r["bytes"][c]},
                           "label": label(r["bytes"]), "blocks": len(r["blocks"]), "made": dict(r["made"]),
                           "readers": [f for f, _n in r["readers"].most_common(3)],
                           "writers": [f for f, _n in r["writers"].most_common(3)],
                           "reader categories": [c for c, _n in r["cats"].most_common(4)]}
        labels = {p["label"] for p in per.values()}
        agreed = labels.pop() if len(labels) == 1 else "mixed (runs disagree: " + "/".join(sorted(labels)) + ")"
        touched = max(sum(p["KB"].values()) for p in per.values())
        state = max(sum(v for c, v in p["KB"].items() if c.endswith("state")) for p in per.values())
        sim = max(p["KB"].get("sim state", 0) for p in per.values())
        table.append({"site": key[0], "size": key[1], "label": agreed, "runs": len(per), "max touched KB": round(touched, 1),
                      "max state KB": round(state, 1), "max sim state KB": round(sim, 1), "per run": per})
    table.sort(key=lambda t: (-t["max state KB"], -t["max touched KB"]))
    with open(out + ".json", "w") as f:
        json.dump({"runs": list(runs), "classes": CLASSES, "rows": table}, f, indent=1)
    tot = {rn: collections.Counter() for rn in runs}
    for t in table:
        for rn, p in t["per run"].items():
            for c, v in p["KB"].items():
                tot[rn][c] += v
    md = ["# Allocation sites coloured by the access trace", "",
          f"Made by `research/tools/sites.py` from the runs {', '.join(runs)}. One row per (allocation site = first two return "
          "addresses of the allocation, block size). KB of the 64-byte lines touched in the trace window, by class: "
          "**sim state** (a value carried between frames, read by app / lua2cpp code), **logic state** (carried, read in "
          "the logic phase by other code), **other state** (carried, read outside the logic phase only), scratch, output, "
          "constant. A row's label is its main class, the same in every run where it appears, else \"mixed\". Readers "
          "and writers are guest functions (`f_<guest address>`): the last one seen per line only. A pool or arena is "
          "one row whatever its slots hold. Lines in no live block are grouped by memory area.", "",
          "## Totals (KB)", "", "| run | " + " | ".join(CLASSES) + " |", "|---|" + "---|" * len(CLASSES)]
    for rn, c in tot.items():
        md.append(f"| {rn} | " + " | ".join(f"{c[k]:.0f}" for k in CLASSES) + " |")
    with_state = [t for t in table if t["max state KB"] > 0]
    md += ["", f"## Rows with state ({len(with_state)} rows; the 150 largest)", "",
           "| site | size | label | runs | state KB (max) | sim state KB (max) | touched KB (max) | blocks | made | readers | writers |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in with_state[:150]:
        p = max(t["per run"].values(), key=lambda p: sum(p["KB"].values()))
        md.append(f"| {t['site']} | {t['size']} | {t['label']} | {t['runs']} | {t['max state KB']} | {t['max sim state KB']} | "
                  f"{t['max touched KB']} | {p['blocks']} | {', '.join(f'{k} {v}' for k, v in p['made'].items())} | "
                  f"{' '.join(p['readers'][:2])} | {' '.join(p['writers'][:2])} |")
    md += ["", "## The largest rows without state (40)", "", "| site | size | label | runs | touched KB (max) |", "|---|---|---|---|---|"]
    for t in sorted([t for t in table if t["max state KB"] == 0], key=lambda t: -t["max touched KB"])[:40]:
        md.append(f"| {t['site']} | {t['size']} | {t['label']} | {t['runs']} | {t['max touched KB']} |")
    open(out + ".md", "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(f"{len(table)} rows ({len(with_state)} with state); written {out}.json and {out}.md")
    for rn, c in tot.items():
        print(f"  {rn}: " + ", ".join(f"{k} {c[k]:.0f} KB" for k in CLASSES))


if __name__ == "__main__":
    main()
