/* Research (research/RESEARCH.md, phase 2): which memory the game's code reads and writes, frame by frame.
 *
 * Only in a build whose generated C has SSBU_MEMTRACE defined (SSBU_GAME_CFLAGS=/DSSBU_MEMTRACE, a build folder of its
 * own): recomp.h then reports every guest access to rt_mt_access while rt_mt_on is set. Elsewhere this file is only
 * the two symbols, never set.
 *
 * SSBU_MEMTRACE=<first fight frame>,<frames>,<file>: from that fight frame (counted at the graphics frame end while
 * the game's ready-go flag is up), for that many frames, every 64-byte line the game's code touches keeps:
 *   frames_r / frames_w  frames that read / wrote it;
 *   first_r              frames whose first access to it was a read;
 *   live_in              frames whose first access was a read and which a write in an earlier frame of the window
 *                        preceded: the line carries a value from one frame into the next (state);
 *   threads              a bit per host thread (the first 32 seen), which touched it.
 * Frames are cut at the frame end. Lines are kept in tables of 2 MB of guest memory each, made on first touch.
 * The file: a header "MT1\0", u32 frames, u32 threads, then per thread (u32 host id, char name[60]), then per line
 * touched (u64 address, u16 frames_r, u16 frames_w, u16 first_r, u16 live_in, u32 threads mask, u32 ra_live, u32 ra_w):
 * then u32 chain[3], u32 cat_r, u32 cat_w: 48 bytes, packed ("MT5"; below).
 * Races between threads on one line's counters are not locked against: a research count. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

#include "frame_hooks.h"
#include "host.h"

volatile int rt_mt_on;

int game_fight_on(void);   /* (hle_fight_test.c) */

typedef struct Line { u16 frame, last_w, frames_r, frames_w, first_r, live_in; u8 fl, pad[3]; u32 threads, ra_live, ra_w, chain[3]; u32 cat_r, cat_w; } Line;
/* cat_r: the code categories (SSBU_MEMTRACE_CATS, research/tools/code_cats.py: a bit each) that read a value the line
 * carried from an earlier frame (read before any write in this frame); cat_w: those that wrote it (first write of a
 * frame). */
static u32 (*cats)[2]; static u32 ncats;
/* The frame's phase: 1 from player 1's pad read (hle_hid.c, rt_mt_poll) to the frame end, the logic frame; 0 the
 * rest (the frame end, the submission, the next frame's render preparation). cat_r / cat_w get bit 16 for an access
 * in the logic phase by the thread that read the pad (the main thread), bit 17 in the logic phase by another
 * thread, bit 18 for one outside it. Code categories use bits 0-15. */
static volatile int mt_phase;
static volatile u32 mt_poll_thread;
#ifdef _WIN32
#define PHASE_BIT() (!mt_phase ? 1u << 18 : GetCurrentThreadId() == mt_poll_thread ? 1u << 16 : 1u << 17)
void rt_mt_poll(u32 id) { if (id == 0) { mt_poll_thread = GetCurrentThreadId(); mt_phase = 1; } }
#else
#define PHASE_BIT() (mt_phase ? 1u << 16 : 1u << 18)
void rt_mt_poll(u32 id) { if (id == 0) mt_phase = 1; }
#endif
static u32 cat_bit(u32 rel) {   /* (a per-thread cache of the last few lookups) */
    if (!ncats || rel == 0xFFFFFFFFu) return 0;
    static __declspec(thread) u32 c_rel[4], c_bit[4]; static __declspec(thread) int c_next;
    for (int k = 0; k < 4; k++) if (c_rel[k] == rel && c_bit[k]) return c_bit[k];
    u32 lo = 0, hi = ncats;
    while (lo < hi) { u32 m = (lo + hi) / 2; if (cats[m][0] <= rel) lo = m + 1; else hi = m; }
    u32 b = lo ? 1u << (cats[lo - 1][1] & 15) : 1;
    c_rel[c_next] = rel; c_bit[c_next] = b; c_next = (c_next + 1) & 3;
    return b;
}
/* ra_live / ra_w: the code that last read it first in a frame after an earlier frame's write (a state read), and that
 * last wrote it: the return address into the generated code, as an offset in ssbu.exe (its ssbu.map names the guest
 * function, f_<address>); 0xFFFFFFFF outside the program. chain: the callers of ra_live's function, from the host
 * stack (a guest call is a host call), offsets as ra_live: a generic reader (a copy, the allocator) says little alone. */
static u64 exe_base, exe_end;
#define CH_SHIFT 21
#define CH_LINES (1u << (CH_SHIFT - 6))
#define CH_COUNT (0x8000000000ull >> CH_SHIFT)
static Line *volatile *chunks;
static int mt_state = -1;   /* -1 not read, 0 off, 1 waiting, 2 tracing, 3 done */
static long long mt_from, mt_frames, fight_frames;
static volatile u16 cur;    /* the window's frame, 1..mt_frames */
static char mt_path[1024];
static volatile LONG nthreads;
static struct { u32 id; char name[60]; } thr[32];
int kernel_thread_of_host(u32 host_id, u64 *entry, u64 *id);   /* (kernel.c) */
#ifdef _WIN32
static __declspec(thread) int my_bit = -1;
#else
static __thread int my_bit = -1;
#endif

static Line *chunk(u64 a) {
    u64 id = a >> CH_SHIFT;
    if (id >= CH_COUNT) return NULL;
    Line *c = chunks[id];
    if (c) return c;
    Line *n = calloc(CH_LINES, sizeof *n);
    if (!n) return NULL;
#ifdef _WIN32
    Line *was = InterlockedCompareExchangePointer((PVOID volatile *)&chunks[id], n, NULL);
#else
    Line *was = __sync_val_compare_and_swap(&chunks[id], NULL, n);
#endif
    if (was) { free(n); return was; }
    return n;
}

static int thread_bit(void) {
    if (my_bit >= 0) return my_bit;
#ifdef _WIN32
    LONG k = InterlockedIncrement(&nthreads) - 1;
    if (k < 32) {
        thr[k].id = GetCurrentThreadId();
        PWSTR d = NULL;
        if (SUCCEEDED(GetThreadDescription(GetCurrentThread(), &d)) && d) {
            WideCharToMultiByte(CP_UTF8, 0, d, -1, thr[k].name, sizeof thr[k].name - 1, NULL, NULL);
            LocalFree(d);
        }
    }
    my_bit = k < 32 ? (int)k : 31;
#else
    my_bit = 31;
#endif
    return my_bit;
}

/* The probe (research: which bytes a getter reads): between rt_mt_probe_begin and rt_mt_probe_end, every access of
 * the calling thread is kept exactly (address, size, write) in a buffer of its own, up to PROBE_MAX. Only a build
 * with SSBU_MEMTRACE reports accesses: elsewhere a probe comes back empty. Other threads see rt_mt_on set meanwhile
 * and find no trace window (cur 0) unless one is open. */
#define PROBE_MAX 4096
typedef struct ProbeRec { u64 addr; u32 size, write; } ProbeRec;
#ifdef _WIN32
static __declspec(thread) ProbeRec *probe_buf; static __declspec(thread) u32 probe_n; static __declspec(thread) int probe_on;
#else
static __thread ProbeRec *probe_buf; static __thread u32 probe_n; static __thread int probe_on;
#endif
static volatile long probes_open;
void rt_mt_probe_begin(void) {
    if (!probe_buf) probe_buf = malloc(sizeof *probe_buf * PROBE_MAX);
    probe_n = 0; probe_on = probe_buf != NULL;
#ifdef _WIN32
    if (probe_on && InterlockedIncrement(&probes_open) == 1 && mt_state != 2) rt_mt_on = 1;
#endif
}
u32 rt_mt_probe_end(const void **recs) {
#ifdef _WIN32
    if (probe_on && InterlockedDecrement(&probes_open) == 0 && mt_state != 2) rt_mt_on = 0;
#endif
    probe_on = 0;
    *recs = probe_buf;
    return probe_n;
}
/* (research, 2026-11-12: the game checks the code reading of the modules, research/map/code_reading/modules/)
 * SSBU_WRITE_WATCH=<file>: in a build with SSBU_MEMTRACE and while its window is open, every write of the game's code
 * into a module object (or a block behind one of its first pointers) that the state dump registered (rt_ww_range) is
 * noted once per (object category, module's boma offset, block's offset in the module or 0, offset in the block,
 * size, writing code's address in the program); the list is written at the end (rt_ww_report): lines
 * "<category> <boma offset> <block offset> <offset> <size> <code rva>" (hex). */
