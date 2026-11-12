"""The getters that take arguments (WorkModule::get_int(id), KineticModule::is_enable_energy(id), AttackModule::
is_attack(index)...): where each (getter, argument) reads its answer, found by the probe (SSBU_PROBE_FIELDS in
build-trace: every byte a call read, with the word there).

    deps/python/python.exe research/tools/argprobe.py list <out.txt>           the calls to probe (+ <out.txt>.json)
    deps/python/python.exe research/tools/argprobe.py show <run> [<getter>]    each call's chain of reads, as seen
    deps/python/python.exe research/tools/argprobe.py fields <run> [<run> ...] [--write]

A call's reads are followed from the boma: a read at an address is placed behind the nearest pointer read before it
(the boma's word for the module, a word of the module, a word behind it...): a path of offsets, [module's offset in
the boma, offset in the module, offset behind that pointer, ...].

For each (class of module, getter, arguments), every reading of a value read by the call that gives the call's
answer is a hypothesis: the value itself (f32, or an integer of the read's size), "not zero", "zero", one bit of it,
or that bit inverted. The hypotheses are intersected over every object and frame probed. A call is a FIELD
  - "seen": its answers took two values at least and one reading explains them all (the plainest one when several
    do: the value, then not zero / zero, then a bit);
  - "by family": its answer never changed (all the flags that stayed 0), but the other arguments of the same getter
    in the same class that were seen all read the same place's kind (same path but the last offset, same reading; for
    a bit, the bit is the argument modulo the word's size) and that reading is among its hypotheses.
A getter over a counted table (WorkModule's: the count is the word before the table's pointer) names only the
arguments below the count. --write: research/map/arg_fields.json (by class: module, getter, arguments, path after
the boma's offset, reading, size, the table's element size or 0) and research/map/state_paths.txt (the blocks the
dump must hold for the reader to follow the paths: SSBU_STATE_PATHS). Every field is then checked against the game
at every dumped frame by research/tools/verify_fields.sh, like the plain getters' fields.
"""
import collections
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reader  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAP = os.path.join(ROOT, "research", "map")
INDEX = os.path.join(MAP, "probe_args.txt.json")
ARG_FIELDS = os.path.join(MAP, "arg_fields.json")
STATE_PATHS = os.path.join(MAP, "state_paths.txt")
N = 0x120
# (module, method, argument signature, [argument tuples], a counted table?)
# Left out, seen to stop the game on some objects: HitModule::get_status(part, index) (reads through a pointer that
# is not there in every state), and every getter called on a weapon that is not in play.
CALLS = [
    ("WorkModule", "get_float", "i", [(b + n,) for b in (0x0, 0x1000000) for n in range(N)], True),
    ("WorkModule", "get_int", "i", [(b + n,) for b in (0x10000000, 0x11000000) for n in range(N)], True),
    ("WorkModule", "is_flag", "i", [(b + n,) for b in (0x20000000, 0x21000000) for n in range(N)], True),
    ("KineticModule", "get_sum_speed_x", "i", [(n,) for n in range(8)], False),
    ("KineticModule", "get_sum_speed_y", "i", [(n,) for n in range(8)], False),
    ("KineticModule", "get_sum_speed_length", "i", [(n,) for n in range(8)], False),
    ("KineticModule", "is_enable_energy", "i", [(n,) for n in range(11)], False),
    ("KineticModule", "is_suspend_energy", "i", [(n,) for n in range(11)], False),
    ("AttackModule", "is_attack", "ib", [(n, 0) for n in range(8)], False),
    ("AttackModule", "is_invalid_invincible", "ib", [(n, 0) for n in range(8)], False),
    ("AttackModule", "is_invalid_xlu", "ib", [(n, 0) for n in range(8)], False),
    ("AttackModule", "get_lr", "ib", [(n, 0) for n in range(8)], False),
    ("ControlModule", "check_button_on", "i", [(n,) for n in range(20)], False),
    ("ControlModule", "check_button_off", "i", [(n,) for n in range(20)], False),
    ("ControlModule", "check_button_trigger", "i", [(n,) for n in range(20)], False),
    ("ControlModule", "check_button_release", "i", [(n,) for n in range(20)], False),
    ("ControlModule", "get_command_flag_cat", "i", [(n,) for n in range(4)], False),
    ("ControlModule", "get_trigger_count", "h", [(n,) for n in range(20)], False),
    ("HitModule", "get_whole", "i", [(n,) for n in range(3)], False),
    ("HitModule", "get_total_status", "i", [(n,) for n in range(3)], False),
]
COUNTED = {(c[0], c[1]) for c in CALLS if c[4]}
# Families the automatic check refused (verify_fields.sh, run vf_args, 2026-11-12): probed and read as "bit <argument>
# of one word", but at one frame of the four-player match the game answered otherwise for buttons 0x9, 0xe and 0x13
# (the getter does more than test a bit for some buttons). A family with one difference is left out whole.
# HitModule::get_total_status (run s1_wide, 2026-11-12): read at the same place as get_whole(2) on the fighters probed,
# but the Hero (brave) gave 0x100 where that place held 0, at 167 of 1,098 frames: the getter combines more than one
# place (whole and per-part status, by its look). Left out whole.
REJECTED = {("ControlModule", "check_button_trigger"), ("HitModule", "get_total_status")}
EXACT = ("f32", "u")


