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
