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
#ifdef _WIN32
#include <windows.h>   /* (SRWLOCK: SSBU_POKE_SITES) */
#endif

#include "frame_hooks.h"
#include "host.h"
#include "fight_test.h"   /* (fight_xxh64: SSBU_CONST_CHECK) */

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
typedef struct Getter { u32 index, off, slot, nargs, nrecv, nguard, gcount, gindex; u64 vptr, a[3]; u32 recv[4], guard[4]; char sym[220]; } Getter;
/* a list's line: "<index> <module's offset in the boma> <vtable slot> <exported getter> [<vptr> <argument> ...]" (hex
 * but the index): a getter with arguments (WorkModule::get_int(id)) is called with up to three integers after the
 * boma, on the objects whose module is of that class only (vptr 0: any). " recv=<o1>[/<o2>...]" anywhere after the
 * symbol: the getter's receiver is not the boma but the object reached from the module by loads at + o1, then + o2...
 * (hex; e.g. a kinetic energy: recv=30 for the pointer at module + 0x30), the arguments after it */
static u32 getters_read(FILE *f, Getter *g, u32 max) {
    char line[512];
    u32 n = 0;
    while (n < max && fgets(line, sizeof line, f)) {
        unsigned long long vp = 0, a0 = 0, a1 = 0, a2 = 0;
        g[n].nrecv = 0; g[n].nguard = 0;
        {   /* " guard=<o1>[/<o2>...]:<count offset>:<index>" (hex): the safe probe of weapons and items (2026-11-12): the
             * getter is called on an object that is not a fighter only if every load from the module along o1, o2... gives
             * a heap pointer and the u32 at <count offset> of the last block is above <index> */
            char *gv = strstr(line, " guard=");
            if (gv) {
                char *q = gv + 7, *end;
                while (g[n].nguard < 4) {
                    unsigned long o = strtoul(q, &end, 16);
                    if (end == q) break;
                    g[n].guard[g[n].nguard++] = (u32)o;
                    q = end;
                    if (*q == '/') q++; else break;
                }
                unsigned long co = 0, ix = 0;
                if (*q == ':') { co = strtoul(q + 1, &end, 16); q = end; if (*q == ':') { ix = strtoul(q + 1, &end, 16); q = end; } }
                g[n].gcount = (u32)co; g[n].gindex = (u32)ix;
                memmove(gv, q, strlen(q) + 1);
            }
        }
        char *rv = strstr(line, " recv=");
        if (rv) {
            char *q = rv + 6;
            while (g[n].nrecv < 4) {
                char *end;
                unsigned long o = strtoul(q, &end, 16);
                if (end == q) break;
                g[n].recv[g[n].nrecv++] = (u32)o;
                q = end;
                if (*q == '/') q++; else break;
            }
            memmove(rv, q, strlen(q) + 1);   /* (the rest of the line, without the token) */
        }
        int k = sscanf(line, "%u %x %x %219s %llx %llx %llx %llx", &g[n].index, &g[n].off, &g[n].slot, g[n].sym, &vp, &a0, &a1, &a2);
        if (k < 4) continue;
        g[n].nargs = k > 5 ? (u32)(k - 5) : 0; g[n].vptr = vp; g[n].a[0] = a0; g[n].a[1] = a1; g[n].a[2] = a2;
        n++;
    }
    return n;
}
#define GETTERS_MAX 32768
static Getter *getters; static u32 ngetters;
static Cpu *line_cpu;
static void getters_load(void) {
    const char *path = getenv("SSBU_VERIFY_FIELDS");
    FILE *f = path && *path ? fopen(path, "r") : NULL;
    if (!f) return;
    getters = calloc(GETTERS_MAX, sizeof *getters);
    if (getters) ngetters = getters_read(f, getters, GETTERS_MAX);
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
        if (getters[i].nargs || getters[i].nrecv || getters[i].vptr) {   /* (with arguments, another receiver, or a class named: called as it is) */
            if (id >> 28) {   /* (not a fighter: only with a guard that holds: the probe saw blind calls stop the game) */
                if (!getters[i].nguard) continue;
                u64 r = m;
                int ok = 1;
                for (u32 q = 0; q < getters[i].nguard && ok; q++)
                    ok = kernel_read64(r + getters[i].guard[q], &r) && r >= 0x6000000000ull && r < 0x7800000000ull && !(r & 7);
                u64 cnt = 0;
                if (!ok || !kernel_read64(r + getters[i].gcount, &cnt) || (u32)cnt <= getters[i].gindex) continue;
            }
            if (getters[i].vptr && getters[i].vptr != v) continue;
            u64 self = boma;
            if (getters[i].nrecv) {   /* (the receiver reached from the module: it must be an object, a vptr in main's data) */
                u64 r = m, rv = 0;
                int ok = 1;
                for (u32 q = 0; q < getters[i].nrecv && ok; q++)
                    ok = kernel_read64(r + getters[i].recv[q], &r) && r >= 0x6000000000ull && r < 0x7800000000ull && !(r & 7);
                if (!ok || !kernel_read64(r, &rv) || rv < 0x7104f17000ull || rv >= 0x71052aa000ull) continue;
                self = r;
            }
            memset(&c->v[0], 0, sizeof c->v[0]);
            u64 x0a = rt_callsym(c, getters[i].sym, 1 + (int)getters[i].nargs, self, getters[i].a[0], getters[i].a[1], getters[i].a[2]);
            u32 fba = (u32)c->v[0].d[0];
            put(&getters[i].index, 4); put(&fba, 4); put(&x0a, 8);
            count++;
            *c = keep;
            continue;
        }
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
/* SSBU_PROBE_FIELDS=<file>,<fight frame> (the file as SSBU_VERIFY_FIELDS's; research/tools/fields.py --probe-list):
 * at that frame of each fighter, each listed getter is called once inside a probe (hle_memtrace.c: a build with
 * SSBU_MEMTRACE) and what it read is written: record u32 'PROB', u32 id, u64 boma, u64 frame, u32 count, u32 0, then
 * count x (u32 index, u32 reads, u64 x0, u32 v0's bits, u32 0, reads x (u64 address, u32 size, u32 write, u64 the
 * word now at the address: the header's last u32 is 1 for this form)). The
 * (SSBU_PROBE_FIELDS=<file>,<frame>:<every> probes again every <every> frames after; SSBU_PROBE_OTHERS=1 also
 * probes the other objects of the pools, weapons, at those frames.) The
 * getter about to be called is logged first when SSBU_PROBE_LOG is set: a getter that stops the game is the last one
 * named, and goes into SSBU_PROBE_SKIP=<index>,<index>... */
void rt_mt_probe_begin(void);
u32 rt_mt_probe_end(const void **recs);
static Getter *pgetters; static u32 npgetters; static long long probe_frame = -1, probe_every = 0;
static int probe_now(long long f) { return npgetters && probe_frame >= 0 && (f == probe_frame || (probe_every > 0 && f > probe_frame && (f - probe_frame) % probe_every == 0)); }
static void probes_load(void) {
    const char *e = getenv("SSBU_PROBE_FIELDS");
    if (!e || !*e) return;
    char path[1024];
    const char *comma = strrchr(e, ',');
    if (!comma) return;
    snprintf(path, sizeof path, "%.*s", (int)(comma - e), e);
    sscanf(comma + 1, "%lld:%lld", &probe_frame, &probe_every);   /* (<frame>[:<every>]) */
    FILE *f = fopen(path, "r");
    if (!f) return;
    pgetters = calloc(GETTERS_MAX, sizeof *pgetters);
    if (pgetters) npgetters = getters_read(f, pgetters, GETTERS_MAX);
    fclose(f);
    fprintf(stderr, "[state] SSBU_PROBE_FIELDS: %u getters to probe at fight frame %lld\n", npgetters, probe_frame);
}
static int probe_skipped(u32 index) {
    const char *e = getenv("SSBU_PROBE_SKIP");
    while (e && *e) { if ((u32)strtoul(e, NULL, 10) == index) return 1; e = strchr(e, ','); if (e) e++; }
    return 0;
}
static void probes(Cpu *c, u64 boma, u32 id, long long frame) {
    if (!npgetters || !out) return;
    static u8 *pb;
    if (!pb && !(pb = malloc(16u << 20))) return;
    u32 n = 0, tag = 0x424f5250, count = 0, zero = 0, form = 1;
    int logit = getenv("SSBU_PROBE_LOG") != NULL;
    Cpu keep = *c;
#define PUT(p_, n_) do { if (n + (n_) <= (16u << 20)) { memcpy(pb + n, (p_), (n_)); n += (n_); } } while (0)
    PUT(&tag, 4); PUT(&id, 4); PUT(&boma, 8); PUT(&frame, 8); PUT(&count, 4); PUT(&form, 4);
    for (u32 i = 0; i < npgetters; i++) {
        u64 m = 0, v = 0;
        if (probe_skipped(pgetters[i].index)) continue;
        if (!kernel_read64(boma + pgetters[i].off, &m) || m < 0x6000000000ull || m >= 0x7800000000ull || (m & 7)) continue;
        if (!kernel_read64(m, &v) || v < 0x7104f17000ull || v >= 0x71052aa000ull) continue;
        if (pgetters[i].vptr && pgetters[i].vptr != v) continue;
        if (logit) { fprintf(stderr, "[state] probe %u %s %llx\n", pgetters[i].index, pgetters[i].sym, (unsigned long long)pgetters[i].a[0]); fflush(stderr); }
        *c = keep;
        memset(&c->v[0], 0, sizeof c->v[0]);
        const void *recs = NULL;
        rt_mt_probe_begin();
        u64 x0 = rt_callsym(c, pgetters[i].sym, 1 + (int)pgetters[i].nargs, boma, pgetters[i].a[0], pgetters[i].a[1], pgetters[i].a[2]);
        u32 reads = rt_mt_probe_end(&recs);
        u32 fb = (u32)c->v[0].d[0];
        PUT(&pgetters[i].index, 4); PUT(&reads, 4); PUT(&x0, 8); PUT(&fb, 4); PUT(&zero, 4);
        for (u32 r = 0; r < reads; r++) {
            const u8 *e = (const u8 *)recs + (size_t)r * 16;
            u64 a, w = 0;
            memcpy(&a, e, 8);
            if (!kernel_read64(a & ~7ull, &w)) w = 0;
            if (a & 7) { u64 w2 = 0; if (!kernel_read64((a & ~7ull) + 8, &w2)) w2 = 0; w = w >> (8 * (a & 7)) | w2 << (64 - 8 * (a & 7)); }
            PUT(e, 16); PUT(&w, 8);
        }
        count++;
    }
#undef PUT
    *c = keep;
    memcpy(pb + 24, &count, 4);
    fwrite(pb, 1, n, out);
    fprintf(stderr, "[state] probed %u getters on object %#x at fight frame %lld\n", count, id, frame);
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
        if (out) { fwrite("SD1", 1, 4, out); on = 1; getters_load(); probes_load(); fprintf(stderr, "[state] SSBU_STATE_DUMP: every %lld frames from %lld into %s\n", every, first, path); }
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

/* SSBU_STATE_PATHS=<file>: lines "<offset> [<offset> ...] <length>" (hex): from the boma, each offset is that of a
 * pointer word in the block reached so far (the first one the module's in the boma); <length> bytes at the last
 * pointer's target are written as a part of level <number of offsets> (offset: the last one; parent: the block that
 * holds the pointer). The fields found behind pointers (research/tools/argprobe.py) need them: WorkModule's tables. */
#define PATHS_MAX 512
#define PATH_BYTES 0x4000
static struct { u32 n, off[6], len; } paths[PATHS_MAX];
static int npaths = -1;
static void paths_load(void) {
    npaths = 0;
    const char *e = getenv("SSBU_STATE_PATHS");
    FILE *f = e && *e ? fopen(e, "r") : NULL;
    if (!f) return;
    char line[256];
    while (npaths < PATHS_MAX && fgets(line, sizeof line, f)) {
        u32 v[7], k = 0;
        char *q = line, *end;
        while (k < 7) { unsigned long x = strtoul(q, &end, 16); if (end == q) break; v[k++] = (u32)x; q = end; }
        if (k < 2) continue;
        paths[npaths].n = k - 1;
        for (u32 i = 0; i + 1 < k; i++) paths[npaths].off[i] = v[i];
        paths[npaths].len = v[k - 1] > PATH_BYTES ? PATH_BYTES : (v[k - 1] + 7) & ~7u;
        npaths++;
    }
    fclose(f);
    fprintf(stderr, "[state] SSBU_STATE_PATHS: %d paths\n", npaths);
}
static int part(u32 level, u32 off, u64 parent, u64 addr, const u8 *b, u32 len);
static u32 path_parts(u64 boma) {
    static u8 xb[PATH_BYTES + 16];
    u32 made = 0;
    if (npaths < 0) paths_load();
    for (int i = 0; i < npaths; i++) {
        u64 p = boma, t = 0;
        u32 k = 0;
        for (; k < paths[i].n; k++) {
            if (!kernel_read64(p + paths[i].off[k], &t) || t < 0x6000000000ull || t >= 0x7800000000ull) break;
            if (k + 1 < paths[i].n) p = t;
        }
        if (k < paths[i].n) continue;
        u64 w = 0;
        u32 len = paths[i].len, sh = (u32)(t & 7);
        if (!kernel_read64(t & ~7ull, &w)) continue;
        for (u32 j = 0; j < len + 8; j += 8) { if (!kernel_read64((t & ~7ull) + j, &w)) w = 0; memcpy(xb + j, &w, 8); }
        made += (u32)part(paths[i].n, paths[i].off[paths[i].n - 1], p, t, xb + sh, len);
    }
    return made;
}

void rt_ww_range(u64 start, u32 len, u32 key);   /* (hle_memtrace.c: SSBU_WRITE_WATCH) */
void rt_ww_report(void);
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
        rt_ww_range(m, MOD_BYTES, (id >> 28) << 28 | o << 16);
        for (u32 s = 8; s < SUB_WORDS * 8; s += 8) {
            u64 p;
            memcpy(&p, mb + s, 8);
            if (!heap_pointer(p) || p == boma || p == m || !copy(p, sb, SUB_BYTES)) continue;
            parts += part(2, s, m, p, sb, SUB_BYTES);
            rt_ww_range(p, SUB_BYTES, (id >> 28) << 28 | o << 16 | s);
        }
    }
    if (kind != 2) parts += path_parts(boma);
    memcpy(rec + 28, &parts, 4);
    fwrite(rec, 1, rec_n, out);
    records++; bytes_out += rec_n;
    if (kind != 2) values(boma, id, frame);
}

