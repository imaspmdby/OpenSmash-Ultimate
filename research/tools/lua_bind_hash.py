"""lua_bind_hash: the hash the game's lib::lua_bind_get_value<int>(hash, &value) takes for a constant's name.

A port of the crate lua_bind_hash 1.0.1 (MIT, jam1garner; https://crates.io/crates/lua_bind_hash), checked against
the crate's own test vectors (run this file). Used by research/tools/community.py to have the game confirm the
community's constant values (research/map/community/).
"""
import struct

M = (1 << 64) - 1
MULT1, MULT2, MULT3 = 0x87bcb65480000000, 0xdef35b010f796ca9, 0x9e3779b185ebca87
MULT4, MULT5, MULT6 = 0xc2b2ae3d27d4eb4f, 0x93ea75a780000000, 0x27d4eb2f165667c5
ADD1, ADD2 = 0x85ebca77c2b2ae63, 0x165667b19e3779f9


def lua_bind_hash(data: bytes) -> int:
    n = len(data)
    length = n & M
    vals = [0x60ea27eeadc0b5d5, 0xc2b2ae3d27d4eb4e, 0xffffffffffffffff, 0x61c8864e7a143578]
    mid = [0, 0, 0, 0]
    end = [0x3c6ef3630bd7950e, 0x1bbcd8c2f5e54380, 0x779b185ebca87000, 0xe6c617af2a1c0000]
    end_shift = [0x3f, 0x39, 0x34, 0x2e]
    lvar5 = 0x27d4eb2f165667c4
    n32 = n // 32 * 32
    if n >= 0x20:
        for o in range(0, n32, 32):
            chunk = struct.unpack_from("<4Q", data, o)
            for i in range(4):
                vals[i] = (vals[i] + chunk[i] * MULT4) & M
                mid[i] = ((vals[i] >> 0x21) | (vals[i] * 0x80000000)) & M
                vals[i] = (mid[i] * MULT3) & M
        val = 0
        for i in range(4):
            val = (val + (((mid[i] * end[i]) & M) | (vals[i] >> end_shift[i]))) & M
        x = ((((mid[0] * MULT1) & M) | (((mid[0] * MULT2) & M) >> 0x21)) * MULT3) & M
        val = ((val ^ x) * MULT3) & M
        for i in range(1, 4):
            x = ((((mid[i] * MULT1) & M) | (((mid[i] * MULT2) & M) >> 0x21)) * MULT3) & M
            val = ((((val + ADD1) & M) ^ x) * MULT3) & M
        val = (val + ADD1) & M
        lvar5 = val
    length = (length + lvar5) & M
    rest = data[n32:]
    n8 = len(rest) // 8 * 8
    for o in range(0, n8, 8):
        w = struct.unpack_from("<Q", rest, o)[0]
        x = ((((w * MULT5) & M) | (((w * MULT4) & M) >> 0x21)) * MULT3) & M
        length = x ^ length
        length = ((((length >> 0x25) | (length << 0x1b)) & M) * MULT3 + ADD1) & M
    rest = rest[n8:]
    if len(rest) >= 4:
        w = struct.unpack_from("<I", rest, 0)[0]
        length = ((w * MULT3) & M) ^ length
        length = ((((length >> 0x29) | (length << 0x17)) & M) * MULT4 + ADD2) & M
        rest = rest[4:]
    for b in rest:
        length = ((b * MULT6) & M) ^ length
        length = ((((length >> 0x35) | (length << 0xb)) & M) * MULT3) & M
    u = ((length ^ (length >> 0x21)) * MULT4) & M
    u = ((u ^ (u >> 0x1d)) * ADD2) & M
    return u ^ (u >> 0x20)


if __name__ == "__main__":
    for s, h in (("password", 0xe58325ff3537c13a), ("password1234", 0xa26a67b576fe1e83),
                 ("FIGHTER_STATUS_DAMAGE_WORK_FLOAT_VECOR_CORRECT_STICK_X", 0xa4d50a730e36970e)):
        got = lua_bind_hash(s.encode())
        print(s, hex(got), "ok" if got == h else "DIFFERENT, want %#x" % h)
