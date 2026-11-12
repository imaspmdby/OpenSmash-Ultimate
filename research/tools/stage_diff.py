"""Where a stage's own state lies: the allocation sites whose state differs between runs that differ by the stage.

    deps/python/python.exe research/tools/stage_diff.py <sites.json> <run A> <run B> [<run C>...] [--min KB]

<sites.json> from sites.py over the runs. Prints the (site, size) rows whose state (any of the three state classes)
is at least --min KB (default 1) larger in run A than in every other run named: e.g. A = Castle 64 with hazards, B =
the same with hazards off (the control: same stage data, the moving parts stopped), C = Final Destination. A row
present in A only is marked "A only". Also prints the rows whose state is in A and B but in no C: the stage's own
state whatever the hazards.
"""
import json
import sys


def state_kb(p):
    return sum(v for c, v in p["KB"].items() if c.endswith("state"))


def main():
    args = [a for a in sys.argv[1:]]
    mn = 1.0
    if "--min" in args:
        i = args.index("--min")
        mn = float(args[i + 1])
        del args[i:i + 2]
    tab = json.load(open(args[0]))
    a, others = args[1], args[2:]
    rows = []
    both = []
    for t in tab["rows"]:
        per = t["per run"]
        sa = state_kb(per[a]) if a in per else 0
        so = [state_kb(per[o]) if o in per else 0 for o in others]
        if sa - max(so) >= mn:
            rows.append((sa - max(so), t, sa, so))
        if len(others) >= 2 and a in per and others[0] in per and min(sa, so[0]) >= mn and all(x == 0 for x in so[1:]):
            both.append((min(sa, so[0]), t, sa, so))
    print(f"rows whose state is >= {mn} KB larger in {a} than in {', '.join(others)}: {len(rows)}, "
          f"{sum(r[0] for r in rows):.1f} KB")
    for d, t, sa, so in sorted(rows, key=lambda r: -r[0])[:40]:
        p = t["per run"][a]
        print(f"  {d:8.1f}  {t['site']:28} {t['size']:>9}  {a} {sa:.1f} | " + " ".join(f"{x:.1f}" for x in so) +
              f"  {'A only' if not any(o in t['per run'] for o in others) else ''}  readers {' '.join(p['readers'][:2])}"
              f"  writers {' '.join(p['writers'][:2])}  made {p['made']}  cats {p['reader categories'][:3]}")
    if len(others) >= 2:
        print(f"\nrows with state in {a} and {others[0]} but none in {', '.join(others[1:])}: {len(both)}, "
              f"{sum(r[0] for r in both):.1f} KB")
        for d, t, sa, so in sorted(both, key=lambda r: -r[0])[:30]:
            p = t["per run"][a]
            print(f"  {d:8.1f}  {t['site']:28} {t['size']:>9}  {sa:.1f} | {so[0]:.1f}  readers {' '.join(p['readers'][:2])}"
                  f"  cats {p['reader categories'][:3]}")


if __name__ == "__main__":
    main()
