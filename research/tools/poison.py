"""The judge by poison (2026-11-13 evening): a claim "these bytes are written before they are read after every rollback
safe point" is tested by overwriting them with garbage at every safe point of an ordinary fight (runtime:
SSBU_POISON, hle_memtrace.c), with no load at all, and comparing the fight with the same fight unpoisoned.

    deps/python/python.exe research/tools/poison.py ref <match> [--matrix M]
    deps/python/python.exe research/tools/poison.py run <match> [--matrix M] --file <units file of modfield lines> [--seed N] [--tag T]
    deps/python/python.exe research/tools/poison.py one <match> [--matrix M] --field <Module>:<offset hex>:<length hex> [--seed N]
    deps/python/python.exe research/tools/poison.py sweep <match> [--matrix M] [--units modules|fields] [--jobs N] [--seed N]
    deps/python/python.exe research/tools/poison.py table <match>...

ref: the fight with no poison (research/runs/poison/ref/<match>), CPUs, 40 s, stock 99, normal build.
run: the fight with the file's fields poisoned from fight frame 300 at every safe point. Two observations:
     - the fight hash's lines (every frame, each fighter: status, motion, frame, position, damage, generator);
     - the digest of the carried state (SSBU_DIGEST): every 32-byte piece of the fighters' carried fields
       (research/map/carried_fields.txt), hashed at every safe point; the pieces that hold a poisoned byte are left
       out of the comparison.
     Verdict: SAME (no hash line and no carried piece different to the fight's end), STATE (the hash lines are the
     same, carried pieces differ: the poisoned bytes changed other state the hash does not show), HASH (hash lines
     differ), CRASH / HANG / STOPPED.
one: one field of a module poisoned alone.
sweep: every unit poisoned alone, `--jobs` games at a time, resumable (research/runs/poison/sweep_<match>.jsonl).
     --units modules: all the carried bytes of one module; --units fields: each carried range of live_state.json cut
     at the code reading's field boundaries.
table: the sweeps' results put together by unit over the matches given.
A match is a name of research/matrix/<M> (default items_cpu.txt; --matrix wide.txt, wide2.txt, wide3.txt).
One run is about 25 s; the other threads are not held while the poison is written, so a verdict is repeated
(--seed changes the garbage).
"""
import argparse
import array
import collections
import concurrent.futures
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reduce as R  # noqa: E402
import refjudge  # noqa: E402

OUT = os.path.join(R.ROOT, "research", "runs", "poison")
CARRIED = os.path.join(R.MAPDIR, "carried_fields.txt")
LOCK = threading.Lock()
BASE, START = 200, 300   # the digest's first fight frame, the poison's: frames 200-299 are each run's own control period


def carried_bytes():
    """{(accessor offset, piece offset): set of byte offsets in the piece that are carried} from CARRIED."""
    out = collections.defaultdict(set)
    for o, off, ln in poisoned_ranges(CARRIED):
        for q in range(off, off + ln):
            out[(o, q & ~31)].add(q & 31)
    return out


def series(d, npieces):
    """digest dict -> {fighter: (frames, [values of piece 0], [values of piece 1], ...)}"""
    out = {}
    for k in sorted({key[1] for key in d}):
        fr = sorted(f for (f, kk) in d if kk == k)
        cols = [[d[(f, k)][i] for f in fr] for i in range(npieces)]
        out[k] = (fr, cols)
    return out


def state_compare(sa, sb, npieces, skip=()):
    """The carried pieces of two runs. A piece that already differs in the control period (frames before START)
    holds something given at the launch (an address, a handle): its values are not compared, only whether it changes
    at the same frames. Else its values are compared. -> {(fighter, piece): number of differing frames}, first frame"""
    diff, first = {}, None
    for k in set(sa) & set(sb):
        fa, ca = sa[k]
        fb, cb = sb[k]
        ia = {f: n for n, f in enumerate(fa)}
        common = [(ia[f], n) for n, f in enumerate(fb) if f in ia]
        if not common:
            continue
        base = [(x, y) for x, y in common if fa[x] < START]
        test = [(x, y) for x, y in common if fa[x] >= START]
        for i in range(npieces):
            if i in skip:
                continue
            a, b = ca[i], cb[i]
            if any(a[x] != b[y] for x, y in base):
                bad = [fa[x] for (x, y), (px, py) in zip(test, [base[-1]] + test[:-1] if base else test[:1] + test[:-1])
                       if (a[x] != a[px]) != (b[y] != b[py])]
            else:
                bad = [fa[x] for x, y in test if a[x] != b[y]]
            if bad:
                diff[(k, i)] = len(bad)
                first = bad[0] if first is None else min(first, bad[0])
    return diff, first


