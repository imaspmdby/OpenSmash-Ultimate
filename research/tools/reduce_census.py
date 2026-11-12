"""The census of the units that differ at a load (SSBU_RB_UNITS_DIFF), over witness runs (nothing removed):

    deps/python/python.exe research/tools/reduce_census.py [--runs N] [--matches] [--ring]

--runs N     N replay-check runs of the search match (save at 600, 3 loads 60 frames later): census_<k>.txt
--matches    one replay-check run of each validation match (reduce.py's VALIDATE): census_<match>_A.txt
--ring       one ring run (150 loads, 5 frames back every 6) of each validation match: census_<match>_B.txt
--again N    replay-check runs 2..N of each validation match: census_<match>_A<n>.txt
(the corrected-input matches of judge L: reduce_night.py copies the witness trials' own diff files, census_<match>_L.txt)
Runs already there are not made again. Then every census_*.txt of research/runs/reduce is read into census.json:
"seen" (site -> the number of loads where it differed), "max" (site -> the most bytes at one load; and the bytes in no
block by area), "loads". A site is a unit that holds from run to run; a 16 MB slice of bytes in no block is not (the
heap's addresses move), so those are counted by area only.
"""
import collections
import concurrent.futures
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reduce as R  # noqa: E402


def one(job):
    (matrix, name, envs), mode, tag = job
    out = os.path.join(R.OUT, "census_%s.txt" % tag)
    if os.path.exists(out):
        return out
    cmd = [R.PY, os.path.join(R.HERE, "matrix.py"), os.path.join(R.ROOT, "research", "matrix", matrix), "--only", name,
           "--out", os.path.join("reduce", "census_" + tag), "--hash", "--override", "stock=99", "--env", "SSBU_RB_UNITS_DIFF=" + out]
    if mode == "A":
        cmd += ["--ring", "none", "--timeout", "150", "--end", "25s", "--env", "SSBU_RB=1", "--env", "SSBU_RB_VERIFY=600,60,3"]
    else:
        cmd += ["--ring", "600,6,5,150", "--timeout", "900", "--end", "40s"]
    for e in envs:
        cmd += ["--env", e]
    p = subprocess.run(cmd, cwd=R.ROOT, capture_output=True, text=True)
    print("  " + (p.stdout.strip().splitlines() or ["?"])[0][:150], flush=True)
    return out


def main():
    a = sys.argv[1:]
    jobs = []
    if "--runs" in a:
        jobs += [(R.SEARCH, "A", str(k)) for k in range(int(a[a.index("--runs") + 1]))]
    if "--matches" in a:
        jobs += [(m, "A", m[1] + "_A") for m in R.VALIDATE]
    if "--ring" in a:
        jobs += [(m, "B", m[1] + "_B") for m in R.VALIDATE]
    if "--again" in a:   # (more runs of every match: what differs changes from one launch to the next)
        for n in range(2, int(a[a.index("--again") + 1]) + 1):
            jobs += [(m, "A", "%s_A%d" % (m[1], n)) for m in R.VALIDATE]
    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        list(ex.map(one, jobs))
    seen, mx, loads = collections.Counter(), collections.Counter(), 0
    per_file = {}
    for f in sorted(glob.glob(os.path.join(R.OUT, "census_*.txt"))):
        acc, n = None, 0
        for ln in open(f):
            p = ln.split()
            if p[0] == "load":
                if acc:
                    for k, v in acc.items():
                        mx[k] = max(mx[k], v)
                acc = collections.Counter()
                loads += 1
                n += 1
                continue
            if acc is None:
                continue
            if p[0] == "site":
                k = " ".join(p[:3])
                seen[k] += 1
                mx[k] = max(mx[k], int(p[3]))
            else:
                acc["rest:" + R.area(int(p[1], 16))] += int(p[3])
        if acc:
            for k, v in acc.items():
                mx[k] = max(mx[k], v)
        per_file[os.path.basename(f)] = n
    json.dump({"loads": loads, "seen": seen, "max": mx, "files": per_file}, open(R.CENSUS, "w"))
    units = {u["spec"]: u for u in R.load_units()}
    sites = list(seen)
    known = [k for k in sites if k in units]
    print(f"{len(per_file)} runs, {loads} loads; sites that differed at least once: {len(sites)} ({len(sites) - len(known)} not in the "
          f"inventory of the search match); of the inventory: {len(known)} sites, {sum(units[k]['bytes'] for k in known) / 2**20:.1f} MB in size")
    print("bytes in no block, the most at one load, by area:", {k: v for k, v in mx.items() if k.startswith("rest:")})
    fam = collections.defaultdict(lambda: [0, 0, 0])
    for k in sites:
        f = units[k]["family"] if k in units else "sites:unlisted"
        fam[f][0] += 1
        fam[f][1] += units[k]["bytes"] if k in units else 0
        fam[f][2] += mx[k]
    for f, (n, b, d) in sorted(fam.items(), key=lambda kv: -kv[1][2]):
        print(f"  {f:18} {n:5} sites {b / 2**20:8.1f} MB  differing {d:9} bytes")


if __name__ == "__main__":
    main()
