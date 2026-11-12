"""The test coverage table: which fighters, stages, modes and situations each kind of test has run on.

    deps/python/python.exe research/tools/coverage_table.py [--out research/map/coverage.md]

Read from the runs on this PC (research/runs/<run>/<match>/result.json, written by matrix.py): each match's settings,
the fighter kinds the game set up (the ready-go line: a fighter name the game does not know leaves Mario, kind 0,
and is not counted), the environment of the run (which probes were on) and its verdict. Kinds of test:
  rollback ring      SSBU_RB_RING (every re-run frame's fight hash against its first pass);
  strict oracle      SSBU_RB_VERIFY in build-trace (memory compared after replays, oracle.py);
  access trace       SSBU_MEMTRACE (the colouring);
  reader             SSBU_STATE_DUMP (the reader's dump, checked against the fight hash log);
  automatic check    SSBU_VERIFY_FIELDS (every named field against the game's getter);
  probe              SSBU_PROBE_FIELDS.
Situations: players, CPU against CPU (p1type=cpu), level 9 CPUs, items (the rule's appearance on; items that fall
(SSBU_RULE_POKE); an item handed over (SSBU_GIVE_ITEM)), hazards, the fight's length (from the fight hash log when
there is one). A run of a deleted folder is not counted: the table says what the disk still shows.
"""
import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = os.path.join(ROOT, "research", "runs")
TESTS = (("rollback ring", lambda r, env: bool(r.get("ring")) or "SSBU_RB_RING" in env),
         ("strict oracle", lambda r, env: "SSBU_RB_VERIFY" in env),
         ("access trace", lambda r, env: "SSBU_MEMTRACE" in env),
         ("reader", lambda r, env: "SSBU_STATE_DUMP" in env),
         ("automatic check", lambda r, env: "SSBU_VERIFY_FIELDS" in env),
         ("probe", lambda r, env: "SSBU_PROBE_FIELDS" in env))


def settings(s):
    d = collections.defaultdict(list)
    for kv in s.split(","):
        k, _, v = kv.partition("=")
        d[k.strip()].append(v.strip())
    return d


def main():
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(ROOT, "research", "map", "coverage.md")
    fighters = collections.defaultdict(lambda: collections.defaultdict(set))   # fighter -> test -> runs
    stages = collections.defaultdict(lambda: collections.defaultdict(set))
    situ = collections.defaultdict(lambda: collections.defaultdict(set))
    longest = collections.Counter()
    nruns = 0
    for rj in glob.glob(os.path.join(RUNS, "*", "*", "result.json")):
        try:
            r = json.load(open(rj))
        except (OSError, ValueError):
            continue
        if r.get("verdict") != "OK":
            continue
        run = os.path.basename(os.path.dirname(os.path.dirname(rj))) + "/" + r["name"]
        env = {e.split("=", 1)[0]: e.split("=", 1)[1] if "=" in e else "" for e in r.get("env", [])}
        log = os.path.join(os.path.dirname(rj), "run.log")
        if os.path.exists(log) and os.path.getsize(log) < 50 << 20:
            text = open(log, errors="replace").read()
            for k in ("SSBU_STATE_DUMP", "SSBU_RB_RING", "SSBU_RB_VERIFY"):
                if k not in env and re.search(r"\[(state|rb)\][^\n]*" + {"SSBU_STATE_DUMP": "SSBU_STATE_DUMP:",
                                                                            "SSBU_RB_RING": "ring test done",
                                                                            "SSBU_RB_VERIFY": "SSBU_RB_VERIFY"}[k], text):
                    env[k] = "(from the log)"
        tests = [t for t, f in TESTS if f(r, env)]
        if not tests:
            tests = ["plain run"]
        st = settings(r.get("settings", ""))
        kinds = [x for x in r.get("records", []) if isinstance(x, dict) and x.get("kind", -1) >= 0]
        names = []
        for i in range(4):
            nm = st.get(f"p{i + 1}", [])
            nm = [n for n in nm if n not in ("cpu", "human")]
            k = next((x["kind"] for x in kinds if x["player"] == i), None)
            if nm and k is not None and (k != 0 or nm[-1] == "mario"):
                names.append(nm[-1])
        if not names:
            continue
        nruns += 1
        fh = os.path.join(os.path.dirname(rj), "fight_hash.txt")
        secs = None
        if os.path.exists(fh):
            with open(fh, "rb") as f:
                n = sum(1 for _ in f)
            secs = n / max(1, len(names)) / 60
            longest[run] = secs
        stage = (st.get("stage", ["(the screens' choice)"])[-1]) + (" (hazards off)" if st.get("hazards", [""])[-1] == "off" else "")
        s = []
        s.append(f"{len(names)} players")
        if st.get("p1type", [""])[-1] == "cpu":
            s.append("CPU against CPU")
        if "9" in st.get("cpu", []):
            s.append("level 9 CPU")
        if st.get("items", [""])[-1] == "on":
            s.append("items on (rule)")
        if "SSBU_RULE_POKE" in env:
            s.append("items falling (rule item list set)")
        if "SSBU_GIVE_ITEM" in env:
            s.append("item handed to player 1")
        if st.get("hazards", [""])[-1] == "on":
            s.append("hazards on")
        if secs and secs >= 100:
            s.append("fight of 100 s or more")
        for t in tests:
            for nm in names:
                fighters[nm][t].add(run)
            stages[stage][t].add(run)
            for x in s:
                situ[x][t].add(run)
    cols = [t for t, _f in TESTS] + ["plain run"]

    def table(title, d):
        lines = [f"## {title}", "", "| | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
        for k in sorted(d):
            lines.append(f"| {k} | " + " | ".join(str(len(d[k][c])) if d[k][c] else "" for c in cols) + " |")
        return lines + [""]

    md = ["# Test coverage", "",
          f"Made by `research/tools/coverage_table.py` from the {nruns} runs with verdict OK still on this PC "
          "(research/runs, git-ignored). Each cell: how many runs of that kind of test included it. A fighter is counted "
          "only when the game set it up (a name it does not know leaves Mario). Kinds of test: see the tool's header.", ""]
    md += table(f"Fighters ({len(fighters)})", fighters)
    md += table(f"Stages ({len(stages)})", stages)
    md += table("Situations", situ)
    md += ["## The longest fights", ""] + [f"- {r}: {s:.0f} s" for r, s in longest.most_common(10)] + [""]
    open(out, "w", encoding="utf-8").write("\n".join(md))
    print(f"{nruns} runs, {len(fighters)} fighters, {len(stages)} stages: {out}")


if __name__ == "__main__":
    main()
