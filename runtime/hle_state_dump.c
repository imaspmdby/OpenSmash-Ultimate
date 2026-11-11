/* Research (research/RESEARCH.md, the reader): the battle objects' raw state, frame by frame.
 *
 * SSBU_STATE_DUMP=<file>[,<every>[,<first>[,<last>]]]: at the fighters' frame line (FRAME_HOOK_LINE, before the game's
 * function: where the fight hash reads its values), every <every>th fight frame of a fighter (default 30) from <first>
 * to <last>, that fighter's module accessor (boma) is written: its first BOMA_BYTES, then each word of it that points
 * to readable memory with the first MOD_BYTES there (a module), and for the first SUB_WORDS words of each module that
 * point to readable memory, the first SUB_BYTES there (what a module keeps behind a pointer: DamageModule's values).
 * With the first fighter's record of a frame, every other battle object seen through
 * app::sv_battle_object::module_accessor(id) (weapons, items, stage gimmicks: asked for by the scripts) and still
 * alive (its boma + 8 still holds the id) is written the same way.
 *
 * File: "SD1\0", then records: u32 'BOMA', u32 id, u64 boma, u64 frame (the fighter's fight frame; for the others the
 * first fighter's), u32 kind (0 a fighter at its line, 1 another object), u32 parts, BOMA_BYTES, then parts x
 * (u32 level (1 module, 2 behind a module), u32 offset in its parent, u64 parent address, u64 address, u32 length,
 * bytes). research/tools/reader.py reads it. Unset: nothing is registered and the wrap only calls the game. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "frame_hooks.h"
#include "host.h"

#define BOMA_BYTES 0x400
#define MOD_BYTES 0x900
#define SUB_WORDS 16
#define SUB_BYTES 0x100

static int on = -1;
static FILE *out;
static long long every = 30, first = 1, last = 1ll << 60;
static struct { u64 boma; long long frame; } fighters[8];
static int nfighters;
#define OTHERS 4096
static struct { u64 boma; u32 id; } others[OTHERS];
static volatile int nothers;
static long long records, bytes_out;

/* The battle objects' pools: the blocks the battle object manager's set-up allocates (its allocation calls return to
 * 0x71014f3000-0x71014f6000 in 13.0.5: the fighters' pool 1,531,408 bytes from 0x71014f48c0, 24 slots of 63,808 with
 * the boma at + 0x400; the weapons' 6,163,216 bytes from 0x71014f4dc4; smaller ones for the other categories).
 * hle_alloc_trace.c's wraps report them here. Each dump scans them for bomas by their shape. */
#define POOL_SITE_LO 0x71014f3000ull
#define POOL_SITE_HI 0x71014f6000ull
static struct { u64 addr, size, lr; } pools[64];
static volatile int npools;
int state_dump_wants(u64 lr) { return on == 1 && lr >= POOL_SITE_LO && lr < POOL_SITE_HI; }
void state_dump_pool(u64 lr, u64 addr, u64 size) {
    if (!addr || size < 0x1000) return;
    int n = npools;
    for (int i = 0; i < n; i++) if (pools[i].lr == lr) { pools[i].addr = addr; pools[i].size = size; return; }   /* (a new match) */
    if (n < 64) { pools[n].addr = addr; pools[n].size = size; pools[n].lr = lr; npools = n + 1; }
}
static int enabled(void) {
    if (on >= 0) return on;
    const char *e = getenv("SSBU_STATE_DUMP");
    on = 0;
    if (e && *e) {
        char path[1024];
        const char *comma = strchr(e, ',');
        size_t n = comma ? (size_t)(comma - e) : strlen(e);
        if (n >= sizeof path) n = sizeof path - 1;
        memcpy(path, e, n); path[n] = 0;
        if (comma) sscanf(comma + 1, "%lld,%lld,%lld", &every, &first, &last);
        if (every < 1) every = 1;
        out = fopen(path, "wb");
        if (out) { fwrite("SD1", 1, 4, out); on = 1; fprintf(stderr, "[state] SSBU_STATE_DUMP: every %lld frames from %lld into %s\n", every, first, path); }
    }
    return on;
}

/* n bytes of guest memory at a, through the kernel's read (memory that may be gone): 0 when its first word is not there */
static int copy(u64 a, u8 *to, u32 n) {
    u64 w;
    if (!kernel_read64(a, &w)) return 0;
    for (u32 k = 0; k < n; k += 8) {
        if (k && !((a + k) & 0xFFF) && !kernel_read64(a + k, &w)) { memset(to + k, 0, n - k); break; }   /* (a new page) */
        if (k) { if (!kernel_read64(a + k, &w)) w = 0; }
        memcpy(to + k, &w, 8);
    }
    return 1;
}
static int heap_pointer(u64 w) { return w >= 0x6000000000ull && w < 0x7800000000ull && !(w & 7); }