def launch(matrix, match, tag, extra):
    run = os.path.join(OUT, tag, match)
    cmd = [R.PY, os.path.join(R.HERE, "matrix.py"), os.path.join(R.ROOT, "research", "matrix", matrix), "--only", match,
           "--out", os.path.join("poison", tag), "--hash", "--override", "stock=99", "--ring", "none", "--timeout", "150", "--end", "40s",
           "--env", "SSBU_FIGHT_HASH_LF=1", "--env", "SSBU_RB=1"]
    if os.path.exists(CARRIED):
        cmd += ["--env", "SSBU_DIGEST=%s,%s,%d" % (CARRIED, os.path.join(OUT, tag, match + ".digest.bin"), BASE)]
    if match.startswith("items_cpu"):
        cmd += ["--env", "SSBU_RULE_POKE=58:ffffffffffffffffffffff"]
    for e in extra:
        cmd += ["--env", e]
    p = subprocess.run(cmd, cwd=R.ROOT, capture_output=True, text=True)
    for d in ("cache", "save"):
        shutil.rmtree(os.path.join(run, d), ignore_errors=True)
    return (p.stdout.strip().splitlines() or [p.stderr[-200:]])[0]


def digest(path):
    """-> pieces [(accessor offset, module offset)], {(fight frame, fighter): array of u32}"""
    if not os.path.exists(path):
        return [], {}
    data = open(path, "rb").read()
    if data[:4] != b"DGF1":
        return [], {}
    n = struct.unpack_from("<I", data, 4)[0]
    pieces = [struct.unpack_from("<II", data, 8 + 8 * i) for i in range(n)]
    off, rec, out = 8 + 8 * n, 16 + 4 * n, {}
    while off + rec <= len(data):
        magic, frame, _lf, k = struct.unpack_from("<IIII", data, off)
        if magic != 0x31474644:
            break
        a = array.array("I")
        a.frombytes(data[off + 16:off + rec])
        out[(frame, k)] = a
        off += rec
    return pieces, out


def poisoned_ranges(path):
    out = []
    for ln in open(path):
        p = ln.split()
        if p and p[0] == "modfield":
            out.append((int(p[1], 16), int(p[2], 16), int(p[3], 16)))
    return out


def hash_diff(ref, test):
    """-> (keys whose state fields differ: status, motion, frame, position, damage; keys where only the generators'
    call count or sum differ: those move at isolated frames between two unpoisoned launches, the fight being the same)"""
    core, rng = [], []
    for k in sorted(k for k in ref if k in test):
        if ref[k] != test[k]:
            (core if ref[k].split(" rngcalls")[0] != test[k].split(" rngcalls")[0] else rng).append(k)
    return core, rng


MODNAME = None


def modname(o):
    global MODNAME
    if MODNAME is None:
        MODNAME = {v: k for k, v in json.load(open(os.path.join(R.MAPDIR, "fields.json")))["boma_offsets"].items()}
    return MODNAME.get(o, "+%#x" % o)