typedef struct WwRange { u64 start; u32 len; u32 key; } WwRange;
static WwRange *ww_r, *ww_pend; static volatile long ww_n; static u32 ww_pn, ww_cap;
static u64 (*ww_tab)[2]; static int ww_on = -1;
#define WW_TAB (1u << 21)
#ifdef _WIN32
static SRWLOCK ww_lock = SRWLOCK_INIT;
#endif
static int ww_cmp(const void *a, const void *b) { const WwRange *x = a, *y = b; return x->start < y->start ? -1 : x->start > y->start; }
void rt_ww_range(u64 start, u32 len, u32 key) {
    if (ww_on < 0) ww_on = getenv("SSBU_WRITE_WATCH") != NULL;
    if (!ww_on) return;
#ifdef _WIN32
    AcquireSRWLockExclusive(&ww_lock);
    for (u32 i = 0; i < ww_pn; i++) if (ww_pend[i].start == start) { ww_pend[i].len = len; ww_pend[i].key = key; ReleaseSRWLockExclusive(&ww_lock); return; }
    if (ww_pn == ww_cap) { u32 nc = ww_cap ? ww_cap * 2 : 1024; WwRange *p = realloc(ww_pend, sizeof *p * nc); if (!p) { ReleaseSRWLockExclusive(&ww_lock); return; } ww_pend = p; ww_cap = nc; }
    ww_pend[ww_pn].start = start; ww_pend[ww_pn].len = len; ww_pend[ww_pn].key = key; ww_pn++;
    WwRange *nr = malloc(sizeof *nr * ww_pn);   /* (a new sorted copy for the readers; the old one is left: a few KB) */
    if (nr) { memcpy(nr, ww_pend, sizeof *nr * ww_pn); qsort(nr, ww_pn, sizeof *nr, ww_cmp); ww_r = nr; ww_n = (long)ww_pn; }
    if (!ww_tab) ww_tab = calloc(WW_TAB, sizeof *ww_tab);
    ReleaseSRWLockExclusive(&ww_lock);
#endif
}
static void ww_note(u64 a, u32 n, u32 rel) {
    WwRange *r = ww_r; long cnt = ww_n;
    if (!r || !cnt || a < r[0].start) return;
    long lo = 0, hi = cnt - 1;
    while (lo < hi) { long mid = (lo + hi + 1) / 2; if (r[mid].start <= a) lo = mid; else hi = mid - 1; }
    if (a - r[lo].start >= r[lo].len || !ww_tab) return;
    u64 k1 = (u64)r[lo].key << 32 | (a - r[lo].start) << 8 | (n & 0xff), k2 = rel;
    u64 h = (k1 * 0x9E3779B97F4A7C15ull) ^ (k2 * 0xC2B2AE3D27D4EB4Full);
#ifdef _WIN32
    AcquireSRWLockExclusive(&ww_lock);
    for (u32 i = 0; i < 64; i++) {
        u64 (*e)[2] = &ww_tab[(h + i) & (WW_TAB - 1)];
        if ((*e)[0] == k1 && (*e)[1] == k2) break;
        if (!(*e)[0]) { (*e)[0] = k1; (*e)[1] = k2; break; }
    }
    ReleaseSRWLockExclusive(&ww_lock);
#endif
}
void rt_ww_report(void) {
    const char *p = getenv("SSBU_WRITE_WATCH");
    if (!p || !ww_tab) return;
    FILE *f = fopen(p, "w");
    if (!f) return;
    u64 n = 0;
    for (u32 i = 0; i < WW_TAB; i++) {
        u64 k1 = ww_tab[i][0];
        if (!k1) continue;
        u32 key = (u32)(k1 >> 32);
        fprintf(f, "%x %x %x %llx %x %llx\n", key >> 28, (key >> 16) & 0xfff, key & 0xffff, (unsigned long long)((k1 >> 8) & 0xffffff), (u32)(k1 & 0xff), (unsigned long long)ww_tab[i][1]);
        n++;
    }
    fclose(f);
    fprintf(stderr, "[memtrace] SSBU_WRITE_WATCH: %llu (place, size, code) writes into %ld registered blocks: %s\n", (unsigned long long)n, ww_n, p);
}

/* ---- (research, 2026-11-13) SSBU_RF: after a load, which bytes the game reads before it writes them ------------------
 * A byte a load puts back matters only if the game reads it before writing it. From the first load of a run
 * (hle_rb_state.c, SSBU_RF) every byte the generated code touches keeps its first access since that load: 1 read
 * first, 2 written first, 3 written first then read by another thread, 0 not touched yet; bits 2-6: the thread of the
 * first access; bit 7: the byte differed from the saved state at that load. A byte of state
 * per byte of guest memory, in tables of 2 MB made on first touch. For the bytes that differed and were read first,
 * the reading code (the return address into the generated code, as an offset in ssbu.exe) is counted.
 * Only a build with SSBU_MEMTRACE reports accesses. The fight hash's own getters are left out (rt_rf_pause). */
#ifdef _WIN32
static u8 *volatile *rf_chunks;
static volatile int rf_rec;
static volatile LONG64 rf_n[4];   /* bytes read first, written first; of those that differed at the load: read first, written first */
static __declspec(thread) int rf_paused;
#define RF_READERS (1u << 16)
static struct { volatile LONG key; volatile LONG64 bytes; } *rf_readers;
void rt_rf_pause(int d) { rf_paused += d; }
static u8 *rf_chunk(u64 a, int make) {
    u64 id = a >> CH_SHIFT;
    if (!rf_chunks || id >= CH_COUNT) return NULL;
    u8 *c = rf_chunks[id];
    if (c || !make) return c;
    u8 *n = calloc(1, 1u << CH_SHIFT);
    if (!n) return NULL;
    u8 *was = InterlockedCompareExchangePointer((PVOID volatile *)&rf_chunks[id], n, NULL);
    if (was) { free(n); return was; }
    return n;
}
void rt_rf_reset(void) {
    if (!rf_chunks) rf_chunks = calloc(CH_COUNT, sizeof *rf_chunks);
    if (!rf_readers) rf_readers = calloc(RF_READERS, sizeof *rf_readers);
    if (!exe_base) {
        HMODULE m = GetModuleHandleA(NULL);
        const IMAGE_NT_HEADERS *nt = (const IMAGE_NT_HEADERS *)((const u8 *)m + ((const IMAGE_DOS_HEADER *)m)->e_lfanew);
        exe_base = (u64)(uintptr_t)m; exe_end = exe_base + nt->OptionalHeader.SizeOfImage;
    }
    for (u64 id = 0; rf_chunks && id < CH_COUNT; id++) if (rf_chunks[id]) memset(rf_chunks[id], 0, 1u << CH_SHIFT);
    if (rf_readers) memset(rf_readers, 0, sizeof *rf_readers * RF_READERS);
    for (int k = 0; k < 4; k++) rf_n[k] = 0;
}
void rt_rf_mark(u64 a, u32 n) {   /* (these bytes differ from the saved state at the load) */
    for (u32 i = 0; i < n; i++) { u8 *c = rf_chunk(a + i, 1); if (c) c[(a + i) & ((1u << CH_SHIFT) - 1)] |= 0x80; }
}
void rt_rf_record(int on) { rf_rec = on; if (on) rt_mt_on = 1; else if (mt_state != 2 && !probes_open) rt_mt_on = 0; }
const u8 *rt_rf_page(u64 g) { u8 *c = rf_chunk(g, 0); return c ? c + (g & ((1u << CH_SHIFT) - 1)) : NULL; }
void rt_rf_counts(long long out[4]) { for (int k = 0; k < 4; k++) out[k] = rf_n[k]; }
void rt_rf_report(const char *path) {
    FILE *f = path && rf_readers ? fopen(path, "w") : NULL;
    if (!f) return;
    fprintf(f, "bytes read_first %lld written_first %lld differed_read_first %lld differed_written_first %lld\n",
            (long long)rf_n[0], (long long)rf_n[1], (long long)rf_n[2], (long long)rf_n[3]);
    for (u32 i = 0; i < RF_READERS; i++) if (rf_readers[i].key) fprintf(f, "reader %x %lld\n", (u32)rf_readers[i].key, (long long)rf_readers[i].bytes);
    /* (the module objects the state dump registered, SSBU_WRITE_WATCH's ranges: each one's bytes by first access, whether
     * they differed at the load or not - "mod <key> <offset> <bytes> <first access> <1: differed>", key = category << 28 |
     * the module's offset in the accessor << 16 | the offset in the module of the pointer to a block behind it, or 0) */
    WwRange *r = ww_r; long cnt = ww_n;
    for (long i = 0; r && i < cnt; i++) {
        u32 from = 0; int cur_c = -1;
        for (u32 o = 0; o <= r[i].len; o++) {
            int cl = -1;
            if (o < r[i].len) { const u8 *c = rf_chunk(r[i].start + o, 0); u8 v = c ? c[(r[i].start + o) & ((1u << CH_SHIFT) - 1)] : 0; cl = (v & 3) | (v >> 7) << 2; }
            if (cl != cur_c) {
                if (cur_c > 0) fprintf(f, "mod %x %x %x %d %d\n", r[i].key, from, o - from, cur_c & 3, cur_c >> 2);
                cur_c = cl; from = o;
            }
        }
    }
    fclose(f);
}
static void rf_access(u64 a, u32 n, int write, u32 rel) {
    u32 got = 0, gotd = 0, me = (u32)thread_bit() & 31;
    for (u32 i = 0; i < n; i++) {
        u8 *c = rf_chunk(a + i, 1);
        if (!c) return;
        u8 *s = &c[(a + i) & ((1u << CH_SHIFT) - 1)], v = *s;
        if (v & 3) {
            /* (a byte one thread wrote first and another thread then reads is 3, "handed over": which of the two comes
             * first is a race between threads, and the next run may read before the write - the hangs of the first
             * trials, where every family passed alone and their union hung one time in two) */
            if ((v & 3) == 2 && !write && ((v >> 2) & 31) != me) *s = v | 3;
            continue;
        }
        *s = v | (write ? 2 : 1) | (u8)(me << 2);
        got++; gotd += v >> 7;
    }
    if (got) InterlockedAdd64(&rf_n[write ? 1 : 0], got);
    if (gotd) {
        InterlockedAdd64(&rf_n[write ? 3 : 2], gotd);
        if (!write && rf_readers) {
            LONG key = rel ? (LONG)rel : 1;
            for (u32 h = rel * 2654435761u >> 16, k = 0; k < 256; k++) {
                u32 e = (h + k) & (RF_READERS - 1);
                LONG was = rf_readers[e].key;
                if (!was) was = InterlockedCompareExchange(&rf_readers[e].key, key, 0);
                if (!was || was == key) { InterlockedAdd64(&rf_readers[e].bytes, gotd); break; }
            }
        }
    }
}
/* (the runtime's own accesses for the game are not in the trace: the native libc, hle_libc.c, and the pad state,
 * hle_hid.c, report theirs here; the reading code is then 0xFFFFFFFE) */
static void lv_access(u64 a, u32 n, int write);
static volatile int lv_state;
void rt_rf_native(u64 a, u64 n, int write) {
    if (lv_state == 2 && !rf_paused) { u64 x = a, m = n; while (m) { u32 k = m > 0x10000 ? 0x10000 : (u32)m; lv_access(x, k, write); x += k; m -= k; } }
    if (!rf_rec || rf_paused) return;
    while (n) { u32 k = n > 0x10000 ? 0x10000 : (u32)n; rf_access(a, k, write, 0xFFFFFFFEu); a += k; n -= k; }
}
#else
void rt_rf_pause(int d) { (void)d; }
void rt_rf_native(u64 a, u64 n, int write) { (void)a; (void)n; (void)write; }
#endif

