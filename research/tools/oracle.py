"""The strict oracle: after a replay (SSBU_RB_VERIFY in a traced run), which of the simulation's differing lines are
explained by known non-simulation causes, and which are not.

    deps/python/python.exe research/tools/oracle.py <run folder> [--show N]

Needs, from one run of build-trace (`matrix.py --exe build-trace --probe` with SSBU_MEMTRACE, SSBU_MEMTRACE_CATS,
SSBU_RB=1, SSBU_RB_VERIFY): <run>/mt.bin (the access trace), <run>/alloc.live (the allocation trace) and
<run>/verify/rb_verify_sim_<round>.txt (the replay's differing simulation lines, hle_rb_state.c).

Known causes (research/RESEARCH.md, 2026-11-11), each by an invariant, not an address:
  render     the line's block is a `nu::` object (render engine state set in the logic phase);
  sound      a reader / writer chain passes through app::SoundModule's request manager or the audio mixer thread's
             code, or the line was touched by the audio mixer thread;
  lua-gc     the last state reader is Lua's GC (propagatemark and its family);
  allocator  the line holds pointers only and lies in jemalloc's bookkeeping (outside every traced block, or in the
             64 KB blocks of site 0x710353cf48);
  thread stack  the line is in the guest stacks' area or in a heap-allocated thread stack (site 0x710353cf48);
  gc marks / flag flip  the words differ only by a two-state bit pair swapped (Lua's white bits, or another epoch);
  lua dead slot  in a block of Lua's allocator (site 0x71038fb578), last written by Lua's GC, only the type tags of
             16-byte Lua values differ and one side is nil: Lua 5.3's traversethread clears the unused part of a
             coroutine's stack (above its top) in the atomic phase; those slots are written before they are read;
  fiber stack  outside every traced block, touched by one thread, in a page where differing lines hold frame
             pointers (a 16-aligned pointer to less than 64 KB from itself): the stack of a fiber the game made;
  sync       a lock's state (a chain through the SDK's mutex functions, or a block holding such a lock);
  pool handle  read by a handle release (HANDLE_FNS): a pooled async object's generation;
  plugin     read / written by a plugin's code (0x7262000000 on: ARCropolis, smashline...);
  moved content  (tried last, over a round's lines) the same contents in other nodes: each differing word of the
             line, heap pointers masked, is found among the round's differing words after, and its word after among
             those before (--bytes: off);
  sdk refcount  a block allocated by the SDK's android::RefBase constructor (its reference counts);
  sound request  a function of the chain is a script animation command that plays a sound (app::sv_animcmd::PLAY_*);
  fiber bookkeeping  pointers, or the fiber objects' own words (tagged 0xf1be in their top 16 bits), read or written by
             phx::Fiber's methods (which pooled fiber or stack runs a script);
anything else is UNEXPLAINED when it is consumed state (a carried value read by the simulation's code or in the logic
phase): the oracle's failure; else an "unexplained output", reported only: a candidate real divergence. Prints per round the counts, and the unexplained lines.
"""
import bisect
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memtrace  # noqa: E402
import rtti  # noqa: E402
import verify_diff  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LUA_SITE = "0x71038fb578"   # Lua's allocation function (every Lua object, stacks included)
LUA_GC = {"f_71038ffa80", "f_71038fe340", "f_71038fe580", "f_71038fedf0", "f_71038fec40", "f_71038ff960"}
# jemalloc's code (its entry points are at 0x710392e1f0-0x710392ee50): the readers of its bookkeeping
JEMALLOC = (0x7103900000, 0x7103960000)
# guest thread stacks allocated from the heap (64 KB, aligned): their content is call frames
STACK_SITES = {"0x710353cf48"}
SOUND_VPTRS = {0x7104f89a70}   # app::SoundModule
# the SDK's locks (nn::os::LockMutex / UnlockMutex, std::recursive_mutex): a mutex's owner and count depend on which
# thread held it at the save; sdk exports, resolved by name at start
SYNC_NAMES = ("LockMutex", "UnlockMutex", "TryLockMutex", "recursive_mutex", "ConditionVariable", "Semaphore",
              "WaitEvent", "SignalEvent", "libcpp_recursive_mutex", "libcpp_mutex")
PLUGINS = 0x7262000000
# functions identified by reading their code as handle releases: they check a handle's generation against its pooled
# object's (+0x20) and clear a flag under the object's lock: the generation follows the async pool's recycling order
HANDLE_FNS = {"f_71004ce860"}
# the audio mixer thread's code (entry sdk+0x338930 -> sdk+0x334450 -> f_7103987e40) and the sound request manager
SOUND = {"f_7103987e40", "f_71039635c0", "f_7103980980", "f_710397a8a0", "f_7103996aa0", "f_710396c8a0",
         "f_71023ef100", "f_71023ef2e0", "f_71006e5cc0"}


