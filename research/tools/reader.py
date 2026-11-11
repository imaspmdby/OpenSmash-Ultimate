"""The gamestate reader: battle objects' named state, frame by frame, from a raw dump (SSBU_STATE_DUMP).

    deps/python/python.exe research/tools/reader.py <dump> [--fields research/map/fields.json] [--hash <fight hash log>]
                                                    [--frame N] [--json <out.jsonl>]

Decodes each record (an object's boma, its modules, one level behind them) with the field dictionary (fields.py:
the game's own getters) and a few fields read off the getters' code by hand (SPECIAL). Prints a summary of one
frame (--frame, default the last), writes every record as a JSON line (--json), and with --hash checks the
fighters' status, motion, motion frame, position and damage against the fight hash log of the same run
(SSBU_FIGHT_HASH: read by the game's getters at the same point of the frame).
"""
import argparse
import collections
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATEGORY = {0: "fighter", 1: "weapon", 2: "enemy", 3: "gimmick", 4: "item"}
KIND = {"f32": "<f", "f64": "<d", "u32": "<I", "i32": "<i", "u64": "<Q", "u8": "<B", "i8": "<b", "u16": "<H"}
# fields the plain-getter decoder does not see, read off the getters' code (research/RESEARCH.md):
#   PostureModule::pos returns the module + 0x30 (a vector: x, y, z); prev_pos + 0x40 by its neighbour
#   DamageModule::damage(i) is the f32 at [module + 0x18] + i * 0x1c0
SPECIAL = {
    "PostureModule": [("pos_x", 0x30, "f32"), ("pos_y", 0x34, "f32"), ("pos_z", 0x38, "f32")],
}
BEHIND = {"DamageModule": [("damage", 0x18, 0x0, "f32")]}   # (name, pointer's offset in the module, offset there, kind)


def records(path):
    data = open(path, "rb").read()
    assert data[:4] == b"SD1\0", "not a state dump"
    off = 4
    while off + 32 <= len(data):
        tag, oid, boma, frame, kind, parts = struct.unpack_from("<IIQqII", data, off)
        assert tag == 0x414d4f42, "bad record at %d" % off
        off += 32
        raw = data[off:off + 0x400]
        off += 0x400
        mods, behind = {}, collections.defaultdict(dict)
        cut = False
        for _ in range(parts):
            if off + 28 > len(data):   # (the run ended while its last record was being written)
                cut = True
                break
            level, o, parent, addr, ln = struct.unpack_from("<IIQQI", data, off)
            if off + 28 + ln > len(data):
                cut = True
                break
            off += 28
            b = data[off:off + ln]
            off += ln
            if level == 1:
                mods[o] = (addr, b)
            else:
                behind[parent][o] = (addr, b)
        if cut:
            return
        yield {"id": oid, "boma": boma, "frame": frame, "kind": kind, "raw": raw, "mods": mods, "behind": behind}


class Reader:
    """Decodes a record with the dictionary of each module's own class (fields.Dictionary: the module's vptr picks
    the vtable the getters' slots are read in), so a weapon's or an item's modules are read by their own layout."""

    def __init__(self, fields_path=None):
        import fields
        self.dic = fields.Dictionary()
        self.off_name = self.dic.off_name

    def decode(self, rec):
        out = {"id": rec["id"], "category": CATEGORY.get(rec["id"] >> 28, "?%d" % (rec["id"] >> 28)), "frame": rec["frame"],
               "at_line": rec["kind"] == 0, "modules": {}}
        for o, (addr, b) in sorted(rec["mods"].items()):
            name = self.off_name.get(o)
            if not name or len(b) < 8:
                continue
            vptr = struct.unpack_from("<Q", b, 0)[0]
            vals = {}
            for meth, fo, kind in self.dic.fields_for(vptr, name) + SPECIAL.get(name, []):
                if fo + struct.calcsize(KIND[kind]) <= len(b):
                    vals[meth] = struct.unpack_from(KIND[kind], b, fo)[0]
            for meth, po, fo, kind in BEHIND.get(name, []):
                sub = rec["behind"].get(addr, {}).get(po)
                if sub and fo + 4 <= len(sub[1]):
                    vals[meth] = struct.unpack_from(KIND[kind], sub[1], fo)[0]
            if vals:
                out["modules"][name] = vals
        st = out["modules"].get("StatusModule", {}).get("status_kind")
        out["active"] = st is not None and st != 0xFFFFFFFF
        return out