def verdict(match, tag, pfile, quiet=False):
    refd = os.path.join(OUT, "ref", match)
    ref, _ = refjudge.hash_lines(os.path.join(refd, "fight_hash.txt"))
    run = os.path.join(OUT, tag, match)
    test, _ = refjudge.hash_lines(os.path.join(run, "fight_hash.txt"))
    log = open(os.path.join(run, "run.log"), errors="replace").read()
    keys = sorted(k for k in ref if k in test)
    bad, rng_only = hash_diff(ref, test)
    last_ref, last = max(k[0] for k in ref), max([k[0] for k in test] or [0])
    m = re.search(r"\[poison\] first safe point poisoned: fight frame (\d+), (\d+) fighters, (\d+) bytes", log)
    crash = "host exception" in log or "stopped during" in log
    hang = "no frame presented" in log
    ended = "SSBU_DEBUG_END:" in log
    # the carried state's digest; left out: the pieces that hold a poisoned carried byte, and those the references
    # themselves do not agree on
    pieces, da = digest(os.path.join(OUT, "ref", match + ".digest.bin"))
    pieces2, db = digest(os.path.join(OUT, tag, match + ".digest.bin"))
    st = {"pieces": 0, "frames": 0, "different": 0, "pieces_different": 0, "first": None, "modules": {}}
    if pieces and pieces == pieces2:
        skip = set()
        cb = carried_bytes()
        for o, off, ln in (poisoned_ranges(pfile) if pfile else []):
            for i, (po, poff) in enumerate(pieces):
                if po == o and any(off <= poff + q < off + ln for q in cb.get((po, poff), ())):
                    skip.add(i)
        uj = os.path.join(OUT, "ref", match + ".unstable.json")
        if os.path.exists(uj):
            skip |= set(json.load(open(uj))["unstable"])
        st["pieces"] = len(pieces) - len(skip)
        st["frames"] = len(set(da) & set(db))
        # (a piece counts when the run differs there from EVERY reference launch: some pieces take one of a few values
        # from launch to launch, and one reference alone would call that a difference)
        sb = series(db, len(pieces))
        d, first = state_compare(series(da, len(pieces)), sb, len(pieces), skip)
        for t in ["ref%d" % k for k in range(2, NREF + 1)]:
            if not d:
                break
            _p, dr = digest(os.path.join(OUT, t, match + ".digest.bin"))
            if not dr:
                continue
            d2, _f2 = state_compare(series(dr, len(pieces)), sb, len(pieces), skip)
            d = {k: min(n, d2[k]) for k, n in d.items() if k in d2}
        mods = collections.Counter()
        for (_k, i), n in d.items():
            mods[modname(pieces[i][0])] += n
        st.update(different=sum(d.values()), pieces_different=len(d), first=first, modules=dict(mods.most_common(8)))
    if not m and pfile:
        v = "NO POISON WRITTEN"
    elif bad:
        v = "HASH"
    elif crash or hang or not ended or last < last_ref - 4:
        v = "CRASH" if crash else "HANG" if hang else "STOPPED"
    elif st["pieces_different"] >= 2:
        v = "STATE"
    elif st["pieces_different"] == 1:
        v = "STATE?"   # (one piece only: seen in unpoisoned launches too, about one time in two; to be repeated)
    elif pieces and not st["frames"]:
        v = "NO DIGEST"
    else:
        v = "SAME"
    res = {"match": match, "tag": tag, "verdict": v, "lines_compared": len(keys), "lines_different": len(bad),
           "first_difference": bad[0][0] if bad else None, "last_logic_frame": last, "reference_last": last_ref,
           "bytes_poisoned_a_frame": int(m.group(3)) if m else 0, "fighters": int(m.group(2)) if m else 0, "crash": crash, "hang": hang,
           "generator_only_lines": len(rng_only),
           "state": st}
    json.dump(res, open(os.path.join(run, "poison.json"), "w"), indent=1)
    if not quiet:
        print(f"{match} [{tag}]: {v}; {res['bytes_poisoned_a_frame']} bytes poisoned a frame ({res['fighters']} fighters); "
              f"hash lines {len(keys)} compared, {len(bad)} different in state" + (f" (first at logic frame {bad[0][0]})" if bad else "")
              + (f", {len(rng_only)} by the generators' counts alone" if rng_only else "")
              + f"; carried pieces {st['pieces']} over {st['frames']} fighter-frames, {st['different']} piece-frames different in {st['pieces_different']} pieces"
              + (f" (first at fight frame {st['first']}; {st['modules']})" if st["different"] else "")
              + f"; last logic frame {last} of {last_ref}" + ("; crash" if crash else "") + ("; hang" if hang else ""), flush=True)
    return res


NREF = 16   # unpoisoned launches a match's reference is made of


