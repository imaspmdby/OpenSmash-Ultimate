/* Research (research/RESEARCH.md, phase 2): the game's heap allocations, by allocation site.
 *
 * SSBU_ALLOC_TRACE=<file prefix> wraps main's exported allocator (malloc, calloc, realloc, aligned_alloc, free,
 * operator new / new[] / delete / delete[] and their nothrow and sized forms) and keeps every live block: its
 * address, size, allocation site and the frame it was made at. A site is the chain of up to SITE_DEPTH return
 * addresses: the allocator's caller (x30) and, through the guest's frame records (x29), its callers. Only the
 * outermost allocator call of a thread is recorded (operator new may call malloc).
 *
 * alloc_trace_report() (hle_fight_test.c, at the SSBU_DEBUG_END exit) writes:
 *   <prefix>.live   one line a live block: "<address> <size> <frame made> <in fight> <first word> <site...>" (the
 *                   first word: a C++ object's vtable, often); its first line "# setup <frame> end <frame>"
 *   <prefix>.sites  one line a site: "<allocs> <frees> <bytes allocated> <live blocks> <live bytes>
 *                   <allocs in the fight> <frees in the fight> <site...>"
 * Frames are counted at the graphics module's frame end (FRAME_HOOK_END); "in fight" is the game's ready-go flag.
 * Unset, every wrap only calls the game's function and nothing is registered. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

#include "frame_hooks.h"
#include "host.h"

#define SITE_DEPTH 4
int game_fight_on(void);   /* (hle_fight_test.c) */

static int on = -1;
static const char *prefix;
static volatile long long frame_no;

typedef struct Block { u64 addr, size; long long frame; u32 site; u8 fight, used; } Block;
typedef struct Site { u64 ra[SITE_DEPTH]; long long allocs, frees, bytes, live, live_bytes, f_allocs, f_frees; u8 used; } Site;
#define BLOCKS (1u << 23)   /* open addressing, by address */
#define SITES (1u << 18)
static Block *blocks;
static Site *sites;
static u32 nsites;
static long long nlive, lost_blocks, lost_sites, unknown_frees;
#ifdef _WIN32
static SRWLOCK lock = SRWLOCK_INIT;
#define LOCK() AcquireSRWLockExclusive(&lock)
#define UNLOCK() ReleaseSRWLockExclusive(&lock)
static __declspec(thread) int depth;
#else
#define LOCK() ((void)0)
#define UNLOCK() ((void)0)
static __thread int depth;
#endif

static void frame_end(Cpu *c, const u64 args[8], void *ctx) { (void)c; (void)args; (void)ctx; frame_no++; }
static volatile long long setup_frame = -1;   /* (the last match set-up: the player record builder's first call there) */
static long long setup_seen = -100;
static void record_hook(Cpu *c, const u64 args[8], void *ctx) {
    (void)c; (void)args; (void)ctx;
    if (frame_no - setup_seen > 60) setup_frame = frame_no;
    setup_seen = frame_no;
}

static int enabled(void) {
    if (on >= 0) return on;
    const char *e = getenv("SSBU_ALLOC_TRACE");
    on = 0;
    if (e && *e) {
        blocks = calloc(BLOCKS, sizeof *blocks);
        sites = calloc(SITES, sizeof *sites);
        if (blocks && sites) {
            prefix = e;
            frame_hook_add(FRAME_HOOK_END, FRAME_ORDER_FIGHT_TEST + 10, NULL, frame_end, NULL);
            frame_hook_add(FRAME_HOOK_RECORD, FRAME_ORDER_FIGHT_TEST + 10, record_hook, NULL, NULL);
            fprintf(stderr, "[alloc] SSBU_ALLOC_TRACE: main's allocator traced, report to %s.live / .sites\n", prefix);
            on = 1;
        }
    }
    return on;
}

static u64 mix(u64 x) { x ^= x >> 33; x *= 0xff51afd7ed558ccdull; x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ull; x ^= x >> 33; return x; }

/* The caller chain: x30, then the frame records from x29 (each [fp] the caller's fp, [fp + 8] its return address),
 * as long as they lie above the thread's stack pointer, within 1 MB of it, and go up (a thread's stack may be in the
 * stack area or in the heap). */