def f32bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def check_hash(decoded, hash_path):
    by_frame = collections.defaultdict(list)
    for line in open(hash_path):
        p = line.split()
        if not p or p[0] != "F":
            continue
        by_frame[int(p[1])].append({"st": int(p[5], 16), "mot": int(p[7], 16), "mf": int(p[9], 16), "x": int(p[11], 16),
                                    "y": int(p[13], 16), "dmg": int(p[15], 16)})
    ok, bad, examples = collections.Counter(), collections.Counter(), []
    per_frame = collections.defaultdict(list)
    for d in decoded:
        if d["category"] == "fighter" and d.get("at_line"):   # (written at the fighter's own frame line, as the hash)
            per_frame[d["frame"]].append(d)
    frames = 0
    for f, ds in sorted(per_frame.items()):
        hs = by_frame.get(f)
        if not hs or len(hs) < len(ds):
            continue
        frames += 1
        for d, h in zip(ds, hs):
            m = d["modules"]
            ours = {"st": m.get("StatusModule", {}).get("status_kind"), "mot": m.get("MotionModule", {}).get("motion_kind"),
                    "mf": f32bits(m["MotionModule"]["frame"]) if "frame" in m.get("MotionModule", {}) else None,
                    "x": f32bits(m["PostureModule"]["pos_x"]) if "pos_x" in m.get("PostureModule", {}) else None,
                    "y": f32bits(m["PostureModule"]["pos_y"]) if "pos_y" in m.get("PostureModule", {}) else None,
                    "dmg": f32bits(m["DamageModule"]["damage"]) if "damage" in m.get("DamageModule", {}) else None}
            for k, v in ours.items():
                if v == h[k]:
                    ok[k] += 1
                else:
                    bad[k] += 1
                    if len(examples) < 8:
                        examples.append(f"frame {f} id {d['id']:#x} {k}: reader {v if v is None else hex(v)} game {h[k]:#x}")
    print(f"cross-check with the game's getters (fight hash log), {frames} frames:")
    for k in ("st", "mot", "mf", "x", "y", "dmg"):
        print(f"  {k:4} equal {ok[k]:5}  different {bad[k]:5}")
    for e in examples:
        print("   ", e)
    return not sum(bad.values()) and sum(ok.values()) > 0


def summary(d):
    m = d["modules"]
    g = lambda mod, k, default=None: m.get(mod, {}).get(k, default)
    parts = [f"{d['category']} {d['id']:#010x}" + ("" if d.get("active", True) else " (inactive)")]
    if "PostureModule" in m:
        parts.append(f"pos ({g('PostureModule', 'pos_x', 0):.2f}, {g('PostureModule', 'pos_y', 0):.2f}) lr {g('PostureModule', 'lr', 0):+.0f}")
    if "StatusModule" in m:
        parts.append(f"status {g('StatusModule', 'status_kind', 0):#x} situation {g('StatusModule', 'situation_kind')}")
    if "MotionModule" in m:
        parts.append(f"motion {g('MotionModule', 'motion_kind', 0):#x} frame {g('MotionModule', 'frame', 0):.1f}")
    if "damage" in m.get("DamageModule", {}):
        parts.append(f"damage {g('DamageModule', 'damage'):.1f}%")
    if "AttackModule" in m:
        parts.append(f"active hitboxes {g('AttackModule', 'active_part_num')}")
    if "StopModule" in m:
        parts.append(f"hitstop {g('StopModule', 'get_hit_stop_real_frame')}")
    return "; ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--fields", default=os.path.join(ROOT, "research", "map", "fields.json"))
    ap.add_argument("--hash")
    ap.add_argument("--frame", type=int)
    ap.add_argument("--json")
    a = ap.parse_args()
    rd = Reader(a.fields)
    decoded = [rd.decode(r) for r in records(a.dump) if r["kind"] != 2]
    frames = sorted({d["frame"] for d in decoded})
    cats = collections.Counter(d["category"] for d in decoded)
    nf = sum(len(v) for d in decoded for v in d["modules"].values())
    print(f"{len(decoded)} records over {len(frames)} frames ({frames[0]}..{frames[-1]}); by category {dict(cats)}; "
          f"{nf // max(1, len(decoded))} named fields a record")
    f = a.frame if a.frame is not None else frames[-1]
    print(f"frame {f}:")
    shown = [d for d in decoded if d["frame"] == f]
    for d in shown:
        if d.get("active", True):
            print("  " + summary(d))
    print(f"  (+ {sum(1 for d in shown if not d.get('active', True))} inactive objects: pre-made articles, status -1)")
    if a.json:
        with open(a.json, "w") as out:
            for d in decoded:
                out.write(json.dumps(d) + "\n")
    if a.hash:
        return 0 if check_hash(decoded, a.hash) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
