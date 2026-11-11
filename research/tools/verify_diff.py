"""What differs in the simulation's lines after a replay (the strict oracle's rb_verify_sim_<round>.txt).

    deps/python/python.exe research/tools/verify_diff.py <rb_verify_sim file> [<alloc prefix>] [--words]

Each line of the file: "<address> class <bits> was <8 words> now <8 words>" (hle_rb_state.c). For every differing
word: its kind (both pointers into guest memory, both small integers, both floats, other), and with an alloc prefix
(SSBU_ALLOC_TRACE of the same run) the block holding the line (site, size, first word: type). Summaries by class,
kind and block. --words prints each differing word.
"""
import bisect
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtti  # noqa: E402

CLASS = {4: "read by sim code", 8: "read in logic phase", 16: "written by sim"}


def kind(a, b):
    def ptr(x):
        return 0x6000000000 <= x < 0x7800000000
    if ptr(a) and ptr(b):
        return "pointer"
    if a < 1 << 32 and b < 1 << 32:
        lo_a, lo_b = a & 0xFFFFFFFF, b & 0xFFFFFFFF
        fa, fb = struct.unpack("<f", struct.pack("<I", lo_a))[0], struct.unpack("<f", struct.pack("<I", lo_b))[0]
        if abs(lo_a - lo_b) < 1 << 16:
            return "small int (diff %d)" % (lo_b - lo_a) if abs(lo_b - lo_a) < 16 else "int"
        if 1e-6 < abs(fa) < 1e7 and 1e-6 < abs(fb) < 1e7:
            return "float"
        return "u32 other"
    return "u64 other"


def main():
    path = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
    show = "--words" in sys.argv
    blocks, starts = [], []
    names = rtti.Names() if prefix else None
    if prefix:
        for line in open(prefix + ".live"):
            if line[0] == "#":
                continue
            p = line.split()
            blocks.append((int(p[0], 16), int(p[1]), int(p[4], 16), " ".join(p[5:8])))
        blocks.sort()
        starts = [b[0] for b in blocks]
    by_class, by_kind, by_block = collections.Counter(), collections.Counter(), collections.Counter()
    n = 0
    for line in open(path):
        p = line.split()
        a, cl = int(p[0], 16), int(p[2], 16)
        was = [int(x, 16) for x in p[4:12]]
        now = [int(x, 16) for x in p[13:21]]
        n += 1
        c = next((v for k, v in CLASS.items() if cl & k), "?")
        by_class[c] += 1
        blk = "-"
        if prefix:
            i = bisect.bisect_right(starts, a) - 1
            if i >= 0 and blocks[i][0] + blocks[i][1] > a:
                b = blocks[i]
                t = rtti.demangle_simple(names.name(b[2])) if 0x7104f17000 <= b[2] < 0x71052aa000 else None
                blk = f"{b[1]} B {t or 'vtable %#x' % b[2] if 0x7104f17000 <= b[2] < 0x71052aa000 else 'data'} site {b[3].split()[0]} +{a - b[0]:#x}"
            else:
                blk = "outside traced blocks"
        for w in range(8):
            if was[w] != now[w]:
                k = kind(was[w], now[w])
                by_kind[k.split(" (")[0]] += 1
                by_block[(blk.split(" +")[0], k.split(" (")[0])] += 1
                if show:
                    print(f"  {a + 8 * w:#x} [{c}] {was[w]:#018x} -> {now[w]:#018x}  {k}  {blk}")
    print(f"{n} differing lines; by class: {dict(by_class)}")
    print(f"differing words by kind: {dict(by_kind)}")
    print("by block and kind (top 25):")
    for (b, k), m in by_block.most_common(25):
        print(f"  {m:5}  {k:12} {b}")


if __name__ == "__main__":
    main()