static void chain(Cpu *c, u64 ra[SITE_DEPTH]) {
    memset(ra, 0, sizeof(u64) * SITE_DEPTH);
    ra[0] = c->x[30];
    u64 fp = c->x[29], sp = c->sp;
    for (int i = 1; i < SITE_DEPTH; i++) {
        if (fp < sp || fp - sp > (1u << 20) || (fp & 7)) break;
        u64 next = 0, r = 0;
        next = ld64(fp); r = ld64(fp + 8);   /* (within 1 MB above this thread's sp: its own stack) */
        if (!r) break;
        ra[i] = r;
        if (next <= fp || next - fp > (1u << 20)) break;
        fp = next;
    }
}

static u32 site_of(const u64 ra[SITE_DEPTH]) {   /* (lock held) */
    u64 h = 0;
    for (int i = 0; i < SITE_DEPTH; i++) h = mix(h ^ ra[i]);
    for (u32 k = 0, i = (u32)h & (SITES - 1); k < SITES; k++, i = (i + 1) & (SITES - 1)) {
        if (!sites[i].used) {
            if (nsites >= SITES * 3 / 4) { lost_sites++; return 0xFFFFFFFFu; }
            sites[i].used = 1; memcpy(sites[i].ra, ra, sizeof sites[i].ra); nsites++;
            return i;
        }
        if (!memcmp(sites[i].ra, ra, sizeof sites[i].ra)) return i;
    }
    return 0xFFFFFFFFu;
}

static Block *find(u64 addr, int make) {   /* (lock held) */
    for (u32 k = 0, i = (u32)mix(addr) & (BLOCKS - 1); k < 64; k++, i = (i + 1) & (BLOCKS - 1)) {
        if (blocks[i].used == 1 && blocks[i].addr == addr) return &blocks[i];
        if (blocks[i].used != 1 && make) return &blocks[i];   /* (a free slot or a tombstone) */
        if (!blocks[i].used) return NULL;
    }
    return NULL;
}

static void note_alloc(Cpu *c, u64 addr, u64 size) {
    if (!addr) return;
    u64 ra[SITE_DEPTH];
    chain(c, ra);
    int fight = game_fight_on();
    LOCK();
    u32 s = site_of(ra);
    Block *b = find(addr, 0);
    if (b) {   /* (made again without our seeing its free: a free through another path) */
        if (b->site != 0xFFFFFFFFu) { sites[b->site].live--; sites[b->site].live_bytes -= (long long)b->size; }
        nlive--;
    } else b = find(addr, 1);
    if (!b) { lost_blocks++; UNLOCK(); return; }
    b->addr = addr; b->size = size; b->frame = frame_no; b->site = s; b->fight = (u8)fight; b->used = 1;
    nlive++;
    if (s != 0xFFFFFFFFu) {
        Site *t = &sites[s];
        t->allocs++; t->bytes += (long long)size; t->live++; t->live_bytes += (long long)size; t->f_allocs += fight;
    }
    UNLOCK();
}

/* The pages that held a block freed since the match set-up (churn: memory used and given back, so in no live block at
 * the report): per page, the site and size of the last block freed there and how many were. <prefix>.freed:
 * "<page> <site's first return address> <size> <frees>". Blocks over 1 MB count their first 256 pages. */
typedef struct FreedPage { u64 page; u64 size; u32 site, count; } FreedPage;
#define FREED (1u << 21)
static FreedPage *freed;
static long long freed_lost;
static void freed_note(u64 addr, u64 size, u32 site) {   /* (lock held) */
    if (!freed && !(freed = calloc(FREED, sizeof *freed))) return;
    u64 pages = ((addr + (size ? size : 1) + 0xFFF) >> 12) - (addr >> 12);
    if (pages > 256) pages = 256;
    for (u64 k = 0; k < pages; k++) {
        u64 pg = (addr & ~0xFFFull) + (k << 12);
        u32 i = (u32)mix(pg) & (FREED - 1), n = 0;
        while (freed[i].page && freed[i].page != pg && n < 64) { i = (i + 1) & (FREED - 1); n++; }
        if (n == 64) { freed_lost++; continue; }
        freed[i].page = pg; freed[i].size = size; freed[i].site = site; freed[i].count++;
    }
}
static void note_free(u64 addr) {
    if (!addr) return;
    int fight = game_fight_on();
    LOCK();
    Block *b = find(addr, 0);
    if (!b) { unknown_frees++; UNLOCK(); return; }
    if (b->site != 0xFFFFFFFFu) {
        Site *t = &sites[b->site];
        t->frees++; t->live--; t->live_bytes -= (long long)b->size; t->f_frees += fight;
    }
    if (setup_frame >= 0) freed_note(b->addr, b->size, b->site);
    b->used = 2;   /* (a tombstone: the probe goes on past it) */
    nlive--;
    UNLOCK();
}

