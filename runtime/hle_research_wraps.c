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