def ensure_ref(matrix, match):
    """The reference: NREF unpoisoned launches (ref, ref2, ...). The carried pieces that differ between any two of them
    depend on the launch (addresses, handles, sound timing) and are no observable: listed in ref/<match>.unstable.json."""
    with LOCK:
        tags = ["ref"] + ["ref%d" % k for k in range(2, NREF + 1)]
        need = [t for t in tags if not os.path.exists(os.path.join(OUT, t, match + ".digest.bin")) or not os.path.exists(os.path.join(OUT, t, match, "fight_hash.txt"))]
        if need:
            with concurrent.futures.ThreadPoolExecutor(4) as ex:
                for line in ex.map(lambda t: launch(matrix, match, t, []), need):
                    print(line, flush=True)
        uj = os.path.join(OUT, "ref", match + ".unstable.json")
        if need or not os.path.exists(uj):
            pieces, base = digest(os.path.join(OUT, "ref", match + ".digest.bin"))
            sbase = series(base, len(pieces))
            bad, hashdiff, rngdiff = collections.Counter(), 0, 0
            h0, _ = refjudge.hash_lines(os.path.join(OUT, "ref", match, "fight_hash.txt"))
            curve = []   # (how many pieces each further launch adds to the unstable ones: the mask's learning curve)
            for t in tags[1:]:
                _p, other = digest(os.path.join(OUT, t, match + ".digest.bin"))
                d, _f = state_compare(sbase, series(other, len(pieces)), len(pieces))
                curve.append(len({i for (_k, i) in d} - set(bad)))
                for (_k, i), n in d.items():
                    bad[i] += n
                h, _ = refjudge.hash_lines(os.path.join(OUT, t, match, "fight_hash.txt"))
                core, rng = hash_diff(h0, h)
                hashdiff += len(core)
                rngdiff += len(rng)
            json.dump({"pieces": len(pieces), "unstable": sorted(bad), "counts": {str(i): n for i, n in bad.items()},
                       "names": sorted({"%s+%#x" % (modname(pieces[i][0]), pieces[i][1]) for i in bad}), "hash_lines_different_between_references": hashdiff,
                       "generator_only_lines_different_between_references": rngdiff, "new_unstable_pieces_by_launch": curve},
                      open(uj, "w"), indent=1)
            print(f"reference of {match}: {NREF} launches; hash lines different between them: {hashdiff} (and {rngdiff} by the generators' counts alone); "
                  f"carried pieces that are not the same from launch to launch: {len(bad)} of {len(pieces)}; new ones added by each further launch: {curve}", flush=True)


def units(kind):
    """The sweep's units from research/map/live_state.json: [(name, [(accessor offset, offset, length)])]."""
    d = json.load(open(os.path.join(R.MAPDIR, "live_state.json")))
    out = []
    for mod, e in sorted(d["modules"]["fighter"].items()):
        if not e.get("size_is_known") or not e["carried"]:
            continue
        o = e["offset_in_accessor"]
        if kind == "modules":
            out.append((mod, [(o, a, n) for a, n in e["carried"]]))
            continue
        cuts = set()
        names = {}
        for f in e.get("fields", []):
            cuts.add(f["off"])
            cuts.add(f["off"] + f["size"])
        for a, n in e["carried"]:
            pts = sorted({a, a + n} | {c for c in cuts if a < c < a + n})
            for x, y in zip(pts, pts[1:]):
                fs = [f for f in e.get("fields", []) if f["off"] < y and f["off"] + f["size"] > x]
                fs.sort(key=lambda f: f["size"])
                nm = (fs[0]["name"] or "").split(" (")[0] if fs else ""
                out.append(("%s+%#x%s" % (mod, x, " " + nm if nm else ""), [(o, x, y - x)]))
    return out


