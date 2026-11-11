"""Colour memory by how the game's code uses it across frames (SSBU_MEMTRACE, a build with /DSSBU_MEMTRACE).

    deps/python/python.exe research/tools/memtrace.py <trace file> [<alloc prefix>]

Each 64-byte line the code touched in the window gets a class:
  state     read first in some frame after a write in an earlier frame (its value crosses a frame boundary);
  scratch   written and read, but never read first after a write in an earlier frame (rebuilt each frame);
  output    written, never read by the game's code (read by the host: GPU, audio, or not at all);
  constant  read, never written in the window.
Prints the classes by memory area and by thread (the threads' guest entry points), and with an alloc prefix
(SSBU_ALLOC_TRACE of the same run) the state lines by allocation site and by the type of their block (RTTI / boma
modules / data). Writes <trace>.json.
"""
import bisect
import collections
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtti  # noqa: E402


def area(a):
    if 0x6000000000 <= a < 0x7000000000:
        return "alias (game heap, GPU memory)"
    if 0x7100000000 <= a < 0x7108000000:
        return "main's data / bss"
    if 0x7108000000 <= a < 0x7400000000:
        return "other modules' data"
    if 0x7400000000 <= a < 0x7600000000:
        return "heap (svcSetHeapSize)"
    if 0x7700000000 <= a < 0x7780000000:
        return "guest stacks"
    if 0x7780000000 <= a < 0x7790000000:
        return "thread-local"
    return "other"


def load(path):
    check_map(path)
    data = open(path, "rb").read()
    assert data[:4] in (b"MT1\0", b"MT2\0", b"MT3\0", b"MT4\0", b"MT5\0"), "not a memtrace file"
    ver = data[2] - ord("0")
    globals()["ver"] = ver
    frames, nt = struct.unpack_from("<II", data, 4)
    off = 12
    threads = []
    for _ in range(nt):
        tid = struct.unpack_from("<I", data, off)[0]
        name = data[off + 4:off + 64].split(b"\0")[0].decode("utf-8", "replace")
        threads.append((tid, name))
        off += 64
    no = 0xFFFFFFFF
    if ver == 5:   # (masks of 32 bits: code categories 0-15, phase bits 16 main logic, 17 other thread in logic, 18 outside)
        lines = [(*x[:8], x[8:11], x[11], x[12]) for x in struct.iter_unpack("<QHHHHIIIIIIII", data[off:])]
    elif ver == 4:   # (+ the categories of the code that read the carried value / wrote it: code_cats.py)
        lines = [(*x[:8], x[8:11], x[11], x[12]) for x in struct.iter_unpack("<QHHHHIIIIIIHH", data[off:])]
    elif ver == 3:   # (+ ra_live, ra_w, and the state reader's 3 callers: offsets in ssbu.exe)
        lines = [(*x[:8], x[8:11], 0, 0) for x in struct.iter_unpack("<QHHHHIIIIII", data[off:])]
    elif ver == 2:
        lines = [(*x, (no, no, no), 0, 0) for x in struct.iter_unpack("<QHHHHIII", data[off:])]
    else:
        lines = [(*x, no, no, (no, no, no), 0, 0) for x in struct.iter_unpack("<QHHHHI", data[off:])]
    return frames, threads, lines


def check_map(trace_path, map_path=None):
    """A trace's code offsets are those of the ssbu.exe that wrote it: with a map made later (the build was linked
    again), every function name would be wrong without a sign. Stops unless SSBU_STALE_MAP=1."""
    map_path = map_path or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "build-trace", "ssbu.map")
    if os.path.exists(map_path) and os.path.exists(trace_path) and os.path.getmtime(map_path) > os.path.getmtime(trace_path) + 1:
        msg = f"{trace_path} is older than {map_path}: the build was linked again since this trace; its function names would be wrong."
        if os.environ.get("SSBU_STALE_MAP") != "1":
            raise SystemExit(msg + " Run the trace again (SSBU_STALE_MAP=1 to read it anyway).")
        print("WARNING:", msg)


class ExeMap:
    """ssbu.exe offset -> the generated function holding it (f_<guest address>) or the runtime's, from ssbu.map."""

    def __init__(self, path):
        self.starts, self.names = [], []
        base = 0x140000000
        rows = []
        with open(path, errors="replace") as f:
            for line in f:
                p = line.split()
                if len(p) >= 4 and ":" in p[0] and len(p[2]) == 16:
                    try:
                        va = int(p[2], 16)
                    except ValueError:
                        continue
                    if va >= base:
                        rows.append((va - base, p[1]))
        rows.sort()
        self.starts = [r[0] for r in rows]
        self.names = [r[1] for r in rows]

    def name(self, off):
        if off == 0xFFFFFFFF:
            return "(outside ssbu.exe)"
        i = bisect.bisect_right(self.starts, off) - 1
        return self.names[i] if i >= 0 else "?"



