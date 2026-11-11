# Gamestate research journal

Branch `gamestate-research`. Goal: a persistent, match-independent map of SSBU's gamestate (in invariants:
types / vtables, allocation sites, globals, fields), able to (1) read and summarise the state of any match and
(2) save / restore only that state (lightweight rollback). Every hypothesis gets a test, a result, and a why.

## Objectives

| # | Objective | Success criterion |
|---|---|---|
| O1 | Reproducible reference (oracle) | Full savestate (existing `hle_rb_state.c`) + fight hash: bit-exact over thousands of rollbacks on varied matches |
| O2 | Gamestate map in invariants | >99 % of a fight's hot bytes classed: state / scratch / output (render, sound, GPU) / constant |
| O3 | Map transfers to unseen matches | Unseen fighters / stages / items: extraction with no learning, no desync vs the oracle |
| O4 | Reader | Structured, diffable per-frame dump + summary, cross-checked with the game's getters |
| O5 | Lightweight savestate | Only the map's state saved; MB and ms measured vs today's ~40 MB / 8-12 ms; unknown memory falls back to the page path |
| O6 | This journal | Every hypothesis: test, result, why |

## Phases

0. Setup (fork, build, target runtime, instrumentation point) — **done 2026-11-11**
1. Test bench + oracle (O1)
2. Observe: allocations, types, accesses, pointer graph
3. Colour + generalise into the map (O2, O3)
4. Reader (O4)
5. Lightweight savestate experiments E1-E4 (O5)

---

## Phase 0 log

### 2026-11-11 — baseline of the existing work (upstream 4940423)

- The rollback savestate is semantics-free: every RW guest page + host stacks / fibers / kernel tables
  (`runtime/hle_rb_state.c`). In a fight, a page state map (hot / cold by write protection, 64 KB groups) bounds it
  to ~20-50 MB of the ~1.9 GB alias area; rebuilt from scratch every fight (`sm_end` / `sm_begin`).
- ssbu-recomp's variant (`ssbu-recomp/runtime/r1_state.c`, `rb_learned.c`): store marks compiled into the lifted
  code (`R1M`, `-DR1_MARK`), then a learned set (~34 MB of 1.9 GB), plus hand-made "not simulation" exclusions
  (`r1_nosim`, async pages, a presentation pool of 3 jemalloc allocation sites).
- Semantic reads exist only for the fight hash (`hle_rb_core.c` `fight_frame`): status, situation, motion, frame,
  pos, lr, speed, damage through exported `app::lua_bind::*_impl` getters, plus the 9 `sv_math::rand` generators.
  No hitboxes, items, projectiles or stage state.

### 2026-11-11 — target runtime and instrumentation point