/* ---- (research, 2026-11-13 afternoon) SSBU_LIVE: which bytes carry state across a frame's boundary -----------------
 * SSBU_LIVE=<first fight frame>,<last fight frame>,<file> (a build with SSBU_MEMTRACE, SSBU_RB=1 and the blocks' table
 * on, e.g. SSBU_RB_UNITS_DIFF): no load is made. A load puts memory back as it was at a rollback safe point (one a
 * frame, hle_rb_core.c); a byte matters to that load if the next access after the safe point is a read. So between two
 * safe points every byte keeps its first access (cur: 1 read, 2 written, the thread in bits 2-6; cleared at each safe
 * point for the pages touched), and over the block's life (acc):
 *   LV_L 1  read first after some safe point: it carried a value across that boundary;
 *   LV_D 2  written first after some safe point: dead at that boundary;
 *   LV_H 4  written first, then read by another thread before the next safe point (which comes first is a race);
 *   LV_W 8  written at all (a byte read and never written is a constant: a load never changes it).
 * One fight of N frames is N load points. When a block is freed (hle_rb_state.c, the blocks' table) and for every live
 * block at the end, its bytes' marks are added to its place's: (allocation site, block size) -> a byte of marks per
 * offset. The file: "site <ra1> <ra2> <size> <blocks>" then "r <offset> <bytes> <marks>" runs; "rest <address> <bytes>
 * <marks>" for bytes in no block; "mod <key> <offset> <bytes> <marks>" for the module objects the state dump
 * registered (SSBU_WRITE_WATCH's ranges), as they are at the end. */
#ifdef _WIN32
#define LV_L 1
#define LV_D 2
#define LV_H 4
#define LV_W 8
static u8 *volatile *lv_cur, *volatile *lv_acc, *volatile *lv_pg;   /* (lv_pg[id]: 512 bytes of "touched since the safe point", then 512 of the page's marks for the whole window: 1 a carried byte, 2 a handed-over byte, 4 written) */
/* (lv_state, declared above: 0 off, 1 waiting, 2 on, 3 done) */
static long long lv_from, lv_to, lv_intervals;
static char lv_path[1024];
static u32 *lv_ids; static volatile LONG lv_nids;   /* the chunks made, for the boundary's sweep */
#define LV_IDS (1u << 16)
static SRWLOCK lv_lock = SRWLOCK_INIT;
typedef struct LvAgg { u64 ra1, ra2, size; u8 *f; u32 n; } LvAgg;
#define LV_AGG (1u << 18)
static LvAgg *lv_agg;
static int lv_chunk(u64 id, u8 **cur, u8 **acc, u8 **pg, int make) {
    if (id >= CH_COUNT) return 0;
    u8 *c = lv_cur[id];
    if (!c) {
        if (!make) return 0;
        AcquireSRWLockExclusive(&lv_lock);
        if (!lv_cur[id]) {
            u8 *a = calloc(1, 1u << CH_SHIFT), *b = calloc(1, 1u << CH_SHIFT), *p = calloc(1, 1024);
            if (a && b && p && lv_nids < (LONG)LV_IDS) { lv_acc[id] = b; lv_pg[id] = p; lv_ids[lv_nids] = (u32)id; lv_nids++; lv_cur[id] = a; }
            else { free(a); free(b); free(p); }
        }
        ReleaseSRWLockExclusive(&lv_lock);
        c = lv_cur[id];
        if (!c) return 0;
    }
    *cur = c; *acc = lv_acc[id]; *pg = lv_pg[id];
    return 1;
}
static void lv_tripwire(u64 g);
static u64 lv_dbg_lo, lv_dbg_hi; static volatile LONG lv_dbg_n;   /* (SSBU_LIVE_DEBUG=<key>,<offset>,<bytes>, hex: the accesses to those bytes of the first module object registered under the key) */
static void lv_access(u64 a, u32 n, int write) {
    u32 me = (u32)thread_bit() & 31;
    if (lv_dbg_hi && a < lv_dbg_hi && a + n > lv_dbg_lo && InterlockedIncrement(&lv_dbg_n) < 400) {
        void *bt[8] = {0};
        USHORT got = RtlCaptureStackBackTrace(1, 6, bt, NULL);
        char t[200]; int k = 0;
        for (USHORT q = 0; q < got && k < 180; q++) { u64 r = (u64)(uintptr_t)bt[q]; k += snprintf(t + k, sizeof t - (size_t)k, " %llx", r >= exe_base && r < exe_end ? (unsigned long long)(r - exe_base) : 0ull); }
        fprintf(stderr, "[lvdbg] interval %lld thread %u %s +%llx %u bytes; code%s" "\n", lv_intervals, me, write ? "W" : "r", (unsigned long long)(a - lv_dbg_lo), n, t);
    }
    u8 *cur = NULL, *acc = NULL, *pg = NULL; u64 have = ~0ull;
    for (u32 i = 0; i < n; i++) {
        u64 g = a + i, id = g >> CH_SHIFT;
        if (id != have) { if (!lv_chunk(id, &cur, &acc, &pg, 1)) return; have = id; }
        u32 o = (u32)(g & ((1u << CH_SHIFT) - 1));
        u8 c = cur[o];
        if (!(c & 3)) {
            if ((c & 0x80) && !write) lv_tripwire(g);   /* (SSBU_POISON with SSBU_LIVE: a poisoned byte read before any write) */
            cur[o] = (u8)((write ? 2 : 1) | me << 2);
            u8 f = write ? (LV_D | LV_W) : LV_L;
            if ((acc[o] & f) != f) acc[o] |= f;
            if (!pg[o >> 12]) pg[o >> 12] = 1;
        } else if (write) { if (!(acc[o] & LV_W)) acc[o] |= LV_W; }
        else if ((c & 3) == 2 && ((u32)(c >> 2) & 31) != me && !(acc[o] & LV_H)) acc[o] |= LV_H;
        {   u8 m = acc[o], pf = (u8)(((m & (LV_L | LV_W)) == (LV_L | LV_W) ? 1 : 0) | (m & LV_H ? 2 : 0) | (m & LV_W ? 4 : 0));
            if ((pg[512 + (o >> 12)] & pf) != pf) pg[512 + (o >> 12)] |= pf; }
    }
}
/* the marks of [lo, hi), bytes of a block of (ra1, ra2, size) from its offset off0 on, added to the place's and cleared */
void rt_lv_flush(u64 lo, u64 hi, u64 ra1, u64 ra2, u64 size, u64 off0) {
    if (lv_state != 2 || !lv_agg || hi <= lo) return;
    LvAgg *e = NULL;
    for (u64 g = lo; g < hi;) {
        u64 id = g >> CH_SHIFT, end = (id + 1) << CH_SHIFT;
        if (end > hi) end = hi;
        u8 *cur, *acc, *pg;
        if (!lv_chunk(id, &cur, &acc, &pg, 0)) { g = end; continue; }
        for (; g < end; g++) {
            u32 o = (u32)(g & ((1u << CH_SHIFT) - 1));
            u8 f = acc[o];
            cur[o] = 0;
            if (!f) continue;
            acc[o] = 0;
            if (!e) {
                AcquireSRWLockExclusive(&lv_lock);
                u64 h = (ra1 * 0x9E3779B97F4A7C15ull) ^ (ra2 * 0xC2B2AE3D27D4EB4Full) ^ (size * 0x165667B19E3779F9ull);
                for (u32 k = 0; k < LV_AGG; k++) {
                    LvAgg *x = &lv_agg[(h + k) & (LV_AGG - 1)];
                    if (!x->size) { x->ra1 = ra1; x->ra2 = ra2; x->size = size; x->f = calloc(1, (size_t)size); }
                    if (x->ra1 == ra1 && x->ra2 == ra2 && x->size == size) { e = x; break; }
                }
                ReleaseSRWLockExclusive(&lv_lock);
                if (!e || !e->f) return;
            }
            u64 off = off0 + (g - lo);
            if (off < size) e->f[off] |= f;
        }
    }
    if (e) InterlockedIncrement((volatile LONG *)&e->n);
}
int rt_lv_on(void) { return lv_state == 2; }
/* (kernel.c: guest memory [at, at + size) committed, 'C', or decommitted, 'D': the game's MapPhysicalMemory and
 * UnmapPhysicalMemory. A save copies such pages whole, hle_rb_state.c; counted here by range, with the safe point) */
#define LV_CHURN 4096
static struct { u64 at, size; u32 commits, decommits; long long first, last; } lv_churn[LV_CHURN];
static u32 lv_nchurn; static u64 lv_churn_pages[2];
void rt_lv_memnote(u64 at, u64 size, int kind) {
    if (lv_state != 2) return;
    AcquireSRWLockExclusive(&lv_lock);
    u32 i = 0;
    while (i < lv_nchurn && !(lv_churn[i].at == at && lv_churn[i].size == size)) i++;
    if (i == lv_nchurn && lv_nchurn < LV_CHURN) { lv_churn[i].at = at; lv_churn[i].size = size; lv_churn[i].first = lv_intervals; lv_nchurn++; }
    if (i < lv_nchurn) { if (kind == 'C') lv_churn[i].commits++; else lv_churn[i].decommits++; lv_churn[i].last = lv_intervals; }
    lv_churn_pages[kind == 'C' ? 0 : 1] += size >> 12;
    ReleaseSRWLockExclusive(&lv_lock);
}
void rb_lv_finish(FILE *f);   /* (hle_rb_state.c: every live block's marks added to their places; the bytes in no block written) */
void rt_lv_rest(FILE *f, u64 lo, u64 hi) {   /* (bytes in no block: their marks as they are) */
    for (LONG k = 0; k < lv_nids; k++) {
        u64 base = (u64)lv_ids[k] << CH_SHIFT, a = base > lo ? base : lo, b = base + (1u << CH_SHIFT) < hi ? base + (1u << CH_SHIFT) : hi;
        if (a >= b) continue;
        u8 *acc = lv_acc[lv_ids[k]];
        u64 from = a; int cf = 0;
        for (u64 g = a; g <= b; g++) {
            int fl = g < b ? acc[g - base] : 0;
            if (fl != cf) { if (cf) fprintf(f, "rest %llx %llx %x\n", (unsigned long long)from, (unsigned long long)(g - from), cf); cf = fl; from = g; }
        }
    }
}

/* ---- (research, 2026-11-13 night) the battle objects by module class ------------------------------------------------
 * A field is the same thing in every object whose module has the same class: (the module's vptr, offset). So the
 * tracker's marks are also added up by vptr, for every battle object in the battle object manager's pools (the
 * fighters', the weapons', ...: blocks allocated from 0x71014f3000-0x71014f6000, hle_rb_state.c's table). At each safe
 * point the pools are scanned for module accessors by their shape (a vptr in main's data, the object id at +8 with
 * nothing above it, modules at +0x38, +0x40, +0x50), as hle_state_dump.c's scan does. A new object's modules are
 * taken from its accessor (each pointer to an object whose first word is a vptr in main's data); when an object is
 * gone or its id changed, its modules' marks go to their classes and are cleared, so the next object in that memory
 * starts clean. A class's size comes from SSBU_LIVE_CLASSES=<file of "vptr size" lines, hex> (research/map/
 * module_sizes.json); a class not in it is taken up to the next module of the same object, 0x900 at most.
 * In the file: "class <vptr> <category> <offset in the accessor> <objects> <size> <1: size known>", then "r" runs. */
