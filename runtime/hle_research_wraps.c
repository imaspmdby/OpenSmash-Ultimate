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
#else
static const long rb_fast = 0;
#endif

/* signature: 16 words, sha256 cf7b0b812eb864d3 */
HLE_WRAP(71038fec40) {
    static int on = -1;
    static long long skipped;
    if (on < 0) { const char *e = getenv("SSBU_RB_SKIP_LUA_GC"); on = e && *e == '1'; }
    if (on && rb_fast > 0 && c->x[30] == 0x71037480C0ull) {
        if (!skipped++ || skipped % 2000 == 0) fprintf(stderr, "[rb] SSBU_RB_SKIP_LUA_GC: %lld Lua GC steps left out of frames run again\n", skipped);
        return;
    }
    f_71038fec40_orig(c);
}
