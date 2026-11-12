"""community: names from the Smash Ultimate modding community (research/map/community/, SOURCES.md), as the game confirmed them.

research/map/community/confirmed.csv holds the constants whose value the game itself gave back (the runtime's
SSBU_CONST_CHECK: lib::lua_bind_get_value<int> of each name, as lua2cpp_common gets its constants; 2026-11-12: 38,579 of
38,774 the same, 2 different, 193 unknown to the game). Only those name anything here.

    labels = Names()
    labels.work("FIGHTER", "MARIO", "get_int", 0x10000004)  -> "FIGHTER_INSTANCE_WORK_ID_INT_CLIFF_NO_CATCH_FRAME"
    labels.status("FIGHTER", "MARIO", 0x48)                  -> "FIGHTER_STATUS_KIND_DAMAGE_AIR"
    labels.hash40(0x...)                                     -> a param-labels label

  community.py --make <SSBU_CONST_CHECK's .out>   writes confirmed.csv
"""
import collections
import csv
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIR = os.path.join(ROOT, "research", "map", "community")
TYPE = {"get_int": "INT", "get_int64": "INT64", "get_float": "FLOAT", "is_flag": "FLAG"}
FIELD = re.compile(r"^(get_int64|get_int|get_float|is_flag)\((0x[0-9a-f]+)\)$")


class Names:
    def __init__(self):
        self.value = {}
        with open(os.path.join(DIR, "confirmed.csv"), newline="") as f:
            r = csv.reader(f)
            next(r)
            for n, v in r:
                self.value[n] = int(v, 16)
        self.by_value = collections.defaultdict(list)
        for n, v in self.value.items():
            self.by_value[v].append(n)
        self.kinds = {}   # (category, value) -> kind's name (MARIO)
        for n, v in self.value.items():
            for cat in ("FIGHTER", "WEAPON", "ITEM"):
                rest = n[len(cat) + 6:]
                if (n.startswith(cat + "_KIND_") and not n.endswith(("_NUM", "_NONE", "_ALL", "_HEAD", "_TAIL"))
                        and not rest.startswith(("BASE_", "OTHER_", "APPEND_"))):   # (range markers share values)
                    self.kinds.setdefault((cat, v), n[len(cat) + 6:])
        self.h40 = None

    def kind(self, cat, value):
        return self.kinds.get((cat, value))

    def _pick(self, value, prefixes):
        c = [n for n in self.by_value.get(value, ()) if n.startswith(prefixes)]
        return c[0] if len(c) == 1 else (sorted(c) if c else None)

    def work(self, cat, kind, getter, wid):
        """A work variable's name: the instance's first (common, then the kind's own), else the status's (whose meaning
        depends on the status: a list when several statuses use the id)."""
        t = TYPE[getter]
        own = (f"{cat}_{kind}_" if kind else None)
        for scope in ("INSTANCE", "STATUS"):
            pre = (f"{cat}_{scope}_WORK_ID_{t}_",)
            n = self._pick(wid, pre)
            if isinstance(n, str):
                return n
            if own:
                m = [x for x in self.by_value.get(wid, ()) if x.startswith(own) and f"_{scope}_" in x and f"_{t}_" in x]
                if len(m) == 1:
                    return m[0]
                if m:
                    return sorted(m)
            if n:
                return n
        return None

    def status(self, cat, kind, value):
        n = self._pick(value, (f"{cat}_STATUS_KIND_",))
        if isinstance(n, str) and not n.endswith("_NUM"):
            return n
        if kind:
            m = [x for x in self.by_value.get(value, ()) if x.startswith(f"{cat}_{kind}_STATUS_KIND_")]
            if len(m) == 1:
                return m[0]
        return None

    def hash40(self, h):
        if self.h40 is None:
            self.h40 = {}
            with open(os.path.join(DIR, "ParamLabels.csv"), newline="", encoding="utf-8") as f:
                for row in csv.reader(f):
                    if len(row) >= 2 and row[1]:
                        self.h40[int(row[0], 16)] = row[1]
        return self.h40.get(h & 0xFFFFFFFFFF)

    def field(self, cat, kind, fname):
        m = FIELD.match(fname)
        return self.work(cat, kind, m.group(1), int(m.group(2), 16)) if m else None


def make(out_path):
    keep = []
    for ln in open(out_path):
        p = ln.split()
        if len(p) == 3 and p[2] != "absent" and int(p[1], 16) == int(p[2], 16):
            keep.append((p[0], p[1]))
    with open(os.path.join(DIR, "confirmed.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["name", "value"])
        w.writerows(keep)
    print(len(keep), "constants the game confirmed")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--make":
        make(sys.argv[2])
    else:
        nm = Names()
        print(nm.work("FIGHTER", "MARIO", "get_int", 0x10000004), nm.status("FIGHTER", "MARIO", 0x48),
              nm.kind("FIGHTER", nm.value["FIGHTER_KIND_MARIO"]), nm.work("FIGHTER", None, "get_float", 0x11))
