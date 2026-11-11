"""A dictionary of the modules' fields, from the game's own getters.

    deps/python/python.exe research/tools/fields.py <types.json> [<out.json>]

Each exported app::lua_bind::<Module>__<method>_impl loads the module from the boma (`ldr x0, [x0, #off]`), its
vtable (`ldr x8, [x0]`) and a slot (`ldr xN, [x8, #slot]`), then calls it. With the module's vtable (types.json: the
vptrs found in a fighter's boma), the slot's function is known; when that function is a plain getter (`ldr / ldrb /
ldrsw / ldr s0 ... [x0, #off]` then `ret`), the method names a field: module, method, offset in the module object,
kind (f32, u32, i32, u8, u64). Functions that are not plain getters are listed as "code" (computed, or through
another object). Prints a summary and writes the dictionary.
"""
import collections
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtti  # noqa: E402

BASE = 0x7100000000
RET = 0xD65F03C0


def decode_getter(m, off):
    """(field offset, kind) when the function at off is `load [x0, #imm]; ret` (optionally a load pair of words)."""
    w0, w1 = struct.unpack_from("<II", m.image, off)
    if w1 != RET:
        return None
    rn = w0 >> 5 & 31
    if rn != 0:
        return None
    imm = w0 >> 10 & 0xFFF
    top = w0 & 0xFFC00000
    table = {
        0xBD400000: ("f32", 4),    # ldr s, [x0, #imm*4]
        0xFD400000: ("f64", 8),    # ldr d
        0xB9400000: ("u32", 4),    # ldr w
        0xF9400000: ("u64", 8),    # ldr x
        0x39400000: ("u8", 1),     # ldrb
        0x79400000: ("u16", 2),    # ldrh
        0xB9800000: ("i32", 4),    # ldrsw
        0x39C00000: ("i8", 1),     # ldrsb (to w)
        0x39800000: ("i8", 1),     # ldrsb (to x)
    }
    if top in table:
        kind, scale = table[top]
        return imm * scale, kind
    return None


