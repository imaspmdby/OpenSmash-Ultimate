/* The C library's memory and string functions, natively.
 *
 * The game imports them from the SDK, whose ARM versions otherwise run recompiled - memcpy
 * alone was about 1.5% of the main thread in an 8-player match. Guest pointers are host
 * pointers (on macOS, RT_MEMBASE above: P() and H2G()), so the host's own (vectorised) functions
 * do the same work. memcpy is memmove: the same result wherever the guest's would be defined,
 * and no surprise where it isn't. */
#include "host.h"

/* (research, SSBU_RF, hle_memtrace.c: these accesses are the game's, and the access trace does not see them) */
void rt_rf_native(u64 a, u64 n, int write);
#define RF_R(a, n) rt_rf_native((a), (n), 0)
#define RF_W(a, n) rt_rf_native((a), (n), 1)

HLE(memcpy) { RF_R(c->x[1], c->x[2]); RF_W(c->x[0], c->x[2]); memmove(P(void, c->x[0]), P(const void, c->x[1]), (size_t)c->x[2]); }
HLE(memmove) { RF_R(c->x[1], c->x[2]); RF_W(c->x[0], c->x[2]); memmove(P(void, c->x[0]), P(const void, c->x[1]), (size_t)c->x[2]); }
HLE(memset) { RF_W(c->x[0], c->x[2]); memset(P(void, c->x[0]), (int)(u8)c->x[1], (size_t)c->x[2]); }
HLE(memcmp) { RF_R(c->x[0], c->x[2]); RF_R(c->x[1], c->x[2]); c->x[0] = (u64)(i64)memcmp(P(const void, c->x[0]), P(const void, c->x[1]), (size_t)c->x[2]); }
HLE(memchr) {
    u64 s = c->x[0];
    const void *p = memchr(P(const void, c->x[0]), (int)(u8)c->x[1], (size_t)c->x[2]);
    RF_R(s, p ? H2G(p) - s + 1 : c->x[2]);   /* (what it read: up to the byte found; the length given can be "no limit") */
    c->x[0] = p ? H2G(p) : 0;
}
HLE(strlen) { u64 a = c->x[0]; c->x[0] = strlen(P(const char, c->x[0])); RF_R(a, c->x[0] + 1); }
HLE(strcmp) {
    RF_R(c->x[0], strlen(P(const char, c->x[0])) + 1); RF_R(c->x[1], strlen(P(const char, c->x[1])) + 1);
    c->x[0] = (u64)(i64)strcmp(P(const char, c->x[0]), P(const char, c->x[1]));
}
HLE(strncmp) {
    RF_R(c->x[0], strnlen(P(const char, c->x[0]), (size_t)c->x[2])); RF_R(c->x[1], strnlen(P(const char, c->x[1]), (size_t)c->x[2]));
    c->x[0] = (u64)(i64)strncmp(P(const char, c->x[0]), P(const char, c->x[1]), (size_t)c->x[2]);
}
HLE(strchr) {
    RF_R(c->x[0], strlen(P(const char, c->x[0])) + 1);
    const char *p = strchr(P(const char, c->x[0]), (int)(u8)c->x[1]);
    c->x[0] = p ? H2G(p) : 0;
}
HLE(strcpy) { u64 n = strlen(P(const char, c->x[1])) + 1; RF_R(c->x[1], n); RF_W(c->x[0], n); strcpy(P(char, c->x[0]), P(const char, c->x[1])); }