def name_of(meth, args):
    return "%s(%s)" % (meth, ", ".join("%#x" % a for a in args))


def symbols(dic):
    """(module, method) -> the exported getter, for CALLS."""
    exports = [n for n, _v, _sz, _i, _sh in dic.names.m.exports]
    out = {}
    for mod, meth, sig, _a, _c in CALLS:
        pat = re.compile(r"^_ZN3app8lua_bind\d+%s__%s_implEPNS_26BattleObjectModuleAccessorE%s$" % (mod, meth, sig))
        syms = [n for n in exports if pat.match(n)]
        if len(syms) == 1 and dic.boma_off.get(mod):
            out[(mod, meth)] = syms[0]
    # the fields named by reading the code (research/map/arg_fields.json entries marked "code"): their getter, when one
    # export alone has that module and method
    if os.path.exists(ARG_FIELDS):
        for v in json.load(open(ARG_FIELDS)).values():
            for mod, meth, *_rest in v:
                if (mod, meth) in out:
                    continue
                pat = re.compile(r"^_ZN3app8lua_bind\d+%s__%s_implEPNS_26BattleObjectModuleAccessorE\w*$" % (mod, meth))
                syms = [n for n in exports if pat.match(n)]
                if len(syms) == 1 and dic.boma_off.get(mod):
                    out[(mod, meth)] = syms[0]
    return out


def make_list(path):
    import fields
    dic = fields.Dictionary()
    syms = symbols(dic)
    lines, index = [], {}
    for mod, meth, sig, argsets, _c in CALLS:
        if (mod, meth) not in syms:
            print(f"  not found: {mod}::{meth}({sig})")
            continue
        for args in argsets:
            i = len(lines)
            lines.append("%d %x %x %s 0 %s" % (i, dic.boma_off[mod], dic.slots[mod].get(meth, 0), syms[(mod, meth)], " ".join("%x" % a for a in args)))
            index[str(i)] = [mod, meth, list(args)]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(path + ".json", "w") as f:
        json.dump(index, f)
    print(f"{len(lines)} calls to probe: {path}")


def heap(w):
    return 0x6000000000 <= w < 0x7800000000


def object_reads(reads):
    """A call's reads of the objects' memory: its own stack (what it wrote first), code and constants left out."""
    written = set()
    for addr, size, wr, val in reads:
        if wr:
            written.add(addr)
        elif addr not in written and not 0x7100000000 <= addr < 0x7400000000 and not 0x7700000000 <= addr < 0x7780000000:
            yield addr, size, val & ((1 << 8 * size) - 1)


def nearest(sorted_bases, addr):
    import bisect
    i = bisect.bisect_right(sorted_bases, addr) - 1
    return sorted_bases[i] if i >= 0 and addr < sorted_bases[i] + 0x40000 else None


def record_bases(rec):
    """Every pointer a record's calls read, with the path of the word it was read from: {pointer: path}. From all
    the calls together, so that a read past a table's end is seen to land in the next table."""
    import bisect
    bases = {rec["boma"]: ()}
    keys = [rec["boma"]]
    order = sorted(rec["probe"].items())
    for _pass in range(2):
        for _idx, (_x0, _fb, reads) in order:
            for addr, size, v in object_reads(reads):
                if size != 8 or not heap(v) or v in bases:
                    continue
                best = nearest(keys, addr)
                if best is not None:
                    bases[v] = bases[best] + (addr - best,)
                    bisect.insort(keys, v)
    return bases, keys


