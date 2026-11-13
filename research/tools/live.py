"""Live across a frame's boundary (2026-11-13 afternoon): which bytes carry state from one frame to the next, measured
on whole fights with no load at all (runtime: SSBU_LIVE, hle_memtrace.c; a build with SSBU_MEMTRACE).

    deps/python/python.exe research/tools/live.py run <match> [--matrix M] [--tag T]
    deps/python/python.exe research/tools/live.py agg [--tags a,b] [--not-matches x,y] [--out SUFFIX]
    deps/python/python.exe research/tools/live.py check [--tags a,b]          (against this morning's recordings)
    deps/python/python.exe research/tools/live.py unseen --built SUFFIX --tags a,b   (the invariant test)

run: the fight (40 s, CPUs, stock 99) in the trace build with the tracker on from fight frame 300 to 2,300: at each
     rollback safe point every byte's first access starts again; a byte's marks over its block's life: L read first
     after some safe point, D written first after some safe point, H written first then read by another thread,
     W written at all. research/runs/live/<tag>/<match>.live.txt.
agg: every run put together by place (allocation site, block size, offset); a place is
       carried     L and W: the game read it before writing it after some boundary, and it changes: state;
       constant    L, never W: only read; a load never changes it;
       handed over H (no L): written by one thread, read by another before the boundary; kept as state;
       recomputed  D only: at every boundary of every run, written before read;
     and a site is "dead" when it has written bytes and none carried or handed over, in every run that saw it.
     Writes research/map/live_state<suffix>.json (families, sites, the fighters' module fields by name) and
     research/runs/live/dead_sites<suffix>.txt (an SSBU_RB_UNITS file).
check: the acceptance test: every place this morning's recordings (readfirst.py, <match>.runs.txt) saw read first
     must be carried or constant here for the same match.
unseen: places called recomputed by the runs of --built that the runs of --tags (other matches) see read first.
"""
import argparse
import collections
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reduce as R  # noqa: E402

OUT = os.path.join(R.ROOT, "research", "runs", "live")
L, D, H, W = 1, 2, 4, 8


def klass(m):
    return "carried" if m & L and m & W else "constant" if m & L else "handed over" if m & H else "recomputed" if m & D else "?"


def step_run(a):
    tag = a.tag or "a"
    d = os.path.join(OUT, tag)
    os.makedirs(d, exist_ok=True)
    pre = os.path.join(d, a.match)
    for ext in (".live.txt", ".diff.txt"):
        if os.path.exists(pre + ext):
            os.remove(pre + ext)
    cmd = [R.PY, os.path.join(R.HERE, "matrix.py"), os.path.join(R.ROOT, "research", "matrix", a.matrix), "--only", a.match,
           "--out", os.path.join("live", tag), "--hash", "--override", "stock=99", "--ring", "none", "--exe", "build-trace",
           "--timeout", "900", "--end", "40s", "--env", "SSBU_FIGHT_HASH_LF=1", "--env", "SSBU_RB=1",
           "--env", "SSBU_RB_UNITS_DIFF=" + pre + ".diff.txt", "--env", "SSBU_LIVE=300,2300," + pre + ".live.txt",
           "--env", "SSBU_WRITE_WATCH=" + pre + ".ww.txt"]   # (the fighters' module objects are registered by the tracker itself, from the frame line's accessors)
    if a.match.startswith("items_cpu"):
        cmd += ["--env", "SSBU_RULE_POKE=58:ffffffffffffffffffffff"]
    p = subprocess.run(cmd, cwd=R.ROOT, capture_output=True, text=True)
    print((p.stdout.strip().splitlines() or [p.stderr[-300:]])[0])
    for fn in (pre + ".state.bin", pre + ".state.bin.table"):
        if os.path.exists(fn):
            os.remove(fn)
    log = open(os.path.join(d, a.match, "run.log"), errors="replace").read()
    print("\n".join(ln[:200] for ln in log.splitlines() if "SSBU_LIVE" in ln))


def files(tags, skip=()):
    out = []
    for f in sorted(glob.glob(os.path.join(OUT, "*", "*.live.txt"))):
        tag, match = os.path.basename(os.path.dirname(f)), os.path.basename(f)[:-9]
        if (not tags or tag in tags) and match not in skip:
            out.append((tag, match, f))
    return out