static void scan_all(void);
/* the fighters' frame line: x0 the agent, agent + 0x40 its boma, boma + 8 the object's id (category in its top 4 bits) */
/* (research: SSBU_POKE_SITES=<allocation site>[,...]: the live blocks allocated by calls returning there, kept for
 * SSBU_POKE_HOLD's target "sites"; hle_alloc_trace.c's wraps report them) */
#define POKE_SITES 8
#define POKE_BLOCKS 4096
static u64 poke_sites[POKE_SITES]; static int npoke_sites = -1;
static struct { u64 addr, size; } poke_blocks[POKE_BLOCKS];
static LONG npoke_blocks;
static SRWLOCK poke_lock = SRWLOCK_INIT;
int poke_site_wants(u64 lr) {
    if (npoke_sites < 0) {
        const char *e = getenv("SSBU_POKE_SITES");
        int n = 0;
        while (e && *e && n < POKE_SITES) { char *end; poke_sites[n++] = strtoull(e, &end, 16); e = *end == ',' ? end + 1 : NULL; }
        npoke_sites = n;
    }
    for (int i = 0; i < npoke_sites; i++) if (poke_sites[i] == lr) return 1;
    return 0;
}
void poke_site_block(u64 addr, u64 size) {
    if (!addr || !size) return;
    AcquireSRWLockExclusive(&poke_lock);
    if (npoke_blocks < POKE_BLOCKS) { poke_blocks[npoke_blocks].addr = addr; poke_blocks[npoke_blocks].size = size; npoke_blocks++; }
    ReleaseSRWLockExclusive(&poke_lock);
}
void poke_site_free(u64 addr) {
    if (npoke_sites <= 0 || !npoke_blocks || !addr) return;
    AcquireSRWLockExclusive(&poke_lock);
    for (LONG i = 0; i < npoke_blocks; i++)
        if (poke_blocks[i].addr == addr) { poke_blocks[i] = poke_blocks[npoke_blocks - 1]; npoke_blocks--; break; }
    ReleaseSRWLockExclusive(&poke_lock);
}
static int looks_pointer(u64 w) { return (w >= 0x6000000000ull && w < 0x7800000000ull) || (w >> 32 && w < 0x100000000000ull); }

