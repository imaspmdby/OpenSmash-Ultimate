"""Two readings of a state dump (SSBU_STATE_DUMP, reader.py) that span frames.

    deps/python/python.exe research/tools/match.py diff <dump> <frame A> <frame B> [--all]
    deps/python/python.exe research/tools/match.py summary <dump> [--events N] [--json <out.json>]

diff: what changed between two dumped frames (the nearest dumped frame at or after each number): the objects that
came, went, woke or fell asleep, and for each object present in both, every named field whose value changed. Then,
per module, how many of the bytes that changed lie in named fields: what the reader does not name yet, where it is.
(--all also lists the objects with no named change.)

summary: a whole match from a dump made at every frame (`matrix.py --state 1`): per fighter, the damage taken and
the hits, the damage resets, the time on the ground and in the air, the statuses, the active hitboxes, the hitstop,
the distance covered; per category of other object, how many came to life and for how long; and the match's events
in order. With a dump made every N frames the counts are those of the frames seen, said in the first line.
"""
import collections
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reader  # noqa: E402

SITUATION = {0: "ground", 1: "cliff", 2: "air"}   # (StatusModule::situation_kind: SITUATION_KIND_GROUND / CLIFF / AIR)


def fmt(v):
    if isinstance(v, float):
        return "%.4g" % v
    return hex(v) if isinstance(v, int) and abs(v) > 9 else str(v)


def pick(frames, want):
    later = [f for f in frames if f >= want]
    return later[0] if later else frames[-1]


def diff(path, fa, fb, show_all):
    rd = reader.Reader()
    frames = sorted({r["frame"] for r in reader.records(path, light=True)})
    fa, fb = pick(frames, fa), pick(frames, fb)
    recs = {fa: {}, fb: {}}
    for r in reader.records(path, only=(fa, fb)):
        if r["kind"] != 2:
            recs[r["frame"]].setdefault(r["id"], r)
    a, b = recs[fa], recs[fb]
    da = {i: rd.decode(r) for i, r in a.items()}
    db = {i: rd.decode(r) for i, r in b.items()}
    print(f"frame {fa} -> frame {fb}: {len(a)} and {len(b)} objects")
    for i in sorted(set(b) - set(a)):
        print(f"  came:  {reader.summary(db[i])}")
    for i in sorted(set(a) - set(b)):
        print(f"  went:  {reader.summary(da[i])}")
    changed_fields = same_fields = quiet = 0
    by_mod = collections.defaultdict(lambda: [0, 0, 0])   # module -> [bytes changed, of them named, objects]
    behind = collections.defaultdict(lambda: [0, 0])      # module -> [bytes changed behind its pointers, of them named]
    for i in sorted(set(a) & set(b)):
        x, y = da[i], db[i]
        lines = []
        if x["active"] != y["active"]:
            lines.append("woke up" if y["active"] else "fell asleep")
        for mod in sorted(set(x["modules"]) | set(y["modules"])):
            mx, my = x["modules"].get(mod, {}), y["modules"].get(mod, {})
            ch = []
            for k in sorted(set(mx) | set(my)):
                u, v = mx.get(k), my.get(k)
                same = u == v or (isinstance(u, float) and isinstance(v, float) and struct.pack("<f", u) == struct.pack("<f", v))
                if same:
                    same_fields += 1
                else:
                    changed_fields += 1
                    ch.append(f"{k} {fmt(u) if u is not None else '-'} -> {fmt(v) if v is not None else '-'}")
            if ch:
                lines.append(f"{mod}: " + ", ".join(ch))
        # the raw bytes: how much of what changed is named
        for o in set(a[i]["mods"]) & set(b[i]["mods"]):
            name = rd.off_name.get(o)
            ba, bb = a[i]["mods"][o][1], b[i]["mods"][o][1]
            if not name or len(ba) < 8 or ba[:8] != bb[:8]:
                continue
            vptr = struct.unpack_from("<Q", ba, 0)[0]
            named = set()
            for _m, fo, kind in rd.dic.fields_for(vptr, name) + reader.SPECIAL.get(name, []):
                named.update(range(fo, fo + struct.calcsize(reader.KIND[kind])))
            # the blocks behind the module's pointers (one and more levels): the bytes the fields of argprobe.py name
            maddr = a[i]["mods"][o][0]
            places = collections.defaultdict(set)
            for _k, size, _v, blk, off in rd.arg_values(a[i], name, maddr, ba).values():
                if blk == maddr:
                    named.update(range(off, off + size))
                else:
                    places[blk].update(range(off, off + size))
            todo, done = [maddr], set()
            while todo:
                parent = todo.pop()
                for po, (addr, bx) in a[i]["behind"].get(parent, {}).items():
                    other = b[i]["behind"].get(parent, {}).get(po)
                    if addr in done or not other or other[0] != addr or addr in (m[0] for m in a[i]["mods"].values()):
                        continue
                    done.add(addr)
                    todo.append(addr)
                    by = other[1]
                    cb2 = [j for j in range(min(len(bx), len(by))) if bx[j] != by[j]]
                    behind[name][0] += len(cb2)
                    behind[name][1] += sum(1 for j in cb2 if j in places[addr])
            n = min(len(ba), len(bb))
            cb = [j for j in range(n) if ba[j] != bb[j]]
            if cb:
                by_mod[name][0] += len(cb)
                by_mod[name][1] += sum(1 for j in cb if j in named)
                by_mod[name][2] += 1
        if lines or show_all:
            print(f"  {x['category']} {i:#010x}" + ("" if y["active"] else " (inactive)") + (":" if lines else ": no named change"))
            for ln in lines:
                print("      " + ln)
        else:
            quiet += 1
    print(f"  {quiet} objects with no named change; {changed_fields} named values changed, {same_fields} the same")
    tot = sum(v[0] for v in by_mod.values())
    nam = sum(v[1] for v in by_mod.values())
    print(f"  the modules' bytes that changed (first {0x900:#x} bytes of each): {tot}, of them {nam} in named fields ({100 * nam // max(1, tot)} %)")
    for name, (c, n, objs) in sorted(by_mod.items(), key=lambda kv: -kv[1][0])[:14]:
        print(f"      {name:28} {c:6} bytes changed in {objs:3} objects, {n:5} named")
    tb, nb = sum(v[0] for v in behind.values()), sum(v[1] for v in behind.values())
    print(f"  behind the modules' pointers (the blocks the dump holds): {tb} bytes changed, of them {nb} in named fields ({100 * nb // max(1, tb)} %)")
    for name, (c, n) in sorted(behind.items(), key=lambda kv: -kv[1][0])[:8]:
        if c:
            print(f"      {name:28} {c:6} bytes changed, {n:5} named")


