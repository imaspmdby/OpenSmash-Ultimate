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
void rt_rf_native(u64 a, u64 n, int write) {
    if (!rf_rec || rf_paused) return;
    while (n) { u32 k = n > 0x10000 ? 0x10000 : (u32)n; rf_access(a, k, write, 0xFFFFFFFEu); a += k; n -= k; }
}
#else
void rt_rf_pause(int d) { (void)d; }
void rt_rf_native(u64 a, u64 n, int write) { (void)a; (void)n; (void)write; }
#endif

void rt_mt_access(u64 a, u32 n, int write) {
#ifdef _WIN32
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
