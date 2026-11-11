"""Names of C++ types from main's RTTI: vtable address -> class name.

    deps/python/python.exe research/tools/rtti.py [<vtable address> ...]      (no address: a census of main's vtables)

Itanium C++ ABI: an object's first word points 16 bytes into its vtable; the word before that point (vtable + 8) is
the type_info's address, and the type_info's second word the mangled name ("N3app8FighterE"...). main's data is
relocated by RELATIVE relocations (RELA: the value is the addend), applied here. Import: rtti.Names().name(vptr).
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import nso  # noqa: E402

BASE = 0x7100000000


class Names:
    def __init__(self, path=os.path.join(ROOT, "dump", "exefs", "main")):
        self.m = nso.Module(path)
        self.rel = {off: add for off, typ, sym, add in self.m.relocs if typ == 1027}   # R_AARCH64_RELATIVE

    def word(self, off):
        if off in self.rel:
            return self.rel[off]
        if 0 <= off <= len(self.m.image) - 8:
            return struct.unpack_from("<Q", self.m.image, off)[0]
        return None

    def cstr(self, off):
        if not 0 <= off < len(self.m.image):
            return None
        end = self.m.image.find(b"\0", off, off + 512)
        if end < 0:
            return None
        try:
            s = self.m.image[off:end].decode("ascii")
        except UnicodeDecodeError:
            return None
        return s if s and s.isprintable() else None

    def name(self, vptr):
        """The mangled type name of an object whose first word is vptr (a guest address), or None."""
        off = vptr - BASE
        if not 16 <= off < len(self.m.image):
            return None
        ti = self.word(off - 8)
        if ti is None or not 0 < ti < len(self.m.image):
            return None
        nm = self.word(ti + 8)
        if nm is None:
            return None
        s = self.cstr(nm)
        if s and (s[0] == "N" or s[0].isdigit()) and len(s) > 2:
            return s
        return None


def demangle_simple(s):
    """N3app8FighterE -> app::Fighter (nested names only; templates left as they are)."""
    if not s:
        return s
    t = s[1:-1] if s[0] == "N" and s.endswith("E") else s
    out, i = [], 0
    while i < len(t) and t[i].isdigit():
        j = i
        while j < len(t) and t[j].isdigit():
            j += 1
        n = int(t[i:j])
        out.append(t[j:j + n])
        i = j + n
    return "::".join(out) + (t[i:] and " " + t[i:]) if out else s


if __name__ == "__main__":
    n = Names()
    if len(sys.argv) > 1:
        for a in sys.argv[1:]:
            v = int(a, 16)
            print(hex(v), demangle_simple(n.name(v)))
    else:
        # every type_info name string reachable: a census of the classes with RTTI
        names = set()
        for off, add in n.rel.items():
            if 0x4f17000 <= off < 0x52aa000:
                s = n.name(add + BASE + 16) if False else None
        print(len(n.rel), "relative relocations")


def vtable_functions(names, extra_vptrs=None):
    """{function address: class name}: every virtual function of every vtable of main whose class is named (RTTI, or
    extra_vptrs {vptr: name}, e.g. the boma modules). A vtable is found at each data word that follows a type_info
    pointer; its functions are the words after it that point into main's code."""
    data_lo, data_hi, text_end = 0x4f17000, 0x52aa000, 0x39c8440
    out = {}
    starts = {}
    for off in range(data_lo + 8, data_hi, 8):
        nm = names.name(BASE + off)
        if nm:
            starts[BASE + off] = demangle_simple(nm)
    for v, n in (extra_vptrs or {}).items():
        starts.setdefault(v, n)
    for v, cls in starts.items():
        off = v - BASE
        for k in range(512):
            w = names.word(off + 8 * k)
            if w is None or not (0 < w < text_end):
                break
            out.setdefault(BASE + w, cls)
    return out


class CodeMap:
    """Guess the library or namespace of a function of main by its neighbours: the nearest virtual functions of named
    classes below and above (code is laid out by source file and library). name(address) -> (label, how) with how
    'virtual of <class>', '~ns (both neighbours)', '~ns (nearest, d KB)' or 'unknown'."""

    def __init__(self, names, extra_vptrs=None):
        import bisect as _b
        self._b = _b
        fns = vtable_functions(names, extra_vptrs)
        # the exported functions of main's code too (app::ai, app::lua_bind, lib::, nn::...), by their outer namespaces
        for n, v, _sz, _i, _sh in names.m.exports:
            if 0 < v < 0x39c8440 and n.startswith("_ZN"):
                parts = demangle_simple(n[2:]).split(" ")[0].split("::")   # (_ZN3app2ai9target_idE... -> app, ai, ...)
                fns.setdefault(BASE + v, "::".join(parts[:2]) if len(parts) > 2 else parts[0])
        self.exact = fns
        self.addrs = sorted(fns)
        self.ns = [fns[a].split("::")[0] if "::" in fns[a] else fns[a] for a in self.addrs]

    def name(self, a):
        if a in self.exact:
            return self.exact[a], "virtual"
        i = self._b.bisect_right(self.addrs, a) - 1
        lo = (self.ns[i], a - self.addrs[i]) if i >= 0 else None
        hi = (self.ns[i + 1], self.addrs[i + 1] - a) if i + 1 < len(self.addrs) else None
        if lo and hi and lo[0] == hi[0]:
            return "~" + lo[0], "between"
        best = min((x for x in (lo, hi) if x), key=lambda x: x[1], default=None)
        if best and best[1] < 0x4000:
            return "~" + best[0], "near"
        return "unknown", "far"
