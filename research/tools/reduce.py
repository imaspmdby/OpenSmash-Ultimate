"""reduce: the minimal set of memory a load must put back for a fight to go on identically, by automatic reduction
from the full savestate (delta debugging), 2026-11-12.

    deps/python/python.exe research/tools/reduce.py inventory      the witness run and the units (units.json)
    deps/python/python.exe research/tools/reduce.py controls       all units kept = the witness; empty list and no
                                                                   fighters' pool must fail
    deps/python/python.exe research/tools/reduce.py families       each family removed alone, then those that pass together
    deps/python/python.exe research/tools/reduce.py search         bisection inside the families that fail
    deps/python/python.exe research/tools/reduce.py validate       the final set on the varied matches and the long ring
    deps/python/python.exe research/tools/reduce.py report         research/map/minimal_set.md
    deps/python/python.exe research/tools/reduce.py all            every step in order; safe to stop and start again

Units (the runtime's SSBU_RB_UNITS, hle_rb_state.c): everything a full save puts back is cut into
  site <ra1> <ra2>   the live blocks of an allocation site (as they lay at the save), to the byte;
  rest <lo> <hi>     the present bytes of an address range in no traced block (16 MB slices at first: the heaps' free
                     memory and other allocators in the alias area, the modules' .data/.bss, stacks, thread-local);
  others             the live blocks of the sites the inventory did not see (transient sites);
  host <part>        kernel tables, fibers, setjmp records, display queue, audio queue, net, ipc.
The threads' host stacks and registers are the load itself (always put back).

A trial removes units ("mode drop": a load leaves their bytes as they are) and passes when, with no crash, the fight
hash AND the reader are identical to the first pass on 3 replays of 60 frames (judge A); the long ring (150 loads) is
judge B, run on the sets that matter. Every trial is one line of research/runs/reduce/trials.jsonl (the units removed,
the judge, the match, the result): a trial already there is not run again, so any step can be stopped and restarted.
"""
import argparse
import collections
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
PY = os.path.join(ROOT, "deps", "python", "python.exe")
OUT = os.path.join(ROOT, "research", "runs", "reduce")
TRIALS = os.path.join(OUT, "trials.jsonl")
UNITS = os.path.join(OUT, "units.json")
STATE = os.path.join(OUT, "search_state.json")
CENSUS = os.path.join(OUT, "census.json")   # (the sites that differ at a load, over several witness runs: research/tools/reduce_census.py)
MAPDIR = os.path.join(ROOT, "research", "map")
# the search's match: two CPUs, Castle 64 with hazards, every item falling
SEARCH = ("items_cpu.txt", "items_cpu_samus_fox", ["SSBU_RULE_POKE=58:ffffffffffffffffffffff"])
VALIDATE = [
    ("items_cpu.txt", "items_cpu_samus_fox", ["SSBU_RULE_POKE=58:ffffffffffffffffffffff"]),   # items, hazards
    ("items_cpu.txt", "items_cpu_four", ["SSBU_RULE_POKE=58:ffffffffffffffffffffff"]),        # 4 players, items
    ("wide.txt", "stadium2_falco_ike", []),                                                    # a stage that transforms
    ("wide.txt", "four_cpu_kalos", []),                                                        # 4 players, hazards
    ("wide.txt", "cpu_marth_megaman", []),                                                     # weapons
    ("wide.txt", "lylat_sephiroth_sora", []),                                                  # a moving stage
    ("wide.txt", "cpu_hero_robin", []),
]
LF_MATCHES = ("lf_castle", "lf_items", "lf_link_samus")   # (judge L: research/matrix/lfi.txt, references in research/runs/lf5_ref)
HOST = ["kernel", "fibers", "setjmp", "vi", "audio", "net", "ipc"]
# the runtime's generation: a trial made with an older mechanism is not reused. 2: the atomic touch of a page left
# whole (generation 1 rewrote a byte in place while the GPU's thread could write the page: hangs one time in two)
GEN = "gen2"
CARVE = [("table1024", 0x710532f490, 0x710532f490 + 0x68100)]   # (the 1,024-entry table in main's .bss)
MIN_REST = 0x10000   # a rest range is not cut below 64 KB
LOCK = threading.Lock()


def area(a):
    if 0x6000000000 <= a < 0x7000000000:
        return "alias"
    if 0x7100000000 <= a < 0x7300000000:
        return "modules"
    if 0x7400000000 <= a < 0x7600000000:
        return "svcheap"
    if 0x7700000000 <= a < 0x7780000000:
        return "stacks"
    if 0x7780000000 <= a < 0x7800000000:
        return "tls"
    return "other"


def spec(u):
    return u["spec"]


# ------------------------------------------------------------------------------------------------ units
def site_family(ra1, ra2, bytes_, gpu, label, fibers, stage):
    key = (ra1, ra2)
    if gpu > 0:   # (any byte in an nvmap allocation: removed, these hang the game about one time in two)
        return "gpu"
    if 0x71014f3000 <= ra1 < 0x71014f6000:
        return "pools"
    if 0x710055c000 <= ra1 < 0x7100560000:
        return "effects"
    if ra1 in (0x7101349620, 0x7101399f34, 0x710141fe44, 0x7101415578):
        return "hud"
    if key in fibers:
        return "fibers"
    if ra1 in stage:
        return "stage"
    if ra1 >= 0x7200000000:
        return "scripts"
    if 0x7108000000 <= ra1 < 0x7200000000:
        return "sdk"
    if label is None:
        return "main:unlabelled"
    if label.startswith("sim state"):
        return "main:sim"
    if label.startswith("other state"):
        return "main:other-state"
    if label.startswith("scratch"):
        return "main:scratch"
    if label.startswith("output"):
        return "main:output"
    return "main:mixed"