def klass(fr, fw, first_r, live):
    if live:
        return "state"
    if fw and fr:
        return "scratch"
    if fw:
        return "output"
    return "constant"


def main():
    path = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else None
    frames, threads, lines = load(path)
    print(f"{frames} frames traced; {len(lines)} lines touched ({len(lines) * 64 >> 20} MB); {len(threads)} threads")
    for i, (tid, name) in enumerate(threads):
        print(f"  thread bit {i:2}: host {tid} {name or '(no guest thread found)'}")
    by_area = collections.defaultdict(collections.Counter)
    by_thread = collections.defaultdict(collections.Counter)
    state_lines = []
    for a, fr, fw, first_r, live, tm, ra_l, ra_w, chain, cat_r, cat_w in lines:
        k = klass(fr, fw, first_r, live)
        by_area[area(a)][k] += 64
        for b in range(len(threads)):
            if tm >> b & 1:
                by_thread[b][k] += 64
        if k == "state":
            state_lines.append((a, live, tm, ra_l, ra_w, chain, cat_r, cat_w))
    print("\nbytes by area and class (KB):")
    print(f"  {'area':32} {'state':>9} {'scratch':>9} {'output':>9} {'constant':>9}")
    for ar, c in sorted(by_area.items(), key=lambda x: -sum(x[1].values())):
        print(f"  {ar:32} {c['state'] >> 10:9} {c['scratch'] >> 10:9} {c['output'] >> 10:9} {c['constant'] >> 10:9}")
    tot = collections.Counter()
    for c in by_area.values():
        tot.update(c)
    print(f"  {'all':32} {tot['state'] >> 10:9} {tot['scratch'] >> 10:9} {tot['output'] >> 10:9} {tot['constant'] >> 10:9}")
    print("\nbytes by thread that touched them (a line counts for each of its threads), KB:")
    for b, c in sorted(by_thread.items(), key=lambda x: -x[1]["state"]):
        print(f"  bit {b:2} {threads[b][1][:40]:40} state {c['state'] >> 10:7} scratch {c['scratch'] >> 10:7} "
              f"output {c['output'] >> 10:7} constant {c['constant'] >> 10:7}")
    shared = collections.Counter(bin(x[2]).count("1") for x in state_lines)
    print("state lines by how many threads touched them:", dict(sorted(shared.items())))
    out = {"frames": frames, "threads": threads, "by_area": by_area, "by_thread": {str(k): v for k, v in by_thread.items()}}
    if any(x[6] for x in state_lines):
        import code_cats
        cn = code_cats.CATS[:14] + ["?"] * 2 + ["logic (main thread)", "logic (other thread)", "outside logic"]
        ver_ = ver

        def cset(m):
            return "+".join(cn[i] for i in range(len(cn)) if m >> i & 1) or "(none)"

        SIM = (1 << 1) | (1 << 8) | (1 << 10)   # app, lua2cpp scripts, app? (its code region)
        sets, sim_r, by_cat = collections.Counter(), collections.Counter(), collections.Counter()
        for x in state_lines:
            cr, cw = x[6], x[7]
            sets[cset(cr)] += 64
            if ver_ < 5:   # (MT4: bit 14 logic phase, any thread)
                main_l, other_l, w_main = cr & (1 << 14), 0, cw & (1 << 14)
            else:
                main_l, other_l, w_main = cr & (1 << 16), cr & (1 << 17), cw & (1 << 16)
            sim_r["read by simulation code (app, app?, scripts)" if cr & SIM else
                  "read in the logic phase on the main thread by other code" if main_l else
                  "read in the logic phase on another thread" if other_l else
                  "written by simulation code only" if cw & SIM else
                  "written in the logic phase on the main thread, read only outside it" if w_main else
                  "neither: outside the logic phase, by other code"] += 64
            for i in range(len(cn)):
                if cr >> i & 1:
                    by_cat[cn[i]] += 64
        print("\nstate bytes by who reads the carried value (all categories that did), KB:")
        for k, n in sim_r.most_common():
            print(f"  {n >> 10:7}  {k}")
        print("  each category (a line counts for each of its readers):", ", ".join(f"{k} {n >> 10}" for k, n in by_cat.most_common()))
        print("  by the set of reader categories (top 15):")
        for k, n in sets.most_common(15):
            print(f"  {n >> 10:7}  {k}")
        out.update(reader_sets=sets, sim=sim_r, reader_categories=by_cat)

    if prefix:
        blocks = []
        with open(prefix + ".live") as f:
            for line in f:
                if line[0] == "#":
                    continue
                p = line.split()
                blocks.append((int(p[0], 16), int(p[1]), int(p[4], 16), " ".join(p[5:7])))
        blocks.sort()
        starts = [b[0] for b in blocks]
        names = rtti.Names()
        modv = {}
        tj = os.path.join(os.path.dirname(prefix), "types.json")
        if os.path.exists(tj):
            modv = {int(k, 16): v for k, v in json.load(open(tj))["module_vptrs"].items()}

        def typ(w):
            if 0x7104f17000 <= w < 0x71052aa000:
                return rtti.demangle_simple(names.name(w)) or modv.get(w) or f"vtable {w:#x}"
            return "data (no vptr)"

        by_type, by_site, outside = collections.Counter(), collections.Counter(), 0
        for a, _live, _tm, _rl, _rw, _ch, *_c in state_lines:
            i = bisect.bisect_right(starts, a) - 1
            # (jemalloc's blocks do not overlap: only the last one starting at or before the line can hold it)
            hit = blocks[i] if i >= 0 and blocks[i][0] + blocks[i][1] > a else None
            if hit is None:
                outside += 64
                continue
            t = typ(hit[2])
            if hit[1] > 0x10000:
                t = f"(in a {hit[1] >> 10} KB block) " + t
            by_type[t] += 64
            by_site[hit[3]] += 64
        print(f"\nstate bytes inside traced blocks {sum(by_type.values()) >> 10} KB, outside any {outside >> 10} KB")
        print("state bytes by the type of their block (top 40), KB:")
        for t, n in by_type.most_common(40):
            print(f"  {n >> 10:7}  {t}")
        print("state bytes by allocation site (first two return addresses, top 20), KB:")
        for s, n in by_site.most_common(20):
            print(f"  {n >> 10:7}  {s}")
        out.update(by_type=by_type, by_site=by_site, outside=outside)
    mp = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "build-trace", "ssbu.map")
    if len(sys.argv) > 3:
        mp = sys.argv[3]
    if os.path.exists(mp) and any(x[3] != 0xFFFFFFFF for x in state_lines):
        em = ExeMap(mp)
        names = rtti.Names()
        modv2 = {}
        tj2 = os.path.join(os.path.dirname(prefix), "types.json") if prefix else ""
        if tj2 and os.path.exists(tj2):
            modv2 = {int(k, 16): v for k, v in json.load(open(tj2))["module_vptrs"].items()}
        cm = rtti.CodeMap(names, modv2)
        exported = {0x7100000000 + v: n for n, v, _sz, _i, _sh in names.m.exports}

        def guest(off):
            fn = em.name(off)
            if not fn.startswith("f_"):
                return fn, "runtime" if fn != "(outside ssbu.exe)" else "-"
            try:
                g = int(fn[2:].split("_")[0], 16)
            except ValueError:
                return fn, "?"
            if g in exported:
                return exported[g][:70], "export"
            if 0x7100000000 <= g < 0x71039c8440:
                lab, _how = cm.name(g)
                return fn, lab
            return fn, "other module"

        def label(off):
            fn, lab = guest(off)
            return f"{fn} [{lab}]"

        readers, writers, chains, libs = (collections.Counter() for _ in range(4))
        for a, _l, _tm, rl, rw, ch, *_c in state_lines:
            readers[label(rl)] += 64
            writers[label(rw)] += 64
            chains[" <- ".join(label(x) for x in (rl, *ch) if x != 0xFFFFFFFF)] += 64
            # the first frame of the chain (reader, then callers) whose library is known: who consumes the state
            lib = "unknown"
            for x in (rl, *ch):
                if x == 0xFFFFFFFF:
                    continue
                _fn, lb = guest(x)
                if lb not in ("unknown", "?", "-", "runtime", "other module"):
                    lib = lb.lstrip("~").split("::")[0]
                    break
            libs[lib] += 64
        print("\nstate bytes by the library of their reader (the reader, else its nearest caller, whose code is placed):")
        for k, n in libs.most_common(15):
            print(f"  {n >> 10:6}  {k}")
        print("state bytes by the function that last read them first in a frame (top 30), KB:")
        for fn, n in readers.most_common(30):
            print(f"  {n >> 10:6}  {fn}")
        print("state bytes by reader and its callers (top 25), KB:")
        for fn, n in chains.most_common(25):
            print(f"  {n >> 10:6}  {fn}")
        print("state bytes by the function that last wrote them (top 25), KB:")
        for fn, n in writers.most_common(25):
            print(f"  {n >> 10:6}  {fn}")
        out.update(readers=readers, writers=writers, chains=chains, reader_libraries=libs)
    with open(path + ".json", "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