class Dictionary:
    """The fields of a module object, by its class: fields_for(vptr, module name) -> [(method, offset, kind)].
    The getters give each method's vtable slot (the same for every class of a module: fighters', weapons', items');
    the class's own vtable gives the function, read as a plain getter when it is one."""

    def __init__(self, names=None):
        self.names = names or rtti.Names()
        m = self.names.m
        pat = re.compile(r"^_ZN3app8lua_bind\d+([A-Za-z0-9]+Module)__(\w+)_impl")
        self.slots = collections.defaultdict(dict)   # module -> {method: slot}
        self.syms = collections.defaultdict(dict)    # module -> {method: (exported name, takes the boma alone)}
        self.boma_off = {}
        self.impure = collections.defaultdict(set)   # module -> methods whose getter does more than relay
        for n, v, sz, _i, _sh in m.exports:
            k = pat.match(n)
            if not k or sz < 12:
                continue
            ws = list(struct.unpack_from("<%dI" % min(10, sz // 4), m.image, v))
            seen_mod = seen_vt = False
            for w in ws:
                if not seen_mod and (w & 0xFFC003E0) == 0xF9400000:
                    seen_mod = True
                    self.boma_off.setdefault(k.group(1), (w >> 10 & 0xFFF) * 8)
                elif seen_mod and not seen_vt and (w & 0xFFC00000) == 0xF9400000 and (w >> 10 & 0xFFF) == 0:
                    seen_vt = True
                elif seen_vt and (w & 0xFFC00000) == 0xF9400000:
                    # only a pure relay names a field: the slot's call must be the getter's last act (`br xN`, or
                    # `blr xN; ldp x29, x30, [sp], #16; ret`). A getter that works on the result (is_situation_changed
                    # compares, pos_x loads through the pointer returned) is code, not a field: the automatic check
                    # (reader.py --verify) caught is_situation_changed read as situation_kind's field.
                    i = ws.index(w)
                    after = ws[i + 1:i + 4]
                    pure = bool(after) and ((after[0] & 0xFFFFFC1F) == 0xD61F0000 or
                                            (len(after) >= 3 and (after[0] & 0xFFFFFC1F) == 0xD63F0000 and
                                             after[1] == 0xA8C17BFD and after[2] == 0xD65F03C0))
                    if pure:
                        self.slots[k.group(1)][k.group(2)] = (w >> 10 & 0xFFF) * 8
                        self.syms[k.group(1)][k.group(2)] = (n, n.endswith("_implEPNS_26BattleObjectModuleAccessorE"))
                    else:
                        self.impure[k.group(1)].add(k.group(2))
                    break
        self.off_name = {}
        for name, off in self.boma_off.items():
            if off:
                self.off_name.setdefault(off, name)
        self.cache = {}

    def fields_for(self, vptr, module):
        key = (vptr, module)
        if key not in self.cache:
            out = []
            if 0x7104f17000 <= vptr < 0x71052aa000:
                for meth, slot in self.slots.get(module, {}).items():
                    fn = self.names.word(vptr - BASE + slot)
                    if fn is None or not 0 < fn < 0x39c8440:
                        continue
                    g = decode_getter(self.names.m, fn)
                    if g:
                        out.append((meth, g[0], g[1]))
            self.cache[key] = sorted(out, key=lambda e: e[1])
        return self.cache[key]


def verify_list(dic, ref_vptrs):
    """The getters to call for the automatic check: [(index, module, method, boma offset, exported name, vtable slot)], the methods
    that are plain fields in the reference classes (a fighter's modules) and take the boma alone. The index is the
    position in the sorted list: stable for one game version."""
    out = []
    for mod in sorted(dic.slots):
        vptr = ref_vptrs.get(mod)
        if vptr is None or mod not in dic.boma_off or not dic.boma_off[mod]:
            continue
        plain = {m for m, _o, _k in dic.fields_for(vptr, mod)}
        for meth in sorted(dic.slots[mod]):
            sym, alone = dic.syms[mod][meth]
            if meth in plain and alone:
                out.append((len(out), mod, meth, dic.boma_off[mod], sym, dic.slots[mod][meth]))
    return out


def probe_list(dic, ref_vptrs):
    """Every pure relay getter that takes the boma alone, plain or code: [(index, module, method, boma offset,
    exported name, vtable slot)], for SSBU_PROBE_FIELDS (which bytes does each one read?)."""
    out = []
    for mod in sorted(dic.slots):
        if mod not in dic.boma_off or not dic.boma_off[mod]:
            continue
        plain = {m for m, _o, _k in dic.fields_for(ref_vptrs.get(mod, 0), mod)}
        for meth in sorted(dic.slots[mod]):
            sym, alone = dic.syms[mod][meth]
            # read-only by its name (get_, is_, has_, can_) or already known as a plain field: a method taking the boma
            # alone may also act (AreaModule::force_update stopped the first probe run)
            # (LinkModule's getters of a parent / a constraint target follow a link a lone fighter does not have: they
            #  stopped the probe runs one after the other)
            if mod == "LinkModule" and ("parent" in meth or "target" in meth or "node" in meth):
                continue
            if alone and (meth in plain or meth.startswith(("get_", "is_", "has_", "can_"))):
                out.append((len(out), mod, meth, dic.boma_off[mod], sym, dic.slots[mod][meth]))
    return out


def main():
    if "--probe-list" in sys.argv:   # fields.py <types.json> --probe-list <out.txt>
        dic = Dictionary()
        tj = json.load(open(sys.argv[1]))
        lst = probe_list(dic, {v.split("::")[1]: int(k, 16) for k, v in tj["module_vptrs"].items()})
        path = sys.argv[sys.argv.index("--probe-list") + 1]
        with open(path, "w") as f:
            for i, mod, meth, off, sym, slot in lst:
                f.write("%d %x %x %s\n" % (i, off, slot, sym))
        with open(path + ".json", "w") as f:
            json.dump({str(i): [mod, meth] for i, mod, meth, _o, _s, _sl in lst}, f, indent=1)
        print(f"{len(lst)} getters to probe, in {len({m for _i, m, _a, _o, _s, _sl in lst})} modules: {path}")
        return
    if "--verify-list" in sys.argv:   # fields.py <types.json> --verify-list <out.txt>: for SSBU_VERIFY_FIELDS
        tj = json.load(open(sys.argv[1]))
        dic = Dictionary()
        ref = {v.split("::")[1]: int(k, 16) for k, v in tj["module_vptrs"].items()}
        lst = verify_list(dic, ref)
        path = sys.argv[sys.argv.index("--verify-list") + 1]
        with open(path, "w") as f:
            for i, mod, meth, off, sym, slot in lst:
                f.write(f"{i} {off:x} {slot:x} {sym}\n")
        with open(path + ".json", "w") as f:
            json.dump({str(i): [mod, meth] for i, mod, meth, _o, _s, _sl in lst}, f, indent=1)
        print(f"{len(lst)} getters to check, in {len({m for _i, m, _a, _o, _s, _sl in lst})} modules: {path}")
        return
    tj = json.load(open(sys.argv[1]))
    out = sys.argv[2] if len(sys.argv) > 2 else None
    names = rtti.Names()
    m = names.m
    vptr_of = {v.split("::")[1]: int(k, 16) for k, v in tj["module_vptrs"].items()}
    boma_off = {v: int(k, 16) for k, v in tj["module_offsets"].items()}
    pat = re.compile(r"^_ZN3app8lua_bind\d+([A-Za-z0-9]+Module)__(\w+)_impl")
    fields = collections.defaultdict(list)
    stats = collections.Counter()
    for n, v, sz, _i, _sh in m.exports:
        k = pat.match(n)
        if not k or sz < 12:
            continue
        mod, meth = k.group(1), k.group(2)
        if mod not in vptr_of:
            stats["module without a vptr"] += 1
            continue
        ws = struct.unpack_from("<%dI" % min(8, sz // 4), m.image, v)
        slot = None
        seen_mod = seen_vt = False
        for w in ws:
            if not seen_mod and (w & 0xFFC003E0) == 0xF9400000:        # ldr xT, [x0, #off]: the module
                seen_mod = True
            elif seen_mod and not seen_vt and (w & 0xFFC00000) == 0xF9400000 and (w >> 10 & 0xFFF) == 0:   # ldr x8, [xM]
                seen_vt = True
            elif seen_vt and (w & 0xFFC00000) == 0xF9400000:            # ldr xN, [x8, #slot]
                slot = (w >> 10 & 0xFFF) * 8
                break
        if slot is None:
            stats["getter shape not understood"] += 1
            continue
        fn = names.word(vptr_of[mod] - BASE + slot)
        if fn is None or not 0 < fn < 0x39c8440:
            stats["slot not a function"] += 1
            continue
        g = decode_getter(m, fn)
        entry = {"method": meth, "slot": slot, "function": hex(BASE + fn)}
        if g:
            entry.update(offset=g[0], kind=g[1])
            stats["plain field"] += 1
        else:
            stats["code"] += 1
        fields[mod].append(entry)
    print("methods:", dict(stats))
    plain = {mod: [e for e in es if "offset" in e] for mod, es in fields.items()}
    for mod in sorted(plain, key=lambda x: -len(plain[x])):
        es = plain[mod]
        if not es:
            continue
        print(f"{mod} (boma+{boma_off.get(mod, 0):#x}): {len(es)} plain fields of {len(fields[mod])} methods")
        print("   " + ", ".join(f"{e['method']}@{e['offset']:#x}:{e['kind']}" for e in sorted(es, key=lambda e: e["offset"])[:14]))
    if out:
        with open(out, "w") as f:
            json.dump({"boma_offsets": boma_off, "vptrs": {k: hex(v) for k, v in vptr_of.items()}, "modules": fields}, f, indent=1)


if __name__ == "__main__":
    main()
