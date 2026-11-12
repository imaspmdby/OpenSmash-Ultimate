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
ENERGY_MASKS = (1, 2, 4, 7)   # (the arguments of KineticModule::get_sum_speed_x / _y the reader computes and the check asks for)
BEHIND = {"DamageModule": [("damage", 0x18, 0x0, "f32")]}   # (name, pointer's offset in the module, offset there, kind)


def records(path, light=False, only=None):
    """The dump's records, one at a time (the file is mapped, not read whole: a dump of every frame is several GB).
    light: the records' headers only (id, boma, frame, kind), for a first pass over the frames; only: a set of
    frames, the other frames' records are passed over the same way and not given."""
    import mmap
    fh = open(path, "rb")
    data = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    assert data[:4] == b"SD1\0", "not a state dump"
    off = 4
    last = None
    while off + 32 <= len(data):
        tag, oid, boma, frame, kind, parts = struct.unpack_from("<IIQqII", data, off)
        if tag == 0x534c4156:   # 'VALS': the game's own answers for the object just before (SSBU_VERIFY_FIELDS)
            count = kind
            if off + 32 + 16 * count > len(data):
                return
            vals = {}
            for i in range(count):
                idx, fb, x0 = struct.unpack_from("<IIQ", data, off + 32 + 16 * i)
                vals[idx] = (fb, x0)
            off += 32 + 16 * count
            if last is not None and last["boma"] == boma:
                last["game"] = vals
            continue
        if tag == 0x424f5250:   # 'PROB': what each getter read when called on the object just before (SSBU_PROBE_FIELDS)
            count = kind
            q = off + 32
            esz = 24 if parts == 1 else 16   # (form 1: each read with the word at its address)
            probe = {}
            for _ in range(count):
                if q + 24 > len(data):
                    return
                idx, reads, x0, fb, _z = struct.unpack_from("<IIQII", data, q)
                q += 24
                if q + esz * reads > len(data):
                    return
                probe[idx] = (x0, fb, [struct.unpack_from("<QIIQ" if esz == 24 else "<QII", data, q + esz * i) for i in range(reads)])
                q += esz * reads
            off = q
            if last is not None and last["boma"] == boma:
                last["probe"] = probe
            continue
        if last is not None:
            yield last
            last = None
        assert tag == 0x414d4f42, "bad record at %d" % off
        off += 32
        if light or (only is not None and frame not in only):
            q, cut = off + 0x400, False
            for _ in range(parts):
                if q + 28 > len(data):
                    cut = True
                    break
                q += 28 + struct.unpack_from("<I", data, q + 24)[0]
            if cut or q > len(data):
                return
            off = q
            if light:
                last = {"id": oid, "boma": boma, "frame": frame, "kind": kind}
            continue
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
            if level == 1:   # (a part given twice, SSBU_STATE_PATHS: the longer one is kept)
                if o not in mods or len(mods[o][1]) < len(b):
                    mods[o] = (addr, b)
            elif o not in behind[parent] or len(behind[parent][o][1]) < len(b):
                behind[parent][o] = (addr, b)
        if cut:
            return
        last = {"id": oid, "boma": boma, "frame": frame, "kind": kind, "raw": raw, "mods": mods, "behind": behind}
    if last is not None:
        yield last