def load(f):
    """-> sites {(ra1, ra2, size): [(off, len, marks)]}, rest [(addr, len, marks)], mods {key: [(off, len, marks)]}"""
    sites, rest, mods = {}, [], collections.defaultdict(list)
    cur = None
    for ln in open(f):
        p = ln.split()
        if p[0] == "r":
            cur.append((int(p[1], 16), int(p[2], 16), int(p[3], 16)))
        elif p[0] == "site":
            cur = sites.setdefault((p[1], p[2], int(p[3], 16)), [])
        elif p[0] == "rest":
            rest.append((int(p[1], 16), int(p[2], 16), int(p[3], 16)))
        elif p[0] == "mod":
            mods[int(p[1], 16)].append((int(p[2], 16), int(p[3], 16), int(p[4], 16)))
    return sites, rest, mods


def merge(fs):
    """Every run's marks by place: {(ra1, ra2, size): bytearray(size)} (OR), and by module key."""
    places, mods, rest = {}, collections.defaultdict(dict), collections.Counter()
    seen_in = collections.defaultdict(set)
    for tag, match, f in fs:
        sites, rs, ms = load(f)
        for key, runs in sites.items():
            b = places.get(key)
            if b is None:
                b = places[key] = bytearray(key[2])
            for off, n, m in runs:
                for o in range(off, min(off + n, key[2])):
                    b[o] |= m
            seen_in[key].add(match)
        for key, runs in ms.items():
            d = mods[key]
            for off, n, m in runs:
                for o in range(off, off + n):
                    d[o] = d.get(o, 0) | m
        for addr, n, m in rs:
            rest[(R.area(addr), klass(m))] += n
        print(f"  {tag} {match}: {len(sites)} places", flush=True)
    return places, mods, rest, seen_in


def ranges(offs):
    out = []
    for o in offs:
        if out and out[-1][0] + out[-1][1] == o:
            out[-1][1] += 1
        else:
            out.append([o, 1])
    return out


