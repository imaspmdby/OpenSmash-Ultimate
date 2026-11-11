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
/* SSBU_VERIFY_FIELDS=<file> (research/tools/fields.py --verify-list): lines "<index> <offset of the module in the boma>
 * <vtable slot> <exported getter>", the getters of the named fields that take the boma alone. A getter is called
 * only when its slot's function in the object's own class is a plain load and a return (two instructions: `ldr*
 * ..., [x0, #off]; ret`): the same getter is other code in other classes (a weapon's, an item's), not to be run here. After each object's record, each
 * getter whose module the object has is called (on the main thread, at the frame line: they are plain loads) and its
 * answer written: record u32 'VALS', u32 id, u64 boma, u64 frame, u32 count, u32 0, then count x (u32 index, u32 the
 * float result's bits (v0), u64 the integer result (x0)). reader.py --verify compares them with its own reading. */
typedef struct Getter { u32 index, off, slot; char sym[220]; } Getter;
static Getter *getters; static u32 ngetters;
static Cpu *line_cpu;
static void getters_load(void) {
    const char *path = getenv("SSBU_VERIFY_FIELDS");
    FILE *f = path && *path ? fopen(path, "r") : NULL;
    if (!f) return;
    getters = calloc(8192, sizeof *getters);
    while (getters && ngetters < 8192 && fscanf(f, "%u %x %x %219s", &getters[ngetters].index, &getters[ngetters].off, &getters[ngetters].slot, getters[ngetters].sym) == 4) ngetters++;
    fclose(f);
    fprintf(stderr, "[state] SSBU_VERIFY_FIELDS: %u getters\n", ngetters);
}
static void put(const void *p, u32 n);
static u8 *rec; static u32 rec_n;
static void values(u64 boma, u32 id, long long frame) {
    if (!ngetters || !line_cpu) return;
    Cpu *c = line_cpu, keep = *c;
    u32 tag = 0x534c4156, count = 0, zero = 0;
    rec_n = 0;
    put(&tag, 4); put(&id, 4); put(&boma, 8); put(&frame, 8); put(&count, 4); put(&zero, 4);
    for (u32 i = 0; i < ngetters; i++) {
        u64 m = 0, v = 0;
        if (!kernel_read64(boma + getters[i].off, &m) || m < 0x6000000000ull || m >= 0x7800000000ull || (m & 7)) continue;
        if (!kernel_read64(m, &v) || v < 0x7104f17000ull || v >= 0x71052aa000ull) continue;
        u64 fn = 0, ins = 0;
        if (!kernel_read64(v + getters[i].slot, &fn) || fn < 0x7100000000ull || fn >= 0x71039c8440ull || !kernel_read64(fn, &ins)) continue;
        u32 w0 = (u32)ins, w1 = (u32)(ins >> 32), top = w0 & 0xFFC00000u;
        if (w1 != 0xD65F03C0u || (w0 >> 5 & 31) != 0 ||
            !(top == 0xBD400000u || top == 0xB9400000u || top == 0xF9400000u || top == 0x39400000u || top == 0x79400000u ||
              top == 0xB9800000u || top == 0x39C00000u || top == 0x39800000u)) continue;
        memset(&c->v[0], 0, sizeof c->v[0]);
        u64 x0 = rt_callsym(c, getters[i].sym, 1, boma);
        u32 fb = (u32)c->v[0].d[0];
        put(&getters[i].index, 4); put(&fb, 4); put(&x0, 8);
        count++;
    }
    *c = keep;
    memcpy(rec + 24, &count, 4);
    fwrite(rec, 1, rec_n, out);
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
        if (out) { fwrite("SD1", 1, 4, out); on = 1; getters_load(); fprintf(stderr, "[state] SSBU_STATE_DUMP: every %lld frames from %lld into %s\n", every, first, path); }
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
    if (kind != 2) values(boma, id, frame);
}