/* A perturbation's target (SSBU_POKE_HOLD, SSBU_RB_VERIFY_INJECT): mode 0 sets bit 0x00400000 (OR) in each word that
 * is neither 0 nor -1; mode 1 flips it (XOR) in every word of the target, zeros included. Targets:
 *   table                              the 1,024-entry table's three per-frame lines ([[0x710532f490]]);
 *   sites                              SSBU_POKE_SITES' live blocks (aligned words that look like pointers left alone);
 *   ptr:<global>:<loads>:<off>:<len>   <len> bytes at <off> past the address read <loads> times from <global> (hex);
 *   boma:<o1>[/<o2>...]:<off>:<len>    from the first fighter's boma, a load at + o1, then at + o2..., then <len>
 *                                      bytes at <off> (hex), e.g. boma:a8:18:4 for [[boma + 0xa8] + 0x18].
 * Returns the number of words changed. */
static u64 poke_word(u64 a, u32 mode) {
    if (a < 0x6000000000ull || a + 4 > 0x7800000000ull) return 0;   /* (the game's heap only: a target misread stops nothing) */
    if (looks_pointer(ld64(a & ~7ull))) return 0;   /* (half of a pointer: an error there stops the game, it proves nothing) */
    u32 w = ld32(a);
    if (mode == 0) { if (!w || w == 0xFFFFFFFFu) return 0; st32(a, w | 0x00400000u); return 1; }
    st32(a, w ^ 0x00400000u);
    return 1;
}
static u64 poke_target(const char *what, u32 mode) {
    u64 n = 0, t = 0;
    if (!strcmp(what, "table")) {
        if (kernel_read64(0x710532f490ull, &t) && t && kernel_read64(t, &t) && t) {
            static const u32 lo[3] = {0x80, 0x140, 0x160};
            for (u32 i = 0; i < 1024; i++)
                for (u32 q = 0; q < 3; q++)
                    for (u32 o = 0; o < 0x40 && lo[q] + o < 0x1a0; o += 4) n += poke_word(t + (u64)i * 0x1a0 + lo[q] + o, mode);
        }
    } else if (!strcmp(what, "sites")) {
        AcquireSRWLockShared(&poke_lock);
        for (LONG b = 0; b < npoke_blocks; b++)
            for (u64 o = 0; o + 8 <= poke_blocks[b].size; o += 8) {
                u64 a = poke_blocks[b].addr + o;
                if (looks_pointer(ld64(a))) continue;
                n += poke_word(a, mode) + poke_word(a + 4, mode);
            }
        ReleaseSRWLockShared(&poke_lock);
    } else if (!strcmp(what, "site1")) {   /* the last live block registered by SSBU_POKE_SITES only (one node of a container) */
        AcquireSRWLockShared(&poke_lock);
        if (npoke_blocks > 0)
            for (u64 o = 0; o + 8 <= poke_blocks[npoke_blocks - 1].size; o += 8) {
                u64 a = poke_blocks[npoke_blocks - 1].addr + o;
                if (looks_pointer(ld64(a))) continue;
                n += poke_word(a, mode) + poke_word(a + 4, mode);
            }
        ReleaseSRWLockShared(&poke_lock);
    } else if (!strncmp(what, "mapnode:", 8)) {   /* mapnode:<head>:<off>: in each SSBU_POKE_SITES block, the first node of
                                                  * the list whose head pointer is at + <head>, its word at + <off> (hex) */
        unsigned long long head = 0, off = 0;
        if (sscanf(what + 8, "%llx:%llx", &head, &off) == 2) {
            AcquireSRWLockShared(&poke_lock);
            for (LONG b = 0; b < npoke_blocks; b++) {
                u64 node = 0;
                if (kernel_read64(poke_blocks[b].addr + head, &node) && node >= 0x6000000000ull && node < 0x7800000000ull)
                    n += poke_word(node + off, mode);
            }
            ReleaseSRWLockShared(&poke_lock);
        }
    } else if (!strncmp(what, "ptr:", 4)) {
        unsigned long long g = 0, loads = 0, off = 0, len = 0;
        if (sscanf(what + 4, "%llx:%llu:%llx:%llx", &g, &loads, &off, &len) == 4) {
            t = g;
            int ok = 1;
            for (unsigned long long q = 0; q < loads && ok; q++) ok = kernel_read64(t, &t) && t;
            for (u64 o = 0; ok && o + 4 <= len; o += 4) n += poke_word(t + off + o, mode);
        }
    } else if (!strncmp(what, "boma:", 5) && nfighters > 0) {
        const char *q = what + 5;
        t = fighters[0].boma;
        int ok = t != 0;
        for (;;) {   /* the loads: hex offsets separated by '/', up to the next ':' */
            char *end;
            unsigned long long o = strtoull(q, &end, 16);
            if (end == q) { ok = 0; break; }
            ok = ok && kernel_read64(t + o, &t) && t;
            q = end;
            if (*q == '/') { q++; continue; }
            break;
        }
        unsigned long long off = 0, len = 0;
        if (ok && *q == ':' && sscanf(q + 1, "%llx:%llx", &off, &len) == 2)
            for (u64 o = 0; o + 4 <= len; o += 4) n += poke_word(t + off + o, mode);
    }
    return n;
}