def make_units(inv_path):
    labels = {}
    for r in json.load(open(os.path.join(MAPDIR, "sites.json")))["rows"]:
        try:
            a, b = r["site"].split()[:2]
            labels[(int(a, 16), int(b, 16))] = r["label"]
        except ValueError:   # (rows that are no site: "no site ...")
            pass

    def pairs(name):
        out = set()
        for ln in open(os.path.join(MAPDIR, name)):
            p = ln.split("#")[0].split()
            if len(p) == 2:
                out.add((int(p[0], 16), int(p[1], 16)))
        return out
    fibers = pairs("only_sim_sites_fibers.txt") - pairs("only_sim_sites.txt")
    stage = {0x7102606480}
    try:
        txt = open(os.path.join(MAPDIR, "code_reading", "stage_collision.json")).read()
        stage |= {int(x, 16) for x in re.findall(r'"site": "(0x71[0-9a-f]+)', txt)}
    except OSError:
        pass
    units, total = [], 0
    regions = []
    for ln in open(inv_path):
        p = ln.split()
        if p[0] == "site":
            ra1, ra2, blocks, b, g = int(p[1], 16), int(p[2], 16), int(p[3]), int(p[4]), int(p[5])
            fam = site_family(ra1, ra2, b, g, labels.get((ra1, ra2)), fibers, stage)
            units.append({"spec": "site %x %x" % (ra1, ra2), "bytes": b, "family": fam, "blocks": blocks, "gpu": g,
                          "label": labels.get((ra1, ra2))})
            total += b
        elif p[0] == "rest":
            lo, hi, b = int(p[1], 16), int(p[2], 16), int(p[3])
            cuts = [(lo, hi, None)]
            for name, clo, chi in CARVE:   # (a known object in the slice: a unit of its own)
                new = []
                for a, e, nm in cuts:
                    if nm is None and clo < e and chi > a:
                        if a < clo:
                            new.append((a, clo, None))
                        new.append((max(a, clo), min(e, chi), name))
                        if chi < e:
                            new.append((chi, e, None))
                    else:
                        new.append((a, e, nm))
                cuts = new
            for a, e, nm in cuts:
                share = int(b * (e - a) / (hi - lo))
                units.append({"spec": "rest %x %x" % (a, e), "bytes": share, "family": nm or "rest:" + area(lo)})
            total += b
        elif p[0] == "region":
            regions.append((int(p[1], 16), int(p[2], 16)))
    # the rest ranges tile the whole address space: the gaps between the slices are units too (no present byte at
    # the inventory; pages that come later)
    rests = sorted((int(u["spec"].split()[1], 16), int(u["spec"].split()[2], 16)) for u in units if u["spec"].startswith("rest "))
    pos = 0
    for lo, hi in rests + [(1 << 48, 1 << 48)]:
        if lo > pos:
            units.append({"spec": "rest %x %x" % (pos, lo), "bytes": 0, "family": "rest:gaps"})
        pos = max(pos, hi)
    units.append({"spec": "others", "bytes": 0, "family": "sites:unlisted"})
    for h in HOST:
        units.append({"spec": "host " + h, "bytes": 0, "family": "host:" + h})
    present = sum(e - a for a, e in regions)
    json.dump({"units": units, "present_bytes": present, "unit_bytes": total, "inventory": os.path.relpath(inv_path, ROOT)},
              open(UNITS, "w"))
    fam = collections.defaultdict(lambda: [0, 0])
    for u in units:
        fam[u["family"]][0] += 1
        fam[u["family"]][1] += u["bytes"]
    print(f"{len(units)} units; present memory {present / 2**20:.1f} MB, in units {total / 2**20:.1f} MB "
          f"({100 * total / max(1, present):.2f} %)")
    for f, (n, b) in sorted(fam.items(), key=lambda kv: -kv[1][1]):
        print(f"  {f:20} {n:6} units {b / 2**20:9.1f} MB")
    return units


def load_units():
    return json.load(open(UNITS))["units"]


# ------------------------------------------------------------------------------------------------ trials
def trial_key(judge, match, mode, specs, rep=0):
    h = hashlib.sha1(("%s|%s|%s|%s|" % (GEN, judge, match, mode) + ("rep%d|" % rep if rep else "") + "\n".join(sorted(specs))).encode()).hexdigest()[:16]
    return h


def known_trials():
    out = {}
    if os.path.exists(TRIALS):
        for ln in open(TRIALS):
            try:
                t = json.loads(ln)
                out[t["key"]] = t
            except ValueError:
                pass
    return out


KNOWN = None


def ring_reader(path):
    """The reader's verdict on a ring run's dump (numbered by logic frame): every frame run again against its first
    pass. Returns (frames run again, values equal, values different)."""
    import match
    import reader
    rd = reader.Reader()
    first, again, eq, ne = {}, 0, 0, 0
    for f, objs in match.by_frame(path, rd):
        if f not in first:
            first[f] = {i: {m: dict(v) for m, v in d["modules"].items()} for i, d in objs.items()}
            continue
        again += 1
        a = first[f]
        for i in set(a) ^ set(objs):
            ne += 1
        for i in set(a) & set(objs):
            for mod in set(a[i]) | set(objs[i]["modules"]):
                mx, my = a[i].get(mod, {}), objs[i]["modules"].get(mod, {})
                for k in set(mx) | set(my):
                    u, v = mx.get(k), my.get(k)
                    if u == v or (isinstance(u, float) and isinstance(v, float) and struct.pack("<f", u) == struct.pack("<f", v)):
                        eq += 1
                    else:
                        ne += 1
    return again, eq, ne


# REDUCE_EXE=build-trace: the trials and the references run in that build folder (the trace build has what the normal
# build has; its trials are keyed apart, its references kept apart)
EXE = os.environ.get("REDUCE_EXE", "")
REFS = os.path.join(OUT, "refs" + ("_" + EXE if EXE else ""))
UNSEEN = [("wide.txt", "smashville_corrin_mm", []), ("wide.txt", "yoshistory_wiifit_krool", []), ("wide.txt", "cpu_mac_joker", [])]


def ref_run(match_t, which="a"):
    """The reference of a match for judge R: a launch with no rollback at all (same settings, same dump), reduced to
    its digest (refjudge.py). Made twice the first time (a, b), and the two must be identical, or there is no judge."""
    import refjudge
    matrix, name, envs = match_t
    out = os.path.join(REFS, which, name)
    if not os.path.exists(os.path.join(out, "digest.pkl")):
        cmd = [PY, os.path.join(HERE, "matrix.py"), os.path.join(ROOT, "research", "matrix", matrix), "--only", name,
               "--out", os.path.join("reduce", os.path.basename(REFS), which), "--hash", *(["--exe", EXE] if EXE else []), "--override", "stock=99", "--ring", "none",
               "--state", "3,590,2150", "--timeout", "300", "--end", "40s", "--env", "SSBU_STATE_DUMP_LF=1", "--env", "SSBU_FIGHT_HASH_LF=1"]
        for e in envs:
            cmd += ["--env", e]
        subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        refjudge.digest(out)
        for fn in ("state.bin", "state.bin.table"):
            try:
                os.remove(os.path.join(out, fn))
            except OSError:
                pass
        shutil.rmtree(os.path.join(out, "cache"), ignore_errors=True)
        shutil.rmtree(os.path.join(out, "save"), ignore_errors=True)
    return out


