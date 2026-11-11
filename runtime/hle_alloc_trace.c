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
#ifdef _WIN32
        __try { next = ld64(fp); r = ld64(fp + 8); } __except (EXCEPTION_EXECUTE_HANDLER) { break; }
#else
        next = ld64(fp); r = ld64(fp + 8);
#endif
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
    b->used = 2;   /* (a tombstone: the probe goes on past it) */
    nlive--;
    UNLOCK();
}

/* An allocator call: kind 0 a size in x[sx], 1 calloc (x0 * x1), 2 realloc (x0 the old block, x1 the size). */
static void alloc_call(Cpu *c, GuestFn *orig, int kind, int sx) {
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
        if (b->size >= 8) {
#ifdef _WIN32
            __try { w0 = ld64(b->addr); } __except (EXCEPTION_EXECUTE_HANDLER) { w0 = 0; }
#else
            w0 = ld64(b->addr);
#endif
        }
        fprintf(f, "%#llx %llu %lld %u %#llx", (unsigned long long)b->addr, (unsigned long long)b->size, b->frame, b->fight, (unsigned long long)w0);
        if (b->site != 0xFFFFFFFFu) for (int k = 0; k < SITE_DEPTH; k++) fprintf(f, " %#llx", (unsigned long long)sites[b->site].ra[k]);
        fputc('\n', f);
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
