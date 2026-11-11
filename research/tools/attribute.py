"""Which allocation sites hold a fight's hot pages? Crosses the state map's hot pages with the live heap blocks.

    deps/python/python.exe research/tools/attribute.py <run folder> <alloc trace prefix> [--top N]

<run folder>/hot_runs.txt (SSBU_RB_SM_DUMP: "<address> <pages> <steady> <gpu pages>") and its .nvmap; <prefix>.live
(SSBU_ALLOC_TRACE: "<address> <size> <frame> <in fight> <site x4>"). Each hot page that is not GPU memory is cut
among the live blocks that overlap it (bytes of the page inside each block); what no block covers is "not from
malloc". Prints the coverage, the split by when blocks were made (before / in the fight), and the top sites by hot
bytes, with their live blocks and sizes. Writes <run folder>/attribution.json.
"""
import argparse
import bisect
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtti  # noqa: E402


def load_hot(run):
    hot = []
    with open(os.path.join(run, "hot_runs.txt")) as f:
        for line in f:
            p = line.split()
            hot.append((int(p[0], 16), int(p[1])))
    gpu = []
    path = os.path.join(run, "hot_runs.txt.nvmap")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                a, n, _h = line.split()
                gpu.append((int(a, 16), int(a, 16) + int(n) * 4096))
    gpu.sort()
    return hot, gpu


def in_ranges(a, rngs, starts):
    i = bisect.bisect_right(starts, a) - 1
    return i >= 0 and rngs[i][0] <= a < rngs[i][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("prefix")
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()
    hot, gpu = load_hot(a.run)
    gstarts = [g[0] for g in gpu]
    blocks = []
    setup = -1
    with open(a.prefix + ".live") as f:
        for line in f:
            p = line.split()
            if p[0] == "#":
                setup = int(p[2])
                continue
            # (address, size, frame, in fight, site, first word)
            blocks.append((int(p[0], 16), int(p[1]), int(p[2]), int(p[3]), tuple(p[5:]), int(p[4], 16)))
    blocks.sort()
    bstarts = [b[0] for b in blocks]
    # the largest block, to bound the backward search
    maxsize = max((b[1] for b in blocks), default=0)

    hot_pages = gpu_pages = covered_pages = 0
    hot_bytes_by_site = collections.Counter()
    hot_blocks_by_site = collections.defaultdict(set)
    bytes_by_when = collections.Counter()
    uncovered = 0
    hot_words = collections.Counter()
    for start, n in hot:
        for k in range(n):
            pg = start + k * 4096
            hot_pages += 1
            if in_ranges(pg, gpu, gstarts):
                gpu_pages += 1
                continue
            pe = pg + 4096
            got = 0
            i = bisect.bisect_left(bstarts, pe) - 1
            while i >= 0 and blocks[i][0] + maxsize > pg:
                b = blocks[i]
                lo, hi = max(pg, b[0]), min(pe, b[0] + b[1])
                if hi > lo:
                    got += hi - lo
                    hot_bytes_by_site[b[4]] += hi - lo
                    hot_blocks_by_site[b[4]].add(b[0])
                    bytes_by_when["in fight" if b[3] else "match load" if setup >= 0 and b[2] >= setup else "boot / menus"] += hi - lo
                    hot_words[b[5]] += hi - lo
                i -= 1
            if got:
                covered_pages += 1
            uncovered += 4096 - min(got, 4096)
    cpu_pages = hot_pages - gpu_pages
    total_hot_cpu_bytes = cpu_pages * 4096
    in_blocks = sum(hot_bytes_by_site.values())
    print(f"hot pages {hot_pages}: GPU memory {gpu_pages}, the rest {cpu_pages} ({total_hot_cpu_bytes >> 20} MB)")
    print(f"  of the rest: {covered_pages} pages touch a live malloc block ({100 * covered_pages // max(1, cpu_pages)}%); "
          f"bytes inside blocks {in_blocks >> 20} MB ({100 * in_blocks // max(1, total_hot_cpu_bytes)}%), "
          f"outside any block {uncovered >> 20} MB")
    print(f"  bytes by when the block was made: {dict((k, v >> 20) for k, v in bytes_by_when.items())} (MB)")
    print(f"  sites holding hot bytes: {len(hot_bytes_by_site)}")
    site_info = {}
    for b in blocks:
        s = site_info.setdefault(b[4], [0, 0, collections.Counter()])
        s[0] += 1; s[1] += b[1]; s[2][b[1]] += 1
    print(f"top {a.top} sites by hot bytes (site = return addresses, innermost first):")
    acc = 0
    rows = []
    for site, by in hot_bytes_by_site.most_common():
        acc += by
        info = site_info[site]
        sizes = ", ".join(f"{sz}x{c}" for sz, c in info[2].most_common(3))
        rows.append({"site": site, "hot_bytes": by, "hot_blocks": len(hot_blocks_by_site[site]), "live_blocks": info[0],
                     "live_bytes": info[1], "sizes": info[2].most_common(5), "cumulative_pct": 100 * acc / max(1, in_blocks)})
        if len(rows) <= a.top:
            print(f"  {by >> 10:7} KB hot ({100 * acc // max(1, in_blocks):3}% cum.) in {len(hot_blocks_by_site[site]):5} of "
                  f"{info[0]:6} live blocks ({info[1] >> 10} KB; sizes {sizes})  {' '.join(site)}")
    print(f"match set-up at frame {setup}")
    names = rtti.Names()
    by_type, by_ns = collections.Counter(), collections.Counter()
    for w, by in hot_words.items():
        t = rtti.demangle_simple(names.name(w)) if 0x7100000000 <= w < 0x7108000000 else None
        if t is None:
            t = "(no RTTI: vptr %#x)" % w if 0x7104f17000 <= w < 0x71052aa000 else "(not an object)"
        by_type[t] += by
        ns = t.split("::")[0] if "::" in t else ("(no RTTI)" if t.startswith("(no RTTI") else t)
        by_ns[ns] += by
    print("hot bytes in malloc blocks, by namespace of the block's type (RTTI of its first word):")
    for ns, by in by_ns.most_common(20):
        print(f"  {by >> 10:7} KB  {ns}")
    print("top types:")
    for t, by in by_type.most_common(40):
        print(f"  {by >> 10:7} KB  {t}")
    with open(os.path.join(a.run, "attribution.json"), "w") as f:
        json.dump({"by_type": by_type, "by_namespace": by_ns, "hot_pages": hot_pages, "gpu_pages": gpu_pages, "cpu_pages": cpu_pages, "covered_pages": covered_pages,
                   "bytes_in_blocks": in_blocks, "bytes_outside": uncovered, "by_when": bytes_by_when, "sites": rows}, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