typedef struct LoMod { u64 m, vptr; u32 o, size, known; } LoMod;
typedef struct LoObj { u64 boma; u32 id, nm; int seen; LoMod mod[100]; } LoObj;
typedef struct LoClass { u64 vptr; u32 cat, o, objects, size, known; u8 f[0x900]; } LoClass;
#define LO_OBJS 4096
#define LO_CLASSES 1024
static LoObj *lo_obj; static u32 lo_nobj;
static LoClass *lo_cls; static u32 lo_ncls;
static struct { u64 vptr; u32 size; } lo_sz[512]; static u32 lo_nsz;
static u64 lo_pools[64][2]; static u32 lo_npools; static long long lo_pool_at = -100000;
static unsigned long long lo_seen_objects, lo_scan_us;
u32 rb_pool_blocks(u64 (*out)[2], u32 max);   /* (hle_rb_state.c) */
static void lo_flush(LoObj *ob, int clear) {
    for (u32 i = 0; i < ob->nm; i++) {
        LoMod *md = &ob->mod[i];
        LoClass *c = NULL;
        for (u32 k = 0; k < lo_ncls; k++) if (lo_cls[k].vptr == md->vptr) { c = &lo_cls[k]; break; }
        if (!c) {
            if (lo_ncls == LO_CLASSES) continue;
            c = &lo_cls[lo_ncls++];
            memset(c, 0, sizeof *c);
            c->vptr = md->vptr; c->cat = ob->id >> 28; c->o = md->o; c->size = md->size; c->known = md->known;
        }
        if (md->size < c->size) c->size = md->size;   /* (a class of unknown size: the shortest extent seen) */
        c->objects++;
        for (u32 q = 0; q < md->size && q < 0x900; q++) {
            u8 *cur, *acc, *pg; u64 g = md->m + q;
            if (!lv_chunk(g >> CH_SHIFT, &cur, &acc, &pg, 0)) continue;
            u32 o = (u32)(g & ((1u << CH_SHIFT) - 1));
            c->f[q] |= acc[o];
            if (clear) { acc[o] = 0; cur[o] = 0; }
        }
    }
}
static void lo_scan(long long fight_frame) {
    int kernel_read64(u64 a, u64 *v);
    if (!lo_obj) {
        lo_obj = calloc(LO_OBJS, sizeof *lo_obj); lo_cls = calloc(LO_CLASSES, sizeof *lo_cls);
        const char *e = getenv("SSBU_LIVE_CLASSES");
        FILE *f = e ? fopen(e, "r") : NULL;
        unsigned long long v; unsigned sz;
        while (f && lo_nsz < 512 && fscanf(f, "%llx %x", &v, &sz) == 2) { lo_sz[lo_nsz].vptr = v; lo_sz[lo_nsz].size = sz; lo_nsz++; }
        if (f) fclose(f);
    }
    if (!lo_obj || !lo_cls) return;
    if (fight_frame - lo_pool_at >= 300) { lo_npools = rb_pool_blocks(lo_pools, 64); lo_pool_at = fight_frame; }
    LARGE_INTEGER q0, q1, fq; QueryPerformanceCounter(&q0);
    for (u32 i = 0; i < lo_nobj; i++) lo_obj[i].seen = 0;
    for (u32 pi = 0; pi < lo_npools; pi++) {
        u64 lo_a = lo_pools[pi][0], hi_a = lo_a + lo_pools[pi][1];
        for (u64 p = (lo_a + 7) & ~7ull; p + 0x400 <= hi_a; p += 8) {
            u64 v = *(const u64 *)RT_HOST(p);
            if (v < 0x7104f17000ull || v >= 0x71052aa000ull || (v & 7)) continue;
            u64 idw = *(const u64 *)RT_HOST(p + 8);
            u32 id = (u32)idw;
            if (idw >> 32 || id >> 28 > 4) continue;
            int ok = 1;
            static const u32 mo[3] = {0x38, 0x40, 0x50};
            for (u32 q = 0; q < 3 && ok; q++) {
                u64 mp = *(const u64 *)RT_HOST(p + mo[q]), mv = 0;
                ok = mp >= 0x6000000000ull && mp < 0x7000000000ull && !(mp & 7) && kernel_read64(mp, &mv) && mv >= 0x7104000000ull && mv < 0x7106000000ull && !(mv & 7);
            }
            if (!ok) continue;
            LoObj *ob = NULL;
            for (u32 i = 0; i < lo_nobj; i++) if (lo_obj[i].boma == p) { ob = &lo_obj[i]; break; }
            if (ob && ob->id == id) { ob->seen = 1; p += 0x3f8; continue; }
            if (ob) lo_flush(ob, 1);
            else if (lo_nobj < LO_OBJS) ob = &lo_obj[lo_nobj++];
            else continue;
            ob->boma = p; ob->id = id; ob->nm = 0; ob->seen = 1;
            lo_seen_objects++;
            for (u32 o = 0x10; o < 0x400 && ob->nm < 100; o += 8) {
                u64 m = *(const u64 *)RT_HOST(p + o), vp = 0;
                if (m < 0x6000000000ull || m >= 0x7000000000ull || (m & 7) || m == p || !kernel_read64(m, &vp)) continue;
                if (vp < 0x7104000000ull || vp >= 0x7106000000ull || (vp & 7)) continue;
                int dup = 0;
                for (u32 k = 0; k < ob->nm; k++) dup |= ob->mod[k].m == m;
                if (dup) continue;
                LoMod *md = &ob->mod[ob->nm++];
                md->m = m; md->vptr = vp; md->o = o; md->size = 0x900; md->known = 0;
                for (u32 k = 0; k < lo_nsz; k++) if (lo_sz[k].vptr == vp) { md->size = lo_sz[k].size; md->known = 1; break; }
            }
            for (u32 a = 0; a < ob->nm; a++)   /* (an unknown class: up to the next module of this object) */
                if (!ob->mod[a].known)
                    for (u32 b = 0; b < ob->nm; b++)
                        if (ob->mod[b].m > ob->mod[a].m && ob->mod[b].m - ob->mod[a].m < ob->mod[a].size) ob->mod[a].size = (u32)(ob->mod[b].m - ob->mod[a].m);
            p += 0x3f8;
        }
    }
    for (u32 i = 0; i < lo_nobj;) {
        if (lo_obj[i].seen) { i++; continue; }
        lo_flush(&lo_obj[i], 1);
        lo_obj[i] = lo_obj[--lo_nobj];
    }
    QueryPerformanceCounter(&q1); QueryPerformanceFrequency(&fq);
    lo_scan_us += (unsigned long long)((q1.QuadPart - q0.QuadPart) * 1000000 / fq.QuadPart);
}
static void lo_write(FILE *f) {
    if (!lo_obj) return;
    for (u32 i = 0; i < lo_nobj; i++) lo_flush(&lo_obj[i], 0);
    for (u32 k = 0; k < lo_ncls; k++) {
        LoClass *c = &lo_cls[k];
        fprintf(f, "class %llx %u %x %u %x %u\n", (unsigned long long)c->vptr, c->cat, c->o, c->objects, c->size, c->known);
        u32 from = 0; int cf = 0;
        for (u32 q = 0; q <= c->size && q <= 0x900; q++) {
            int fl = q < c->size && q < 0x900 ? c->f[q] : 0;
            if (fl != cf) { if (cf) fprintf(f, "r %x %x %x\n", from, q - from, cf); cf = fl; from = q; }
        }
    }
    fprintf(stderr, "[memtrace] SSBU_LIVE: battle objects by class: %llu objects seen in %u pools, %u live at the end, %u module classes; the scan %.2f ms a safe point\n",
            lo_seen_objects, lo_npools, lo_nobj, lo_ncls, lv_intervals ? (double)lo_scan_us / 1000.0 / (double)lv_intervals : 0.0);
}
static void lv_write(void) {
    FILE *f = fopen(lv_path, "w");
    if (!f) { fprintf(stderr, "[memtrace] SSBU_LIVE: cannot write %s\n", lv_path); return; }
    fprintf(f, "live %lld %lld %lld\n", lv_from, lv_to, lv_intervals);
    WwRange *r = ww_r; long cnt = ww_n;   /* (the module objects, before the blocks' marks are taken) */
    for (long i = 0; r && i < cnt; i++) {
        u32 from = 0; int cf = 0;
        for (u32 o = 0; o <= r[i].len; o++) {
            int fl = 0;
            if (o < r[i].len) { u8 *cur, *acc, *pg; u64 g = r[i].start + o; if (lv_chunk(g >> CH_SHIFT, &cur, &acc, &pg, 0)) fl = acc[g & ((1u << CH_SHIFT) - 1)]; }
            if (fl != cf) { if (cf) fprintf(f, "mod %x %x %x %x %llx\n", r[i].key, from, o - from, cf, (unsigned long long)r[i].start); cf = fl; from = o; }
        }
    }
    {   /* the pages written in the window (what a save copies), by what their bytes are: with a carried byte (read first
         * after some safe point, and written), else with a handed-over byte, else dead (every written byte written
         * before read at every safe point); the GPU's memory (nvmap allocations, hle_nv.c) apart */
        u32 nv_rb_maps(u64 (*out)[2], u32 max);
        static u64 maps[4096][2];
        u32 nm = nv_rb_maps(maps, 4096);
        u64 n[2][4] = {{0}};
        for (LONG k = 0; k < lv_nids; k++) {
            u8 *acc = lv_acc[lv_ids[k]];
            u64 base = (u64)lv_ids[k] << CH_SHIFT;
            for (u32 p = 0; p < 512; p++) {
                int w = 0, c = 0, h = 0;
                for (u32 o = 0; o < 0x1000; o++) { u8 m = acc[(p << 12) + o]; if (m & LV_W) { w = 1; if (m & LV_L) c = 1; if (m & LV_H) h = 1; } }
                if (!w) continue;
                u64 g = base + ((u64)p << 12); int gpu = 0;
                for (u32 i = 0; i < nm && !gpu; i++) gpu = g >= maps[i][0] && g < maps[i][0] + maps[i][1];   /* (address, size) */
                n[gpu][0]++; n[gpu][c ? 1 : h ? 2 : 3]++;
            }
        }
        fprintf(f, "pages %llu %llu %llu %llu gpu %llu %llu %llu %llu\n", (unsigned long long)n[0][0], (unsigned long long)n[0][1], (unsigned long long)n[0][2], (unsigned long long)n[0][3],
                (unsigned long long)n[1][0], (unsigned long long)n[1][1], (unsigned long long)n[1][2], (unsigned long long)n[1][3]);
        fprintf(stderr, "[memtrace] SSBU_LIVE: pages written: %llu not the GPU's (%llu with a carried byte, %llu handed over only, %llu dead), %llu the GPU's (%llu, %llu, %llu); %u nvmap ranges\n",
                (unsigned long long)n[0][0], (unsigned long long)n[0][1], (unsigned long long)n[0][2], (unsigned long long)n[0][3],
                (unsigned long long)n[1][0], (unsigned long long)n[1][1], (unsigned long long)n[1][2], (unsigned long long)n[1][3], nm);
    }
    {   /* the same count from the pages' marks of the whole window (a block freed in the fight has given its bytes' marks to
         * its place by now; the page keeps its own), and the memory given back and taken again */
        u32 nv_rb_maps(u64 (*out)[2], u32 max);
        static u64 maps2[4096][2];
        u32 nm = nv_rb_maps(maps2, 4096);
        u64 n[2][4] = {{0}};
        for (LONG k = 0; k < lv_nids; k++) {
            u8 *pg = lv_pg[lv_ids[k]];
            u64 base = (u64)lv_ids[k] << CH_SHIFT;
            for (u32 p = 0; p < 512; p++) {
                u8 pf = pg[512 + p];
                if (!(pf & 4)) continue;
                u64 g = base + ((u64)p << 12); int gpu = 0;
                for (u32 i = 0; i < nm && !gpu; i++) gpu = g >= maps2[i][0] && g < maps2[i][0] + maps2[i][1];
                n[gpu][0]++; n[gpu][pf & 1 ? 1 : pf & 2 ? 2 : 3]++;
            }
        }
        fprintf(f, "pages_window %llu %llu %llu %llu gpu %llu %llu %llu %llu\n", (unsigned long long)n[0][0], (unsigned long long)n[0][1], (unsigned long long)n[0][2], (unsigned long long)n[0][3],
                (unsigned long long)n[1][0], (unsigned long long)n[1][1], (unsigned long long)n[1][2], (unsigned long long)n[1][3]);
        fprintf(stderr, "[memtrace] SSBU_LIVE: pages written in the whole window: %llu not the GPU's (%llu with a carried byte, %llu handed over only, %llu dead), %llu the GPU's (%llu, %llu, %llu)\n",
                (unsigned long long)n[0][0], (unsigned long long)n[0][1], (unsigned long long)n[0][2], (unsigned long long)n[0][3],
                (unsigned long long)n[1][0], (unsigned long long)n[1][1], (unsigned long long)n[1][2], (unsigned long long)n[1][3]);
        u64 tot[5] = {0}; u32 often = 0;
        for (u32 i = 0; i < lv_nchurn; i++) {
            u64 c[4] = {0};   /* pages: all, written, with a carried byte, handed over only */
            for (u64 g = lv_churn[i].at & ~0xFFFull; g < lv_churn[i].at + lv_churn[i].size; g += 0x1000) {
                u8 *cur, *acc, *pg;
                c[0]++;
                if (!lv_chunk(g >> CH_SHIFT, &cur, &acc, &pg, 0)) continue;
                u8 pf = pg[512 + ((g & ((1u << CH_SHIFT) - 1)) >> 12)];
                if (pf & 4) c[1]++;
                if (pf & 1) c[2]++; else if (pf & 2) c[3]++;
            }
            fprintf(f, "churn %llx %llx %u %u %lld %lld %llu %llu %llu %llu\n", (unsigned long long)lv_churn[i].at, (unsigned long long)lv_churn[i].size, lv_churn[i].commits, lv_churn[i].decommits,
                    lv_churn[i].first, lv_churn[i].last, (unsigned long long)c[0], (unsigned long long)c[1], (unsigned long long)c[2], (unsigned long long)c[3]);
            if (lv_churn[i].commits + lv_churn[i].decommits >= 20) { often++; for (int q = 0; q < 4; q++) tot[q] += c[q]; }
        }
        fprintf(stderr, "[memtrace] SSBU_LIVE: memory given back and taken again: %u ranges, %llu pages committed and %llu decommitted in %lld frames; the %u ranges that move 20 times or more: "
                "%llu pages, %llu written by the game's code, %llu with a carried byte, %llu handed over only\n", lv_nchurn, (unsigned long long)lv_churn_pages[0], (unsigned long long)lv_churn_pages[1],
                lv_intervals, often, (unsigned long long)tot[0], (unsigned long long)tot[1], (unsigned long long)tot[2], (unsigned long long)tot[3]);
    }
    lo_write(f);   /* (the battle objects' marks by module class, before the blocks' marks are taken) */
    rb_lv_finish(f);
    u64 places = 0;
    for (u32 k = 0; k < LV_AGG; k++) {
        LvAgg *e = &lv_agg[k];
        if (!e->size || !e->f) continue;
        fprintf(f, "site %llx %llx %llx %u\n", (unsigned long long)e->ra1, (unsigned long long)e->ra2, (unsigned long long)e->size, e->n);
        u64 from = 0; int cf = 0;
        for (u64 o = 0; o <= e->size; o++) {
            int fl = o < e->size ? e->f[o] : 0;
            if (fl != cf) { if (cf) fprintf(f, "r %llx %llx %x\n", (unsigned long long)from, (unsigned long long)(o - from), cf); cf = fl; from = o; }
        }
        places++;
    }
    fclose(f);
    fprintf(stderr, "[memtrace] SSBU_LIVE: %lld safe points, %llu places (site, block size), %ld tables of 2 MB: %s\n", lv_intervals, (unsigned long long)places, (long)lv_nids, lv_path);
}
/* ---- (research, 2026-11-13 night) the live battle objects' modules, for the poison and the digest by class ---------
 * "classfield <vptr> <offset> <length>" lines (hex) name bytes of every module object whose class has that vptr, in
 * every battle object of the pools (fighters, weapons...): found at each safe point by the scan the tracker uses
 * (lo_scan above; needs the blocks' table, e.g. SSBU_RB_UNITS_DIFF, for the pools). */