static void scan_all(void);
/* the fighters' frame line: x0 the agent, agent + 0x40 its boma, boma + 8 the object's id (category in its top 4 bits) */
static void line(Cpu *c, const u64 args[8], void *ctx) {
    (void)args; (void)ctx;
    u64 agent = c->x[0], boma = agent ? ld64(agent + 0x40) : 0;
    if (!boma || ld32(boma + 8) >> 28 != 0) return;
    line_cpu = c;
    int k = 0;
    while (k < nfighters && fighters[k].boma != boma) k++;
    if (k == nfighters) { if (k == 8) return; fighters[k].boma = boma; fighters[k].frame = 0; nfighters++; }
    long long f = ++fighters[k].frame;
    {   /* (research: stage items without the rule's item list) SSBU_GIVE_ITEM=<fight frame>,<item kind>[,<every>]: at that
         * frame (and every <every> after), the first fighter is handed an item of that kind through the game's own
         * app::lua_bind::ItemModule__have_item_impl(boma, kind, 0, 0, false, false). */
        static long long g_at = -2, g_kind, g_every;
        if (g_at == -2) { const char *e = getenv("SSBU_GIVE_ITEM"); g_at = -1; if (e && *e) sscanf(e, "%lld,%lld,%lld", &g_at, &g_kind, &g_every); }
        if (k == 0 && g_at >= 0 && (f == g_at || (g_every > 0 && f > g_at && (f - g_at) % g_every == 0))) {
            Cpu keep = *c;
            rt_callsym(c, "_ZN3app8lua_bind26ItemModule__have_item_implEPNS_26BattleObjectModuleAccessorENS_8ItemKindEiibb", 6, boma, (u64)g_kind, (u64)0, (u64)0, (u64)0, (u64)0);
            u64 kind = rt_callsym(c, "_ZN3app8lua_bind35ItemModule__get_have_item_kind_implEPNS_26BattleObjectModuleAccessorEi", 2, boma, (u64)0);
            u64 id = rt_callsym(c, "_ZN3app8lua_bind33ItemModule__get_have_item_id_implEPNS_26BattleObjectModuleAccessorEi", 2, boma, (u64)0);
            *c = keep;
            fprintf(stderr, "[state] SSBU_GIVE_ITEM: fight frame %lld, kind %lld asked: the fighter now holds kind %d, object id %#x\n", f, g_kind, (int)kind, (u32)id);
        }
    }
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
            for (u64 a = pools[i].addr & ~7ull; a + 0x200 <= pools[i].addr + pools[i].size; a += 8) {   /* (an item's boma is 8-aligned) */
                if (!(a & 0xFFF) || a == (pools[i].addr & ~7ull)) { if (!kernel_read64(a, &w)) { a = (a | 0xFFF) - 7; continue; } }
                u64 v = ld64(a);
                if (v < 0x7104f17000ull || v >= 0x71052aa000ull || (v & 7)) continue;
                if (((a + 0x58) ^ a) >> 12 && !kernel_read64(a + 0x58, &w)) continue;
                u64 idw = ld64(a + 8);
                u32 id = (u32)idw;
                /* a live object: a category 0-4 (5, id 0x50000000, is a free slot), nothing above the id, and its
                 * posture, status and work modules are objects (a vptr in main's data each) */
                if (idw >> 32 || id >> 28 > 3) continue;   /* (4, the items: through the ItemManager, below) */
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
    {   /* (research: a perturbation test) SSBU_POKE_TABLE=<fight frame>: at that frame of the first fighter, the words of
         * the 1,024-entry table's three per-frame lines (+0x80, +0x140, +0x160 of each entry) that are neither 0 nor -1
         * get a bit flipped (0x00400000: a float changes by up to 2x). Does the fight go on the same? */
        static long long poke = -2;
        if (poke == -2) { const char *e = getenv("SSBU_POKE_TABLE"); poke = e && *e ? atoll(e) : -1; }
        u64 t = 0;
        if (k == 0 && f == poke && kernel_read64(0x710532f490ull, &t) && t && kernel_read64(t, &t) && t) {
            static const u32 lo[3] = {0x80, 0x140, 0x160};
            u64 n = 0;
            for (u32 i = 0; i < 1024; i++)
                for (u32 q = 0; q < 3; q++)
                    for (u32 o = 0; o < 0x40 && lo[q] + o < 0x1a0; o += 4) {
                        u64 a = t + (u64)i * 0x1a0 + lo[q] + o;
                        u32 w = ld32(a);
                        if (w && w != 0xFFFFFFFFu) { st32(a, w ^ 0x00400000u); n++; }
                    }
            fprintf(stderr, "[state] SSBU_POKE_TABLE: %llu words of the table changed at fight frame %lld\n", (unsigned long long)n, f);
        }
    }
    if (k == 0) {   /* the items, asked of the game's ItemManager: how many are active, and each one's object */
        static int said;
        u64 sym = rt_symbol("_ZN3lib9SingletonIN3app11ItemManagerEE9instance_E"), mgr = 0;
        if (sym && kernel_read64(sym, &mgr) && mgr) {
            Cpu keep = *c;
            u64 n = rt_callsym(c, "_ZN3app8lua_bind44ItemManager__get_num_of_active_item_all_implEPNS_11ItemManagerE", 1, mgr) & 0xFFFFFFFF;
            for (u64 i = 0; i < n && i < 16; i++) {
                u64 item = rt_callsym(c, "_ZN3app8lua_bind33ItemManager__get_active_item_implEPNS_11ItemManagerEm", 2, mgr, i);
                if (!item) continue;
                if (said < 12) {
                    said++;
                    fprintf(stderr, "[state] frame %lld: item %llu of %llu at %#llx:", f, (unsigned long long)i, (unsigned long long)n, (unsigned long long)item);
                    for (u32 o = 0; o < 0x60; o += 8) { u64 w = 0; kernel_read64(item + o, &w); fprintf(stderr, " %llx", (unsigned long long)w); }
                    fprintf(stderr, "\n");
                }
                /* an item is a battle object: its word at + 0x20 points to its boma (inside the Item, at + 0x98); the
                 * ItemManager's list is the authority, so only the boma's vptr is asked for (an item may lack modules
                 * a fighter has) */
                u64 b = 0, v = 0, idw = 0;
                if (kernel_read64(item + 0x20, &b) && heap_pointer(b) && kernel_read64(b, &v) && kernel_read64(b + 8, &idw) &&
                    v >= 0x7104f17000ull && v < 0x71052aa000ull)
                    dump(b, (u32)idw, f, 1);
            }
            *c = keep;
        }
    }
    {   /* (research: where the live objects are; SSBU_STATE_SCAN=1: at every dump, else every 5 s of fight) */
        static int scan_each = -1;
        if (scan_each < 0) { const char *e = getenv("SSBU_STATE_SCAN"); scan_each = e && *e == '1'; }
        if (k == 0 && (scan_each || f % 300 == 0)) { fprintf(stderr, "[state] frame %lld: ", f); scan_all(); }
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
            for (u64 p = (a + 7) & ~7ull; p + 0x60 <= end; p += 8) {
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
                if (!pool && id >> 28 >= 2 && shown[id >> 28]++ < 6)
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

/* (research) The 1,024-entry table at [[0x710532f490]] (0x1a0 bytes an entry, then a tail): written whole to
 * <dump>.table at the report, for reading what it holds. */
static void table_dump(void) {
    u64 t = 0;
    const char *e = getenv("SSBU_STATE_DUMP");
    if (!kernel_read64(0x710532f490ull, &t) || !t || !kernel_read64(t, &t) || !t || !e) return;   /* ([[global]]: the game's two loads) */
    char path[1100];
    const char *comma = strchr(e, ',');
    snprintf(path, sizeof path, "%.*s.table", comma ? (int)(comma - e) : (int)strlen(e), e);
    FILE *f = fopen(path, "wb");
    if (!f) return;
    fwrite(&t, 8, 1, f);
    for (u64 a = t; a < t + 0x682d0; a += 8) { u64 w = 0; kernel_read64(a, &w); fwrite(&w, 8, 1, f); }
    fclose(f);
    fprintf(stderr, "[state] the table at %#llx written to %s\n", (unsigned long long)t, path);
}

void state_dump_report(void) {
    if (on != 1) return;
    fflush(out);
    table_dump();
    scan_all();
    fprintf(stderr, "[state] dump: %lld records, %lld MB; %d fighters, %d pools of battle objects\n", records, bytes_out >> 20, nfighters, npools);
    for (int i = 0; i < npools; i++) fprintf(stderr, "[state]   pool %#llx, %llu bytes, allocated from %#llx\n", (unsigned long long)pools[i].addr, (unsigned long long)pools[i].size, (unsigned long long)pools[i].lr);
}