def chain(bases, reads):
    """[(path or None, size, value, address)] for a call's reads."""
    table, keys = bases
    out = []
    for addr, size, v in object_reads(reads):
        best = nearest(keys, addr)
        out.append((table[best] + (addr - best,) if best is not None else None, size, v, addr))
    return out


def hypotheses(ch, x0, fb, boma_off):
    """Every (path, size, reading) of a value the call read that gives its answer."""
    out = set()
    lo = x0 & 0xFFFFFFFF
    for path, size, v, _a in ch:
        if path is None or len(path) < 2 or path[0] != boma_off or (size == 8 and heap(v)):
            continue
        if size == 4 and v == fb:
            out.add((path, size, "f32"))
        if v == x0 & ((1 << 8 * size) - 1) and (size < 8 or v == x0):
            out.add((path, size, "u"))
        if lo in (0, 1):
            out.add((path, size, "nz" if (v != 0) == lo else "z"))
            for k in range(8 * size):
                out.add((path, size, ("bit%d" if (v >> k & 1) == lo else "nbit%d") % k))
    return out


def rank(reading):
    return 0 if reading in EXACT else 1 if reading in ("nz", "z") else 2


def klass(reading):
    return re.sub(r"\d+$", "", reading)


def load(run):
    index = {int(k): (v[0], v[1], tuple(v[2])) for k, v in json.load(open(INDEX)).items()}
    for r in reader.records(os.path.join(run, "state.bin")):
        if r.get("probe"):
            yield r, index


def show(run, only):
    for r, index in load(run):
        bases = record_bases(r)
        print(f"object {r['id']:#x} frame {r['frame']}: {len(r['probe'])} calls")
        seen = collections.Counter()
        for idx, (x0, fb, reads) in sorted(r["probe"].items()):
            mod, meth, args = index[idx]
            if only and meth != only:
                continue
            seen[(mod, meth)] += 1
            if not only and seen[(mod, meth)] > 4:
                continue
            ch = chain(bases, reads)
            txt = " ; ".join(("?%#x" % a if p is None else "/".join("%#x" % o for o in p)) + f":{s}={v:#x}" for p, s, v, a in ch[:12])
            print(f"  {mod}.{name_of(meth, args)} -> x0 {x0 & 0xFFFFFFFF:#x} v0 {fb:#x} | {txt}")


def block_bytes(rec, path):
    """The dumped bytes of the block a path of pointers leads to (path: the boma's offset, then pointer words)."""
    m = rec["mods"].get(path[0])
    if not m:
        return None
    addr, b = m
    for o in path[1:]:
        sub = rec["behind"].get(addr, {}).get(o)
        if not sub:
            return None
        addr, b = sub
    return b