def main():
    run = sys.argv[1]
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 15
    _fr, threads, lines = memtrace.load(os.path.join(run, "mt.bin"))
    L = {x[0]: x for x in lines}
    em = memtrace.ExeMap(os.path.join(ROOT, "build-trace", "ssbu.map"))
    names = rtti.Names()
    audio_bits = 0
    for b, (_tid, nm) in enumerate(threads):
        pass
    # the audio thread: the thread that touches lines whose readers are the mixer's code
    votes = collections.Counter()
    for x in lines:
        if x[4] and em.name(x[6]) in SOUND:
            for b in range(len(threads)):
                if x[5] >> b & 1:
                    votes[b] += 1
    main_bit = next((b for b, t in enumerate(threads) if "main" in t[1]), 0)
    audio = [b for b, _n in votes.most_common() if b != main_bit][:1]
    for b in audio:
        audio_bits |= 1 << b
    blocks = []
    for line in open(os.path.join(run, "alloc.live")):
        if line[0] == "#":
            continue
        p = line.split()
        blocks.append((int(p[0], 16), int(p[1]), int(p[4], 16), p[5] if len(p) > 5 else "?",
                       tuple(int(x, 16) for x in p[5:9])))   # (+ the allocation's return addresses)
    blocks.sort()
    starts = [b[0] for b in blocks]

    def block(a):
        i = bisect.bisect_right(starts, a) - 1
        return blocks[i] if i >= 0 and blocks[i][0] + blocks[i][1] > a else None

    def guest(fn):
        try:
            return int(fn[2:].split("_")[0], 16) if fn.startswith("f_") else None
        except ValueError:
            return None

    import nso  # noqa: E402  (tools/: the sdk's exported lock functions)
    sdk = nso.Module(os.path.join(ROOT, "dump", "exefs", "sdk"))
    sync_fns = {"f_%x" % (0x7109000000 + v) for n, v, _s, _i, _sh in sdk.exports if any(k in n for k in SYNC_NAMES)}
    sync_blocks = set()
    # the SDK's android::RefBase constructor: the reference-count blocks it allocates (weakref_impl, 24 bytes)
    refbase = [(0x7109000000 + v, 0x7109000000 + v + sz) for n, v, sz, _i, _sh in sdk.exports if n.startswith("_ZN7android7RefBaseC")]

    def fnames(x):
        return [em.name(o) for o in (x[6], x[7], *x[8]) if o not in (0, 0xFFFFFFFF)]

    code_map = rtti.CodeMap(names, {})
    label_cache = {}

    def code_label(fn):   # (the nearest named code: a virtual function of a named class, or an export)
        if fn not in label_cache:
            g = guest(fn)
            label_cache[fn] = code_map.name(g)[0] if g and 0x7100000000 <= g < 0x71039c8440 else ""
        return label_cache[fn]

    for x in lines:   # blocks holding a lock: every line of them is lock state
        if x[4] and set(fnames(x)) & sync_fns:
            b = block(x[0])
            if b:
                sync_blocks.add(b[0])

    files = sorted(glob.glob(os.path.join(run, "verify", "rb_verify_sim_*.txt")),
                   key=lambda p: int(re.search(r"_(\d+)\.txt$", p).group(1)))
    stack_pages = set()   # pages outside the traced blocks where a differing line holds a frame pointer
    for path in files:
        for line in open(path):
            p = line.split()
            a = int(p[0], 16)
            if block(a) is None and 0x6000000000 <= a < 0x7000000000:
                for v in p[4:12] + p[13:21]:
                    v = int(v, 16)
                    if v & 15 == 0 and 0 < abs(v - a) < 0x10000:
                        stack_pages.add(a >> 12)

    def cause(a, was, now):
        b = block(a)
        x0 = L.get(a)
        if x0 is not None and set(fnames(x0)) & sync_fns or (b and b[0] in sync_blocks):
            return "sync"
        if x0 is not None and any((guest(f) or 0) >= PLUGINS for f in fnames(x0)):
            return "plugin"
        if x0 is not None and em.name(x0[6]) in HANDLE_FNS:
            return "pool handle"
        if b and b[3] in STACK_SITES:
            return "thread stack"
        if b and b[2] in SOUND_VPTRS:
            return "sound"
        diff = [(w, n) for w, n in zip(was, now) if w != n]
        # Lua's GC flips its two white bits (marked, bit 0 / bit 1) between cycles: a word that differs only there
        if diff and all(((w ^ n) & ~0x0300) == 0 and (w ^ n) for w, n in diff):
            return "gc marks"
        if 0x7700000000 <= a < 0x7780000000:
            return "thread stack"
        # a two-state flag flipped (two adjacent bits swapped, 1 <-> 2): a GC-like epoch elsewhere than Lua's marks
        def flip(w, n):
            x = w ^ n
            return x and (x >> ((x & -x).bit_length() - 1)) == 3
        if diff and all(flip(w, n) for w, n in diff):
            return "flag flip"
        if b and 0x7104f17000 <= b[2] < 0x71052aa000:
            t = rtti.demangle_simple(names.name(b[2])) or ""
            if t.startswith("nu::"):
                return "render"
        x = L.get(a)
        if x is not None:
            fns = set(fnames(x))
            if fns & SOUND or x[5] & audio_bits:
                return "sound"
            if em.name(x[6]) in LUA_GC:
                return "lua-gc"
            g = [guest(f) for f in fnames(x)]
            if any(v and JEMALLOC[0] <= v < JEMALLOC[1] for v in g):
                return "allocator"
            if g and g[0] and 0x7103600000 <= g[0] < 0x71038f0000:   # (the last reader is the render engine's code)
                return "render"
        # the two causes below come last: they only take lines nothing else explains
        if b is None and a >> 12 in stack_pages and x0 is not None and bin(x0[5]).count("1") == 1:
            return "fiber stack"
        if b and b[3] == LUA_SITE and x0 is not None and em.name(x0[7]) in LUA_GC and diff and all(
                w == n or ((a - b[0] + 8 * i) % 16 == 8 and (w ^ n) >> 32 == 0 and 0 in (w & 0xFFFFFFFF, n & 0xFFFFFFFF))
                for i, (w, n) in enumerate(zip(was, now))):
            return "lua dead slot"
        ptrs = all(verify_diff.kind(w, n) == "pointer" or (w == 0 or n == 0) for w, n in diff)
        if ptrs and b is None:
            return "allocator"
        # (2026-11-12 afternoon) an android::RefBase reference-count block of the SDK (allocated by RefBase::RefBase:
        # strong / weak counts; the game imports no RefBase symbol; an SDK thread holds a reference at a save or not)
        if b and len(b) > 4 and any(lo <= ra < hi for ra in b[4] for lo, hi in refbase):
            return "sdk refcount"
        # (2026-11-12, runs st_*: matches the rules were not written on) a sound request made by the scripts' animation
        # commands: a function of the line's chain is app::sv_animcmd::PLAY_SE / PLAY_SEQUENCE / ... (a sound's
        # parameters and handles, not simulation)
        if x0 is not None and any(re.search(r"sv_animcmd\d+PLAY_", code_label(f)) for f in fnames(x0)):
            return "sound request"
        # the fibers' own bookkeeping (phx::Fiber, read or written by its methods), pointers only: which pooled fiber
        # or stack a script runs on, not what it computes
        # (also when the fiber object's own number changes: its words tagged 0xf1be in the top 16 bits, run st_castle_cpu)
        fiber_tag = all(verify_diff.kind(w, n) == "pointer" or (w == 0 or n == 0) or (w >> 48 == 0xf1be and n >> 48 == 0xf1be)
                        for w, n in diff)
        if x0 is not None and fiber_tag and any("phx5Fiber" in code_label(f) for f in fnames(x0)):
            return "fiber bookkeeping"
        return "UNEXPLAINED"

    def masked(b, a, words):   # a line's content with its heap pointers masked, placed by its block's size and offset
        return (b[1] if b else 0, (a - b[0]) if b else -1,
                tuple("P" if 0x6000000000 <= w < 0x7800000000 else w for w in words))

    summary = {}
    for path in files:
        rnd = int(re.search(r"_(\d+)\.txt$", path).group(1))
        counts, unexplained, outputs = collections.Counter(), [], []
        allrows = []
        for line in open(path):
            p = line.split()
            a = int(p[0], 16)
            was = [int(v, 16) for v in p[4:12]]
            now = [int(v, 16) for v in p[13:21]]
            c = cause(a, was, now)
            cl = int(p[2], 16)
            consumed = cl & 2 and cl & (4 | 8)   # state, read by sim code or in the logic phase
            if c == "UNEXPLAINED" and not consumed:
                c = "unexplained output"   # (written by the simulation, not read back: reported, not a failure)
                outputs.append((a, cl, block(a), was, now))
            counts[c] += 1
            if c == "UNEXPLAINED":
                b = block(a)
                unexplained.append((a, int(p[2], 16), b, was, now))
            allrows.append((a, was, now))
        # (2026-11-12 afternoon) comparison by content: containers whose same contents land in other nodes after a
        # replay (libc++ unordered_map nodes, event lists: research/RESEARCH.md). A line whose content before, pointers
        # masked and placed by its block's size and offset, is the content after of another differing line, and whose
        # content after is the content before of another, holds moved content, not a different value.
        if unexplained and "--bytes" not in sys.argv:
            def wkey(addr, w):   # a word's value, heap pointers masked (the blocks at the run's end do not tell the
                return "P" if 0x6000000000 <= w < 0x7800000000 else w   # nodes' blocks at the comparison: freed, reused)
            before, after = collections.Counter(), collections.Counter()
            for a2, w2, n2 in allrows:
                for i, (x, y) in enumerate(zip(w2, n2)):
                    if x != y:
                        before[wkey(a2 + 8 * i, x)] += 1
                        after[wkey(a2 + 8 * i, y)] += 1
            keep = []
            for u in unexplained:
                a2, _cl, b2, was, now = u
                kw = [wkey(a2 + 8 * i, x) for i, (x, y) in enumerate(zip(was, now)) if x != y]
                kn = [wkey(a2 + 8 * i, y) for i, (x, y) in enumerate(zip(was, now)) if x != y]
                if all(after[k] > 0 for k in kw) and all(before[k] > 0 for k in kn):
                    for k in kw: after[k] -= 1
                    for k in kn: before[k] -= 1
                    counts["UNEXPLAINED"] -= 1; counts["moved content"] += 1
                    if "--moved-out" in sys.argv:   # (the lines it explains, for a check: research/RESEARCH.md)
                        with open(sys.argv[sys.argv.index("--moved-out") + 1], "a") as mo:
                            mo.write(f"{rnd} {a2:#x}\n")
                else:
                    keep.append(u)
            unexplained = keep
            if counts["UNEXPLAINED"] == 0:
                del counts["UNEXPLAINED"]
        summary[rnd] = counts
        print(f"round {rnd}: {sum(counts.values())} differing simulation lines: " +
              ", ".join(f"{k} {v}" for k, v in counts.most_common()))
        for a, cl, b, was, now in unexplained[:show]:
            bs = f"block {b[1]} B site {b[3]} +{a - b[0]:#x}" if b else "outside traced blocks"
            x = L.get(a)
            rd = (" <- ".join(em.name(o) for o in (x[6], *x[8]) if o not in (0, 0xFFFFFFFF)) or "-") +                 (f"; written by {em.name(x[7])}" if x and x[7] not in (0, 0xFFFFFFFF) else "") if x else "-"
            dw = ", ".join(f"+{8 * i:#x} {w:#x}->{n:#x}" for i, (w, n) in enumerate(zip(was, now)) if w != n)
            print(f"    {a:#x} class {cl:#x} {bs}; read by {rd}; {dw}")
        if "--outputs" in sys.argv and outputs:   # the unexplained outputs, grouped by block and writer
            grp = collections.Counter()
            for a, cl, b, was, now in outputs:
                x = L.get(a)
                w = em.name(x[7]) if x and x[7] not in (0, 0xFFFFFFFF) else "-"
                r = em.name(x[6]) if x and x[6] not in (0, 0xFFFFFFFF) else "-"
                t = ""
                if b and 0x7104f17000 <= b[2] < 0x71052aa000:
                    t = rtti.demangle_simple(names.name(b[2])) or "vtable %#x" % b[2]
                grp[(f"block {b[1]} B site {b[3]} {t}" if b else "outside traced blocks", w, r, cl)] += 1
            print(f"    unexplained outputs of round {rnd}: {len(outputs)} lines")
            for (blk, w, r, cl), n in grp.most_common(12):
                print(f"      {n:3}  {blk}; written by {w}; state reader {r}; class {cl:#x}")
            if "--detail" in sys.argv:   # each line: where in its block, which 8-byte words differ
                for a, cl, b, was, now in sorted(outputs):
                    x = L.get(a)
                    w = em.name(x[7]) if x and x[7] not in (0, 0xFFFFFFFF) else "-"
                    bs = f"block {b[1]} B +{a - b[0]:#x}" if b else "no block"
                    dw = ", ".join(f"+{8 * i:#x} {u:#x}->{n:#x}" for i, (u, n) in enumerate(zip(was, now)) if u != n)
                    print(f"        {a:#x} {bs}; {w}; {dw}")
    # (no replay compared is not a pass: the run may have ended before the replay check's save, 2026-11-12 st_items4)
    verdict = "NO REPLAYS" if not summary else "PASS" if all(c["UNEXPLAINED"] == 0 for c in summary.values()) else "FAIL"
    print(f"strict oracle: {verdict} (audio thread bit {audio})")
    with open(os.path.join(run, "oracle.json"), "w") as f:
        json.dump({"rounds": summary, "verdict": verdict}, f, indent=1)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