def step_agg(a):
    import reader
    fs = files(set(filter(None, a.tags.split(","))), set(filter(None, a.not_matches.split(","))))
    places, mods, rest, seen_in = merge(fs)
    units = {u["spec"]: u for u in R.load_units()}
    removed = set(json.load(open(os.path.join(R.OUT, "validated_state.json")))["removed"])
    fam = collections.defaultdict(collections.Counter)
    sites = collections.defaultdict(lambda: {"sizes": 0, "bytes": collections.Counter(), "matches": set()})
    for (ra1, ra2, size), b in places.items():
        spec = "site %s %s" % (ra1, ra2)
        u = units.get(spec)
        f = "nvn-sync" if ra1 == "710373e524" else u["family"] if u else "sites not in the inventory"
        c = collections.Counter(klass(m) for m in b if m)
        fam[f].update(c)
        s = sites[spec]
        s["sizes"] += 1
        s["bytes"].update(c)
        s["matches"] |= seen_in[(ra1, ra2, size)]
        s["family"] = f
    # the recomputed ranges of each place, as an SSBU_RB_UNITS file of parts (research/runs/live/recomputed_parts<suffix>.txt),
    # for the families given (--parts: "a,b"; "-a,b" = all but these)
    neg = a.parts.startswith("-")
    pf = set(a.parts.lstrip("-").split(","))
    nparts = nbytes = 0
    with open(os.path.join(OUT, "recomputed_parts%s.txt" % a.out), "w", newline="\n") as f:
        f.write("mode drop\n")
        for (ra1, ra2, size), b in sorted(places.items()):
            u = units.get("site %s %s" % (ra1, ra2))
            fm = "nvn-sync" if ra1 == "710373e524" else u["family"] if u else "sites not in the inventory"
            if (fm in pf) == neg:
                continue
            for off, n in ranges([o for o, m in enumerate(b) if m and klass(m) == "recomputed"]):
                f.write("part %s %s %x %x %x\n" % (ra1, ra2, size, off, n))
                nparts += 1
                nbytes += n
    print(f"recomputed parts for the ring ({a.parts}): {nparts} ranges, {nbytes:,} bytes of places")
    dead, rows = [], []
    for spec, s in sites.items():
        c = s["bytes"]
        isdead = c["recomputed"] > 0 and not c["carried"] and not c["handed over"]
        rows.append({"site": spec[5:], "family": s["family"], "block_sizes": s["sizes"], "bytes": dict(c), "matches": sorted(s["matches"]),
                     "dead": isdead, "size_in_inventory": units[spec]["bytes"] if spec in units else None,
                     "already_removed_2026-11-12": spec in removed})
        if isdead:
            dead.append(spec)
    rows.sort(key=lambda r: -(r["bytes"].get("carried", 0)))
    # the fighters' module fields by name
    fj = json.load(open(os.path.join(R.MAPDIR, "fields.json")))
    name_at = {off: n for n, off in fj["boma_offsets"].items()}
    size_of = {}
    for _v, (n, sz) in json.load(open(os.path.join(R.MAPDIR, "module_sizes.json"))).items():
        size_of[n] = max(size_of.get(n, 0), sz)
    vf = os.path.join(R.MAPDIR, "code_reading", "verified_fields.json")
    verified = json.load(open(vf)) if os.path.exists(vf) else {}
    modules, ftot, vtot = {}, collections.Counter(), collections.Counter()
    for key, d in sorted(mods.items()):
        cat, moff, sub = key >> 28, (key >> 16) & 0xfff, key & 0xffff
        if sub:
            continue
        cname, mname = reader.CATEGORY.get(cat, "?%d" % cat), name_at.get(moff, "+%#x" % moff)
        lim = size_of.get(mname, 0x900)
        by = collections.defaultdict(list)
        for o in sorted(d):
            if o < lim:
                by[klass(d[o])].append(o)
        ent = {"size": size_of.get(mname), "bytes": {k: len(v) for k, v in by.items()}, "carried": ranges(by["carried"]),
               "recomputed": ranges(by["recomputed"]), "handed_over": ranges(by["handed over"]), "constant": ranges(by["constant"])}
        rd = os.path.join(R.MAPDIR, "code_reading", "modules", mname + ".json")
        if cname == "fighter" and os.path.exists(rd):
            ver = set()
            for vp, rws in verified.get(mname, {}).items():
                if "behind" not in vp:
                    ver |= {(r[0], r[1]) for r in rws}
            fields = []
            for fd in json.load(open(rd)).get("fields", []):
                if fd.get("path"):
                    continue
                try:
                    off, size = int(str(fd["off"]), 0), int(fd["size"])
                except (KeyError, ValueError, TypeError):
                    continue
                m = 0
                for o in range(off, off + size):
                    m |= d.get(o, 0)
                k = klass(m) if m else "not touched"
                fields.append({"off": off, "size": size, "name": fd.get("name"), "class": k, "verified_by_the_game": (off, size) in ver})
                ftot[k] += 1
                if (off, size) in ver:
                    vtot[k] += 1
            ent["fields"] = fields
        modules.setdefault(cname, {})[mname] = ent
    out = {"what": __doc__.split("agg:")[1].split("check:")[0], "runs": [[t, m] for t, m, _ in fs], "by_family": {f: dict(c) for f, c in fam.items()},
           "bytes_in_no_block": {"%s / %s" % k: v for k, v in rest.items()}, "fighter_fields": dict(ftot), "fighter_fields_verified": dict(vtot),
           "dead_sites": sorted(dead), "sites": rows, "modules": modules}
    json.dump(out, open(os.path.join(R.MAPDIR, "live_state%s.json" % a.out), "w"))
    with open(os.path.join(OUT, "dead_sites%s.txt" % a.out), "w", newline="\n") as f:
        f.write("mode drop\n")
        for s in sorted(dead):
            f.write(s + "\n")
    cols = ("carried", "constant", "handed over", "recomputed")
    print(f"\n{len(fs)} runs; {len(places)} places (site, block size); bytes of places by family:")
    print(f"  {'family':28}" + "".join(f"{c:>13}" for c in cols))
    tot = collections.Counter()
    for f, c in sorted(fam.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {f:28}" + "".join(f"{c[k]:13,}" for k in cols))
        tot.update(c)
    print(f"  {'all':28}" + "".join(f"{tot[k]:13,}" for k in cols))
    print("bytes in no block:", ", ".join(f"{k[0]} {k[1]} {v:,}" for k, v in sorted(rest.items())))
    dn = [r for r in rows if r["dead"]]
    new = [r for r in dn if not r["already_removed_2026-11-12"]]
    print(f"dead sites (written, never carried, never handed over): {len(dn)}; not already in the set of 2026-11-12: {len(new)}, "
          f"{sum(r['size_in_inventory'] or 0 for r in new) / 2**20:.1f} MB in the inventory, by family: "
          + ", ".join(f"{k} {v}" for k, v in collections.Counter(r["family"] for r in new).most_common()))
    print("fighter fields (code reading):", dict(ftot), "; verified by the game:", dict(vtot))
    print("written: research/map/live_state%s.json, research/runs/live/dead_sites%s.txt" % (a.out, a.out))


def step_check(a):
    fs = files(set(filter(None, a.tags.split(","))))
    by_match = collections.defaultdict(list)
    for t, m, f in fs:
        by_match[m].append((t, m, f))
    rf = os.path.join(R.ROOT, "research", "runs", "rf")
    for match, mf in sorted(by_match.items()):
        places, _mods, _rest, _s = merge(mf)
        n = bad = unseen = 0
        worst = collections.Counter()
        for f in glob.glob(os.path.join(rf, a.rf_tags + "*", match + ".runs.txt")):
            for ln in open(f):
                p = ln.split()
                if p[0] == "0" or p[5] != "1":
                    continue
                key = (p[0], p[1], int(p[2], 16))
                b = places.get(key)
                off, ln_ = int(p[3], 16), int(p[4], 16)
                for o in range(off, off + ln_):
                    n += 1
                    if b is None:
                        unseen += 1
                    elif not b[o] & L:
                        bad += 1
                        worst[(key[0], key[1], hex(key[2]), klass(b[o]) if b[o] else "not touched")] += 1
        print(f"{match}: bytes the recordings saw read first {n:,}; not live here {bad:,} ({100 * bad / max(n, 1):.2f} %); in places this run "
              f"did not see {unseen:,}")
        for k, v in worst.most_common(8):
            print("     ", v, k)


def step_unseen(a):
    built = json.load(open(os.path.join(R.MAPDIR, "live_state%s.json" % a.built)))
    fs = files(set(filter(None, a.tags.split(","))))
    places, mods, _rest, _s = merge(fs)
    # module fields: recomputed in the built map, read first in the other matches
    tot = collections.Counter()
    for mname, ent in built["modules"].get("fighter", {}).items():
        pass
    name_at = {off: n for n, off in json.load(open(os.path.join(R.MAPDIR, "fields.json")))["boma_offsets"].items()}
    by_mod = {}
    for key, d in mods.items():
        if key >> 28 == 0 and not key & 0xffff:
            by_mod[name_at.get((key >> 16) & 0xfff, "+%#x" % ((key >> 16) & 0xfff))] = d
    viol = []
    for mname, ent in built["modules"].get("fighter", {}).items():
        d = by_mod.get(mname, {})
        for fd in ent.get("fields", []):
            m = 0
            for o in range(fd["off"], fd["off"] + fd["size"]):
                m |= d.get(o, 0)
            k = klass(m) if m else "not touched"
            tot[(fd["class"], k)] += 1
            if fd["class"] == "recomputed" and k in ("carried", "handed over"):
                viol.append((mname, hex(fd["off"]), fd["name"], k))
    print("fighter fields: class in the built map -> class in the other matches:")
    for (x, y), n in sorted(tot.items()):
        print(f"  {x:12} -> {y:12} {n}")
    print("fields recomputed in the built map and read first (or handed over) in the other matches:", len(viol))
    for v in viol[:20]:
        print("   ", v)
    dead = set(built["dead_sites"])
    sv = collections.Counter()
    for (ra1, ra2, size), b in places.items():
        spec = "site %s %s" % (ra1, ra2)
        if spec in dead:
            c = collections.Counter(klass(m) for m in b if m)
            if c["carried"] or c["handed over"]:
                sv[spec] += c["carried"] + c["handed over"]
    seen = {"site %s %s" % (k[0], k[1]) for k in places}
    print(f"dead sites of the built map: {len(dead)}; seen in the other matches: {len(dead & seen)}; with a carried or handed-over byte there: {len(sv)}")
    for s, n in sv.most_common(10):
        print("   ", s, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["run", "agg", "check", "unseen"])
    ap.add_argument("match", nargs="?")
    ap.add_argument("--matrix", default="items_cpu.txt")
    ap.add_argument("--tag")
    ap.add_argument("--tags", default="")
    ap.add_argument("--not-matches", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--built", default="")
    ap.add_argument("--parts", default="pools,main:sim,stage,effects,scripts,hud", help="agg: the families whose recomputed ranges go to the parts file")
    ap.add_argument("--rf-tags", default="", help="check: only the recordings whose tag starts so")
    a = ap.parse_args()
    {"run": step_run, "agg": step_agg, "check": step_check, "unseen": step_unseen}[a.step](a)


if __name__ == "__main__":
    main()