- Target: the main runtime (`runtime/`, WindowSmash), where online rollback is on by default.
- Every guest memory access of the generated C goes through `runtime/recomp.h`: `ld8..ld128`, `st8..st128`,
  `lda*/sta*`, the CAS helpers, `ldv*/stv*`, and direct `RT_HOST` memcpy for SIMD lanes and `rt_zva`. One header =
  one interception point for reads and writes (the equivalent of ssbu-recomp's `R1M`, extended to loads).
- Caveats: `ld/st` take no `Cpu *`, so attribution of an access to a guest function needs the host return address
  (or a per-thread "current function"). Changing `recomp.h` changes every object's key: an instrumented build must
  live in a build folder of its own so the normal build is not recompiled.

### 2026-11-11 — setup

- Clone of upstream at `C:\Users\Lucas\OpenSmash-research`, branch `gamestate-research`.
- `deps/`, `dump/`, `build/` copied from the existing install (`C:\Users\Lucas\OpenSmash-Ultimate`, left untouched);
  objects are keyed by content, so only what changed since 2026-11-04 recompiles.
- Remotes: `origin` = fork `imaspmdby/OpenSmash-Ultimate` (at 4940423, same as upstream), `upstream` =
  `OpenSmash-Ultimate/OpenSmash-Ultimate`. Nothing pushed yet.

### 2026-11-11 — build and baseline (phase 0 closed)

- Build: `tools/build_game.py` from the clone; generated C regenerated (recompiler changed since 2026-11-04), only
  changed objects recompiled. `build/ssbu.exe` OK. Only failure: `ssbu_glslang.dll` (Vulkan shader translator;
  `deps/msvc` lacks `msvcrt.lib` / `msvcprt.lib`, fixed by `tools/msvc_deps.py install`, which needs the user to
  accept Microsoft's licence). Not needed: Direct3D 11 is the default renderer.
- Test runs: `research/tools/run.sh <name> <timeout> VAR=...` — fresh copy of `research/runs/save_template`
  (copy of the user's save) as `SSBU_DATA_ROOT`, headless, movies skipped; outputs in `research/runs/<name>/`
  (git-ignored).
- Menu path for this build (`SSBU_SEQ_LOG` + `SSBU_CAPTURE`, run `discover3`): title 505 draws -> main menu ~1039
  -> Smash menu ~1190 -> rulesets 550 -> stage select ~350 -> fighter select ~2866. Sequence:
  `research/seq/to_fight.seq`; with the repo's gate input after `@fight`: `research/seq/gate.seq`.
- **Determinism gate** (`docs/TESTING-RUNS.md`, Mario vs CPU 3 Donkey Kong, Final Destination, `SSBU_SPEED=0`,
  fixed seed, deterministic, 20 s): two runs identical over 2834 hash lines (frames 1-1417). ~25 s a run.
- **Rollback oracle** (`SSBU_RB=1 SSBU_RB_RING=600,10,4,50`): 50 loads 4 frames back, 49 re-run frames checked,
  **0 different**. Save 7.9 ms mean (max 13.5), load 0.8 ms, catch-up of 4 frames 15.4 ms. A save copies
  ~1,200-1,800 pages (4-6 MB) a frame; the state map starts the fight with 4,310 hot alias pages (17 MB) and
  537,067 cold (2,097 MB). Guest memory 2,155 MB in 140 regions; 25 other threads, 18 switched-away fibers,
  81 setjmp records.
- Re-run both with `research/tools/baseline.sh [SSBU_DEBUG_MATCH settings]`.
- Note: the `SSBU_DEBUG_END` exit skips `sm_end`, so the fight's final hot-page count is not logged; phase 1
  needs it (log it at the end-of-run hook).

---

## Phase 1 log

### 2026-11-11 — instrumentation: the state map at the end of a run

- `runtime/hle_rb_state.c` `rb_state_map_report`, called by `hle_fight_test.c` at the `SSBU_DEBUG_END` exit (which
  skips `sm_end`): a `[rb] state map now:` line (hot / steady / cold pages, faults, saves) and, with
  `SSBU_RB_SM_DUMP=<file>`, the hot pages as runs (`<address> <pages> <steady pages>`). Runtime-only rebuild: 30 s.

### 2026-11-11 — test bench

- `research/tools/matrix.py <matrix> [--out] [--ring] [--only] [--env VAR=v]`: each match of a matrix
  (`research/matrix/*.txt`, `<name> | <SSBU_DEBUG_MATCH>`) through the oracle (`SSBU_RB_RING`, default
  `600,10,4,50`), with the gate's sequence and settings; `result.json` per run, `summary.json`, `summary.md`.
  Verdicts: OK, DESYNC, NO-RING, BAD-SETTINGS (checked on the ready-go line: the player record lines show player 2
  before the change, and an unknown fighter name leaves the menu's Mario), CRASH/TIMEOUT.
- `research/tools/hot_overlap.py <runs folder>`: pairwise overlap of the runs' hot pages by address.

### 2026-11-11 — matrix v1 (run `m1_v1`): 12 matches, 12 OK

| Match | Hot at start | Hot at end | Steady | Faults | Save ms mean (max) |
|---|---|---|---|---|---|
| base_mario_dk (FD) | 4295 | 15154 (59 MB) | 6665 | 724 | 8.0 (13.2) |
| proj_link_samus (BF) | 4444 | 19746 (77 MB) | 7554 | 972 | 4.6 (11.3) |
| pika_fox | 4042 | 17260 (67 MB) | 6773 | 889 | 8.1 (13.5) |
| duo_iceclimbers_vill | 4612 | 19875 (77 MB) | 7899 | 1008 | 8.7 (19.2) |
| luma_rosa_inkling | 4738 | 18696 (73 MB) | 7630 | 919 | 5.6 (14.7) |
| (mario)_steve * | 4431 | 20803 (81 MB) | 7738 | 1064 | 8.4 (14.9) |
| items_peach_snake (items on) | 4477 | 17723 (69 MB) | 7332 | 861 | 4.7 (11.4) |
| hazards_castle64 (items, hazards) | 3874 | 15173 (59 MB) | 6108 | 771 | 2.9 (7.8) |
| four_players (BF) | 4775 | 23091 (90 MB) | 9027 | 1159 | 5.7 (16.8) |
| isabelle_pacman (items on) | 4140 | 20168 (78 MB) | 7441 | 1003 | 8.4 (14.8) |
| (mario)_kazuya * | 4321 | 18715 (73 MB) | 7222 | 955 | 8.4 (17.0) |
| jr_duckhunt (items on) | 4429 | 17614 (68 MB) | 7201 | 862 | 4.6 (10.6) |

\* `ptrainer` and `eflame` are not ui_chara ids: player 1 stayed Mario (matrix fixed: pikmin, ness).

Findings:
1. **The oracle holds on every mechanic tried** (projectiles, companions, Nana, Luma, ink, Steve, items, hazards,
   4 players): 588 re-run frames, 0 different. Limit: rollbacks of 4 frames, 50 a fight, 20 s fights.
2. **The hot set grows all fight long**: ~4,300 pages at the first save, 15,000-23,000 after 20 s, monotonic.
3. **By address, little is shared between matches**: union 404 MB, hot in every run 4,164 pages (16 MB, about the
   size of the hot set at the first save), pairwise Jaccard 20-31 %. A map in addresses would not transfer from
   one match to another; this supports describing the state in invariants (types, allocation sites).
4. **The 64 KB fault groups inflate the set ~1.75x** (run `m1_group1`, `SSBU_RB_SM_GROUP=1`): 8,771 / 11,113 /
   12,834 hot pages (34 / 43 / 50 MB) instead of 15,154 / 19,746 / 23,091, for 6x the faults (4,225-6,776) and
   no change in save time or correctness. With one-page groups the size matches upstream's 20-50 MB and
   ssbu-recomp's 34 MB learned set.
5. **Written is not changed**: ~6,700-9,000 steady pages (written at every save) but only ~1,200-1,800 pages a
   save differ from the shadow and are copied (4-6 MB). Much of the per-frame writing rewrites the same bytes.

Questions for phase 2: what are the ~4,300 pages hot from the first save (the common core)? Where does the
growth come from (allocation churn, GPU ring buffers, new objects)? Which of the steady pages ever change?

### 2026-11-11 — hot pages: GPU memory or heap (run `m1_gpu`, one-page fault groups)

- `rb_state_map_report` now classes each hot page by the nvmap allocations (`nv_rb_maps`): a 4th column in the hot
  runs dump (GPU pages of the run) and `<dump>.nvmap` (every allocation: address, pages, hot pages).
- **Only 26-31 % of the hot pages are GPU memory**: 2,780 / 2,833 / 3,423 of 8,878 / 9,828 / 12,933 (10-13 MB), in
  ~60-70 of ~2,100-2,500 allocations (730-880 MB). Two shapes: small allocations almost wholly hot (2 MB at 98 %,
  600 KB at 98 %, 32 KB at 100 %), and large ones barely touched (147 MB at 0.3 %, 32 MB at 4 %, 18 MB at 11 %:
  ring buffers, by their look).
- **~70 % (24-37 MB) is the game's heap**, scattered over the whole 2 GB alias area in small runs (Mario vs DK:
  6,098 pages; 772 single pages, 2,415 in runs of 2-15, 1,931 in 16-255, 956 in 256+). An allocator's objects
  spread everywhere: what they are needs allocation sites and types (phase 2).

### 2026-11-11 — hardened oracle (run `m1_hard`): 12 matches, 12 OK, 1,788 rollbacks, 0 different

`--ring 300,6,8,150 --end 60s --override stock=99 --env SSBU_RB_RING_ROTATE=1`: from fight frame 300, every 6 frames
a load 1, 2, ... 8 frames back in turn, 150 times a fight, 60 s fights. Every match OK: 149 re-run frames the same,
0 different, each (the corrected names: Olimar kind 43, Ness kind 10). Hot at the end (64 KB groups) 18,849-26,082
pages (73-101 MB), of which GPU 5,673-7,803; save 3.7-8.4 ms mean, max 20.8-33.0 ms; load 0.75-1.24 ms.
The hot set still grows from 20 s to 60 s, but more slowly (Mario vs DK: 15,154 at 20 s, 20,128 at 60 s).

Pitfall: with 3 stocks a CPU 9 fight can end before `SSBU_DEBUG_END`; the game then waits on the results screen and
the run times out (the first `m1_hard` attempt). Long fights use `--override stock=99`.