class Reader:
    """Decodes a record with the dictionary of each module's own class (fields.Dictionary: the module's vptr picks
    the vtable the getters' slots are read in), so a weapon's or an item's modules are read by their own layout."""

    def __init__(self, fields_path=None):
        import fields
        import argprobe
        self.dic = fields.Dictionary()
        self.off_name = self.dic.off_name
        self.arg = argprobe.table()   # {module's vptr: [(module, name, path, reading, size, table's element size)]}

    def arg_values(self, rec, name, addr, b):
        """The fields the getters with arguments name in this module (argprobe.py): {name: (reading, size, value, block address, offset)}.
        A fighter's only (the probe was made on fighters). The value: the float's bits, the integer, or 0 / 1."""
        out = {}
        if rec["id"] >> 28 or len(b) < 8:
            return out
        for mod, fname, path, kind, size, stride in self.arg.get(struct.unpack_from("<Q", b, 0)[0], ()):
            if mod != name:
                continue
            cur, data, prev = addr, b, None
            ok = True
            for o in path[:-1]:
                sub = rec["behind"].get(cur, {}).get(o)
                if not sub:
                    ok = False
                    break
                prev = data
                cur, data = sub
            off = path[-1]
            if not ok or off + size > len(data):
                continue
            raw = int.from_bytes(data[off:off + size], "little")
            if stride:   # a counted table: the count is the word before the table's pointer
                po = path[-2]
                if prev is None or po < 8 or po > len(prev):
                    continue
                if off // stride >= struct.unpack_from("<Q", prev, po - 8)[0]:
                    continue
            if kind in ("f32", "u"):
                v = raw
            elif kind in ("nz", "z"):
                v = int((raw != 0) == (kind == "nz"))
            else:
                bit = raw >> int(kind.lstrip("nbit")) & 1
                v = bit ^ kind.startswith("n")
            out[fname] = (kind, size, v, cur, off)   # (and where it lies: the block's address, the offset)
        if name == "KineticModule" and out:
            self.energies(rec, addr, b, out)
        return out

    def energies(self, rec, addr, b, out):
        """A fighter's kinetic energies, read off what KineticModule::get_sum_speed_x / _y(mask) read (the probe,
        research/RESEARCH.md 2026-11-12): the module holds a count at + 0x20 and, for energy k, a pointer at
        + 0x30 + 0x18 k and an attribute mask at + 0x3c + 0x18 k; an energy holds its speed (x, y: two floats) at
        + 0x10 and "enabled" at + 0x30. The getter's answer is the sum, in order, of the speeds of the enabled
        energies whose mask meets the argument: computed here the same way and checked against the game."""
        if len(b) < 0x30:
            return
        n = struct.unpack_from("<Q", b, 0x20)[0]
        if not 0 < n <= 16 or len(b) < 0x30 + 0x18 * n:
            return
        es = []
        for k in range(n):
            sub = rec["behind"].get(addr, {}).get(0x30 + 0x18 * k)
            if not sub or len(sub[1]) < 0x31:
                return
            # (the energy's speed, as its class's virtual getter gives it: the damage energy's override speed at + 0xC0
            # while the u32 at + 0xD0 counts down, the gravity energy's at + 0x60 while + 0x70 does; else + 0x10.
            # research/map/code_reading/KineticModule.json, and the automatic check on Ice Climbers, 2026-11-12)
            ev = struct.unpack_from("<Q", sub[1], 0)[0]
            so = 0x10
            for cls, cnt, alt in ((0x7104f88a18, 0xd0, 0xc0), (0x7104f88810, 0x70, 0x60)):
                if ev == cls and len(sub[1]) >= cnt + 4 and struct.unpack_from("<i", sub[1], cnt)[0] > 0:
                    so = alt
            x, y = struct.unpack_from("<ff", sub[1], so)
            es.append((struct.unpack_from("<I", b, 0x3c + 0x18 * k)[0], sub[1][0x30], x, y))
            out["energy%d.speed_x" % k] = ("f32", 4, struct.unpack_from("<I", sub[1], 0x10)[0], sub[0], 0x10)
            out["energy%d.speed_y" % k] = ("f32", 4, struct.unpack_from("<I", sub[1], 0x14)[0], sub[0], 0x14)
        f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]
        for mask in ENERGY_MASKS:
            sx = sy = 0.0
            for attr, on, x, y in es:
                if on and attr & mask:
                    sx, sy = f32(sx + x), f32(sy + y)
            out["get_sum_speed_x(%#x)" % mask] = ("f32", 4, struct.unpack("<I", struct.pack("<f", sx))[0], 0, 0)
            out["get_sum_speed_y(%#x)" % mask] = ("f32", 4, struct.unpack("<I", struct.pack("<f", sy))[0], 0, 0)

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
            for fname, (kind, _size, v, _blk, _off) in self.arg_values(rec, name, addr, b).items():
                vals[fname] = struct.unpack("<f", struct.pack("<I", v))[0] if kind == "f32" else v
            for meth, po, fo, kind in BEHIND.get(name, []):
                sub = rec["behind"].get(addr, {}).get(po)
                if sub and fo + 4 <= len(sub[1]):
                    vals[meth] = struct.unpack_from(KIND[kind], sub[1], fo)[0]
            if vals:
                out["modules"][name] = vals
        st = out["modules"].get("StatusModule", {}).get("status_kind")
        out["active"] = st is not None and st != 0xFFFFFFFF
        return out


MASK = {"u8": 0xFF, "i8": 0xFF, "u16": 0xFFFF, "u32": 0xFFFFFFFF, "i32": 0xFFFFFFFF, "u64": (1 << 64) - 1}