def step_refs(a):
    """The references of every validation match, each made twice and compared with itself."""
    jobs = [(m, w) for m in VALIDATE for w in ("a", "b")]
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda j: ref_run(*j), jobs))
    import refjudge
    good = True
    for m in VALIDATE:
        print("reference of", m[1], "against its second launch:")
        r = refjudge.compare(ref_run(m, "a"), ref_run(m, "b"))
        good = good and r["pass"]
    print("references:", "OK, each identical to its second launch" if good else "NOT IDENTICAL")
    return good


def run_trial(judge, match_t, mode, specs, note="", rep=0):
    """A trial, run again (twice at most) when the game hung with no crash ("no frame presented"): removing units
    sometimes hangs the game about one time in five whatever the units (2026-11-12: each of four families passes 6
    times of 6 alone, their union 5 of 6; the witness never hangs), so a hang alone does not say the units are needed.
    The record's "hangs" counts them; three hangs in a row fail."""
    r = run_once(judge, match_t, mode, specs, note, rep)
    hangs = 0
    while (not r["pass"] and "no frame presented" in r.get("why", "") and "host exception" not in r.get("why", "") and hangs < 2):
        hangs += 1
        r = run_once(judge, match_t, mode, specs, note + " (after %d hang%s)" % (hangs, "s" if hangs > 1 else ""), rep + 100 * hangs)
    if hangs:
        r = dict(r, hangs=hangs + (0 if r["pass"] else 1))
        with LOCK:
            HANGS.append((len(specs), hangs, r["pass"]))
    return r


HANGS = []