/* a record is put together in memory and written once (no seek: the file may pass 2 GB) */
#define REC_MAX (8u << 20)
static u8 *rec; static u32 rec_n;
static void put(const void *p, u32 n) { if (rec_n + n <= REC_MAX) { memcpy(rec + rec_n, p, n); rec_n += n; } }
static int part(u32 level, u32 off, u64 parent, u64 addr, const u8 *b, u32 len) {
    if (rec_n + 28 + len > REC_MAX) return 0;
    put(&level, 4); put(&off, 4); put(&parent, 8); put(&addr, 8); put(&len, 4); put(b, len);
    return 1;
}

static void dump(u64 boma, u32 id, long long frame, u32 kind) {
    static u8 bb[BOMA_BYTES], mb[MOD_BYTES], sb[SUB_BYTES];
    if (!rec && !(rec = malloc(REC_MAX))) return;
    if (!copy(boma, bb, BOMA_BYTES)) return;
    u32 tag = 0x414d4f42, parts = 0;
    rec_n = 0;
    put(&tag, 4); put(&id, 4); put(&boma, 8); put(&frame, 8); put(&kind, 4); put(&parts, 4); put(bb, BOMA_BYTES);
    for (u32 o = 0x10; o < BOMA_BYTES; o += 8) {
        u64 m;
        memcpy(&m, bb + o, 8);
        if (!heap_pointer(m) || m == boma || !copy(m, mb, MOD_BYTES)) continue;
        parts += part(1, o, boma, m, mb, MOD_BYTES);
        for (u32 s = 8; s < SUB_WORDS * 8; s += 8) {
            u64 p;
            memcpy(&p, mb + s, 8);
            if (!heap_pointer(p) || p == boma || p == m || !copy(p, sb, SUB_BYTES)) continue;
            parts += part(2, s, m, p, sb, SUB_BYTES);
        }
    }
    memcpy(rec + 28, &parts, 4);
    fwrite(rec, 1, rec_n, out);
    records++; bytes_out += rec_n;
}

/* the fighters' frame line: x0 the agent, agent + 0x40 its boma, boma + 8 the object's id (category in its top 4 bits) */
static void line(Cpu *c, const u64 args[8], void *ctx) {
    (void)args; (void)ctx;
    u64 agent = c->x[0], boma = agent ? ld64(agent + 0x40) : 0;
    if (!boma || ld32(boma + 8) >> 28 != 0) return;
    int k = 0;
    while (k < nfighters && fighters[k].boma != boma) k++;
    if (k == nfighters) { if (k == 8) return; fighters[k].boma = boma; fighters[k].frame = 0; nfighters++; }
    long long f = ++fighters[k].frame;
    if (f < first || f > last || f % every) return;
    dump(boma, ld32(boma + 8), f, 0);
    static int roots_done;   /* (once: the BattleObjectManager object, kind 2, for finding the objects' pools) */
    if (!roots_done++) {
        u64 sym = rt_symbol("_ZN3lib9SingletonIN3app19BattleObjectManagerEE9instance_E"), obj = 0;
        if (sym && kernel_read64(sym, &obj) && obj) dump(obj, 0xFFFFFFFFu, f, 2);
    }
    if (k == 0) {
        /* every other battle object: a boma is a vptr in main's data, an id (category 0-5 in its top 4 bits) and module
         * pointers at + 0x38 (posture), + 0x40 (status) and + 0x50 (work) */
        int n = npools;
        for (int i = 0; i < n; i++) {
            u64 w;
            for (u64 a = pools[i].addr & ~15ull; a + 0x200 <= pools[i].addr + pools[i].size; a += 16) {
                if (!(a & 0xFFF) || a == (pools[i].addr & ~15ull)) { if (!kernel_read64(a, &w)) { a = (a | 0xFFF) - 15; continue; } }
                u64 v = ld64(a);
                if (v < 0x7104f17000ull || v >= 0x71052aa000ull || (v & 7)) continue;
                if (((a + 0x58) ^ a) >> 12 && !kernel_read64(a + 0x58, &w)) continue;
                u64 idw = ld64(a + 8);
                u32 id = (u32)idw;
                /* a live object: a category 0-4 (5, id 0x50000000, is a free slot), nothing above the id, and its
                 * posture, status and work modules are objects (a vptr in main's data each) */
                if (idw >> 32 || id >> 28 > 4) continue;
                int mods_ok = 1;
                for (u32 q = 0; q < 3 && mods_ok; q++) {
                    static const u32 mo[3] = {0x38, 0x40, 0x50};
                    u64 mp = ld64(a + mo[q]), mv = 0;
                    mods_ok = heap_pointer(mp) && kernel_read64(mp, &mv) && mv >= 0x7104f17000ull && mv < 0x71052aa000ull && !(mv & 7);
                }
                if (!mods_ok) continue;
                int fighter = 0;
                for (int q = 0; q < nfighters; q++) fighter |= fighters[q].boma == a;
                if (!fighter) dump(a, id, f, 1);
            }
        }
    }
    if ((f / every) % 20 == 0) fflush(out);
}