def verify(rd, recs, index_path):
    """Every named field of every object against the game's own getter, called at the same moment (the VALS records).
    Returns (equal, different) and prints the fields by class of object; a field counts for an object only when the
    getter's function in that object's own class is a plain load (the reader names it)."""
    index = {int(k): tuple(v) for k, v in json.load(open(index_path)).items()}
    eq, ne = collections.Counter(), collections.Counter()
    seen_values = collections.defaultdict(set)   # (the fields behind pointers: the values each one took)
    skipped = collections.Counter()
    examples = []
    objects = 0
    for r in recs:
        game = r.get("game")
        if not game:
            continue
        objects += 1
        cat = CATEGORY.get(r["id"] >> 28, "?")
        by_name, by_arg = {}, {}
        for o, (addr, b) in r["mods"].items():
            name = rd.off_name.get(o)
            if name and len(b) >= 8:
                by_name[name] = b
                by_arg[name] = rd.arg_values(r, name, addr, b)
        for idx, (fb, x0) in game.items():
            mod, meth = index[idx]
            b = by_name.get(mod)
            if b is None:
                continue
            if "(" in meth:   # a getter with arguments: the field behind pointers
                got = by_arg[mod].get(meth)
                if got is None:
                    skipped[(cat, mod, meth)] += 1
                    continue
                kind, size, ours = got[:3]
                theirs = fb if kind == "f32" else x0 & ((1 << 8 * min(size, 4)) - 1) if kind == "u" else x0 & 0xFF
                if ours == theirs:
                    eq[(cat, mod, meth)] += 1
                    seen_values[(cat, mod, meth)].add(ours)
                else:
                    ne[(cat, mod, meth)] += 1
                    if len(examples) < 10:
                        examples.append(f"frame {r['frame']} {cat} {r['id']:#x} {mod}.{meth} ({kind}): reader {ours:#x} game {theirs:#x}")
                continue
            vptr = struct.unpack_from("<Q", b, 0)[0]
            f = next((e for e in rd.dic.fields_for(vptr, mod) if e[0] == meth), None)
            if f is None:
                skipped[(cat, mod, meth)] += 1
                continue
            _m, fo, kind = f
            if fo + struct.calcsize(KIND[kind]) > len(b):
                continue
            if kind in ("f32",):
                ours, theirs = struct.unpack_from("<I", b, fo)[0], fb
            elif kind == "f64":
                continue
            else:
                raw = struct.unpack_from(KIND[kind].replace("i", "I").replace("b", "B"), b, fo)[0]
                ours, theirs = raw & MASK[kind], x0 & MASK[kind]
            if ours == theirs:
                eq[(cat, mod, meth)] += 1
            else:
                ne[(cat, mod, meth)] += 1
                if len(examples) < 10:
                    examples.append(f"frame {r['frame']} {cat} {r['id']:#x} {mod}.{meth} (+{fo:#x} {kind}): reader {ours:#x} game {theirs:#x}")
    fields_ok = sorted(k for k in eq if k not in ne)
    fields_bad = sorted(ne)
    print(f"automatic check of the named fields: {objects} objects; {sum(eq.values())} values equal, {sum(ne.values())} different; "
          f"{len(fields_ok)} (class, field) pairs always equal, {len(fields_bad)} with a difference; "
          f"{sum(skipped.values())} values not named for the object's class")
    if seen_values:
        moved = sum(1 for k, v in seen_values.items() if len(v) > 1 and k not in ne)
        print(f"  fields behind pointers (getters with arguments): {len(seen_values)} checked, {moved} of them with a value that changed, "
              f"{sum(eq[k] for k in seen_values)} values equal")
    by_cat = collections.Counter()
    for (cat, _m, _f), n in eq.items():
        by_cat[cat] += n
    print("  equal values by category:", dict(by_cat))
    for k in fields_bad[:25]:
        print(f"  DIFFERENT {k[0]} {k[1]}.{k[2]}: {ne[k]} different, {eq.get(k, 0)} equal")
    for e in examples:
        print("   ", e)
    return sum(eq.values()), sum(ne.values()), fields_bad


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
    ap.add_argument("--verify", help="the getters' index (<verify list>.json): check every named field against the game")
    ap.add_argument("--frame", type=int)
    ap.add_argument("--json")
    a = ap.parse_args()
    rd = Reader(a.fields)
    recs = [r for r in records(a.dump) if r["kind"] != 2]
    decoded = [rd.decode(r) for r in recs]
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
    ok = True
    if a.verify:
        _eq, ne, _bad = verify(rd, recs, a.verify)
        ok = ok and ne == 0
    if a.hash:
        ok = check_hash(decoded, a.hash) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