def step_sweep(a):
    us = units(a.units)
    log = os.path.join(OUT, "sweep_%s.jsonl" % a.match)
    done = set()
    if os.path.exists(log):
        for ln in open(log):
            r = json.loads(ln)
            done.add((r["unit"], r["seed"]))
    todo = [u for u in us if (u[0], a.seed) not in done]
    print(f"{len(us)} units ({a.units}), {len(todo)} to run, {a.jobs} games at a time", flush=True)
    ensure_ref(a.matrix, a.match)

    def one(iu):
        i, (name, rngs) = iu
        tag = "sw_%s_%d_%d" % (a.match[:12], a.seed, i)
        os.makedirs(os.path.join(OUT, tag), exist_ok=True)
        pf = os.path.join(OUT, tag, "unit.txt")
        open(pf, "w").write("".join("modfield %x %x %x\n" % r for r in rngs))
        launch(a.matrix, a.match, tag, ["SSBU_POISON=%s,%d" % (pf, a.seed)])
        try:
            r = verdict(a.match, tag, pf, quiet=True)
        except Exception as e:
            r = {"verdict": "ERROR", "error": repr(e)[:200], "state": {}}
        rec = {"unit": name, "seed": a.seed, "ranges": rngs, "bytes": sum(n for _o, _a, n in rngs), "verdict": r["verdict"],
               "lines_different": r.get("lines_different"), "first_difference": r.get("first_difference"),
               "state_different": r.get("state", {}).get("different"), "state_first": r.get("state", {}).get("first"),
               "state_modules": r.get("state", {}).get("modules"), "last_logic_frame": r.get("last_logic_frame")}
        with LOCK:
            open(log, "a").write(json.dumps(rec) + "\n")
            print(f"  {name}: {rec['verdict']}", flush=True)
        shutil.rmtree(os.path.join(OUT, tag), ignore_errors=True)
        return rec
    idx = {u[0]: i for i, u in enumerate(us)}
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(one, [(idx[u[0]], u) for u in todo]))
    c = collections.Counter(r["verdict"] for r in res)
    print("this pass:", dict(c))


FAIL = ("HASH", "CRASH", "HANG", "STOPPED", "STATE")


def read_first_in(match):
    """From the tracker's own runs of this match (research/runs/live/*/<match>.live.txt, the fighters' "mod" lines):
    {(accessor offset, byte offset): marks}. A unit none of whose bytes is read first in the match was not exercised
    there: a poison verdict SAME says nothing about it."""
    import glob
    out = {}
    files = glob.glob(os.path.join(R.ROOT, "research", "runs", "live", "*", match + ".live.txt"))
    for f in files:
        for ln in open(f):
            if ln.startswith("mod "):
                q = ln.split()
                key = int(q[1], 16)
                if key >> 28 or key & 0xffff:
                    continue
                o, off, n, m = key >> 16, int(q[2], 16), int(q[3], 16), int(q[4], 16)
                for b in range(off, off + n):
                    out[(o, b)] = out.get((o, b), 0) | m
            elif ln.startswith("site ") or ln.startswith("rest "):
                break
    return out, len(files)


def sweep_verdicts(match):
    """{unit: [verdicts]} of a match's sweep."""
    out = collections.defaultdict(list)
    p = os.path.join(OUT, "sweep_%s.jsonl" % match)
    if os.path.exists(p):
        for ln in open(p):
            r = json.loads(ln)
            out[r["unit"]].append(r["verdict"])
    return out


