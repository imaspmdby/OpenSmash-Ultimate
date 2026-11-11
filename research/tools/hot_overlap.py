"""How alike are the state maps' hot sets of the runs of a matrix? Pairwise overlap of their hot pages (by address).

    deps/python/python.exe research/tools/hot_overlap.py research/runs/<matrix run>

Reads each run's hot_runs.txt ("<first address> <pages> <steady>" a line). Prints each run's hot pages, the pages hot
in every run (the common core), the pages hot in one run only, and the Jaccard index of each pair. Addresses only:
the same address holding other data in two runs counts as overlap, so this is an upper bound of what is shared.
"""
import os
import sys


def load(path):
    pages = set()
    with open(path) as f:
        for line in f:
            a, n = line.split()[:2]
            a, n = int(a, 16), int(n)
            pages.update(range(a >> 12, (a >> 12) + n))
    return pages


def main():
    top = sys.argv[1]
    sets = {}
    for name in sorted(os.listdir(top)):
        p = os.path.join(top, name, "hot_runs.txt")
        if os.path.isfile(p):
            sets[name] = load(p)
    if not sets:
        print("no hot_runs.txt under", top)
        return 1
    names = list(sets)
    union = set().union(*sets.values())
    core = set.intersection(*sets.values())
    print(f"{len(names)} runs; union {len(union)} pages ({len(union) >> 8} MB); hot in every run {len(core)} pages "
          f"({len(core) >> 8} MB)")
    for n in names:
        only = sets[n] - set().union(*(sets[m] for m in names if m != n))
        print(f"  {n:24} {len(sets[n]):6} hot pages ({len(sets[n]) >> 8:3} MB); {len(sets[n] & core) * 100 // max(1, len(sets[n])):3}% "
              f"in the common core; {len(only):6} hot in this run only")
    print("Jaccard (shared / union), %:")
    print(" " * 24 + "".join(f"{i:>5}" for i in range(len(names))))
    for i, a in enumerate(names):
        row = "".join(f"{100 * len(sets[a] & sets[b]) // max(1, len(sets[a] | sets[b])):5}" for b in names)
        print(f"{i:2} {a:21}{row}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