def find_fields(runs, write):
    import fields
    dic = fields.Dictionary()
    hyp, nobs = {}, collections.Counter()
    values = collections.defaultdict(lambda: collections.defaultdict(set))   # key -> (path, size) -> the values read there
    counts = {}       # (key, the table's path) -> the smallest count seen (counted getters)
    nocount = set()
    for run in runs:
        for r, index in load(run):
            bases = record_bases(r)
            vptrs = {}
            for o, (_addr, b) in r["mods"].items():
                name = dic.off_name.get(o)
                if name and len(b) >= 8:
                    vptrs[name] = struct.unpack_from("<Q", b, 0)[0]
            hdr = {}
            for idx, (x0, fb, reads) in r["probe"].items():
                mod, meth, args = index[idx]
                key = (vptrs.get(mod, 0), mod, meth, args)
                ch = chain(bases, reads)
                h = hypotheses(ch, x0, fb, dic.boma_off[mod])
                hyp[key] = h if key not in hyp else hyp[key] & h
                nobs[key] += 1
                for path, size, v, _a in ch:
                    if path is not None:
                        values[key][(path, size)].add(v)
                if (mod, meth) in COUNTED:
                    for tp in {p[:-1] for p, _s, _k in h if len(p) >= 3 and p[-2] >= 8}:
                        if tp not in hdr:
                            b = block_bytes(r, tp[:-1])
                            hdr[tp] = struct.unpack_from("<Q", b, tp[-1] - 8)[0] if b is not None and len(b) >= tp[-1] else None
                        if hdr[tp] is None:
                            nocount.add((mod, meth))
                        else:
                            counts[(key, tp)] = min(hdr[tp], counts.get((key, tp), 1 << 62))
    if nocount:
        print("the tables' counts are not in the dump for:", sorted(nocount), "- run the probe with SSBU_STATE_PATHS (the tables' headers)")

    def derived(kind, v):
        if kind in EXACT:
            return v
        if kind in ("nz", "z"):
            return v != 0
        return v >> int(re.search(r"\d+$", kind).group()) & 1

    def supported(key, x):   # the place's value took two readings at least, and the hypothesis held each time
        path, size, kind = x
        return len({derived(kind, v) for v in values[key][(path, size)]}) >= 2

    def fits(x, args):   # a bit's number is the argument modulo the word's size
        kl = klass(x[2])
        return kl not in ("bit", "nbit") or int(x[2][len(kl):]) == args[0] % (8 * x[1])

    def sig(x):
        return len(x[0]), x[1], klass(x[2])

    # a getter's reading, by class: the plainest one that every argument whose value changed supports
    fam = collections.defaultdict(list)
    for key in hyp:
        fam[key[:3]].append(key)
    out, dropped = {}, 0
    found = {}
    for f, keys in fam.items():
        if f[1:3] in REJECTED:
            continue
        common = None
        for key in keys:
            sup = {sig(x) for x in hyp[key] if supported(key, x) and fits(x, key[3])}
            if sup:
                common = sup if common is None else common & sup
        if not common:
            continue
        top = min(rank(kl) for _n, _s, kl in common)
        best = [c for c in common if rank(c[2]) == top]
        if len(best) != 1:
            continue
        for key in keys:
            cands = [x for x in hyp[key] if sig(x) == best[0] and fits(x, key[3])]
            if len(cands) == 1:
                found[key] = (cands[0], "seen" if supported(key, cands[0]) else "family")
    # a counted table is regular: same table as its first argument's, the offset linear in the argument, below the count
    areas = collections.defaultdict(dict)
    for key, ((path, size, kind), how) in found.items():
        if key[1:3] in COUNTED:
            areas[(key[0], key[1], key[2], key[3][0] >> 24)][key[3][0] & 0xFFFFFF] = path
    for key, ((path, size, kind), how) in found.items():
        vptr, mod, meth, args = key
        stride = 0
        if (mod, meth) in COUNTED:
            area = areas[(vptr, mod, meth, args[0] >> 24)]
            n = args[0] & 0xFFFFFF
            per_word = 8 * size if klass(kind) in ("bit", "nbit") else 1
            p0 = area.get(0)
            stride = size if per_word > 1 else None
            if p0 is not None and stride is None:
                p1 = area.get(1)
                stride = p1[-1] - p0[-1] if p1 is not None and p1[:-1] == p0[:-1] else None
            c = counts.get((key, path[:-1]))
            if (p0 is None or not stride or stride < 0 or path[:-1] != p0[:-1] or path[-1] != p0[-1] + stride * (n // per_word)
                    or c is None or n // per_word >= c):
                dropped += 1
                continue
        out[key] = (path, size, kind, stride, how)
    per = collections.Counter()
    for (vptr, mod, meth, _a), v in out.items():
        per[(mod, meth, v[4])] += 1
    print(f"{len(hyp)} (class, getter, arguments) probed, {sum(nobs.values())} calls; fields: {sum(1 for v in out.values() if v[4] == 'seen')} seen, "
          f"{sum(1 for v in out.values() if v[4] == 'family')} by family; {dropped} outside their table (past its count, or not in line); "
          f"{len(hyp) - len(out) - dropped} not named")
    for mod, meth in sorted({(k[1], k[2]) for k in hyp}):
        tot = sum(1 for k in hyp if k[1] == mod and k[2] == meth)
        ex = next((v for k, v in out.items() if k[1] == mod and k[2] == meth), None)
        print(f"  {mod}.{meth}: {per[(mod, meth, 'seen')]} seen, {per[(mod, meth, 'family')]} by family, of {tot}"
              + (f"; e.g. {'/'.join('%#x' % o for o in ex[0])} {ex[2]}:{ex[1]}" if ex else ""))
    if write:
        js = collections.defaultdict(list)
        need = {}   # a block's path -> the bytes needed there
        for (vptr, mod, meth, args), (path, size, kind, stride, how) in sorted(out.items()):
            js[hex(vptr)].append([mod, meth, list(args), list(path[1:]), kind, size, stride, how])
            for j in range(1, len(path)):
                blk = path[:j]
                end = path[j] + (8 if j < len(path) - 1 else size)
                need[blk] = max(need.get(blk, 0), end)
        with open(ARG_FIELDS, "w") as f:
            json.dump(js, f)
        with open(STATE_PATHS, "w") as f:
            for blk, n in sorted(need.items()):
                if len(blk) == 1 and n <= 0x900:
                    continue   # (the module itself: the dump's own first bytes are enough)
                f.write(" ".join("%x" % o for o in blk) + " %x\n" % ((n + 15) & ~7))
            # (not a getter's: the object's own BattleObject, for its id and kind: boma -> LuaModule (+0x190) -> +0x220;
            # reader.py, research/map/code_reading/objects/, 2026-11-12)
            f.write("190 220 10\n")
        print(f"written: {ARG_FIELDS} ({sum(len(v) for v in js.values())} fields in {len(js)} classes), {STATE_PATHS}")


def table():
    """{vptr: [(module, name, path, kind, size, stride)]} from research/map/arg_fields.json (empty when not there)."""
    if not os.path.exists(ARG_FIELDS):
        return {}
    return {int(k, 16): [(m, name_of(meth, args), tuple(path), kind, size, stride) for m, meth, args, path, kind, size, stride, _how in v
                         if (m, meth) not in REJECTED]
            for k, v in json.load(open(ARG_FIELDS)).items()}


_EXPORTS = None


def exports_of(dic):
    global _EXPORTS
    if _EXPORTS is None:
        _EXPORTS = {n for n, _v, _sz, _i, _sh in dic.names.m.exports}
    return _EXPORTS


def verify_entries(dic):
    """The getters with arguments to call for the automatic check: [(module, name, boma offset, slot, symbol, vptr, args)]."""
    if not os.path.exists(ARG_FIELDS):
        return []
    syms = symbols(dic)
    out = []
    kinetic = None
    for k, v in sorted(json.load(open(ARG_FIELDS)).items()):
        for mod, meth, args, _path, _kind, _size, _stride, _how in v:
            if ";guard=" in _how:   # (weapons' and items' variables: the safe probe's guard, hle_state_dump.c)
                g = _how.split(";guard=", 1)[1]
                if (mod, meth) in syms:
                    out.append((mod, name_of(meth, args), dic.boma_off[mod], dic.slots[mod].get(meth, 0), syms[(mod, meth)] + " guard=" + g, int(k, 16), args))
                continue
            if _how.startswith("code;recv="):   # (a getter of another receiver, reached from the module: a kinetic energy)
                kv = dict(x.split("=", 1) for x in _how.split(";")[1:])
                if kv["sym"] in exports_of(dic):
                    out.append((mod, name_of(meth, args), dic.boma_off[mod], 0, kv["sym"] + " recv=" + kv["recv"], int(k, 16), args))
                continue
            if (mod, meth) in syms and (mod, meth) not in REJECTED:
                out.append((mod, name_of(meth, args), dic.boma_off[mod], dic.slots[mod].get(meth, 0), syms[(mod, meth)], int(k, 16), args))
            if mod == "KineticModule":
                kinetic = int(k, 16)
    if kinetic is not None:   # the sums the reader computes from the energies (reader.Reader.energies)
        for meth in ("get_sum_speed_x", "get_sum_speed_y"):
            for mask in reader.ENERGY_MASKS:
                out.append(("KineticModule", name_of(meth, (mask,)), dic.boma_off["KineticModule"], dic.slots["KineticModule"].get(meth, 0),
                            syms[("KineticModule", meth)], kinetic, [mask]))
    return out


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "list":
        make_list(a[1])
    elif len(a) >= 2 and a[0] == "show":
        show(a[1], a[2] if len(a) > 2 else None)
    elif len(a) >= 2 and a[0] == "fields":
        find_fields([x for x in a[1:] if not x.startswith("--")], "--write" in a)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
