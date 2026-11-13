"""Carried or recomputed (2026-11-13): the first accesses recorded after a load (research/tools/readfirst.py,
<match>.runs.txt of research/runs/rf/<tag>/) put together over runs, matches and window lengths.

    deps/python/python.exe research/tools/carried.py [--min N] [--tags PREFIX,...] [--not-matches a,b]

A byte is placed by (allocation site, block size, offset in the block): the same place in every run and match.
Over all the recordings where the byte differed from the saved state at the second load:
  carried      read before written at least once: the load must put it back (state that goes from frame to frame);
  recomputed   written before read in EVERY recording, by the thread that goes on using it, in at least N recordings
               (default 3): a load need not put it back;
  handed over  written first, then read by another thread, at least once (never read first): which comes first is
               a race between threads; kept;
  few          written first every time but seen in fewer than N recordings; kept;
  untouched    never accessed in the window in some recording, never read first: undetermined; kept.
One recording is one window of one launch: a byte "written first" there can still be read first in another launch
(a lock word a thread holds at the load), hence "every recording" and N. Sites of the GPU's family and of the fibers
are left out (their readers are the runtime's own threads, outside the trace), and the bytes in no traced block (no
place that holds from run to run).
Writes research/map/carried_state.json (per site and block size: the counts and the ranges) and
research/map/recomputed_parts.txt (an SSBU_RB_UNITS file: "part <site> <block size> <offset> <length>" for every
recomputed range), and prints the table by family.
"""
import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reduce as R  # noqa: E402

RF = os.path.join(R.ROOT, "research", "runs", "rf")
SKIP_FAM = {"gpu", "fibers"}


def ranges(offs):
    out = []
    for o in sorted(offs):
        if out and out[-1][0] + out[-1][1] == o:
            out[-1][1] += 1
        else:
            out.append([o, 1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=3)
    ap.add_argument("--tags", default="rec_,h_m1_r")
    ap.add_argument("--not-matches", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    units = {u["spec"]: u for u in R.load_units()}
    skip_m = set(filter(None, a.not_matches.split(",")))
    files = []
    for f in sorted(glob.glob(os.path.join(RF, "*", "*.runs.txt"))):
        tag, match = os.path.basename(os.path.dirname(f)), os.path.basename(f)[:-9]
        if any(tag.startswith(p) for p in a.tags.split(",")) and match not in skip_m and os.path.getsize(f):
            files.append((tag, match, f))
    # (site, size) -> offset -> [mask of first accesses seen, recordings]
    seen = collections.defaultdict(dict)
    fam_of = {}
    for tag, match, f in files:
        local = collections.defaultdict(dict)
        for ln in open(f):
            p = ln.split()
            if p[0] == "0":
                continue
            key = (p[0], p[1], int(p[2], 16))
            if key not in fam_of:
                u = units.get("site %s %s" % (p[0], p[1]))
                fam_of[key] = "nvn-sync" if p[0] == "710373e524" else u["family"] if u else "sites not in the inventory"
            if fam_of[key] in SKIP_FAM:
                continue
            off, n, bit = int(p[3], 16), int(p[4], 16), 1 << int(p[5])
            d = local[key]
            for o in range(off, off + n):
                d[o] = d.get(o, 0) | bit
        for key, d in local.items():
            g = seen[key]
            for o, m in d.items():
                e = g.get(o)
                if e is None:
                    g[o] = [m, 1]
                else:
                    e[0] |= m
                    e[1] += 1
        print(f"  {tag} {match}: {sum(len(d) for d in local.values()):,} bytes in {len(local)} (site, size)", flush=True)
    sites, parts = [], []
    fam = collections.defaultdict(lambda: collections.Counter())
    for key, g in seen.items():
        cls = {"carried": [], "recomputed": [], "handed over": [], "few": [], "untouched": []}
        for o, (m, n) in g.items():
            if m & 2:
                cls["carried"].append(o)
            elif m & 8:
                cls["handed over"].append(o)
            elif m & 1:
                cls["untouched"].append(o)
            elif n >= a.min:
                cls["recomputed"].append(o)
            else:
                cls["few"].append(o)
        for k, v in cls.items():
            fam[fam_of[key]][k] += len(v)
        rec = ranges(cls["recomputed"])
        sites.append({"site": key[0] + " " + key[1], "block_size": key[2], "family": fam_of[key],
                      "bytes": {k: len(v) for k, v in cls.items()}, "carried": ranges(cls["carried"]), "recomputed": rec})
        parts += [(key[0], key[1], key[2], o, n) for o, n in rec]
    sites.sort(key=lambda s: -s["bytes"]["carried"])
    out = {"recordings": [[t, m] for t, m, _ in files], "min_recordings": a.min, "rule": __doc__.split("Over all")[1].split("One recording")[0],
           "by_family": {f: dict(c) for f, c in fam.items()}, "sites": sites}
    name = "carried_state" + a.out
    json.dump(out, open(os.path.join(R.MAPDIR, name + ".json"), "w"))
    pf = os.path.join(R.MAPDIR, "recomputed_parts" + a.out + ".txt")
    with open(pf, "w", newline="\n") as f:
        f.write("mode drop\n")
        for p in sorted(parts):
            f.write("part %s %s %x %x %x\n" % p)
    tot = collections.Counter()
    print(f"\n{len(files)} recordings, {len(seen)} (site, block size) with differing bytes; bytes by family:")
    print(f"  {'family':28} {'carried':>10} {'recomputed':>11} {'handed over':>12} {'few':>9} {'untouched':>10}")
    for f, c in sorted(fam.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {f:28} {c['carried']:10,} {c['recomputed']:11,} {c['handed over']:12,} {c['few']:9,} {c['untouched']:10,}")
        tot.update(c)
    print(f"  {'all':28} {tot['carried']:10,} {tot['recomputed']:11,} {tot['handed over']:12,} {tot['few']:9,} {tot['untouched']:10,}")
    print(f"written: research/map/{name}.json, {os.path.relpath(pf, R.ROOT)} ({len(parts)} ranges)")


if __name__ == "__main__":
    main()
