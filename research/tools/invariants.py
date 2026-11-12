"""A second method for fields read from the code (research/map/code_reading/): invariants across consecutive frames.

    deps/python/python.exe research/tools/invariants.py <dump made at every frame (matrix.py --state 1,<first>,<last>)>

On each fighter, frame t against frame t-1 (both dumped), with the raw bytes of the module objects and of the blocks
behind their pointers (SSBU_STATE_PATHS):
  ControlModule (block = module + 0x20, [module + 0x110]):
    stick previous (block + 0x20 / 0x24) at t   == stick current (block + 0x10 / 0x14) at t-1
    sub stick previous (+0x50 / 0x54) at t      == sub stick current (+0x40 / 0x44) at t-1
    buttons previous (+0x80) at t               == buttons held (+0x7c) at t-1
    newly pressed (+0x88)                       == (previous ^ held) & held, same frame
    released (+0x8c)                            == (previous ^ held) & previous, same frame
  GroundModule's record ([GM + 0x28]):
    status (+0x5a0: 1 ground, 2 air, 3 cliff)  against StatusModule.situation_kind (0 ground, 2 air, 1 cliff)
    floor contact (+0xa0 not 0)                when the status is ground
  KineticModule:
    energy enabled byte (+0x30) == KineticModule.is_enable_energy(k) as the reader names it (already checked by the
    game); the energies' class vptrs (+0) the same at every frame (code_reading's slot table)
Prints, for each invariant, how many frame pairs hold it and how many do not, with the first failures.
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fields  # noqa: E402
import reader  # noqa: E402

ENERGY_CLASSES = {0: 0x7104f888b8, 1: 0x7104f88810, 2: 0x7104f88760, 3: 0x7104f88968, 4: 0x7104f88a18, 5: 0x7104f6f608,
                  6: 0x7104f6f278, 7: 0x7104f6f348, 8: 0x7104f88760, 9: 0x7104f88a18, 10: 0x7104f88968}
SITUATION_OF_STATUS = {1: 0, 2: 2, 3: 1}


def main():
    dic = fields.Dictionary()
    ok, bad = collections.Counter(), collections.Counter()
    examples = collections.defaultdict(list)
    prev = {}

    def check(name, cond, why=""):
        if cond:
            ok[name] += 1
        else:
            bad[name] += 1
            if len(examples[name]) < 3:
                examples[name].append(why)

    seen = set()
    for r in reader.records(sys.argv[1]):
        if r["kind"] == 2 or r["id"] >> 28 or (r["id"], r["frame"]) in seen:
            continue
        seen.add((r["id"], r["frame"]))   # (the first record of a fighter a frame)
        mods = {dic.off_name.get(o): (a, b) for o, (a, b) in r["mods"].items() if dic.off_name.get(o)}
        cur = {}
        c = mods.get("ControlModule")
        if c and len(c[1]) >= 0x120:
            a, b = c
            if struct.unpack_from("<Q", b, 0x110)[0] == a + 0x20:
                blk = b[0x20:]
                cur["stick"] = blk[0x10:0x18]
                cur["stick_prev"] = blk[0x20:0x28]
                cur["sub"] = blk[0x40:0x48]
                cur["sub_prev"] = blk[0x50:0x58]
                held, prv, trig, rel = struct.unpack_from("<IIII", blk, 0x7c)[0], struct.unpack_from("<I", blk, 0x80)[0], \
                    struct.unpack_from("<I", blk, 0x88)[0], struct.unpack_from("<I", blk, 0x8c)[0]
                cur["held"], cur["prev_held"] = held, prv
                check("ControlModule: newly pressed == (prev ^ held) & held", trig == (prv ^ held) & held,
                      f"frame {r['frame']}: {trig:#x} vs {(prv ^ held) & held:#x}")
                check("ControlModule: released == (prev ^ held) & prev", rel == (prv ^ held) & prv,
                      f"frame {r['frame']}: {rel:#x} vs {(prv ^ held) & prv:#x}")
        g = mods.get("GroundModule")
        s = mods.get("StatusModule")
        if g and s and len(g[1]) >= 0x30:
            rec = r["behind"].get(g[0], {}).get(0x28)
            if rec and len(rec[1]) >= 0x5a4:
                st = struct.unpack_from("<I", rec[1], 0x5a0)[0]
                sit = struct.unpack_from("<I", s[1], 0xdc)[0]
                check("GroundModule record +0x5a0 status matches StatusModule situation_kind",
                      SITUATION_OF_STATUS.get(st) == sit, f"frame {r['frame']}: status {st} situation {sit}")
                if st == 1:
                    check("GroundModule record: floor contact (+0xa0 not 0) when on the ground",
                          struct.unpack_from("<Q", rec[1], 0xa0)[0] != 0, f"frame {r['frame']}")
        k = mods.get("KineticModule")
        if k:
            for e in range(11):
                sub = r["behind"].get(k[0], {}).get(0x30 + 0x18 * e)
                if sub and len(sub[1]) >= 8:
                    check("KineticModule energy classes as read from the constructor",
                          struct.unpack_from("<Q", sub[1], 0)[0] == ENERGY_CLASSES[e],
                          f"frame {r['frame']} energy {e}: {struct.unpack_from('<Q', sub[1], 0)[0]:#x}")
        key = r["id"]
        p = prev.get(key)
        if p and p["frame"] == r["frame"] - 1 and "stick" in cur and "stick" in p:
            check("ControlModule: stick previous(t) == stick(t-1)", cur["stick_prev"] == p["stick"], f"frame {r['frame']}")
            check("ControlModule: sub stick previous(t) == sub stick(t-1)", cur["sub_prev"] == p["sub"], f"frame {r['frame']}")
            check("ControlModule: buttons previous(t) == held(t-1)", cur["prev_held"] == p["held"],
                  f"frame {r['frame']}: {cur['prev_held']:#x} vs {p['held']:#x}")
        cur["frame"] = r["frame"]
        prev[key] = cur
    for name in sorted(set(ok) | set(bad)):
        print(f"  {name}: {ok[name]} hold, {bad[name]} do not" + (f"  e.g. {'; '.join(examples[name])}" if bad[name] else ""))
    return 1 if sum(bad.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
