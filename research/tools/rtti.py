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
