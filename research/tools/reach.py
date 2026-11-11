"""Reachability from the fighters' bomas (SSBU_REACH), by depth and by type, against the hot pages.

    deps/python/python.exe research/tools/reach.py <run folder> <prefix>

Needs <prefix>.reach, <run>/hot_runs.txt (+ .nvmap) and <run>/types.json (objtypes.py: the module vptrs). A granule's
type is its first word's: RTTI, a boma module, or the neighbouring-vtable namespace (~), else "data" (no vptr).
Prints, per depth: granules, MB, the hot pages they cover (cumulative), and their types by namespace; then the
edges that first enter each namespace (parent type -> child type), and the hot pages never reached.
"""
import bisect
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtti  # noqa: E402


def main():
    run, prefix = sys.argv[1], sys.argv[2]
    names = rtti.Names()
    tj = json.load(open(os.path.join(run, "types.json")))
    modv = {int(k, 16): v for k, v in tj["module_vptrs"].items()}
    cache = {}

    def typ(w):
        if w in cache:
            return cache[w]
        t = "data"
        if 0x7104f17000 <= w < 0x71052aa000:
            r = rtti.demangle_simple(names.name(w))
            t = r or modv.get(w) or "vtable?"
        cache[w] = t
        return t

    def ns(t):
        if t == "data" or t == "vtable?":
            return t
        return t.split("::")[0]

    gr = []
    root_label = {}
    with open(prefix + ".reach") as f:
        for line in f:
            if line.startswith("#"):
                _h, _r, r, lab, _addr = line.split()
                root_label[int(r)] = lab
                continue
            a, ln, d, root, parent, w0 = line.split()
            gr.append((int(a, 16), int(ln), int(d), int(root), int(parent, 16), int(w0, 16)))
    by_addr = {g[0]: g for g in gr}
    hot = set()
    with open(os.path.join(run, "hot_runs.txt")) as f:
        for line in f:
            p = line.split()
            a, n = int(p[0], 16), int(p[1])
            hot.update(range(a >> 12, (a >> 12) + n))
    gpu = []
    with open(os.path.join(run, "hot_runs.txt.nvmap")) as f:
        for line in f:
            a, n, _h = line.split()
            gpu.append((int(a, 16) >> 12, (int(a, 16) >> 12) + int(n)))
    gpu.sort()
    gs = [g[0] for g in gpu]

    def is_gpu(pg):
        i = bisect.bisect_right(gs, pg) - 1
        return i >= 0 and gpu[i][0] <= pg < gpu[i][1]

    hot_cpu = {p for p in hot if not is_gpu(p)}
    print(f"{len(gr)} granules reached; hot pages {len(hot)}, of them not GPU memory {len(hot_cpu)}")
    covered = set()
    per_depth = collections.defaultdict(lambda: [0, 0, collections.Counter()])
    page_depth = {}
    for a, ln, d, root, parent, w0 in gr:
        e = per_depth[d]
        e[0] += 1
        e[1] += ln
        e[2][ns(typ(w0))] += ln
        for pg in range(a >> 12, (a + ln - 1 >> 12) + 1):
            if pg not in page_depth or d < page_depth[pg]:
                page_depth[pg] = d
    print("depth  granules      MB  hot non-GPU pages reached (cumulative)  bytes by type of granule")
    for d in sorted(per_depth):
        n, by, nsc = per_depth[d]
        covered |= {p for p, pd in page_depth.items() if pd == d and p in hot_cpu}
        top = ", ".join(f"{k} {v >> 10} KB" for k, v in nsc.most_common(5))
        print(f"{d:5} {n:9} {by / 2**20:7.1f}  {len(covered):6} ({100 * len(covered) // max(1, len(hot_cpu)):3}%)   {top}")
    print(f"hot non-GPU pages never reached from the fighters: {len(hot_cpu - set(page_depth))}")

    # where the walk first enters each namespace: parent type -> child type, by bytes
    entries = collections.Counter()
    first_seen = {}
    for a, ln, d, root, parent, w0 in sorted(gr, key=lambda g: g[2]):
        c = ns(typ(w0))
        if c in first_seen and first_seen[c] < d:
            continue
        first_seen.setdefault(c, d)
    print("first depth each namespace is reached:", dict(sorted(first_seen.items(), key=lambda x: x[1])))
    cross = collections.Counter()
    for a, ln, d, root, parent, w0 in gr:
        p = by_addr.get(parent)
        pt = ns(typ(p[5])) if p else "boma"
        ct = ns(typ(w0))
        if pt != ct:
            cross[(pt, ct)] += 1
    print("edges between namespaces (parent granule -> child granule), top 20:")
    for (pt, ct), n in cross.most_common(20):
        print(f"  {n:7}  {pt} -> {ct}")
    # by root family: the hot non-GPU pages whose nearest root it is, within depth 3, 6 and 12
    fam = lambda root: root_label.get(root // 1024, "fighter%d" % (root // 1024 + 1)).rstrip("0123456789") if root_label.get(root // 1024, "").startswith("fighter") else root_label.get(root // 1024, "?")
    best = {}
    for a, ln, d, root, parent, w0 in gr:
        for pg in range(a >> 12, (a + ln - 1 >> 12) + 1):
            if pg in hot_cpu and (pg not in best or d < best[pg][0]):
                best[pg] = (d, fam(root))
    print("hot non-GPU pages by their nearest root family (cumulative by depth):")
    fams = collections.Counter(f for _d, f in best.values())
    for f_, total in fams.most_common():
        row = [sum(1 for d, ff in best.values() if ff == f_ and d <= k) for k in (2, 3, 4, 6, 12)]
        print(f"  {f_:16} depth<=2 {row[0]:5}  <=3 {row[1]:5}  <=4 {row[2]:5}  <=6 {row[3]:5}  <=12 {row[4]:5}")
    print(f"  {'(none)':16} {len(hot_cpu) - len(best)} never reached")
    # which boma words (modules) lead the most hot pages at a shallow depth (<= 4)
    lead = collections.Counter()
    tj_off = {int(k, 16): v for k, v in tj["module_offsets"].items()}
    for a, ln, d, root, parent, w0 in gr:
        if d <= 4 and root % 1024 != 1023:
            pages = {pg for pg in range(a >> 12, (a + ln - 1 >> 12) + 1)} & hot_cpu
            lead[tj_off.get((root % 1024) * 8, f"boma+{(root % 1024) * 8:#x}")] += len(pages)
    print("hot non-GPU pages within depth 4, by the boma word the path left by (module), top 25:")
    for k, n in lead.most_common(25):
        print(f"  {n:6}  {k}")


if __name__ == "__main__":
    main()