def run_once(judge, match_t, mode, specs, note="", rep=0):
    """One game. judge 'A': the replay check (save at 600, 60 frames, 3 replays); 'B': the ring, 150 loads.
    Returns the trial's record (from the log when it is already there)."""
    global KNOWN
    matrix, name, envs = match_t
    # (rep: the same trial again, for a result that may not repeat; "L2": judge L's second form, which takes matrix.py's
    # DESYNC as it must - with corrected inputs the ring's frames run again differ from their first pass by design)
    key = trial_key("L2" if judge == "L" else judge, name, mode, specs, rep + (7000 if EXE else 0))
    with LOCK:
        if KNOWN is None:
            KNOWN = known_trials()
        if key in KNOWN:
            return KNOWN[key]
    tdir = os.path.join(OUT, "t_" + key)
    os.makedirs(tdir, exist_ok=True)
    ufile = os.path.join(tdir, "units.txt")
    with open(ufile, "w") as f:
        f.write("mode %s\n" % mode)
        for s in sorted(specs):
            f.write(s + "\n")
        if "others" in specs:   # (the sites the inventory knows and this list does not name)
            named = set(specs)
            for u in load_units():
                if u["spec"].startswith("site ") and u["spec"] not in named:
                    f.write("known" + u["spec"][4:] + "\n")
    cmd = [PY, os.path.join(HERE, "matrix.py"), os.path.join(ROOT, "research", "matrix", matrix), "--only", name,
           "--out", os.path.join("reduce", "t_" + key), "--hash", "--env", "SSBU_RB_UNITS=" + ufile]
    dfile = os.path.join(tdir, "diff.txt")   # (the bytes that differ at each load, by unit: SSBU_RB_UNITS_DIFF)
    try:
        os.remove(dfile)
    except OSError:
        pass
    cmd += ["--env", "SSBU_RB_UNITS_DIFF=" + dfile]
    if EXE:
        cmd += ["--exe", EXE]
    if judge != "L":
        cmd += ["--override", "stock=99", "--env", "SSBU_STATE_DUMP_LF=1"]
    for e in envs:
        cmd += ["--env", e]
    if judge == "L":   # (rollbacks that replay corrected inputs: player 1 by logic frame, netplay's guesses, 150 ring loads)
        cmd += ["--ring", "600,10,9,150", "--timeout", "900", "--end", "45s", "--env", "SSBU_RB_LF_INPUT=7,1,1800,8"]
    elif judge == "A":
        cmd += ["--ring", "none", "--state", "1,590,670", "--timeout", "95", "--end", "25s",
                "--env", "SSBU_RB=1", "--env", "SSBU_RB_VERIFY=600,60,3"]
    elif judge == "R":   # (the ring, then 650 frames more, against a launch with no rollback: research/tools/refjudge.py)
        cmd += ["--ring", "600,6,5,150", "--state", "3,590,2150", "--timeout", "700", "--end", "40s", "--env", "SSBU_FIGHT_HASH_LF=1"]
    else:
        cmd += ["--ring", "600,6,5,150", "--state", "1,590,1520", "--timeout", "480", "--end", "40s"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1500)
        out = p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        out = "TIMEOUT"
    run = os.path.join(tdir, name)
    log = ""
    try:
        log = open(os.path.join(run, "run.log"), errors="replace").read()
    except OSError:
        pass
    verdict = (re.search(r"^\[1/1\] [^:]+: ([A-Z/-]+)", out, re.M) or [None, "NO-RUN"])[1]
    res = {"key": key, "judge": judge, "match": name, "mode": mode, "n": len(specs), "note": note, "verdict": verdict,
           "seconds": round(time.time() - t0, 1), "time": time.strftime("%H:%M:%S")}
    m = re.search(r"SSBU_RB_UNITS: load: (\d+) ranges left alone; (\d+) pages copied in part or not at all, (\d+) bytes left", log)
    if m:
        res["left_bytes_first_load"] = int(m.group(3))
    # the removed units that had differing bytes at a load of this very run (a unit with none changes nothing there)
    if os.path.exists(dfile) and mode == "drop":
        named = set(specs)
        rests = [(int(x.split()[1], 16), int(x.split()[2], 16)) for x in named if x.startswith("rest ")]
        hit, loads_seen = collections.Counter(), 0
        for ln in open(dfile):
            q = ln.split()
            if q[0] == "load":
                loads_seen += 1
                continue
            k = " ".join(q[:3])
            if q[0] == "site" and k in named:
                hit[k] = max(hit[k], int(q[3]))
            elif q[0] == "rest":
                lo, hi = int(q[1], 16), int(q[2], 16)
                if any(a < hi and b > lo for a, b in rests):
                    hit[k] = max(hit[k], int(q[3]))
        res["loads_seen"] = loads_seen
        res["removed_that_differed"] = [len(hit), sum(hit.values())]
        res["removed_that_differed_top"] = [[k, v] for k, v in hit.most_common(400)]
    dump = os.path.join(run, "state.bin")
    ok = False
    if judge == "A":
        good = len(re.findall(r"fight hash: replay \d+ matches the reference on all 60 frames", log))
        res["hash_replays_ok"] = good
        rd_ok, detail = False, ""
        if os.path.exists(dump) and good == 3 and verdict == "OK":
            q = subprocess.run([PY, os.path.join(HERE, "match.py"), "passes", dump], cwd=ROOT, capture_output=True, text=True)
            detail = q.stdout
            reps = re.findall(r"replay \d+: (\d+) frames; (.*)", q.stdout)
            rd_ok = (q.returncode == 0 and len(reps) == 3 and all(int(n) == 60 for n, _ in reps)
                     and "one pass only" not in q.stdout and all(re.search(r"[1-9]\d* equal", r) for _, r in reps))
            res["reader"] = [r for _, r in reps]
        ok = verdict == "OK" and good == 3 and rd_ok
        if not ok:
            res["why"] = ("crash or timeout" if verdict != "OK" else "hash" if good != 3 else "reader") + \
                (": " + "; ".join(re.findall(r"(host exception[^\n]{0,80}|watchdog[^\n]{0,80}|fight hash: replay \d+ DIFFERS[^\n]{0,80})", log)[:2]))
    elif judge == "L":
        ref = os.path.join(ROOT, "research", "runs", "lf5_ref", name, "fight_hash.txt")
        q = subprocess.run([PY, os.path.join(HERE, "lfcompare.py"), ref, os.path.join(run, "fight_hash.txt")], cwd=ROOT, capture_output=True, text=True)
        res["lfcompare"] = q.stdout.strip()[:300]
        m = re.search(r"frames run again in the test: (\d+) .*different: (\d+)", q.stdout)
        ran = verdict in ("OK", "DESYNC")
        ok = bool(ran and q.returncode == 0 and m and int(m.group(1)) > 500 and int(m.group(2)) == 0)
        if not ok:
            res["why"] = "crash or timeout" if not ran else "corrected-input rollbacks differ from the reference"
    elif judge == "R":
        import refjudge
        m = re.search(r"ring test done: (\d+) loads, (\d+) saves; frames run again: (\d+) the same, (\d+) DIFFERENT", log)
        if m:
            res["ring"] = [int(x) for x in m.groups()]
        ran = bool(verdict in ("OK", "DESYNC") and m and int(m.group(1)) >= 150)
        cmp_ = None
        if ran:
            try:
                refjudge.digest(run)
                cmp_ = refjudge.compare(ref_run(match_t), run)
            except Exception as e:
                res["reader_error"] = repr(e)[:160]
        if cmp_:
            res["ref"] = {k: cmp_[k] for k in ("hash_frames", "hash_different", "hash_first", "dump_frames", "values_equal",
                                               "values_different", "modules_one_run_only", "dump_first", "again_hash", "objects_not_compared")}
        ok = bool(ran and cmp_ and cmp_["pass"] and cmp_["again_hash"] > 500 and cmp_["hash_frames"] > 3000 and cmp_["dump_frames"] > 400)
        if not ok:
            how = ("crash" if "host exception" in log else "hang (no frame presented)" if "no frame presented" in log
                   else "timeout with no hang reported (too slow?)")
            res["why"] = how if not ran else "reader error" if not cmp_ else "differs from the run with no rollback" if not cmp_["pass"] else "too little compared"
    else:
        m = re.search(r"ring test done: (\d+) loads, (\d+) saves; frames run again: (\d+) the same, (\d+) DIFFERENT", log)
        if m:
            res["ring"] = [int(x) for x in m.groups()]
        rd_ok = False
        if os.path.exists(dump) and m and verdict == "OK":
            try:
                again, eq, ne = ring_reader(dump)
            except Exception as e:   # (a dump cut short or unreadable: the trial fails, the run goes on)
                again, eq, ne = 0, 0, -1
                res["reader_error"] = repr(e)[:120]
            res["ring_reader"] = [again, eq, ne]
            rd_ok = again >= 300 and eq > 0 and ne == 0
        ok = bool(verdict == "OK" and m and int(m.group(1)) >= 150 and int(m.group(4)) == 0 and int(m.group(3)) > 0 and rd_ok)
        if not ok:
            how = ("crash" if "host exception" in log else "hang (no frame presented)" if "no frame presented" in log
                   else "timeout with no hang reported (too slow?)")
            res["why"] = how if verdict != "OK" else "ring hash" if not (m and int(m.group(4)) == 0) else "ring reader"
    res["pass"] = ok
    for fn in ("state.bin", "state.bin.table", "digest.pkl"):
        if "reader_error" in res:   # (kept, to see why the reader could not read it)
            break
        try:
            os.remove(os.path.join(run, fn))
        except OSError:
            pass
    shutil.rmtree(os.path.join(run, "cache"), ignore_errors=True)
    shutil.rmtree(os.path.join(run, "save"), ignore_errors=True)
    with LOCK:
        with open(TRIALS, "a") as f:
            f.write(json.dumps(dict(res, specs=sorted(specs) if len(specs) <= 40 else None, units_file=os.path.relpath(ufile, ROOT))) + "\n")
        KNOWN[key] = res
    print(f"  [{res['time']}] {judge} {name} {mode} {len(specs)} units ({note}): {'PASS' if ok else 'FAIL ' + res.get('why', '')} "
          f"({res['seconds']} s)", flush=True)
    return res


def run_many(jobs, workers):
    """jobs: [(judge, match, mode, specs, note)] -> results in order, `workers` games at a time."""
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda j: run_trial(*j), jobs))