/* An allocator call: kind 0 a size in x[sx], 1 calloc (x0 * x1), 2 realloc (x0 the old block, x1 the size). */
int state_dump_wants(u64 lr);                 /* (hle_state_dump.c: an allocation from the battle objects' set-up) */
void state_dump_pool(u64 lr, u64 addr, u64 size);
/* (research: SSBU_RB_SKIP_SITES, hle_rb_state.c) blocks of the allocation sites a save leaves out: 0 when off */
#ifdef _WIN32
int rb_skip_site_wants(u64 lr);
void rb_skip_site_block(u64 lr, u64 addr, u64 size);
void rb_skip_site_free(u64 addr);
#else
static int rb_skip_site_wants(u64 lr) { (void)lr; return 0; }
static void rb_skip_site_block(u64 lr, u64 addr, u64 size) { (void)lr; (void)addr; (void)size; }
static void rb_skip_site_free(u64 addr) { (void)addr; }
#endif
static void alloc_call(Cpu *c, GuestFn *orig, int kind, int sx) {
    if (kind != 2 && rb_skip_site_wants(c->x[30])) {
        u64 lr = c->x[30], size = kind == 1 ? c->x[0] * c->x[1] : c->x[sx];
        int traced = enabled() && !depth;
        Cpu at = *c;
        depth++; orig(c); depth--;
        if (traced) note_alloc(&at, c->x[0], size);
        rb_skip_site_block(lr, c->x[0], size);
        return;
    }
    if (kind != 2 && state_dump_wants(c->x[30])) {
        u64 lr = c->x[30], size = kind == 1 ? c->x[0] * c->x[1] : c->x[sx];
        if (!enabled() || depth) { orig(c); state_dump_pool(lr, c->x[0], size); return; }
        Cpu at = *c;
        depth++; orig(c); depth--;
        note_alloc(&at, c->x[0], size);
        state_dump_pool(lr, c->x[0], size);
        return;
    }
    if (!enabled() || depth) { orig(c); return; }
    Cpu at = *c;   /* (the arguments and the caller's x29 / x30, as at the call) */
    depth++;
    orig(c);
    depth--;
    u64 r = c->x[0];
    if (kind == 2) {
        if (at.x[0] && (r || !at.x[1])) note_free(at.x[0]);
        if (r) note_alloc(&at, r, at.x[1]);
    } else note_alloc(&at, r, kind == 1 ? at.x[0] * at.x[1] : at.x[sx]);
}
static void free_call(Cpu *c, GuestFn *orig) {
    rb_skip_site_free(c->x[0]);
    if (!enabled() || depth) { orig(c); return; }
    u64 p = c->x[0];
    depth++;
    orig(c);
    depth--;
    note_free(p);
}

/* jemalloc's own entry points in main (13.0.5; ssbu-recomp's rb_learned.c and hostrt.c found them in 13.0.4): what
 * the game calls without the exported names. posix_memalign(&p, align, size) returns 0 and the block in *p. */