typedef struct BoMod { u64 m, vptr; u32 id, o; } BoMod;
#define BO_MAX 16384
static BoMod *bo_mod; static u32 bo_n; static long long bo_frame = -1, bo_pool_at = -100000;
static u64 bo_pools[64][2]; static u32 bo_npools;
static int bo_cmp(const void *a, const void *b) { const BoMod *x = a, *y = b; return x->id != y->id ? (x->id < y->id ? -1 : 1) : x->o < y->o ? -1 : x->o > y->o; }
static void bo_scan(long long fight_frame) {
    int kernel_read64(u64 a, u64 *v);
    u32 rb_pool_blocks(u64 (*out)[2], u32 max);
    if (bo_frame == fight_frame) return;
    bo_frame = fight_frame;
    if (!bo_mod && !(bo_mod = malloc(sizeof *bo_mod * BO_MAX))) return;
    if (fight_frame - bo_pool_at >= 300) { bo_npools = rb_pool_blocks(bo_pools, 64); bo_pool_at = fight_frame; }
    bo_n = 0;
    for (u32 pi = 0; pi < bo_npools; pi++) {
        u64 lo_a = bo_pools[pi][0], hi_a = lo_a + bo_pools[pi][1];
        for (u64 p = (lo_a + 7) & ~7ull; p + 0x400 <= hi_a; p += 8) {
            u64 v = *(const u64 *)RT_HOST(p);
            if (v < 0x7104f17000ull || v >= 0x71052aa000ull || (v & 7)) continue;
            u64 idw = *(const u64 *)RT_HOST(p + 8);
            u32 id = (u32)idw;
            if (idw >> 32 || id >> 28 > 4) continue;
            int ok = 1;
            static const u32 mo[3] = {0x38, 0x40, 0x50};
            for (u32 q = 0; q < 3 && ok; q++) {
                u64 mp = *(const u64 *)RT_HOST(p + mo[q]), mv = 0;
                ok = mp >= 0x6000000000ull && mp < 0x7000000000ull && !(mp & 7) && kernel_read64(mp, &mv) && mv >= 0x7104000000ull && mv < 0x7106000000ull && !(mv & 7);
            }
            if (!ok) continue;
            u32 first = bo_n;
            for (u32 o = 0x10; o < 0x400 && bo_n < BO_MAX; o += 8) {
                u64 m = *(const u64 *)RT_HOST(p + o), vp = 0;
                if (m < 0x6000000000ull || m >= 0x7000000000ull || (m & 7) || m == p || !kernel_read64(m, &vp)) continue;
                if (vp < 0x7104000000ull || vp >= 0x7106000000ull || (vp & 7)) continue;
                int dup = 0;
                for (u32 k = first; k < bo_n; k++) dup |= bo_mod[k].m == m;
                if (dup) continue;
                bo_mod[bo_n].m = m; bo_mod[bo_n].vptr = vp; bo_mod[bo_n].id = id; bo_mod[bo_n].o = o; bo_n++;
            }
            p += 0x3f8;
        }
    }
    if (bo_n) qsort(bo_mod, bo_n, sizeof *bo_mod, bo_cmp);
}
typedef struct BoField { u64 vptr; u32 off, len; } BoField;
static int bof_cmp(const void *a, const void *b) { const BoField *x = a, *y = b; return x->vptr != y->vptr ? (x->vptr < y->vptr ? -1 : 1) : x->off < y->off ? -1 : x->off > y->off; }
static u32 bof_first(const BoField *f, u32 n, u64 vptr) {   /* the first field of the class, or n */
    u32 lo = 0, hi = n;
    while (lo < hi) { u32 m = (lo + hi) / 2; if (f[m].vptr < vptr) lo = m + 1; else hi = m; }
    return lo;
}
static u32 bof_load(const char *path, BoField **out) {
    FILE *f = fopen(path, "r");
    char line[256]; unsigned long long v; unsigned b, c; u32 n = 0, cap = 0;
    while (f && fgets(line, sizeof line, f))
        if (sscanf(line, "classfield %llx %x %x", &v, &b, &c) == 3) {
            if (n == cap) *out = realloc(*out, sizeof **out * (cap = cap ? cap * 2 : 1024));
            (*out)[n].vptr = v; (*out)[n].off = b; (*out)[n].len = c; n++;
        }
    if (f) fclose(f);
    if (n) qsort(*out, n, sizeof **out, bof_cmp);
    return n;
}

