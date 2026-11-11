"""The hot heap memory outside every live traced block: what is it?

    deps/python/python.exe research/tools/unknown.py <run folder>

Needs one run of build-trace with the ring, the probes and the access trace (hot_runs.txt + .nvmap, alloc.live,
alloc.freed when the tracer wrote it, mt.bin). For each 64-byte line of the hot non-GPU pages that no live block
holds: its trace class, the code that wrote it last (function, category), its place in its 2 MB chunk, and, with
alloc.freed, whether a block freed during the fight covered it (churn: memory used and given back).
"""
import bisect
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import code_cats  # noqa: E402
import memtrace  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    run = sys.argv[1]
    hot = []
    for line in open(os.path.join(run, "hot_runs.txt")):
        p = line.split()
        a = int(p[0], 16)
        hot.extend(range(a, a + int(p[1]) * 4096, 4096))
    gpu = sorted((int(a, 16), int(a, 16) + int(n) * 4096) for a, n, _h in
                 (line.split() for line in open(os.path.join(run, "hot_runs.txt.nvmap"))))
    gs = [g[0] for g in gpu]

    def is_gpu(a):
        i = bisect.bisect_right(gs, a) - 1
        return i >= 0 and gpu[i][0] <= a < gpu[i][1]

    blocks = []
    for line in open(os.path.join(run, "alloc.live")):
        if line[0] == "#":
            continue
        p = line.split()
        blocks.append((int(p[0], 16), int(p[1])))
    blocks.sort()
    bs = [b[0] for b in blocks]
    freed = {}
    fp = os.path.join(run, "alloc.freed")
    if os.path.exists(fp):
        for line in open(fp):
            p = line.split()
            freed[int(p[0], 16)] = (p[1], int(p[2]), int(p[3]))   # page -> last site, its size, frees
    _fr, _th, lines = memtrace.load(os.path.join(run, "mt.bin"))
    L = {x[0]: x for x in lines}
    em = memtrace.ExeMap(os.path.join(ROOT, "build-trace", "ssbu.map"))
    cn = code_cats.CATS

    def in_block(a):
        i = bisect.bisect_right(bs, a + 63) - 1
        return i >= 0 and blocks[i][0] + blocks[i][1] > a

    cpu = [a for a in hot if not is_gpu(a)]
    tot = out = 0
    cls, writers, wcat, chunk_pos, churn = (collections.Counter() for _ in range(5))
    pages_out = collections.Counter()
    for pg in cpu:
        for a in range(pg, pg + 4096, 64):
            tot += 1
            if in_block(a):
                continue
            out += 1
            pages_out[pg] += 1
            x = L.get(a)
            if x is None:
                cls["not touched in the window"] += 1
            else:
                cls[memtrace.klass(x[1], x[2], x[3], x[4])] += 1
                if x[7] not in (0, 0xFFFFFFFF):
                    writers[em.name(x[7])] += 1
                for i in range(14):
                    if x[10] >> i & 1:
                        wcat[cn[i]] += 1
            off = a & 0x1FFFFF
            chunk_pos["first 64 KB of a 2 MB chunk" if off < 0x10000 else "rest of the chunk"] += 1
            if freed:
                churn["a block freed in the fight covered its page" if pg in freed else "no free seen on its page"] += 1
    print(f"hot non-GPU pages {len(cpu)} ({len(cpu) * 4 >> 10} MB); lines outside every live block {out} of {tot} "
          f"({out * 64 >> 10} KB, {100 * out // max(1, tot)} %); pages wholly outside {sum(1 for v in pages_out.values() if v == 64)}, "
          f"partly {sum(1 for v in pages_out.values() if v < 64)}")
    for title, c in (("trace class", cls), ("place", chunk_pos), ("churn", churn), ("writer category (each)", wcat)):
        if c:
            print(f"  by {title}: " + ", ".join(f"{k} {v * 64 >> 10} KB" for k, v in c.most_common(8)))
    print("  top writers:")
    for fn, n in writers.most_common(12):
        print(f"    {n * 64 >> 10:6} KB  {fn}")
    if freed:
        sites = collections.Counter()
        for pg, v in pages_out.items():
            if pg in freed:
                sites[(freed[pg][0], freed[pg][1])] += v
        print("  freed blocks' sites on those pages (last free of the page: site, size), top 12:")
        for (s, sz), n in sites.most_common(12):
            print(f"    {n * 64 >> 10:6} KB  site {s}  {sz} B")


if __name__ == "__main__":
    main()
