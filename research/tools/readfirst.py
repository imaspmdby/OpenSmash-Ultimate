"""Read before written (2026-11-13): after a load, which of the bytes it puts back does the game read before writing
them? Measured by the trace build (build-trace, SSBU_MEMTRACE) and tested in the same run (runtime: SSBU_RF,
hle_rb_state.c and hle_memtrace.c).

    deps/python/python.exe research/tools/readfirst.py ref  <match> [--matrix M]
    deps/python/python.exe research/tools/readfirst.py run  <match> [--matrix M] [--window W] [--mode 1|2] [--drop-pool] [--tag T]
    deps/python/python.exe research/tools/readfirst.py show <match> [--tag T]

ref: the fight with no rollback at all, in the trace build (research/runs/rf/ref/<match>): the reference.
run: save at fight frame 600; W frames later (default 60) the first load, whole, after which every byte keeps its
     first access; W frames later the second load, which leaves alone the bytes written first (mode 1) or every byte
     not read first (mode 2); the fight then goes on to its end (40 s). Judged against the reference, logic frame by
     logic frame, over the whole fight (refjudge.py, hash lines), and by the runtime's own check of the replay.
     --drop-pool: the negative control, the fighters' pool also left alone at the second load (must fail).
show: the run's numbers again: the differing bytes of the second load by first access and by family of units, the
     reading code, and the check against yesterday's removed set (a byte read first in a removed site contradicts it).
A match is a name of research/matrix/<M> (default items_cpu.txt; the poke of every item is added for items_cpu*).
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reduce as R  # noqa: E402
import refjudge  # noqa: E402

OUT = os.path.join(R.ROOT, "research", "runs", "rf")
CLS = {0: "not touched", 1: "read first", 2: "written first"}


def matrix_cmd(a, tag, extra):
    cmd = [R.PY, os.path.join(R.HERE, "matrix.py"), os.path.join(R.ROOT, "research", "matrix", a.matrix), "--only", a.match,
           "--out", os.path.join("rf", tag), "--hash", "--override", "stock=99", "--ring", "none", "--exe", "build-trace",
           "--timeout", str(a.timeout), "--end", "40s", "--env", "SSBU_FIGHT_HASH_LF=1"]
    if a.match.startswith("items_cpu"):
        cmd += ["--env", "SSBU_RULE_POKE=58:ffffffffffffffffffffff"]
    for e in extra:
        cmd += ["--env", e]
    return cmd


def step_ref(a):
    p = subprocess.run(matrix_cmd(a, "ref", []), cwd=R.ROOT, capture_output=True, text=True)
    print((p.stdout.strip().splitlines() or [p.stderr[-300:]])[0])
    refjudge.digest(os.path.join(OUT, "ref", a.match))


def step_run(a):
    tag = a.tag or "w%d_m%d%s%s" % (a.window, a.mode, "_nopool" if a.drop_pool else "", ("_s" + re.sub(r"[^a-z0-9-]", "", a.scope)) if a.scope else "")
    run = os.path.join(OUT, tag, a.match)
    os.makedirs(os.path.join(OUT, tag), exist_ok=True)
    dfile = os.path.join(OUT, tag, a.match + ".diff.txt")
    rfile = os.path.join(OUT, tag, a.match + ".readers.txt")
    for f in (dfile, rfile):
        if os.path.exists(f):
            os.remove(f)
    extra = ["SSBU_RB=1", "SSBU_RB_VERIFY=600,%d,2" % a.window, "SSBU_RF=%d" % a.mode, "SSBU_RF_OUT=" + rfile, "SSBU_RB_UNITS_DIFF=" + dfile,
             "SSBU_RF_RUNS=" + os.path.join(OUT, tag, a.match + ".runs.txt")]
    if a.modules:   # (the state dump just before the save registers the module objects: their bytes by first access)
        extra += ["SSBU_WRITE_WATCH=" + os.path.join(OUT, tag, a.match + ".ww.txt"),
                  "SSBU_STATE_DUMP=" + os.path.join(OUT, tag, a.match + ".state.bin") + ",1,597,599"]
    if a.drop_pool:
        ufile = os.path.join(OUT, tag, a.match + ".units.txt")
        with open(ufile, "w") as f:
            f.write("mode drop\n")
            for u in R.load_units():
                if u["spec"].startswith("site 71014f48c0 "):
                    f.write(u["spec"] + "\n")
        extra.append("SSBU_RB_UNITS=" + ufile)
    if a.scope:   # (only these families' bytes may be left alone: "fam1,fam2"; "-fam" = every family but these)
        neg = a.scope.startswith("-")
        fams = set(a.scope.lstrip("-").split(","))
        ufile = os.path.join(OUT, tag, a.match + ".scope.txt")
        with open(ufile, "w") as f:
            f.write("mode drop\n")
            for u in R.load_units():
                fam = "nvn-sync" if u["spec"].startswith("site 710373e524 ") else u["family"]
                if (fam in fams) != neg and not u["spec"].startswith("host "):
                    f.write(u["spec"] + "\n")
        extra += ["SSBU_RB_UNITS=" + ufile, "SSBU_RF_SCOPE=1"]
    p = subprocess.run(matrix_cmd(a, tag, extra), cwd=R.ROOT, capture_output=True, text=True)
    print((p.stdout.strip().splitlines() or [p.stderr[-300:]])[0])
    return step_show(a, tag)


def step_show(a, tag=None):
    tag = tag or a.tag or "w%d_m%d%s" % (a.window, a.mode, "_nopool" if a.drop_pool else "")
    run = os.path.join(OUT, tag, a.match)
    log = open(os.path.join(run, "run.log"), errors="replace").read()
    res = {"match": a.match, "tag": tag}
    m = re.search(r"SSBU_RF: second load \(mode (\d)\): since the first load the game read first (\d+) bytes and wrote first (\d+) \(of the bytes "
                  r"that differed then: (\d+) read first, (\d+) written first\)\. Bytes that differ now: (\d+) read first, (\d+) written first, "
                  r"(\d+) not touched; (\d+) left alone(?:; (\d+) written first then read by another thread)?", log)
    if not m:
        print("no second load in the log:", [ln for ln in log.splitlines() if "host exception" in ln or "watchdog" in ln or "SSBU_RF" in ln][:4])
        res["pass"] = False
        res["why"] = "no second load"
        json.dump(res, open(os.path.join(run, "rf.json"), "w"), indent=1)
        return res
    g = [int(x or 0) for x in m.groups()]
    res.update(mode=g[0], touched_read_first=g[1], touched_written_first=g[2], load1_differing_read_first=g[3], load1_differing_written_first=g[4],
               load2_differing={"read first": g[5], "written first": g[6], "not touched": g[7],
                                "written first then read by another thread": g[9]}, left_alone=g[8])
    tot = g[5] + g[6] + g[7] + g[9]
    print(f"second load: {tot:,} bytes differ from the saved state: read first {g[5]:,} ({100 * g[5] / max(tot, 1):.1f} %), written first {g[6]:,} "
          f"({100 * g[6] / max(tot, 1):.1f} %), not touched in the window {g[7]:,} ({100 * g[7] / max(tot, 1):.1f} %), written first then read by another thread {g[9]:,} "
          f"({100 * g[9] / max(tot, 1):.1f} %); left alone {g[8]:,}")
    res["replay_ok"] = len(re.findall(r"fight hash: replay \d+ matches the reference on all \d+ frames", log))
    res["replay_differs"] = re.findall(r"fight hash: replay \d+ DIFFERS[^\n]{0,100}", log)[:2]
    res["crash"] = bool(re.search(r"host exception|no frame presented", log))
    ref = os.path.join(OUT, "ref", a.match)
    try:
        dg = os.path.join(run, "digest.pkl")
        if os.path.exists(dg):
            os.remove(dg)
        c = refjudge.compare(ref, run)
        res["ref"] = {k: c[k] for k in ("hash_frames", "hash_different", "hash_first", "again_hash")}
        res["pass"] = bool(c["hash_frames"] > 4000 and c["hash_different"] == 0 and not res["crash"] and "SSBU_DEBUG_END:" in log
                           and res["replay_ok"] == 2)
    except Exception as e:
        res["pass"] = False
        res["why"] = repr(e)[:200]
    print("replays the runtime found identical:", res["replay_ok"], "of 2;", "crash or hang" if res["crash"] else "no crash;",
          "JUDGE:", "PASS" if res["pass"] else "FAIL")
    # the second load's differing bytes by unit and first access
    dfile = os.path.join(OUT, tag, a.match + ".diff.txt")
    units = {u["spec"]: u for u in R.load_units()}
    removed = set(json.load(open(os.path.join(R.OUT, "validated_state.json")))["removed"])
    fam = collections.defaultdict(lambda: [0, 0, 0, 0])
    site = collections.defaultdict(lambda: [0, 0, 0, 0])
    in_removed = [0, 0, 0, 0]
    load = 0
    if os.path.exists(dfile):
        for ln in open(dfile):
            p = ln.split()
            if p[0] == "load":
                load = int(p[1])
                if load == 1:   # (a run made again by matrix.py appends to the same file: the last one counts)
                    fam.clear()
                    site.clear()
                    in_removed = [0, 0, 0, 0]
                continue
            if load != 2 or len(p) < 5:
                continue
            k, n, c = " ".join(p[:3]), int(p[3]), int(p[4])
            if p[0] == "site":
                f = ("nvn-sync" if p[1] == "710373e524" else units[k]["family"]) if k in units else "sites not in the inventory"
                site[k][c] += n
                if k in removed:
                    in_removed[c] += n
            else:
                f = "no block: " + R.area(int(p[1], 16))
            fam[f][c] += n
    res["by_family"] = {f: v for f, v in fam.items()}
    res["in_removed_sites"] = dict(zip(("not touched", "read first", "written first"), in_removed))
    print("\nby family of units (bytes that differ at the second load):")
    print(f"  {'family':28} {'read first':>12} {'written first':>14} {'handed over':>12} {'not touched':>12}")
    for f, v in sorted(fam.items(), key=lambda kv: -sum(kv[1])):
        print(f"  {f:28} {v[1]:12,} {v[2]:14,} {v[3]:12,} {v[0]:12,}")
    print(f"in the sites removed on 2026-11-12: read first {in_removed[1]:,}, written first {in_removed[2]:,}, not touched {in_removed[0]:,}")
    res["sites_read_first"] = sum(1 for v in site.values() if v[1])
    res["sites_differing"] = len(site)
    res["sites_dead"] = sum(1 for v in site.values() if not v[1] and not v[0] and not v[3])
    print(f"sites with differing bytes: {len(site)}; with a byte read first: {res['sites_read_first']}; wholly written first: {res['sites_dead']}")
    top = sorted(site.items(), key=lambda kv: -kv[1][1])[:25]
    res["top_sites_read_first"] = [[k, v[1], v[2], v[0], units[k]["family"] if k in units else None] for k, v in top]
    # the reading code
    rfile = os.path.join(OUT, tag, a.match + ".readers.txt")
    mp = os.path.join(R.ROOT, "build-trace", "ssbu.map")
    if os.path.exists(rfile) and os.path.exists(mp):
        import memtrace
        em = memtrace.ExeMap(mp)
        fn = collections.Counter()
        for ln in open(rfile):
            p = ln.split()
            if p[0] == "reader":
                n = "(the runtime's native libc)" if p[1] == "fffffffe" else em.name(int(p[1], 16))
                if n.startswith("f_"):
                    n = "f_" + n[2:].split("_")[0]
                fn[n] += int(p[2])
        res["readers"] = len(fn)
        res["top_readers"] = fn.most_common(40)
        print(f"\nreading code (of the bytes that differed at the first load and were read first): {len(fn)} functions; the first 15:")
        for n, b in fn.most_common(15):
            print(f"  {b:10,}  {n}")
        try:   # (which library the reading code is: research/tools/code_cats.py)
            import code_cats
            import rtti
            names = rtti.Names()
            cm = rtti.CodeMap(names, {})
            exported = {0x7100000000 + v: n for n, v, _s, _i, _sh in names.m.exports}
            cat = collections.Counter()
            for n, b in fn.items():
                cat[code_cats.CATS[code_cats.category(n, cm, exported)]] += b
            res["readers_by_category"] = cat.most_common()
            print("by library of the reading code:", ", ".join(f"{k} {v:,}" for k, v in cat.most_common()))
        except Exception as e:
            print("(no categories:", repr(e)[:100], ")")
    json.dump(res, open(os.path.join(run, "rf.json"), "w"), indent=1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["ref", "run", "show"])
    ap.add_argument("match")
    ap.add_argument("--matrix", default="items_cpu.txt")
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--mode", type=int, default=1)
    ap.add_argument("--drop-pool", action="store_true")
    ap.add_argument("--tag")
    ap.add_argument("--modules", action="store_true", help="also the module objects' bytes by first access (mod lines of the readers file)")
    ap.add_argument("--scope", help="only these families of units may be left alone (a,b) or all but these (-a,b)")
    ap.add_argument("--timeout", type=int, default=150)
    a = ap.parse_args()
    if a.step == "ref":
        step_ref(a)
    elif a.step == "run":
        step_run(a)
    else:
        step_show(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