__attribute__((constructor)) static void state_dump_init(void) {
    if (enabled()) frame_hook_add(FRAME_HOOK_LINE, FRAME_ORDER_FIGHT_TEST + 30, line, NULL, NULL);
}

/* app::sv_battle_object::module_accessor(u32 id): the scripts' way to another object's boma. Every object asked for
 * that is not a fighter (category != 0) is remembered, for the dump. */
HLE_WRAP_EXPORT(_ZN3app16sv_battle_object15module_accessorEj) {
    u32 id = (u32)c->x[0];
    orig(c);
    if (on != 1 || !c->x[0] || id >> 28 == 0) return;
    u64 boma = c->x[0];
    int n = nothers;
    for (int i = 0; i < n; i++) if (others[i].boma == boma && others[i].id == id) return;
    if (n < OTHERS) { others[n].boma = boma; others[n].id = id; nothers = n + 1; }   /* (a race may lose one: asked again later) */
}

#ifdef _WIN32
#include <windows.h>
/* (once, at the report) Every live battle object anywhere in the alias area, by the boma's shape: where the objects
 * outside the known pools are (items, stage gimmicks). One line a category and 1 MB region, and the first of each. */
static void scan_all(void) {
    u64 found[6] = {0}, in_pool[6] = {0};
    int shown[6] = {0};
    for (u64 a = ALIAS_BASE; a < ALIAS_BASE + ALIAS_SIZE;) {
        MEMORY_BASIC_INFORMATION mi;
        if (!VirtualQuery((void *)(uintptr_t)a, &mi, sizeof mi)) break;
        u64 end = (u64)(uintptr_t)mi.BaseAddress + mi.RegionSize;
        if (mi.State == MEM_COMMIT && !(mi.Protect & (PAGE_NOACCESS | PAGE_GUARD))) {
            for (u64 p = (a + 15) & ~15ull; p + 0x60 <= end; p += 16) {
                u64 v = *(const u64 *)(uintptr_t)p;
                if (v < 0x7104f17000ull || v >= 0x71052aa000ull || (v & 7)) continue;
                u64 idw = *(const u64 *)(uintptr_t)(p + 8);
                u32 id = (u32)idw;
                if (idw >> 32 || id >> 28 > 4) continue;
                int ok = 1;
                static const u32 mo[3] = {0x38, 0x40, 0x50};
                for (u32 q = 0; q < 3 && ok; q++) {
                    u64 mp = *(const u64 *)(uintptr_t)(p + mo[q]), mv = 0;
                    ok = heap_pointer(mp) && kernel_read64(mp, &mv) && mv >= 0x7104f17000ull && mv < 0x71052aa000ull && !(mv & 7);
                }
                if (!ok) continue;
                int pool = 0;
                for (int i = 0; i < npools; i++) pool |= p >= pools[i].addr && p < pools[i].addr + pools[i].size;
                found[id >> 28]++; in_pool[id >> 28] += pool;
                if (!pool && shown[id >> 28]++ < 6)
                    fprintf(stderr, "[state]   outside the pools: category %u id %#x boma %#llx vptr %#llx\n", id >> 28, id, (unsigned long long)p, (unsigned long long)v);
            }
        }
        a = end;
    }
    fprintf(stderr, "[state] whole-heap scan: live bomas by category 0-4: %llu %llu %llu %llu %llu; of them in the known pools: %llu %llu %llu %llu %llu\n",
            (unsigned long long)found[0], (unsigned long long)found[1], (unsigned long long)found[2], (unsigned long long)found[3], (unsigned long long)found[4],
            (unsigned long long)in_pool[0], (unsigned long long)in_pool[1], (unsigned long long)in_pool[2], (unsigned long long)in_pool[3], (unsigned long long)in_pool[4]);
}
#else
static void scan_all(void) {}
#endif

void state_dump_report(void) {
    if (on != 1) return;
    fflush(out);
    scan_all();
    fprintf(stderr, "[state] dump: %lld records, %lld MB; %d fighters, %d pools of battle objects\n", records, bytes_out >> 20, nfighters, npools);
    for (int i = 0; i < npools; i++) fprintf(stderr, "[state]   pool %#llx, %llu bytes, allocated from %#llx\n", (unsigned long long)pools[i].addr, (unsigned long long)pools[i].size, (unsigned long long)pools[i].lr);
}
