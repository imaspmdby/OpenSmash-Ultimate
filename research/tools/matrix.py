"""Phase 1 test bench: every match of a matrix through the rollback oracle.

    deps/python/python.exe research/tools/matrix.py <matrix file> [--out <name>] [--ring F,E,D,N] [--only a,b]

The matrix file has one match a line: `<name> | <SSBU_DEBUG_MATCH settings>` (`#` starts a comment). Each match is run
once (research/runs/<out>/<name>/, a fresh save as in run.sh) with the gate's sequence and settings (fixed seed,
deterministic, 20 s of fight, uncapped) and SSBU_RB_RING: from fight frame F, a load D frames back every E frames,
N times; every re-run frame's fight hash is checked against its first pass. The state map's hot pages at the end of
the fight are written to hot_runs.txt (SSBU_RB_SM_DUMP). Results: result.json per run, summary.json and summary.md.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = os.path.join(ROOT, "research", "runs")


def read_matrix(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            name, _, settings = (x.strip() for x in line.partition("|"))
            out.append((name, settings))
    return out


def parse_log(text):
    r = {"records": [], "ready_go": None, "ring": None, "state_map_start": None, "state_map_end": None,
         "save_ms": None, "load_ms": None, "end_line": False, "first_difference": None, "errors": []}
    for m in re.finditer(r"debug match: player (\d): .*fighter kind (-?\d+), type (\d+)", text):
        r["records"].append({"player": int(m.group(1)), "kind": int(m.group(2)), "type": int(m.group(3))})
    m = re.search(r"\[fight\] fight 1 on \(the game's ready-go\).*?: (p1 kind.*)", text)
    if m:
        r["ready_go"] = m.group(1).strip()
    m = re.search(r"ring test done: (\d+) loads, (\d+) saves; frames run again: (\d+) the same, (\d+) DIFFERENT; "
                  r"save ([\d.]+) ms mean \(max ([\d.]+)\), load ([\d.]+) ms mean \(max ([\d.]+)\)", text)
    if m:
        r["ring"] = {"loads": int(m.group(1)), "saves": int(m.group(2)), "same": int(m.group(3)),
                     "different": int(m.group(4))}
        r["save_ms"] = {"mean": float(m.group(5)), "max": float(m.group(6))}
        r["load_ms"] = {"mean": float(m.group(7)), "max": float(m.group(8))}
    m = re.search(r"state map: on for this fight: (\d+) alias pages cold .*?, (\d+) hot", text)
    if m:
        r["state_map_start"] = {"cold": int(m.group(1)), "hot": int(m.group(2))}
    m = re.search(r"state map now: (\d+) hot alias pages \((\d+) MB\) in (\d+) runs, (\d+) of them steady; (\d+) cold; "
                  r"(\d+) faults opened (\d+) pages, (\d+) opened for the system; (\d+) saves", text)
    if m:
        k = ["hot", "hot_mb", "runs", "steady", "cold", "faults", "opened", "sys_opened", "saves"]
        r["state_map_end"] = dict(zip(k, (int(g) for g in m.groups())))
    m = re.search(r"state map now, GPU memory: (\d+) of the hot pages .*?; (\d+) allocations \((\d+) pages, \d+ MB\), "
                  r"(\d+) of them with a hot page", text)
    if m and r["state_map_end"]:
        r["state_map_end"].update(hot_gpu=int(m.group(1)), nvmap_allocs=int(m.group(2)), nvmap_pages=int(m.group(3)),
                                  nvmap_allocs_hot=int(m.group(4)))
    r["end_line"] = "SSBU_DEBUG_END:" in text
    m = re.search(r"(\[rb\][^\n]*(?:differ|DIFFERENT at)[^\n]*)", text)
    if m and r["ring"] and r["ring"]["different"]:
        r["first_difference"] = m.group(1)[:300]
    for m in re.finditer(r"^.*(?:crash|fault at|stopped:|FAILED|IMPOSSIBLE).*$", text, re.M | re.I):
        if len(r["errors"]) < 10:
            r["errors"].append(m.group(0)[:300])
    return r


def verdict(code, p, settings=""):
    if code != 0 or not p["end_line"]:
        return "CRASH/TIMEOUT"
    m = re.search(r"p1 kind (-?\d+), p2 kind (-?\d+)", p["ready_go"] or "")
    if not m or int(m.group(1)) < 0 or int(m.group(2)) < 0:   # (the record lines show player 2 before the change)
        return "BAD-SETTINGS"
    want = dict(kv.split("=", 1) for kv in settings.split(",") if "=" in kv)
    if int(m.group(1)) == 0 and want.get("p1", "mario") != "mario":   # (an unknown name keeps the menu's Mario)
        return "BAD-SETTINGS"
    if not p["ring"]:
        return "NO-RING"
    if p["ring"]["different"]:
        return "DESYNC"
    return "OK"


def run_one(name, settings, outdir, ring, seq, timeout, extra=(), end="20s"):
    run = os.path.join(outdir, name)
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    shutil.copytree(os.path.join(RUNS, "save_template", "save"), os.path.join(run, "save"))
    env = dict(os.environ)
    env.update({
        "SSBU_DATA_ROOT": run, "SSBU_HEADLESS": "1", "SSBU_SKIP_MOVIES": "1", "SSBU_SPEED": "0",
        "SSBU_FIXED_SEED": "1", "SSBU_DETERMINISTIC": "1", "SSBU_DEBUG_END": end, "SSBU_SEQ": seq,
        "SSBU_DEBUG_MATCH": settings, "SSBU_RB": "1", "SSBU_RB_RING": ring,
        "SSBU_RB_SM_DUMP": os.path.join(run, "hot_runs.txt"),
    })
    env.update(dict(kv.split("=", 1) for kv in extra))
    t0 = time.time()
    with open(os.path.join(run, "run.log"), "wb") as log:
        try:
            p = subprocess.run([os.path.join(ROOT, "build", "ssbu.exe"), os.path.join("dump", "modules")], cwd=ROOT,
                               env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            code = p.returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/F", "/T", "/IM", "ssbu.exe"], capture_output=True)
            code = "timeout"
    secs = round(time.time() - t0, 1)
    with open(os.path.join(run, "run.log"), encoding="utf-8", errors="replace") as f:
        parsed = parse_log(f.read())
    res = {"name": name, "settings": settings, "ring": ring, "env": list(extra), "exit": code, "seconds": secs, **parsed}
    res["verdict"] = verdict(code, parsed, settings)
    with open(os.path.join(run, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    return res


def summary_md(results, ring):
    lines = [f"Ring `{ring}`; extra settings {results[0].get('env') if results else ''}. Hot = the state map's hot alias pages at the end of the fight (4 KB each).", "",
             "| Match | Verdict | Re-run frames same / different | Hot at start | Hot at end (MB) | Steady | Faults | "
             "Hot in GPU memory | Save ms mean (max) | Load ms | Ready-go |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        ring_s = f"{r['ring']['same']} / {r['ring']['different']}" if r["ring"] else "-"
        st = r["state_map_start"]["hot"] if r["state_map_start"] else "-"
        e = r["state_map_end"]
        end = f"{e['hot']} ({e['hot_mb']})" if e else "-"
        sv = f"{r['save_ms']['mean']} ({r['save_ms']['max']})" if r["save_ms"] else "-"
        ld = r["load_ms"]["mean"] if r["load_ms"] else "-"
        lines.append(f"| {r['name']} | {r['verdict']} | {ring_s} | {st} | {end} | {e['steady'] if e else '-'} | "
                     f"{e['faults'] if e else '-'} | {e.get('hot_gpu', '-') if e else '-'} | {sv} | {ld} | {(r['ready_go'] or '-').replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("matrix")
    ap.add_argument("--out", default=None)
    ap.add_argument("--ring", default="600,10,4,50")
    ap.add_argument("--only", default=None)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--override", default="", help="settings added after each match's own (later ones win), e.g. stock=99")
    ap.add_argument("--end", default="20s", help="SSBU_DEBUG_END: the fight's length (20s)")
    ap.add_argument("--env", action="append", default=[], help="VAR=value for the game, repeatable")
    a = ap.parse_args()
    matrix = read_matrix(a.matrix)
    if a.only:
        keep = set(a.only.split(","))
        matrix = [m for m in matrix if m[0] in keep]
    out = os.path.join(RUNS, a.out or "matrix_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(ROOT, "research", "seq", "gate.seq"), encoding="utf-8") as f:
        seq = f.read()
    results = []
    if a.override:
        matrix = [(n, f"{st},{a.override}") for n, st in matrix]
    for i, (name, settings) in enumerate(matrix, 1):
        r = run_one(name, settings, out, a.ring, seq, a.timeout, a.env, a.end)
        results.append(r)
        ring_s = f"{r['ring']['same']} same / {r['ring']['different']} different" if r["ring"] else "no ring result"
        hot = r["state_map_end"]["hot"] if r["state_map_end"] else "?"
        print(f"[{i}/{len(matrix)}] {name}: {r['verdict']} ({ring_s}; {hot} hot pages at the end; {r['seconds']} s)",
              flush=True)
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(summary_md(results, a.ring))
    print("summary:", os.path.join(out, "summary.md"))
    return 0 if all(r["verdict"] == "OK" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