# ------------------------------------------------------------------------------------------------ steps
def step_inventory(a):
    os.makedirs(OUT, exist_ok=True)
    inv = os.path.join(OUT, "inv.txt")
    if not os.path.exists(inv) or a.force:
        matrix, name, envs = SEARCH
        cmd = [PY, os.path.join(HERE, "matrix.py"), os.path.join(ROOT, "research", "matrix", matrix), "--only", name,
               "--out", os.path.join("reduce", "inventory"), "--hash", "--override", "stock=99", "--ring", "none",
               "--timeout", "240", "--end", "25s", "--env", "SSBU_RB=1", "--env", "SSBU_RB_VERIFY=600,60,3",
               "--env", "SSBU_RB_UNITS_INV=" + inv]
        for e in envs:
            cmd += ["--env", e]
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        print(p.stdout.strip().splitlines()[0] if p.stdout.strip() else p.stderr[-300:])
    make_units(inv)


def step_controls(a):
    units = load_units()
    allspecs = [spec(u) for u in units]
    pool = [spec(u) for u in units if u["spec"].startswith("site 71014f48c0 ")]
    jobs = [("A", SEARCH, "drop", [], "witness: nothing removed"),
            ("A", SEARCH, "keep", allspecs, "control: every unit kept, the rest of memory left as it is"),
            ("A", SEARCH, "keep", [], "negative control: empty list"),
            ("A", SEARCH, "drop", pool, "negative control: the fighters' pool removed")]
    r = run_many(jobs, a.jobs)
    good = r[0]["pass"] and r[1]["pass"] and not r[2]["pass"] and not r[3]["pass"] and pool
    print("controls:", "OK" if good else "NOT AS EXPECTED", [x["pass"] for x in r], "pool units", len(pool))
    return good


def families(units):
    fam = collections.defaultdict(list)
    for u in units:
        fam[u["family"]].append(u)
    return fam


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {"removed": [], "needed": [], "family": {}}


def save_state(st):
    json.dump(st, open(STATE, "w"), indent=1)


def step_families(a):
    units = load_units()
    fam = families(units)
    st = load_state()
    names = sorted(fam, key=lambda f: -sum(u["bytes"] for u in fam[f]))
    res = run_many([("A", SEARCH, "drop", [spec(u) for u in fam[f]], "family " + f) for f in names], a.jobs)
    passing = [f for f, r in zip(names, res) if r["pass"]]
    for f, r in zip(names, res):
        st["family"][f] = {"alone": r["pass"], "units": len(fam[f]), "bytes": sum(u["bytes"] for u in fam[f]), "why": r.get("why")}
    # the families that pass alone, together (the GPU's memory apart: removed with another family it hung the game,
    # 2026-11-12, as SSBU_RB_SKIP_GPU did); if not, the largest first, one more at a time
    late = [f for f in passing if f == "gpu"]
    passing = [f for f in passing if f != "gpu"]
    together = [spec(u) for f in passing for u in fam[f]]
    r = run_trial("A", SEARCH, "drop", together, "the %d passing families together (GPU apart)" % len(passing))
    removed = []
    if r["pass"]:
        removed = together
        for f in passing:
            st["family"][f]["cumulative"] = True
    else:
        for f in passing:
            cand = removed + [spec(u) for u in fam[f]]
            ok = run_trial("A", SEARCH, "drop", cand, "cumulative + " + f)["pass"]
            st["family"][f]["cumulative"] = ok
            if ok:
                removed = cand
    for f in late:   # (three times: a hang that comes one time in two must not pass)
        cand = removed + [spec(u) for u in fam[f]]
        oks = [run_trial("A", SEARCH, "drop", cand, "cumulative + %s, time %d" % (f, k + 1), rep=k + 1)["pass"] for k in range(3)]
        st["family"][f]["cumulative"] = all(oks)
        st["family"][f]["repeats"] = oks
        if all(oks):
            removed = cand
    st["removed"] = sorted(set(st["removed"]) | set(removed))
    save_state(st)
    print(f"families: {len(passing)} of {len(names)} pass alone; removed together: {len(st['removed'])} units")


