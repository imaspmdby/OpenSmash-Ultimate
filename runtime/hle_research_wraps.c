/* Research (research/RESEARCH.md, "where a rollback's time goes"): work left out of the frames run again after a load.
 * Each switch is off unless set; with it off the wrap only calls the game's function.
 *
 * SSBU_RB_SKIP_LUA_GC=1: the main loop's own Lua garbage collection step (FUN 0x71038fec40, Lua 5.3's luaC_step,
 * called once a frame from the main loop at 0x71037480bc, returning to 0x71037480c0) is not run in a frame run again
 * (rb_fast > 0, kernel.c). The function's 513 other callers (the allocations' own checks) are left as they are. The
 * time profile gave that step ~6 % of the main thread in a catch-up; Lua runs no game logic in a fight. */
#include <stdio.h>
#include <stdlib.h>

#include "host.h"

#ifdef _WIN32
extern volatile long rb_fast;   /* (kernel.c: > 0 while frames are run again, unseen) */
int rb_verify_replaying(void);  /* (hle_rb_core.c: a replay of SSBU_RB_VERIFY, which runs at normal speed) */
#else
static const long rb_fast = 0;
static int rb_verify_replaying(void) { return 0; }
#endif

/* SSBU_RB_SKIP_LUA_GC=2: also in the replay check's replays (so that the strict oracle judges it).
 * SSBU_LUA_HEAP_LOG=<n>: every n calls from the main loop, the Lua heap's size is logged: the lua_State is the
 * call's x0, its global_State at + 0x18, whose totalbytes (+ 0x10) and GCdebt (+ 0x18) add up to the bytes in use
 * (Lua 5.3's gettotalbytes; the main loop writes both just before this call). */
/* signature: 16 words, sha256 cf7b0b812eb864d3 */
HLE_WRAP(71038fec40) {
    static int on = -1, log_every = -1;
    static long long skipped, calls;
    if (on < 0) {
        const char *e = getenv("SSBU_RB_SKIP_LUA_GC"), *l = getenv("SSBU_LUA_HEAP_LOG");
        on = e && (*e == '1' || *e == '2') ? *e - '0' : 0;
        log_every = l && atoi(l) > 0 ? atoi(l) : 0;
    }
    int main_loop = c->x[30] == 0x71037480C0ull;
    if (main_loop && log_every && ++calls % log_every == 0) {
        u64 g = 0, total = 0, debt = 0;
        if (kernel_read64(c->x[0] + 0x18, &g) && g && kernel_read64(g + 0x10, &total) && kernel_read64(g + 0x18, &debt))
            fprintf(stderr, "[rb] lua heap: call %lld, %lld KB in use (%lld steps left out so far)\n", calls, (long long)(total + debt) >> 10, skipped);
    }
    if (on && main_loop && (rb_fast > 0 || (on == 2 && rb_verify_replaying()))) {
        if (!skipped++) fprintf(stderr, "[rb] SSBU_RB_SKIP_LUA_GC=%d: the main loop's Lua GC step is left out of the frames run again\n", on);
        return;
    }
    f_71038fec40_orig(c);
}

/* SSBU_FRAME_END_TIME=1: how long the graphics frame end (FRAME_END, frame_hooks.h) takes, by the kind of frame: a
 * normal frame, a frame run again unseen (rb_fast > 0 at its frame end), and the frame shown at the end of a catch-up
 * (the first frame end with rb_fast 0 after one with it set). Is the GPU wait at the end of a catch-up a cost of the
 * rollback, or what showing any frame costs? A line every 600 frame ends, and the fight's totals in each. */
#include "frame_hooks.h"
#ifdef _WIN32
#include <windows.h>
int game_fight_on(void);
static double fe_t0, fe_sum[3], fe_max[3], fe_freq;
static long long fe_n[3], fe_frames, fe_over[3];
static int fe_kind, fe_prev_fast;
static double fe_now(void) { LARGE_INTEGER t; QueryPerformanceCounter(&t); return (double)t.QuadPart * 1000.0 / fe_freq; }
static void fe_before(Cpu *c, const u64 args[8], void *ctx) {
    (void)c; (void)args; (void)ctx;
    int fast = rb_fast > 0;
    fe_kind = fast ? 1 : fe_prev_fast ? 2 : 0;
    fe_prev_fast = fast;
    fe_t0 = fe_now();
}
static void fe_after(Cpu *c, const u64 args[8], void *ctx) {
    (void)c; (void)args; (void)ctx;
    if (!game_fight_on()) return;
    double ms = fe_now() - fe_t0;
    fe_sum[fe_kind] += ms; fe_n[fe_kind]++; fe_over[fe_kind] += ms > 2.0;
    if (ms > fe_max[fe_kind]) fe_max[fe_kind] = ms;
    if (++fe_frames % 600 == 0) {
        static const char *const names[3] = {"normal", "run again unseen", "shown at a catch-up's end"};
        fprintf(stderr, "[rb] frame end time:");
        for (int k = 0; k < 3; k++)
            if (fe_n[k]) fprintf(stderr, " %s %.3f ms mean (max %.1f, %lld over 2 ms) of %lld;", names[k], fe_sum[k] / (double)fe_n[k], fe_max[k], fe_over[k], fe_n[k]);
        fprintf(stderr, "\n");
    }
}
__attribute__((constructor)) static void fe_init(void) {
    const char *e = getenv("SSBU_FRAME_END_TIME");
    if (!e || *e != '1') return;
    LARGE_INTEGER f; QueryPerformanceFrequency(&f); fe_freq = (double)f.QuadPart;
    frame_hook_add(FRAME_HOOK_END, FRAME_ORDER_FIGHT_TEST + 40, fe_before, fe_after, NULL);
}
#endif