def step_narrow(a):
    """The units with no effect in the base match's sweep (--base), on another match: their union poisoned at once;
    a set that fails is cut in two and each half tried, down to single units. A set that passes is harmless there,
    whole. So a match costs a few tens of runs, not one a unit. A set that fails while both its halves pass is
    kept as an interaction. Results: research/runs/poison/narrow_<match>.json (and .jsonl, every trial)."""
    us = dict(units("fields"))
    sv = sweep_verdicts(a.base)
    cand = sorted(u for u in us if sv.get(u) and not any(v in FAIL for v in sv[u]))
    log = os.path.join(OUT, "narrow_%s.jsonl" % a.match)
    print(f"{len(cand)} units with no effect on {a.base}; narrowing on {a.match}, {a.jobs} games at a time", flush=True)
    ensure_ref(a.matrix, a.match)
    counter = [0]

    def trial(names):
        with LOCK:
            counter[0] += 1
            tag = "nw_%s_%d_%d" % (a.match[:12], a.seed, counter[0])
        os.makedirs(os.path.join(OUT, tag), exist_ok=True)
        pf = os.path.join(OUT, tag, "set.txt")
        open(pf, "w").write("".join("modfield %x %x %x\n" % r for n in names for r in us[n]))
        launch(a.matrix, a.match, tag, ["SSBU_POISON=%s,%d" % (pf, a.seed)])
        try:
            r = verdict(a.match, tag, pf, quiet=True)
        except Exception as e:
            r = {"verdict": "ERROR", "error": repr(e)[:200], "state": {}}
        with LOCK:
            open(log, "a").write(json.dumps({"n": len(names), "verdict": r["verdict"], "first_hash": r.get("first_difference"),
                                             "state": r.get("state", {}).get("modules"), "units": names if len(names) <= 8 else None}) + "\n")
            print(f"  {len(names)} units: {r['verdict']}", flush=True)
        shutil.rmtree(os.path.join(OUT, tag), ignore_errors=True)
        return r["verdict"]
    harmless, matters, inter, weak = [], [], [], []
    queue = [cand]
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        while queue:
            vs = list(ex.map(trial, queue))
            nxt = []
            for names, v in zip(queue, vs):
                if v not in FAIL and v != "ERROR":
                    harmless += names
                    if v == "STATE?":
                        weak.append(names if len(names) <= 8 else len(names))
                elif len(names) == 1:
                    matters.append((names[0], v))
                else:
                    h = len(names) // 2
                    nxt += [names[:h], names[h:]]
            queue = nxt
    res = {"match": a.match, "base": a.base, "seed": a.seed, "candidates": len(cand), "harmless": sorted(harmless), "matters": matters,
           "one_piece_only": weak, "trials": counter[0]}
    json.dump(res, open(os.path.join(OUT, "narrow_%s.json" % a.match), "w"), indent=1)
    print(f"{a.match}: of {len(cand)} units with no effect on {a.base}, {len(harmless)} have none here either, {len(matters)} matter here "
          f"({counter[0]} trials): " + ", ".join("%s [%s]" % m for m in matters[:30]), flush=True)