static void posix_memalign_call(Cpu *c, GuestFn *orig) {
    if (rb_skip_site_wants(c->x[30])) {
        u64 lr = c->x[30], out = c->x[0], size = c->x[2];
        int traced = enabled() && !depth;
        Cpu at = *c;
        depth++; orig(c); depth--;
        if (c->x[0] == 0 && out) { if (traced) note_alloc(&at, ld64(out), size); rb_skip_site_block(lr, ld64(out), size); }
        return;
    }
    if (state_dump_wants(c->x[30])) {
        u64 lr = c->x[30], out = c->x[0], size = c->x[2];
        int traced = enabled() && !depth;
        Cpu at = *c;
        depth++; orig(c); depth--;
        if (c->x[0] == 0 && out) { if (traced) note_alloc(&at, ld64(out), size); state_dump_pool(lr, ld64(out), size); }
        return;
    }
    if (!enabled() || depth) { orig(c); return; }
    Cpu at = *c;
    depth++;
    orig(c);
    depth--;
    if (c->x[0] == 0 && at.x[0]) note_alloc(&at, ld64(at.x[0]), at.x[2]);
}
/* signature: 16 words, sha256 200ca5879ab69847 */
HLE_WRAP(710392e1f0) { posix_memalign_call(c, f_710392e1f0_orig); }
/* signature: 16 words, sha256 b3a1f997ac047ac6 */
HLE_WRAP(710392e290) { alloc_call(c, f_710392e290_orig, 0, 1); }
/* signature: 16 words, sha256 56a9f4d6b487fcfb */
HLE_WRAP(710392e330) { alloc_call(c, f_710392e330_orig, 2, 0); }
/* signature: 16 words, sha256 f116e7eee180c88d */
HLE_WRAP(710392eb40) { free_call(c, f_710392eb40_orig); }

HLE_WRAP_EXPORT(malloc) { alloc_call(c, orig, 0, 0); }
HLE_WRAP_EXPORT(calloc) { alloc_call(c, orig, 1, 0); }
HLE_WRAP_EXPORT(realloc) { alloc_call(c, orig, 2, 0); }
HLE_WRAP_EXPORT(aligned_alloc) { alloc_call(c, orig, 0, 1); }
HLE_WRAP_EXPORT(_Znwm) { alloc_call(c, orig, 0, 0); }
HLE_WRAP_EXPORT(_Znam) { alloc_call(c, orig, 0, 0); }
HLE_WRAP_EXPORT(_ZnwmRKSt9nothrow_t) { alloc_call(c, orig, 0, 0); }
HLE_WRAP_EXPORT(_ZnamRKSt9nothrow_t) { alloc_call(c, orig, 0, 0); }
HLE_WRAP_EXPORT(free) { free_call(c, orig); }
HLE_WRAP_EXPORT(_ZdlPv) { free_call(c, orig); }
HLE_WRAP_EXPORT(_ZdaPv) { free_call(c, orig); }
HLE_WRAP_EXPORT(_ZdlPvm) { free_call(c, orig); }
HLE_WRAP_EXPORT(_ZdaPvm) { free_call(c, orig); }
HLE_WRAP_EXPORT(_ZdlPvRKSt9nothrow_t) { free_call(c, orig); }
HLE_WRAP_EXPORT(_ZdaPvRKSt9nothrow_t) { free_call(c, orig); }

void alloc_trace_report(void) {
    if (on != 1) return;
    char path[1024];
    LOCK();
    snprintf(path, sizeof path, "%s.live", prefix);
    FILE *f = fopen(path, "w");
    long long live_bytes = 0;
    if (f) fprintf(f, "# setup %lld end %lld\n", setup_frame, frame_no);
    for (u32 i = 0; f && i < BLOCKS; i++) {
        const Block *b = &blocks[i];
        if (b->used != 1) continue;
        live_bytes += (long long)b->size;
        u64 w0 = 0;
        if (b->size >= 8 && !kernel_read64(b->addr, &w0)) w0 = 0;   /* (the kernel's read: memory that may be gone) */
        fprintf(f, "%#llx %llu %lld %u %#llx", (unsigned long long)b->addr, (unsigned long long)b->size, b->frame, b->fight, (unsigned long long)w0);
        if (b->site != 0xFFFFFFFFu) for (int k = 0; k < SITE_DEPTH; k++) fprintf(f, " %#llx", (unsigned long long)sites[b->site].ra[k]);
        fputc('\n', f);
    }
    if (f) fclose(f);
    snprintf(path, sizeof path, "%s.freed", prefix);
    f = freed ? fopen(path, "w") : NULL;
    for (u32 i = 0; f && i < FREED; i++) {
        if (!freed[i].page) continue;
        fprintf(f, "%#llx %#llx %llu %u\n", (unsigned long long)freed[i].page,
                (unsigned long long)(freed[i].site != 0xFFFFFFFFu ? sites[freed[i].site].ra[0] : 0), (unsigned long long)freed[i].size, freed[i].count);
    }
    if (f) fclose(f);
    snprintf(path, sizeof path, "%s.sites", prefix);
    f = fopen(path, "w");
    for (u32 i = 0; f && i < SITES; i++) {
        const Site *t = &sites[i];
        if (!t->used) continue;
        fprintf(f, "%lld %lld %lld %lld %lld %lld %lld", t->allocs, t->frees, t->bytes, t->live, t->live_bytes, t->f_allocs, t->f_frees);
        for (int k = 0; k < SITE_DEPTH; k++) fprintf(f, " %#llx", (unsigned long long)t->ra[k]);
        fputc('\n', f);
    }
    if (f) fclose(f);
    fprintf(stderr, "[alloc] report: %lld live blocks (%lld MB), %u sites; %lld blocks and %lld sites not kept (tables full), "
            "%lld frees of blocks not seen made; frame %lld\n", nlive, live_bytes >> 20, nsites, lost_blocks, lost_sites, unknown_frees, frame_no);
    UNLOCK();
}