/* ---- (research, 2026-11-13 evening) SSBU_POISON: the judge by poison -------------------------------------------------
 * SSBU_POISON=<file>[,<seed>[,<first fight frame>]]: at every rollback safe point of a fight (hle_rb_core.c, from the
 * given frame, default 300), the bytes the file names are overwritten with a value that cannot pass for a real one
 * (every byte 0xC1..0xFE, by seed and frame: no valid pointer, no small integer, no 0 or 1). The claim under test is
 * "after every safe point these bytes are written before they are read": if it holds the fight is the same as with
 * no poison, at every frame of the fight and with no load at all; if one of them is read first, it reads poison, not
 * a slightly old value. Lines of the file: "modfield <offset in the accessor> <offset in the module> <length>" (hex):
 * that field of every fighter's module (the accessors the frame line has seen, hle_fight_test.c). Any build. The
 * other threads are not held while the bytes are written (a save holds them): a verdict is to be repeated. */
static struct { u32 o, off, len; } *po_f; static u32 po_n; static int po_state = -1; static u32 po_seed; static long long po_from = 300;
static BoField *po_c; static u32 po_nc;   /* ("classfield" lines: by module class, in every battle object of the pools) */
static long long po_frame;
/* (trace build, SSBU_POISON with SSBU_LIVE) the game read a poisoned byte before writing it: which field of which
 * fighter, at which fight frame, from which code (the first 300 are printed; all are counted by field at the end) */
static void lv_tripwire(u64 g) {
    static volatile LONG n;
    if (InterlockedIncrement(&n) > 300) return;
    u64 fight_test_boma(int k); int kernel_read64(u64 a, u64 *v);
    int fk = -1; u32 fo = 0, foff = 0;
    for (int k = 0; k < 8 && fk < 0; k++) {
        u64 bo = fight_test_boma(k);
        if (!bo) break;
        for (u32 i = 0; i < po_n; i++) {
            u64 m = 0;
            if (kernel_read64(bo + po_f[i].o, &m) && g >= m + po_f[i].off && g < m + po_f[i].off + po_f[i].len) { fk = k; fo = po_f[i].o; foff = (u32)(g - m); break; }
        }
    }
    void *bt[8] = {0};
    USHORT got = RtlCaptureStackBackTrace(2, 5, bt, NULL);
    char t[160]; int k2 = 0;
    for (USHORT q = 0; q < got && k2 < 140; q++) { u64 r = (u64)(uintptr_t)bt[q]; k2 += snprintf(t + k2, sizeof t - (size_t)k2, " %llx", r >= exe_base && r < exe_end ? (unsigned long long)(r - exe_base) : 0ull); }
    fprintf(stderr, "[poison] TRIPWIRE: fight frame %lld, fighter %d, accessor +%#x, module +%#x read before written; code%s\n", po_frame, fk, fo, foff, t);
}
void rt_poison_boundary(long long fight_frame) {
    if (po_state < 0) {
        const char *e = getenv("SSBU_POISON");
        po_state = 0;
        if (e && *e) {
            char path[1024]; unsigned seed = 1; long long from = 300;
            int k = 0;
            while (e[k] && e[k] != ',' && k < 1023) { path[k] = e[k]; k++; }
            path[k] = 0;
            if (e[k] == ',') sscanf(e + k + 1, "%u,%lld", &seed, &from);
            po_seed = seed; po_from = from;
            FILE *f = fopen(path, "r");
            char line[256]; unsigned a, b, c; u32 cap = 0;
            while (f && fgets(line, sizeof line, f))
                if (sscanf(line, "modfield %x %x %x", &a, &b, &c) == 3) {
                    if (po_n == cap) po_f = realloc(po_f, sizeof *po_f * (cap = cap ? cap * 2 : 256));
                    po_f[po_n].o = a; po_f[po_n].off = b; po_f[po_n].len = c; po_n++;
                }
            if (f) fclose(f);
            po_nc = bof_load(path, &po_c);
            po_state = po_n || po_nc ? 1 : 0;
            fprintf(stderr, "[poison] SSBU_POISON: %u fields and %u class fields from %s, seed %u, from fight frame %lld\n", po_n, po_nc, path, seed, from);
        }
    }
    if (po_state != 1 || fight_frame < po_from) return;
    po_frame = fight_frame;
    u64 fight_test_boma(int k); int kernel_read64(u64 a, u64 *v);
    u8 fill = (u8)(0xC1 + (po_seed * 7u + (u32)fight_frame * 13u) % 0x3Eu);
    u64 bytes = 0; int fighters = 0;
    for (int k = 0; k < 8; k++) {
        u64 bo = fight_test_boma(k);
        if (!bo) break;
        fighters++;
        for (u32 i = 0; i < po_n; i++) {
            u64 m = 0;
            if (!kernel_read64(bo + po_f[i].o, &m) || m < 0x6000000000ull || m >= 0x7000000000ull) continue;
            memset(RT_HOST(m + po_f[i].off), fill, po_f[i].len);
            bytes += po_f[i].len;
            if (lv_state == 2)   /* (the tripwire's marks: bit 7 of the byte's first-access state, cleared with it at the next safe point) */
                for (u32 q = 0; q < po_f[i].len; q++) {
                    u8 *cur, *acc, *pg; u64 g = m + po_f[i].off + q;
                    if (lv_chunk(g >> CH_SHIFT, &cur, &acc, &pg, 1)) { u32 o = (u32)(g & ((1u << CH_SHIFT) - 1)); cur[o] = 0x80; pg[o >> 12] = 1; }
                }
        }
    }
    if (po_nc) {
        bo_scan(fight_frame);
        for (u32 j = 0; j < bo_n; j++)
            for (u32 i = bof_first(po_c, po_nc, bo_mod[j].vptr); i < po_nc && po_c[i].vptr == bo_mod[j].vptr; i++) {
                memset(RT_HOST(bo_mod[j].m + po_c[i].off), fill, po_c[i].len);
                bytes += po_c[i].len;
                if (lv_state == 2)
                    for (u32 q = 0; q < po_c[i].len; q++) {
                        u8 *cur, *acc, *pg; u64 g = bo_mod[j].m + po_c[i].off + q;
                        if (lv_chunk(g >> CH_SHIFT, &cur, &acc, &pg, 1)) { u32 o = (u32)(g & ((1u << CH_SHIFT) - 1)); cur[o] = 0x80; pg[o >> 12] = 1; }
                    }
            }
    }
    { static int told; if (!told++) fprintf(stderr, "[poison] first safe point poisoned: fight frame %lld, %d fighters, %llu bytes, fill %#x (%u live modules of %u pools scanned)\n", fight_frame, fighters, (unsigned long long)bytes, fill, bo_n, bo_npools); }
}

/* ---- (research, 2026-11-13 evening) SSBU_DIGEST: the fighters' carried state, hashed at every safe point -------------
 * SSBU_DIGEST=<file>,<out>[,<first fight frame>]: the file's "modfield <offset in the accessor> <offset in the
 * module> <length>" lines name bytes of the fighters' modules (the carried ones, research/tools/live.py). At every
 * safe point, before any poison is written, each fighter's named bytes are hashed by pieces of 32 bytes of a module
 * (FNV-1a, 32 bits; a piece's unnamed bytes count as 0; an aligned 8-byte word that looks like a guest address,
 * 0x60... to 0x72..., counts as 0: addresses change from launch to launch). The out file: "DGF1", u32 pieces, then
 * per piece (u32 accessor offset, u32 offset in the module); then per safe point and fighter: u32 0x31474644, u32
 * fight frame, u32 logic frame, u32 fighter, then a u32 per piece. Two launches of one fight give the same file; a
 * run with poison is compared piece by piece, the poisoned pieces left out (research/tools/poison.py). */
static struct { u32 o, off; u8 mask[32]; } *dg_p; static u32 dg_n; static int dg_state = -1; static FILE *dg_out; static long long dg_from = 300;
/* ("classfield" lines of the same file: pieces by module class, for every live battle object of the pools; written to
 * <out>.cls: per safe point u32 0x32474644, fight frame, logic frame, records, then per piece of each live module
 * u32 object id, u32 (offset in the accessor << 16 | piece offset), u32 the vptr's low half, u32 hash) */
