"""The judge by poison (2026-11-13 evening): a claim "these bytes are written before they are read after every rollback
safe point" is tested by overwriting them with garbage at every safe point of an ordinary fight (runtime:
SSBU_POISON, hle_memtrace.c), with no load at all, and comparing the fight with the same fight unpoisoned.

    deps/python/python.exe research/tools/poison.py ref <match> [--matrix M]
    deps/python/python.exe research/tools/poison.py run <match> [--matrix M] --file <units file of modfield lines> [--seed N] [--tag T]
    deps/python/python.exe research/tools/poison.py one <match> [--matrix M] --field <Module>:<offset hex>:<length hex> [--seed N]

ref: the fight with no poison (research/runs/poison/ref/<match>/fight_hash.txt), CPUs, 40 s, stock 99, normal build.
run: the fight with the file's fields poisoned from fight frame 300 at every safe point. Verdict from the fight hash's
     lines (every frame, both fighters: status, motion, frame, position, damage, generator): SAME (0 line different
     to the fight's end), DIFFERENT (how many, the first logic frame) or CRASH / HANG (the last logic frame reached).
     The reader is not used: a poisoned field differs for it by construction.
one: one field of a module poisoned alone (the judge's sensitivity: a carried field must not come out SAME).
A match is a name of research/matrix/<M> (default items_cpu.txt; --matrix wide.txt, wide2.txt, wide3.txt).
One run is about 25 s; the other threads are not held while the poison is written, so a verdict is repeated
(--seed changes the garbage).
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reduce as R  # noqa: E402
import refjudge  # noqa: E402

OUT = os.path.join(R.ROOT, "research", "runs", "poison")


def launch(a, tag, extra):
    cmd = [R.PY, os.path.join(R.HERE, "matrix.py"), os.path.join(R.ROOT, "research", "matrix", a.matrix), "--only", a.match,
           "--out", os.path.join("poison", tag), "--hash", "--override", "stock=99", "--ring", "none", "--timeout", "150", "--end", "40s",
           "--env", "SSBU_FIGHT_HASH_LF=1", "--env", "SSBU_RB=1"]
    if a.match.startswith("items_cpu"):
        cmd += ["--env", "SSBU_RULE_POKE=58:ffffffffffffffffffffff"]
    for e in extra:
        cmd += ["--env", e]
    p = subprocess.run(cmd, cwd=R.ROOT, capture_output=True, text=True)
    return (p.stdout.strip().splitlines() or [p.stderr[-200:]])[0]


def verdict(a, tag):
    ref, _ = refjudge.hash_lines(os.path.join(OUT, "ref", a.match, "fight_hash.txt"))
    run = os.path.join(OUT, tag, a.match)
    test, _ = refjudge.hash_lines(os.path.join(run, "fight_hash.txt"))
    log = open(os.path.join(run, "run.log"), errors="replace").read()
    keys = sorted(k for k in ref if k in test)
    bad = [k for k in keys if ref[k] != test[k]]
    last_ref, last = max(k[0] for k in ref), max([k[0] for k in test] or [0])
    m = re.search(r"\[poison\] first safe point poisoned: fight frame (\d+), (\d+) fighters, (\d+) bytes", log)
    crash = "host exception" in log or "stopped during" in log
    hang = "no frame presented" in log
    ended = "SSBU_DEBUG_END:" in log
    if not m:
        v = "NO POISON WRITTEN"
    elif bad:
        v = "DIFFERENT"
    elif crash or hang or not ended or last < last_ref - 2:
        v = "CRASH" if crash else "HANG" if hang else "STOPPED"
    else:
        v = "SAME"
    res = {"match": a.match, "tag": tag, "verdict": v, "lines_compared": len(keys), "lines_different": len(bad),
           "first_difference": bad[0][0] if bad else None, "last_logic_frame": last, "reference_last": last_ref,
           "bytes_poisoned_a_frame": int(m.group(3)) if m else 0, "fighters": int(m.group(2)) if m else 0, "crash": crash, "hang": hang}
    json.dump(res, open(os.path.join(run, "poison.json"), "w"), indent=1)
    print(f"{a.match} [{tag}]: {v}; {res['bytes_poisoned_a_frame']} bytes poisoned a frame ({res['fighters']} fighters); "
          f"{len(keys)} hash lines compared, {len(bad)} different" + (f", first at logic frame {bad[0][0]}" if bad else "")
          + f"; last logic frame {last} of {last_ref}" + ("; crash" if crash else "") + ("; hang" if hang else ""), flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["ref", "run", "one"])
    ap.add_argument("match")
    ap.add_argument("--matrix", default="items_cpu.txt")
    ap.add_argument("--file")
    ap.add_argument("--field")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag")
    a = ap.parse_args()
    if a.step == "ref":
        print(launch(a, "ref", []))
        return 0
    if not os.path.exists(os.path.join(OUT, "ref", a.match, "fight_hash.txt")):
        print(launch(a, "ref", []))
    if a.step == "one":
        mod, off, ln = a.field.split(":")
        bo = json.load(open(os.path.join(R.MAPDIR, "fields.json")))["boma_offsets"][mod]
        tag = a.tag or "one_%s_%s_s%d" % (mod, off, a.seed)
        os.makedirs(os.path.join(OUT, tag), exist_ok=True)
        a.file = os.path.join(OUT, tag, a.match + ".field.txt")
        open(a.file, "w").write("modfield %x %s %s\n" % (bo, off, ln))
    else:
        tag = a.tag or "%s_s%d" % (os.path.splitext(os.path.basename(a.file))[0], a.seed)
    launch(a, tag, ["SSBU_POISON=%s,%d" % (os.path.abspath(a.file), a.seed)])
    r = verdict(a, tag)
    return 0 if r["verdict"] == "SAME" else 1


if __name__ == "__main__":
    sys.exit(main())