/* ---- reachability from the fighters (research, SSBU_REACH=<file>, with SSBU_ALLOC_TRACE) -------------------------
 * From each root (a fighter's boma) every aligned word that points into a live traced block is followed: a block
 * of 64 KB or less is a granule whole, a larger one (an arena, a sub-heap) only the 4 KB page pointed into. Each
 * granule is scanned once, breadth first, up to REACH_DEPTH levels. One line a granule reached:
 * "<address> <length> <depth> <root> <parent granule> <first word>", root = fighter * 1024 + the boma word's index
 * the path left the boma by (its module, for the module words). Memory is read as the threads run (a report). */
#define REACH_DEPTH 12
#define REACH_MAX (1u << 21)
typedef struct Gran { u64 addr, len, parent; u32 root; u8 depth; } Gran;
static u64 (*rb_sorted)[2]; static u32 rn;   /* the live blocks, by address */
static int blk_cmp(const void *a, const void *b) { u64 x = ((const u64 *)a)[0], y = ((const u64 *)b)[0]; return (x > y) - (x < y); }
static long blk_find(u64 g) {
    long lo = 0, hi = (long)rn;
    while (lo < hi) { long m = (lo + hi) / 2; if (rb_sorted[m][0] + rb_sorted[m][1] <= g) lo = m + 1; else hi = m; }
    return lo < (long)rn && rb_sorted[lo][0] <= g ? lo : -1;
}
static u64 *seen_tab; static u32 seen_n;   /* granule starts seen: open addressing */
static int seen_add(u64 a) {
    for (u32 k = 0, i = (u32)mix(a) & (REACH_MAX * 2 - 1); k < REACH_MAX * 2; k++, i = (i + 1) & (REACH_MAX * 2 - 1)) {
        if (seen_tab[i] == a) return 0;
        if (!seen_tab[i]) { seen_tab[i] = a; seen_n++; return 1; }
    }
    return 0;
}
#ifdef _WIN32
static const u8 *rc_lo, *rc_hi;   /* (the last committed run found) */
static int readable_page(u64 g) {
    const u8 *p = (const u8 *)G2H(g);
    if (p >= rc_lo && p < rc_hi) return 1;
    MEMORY_BASIC_INFORMATION mi;
    if (!VirtualQuery(p, &mi, sizeof mi) || mi.State != MEM_COMMIT || (mi.Protect & (PAGE_NOACCESS | PAGE_GUARD))) return 0;
    rc_lo = mi.BaseAddress; rc_hi = (const u8 *)mi.BaseAddress + mi.RegionSize;
    return 1;
}
#else
static int readable_page(u64 g) { u64 w; return kernel_read64(g, &w); }
#endif
static Gran *q; static u32 qn, qh;
static void reach_push(u64 target, u32 root, u8 depth, u64 parent) {
    long i = blk_find(target);
    if (i < 0 || qn >= REACH_MAX) return;
    u64 a = rb_sorted[i][0], len = rb_sorted[i][1];
    if (len > 0x10000) { a = target & ~0xFFFull; len = 0x1000; if (a < rb_sorted[i][0]) { len -= rb_sorted[i][0] - a; a = rb_sorted[i][0]; } }
    if (!seen_add(a)) return;
    q[qn++] = (Gran){a, len, parent, root, depth};
}
/* roots: kinds[r] 0 a boma (the path's root is the boma word it left by: r * 1024 + word), 1 an object (r * 1024 +
 * 1023: its block whole, or 4 KB from it when no traced block holds it, a global). labels[r] goes to the file's
 * "# root <r> <label>" lines. A granule is reached from the nearest root, breadth first over all roots at once. */