def summary(path, nevents, json_out):
    rd = reader.Reader()
    fighters = collections.OrderedDict()
    others = {}
    events = []
    frames = set()
    for r in reader.records(path):
        if r["kind"] == 2:
            continue
        d = rd.decode(r)
        f, i, m = d["frame"], d["id"], d["modules"]
        frames.add(f)
        if d["category"] == "fighter":
            if not d["at_line"]:
                continue
            s = fighters.get(i)
            if s is None:
                s = fighters[i] = {"frames": 0, "first": f, "last": f, "hits": 0, "taken": 0.0, "resets": 0, "max": 0.0, "dmg": None,
                                   "sit": collections.Counter(), "status": collections.Counter(), "changes": 0, "st": None,
                                   "attack": 0, "hitstop": 0, "dist": 0.0, "pos": None, "x": [1e9, -1e9], "y": [1e9, -1e9], "turns": 0, "lr": None}
            s["frames"] += 1
            s["last"] = f
            dmg = m.get("DamageModule", {}).get("damage")
            if dmg is not None:
                if s["dmg"] is not None and dmg > s["dmg"] + 1e-4:
                    s["hits"] += 1
                    s["taken"] += dmg - s["dmg"]
                    events.append((f, f"fighter {i:#x} takes {dmg - s['dmg']:.1f} % (now {dmg:.1f} %)"))
                elif s["dmg"] is not None and s["dmg"] > 0 and dmg == 0:
                    s["resets"] += 1
                    events.append((f, f"fighter {i:#x}: damage back to 0 from {s['dmg']:.1f} %"))
                s["dmg"] = dmg
                s["max"] = max(s["max"], dmg)
            st = m.get("StatusModule", {})
            if "situation_kind" in st:
                s["sit"][SITUATION.get(st["situation_kind"], str(st["situation_kind"]))] += 1
            if "status_kind" in st:
                s["status"][st["status_kind"]] += 1
                if s["st"] is not None and st["status_kind"] != s["st"]:
                    s["changes"] += 1
                s["st"] = st["status_kind"]
            if (m.get("AttackModule", {}).get("active_part_num") or 0) > 0:
                s["attack"] += 1
            if (m.get("StopModule", {}).get("get_hit_stop_real_frame") or 0) > 0:
                s["hitstop"] += 1
            p = m.get("PostureModule", {})
            if "pos_x" in p:
                x, y = p["pos_x"], p["pos_y"]
                if s["pos"] is not None:
                    step = ((x - s["pos"][0]) ** 2 + (y - s["pos"][1]) ** 2) ** 0.5
                    if step < 60:   # (a respawn's jump is not distance covered)
                        s["dist"] += step
                s["pos"] = (x, y)
                s["x"] = [min(s["x"][0], x), max(s["x"][1], x)]
                s["y"] = [min(s["y"][0], y), max(s["y"][1], y)]
                if s["lr"] is not None and p.get("lr") not in (None, 0, s["lr"]):
                    s["turns"] += 1
                if p.get("lr"):
                    s["lr"] = p["lr"]
        else:
            o = others.get(i)
            if o is None:
                o = others[i] = {"category": d["category"], "lives": 0, "frames": 0, "active": False}
            if d["active"]:
                o["frames"] += 1
                if not o["active"]:
                    o["lives"] += 1
                    events.append((f, f"{d['category']} {i:#x} comes to life"))
            o["active"] = d["active"]
    fl = sorted(frames)
    step = (fl[-1] - fl[0]) // max(1, len(fl) - 1) if len(fl) > 1 else 1
    print(f"match: fight frames {fl[0]}..{fl[-1]} ({(fl[-1] - fl[0]) / 60:.1f} s), {len(fl)} frames seen (one every {step}); "
          f"{len(fighters)} fighters, {len(others)} other objects")
    for i, s in fighters.items():
        n = max(1, s["frames"])
        top = ", ".join(f"{k:#x} {100 * v // n} %" for k, v in s["status"].most_common(4))
        sit = ", ".join(f"{k} {100 * v // n} %" for k, v in s["sit"].most_common())
        print(f"  fighter {i:#x}: damage taken {s['taken']:.1f} % in {s['hits']} hits (highest {s['max']:.1f} %, at the end {s['dmg'] or 0:.1f} %), "
              f"damage back to 0 {s['resets']} times")
        print(f"      {sit}; {s['changes']} status changes, most seen {top}")
        print(f"      hitboxes out {s['attack']} frames, in hitstop {s['hitstop']} frames, turned {s['turns']} times; "
              f"covered {s['dist']:.0f} units, x {s['x'][0]:.0f}..{s['x'][1]:.0f}, y {s['y'][0]:.0f}..{s['y'][1]:.0f}")
    cats = collections.defaultdict(lambda: [0, 0, 0, 0])
    for o in others.values():
        c = cats[o["category"]]
        c[0] += 1
        c[1] += 1 if o["lives"] else 0
        c[2] += o["lives"]
        c[3] += o["frames"]
    for cat, (n, used, lives, fr) in sorted(cats.items()):
        print(f"  {cat}s: {n} objects seen, {used} came to life ({lives} times in all, {fr // max(1, lives)} frames seen a life)")
    events.sort(key=lambda e: e[0])
    main_events = [e for e in events if "comes to life" not in e[1]]
    print(f"  events: {len(events)} ({len(main_events)} hits and damage resets; the first {min(nevents, len(main_events))}):")
    for f, t in main_events[:nevents]:
        print(f"      frame {f:5}  {t}")
    if json_out:
        with open(json_out, "w") as out:
            json.dump({"frames": [fl[0], fl[-1], len(fl)],
                       "fighters": {hex(i): {k: (dict(v) if isinstance(v, collections.Counter) else v) for k, v in s.items() if k not in ("pos", "st", "lr")}
                                    for i, s in fighters.items()},
                       "others": {hex(i): o for i, o in others.items()}, "events": events}, out, indent=1)
        print("written:", json_out)


def main():
    a = sys.argv[1:]
    if len(a) >= 4 and a[0] == "diff":
        diff(a[1], int(a[2]), int(a[3]), "--all" in a)
    elif len(a) >= 2 and a[0] == "summary":
        n = int(a[a.index("--events") + 1]) if "--events" in a else 25
        summary(a[1], n, a[a.index("--json") + 1] if "--json" in a else None)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