static struct { u64 vptr; u32 off; u8 mask[32]; } *dc_p; static u32 dc_n; static FILE *dc_out;
static int dg_cmp(const void *a, const void *b) { const u32 *x = a, *y = b; return x[0] != y[0] ? (x[0] < y[0] ? -1 : 1) : x[1] < y[1] ? -1 : x[1] > y[1]; }
void rt_digest_boundary(long long fight_frame) {
    if (dg_state < 0) {
        const char *e = getenv("SSBU_DIGEST");
        dg_state = 0;
        if (e && *e) {
            char path[1024], outp[1024]; long long from = 300; int k = 0, j = 0;
            while (e[k] && e[k] != ',' && k < 1023) { path[k] = e[k]; k++; }
            path[k] = 0;
            if (e[k] == ',') { k++; while (e[k] && e[k] != ',' && j < 1023) outp[j++] = e[k++]; }
            outp[j] = 0;
            if (e[k] == ',') sscanf(e + k + 1, "%lld", &from);
            dg_from = from;
            FILE *f = fopen(path, "r");
            char line[256]; unsigned a, b, c; u32 cap = 0;
            while (f && fgets(line, sizeof line, f))
                if (sscanf(line, "modfield %x %x %x", &a, &b, &c) == 3)
                    for (u32 q = b; q < b + c; q++) {
                        u32 i = 0;
                        while (i < dg_n && !(dg_p[i].o == a && dg_p[i].off == (q & ~31u))) i++;
                        if (i == dg_n) {
                            if (dg_n == cap) dg_p = realloc(dg_p, sizeof *dg_p * (cap = cap ? cap * 2 : 1024));
                            memset(&dg_p[i], 0, sizeof *dg_p); dg_p[i].o = a; dg_p[i].off = q & ~31u; dg_n++;
                        }
                        dg_p[i].mask[q & 31] = 1;
                    }
            if (f) fclose(f);
            if (dg_n) qsort(dg_p, dg_n, sizeof *dg_p, dg_cmp);
            {   BoField *cf = NULL; u32 ncf = bof_load(path, &cf), cap2 = 0;
                for (u32 i = 0; i < ncf; i++)
                    for (u32 q = cf[i].off; q < cf[i].off + cf[i].len; q++) {
                        u32 k = dc_n;   /* (sorted by class then offset: the piece, if there, is the last one) */
                        if (dc_n && dc_p[dc_n - 1].vptr == cf[i].vptr && dc_p[dc_n - 1].off == (q & ~31u)) k = dc_n - 1;
                        if (k == dc_n) {
                            if (dc_n == cap2) dc_p = realloc(dc_p, sizeof *dc_p * (cap2 = cap2 ? cap2 * 2 : 4096));
                            memset(&dc_p[k], 0, sizeof *dc_p); dc_p[k].vptr = cf[i].vptr; dc_p[k].off = q & ~31u; dc_n++;
                        }
                        dc_p[k].mask[q & 31] = 1;
                    }
                free(cf);
                if (dc_n && outp[0]) { char p2[1100]; snprintf(p2, sizeof p2, "%s.cls", outp); dc_out = fopen(p2, "wb"); }
            }
            dg_out = dg_n && outp[0] ? fopen(outp, "wb") : NULL;
            if (dg_out) {
                fwrite("DGF1", 1, 4, dg_out); fwrite(&dg_n, 4, 1, dg_out);
                for (u32 i = 0; i < dg_n; i++) { fwrite(&dg_p[i].o, 4, 1, dg_out); fwrite(&dg_p[i].off, 4, 1, dg_out); }
                dg_state = 1;
            }
            if (dc_out) dg_state = 1;
            fprintf(stderr, "[digest] SSBU_DIGEST: %u pieces of 32 bytes from %s into %s, from fight frame %lld%s\n", dg_n, path, outp, from, dg_out ? "" : " (NOT WRITTEN)");
        }
    }
    if (dg_state != 1 || fight_frame < dg_from) return;
    u64 fight_test_boma(int k); int kernel_read64(u64 a, u64 *v);
    u32 lf = ld32(0x71052c5184ull);
    if (dc_out) {
        bo_scan(fight_frame);
        long at = ftell(dc_out);
        u32 head[4] = {0x32474644u, (u32)fight_frame, lf, 0}, nrec = 0;
        fwrite(head, 4, 4, dc_out);
        for (u32 j = 0; j < bo_n; j++) {
            u32 lo = 0, hi = dc_n;
            while (lo < hi) { u32 md = (lo + hi) / 2; if (dc_p[md].vptr < bo_mod[j].vptr) lo = md + 1; else hi = md; }
            for (u32 i = lo; i < dc_n && dc_p[i].vptr == bo_mod[j].vptr; i++) {
                u8 b[32]; u32 h = 0x811c9dc5u;
                memcpy(b, RT_HOST(bo_mod[j].m + dc_p[i].off), 32);
                for (int w = 0; w < 32; w += 8) {
                    u64 v; memcpy(&v, b + w, 8);
                    int whole = 1;
                    for (int q = 0; q < 8; q++) whole &= dc_p[i].mask[w + q];
                    if (whole && v >= 0x6000000000ull && v < 0x7300000000ull && (((bo_mod[j].m + dc_p[i].off + w) & 7) == 0)) memset(b + w, 0, 8);
                }
                for (int q = 0; q < 32; q++) { h ^= dc_p[i].mask[q] ? b[q] : 0; h *= 16777619u; }
                u32 rec[4] = {bo_mod[j].id, bo_mod[j].o << 16 | dc_p[i].off, (u32)bo_mod[j].vptr, h};
                fwrite(rec, 4, 4, dc_out); nrec++;
            }
        }
        long end = ftell(dc_out);
        fseek(dc_out, at + 12, SEEK_SET); fwrite(&nrec, 4, 1, dc_out); fseek(dc_out, end, SEEK_SET);
        if (!(fight_frame & 63)) fflush(dc_out);
    }
    if (!dg_out) return;
    for (int k = 0; k < 8; k++) {
        u64 bo = fight_test_boma(k);
        if (!bo) break;
        u32 head[4] = {0x31474644u, (u32)fight_frame, lf, (u32)k};
        fwrite(head, 4, 4, dg_out);
        u32 last_o = ~0u; u64 m = 0; int ok = 0;
        for (u32 i = 0; i < dg_n; i++) {
            if (dg_p[i].o != last_o) { last_o = dg_p[i].o; m = 0; ok = kernel_read64(bo + last_o, &m) && m >= 0x6000000000ull && m < 0x7000000000ull; }
            u32 h = 0x811c9dc5u;
            if (ok) {
                u8 b[32];
                memcpy(b, RT_HOST(m + dg_p[i].off), 32);
                for (int w = 0; w < 32; w += 8) {
                    u64 v; memcpy(&v, b + w, 8);
                    int whole = 1;   /* (only a word whose 8 bytes are all named: a named 4-byte value beside an unnamed one is no address) */
                    for (int q = 0; q < 8; q++) whole &= dg_p[i].mask[w + q];
                    if (whole && v >= 0x6000000000ull && v < 0x7300000000ull && (((m + dg_p[i].off + w) & 7) == 0)) memset(b + w, 0, 8);
                }
                for (int q = 0; q < 32; q++) { h ^= dg_p[i].mask[q] ? b[q] : 0; h *= 16777619u; }
            }
            fwrite(&h, 4, 1, dg_out);
        }
    }
    if (!(fight_frame & 63)) fflush(dg_out);
}

/* the rollback safe point (hle_rb_core.c, once a fight frame, on the main thread) */
void rt_lv_boundary(long long fight_frame) {
    if (lv_state == 1 && fight_frame >= lv_from) {
        lv_state = 2; rt_mt_on = 1;
        if (!exe_base) { HMODULE m = GetModuleHandleA(NULL); const IMAGE_NT_HEADERS *nt = (const IMAGE_NT_HEADERS *)((const u8 *)m + ((const IMAGE_DOS_HEADER *)m)->e_lfanew); exe_base = (u64)(uintptr_t)m; exe_end = exe_base + nt->OptionalHeader.SizeOfImage; }
        {   const char *d = getenv("SSBU_LIVE_DEBUG"); unsigned key = 0, off = 0, len = 0, skip = 0;
            if (d && sscanf(d, "%x,%x,%x,%u", &key, &off, &len, &skip) >= 3)
                for (long i = 0; ww_r && i < ww_n; i++) if (ww_r[i].key == key && !skip--) { lv_dbg_lo = ww_r[i].start + off; lv_dbg_hi = lv_dbg_lo + len; break; }
            {   u64 fight_test_boma(int k); int kernel_read64(u64 a, u64 *v);
                for (int k = 0; k < 8; k++) {
                    u64 b = fight_test_boma(k), w[4] = {0}, v[4] = {0};
                    if (!b) break;
                    static const u32 offs[4] = {0x38, 0x40, 0x58, 0x88};
                    for (int q = 0; q < 4; q++) { kernel_read64(b + offs[q], &w[q]); if (w[q]) kernel_read64(w[q], &v[q]); }
                    fprintf(stderr, "[lvdbg] fighter %d: accessor %llx; +0x38 -> %llx (vptr %llx); +0x40 -> %llx (vptr %llx); +0x58 -> %llx (vptr %llx); +0x88 -> %llx (vptr %llx)" "\n",
                            k, (unsigned long long)b, (unsigned long long)w[0], (unsigned long long)v[0], (unsigned long long)w[1], (unsigned long long)v[1],
                            (unsigned long long)w[2], (unsigned long long)v[2], (unsigned long long)w[3], (unsigned long long)v[3]);
                    /* (the fighters' own module objects, from the accessors the frame line gives: every pointer of the accessor
                     * to an object with a vptr in main's data. The state dump's registrations at these frames were other
                     * objects: found 2026-11-13 with this debug.) */
                    for (u32 o = 0x10; o < 0x400; o += 8) {
                        u64 m = 0, vp = 0;
                        if (!kernel_read64(b + o, &m) || m < 0x6000000000ull || m >= 0x7000000000ull || m == b || !kernel_read64(m, &vp)) continue;
                        if (vp < 0x7104000000ull || vp >= 0x7106000000ull) continue;
                        rt_ww_range(m, 0x900, o << 16);
                    }
                    if (d && key == 0xf00000u + (unsigned)k) { lv_dbg_lo = w[1] + off; lv_dbg_hi = lv_dbg_lo + len; }   /* (key f0000k: fighter k's object at +0x40) */
                }
            }
            if (d) fprintf(stderr, "[lvdbg] key %x: %llx-%llx (%ld ranges registered)" "\n", key, (unsigned long long)lv_dbg_lo, (unsigned long long)lv_dbg_hi, (long)ww_n);
        }
        fprintf(stderr, "[memtrace] SSBU_LIVE: on at fight frame %lld\n", fight_frame);
        return;
    }
    if (lv_state != 2) return;
    { static int told; if ((rf_paused || !rt_mt_on) && told++ < 5) fprintf(stderr, "[lvdbg] at the safe point of fight frame %lld: paused %d, rt_mt_on %d" "\n", fight_frame, rf_paused, (int)rt_mt_on); }
    {   /* (SSBU_LIVE_DRAIN=1: the GPU's queue is run to its end before the boundary, as a save does: what the GPU thread
         * then reads after the boundary was submitted after it; without, its lag behind the game counts as reads
         * across the boundary) */
        static int drain = -1;
        if (drain < 0) drain = getenv("SSBU_LIVE_DRAIN") != NULL;
        if (drain) { void gpu_queue_drain(void); gpu_queue_drain(); }
    }
    lo_scan(fight_frame);   /* (the objects that came and went: before the first accesses start again) */
    for (LONG k = 0; k < lv_nids; k++) {
        u8 *pg = lv_pg[lv_ids[k]], *cur = lv_cur[lv_ids[k]];
        for (u32 p = 0; p < 512; p++) if (pg[p]) { pg[p] = 0; memset(cur + ((size_t)p << 12), 0, 0x1000); }
    }
    lv_intervals++;
    if (fight_frame >= lv_to) {
        rt_mt_on = (mt_state == 2 || probes_open) ? 1 : 0;
        lv_write();
        lv_state = 3;
    }
}
__attribute__((constructor)) static void lv_init(void) {
    const char *e = getenv("SSBU_LIVE");
    int used = 0;
    if (!e || sscanf(e, "%lld,%lld,%n", &lv_from, &lv_to, &used) < 2 || !used) return;
    snprintf(lv_path, sizeof lv_path, "%s", e + used);
    lv_cur = calloc(CH_COUNT, sizeof *lv_cur); lv_acc = calloc(CH_COUNT, sizeof *lv_acc); lv_pg = calloc(CH_COUNT, sizeof *lv_pg);
    lv_ids = calloc(LV_IDS, sizeof *lv_ids); lv_agg = calloc(LV_AGG, sizeof *lv_agg);
    if (!lv_cur || !lv_acc || !lv_pg || !lv_ids || !lv_agg) return;
    lv_state = 1;
    fprintf(stderr, "[memtrace] SSBU_LIVE: fight frames %lld to %lld, into %s\n", lv_from, lv_to, lv_path);
}
#else
void rt_lv_boundary(long long fight_frame) { (void)fight_frame; }
void rt_lv_flush(u64 lo, u64 hi, u64 ra1, u64 ra2, u64 size, u64 off0) { (void)lo; (void)hi; (void)ra1; (void)ra2; (void)size; (void)off0; }
void rt_lv_memnote(u64 at, u64 size, int kind) { (void)at; (void)size; (void)kind; }
int rt_lv_on(void) { return 0; }
#endif