void alloc_trace_reach(const u64 *roots, const int *kinds, const char *const *labels, int nroots) {
    const char *path = getenv("SSBU_REACH");
    if (on != 1 || !path || !*path || !nroots) return;
    LOCK();
    rb_sorted = malloc(sizeof *rb_sorted * (size_t)(nlive + 1));
    seen_tab = calloc(REACH_MAX * 2, sizeof *seen_tab);
    q = malloc(sizeof *q * REACH_MAX);
    rn = 0; seen_n = 0; qn = qh = 0;
    if (!rb_sorted || !seen_tab || !q) { UNLOCK(); return; }
    for (u32 i = 0; i < BLOCKS; i++) if (blocks[i].used == 1) { rb_sorted[rn][0] = blocks[i].addr; rb_sorted[rn][1] = blocks[i].size ? blocks[i].size : 1; rn++; }
    UNLOCK();
    qsort(rb_sorted, rn, sizeof *rb_sorted, blk_cmp);
    /* depth 0: each boma's words (its modules at fixed offsets); a path's root is the word it left by */
    for (int r = 0; r < nroots; r++) {
        if (kinds[r] == 1) {
            if (!roots[r]) continue;
            if (blk_find(roots[r]) >= 0) reach_push(roots[r], (u32)r * 1024 + 1023, 1, 0);
            else if (seen_add(roots[r])) q[qn++] = (Gran){roots[r], 0x1000, 0, (u32)r * 1024 + 1023, 1};
            continue;
        }
        for (u32 w = 0; w < 0x400 / 8; w++) {
            u64 x;
            if (!kernel_read64(roots[r] + 8ull * w, &x)) break;
            reach_push(x, (u32)r * 1024 + w, 1, roots[r]);
        }
    }
    u64 words = 0;
    while (qh < qn) {
        Gran g = q[qh++];
        if (g.depth >= REACH_DEPTH) continue;
        for (u64 a = g.addr & ~7ull; a + 8 <= g.addr + g.len; a += 8) {
            if (!(a & 0xFFF) || a == (g.addr & ~7ull)) if (!readable_page(a)) { a = (a | 0xFFF) - 7; continue; }
            u64 x = ld64(a);
            words++;
            if (x < 0x1000000 || (x & 7)) continue;
            reach_push(x, g.root, (u8)(g.depth + 1), g.addr);
        }
    }
    FILE *f = fopen(path, "w");
    u64 bytes = 0;
    for (int r = 0; f && r < nroots; r++) fprintf(f, "# root %d %s %#llx\n", r, labels[r], (unsigned long long)roots[r]);
    for (u32 i = 0; f && i < qn; i++) {
        u64 w0 = 0;
        if (q[i].len >= 8) kernel_read64(q[i].addr, &w0);
        bytes += q[i].len;
        fprintf(f, "%#llx %llu %u %u %#llx %#llx\n", (unsigned long long)q[i].addr, (unsigned long long)q[i].len, q[i].depth, q[i].root,
                (unsigned long long)q[i].parent, (unsigned long long)w0);
    }
    if (f) fclose(f);
    fprintf(stderr, "[alloc] reach: from %d bomas, %u granules (%llu MB), %llu words read, depth up to %d%s\n", nroots, qn,
            (unsigned long long)(bytes >> 20), (unsigned long long)words, REACH_DEPTH, qn >= REACH_MAX ? " (STOPPED: the granule table is full)" : "");
    free(rb_sorted); free(seen_tab); free(q); rb_sorted = NULL; seen_tab = NULL; q = NULL;
}