def split(group):
    """Two halves of a group of units by bytes (a single rest range: by address)."""
    if len(group) == 1:
        u = group[0]
        kind, lo, hi = u["spec"].split()
        lo, hi = int(lo, 16), int(hi, 16)
        mid = (lo + hi) // 2 & ~0xfff
        return ([{"spec": "rest %x %x" % (lo, mid), "bytes": u["bytes"] // 2, "family": u["family"]}],
                [{"spec": "rest %x %x" % (mid, hi), "bytes": u["bytes"] - u["bytes"] // 2, "family": u["family"]}])
    group = sorted(group, key=lambda u: -u["bytes"])
    a, b, sa, sb = [], [], 0, 0
    for u in group:   # (greedy: two halves of about the same size, each with units)
        if (sa <= sb and len(a) <= len(group) // 2 + len(group) % 2) or len(b) > len(group) // 2:
            a.append(u); sa += u["bytes"] + 1
        else:
            b.append(u); sb += u["bytes"] + 1
    if not b:
        b = [a.pop()]
    return a, b


def can_split(group):
    if len(group) > 1:
        return True
    u = group[0]
    if not u["spec"].startswith("rest "):
        return False
    _k, lo, hi = u["spec"].split()
    return int(hi, 16) - int(lo, 16) > MIN_REST


def step_search(a):
    """Inside the families that fail alone: a group of units is removed on top of everything removed so far; if the
    trial passes the whole group is not needed, else it is cut in two (by bytes; a single rest range by address) and
    both halves go back in the queue; a single unit that fails is needed. The queue holds the groups of every family
    and the largest (in bytes) are tried first, `jobs` at a time. The queue, the removed and the needed units are
    saved after every batch (search_state.json): the search restarts where it was."""
    units = load_units()
    by = {spec(u): u for u in units}
    fam = families(units)
    st = load_state()
    removed, needed = set(st["removed"]), set(st["needed"])
    deadline = time.time() + a.minutes * 60 if a.minutes else None

    def unit_of(sp, family):
        return by.get(sp) or {"spec": sp, "bytes": st.get("part_bytes", {}).get(sp, 0), "family": family}
    if "queue" in st:
        queue = [[unit_of(sp, f) for sp in g] for f, g in st["queue"]]
    elif a.seed:   # (groups to try first, [[family, [specs]]]: e.g. those an earlier search removed)
        queue = [[unit_of(sp, f) for sp in g if sp not in removed and sp not in needed] for f, g in json.load(open(a.seed))]
        queue = [g for g in queue if g]
    elif os.path.exists(CENSUS):
        # the sites that differed at a load of the witness runs and are still put back, by family; a unit's weight is
        # its differing bytes (the most at one load), not its size; the sites allocated from 0x710373e524 stay
        # (removed, the game hangs in NVN: research/RESEARCH.md, 2026-11-12) and so does the GPU's family
        cen = json.load(open(CENSUS))
        queue = []
        groups = collections.defaultdict(list)
        for u in units:
            sp = spec(u)
            if (sp.startswith("site ") and sp in cen["seen"] and sp not in removed and sp not in needed
                    and not sp.startswith("site 710373e524 ") and u["family"] != "gpu" and (not a.family or u["family"] in a.family)):
                groups[u["family"]].append(dict(u, bytes=cen["max"].get(sp, 1)))
        for f, g in groups.items():
            queue += list(split(g)) if len(g) > 1 else [g]
        by = {spec(u): u for g in queue for u in g}
    else:
        queue = []
        for f in fam:
            if st["family"].get(f, {}).get("cumulative") or (a.family and f not in a.family):
                continue
            g = [u for u in fam[f] if spec(u) not in removed and spec(u) not in needed]
            if not g:
                continue
            queue += list(split(g)) if can_split(g) else [g]   # (the whole family failed alone: its halves)
    st.setdefault("part_bytes", {})

    def keep_state():
        st["removed"], st["needed"] = sorted(removed), sorted(needed)
        st["queue"] = [[g[0]["family"], [spec(u) for u in g]] for g in queue]
        for g in queue:
            for u in g:
                if spec(u) not in by:
                    st["part_bytes"][spec(u)] = u["bytes"]
        save_state(st)
    size = lambda g: sum(u["bytes"] for u in g)
    while queue:
        if deadline and time.time() > deadline:
            keep_state()
            print("time is up: the search stops here (run it again to go on); %d groups left" % len(queue))
            return False
        queue.sort(key=lambda g: -size(g))
        batch, queue = queue[:a.jobs], queue[a.jobs:]
        base = sorted(removed)
        res = run_many([("A", SEARCH, "drop", base + [spec(u) for u in g],
                         f"{g[0]['family']}: {len(g)} units, {size(g) / 2**20:.2f} MB") for g in batch], a.jobs)
        passed = [g for g, r in zip(batch, res) if r["pass"]]
        if passed and a.reps > 1:   # (a pass may be luck where the failure is a race: the same trial again)
            again = run_many([("A", SEARCH, "drop", base + [spec(u) for u in g], f"{g[0]['family']}: {len(g)} units again, time {k}", k)
                              for g in passed for k in range(1, a.reps)], a.jobs)
            keep = []
            for n, g in enumerate(passed):
                if all(r["pass"] for r in again[n * (a.reps - 1):(n + 1) * (a.reps - 1)]):
                    keep.append(g)
            res = [dict(r, **{"pass": r["pass"] and g in keep}) for g, r in zip(batch, res)]
            passed = keep
        for g, r in zip(batch, res):
            if r["pass"]:
                continue
            if can_split(g):
                x, y = split(g)
                for h in (x, y):
                    for u in h:
                        if spec(u) not in by:
                            st["part_bytes"][spec(u)] = u["bytes"]
                queue += [x, y]
            else:
                needed.add(spec(g[0]))
                st["part_bytes"].setdefault(spec(g[0]), g[0]["bytes"])
        if len(passed) > 1:   # (passed apart, on the same base: together too?)
            both = base + [spec(u) for g in passed for u in g]
            if run_trial("A", SEARCH, "drop", both, f"{len(passed)} groups that passed apart, together")["pass"]:
                removed |= {spec(u) for g in passed for u in g}
            else:
                removed |= {spec(u) for u in passed[0]}
                queue += passed[1:]   # (tried again on the new base)
        elif passed:
            removed |= {spec(u) for u in passed[0]}
        for g in passed:
            for u in g:
                st["part_bytes"].setdefault(spec(u), u["bytes"])
        keep_state()
        left = sum(size(g) for g in queue)
        print(f"    removed {len(removed)} units, needed {len(needed)}, queue {len(queue)} groups ({left / 2**20:.1f} MB undecided)", flush=True)
    keep_state()
    print(f"search done: {len(removed)} units removed, {len(needed)} needed")
    return True


def step_set(a):
    """The candidate set from the census: every site of the inventory that differed at no load of the census
    (census.json) and is not in ever_differ_extra.json (the removed sites that differed in a trial that hung) is
    removed; the host parts stay. Written to the search's state, for validate, search and report."""
    units = load_units()
    cen = json.load(open(CENSUS))
    extra_path = os.path.join(OUT, "ever_differ_extra.json")
    extra = set(json.load(open(extra_path))) if os.path.exists(extra_path) else set()
    differ = set(cen["seen"]) | extra
    static = [u for u in units if spec(u).startswith("site ") and spec(u) not in differ]
    st = load_state()
    st["removed"] = sorted(spec(u) for u in static)
    st["needed"] = ["host fibers"]
    st["static_sites"], st["static_bytes"] = len(static), sum(u["bytes"] for u in static)
    st.pop("queue", None)
    st.pop("validation", None)
    save_state(st)
    print(f"candidate set: {len(static)} sites that never differed removed, {st['static_bytes'] / 2**20:.1f} MB")


def step_judge(a):
    """Judge R (against a launch with no rollback) on the search match: the full restore, the two negative controls,
    then the validated set. Then, with --all, the set on every validation match."""
    removed = list(json.load(open(os.path.join(OUT, "validated_state.json")))["removed"])
    units = load_units()
    pool = [spec(u) for u in units if u["spec"].startswith("site 71014f48c0 ")]
    import refjudge
    print("reference against its second launch:")
    if not refjudge.compare(ref_run(SEARCH, "a"), ref_run(SEARCH, "b"))["pass"]:
        print("the two references differ: no judge")
        return False
    jobs = [("R", SEARCH, "drop", [], "judge R, witness: full restore", 0),
            ("R", SEARCH, "drop", pool, "judge R, negative control: the fighters' pool removed", 0),
            ("R", SEARCH, "keep", [], "judge R, negative control: empty list", 0),
            ("R", SEARCH, "drop", removed, "judge R, the set of 2026-11-12", 0)]
    if a.all:
        step_refs(a)
        jobs += [("R", m, "drop", [], "judge R, witness on " + m[1], 0) for m in VALIDATE[1:]]
        jobs += [("R", m, "drop", removed, "judge R, the set of 2026-11-12 on " + m[1], 0) for m in VALIDATE[1:]]
    res = run_many(jobs, a.jobs)
    for j, r in zip(jobs, res):
        print(f"{j[4]}: {'PASS' if r['pass'] else 'FAIL: ' + str(r.get('why'))}  ring {r.get('ring')}  ref {r.get('ref')}")
    return res


def step_parts(a):
    """The recomputed fields (research/tools/carried.py, research/map/recomputed_parts<suffix>.txt) left alone at every
    load of the ring, judged against a launch with no rollback: on the search match and on three matches no recording
    saw (other fighters, other stages). With --all, the witness (full restore) of each too."""
    parts = [ln.strip() for ln in open(os.path.join(MAPDIR, "recomputed_parts%s.txt" % (a.suffix or ""))) if ln.startswith("part ")]
    ms = [SEARCH] + UNSEEN
    if a.suffix == "_control":   # (the negative control: the carried bytes of the pools, main:sim and the stage left alone; must fail)
        ms = [SEARCH]
    for m in ms:
        ref_run(m)
    jobs = [("R", m, "drop", parts, "recomputed fields left alone on " + m[1], 0) for m in ms]
    if a.all:
        jobs += [("R", m, "drop", [], "witness on " + m[1], 0) for m in ms]
    res = run_many(jobs, a.jobs)
    for j, r in zip(jobs, res):
        print(f"{j[4]}: {'PASS' if r['pass'] else 'FAIL: ' + str(r.get('why'))}  left alone at the first load {r.get('left_bytes_first_load')}  "
              f"ring {r.get('ring')}  ref {r.get('ref')}")
    return res


def step_validate(a):
    st = load_state()
    removed = list(st["removed"])
    jobs = [("B", SEARCH, "drop", removed, "final set, long ring", 0)]
    jobs += [("A", m, "drop", removed, "final set on " + m[1], 0) for m in VALIDATE]
    jobs += [("B", m, "drop", removed, "final set, long ring on " + m[1], 0) for m in VALIDATE[1:]]
    jobs += [("L", ("lfi.txt", n, []), "drop", removed, "final set, corrected-input rollbacks on " + n, 0)
             for n in LF_MATCHES if n not in st.get("skip_L", [])]
    jobs += [("A", SEARCH, "drop", removed, "final set again, time %d" % k, k) for k in (1, 2)]
    res = run_many(jobs, a.jobs)
    st["validation"] = [{"judge": j[0], "match": j[1][1], "pass": r["pass"], "why": r.get("why"), "units": len(removed),
                         "detail": r.get("ring") or r.get("lfcompare") or r.get("reader"),
                         "differed": r.get("removed_that_differed_top")} for j, r in zip(jobs, res)]
    save_state(st)
    print("validation:", sum(1 for r in res if r["pass"]), "of", len(res), "pass")
    return all(r["pass"] for r in res)


TAG = {"main:sim": "gamestate", "pools": "gamestate", "stage": "gamestate",
       "fibers": "glue", "rest:stacks": "glue", "rest:tls": "glue", "nvn-sync": "glue", "host:fibers": "glue", "host:threads": "glue"}


def step_report(a):
    units = load_units()
    meta = json.load(open(UNITS))
    st = load_state()
    cen = json.load(open(CENSUS)) if os.path.exists(CENSUS) else {"seen": {}, "max": {}, "loads": 0, "files": {}}
    removed, needed = set(st["removed"]), set(st["needed"])
    by = {spec(u): u for u in units}
    mb = lambda b: f"{b / 2**20:.2f}"

    def fam_of(u):
        return "nvn-sync" if u["spec"].startswith("site 710373e524 ") else u["family"]
    total = meta["unit_bytes"]
    rem_sites = [by[x] for x in removed if x in by and x.startswith("site ")]
    rem_b = sum(u["bytes"] for u in rem_sites)
    kept = [u for u in units if spec(u) not in removed and not spec(u).startswith("host ")]
    val = st.get("validation", [])
    ok_all = bool(val) and all(v["pass"] for v in val)
    lines = ["# The minimal restore set, by reduction from the full savestate", "",
             f"Written by `research/tools/reduce.py report` at {time.strftime('%Y-%m-%d %H:%M')} (Paris). Journal: `research/RESEARCH.md`, "
             "entries of 2026-11-12 from \"new priority: the minimal restore set\" on. Every trial: `research/runs/reduce/trials.jsonl`.", "",
             "## Where it stands", "",
             f"- A full save puts back **{meta['present_bytes'] / 2**20:.1f} MB** of guest memory. It is cut into {len(units)} units that cover "
             f"100.00 % of it: {sum(1 for u in units if spec(u).startswith('site '))} allocation sites ({mb(sum(u['bytes'] for u in units if spec(u).startswith('site ')))} MB), "
             "the bytes in no traced block, `others` (blocks of sites the inventory did not see), and 7 host parts.",
             f"- At a load, only a few MB of bytes differ from the saved state (5.5 MB on the search match 60 frames after the save). Over "
             f"{len(cen.get('files', {}))} witness runs and {cen['loads']} loads (7 matches, replays and ring), {len(cen['seen'])} sites differed at least once.",
             f"- **Removed: {len(rem_sites)} sites, {mb(rem_b)} MB ({100 * rem_b / total:.1f} % of the memory a full save puts back).** "
             f"The host parts kernel, setjmp, vi, audio, net, ipc can be left alone in the replay check (judge A) but not in the ring: kept. Validation: "
             + ("**every trial passes**." if ok_all else ("see the table below: **not all pass**." if val else "not run yet.")),
             f"- Kept: {mb(sum(u['bytes'] for u in kept))} MB (the sites that differ at some load, the bytes in no block, `others`), the fibers and "
             "the threads' host stacks. The search inside them (which of the differing sites are needed) is not done: see \"To go on\".",
             "- The hang (\"no frame presented\") seen when units are removed is explained: the blocks allocated from `0x710373e524` "
             "(91 sites, 2.13 MB) must be put back, or the main thread spins in an NVN function of the SDK at the frame's end. They are kept (tag: glue).", ""]
    add = os.path.join(MAPDIR, "minimal_set_2026-11-13.md")   # (the day's results on the repaired judge and by read-before-write, written by hand)
    if os.path.exists(add):
        lines += open(add, encoding="utf-8").read().rstrip().splitlines() + [""]
    if val:
        lines += ["## Validation of the removed set", "",
                  "Judge A: save at fight frame 600, 3 replays of 60 frames; B: the ring, 150 loads (5 frames back every 6); L: rollbacks "
                  "that replay corrected inputs (150 ring loads + corrections), against a run with the true inputs. Each: no crash, fight hash and reader identical.", "",
                  "| judge | match | result | detail |", "|---|---|---|---|"]
        for v in val:
            lines.append(f"| {v['judge']} | {v['match']} | {'passes' if v['pass'] else 'FAILS: ' + str(v.get('why'))} | {str(v.get("detail") or "")[:200]} |")
        lines.append("")
    lines += ["## Kept: what a load still puts back", "",
              "Tags: **gamestate** = read by the simulation's code (the access trace's label, the pools, the stage); **glue** = needed for the fight "
              "to go on without being fight information; **unknown** = not decided.", "",
              "| unit or family | units | size, MB | most bytes differing at one load | tag |", "|---|---|---|---|---|"]
    fam = collections.defaultdict(lambda: [0, 0, 0])
    for u in kept:
        if not spec(u).startswith("site "):
            continue
        f = fam_of(u)
        fam[f][0] += 1
        fam[f][1] += u["bytes"]
        fam[f][2] += cen["max"].get(spec(u), 0)
    for f, (n, b, d) in sorted(fam.items(), key=lambda kv: -kv[1][1]):
        lines.append(f"| sites: {f} | {n} | {mb(b)} | {d:,} | {TAG.get(f, 'unknown')} |")
    for ar in ("alias", "modules", "stacks", "tls"):
        us = [u for u in kept if spec(u).startswith("rest ") and u["family"] in ("rest:" + ar, "table1024")
              and area(int(spec(u).split()[1], 16)) == ar]
        lines.append(f"| bytes in no traced block: {ar} | {len(us)} slices | {mb(sum(u['bytes'] for u in us))} | {cen['max'].get('rest:' + ar, 0):,} | "
                     f"{TAG.get('rest:' + ar, 'unknown')} |")
    lines.append(f"| `others`: blocks of sites the inventory did not see ({sum(1 for k in cen['seen'] if k not in by)} such sites differed) | 1 | - | - | unknown |")
    lines.append("| host: fibers (removed alone: crash) | 1 | - | - | glue |")
    lines.append("| host: kernel, setjmp, vi, audio, net, ipc (" + st.get("host_note", "") + ") | 6 | - | - | glue |")
    lines.append("| host: the threads' stacks and registers (the load itself; not removable) | 1 | - | - | glue |")
    lines += ["", "The GPU's family (sites with bytes in nvmap allocations) is kept whole: its sites that differ, removed, hung the game 4 times of 7.", "",
              "## Removed: proven not needed", "", "| family | sites | MB |", "|---|---|---|"]
    fr = collections.defaultdict(lambda: [0, 0])
    for u in rem_sites:
        fr[u["family"]][0] += 1
        fr[u["family"]][1] += u["bytes"]
    for f, (n, b) in sorted(fr.items(), key=lambda kv: -kv[1][1]):
        lines.append(f"| {f} | {n} | {mb(b)} |")
    lines.append(f"| **all** | **{len(rem_sites)}** | **{mb(rem_b)}** |")
    lines += ["", "Read \"proven\" as: an upper bound that the replays confirm on 7 matches and the ring on one of two so far. In each trial "
              "2 to 37 of the removed sites still differed in the trial's own run (the census has not converged), and the long ring is not "
              "passed on every match: until it is, this is a candidate set.", "", "The list of the sites: `research/map/minimal_set_state.json` (`removed`).",
              "What \"proven\" means here: no byte of these sites differed at any of the census's loads, so leaving them alone changes nothing "
              "there; and the validation above ran the fights with them left alone. A site that differs in a situation none of these runs "
              "met (another fighter, another stage) would have to come back: the census is to be widened with every new match.", "",
              "## To go on (everything restarts where it was)", "", "```",
              "deps/python/python.exe research/tools/reduce.py controls --jobs 3    # (after any change of the runtime or the judge: bump GEN in reduce.py first)",
              "# widen the census: add matches to VALIDATE in reduce.py (the lfi.txt matches of judge L are not in it yet), then",
              "# (runs whose census_*.txt exists are not made again: delete research/runs/reduce/census_*.txt to make them anew)",
              "deps/python/python.exe research/tools/reduce_census.py --runs 6 --matches --ring",
              "deps/python/python.exe research/tools/reduce.py set                  # the candidate set from the census (+ ever_differ_extra.json)",
              "deps/python/python.exe research/tools/reduce.py validate --jobs 3    # a trial that hangs lists the removed sites that differed: add them to ever_differ_extra.json, set, validate again",
              "# the search inside the sites that differ (bisection weighted by differing bytes; a hang is run again). Not run yet in this form: untested",
              "deps/python/python.exe research/tools/reduce.py search --jobs 3 --minutes 480",
              "deps/python/python.exe research/tools/reduce.py report", "```", ""]
    open(os.path.join(MAPDIR, "minimal_set.md"), "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    shutil.copyfile(STATE, os.path.join(MAPDIR, "minimal_set_state.json"))
    print("written: research/map/minimal_set.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["inventory", "controls", "families", "set", "search", "validate", "report", "all", "refs", "judge", "parts"])
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--minutes", type=float, default=0, help="search: stop after this long (it restarts where it was)")
    ap.add_argument("--family", action="append", help="search: only these families")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--reps", type=int, default=1, help="search: a group is removed only when it passes this many times")
    ap.add_argument("--seed", help="search: a json file of groups to start from")
    ap.add_argument("--all", action="store_true", help="judge: every validation match too")
    ap.add_argument("--suffix", default="", help="parts: recomputed_parts<suffix>.txt")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.step == "refs":
        return 0 if step_refs(a) else 1
    if a.step == "parts":
        step_parts(a)
        return 0
    if a.step == "judge":
        step_judge(a)
        return 0
    if a.step in ("inventory", "all"):
        step_inventory(a)
    if a.step in ("controls", "all"):
        if not step_controls(a) and a.step == "all":
            print("the controls are not as expected: stop")
            return 1
    if a.step in ("families", "all"):
        step_families(a)
    if a.step == "set":
        step_set(a)
    if a.step in ("search", "all"):
        step_search(a)
    if a.step in ("validate", "all"):
        step_validate(a)
    if a.step in ("report", "all"):
        step_report(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