def step_map(a):
    """research/map/gamestate_state.json and research/map/gamestate_fields.md: the fighters' fields in four classes, by
    two instruments. From the tracker (live_state.json): carried / recomputed / constant. From the poison: a carried
    unit MATTERS when, poisoned alone at every safe point, the fight's hash lines or other carried pieces change or
    the game crashes, in at least one match (the base match's sweep, the other matches' narrowing); else it is READ
    WITH NO EFFECT SEEN. The recomputed list is the one the poison holds SAME (research/map/recomputed_fields_v2.txt)."""
    live = json.load(open(os.path.join(R.MAPDIR, "live_state.json")))
    us = dict(units("fields"))
    base = a.matches[0]
    sv = sweep_verdicts(base)
    evidence = collections.defaultdict(dict)   # unit -> {match: verdict}
    for u, vs in sv.items():
        evidence[u][base] = "/".join(vs)
    narrowed = []
    for m in a.matches[1:]:
        pj = os.path.join(OUT, "narrow_%s.json" % m)
        if not os.path.exists(pj):
            continue
        nj = json.load(open(pj))
        narrowed.append(m)
        for u in nj["harmless"]:
            evidence[u][m] = "SAME (in a set)"
        for u, v in nj["matters"]:
            evidence[u][m] = v
    marks = {}
    for m in [base] + narrowed:
        marks[m], _n = read_first_in(m)

    def exercised(rngs):   # the matches of the map where the tracker saw a byte of the unit read first
        return [m for m in marks if any(marks[m].get((o, b), 0) & 1 for o, off, ln in rngs for b in range(off, off + ln))]
    rec = poisoned_ranges(os.path.join(R.MAPDIR, "recomputed_fields_v2.txt"))
    rec_by = collections.defaultdict(list)
    for o, off, ln in rec:
        rec_by[o].append((off, ln))
    out = {"what": step_map.__doc__, "base_match": base, "other_matches": narrowed, "modules": {}}
    tot = collections.Counter()
    L_ = ["# The fighters' state, field by field: what matters to the fight", "",
          "Written by `research/tools/poison.py map`. Two instruments (research/RESEARCH.md, 2026-11-13 evening):",
          "- the tracker (`SSBU_LIVE`, 28 whole fights of 21 matches): which bytes the game reads before writing them after a frame's safe point;",
          "- the poison (`SSBU_POISON`): the bytes overwritten with garbage at every safe point of an ordinary fight, the fight compared with",
          "  16 unpoisoned launches by its hash lines and by a digest of every carried piece (`SSBU_DIGEST`).", "",
          "Classes:",
          "- **state**: carried, and poisoned alone it changes the fight (HASH), other carried state (STATE) or crashes the game (CRASH);",
          "- **read, no effect seen**: read first by the game in a match where it was poisoned alone at every frame, and nothing else changed;",
          "- **not exercised**: carried in some match of the tracker, but never read first in the matches where it was poisoned: nothing is known;",
          "- **recomputed**: written before read after every safe point; all poisoned together at every frame: nothing changes (21 matches);",
          "- **constant**: read, never written in a fight.", "",
          "Base match (every unit alone): `%s`. Other matches (the units with no effect on the base match, narrowed by halves): %s." % (base, ", ".join("`%s`" % m for m in narrowed) or "none yet"),
          "Offsets are in the module object; `+0x..` after a module's name is its offset in the module accessor. Field names are the code reading's.", ""]
    body = []
    for mod, e in sorted(live["modules"]["fighter"].items(), key=lambda kv: kv[1]["offset_in_accessor"]):
        if not e.get("size_is_known"):
            continue
        o = e["offset_in_accessor"]
        mu = [(u, r) for u, r in us.items() if r[0][0] == o and u.split("+")[0] == mod]
        state, noeff, untested, idle = [], [], [], []
        for u, r in sorted(mu, key=lambda x: x[1][0][1]):
            ev = evidence.get(u, {})
            ex = exercised(r)
            item = {"unit": u, "offset": r[0][1], "length": r[0][2], "evidence": ev, "read_first_in": ex}
            if not ev:
                untested.append(item)
            elif any(any(x in v for x in FAIL) for v in ev.values()):
                state.append(item)
            elif any(m in ex for m in ev):
                noeff.append(item)
            else:
                idle.append(item)   # (SAME, but the tracker never saw it read first in the matches it was poisoned in)
        consts = [f for f in e.get("fields", []) if f["class"] == "constant"]
        recs = rec_by.get(o, [])
        b = {"state": sum(i["length"] for i in state), "read_no_effect": sum(i["length"] for i in noeff), "untested": sum(i["length"] for i in untested),
             "not_exercised": sum(i["length"] for i in idle),
             "recomputed": sum(n for _a, n in recs), "constant": e["bytes"].get("constant", 0)}
        tot.update(b)
        tot.update({"units_state": len(state), "units_no_effect": len(noeff), "units_untested": len(untested), "units_not_exercised": len(idle)})
        out["modules"][mod] = {"offset_in_accessor": o, "size": e["size"], "bytes": b, "state": state, "read_no_effect": noeff, "not_exercised": idle, "untested": untested,
                               "recomputed": [[x, n] for x, n in recs], "constant_fields": [[f["off"], f["size"], f["name"]] for f in consts]}

        def show(items):
            return ", ".join("%s (+%#x, %d)%s" % (i["unit"].split(" ", 1)[1] if " " in i["unit"] else "?", i["offset"], i["length"],
                                                 " [%s]" % "; ".join(sorted(set(v.split(" ")[0] for v in i["evidence"].values()))) if i["evidence"] else "") for i in items)
        body += ["## %s (+%#x, %s bytes)" % (mod, o, e["size"]), "",
                 "Bytes: state %d, read with no effect seen %d, not exercised in the matches tried %d, recomputed %d, constant %d%s." % (
                     b["state"], b["read_no_effect"], b["not_exercised"], b["recomputed"], b["constant"], ", not tested yet %d" % b["untested"] if b["untested"] else ""), ""]
        if state:
            body += ["**state** (%d): " % len(state) + show(state), ""]
        if noeff:
            body += ["**read, no effect seen** (%d): " % len(noeff) + show(noeff), ""]
        if idle:
            body += ["**not exercised in the matches tried** (%d): " % len(idle) + show(idle), ""]
        if untested:
            body += ["**not tested yet** (%d): " % len(untested) + show(untested), ""]
        if recs:
            body += ["**recomputed** (%d ranges): " % len(recs) + ", ".join("+%#x..+%#x" % (x, x + n) for x, n in recs[:40]) + (" ..." if len(recs) > 40 else ""), ""]
    L_ += ["**Totals, bytes of a fighter's named modules**: state %d (%d units), read with no effect seen %d (%d units), not exercised in the matches tried %d (%d units), recomputed %d, constant %d%s." % (
        tot["state"], tot["units_state"], tot["read_no_effect"], tot["units_no_effect"], tot["not_exercised"], tot["units_not_exercised"], tot["recomputed"], tot["constant"],
        ", not tested yet %d (%d units)" % (tot["untested"], tot["units_untested"]) if tot["untested"] else ""), ""] + body
    out["totals"] = dict(tot)
    json.dump(out, open(os.path.join(R.MAPDIR, "gamestate_state.json"), "w"))
    open(os.path.join(R.MAPDIR, "gamestate_fields.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L_) + "\n")
    print("totals:", dict(tot))
    print("written: research/map/gamestate_state.json, research/map/gamestate_fields.md")


def step_table(a):
    by = collections.defaultdict(dict)
    for m in a.matches:
        p = os.path.join(OUT, "sweep_%s.jsonl" % m)
        if not os.path.exists(p):
            continue
        for ln in open(p):
            r = json.loads(ln)
            by[r["unit"]].setdefault(m, []).append(r["verdict"])
    tot = collections.Counter()
    for u, d in sorted(by.items()):
        vs = [v for m in d for v in d[m]]
        k = "matters" if any(v in ("HASH", "CRASH", "HANG", "STOPPED", "STATE") for v in vs) else "no effect seen" if vs else "?"
        tot[k] += 1
        print(f"{u:60} {k:15} " + " ".join("%s:%s" % (m[:10], "/".join(d[m])) for m in d))
    print(dict(tot))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["ref", "run", "one", "sweep", "narrow", "table", "map"])
    ap.add_argument("matches", nargs="+")
    ap.add_argument("--matrix", default="items_cpu.txt")
    ap.add_argument("--file")
    ap.add_argument("--field")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag")
    ap.add_argument("--units", default="fields")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--base", default="items_cpu_samus_fox", help="narrow: the match whose sweep gives the units with no effect")
    a = ap.parse_args()
    a.match = a.matches[0]
    os.makedirs(OUT, exist_ok=True)
    if a.step == "table":
        return step_table(a)
    if a.step == "map":
        return step_map(a)
    if a.step == "ref":
        ensure_ref(a.matrix, a.match)
        if a.tag:   # (one more unpoisoned launch, judged like a poisoned one: the known-answer test, must be SAME)
            print(launch(a.matrix, a.match, a.tag, []))
            verdict(a.match, a.tag, None)
        return 0
    ensure_ref(a.matrix, a.match)
    if a.step == "sweep":
        return step_sweep(a)
    if a.step == "narrow":
        return step_narrow(a)
    if a.step == "one":
        mod, off, ln = a.field.split(":")
        bo = json.load(open(os.path.join(R.MAPDIR, "fields.json")))["boma_offsets"][mod]
        tag = a.tag or "one_%s_%s_s%d" % (mod, off, a.seed)
        os.makedirs(os.path.join(OUT, tag), exist_ok=True)
        a.file = os.path.join(OUT, tag, a.match + ".field.txt")
        open(a.file, "w").write("modfield %x %s %s\n" % (bo, off, ln))
    else:
        tag = a.tag or "%s_s%d" % (os.path.splitext(os.path.basename(a.file))[0], a.seed)
    launch(a.matrix, a.match, tag, ["SSBU_POISON=%s,%d" % (os.path.abspath(a.file), a.seed)])
    r = verdict(a.match, tag, a.file)
    return 0 if r["verdict"] == "SAME" else 1


if __name__ == "__main__":
    sys.exit(main())