void rt_mt_access(u64 a, u32 n, int write) {
#ifdef _WIN32
    if (lv_state == 2 && !rf_paused) lv_access(a, n, write);
    if (rf_rec && !rf_paused) {
        u64 ra0 = (u64)(uintptr_t)__builtin_return_address(0);
        rf_access(a, n, write, ra0 >= exe_base && ra0 < exe_end ? (u32)(ra0 - exe_base) : 0xFFFFFFFFu);
    }
#endif
    if (probe_on) { if (probe_n < PROBE_MAX) { probe_buf[probe_n].addr = a; probe_buf[probe_n].size = n; probe_buf[probe_n].write = (u32)write; probe_n++; } }
    u16 f = cur;
    if (!f || !n) return;
    u64 ra = (u64)(uintptr_t)__builtin_return_address(0);
    u32 rel = ra >= exe_base && ra < exe_end ? (u32)(ra - exe_base) : 0xFFFFFFFFu;
    if (write && ww_on > 0) ww_note(a, n, rel);
    u32 bit = 1u << thread_bit();
    for (u64 l = a >> 6, e = (a + n - 1) >> 6; l <= e; l++) {
        Line *c = chunk(l << 6);
        if (!c) return;
        Line *x = &c[l & (CH_LINES - 1)];
        x->threads |= bit;
        if (x->frame != f) {
            x->frame = f;
            if (write) { x->fl = 2; x->frames_w++; x->last_w = f; x->ra_w = rel; x->cat_w |= cat_bit(rel) | PHASE_BIT(); }
            else {
                x->fl = 1; x->frames_r++; x->first_r++;
                if (x->last_w && x->last_w < f) x->cat_r |= cat_bit(rel) | PHASE_BIT();
                if (x->last_w && x->last_w < f) {
                    x->live_in++; x->ra_live = rel;
#ifdef _WIN32
                    void *bt[5] = {0};
                    USHORT got = RtlCaptureStackBackTrace(1, 4, bt, NULL);   /* [0] the reading function (= ra), then its callers */
                    for (int k = 0; k < 3; k++) {
                        u64 r = k + 1 < got ? (u64)(uintptr_t)bt[k + 1] : 0;
                        x->chain[k] = r >= exe_base && r < exe_end ? (u32)(r - exe_base) : 0xFFFFFFFFu;
                    }
#endif
                }
            }
        } else if (write) {
            if (!(x->fl & 2)) { x->fl |= 2; x->frames_w++; x->cat_w |= cat_bit(rel) | PHASE_BIT(); }
            x->last_w = f; x->ra_w = rel;
        } else {
            if (!(x->fl & 1)) { x->fl |= 1; x->frames_r++; }
            if (!(x->fl & 2) && x->last_w && x->last_w < f) x->cat_r |= cat_bit(rel) | PHASE_BIT();   /* (still the carried value) */
        }
    }
}

static void mt_write(void) {
    FILE *f = fopen(mt_path, "wb");
    if (!f) { fprintf(stderr, "[memtrace] cannot write %s\n", mt_path); return; }
    u32 frames = (u32)mt_frames, nt = nthreads < 32 ? (u32)nthreads : 32;
    fwrite("MT5", 1, 4, f);
    fwrite(&frames, 4, 1, f);
    fwrite(&nt, 4, 1, f);
    for (u32 i = 0; i < nt; i++) {
#ifdef _WIN32
        u64 entry = 0, kid = 0;   /* (the guest thread's entry point names it: written at the file's end, now its threads are known) */
        if (!thr[i].name[0] && kernel_thread_of_host(thr[i].id, &entry, &kid))
            snprintf(thr[i].name, sizeof thr[i].name, "guest entry %#llx id %llu", (unsigned long long)entry, (unsigned long long)kid);
#endif
        fwrite(&thr[i].id, 4, 1, f); fwrite(thr[i].name, 1, 60, f);
    }
    u64 lines = 0, live = 0;
    for (u64 id = 0; id < CH_COUNT; id++) {
        Line *c = chunks[id];
        if (!c) continue;
        for (u32 i = 0; i < CH_LINES; i++) {
            const Line *x = &c[i];
            if (!x->frames_r && !x->frames_w) continue;
            u64 addr = (id << CH_SHIFT) + ((u64)i << 6);
            fwrite(&addr, 8, 1, f);
            fwrite(&x->frames_r, 2, 1, f); fwrite(&x->frames_w, 2, 1, f); fwrite(&x->first_r, 2, 1, f); fwrite(&x->live_in, 2, 1, f);
            fwrite(&x->threads, 4, 1, f); fwrite(&x->ra_live, 4, 1, f); fwrite(&x->ra_w, 4, 1, f);
            fwrite(x->chain, 4, 3, f); fwrite(&x->cat_r, 4, 1, f); fwrite(&x->cat_w, 4, 1, f);
            lines++; live += x->live_in != 0;
        }
    }
    fclose(f);
    fprintf(stderr, "[memtrace] %llu lines touched (%llu MB), %llu of them live from one frame into another; %u threads; %s\n",
            (unsigned long long)lines, (unsigned long long)(lines >> 14), (unsigned long long)live, nt, mt_path);
}

/* the frame end: the window opens, moves on a frame, or closes (and the file is written) */
static void mt_frame_end_before(Cpu *c, const u64 args[8], void *ctx) { (void)c; (void)args; (void)ctx; mt_phase = 0; }
static void mt_frame_end(Cpu *c, const u64 args[8], void *ctx) {
    (void)c; (void)args; (void)ctx;
    if (mt_state != 1 && mt_state != 2) return;
    if (!game_fight_on()) return;
    fight_frames++;
    if (mt_state == 1 && fight_frames == mt_from) {
        mt_state = 2; cur = 1; rt_mt_on = 1;
        fprintf(stderr, "[memtrace] on at fight frame %lld for %lld frames\n", fight_frames, mt_frames);
    } else if (mt_state == 2) {
        if ((long long)cur >= mt_frames) { rt_mt_on = 0; cur = 0; mt_state = 3; mt_write(); }
        else cur++;
    }
}

/* (a constructor, as hle_rb_core.c's: registers the frame end before the game runs, when SSBU_MEMTRACE is set) */
__attribute__((constructor)) static void mt_init(void) {
    const char *e = getenv("SSBU_MEMTRACE");
    mt_state = 0;
    if (!e || !*e) return;
    int used = 0;
    if (sscanf(e, "%lld,%lld,%n", &mt_from, &mt_frames, &used) < 2 || !used || mt_frames < 2 || mt_frames > 60000) {
        fprintf(stderr, "[memtrace] SSBU_MEMTRACE=<first fight frame>,<frames>,<file>: not understood\n");
        return;
    }
    snprintf(mt_path, sizeof mt_path, "%s", e + used);
    const char *cf = getenv("SSBU_MEMTRACE_CATS");   /* (research/tools/code_cats.py's file) */
    FILE *cfile = cf && *cf ? fopen(cf, "rb") : NULL;
    if (cfile) {
        u32 n = 0;
        if (fread(&n, 4, 1, cfile) == 1 && n < (1u << 24) && (cats = malloc(sizeof *cats * (n ? n : 1))) && fread(cats, 8, n, cfile) == n) ncats = n;
        fclose(cfile);
        fprintf(stderr, "[memtrace] code categories: %u ranges from %s\n", ncats, cf);
    }
    chunks = calloc(CH_COUNT, sizeof *chunks);
    if (!chunks) return;
#ifdef _WIN32
    {   /* the program's span, for the return addresses */
        HMODULE m = GetModuleHandleA(NULL);
        const IMAGE_NT_HEADERS *nt = (const IMAGE_NT_HEADERS *)((const u8 *)m + ((const IMAGE_DOS_HEADER *)m)->e_lfanew);
        exe_base = (u64)(uintptr_t)m; exe_end = exe_base + nt->OptionalHeader.SizeOfImage;
    }
#endif
    mt_state = 1;
    frame_hook_add(FRAME_HOOK_END, FRAME_ORDER_FIGHT_TEST + 20, mt_frame_end_before, mt_frame_end, NULL);
    fprintf(stderr, "[memtrace] SSBU_MEMTRACE: fight frames %lld to %lld traced into %s\n", mt_from, mt_from + mt_frames - 1, mt_path);
}

/* (research: the strict oracle, hle_rb_state.c's rb_ref_compare) What the trace window saw of the 64-byte line at a:
 * bit 0 touched, 1 state (a value carried between frames), 2 read by simulation code (app, app?, lua2cpp scripts),
 * 3 read in the logic phase on the main thread, 4 written by simulation code or in the logic phase on the main thread.
 * 0: not traced (no window, or the window never touched it). */
#define MT_SIM_CATS ((1u << 1) | (1u << 8) | (1u << 10))
u32 rt_mt_line_class(u64 a) {
    if (!chunks || mt_state != 3) return 0;
    u64 id = a >> CH_SHIFT;
    if (id >= CH_COUNT || !chunks[id]) return 0;
    const Line *x = &chunks[id][(a >> 6) & (CH_LINES - 1)];
    if (!x->frames_r && !x->frames_w) return 0;
    return 1u | (x->live_in ? 2u : 0) | (x->cat_r & MT_SIM_CATS ? 4u : 0) | (x->cat_r & (1u << 16) ? 8u : 0) |
           (x->cat_w & (MT_SIM_CATS | (1u << 16)) ? 16u : 0);
}
/* (research: hle_rb_state.c's SSBU_RB_SKIP_NONSIM) 1 once the trace window is over and its lines can be asked about. */
int rt_mt_done(void) { return chunks && mt_state == 3; }