/* (research: errors injected on purpose) SSBU_RB_VERIFY_INJECT=<round>:<target>: right after the replay check's load
 * of that round (hle_rb_core.c), the target's words get bit 0x00400000 flipped once (poke_target, mode 1): an error
 * the strict oracle must find in that round's comparison. */
void research_inject(long long round) {
    const char *e = getenv("SSBU_RB_VERIFY_INJECT");
    char *end;
    if (!e || !*e || strtoll(e, &end, 10) != round || *end != ':') return;
    u64 n = poke_target(end + 1, 0);   /* (mode 0, as the held perturbations: words that are 0 or -1 are indices and sentinels, and
                                         * flipping them stops the game (the table's tick, 2026-11-12), which proves nothing) */
    fprintf(stderr, "[state] SSBU_RB_VERIFY_INJECT: replay %lld, %s: %llu words changed after the load\n", round, end + 1, (unsigned long long)n);
}

static long long mc_n[6], mc_bad[6]; static int mc_said;   /* (SSBU_MATCH_CHECK) */
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
    {   /* (research: a sustained perturbation) SSBU_POKE_HOLD=<first fight frame>,<frames>,<target>: at the first
         * fighter's frame line of each frame from <first> for <frames> frames, bit 0x00400000 is SET (OR: the same
         * perturbation whether the game rewrote the word this frame or not) in each word that is neither 0 nor -1 of:
         *   table                      the 1,024-entry table's three per-frame lines (+0x80, +0x140, +0x160 of each
         *                              entry, [[0x710532f490]]), as SSBU_POKE_TABLE;
         *   ptr:<global>:<loads>:<off>:<len>  <len> bytes at <off> past the address read <loads> times from <global>
         *                              (hex), e.g. a block reached through a global pointer. */
        static long long h_at = -2, h_n;
        static char h_what[96];
        if (h_at == -2) {
            const char *e = getenv("SSBU_POKE_HOLD");
            h_at = -1;
            if (e && *e && sscanf(e, "%lld,%lld,%95s", &h_at, &h_n, h_what) != 3) h_at = -1;
        }
        if (k == 0 && h_at >= 0 && f >= h_at && f < h_at + h_n) {
            u64 n = poke_target(h_what, 0);
            if (f == h_at || f == h_at + h_n - 1 || (f - h_at) % 300 == 0)
                fprintf(stderr, "[state] SSBU_POKE_HOLD %s: fight frame %lld, %llu words with the bit set\n", h_what, f, (unsigned long long)n);
        }
    }
    {   /* (research: SSBU_FINAL_LOG=1) at the first fighter's frame line, the game's own FighterManager::is_final and
         * get_final_actor_entry_id: a line each time a Final Smash starts or ends */
        static int fl = -1, was;
        if (fl < 0) fl = getenv("SSBU_FINAL_LOG") != NULL;
        u64 sym = 0, mgr = 0;
        if (fl && k == 0 && (sym = rt_symbol("_ZN3lib9SingletonIN3app14FighterManagerEE9instance_E")) && kernel_read64(sym, &mgr) && mgr) {
            Cpu keep = *c;
            int on = (int)(rt_callsym(c, "_ZN3app8lua_bind29FighterManager__is_final_implEPNS_14FighterManagerE", 1, mgr) & 1);
            u64 who = on ? rt_callsym(c, "_ZN3app8lua_bind45FighterManager__get_final_actor_entry_id_implEPNS_14FighterManagerE", 1, mgr) : 0;
            *c = keep;
            if (on != was) fprintf(stderr, "[state] final smash %s at fight frame %lld (actor entry %d)\n", on ? "ON" : "off", f, (int)(u32)who);
            was = on;
        }
    }
    {   /* (SSBU_RB_LF_INPUT, hle_rb_core.c) the dump counts logic frames from the fight's first read of player 1: frames
         * run again by a rollback then keep their number, and two runs compare frame by frame */
        int rb_lfi_rel_now(void);
        int rl = rb_lfi_rel_now();
        if (rl >= 0) f = rl;
        static int lfd = -1;   /* SSBU_STATE_DUMP_LF=1: by the game's logic frame counter (a replay's frames keep their numbers) */
        if (lfd < 0) lfd = getenv("SSBU_STATE_DUMP_LF") != NULL;
        if (lfd) f = (long long)ld32(0x71052c5184ull);
    }
    if (f < first || f > last || f % every) return;
    {   /* (research, 2026-11-12: the community's constants checked by the game, research/map/community/)
         * SSBU_CONST_CHECK=<file> of "NAME value" lines (hex value, as u32): once, at the first dumped frame, asks the game
         * lib::lua_bind_get_value<int>(xxh64(NAME, seed ~0)) for each name, as lua2cpp_common gets its constants, and writes
         * "NAME community game" (game "absent" when the game does not know the name) to <file>.out. */
        static int cc = -1;
        if (cc < 0) {
            const char *path = getenv("SSBU_CONST_CHECK");
            cc = 0;
            u64 fn = rt_symbol("_ZN3lib18lua_bind_get_valueIiEEbmRT_");
            FILE *in = path && fn ? fopen(path, "r") : NULL;
            if (in) {
                char outp[600];
                snprintf(outp, sizeof outp, "%s.out", path);
                FILE *out = fopen(outp, "w");
                char ln[400];
                long long n = 0, same = 0, diff = 0, absent = 0;
                while (out && fgets(ln, sizeof ln, in)) {
                    char name[300]; unsigned long v = 0;
                    if (sscanf(ln, "%299s %lx", name, &v) != 2) continue;
                    Cpu saved = *c;
                    u64 sp = (c->sp - 0x40) & ~15ull, o = sp + 0x20;
                    st32(o, 0xdeadbeefu);
                    c->sp = sp;
                    c->x[0] = fight_xxh64(name, strlen(name), ~0ull);
                    c->x[1] = o;
                    rt_call(c, fn);
                    int ok = (int)(c->x[0] & 1);
                    u32 got = ld32(o);
                    *c = saved;
                    n++;
                    if (!ok) { absent++; fprintf(out, "%s %#lx absent\n", name, v); }
                    else { if (got == (u32)v) same++; else diff++; fprintf(out, "%s %#lx %#x\n", name, v, got); }
                }
                fclose(in);
                if (out) fclose(out);
                fprintf(stderr, "[state] SSBU_CONST_CHECK: %lld names: %lld same value, %lld different, %lld unknown to the game (%s)\n", n, same, diff, absent, outp);
            }
        }
    }
    {   /* (research, 2026-11-12: match-level state read from the code, research/map/code_reading/tail_sites.json)
         * SSBU_MATCH_CHECK=1: at the first fighter's dumped frames, the bytes at the offsets the code reading gives against
         * the game's own getters: each player entry's stock count (+0x1e8) and "on rebirth" (+0x49c) against
         * FighterInformation::stock_count / is_on_rebirth; the battle camera's limit range (+0xc20), dead area (+0xc30)
         * and target position (+0xeb0) against app::camera's getters. Totals at the report. */
        static int mc = -1;
        if (mc < 0) mc = getenv("SSBU_MATCH_CHECK") != NULL;
        if (mc && k == 0) {
            u64 mgr = 0, data = 0, nent = 0;
            u64 sym = rt_symbol("_ZN3lib9SingletonIN3app14FighterManagerEE9instance_E");
            Cpu keep = *c;
            if (sym && kernel_read64(sym, &mgr) && mgr && kernel_read64(mgr, &data) && data && kernel_read64(data + 0xa0, &nent)) {
                for (u64 e = 0; e < 8 && e < (nent & 0xffffffff); e++) {
                    u64 entry = 0;
                    if (!kernel_read64(data + 0x20 + 8 * e, &entry) || !entry) continue;
                    u64 info = rt_callsym(c, "_ZN3app8lua_bind44FighterManager__get_fighter_information_implEPNS_14FighterManagerENS_14FighterEntryIDE", 2, mgr, e);
                    if (!info) continue;
                    u32 st = (u32)rt_callsym(c, "_ZN3app8lua_bind36FighterInformation__stock_count_implEPNS_18FighterInformationE", 1, info);
                    u32 rb = (u32)rt_callsym(c, "_ZN3app8lua_bind38FighterInformation__is_on_rebirth_implEPNS_18FighterInformationE", 1, info) & 1;
                    mc_n[0]++; if (ld32(entry + 0x1e8) != st) mc_bad[0]++;
                    mc_n[1]++; if ((ld8(entry + 0x49c) & 1) != rb) mc_bad[1]++;
                    mc_n[5]++; if (info != entry + 0xf0) mc_bad[5]++;
                    if (mc_said < 4 && (ld32(entry + 0x1e8) != st || info != entry + 0xf0)) { mc_said++; fprintf(stderr, "[state] match check: entry %llu: stock raw %u game %u, info %#llx entry+0xf0 %#llx\n", (unsigned long long)e, ld32(entry + 0x1e8), st, (unsigned long long)info, (unsigned long long)(entry + 0xf0)); }
                }
            }
            u64 cam = 0, holder = 0;
            if (kernel_read64(0x71052b8f00ull, &holder) && holder && kernel_read64(holder, &cam) && cam) {
                static const char *fn[3] = {"_ZN3app6camera22get_camera_limit_rangeEv", "_ZN3app6camera13get_dead_areaEv", "_ZN3app6camera10target_posEv"};
                static const u32 off[3] = {0xc20, 0xc30, 0xeb0}, len[3] = {16, 16, 8};
                for (int q = 0; q < 3; q++) {
                    memset(&c->v[0], 0, sizeof c->v[0] * 4);
                    rt_callsym(c, fn[q], 0);
                    u8 got_q[16], got_s[16];
                    memcpy(got_q, &c->v[0], 16);   /* (a 128-bit vector in q0) */
                    for (int l = 0; l < 4; l++) memcpy(got_s + 4 * l, &c->v[l], 4);   /* (or four floats in s0-s3) */
                    u8 raw[16];
                    for (u32 b = 0; b < len[q]; b++) raw[b] = ld8(cam + off[q] + b);
                    mc_n[2 + q]++;
                    if (memcmp(raw, got_q, len[q]) && memcmp(raw, got_s, len[q])) {
                        mc_bad[2 + q]++;
                        if (mc_said < 8) { mc_said++; fprintf(stderr, "[state] match check: camera %s differs: raw %08x %08x game q0 %08x %08x s %08x %08x\n", fn[q], *(u32 *)raw, *(u32 *)(raw + 4), *(u32 *)got_q, *(u32 *)(got_q + 4), *(u32 *)got_s, *(u32 *)(got_s + 4)); }
                    }
                }
            }
            *c = keep;
        }
    }
    dump(boma, ld32(boma + 8), f, 0);
    if (probe_now(f)) probes(c, boma, ld32(boma + 8), f);
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
                if (!fighter) {
                    dump(a, id, f, 1);
                    static int po = -1;
                    if (po < 0) po = getenv("SSBU_PROBE_OTHERS") != NULL;
                    if (po && probe_now(f)) probes(c, a, id, f);
                }
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
    rt_ww_report();
    if (mc_n[0] || mc_n[2]) {
        static const char *nm[6] = {"stock count (+0x1e8)", "on rebirth (+0x49c)", "camera limit range (+0xc20)", "camera dead area (+0xc30)", "camera target (+0xeb0)", "information = entry + 0xf0"};
        for (int q = 0; q < 6; q++)
            fprintf(stderr, "[state] SSBU_MATCH_CHECK: %s: %lld equal, %lld different\n", nm[q], mc_n[q] - mc_bad[q], mc_bad[q]);
    }
    if (on != 1) return;
    fflush(out);
    table_dump();
    scan_all();
    fprintf(stderr, "[state] dump: %lld records, %lld MB; %d fighters, %d pools of battle objects\n", records, bytes_out >> 20, nfighters, npools);
    for (int i = 0; i < npools; i++) fprintf(stderr, "[state]   pool %#llx, %llu bytes, allocated from %#llx\n", (unsigned long long)pools[i].addr, (unsigned long long)pools[i].size, (unsigned long long)pools[i].lr);
}
