# Gamestate research journal

Branch `gamestate-research`. Goal: a persistent, match-independent map of SSBU's gamestate (in invariants:
types / vtables, allocation sites, globals, fields), able to (1) read and summarise the state of any match and
(2) save / restore only that state (lightweight rollback). Every hypothesis gets a test, a result, and a why.

## Where the map stands (summary; revised 2026-11-12 05:52)

Each claim names the entry that holds its evidence. **Established**: two methods agree, or one method with a
positive control, on several matches that differ by fighters, stage and situation. **Probable**: one method, or few
matches. **Open**: not known. Statements of older entries found false are annotated in place ("[Corrected ...]").

**Established**
- **Oracles.** The full savestate replays bit-exact on every mechanic tried (fight hash; ring and replay checks,
  2026-11-11 phase 1). The strict oracle explains the differing simulation lines by invariant causes, and finds injected
  errors the hash misses, in the round and the block where they were put (2026-11-12 02:33); on ten matches, five of
  them new to its rules, one line stays open (03:57); **with items on the stage it does not** (17-42 lines a replay,
  containers whose nodes move: 04:36). The rollback ring passes on 37 more matches of new
  fighters and stages, 3 of them with items falling (04:20, 04:36, 04:49, 05:58).
- **Battle objects.** Pools made once a match; the fighters' 43 modules at fixed boma offsets; each module class's
  object size (`research/map/module_sizes.json`, 02:03); items through the ItemManager (2026-11-11); one
  ground-collision record per object in a pool of 350 (02:27).
- **The reader.** Fighters' status, motion, position, damage equal to the game's getters on every match run; every
  named field (169 plain getters, 1,026 getters with arguments or another receiver) equal to the game's own answer
  at every dumped frame, on long CPU-against-CPU series: 69 fighters, 15 stages, 2-4 players, items (02:03, 02:38).
  The check found two errors the earlier matches had not shown (a field on the Hero, a speed override on Ice
  Climbers) and both were fixed. It holds through Final Smashes and through a fight's end (03:57, 04:26).
- **The state the simulation reads, by allocation site, over whole fights**: ~245 KB a 60 s fight; the stage table
  96 KB (carried, read by app code, no effect on the fight observed when perturbed: a grid of the stage's lines by the
  code reading), the battle objects' pools ~18 KB, the collision records ~3 KB, the stage objects 1-7 KB, stacks
  3-7 KB, and a flat tail of ~95 KB in ~320 sites that recur from match to match (01:48, 02:27; `research/map/sites.md`).
  The figure grows slowly with the window (183 / 218 / 246 KB for 300 / 1,200 / 3,600 frames).
- **Perturbed without effect on the fight**: the stage table (one-frame and 10 s held perturbations, positive
  control: 02:03; carried from frame to frame, so its role is open: 05:44);
  the gimmick objects, which some runs make and others do not, on Castle 64 and Pokémon Stadium 2 (runs with and
  without them identical: 02:03, 04:26); the Lua GC step in frames run again
  (2026-11-11, 2026-11-12 00:26).
- **The stage's moving parts keep their state in the stage's collision geometry** (segments, vertices, groups made at
  the match load; traces and held perturbations on two stages, 02:12; the code reading and the fighters' contact
  pointers, 05:18).
- **Repeatability**: CPU against CPU, and player 1 driven by logic frame, repeat exactly; a scripted player 1 does not
  (02:03, 03:31).

**Probable**
- The code-read fields marked "probable" in `research/map/code_reading/` (from writers and constructors only); a few of
  them now have a second method (frame-to-frame invariants, 03:31).
- The "no live block" state (~27 KB) belongs to another allocator (by its last reader).

**Open**
- Loading the ring's first saved state stops the game (rings whose depth is at least their interval; also with
  yesterday's runtime: 03:31, 05:51); the corrected-input rollback test waits on it, and on a fix of its own (G must
  start with the ring).
- Why the repo's scripted determinism gate fails tonight (its input's timing, probably; it passed yesterday: 03:31).
- What decides whether the gimmick objects are made; a reference-count-like pair seen twice by the strict oracle
  (02:33, 03:57); with items on the stage the strict oracle shows 17-42 unexplained lines a replay, mostly a
  container keyed by effect and sound names (04:36).
- The weapons' and items' work variables (no safe probe yet).

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

---

## Phase 2 log

### 2026-11-11 — allocation tracer (`runtime/hle_alloc_trace.c`, `SSBU_ALLOC_TRACE=<prefix>`)

- Wraps main's exported allocator by name (`malloc`, `calloc`, `realloc`, `aligned_alloc`, `free`, operator
  new / new[] / delete / delete[], nothrow and sized forms) and jemalloc's own entry points by address (13.0.5,
  from ssbu-recomp's hostrt.c table; signatures from `recomp.py wrap-sig`): `posix_memalign` 0x710392e1f0,
  `aligned_alloc` 0x710392e290, `realloc` 0x710392e330, `free` 0x710392eb40. Outermost call of a thread only.
- Per live block: address, size, frame made, made in the fight or not, first word (vptr), site = 4 return
  addresses (x30, then the frame records from x29, checked against the thread's sp). Report at the
  `SSBU_DEBUG_END` exit: `<prefix>.live` (first line `# setup <frame> end <frame>`, the match set-up being the player
  record builder's first call) and `<prefix>.sites`. Off: every wrap only calls the game's function.
- Lesson: with the exported names only, 8 % of the hot heap bytes were in traced blocks (the game calls jemalloc's
  entry points directly); with them, 74 %. A frame chain check against the stack area (0x77...) cut most chains
  at depth 1: thread stacks also live in the heap.

### 2026-11-11 — what the hot heap pages hold (run `m2_alloc`, Mario vs DK, 20 s, one-page groups)

`research/tools/attribute.py <run> <prefix>` (hot pages x live blocks) and `research/tools/rtti.py` (vptr ->
type name through main's RTTI, RELATIVE relocations applied).

- Hot 8,725 pages: GPU memory 2,783, the rest 5,942 (23 MB). Of the rest, 17 MB (74 %) inside live jemalloc
  blocks, 5 MB outside any (jemalloc's metadata? another allocator?).
- 2.04 M live blocks (1,750 MB, arenas included) from 95,128 sites. **No hot byte is in a block made during the
  fight**: 9 MB in blocks made at boot / in the menus, 7 MB in blocks made at the match load (set-up frame 4386).
  The fight fills pools and arenas made before it: the set of blocks is fixed when the fight starts. **[Corrected 2026-11-12 01:48: true of the hot pages over 20 s only; over whole 60 s fights 118-279 KB of state lie in blocks made in the fight, ~5-9 KB of it read by the simulation (fiber stacks mostly).]**
- By the type of the block (its first word through RTTI): 10.2 MB in blocks not starting with a vptr (arrays,
  pools, sub-heaps: a 1.7 MB block starts with "FRMH", an `nn::lmem` frame heap); **4.0 MB `nu::` (the render
  engine: RenderCommandBase 2.7 MB, ConstantBuffer, MeshBatch, QuadRenderPass, Instance, Material, Texture_NX,
  CommandList_NX, dev::AnimationNode...)**; 2.9 MB objects with a vptr but no RTTI (the game's own classes, by
  their look: compiled without RTTI); 0.55 MB `nn::ui2d` (the HUD: Pane, Material, Parts, Picture).
- So a good part of the CPU-side hot set is rendering and UI, not simulation: a first pruning target.

Next: the objects inside pools and arenas (a vptr census of each hot page, not only the blocks' first words), and
names for the vptrs without RTTI (their vtables' functions).

### 2026-11-11 — the user's questions on "not simulation" (answered, recorded as method)

- The render / UI split above is **by type name only**: a hypothesis, not a proof. Two separate questions for each
  part of the state: (a) does the simulation read it across frames (a dependency)? (b) can it be left out of a
  save without breaking the program (allocator metadata shared between both worlds, pointers and handles from the
  simulation into render objects, CPU structures in GPU memory: upstream's `SSBU_RB_SKIP_GPU=1` hang)? The map must
  carry both. Known trap: skeletal animation lives in the render engine (`nu::dev::AnimationNode`) but drives the
  bones that hitboxes hang on.
- Proof will come from read tracing (`ld*` in `recomp.h`) and from exclusion tests. **The oracle's limit**:
  `SSBU_RB_RING` compares a narrow fight hash (status, motion, pos, speed, damage, RNG). A pruning that breaks a
  hitbox, an item or a projectile is caught only when it reaches those fields. Before pruning: a stricter oracle
  (full memory comparison after a replay: upstream's `SSBU_RB_VERIFY` / `rb_ref_compare`).
- Not based on Lua: the method is memory-based (write protection, allocator, RTTI). The 2,224 exported
  `app::lua_bind::*_impl` getters serve as a dictionary (below).

### 2026-11-11 — the fighter's modules named; hot pages coloured by their objects

Runtime: `SSBU_BOMA_DUMP=<file>` (hle_fight_test.c: each fighter's boma words and their pointees' first words) and
`SSBU_RB_SM_VPTRS=<file>` (hle_rb_state.c: words of each hot non-GPU page pointing into main's data). The crash
handler is a vectored handler, so `__try` does not protect a read: a hot page the game decommitted crashed the first
try; pages are now checked with `VirtualQuery`, and the tracer reads through `kernel_read64`.
`research/tools/objtypes.py <run> <prefix>`.

- **43 boma modules at fixed offsets**, from the getters' first instruction (`ldr xN, [x0, #off]`): 0x38 Posture,
  0x40 Status, 0x48 Control, 0x50 Work, 0x58 Ground, 0x60 Camera, 0x68 Kinetic, 0x70 ColorBlend, 0x78 Model,
  0x80 Physics, 0x88 Motion, 0x90 Stop, 0x98 Article, 0xa0 Attack, 0xa8 Damage, 0xb0 Hit, 0xb8 Combo, 0xc0 Area,
  0xc8 Item, 0xd0 Link, 0xd8 Team, 0xe0 Search, 0xf0 Turn, 0xf8 Reflect, 0x100 Shield, 0x108 Reflector,
  0x110 Absorber, 0x118 Jostle, 0x120 Catch, 0x128 Cancel, 0x138 Capture, 0x140 Effect, 0x148 Sound,
  0x150 Visibility, 0x158 Grab, 0x160 Slope, 0x168 Shake, 0x170 Slow, 0x180 Shadow, 0x188 MotionAnimcmd, 0x190 Lua,
  0x198 InkPaint (0x0 "FighterPitBFinalModule" is an artefact of another getter shape). Their 43 vptrs follow from
  the bomas (`app::` classes have no RTTI; their vtables lie at 0x7104f6...-0x7104f8...).
- Hot non-GPU pages, 5,942: 2,556 hold no vptr at all (arrays, raw data, sub-heaps, allocator metadata); of the
  3,386 that hold objects, the most frequent object is `nu` in 1,672 (820 by RTTI, 852 by the neighbouring-vtable
  heuristic, marked ~), `nn` (ui2d, vfx) in 651, `app` in 119 (24 + ~95), unnamed in 944.
- Objects counted: render-engine retainers and commands dominate (`nu::InstanceRetainer<ConstantBuffer>` 14,195,
  `nu::RenderCommandBase` 5,740, RenderCommandFactory functors ~12,500...). The simulation's own objects are few
  (one module object per fighter and module) and their data is mostly raw (no vptr): following the modules'
  pointers (reachability from the 43 modules) is the next step.

### 2026-11-11 — reachability from the fighters (`SSBU_REACH`, run `m2_alloc`)

Runtime: `alloc_trace_reach` (hle_alloc_trace.c, called at the `SSBU_DEBUG_END` exit with the fighters' bomas):
breadth first from each boma's words, following every aligned word that points into a live traced block (a block
<= 64 KB whole, a larger one only the 4 KB page pointed into), 12 levels. `research/tools/reach.py`.

- 260,189 granules, 156 MB reached from the 2 bomas: the heap is one connected graph. Hot non-GPU pages covered
  (cumulative): depth 1-3 5 %, 4 8 %, 6 25 %, 8 48 %, 12 66 %; **1,989 hot non-GPU pages are never reached from the
  fighters** (other roots: stage, items, camera, UI, sound, managers).
- **The fighter's own state is small**: everything within depth 3 of the bomas is ~1.3 MB (by module: Sound
  479 KB, Motion 158, Lua 113, Work 86, Model 79, Article 67, Ground 53, Control 42, Slope 38, Reflector 24,
  Link 20, Attack 19...).
- **The simulation touches the render engine at depth 2-3**, as the user expected: ModelModule -> `nu::Model`,
  `nu::ConstantBuffer` / ResourceAdapter; EffectModule -> `nu::dev::AnimationSpace`; VisibilityModule ->
  `nu::dev::AnimationNode`; GroundModule -> `nn::vfx::Resource`. These are the sim / render boundary points to study
  (skeleton and bones: what hitboxes and ground collision read).
- Limit: a conservative scan takes any value for a pointer; some edges are false (ComboModule ->
  `nu::RenderCommandBase`, ArticleModule -> `nn::ui2d::Pane` look like stale or coincidental words). Reachability
  over-approximates and does not tell a dependency: it is a map of links, not of reads. Read tracing is the next
  tool.

### 2026-11-11 — roots extended (stage, items, 13 managers), parallel runs (runs `m3_*`)

- `matrix.py --jobs N` (a timeout kills only that run's game), `--probe` (alloc trace, vptrs, bomas, reach in
  `<run>/alloc.*`), `--hash`. Parallel is deterministic: 3 runs at once gave the sequential runs' fight hashes over
  3,136 lines each; throughput x2. The shader cache (`dump/shadercache`) is shared: a risk if new shaders appear.
  Retry: a run that stops in its first 30 s is run again once (ARCropolis stopped once at start-up in a parallel
  run: "a plugin showed an error", a race on its shared files, by its look).
- Reach roots: the fighters' bomas and 13 exported `lib::Singleton<T>::instance_` (StageManager, ItemManager,
  BattleObjectManager, BattleObjectWorld, BattleObjectSlow, FighterManager, BossManager (null),
  GimmickEventPresenter, FighterCutInManager, FighterParamAccessor2, ItemParamAccessor, LuaManager, EffectManager).
- **The managers barely change the picture**: ~2,000 hot non-GPU pages still never reached (3,537 with 4 players);
  stage-rooted ~100-130 pages. Of the never-reached pages (Mario vs DK): 1,114 outside any traced block, 982 inside
  traced blocks, mostly large ones (a 1.7 MB frame heap 400, a 16 MB arena 172, a 426 KB block 105).
- Why: untraced memory, sub-heaps, and **links by id** (the game reaches battle objects through ids:
  `sv_battle_object::module_accessor(id)`), which no pointer walk follows. Pointer reachability cannot delimit
  the simulation: the access trace replaces it.

### 2026-11-11 — memory-access trace (`build-trace`, `SSBU_MEMTRACE`, runs `m4_*`)

Build: `runtime/recomp.h` calls `rt_mt_access` on every guest load / store of the generated code when compiled with
`SSBU_MEMTRACE` (`tools/cc.py`: `SSBU_GAME_CFLAGS=-DSSBU_MEMTRACE`, `recomp.py all dump/exefs --out build-trace`; the
`/D` spelling is turned into a path by Git Bash). Changing recomp.h re-keys every object: the usual build was
compiled again whole once (~15 min); build-trace from nothing ~45 min. Collector `runtime/hle_memtrace.c`
(`SSBU_MEMTRACE=<first fight frame>,<frames>,<file>`): per 64-byte line, frames read / written, frames read first,
frames "live" (read first after a write in an earlier frame of the window), threads, the last state reader (return
address into ssbu.exe) and its 3 callers (`RtlCaptureStackBackTrace`: a guest call is a host call), the last writer.
`kernel.c` `kernel_thread_of_host` names the guest threads. Analysis `research/tools/memtrace.py <trace> [<alloc
prefix>]` (classes by area / thread, state by block type and site, readers / writers via `build-trace/ssbu.map`);
code labels by `rtti.CodeMap` (14,910 anchors: the virtual functions of named classes, 10,049, and main's exports).
`research/tools/types.py` renamed `objtypes.py` (it shadowed Python's own `types`).

Cost: the traced game with the trace off runs a match like the usual build; 300 traced frames add ~20 s.

Classes over 300 fight frames (frames 300-599), three matches:

| Match | state | scratch | output | constant |
|---|---|---|---|---|
| Mario vs DK (FD) | 3.1 MB | 3.6 MB | 4.3 MB | 5.9 MB |
| Castle 64, hazards, items | 3.2 MB | 3.1 MB | 4.3 MB | 6.2 MB |
| Peach vs Snake, items | 3.6 MB | 3.9 MB | 4.6 MB | 7.5 MB |

(10 frames gave 2.3 MB of state: short windows miss slow state. "Constant" still holds state written outside the
window.) ~97 % of the state is in traced heap blocks, mostly raw arrays (no vptr). The main thread carries most
of it (1.7 MB of 2.3 in the 10-frame run); two guest threads (priority 44) only scratch / output (render
workers, by their look).

**Who reads the state** (the reader, else its nearest caller with a placed label), Mario vs DK: unlabelled core
1,702 KB, `nn` 798 KB (ui2d: `nn::ui2d::Animator`, `AnimTransformBasic`, `Layout`, `Bounding`; vfx), `nu` 298 KB,
**`app` 153 KB**, exports 68 KB. The same shape in the other two (app 170 / 173 KB; nu 284 / 559 KB).
- The largest reader, 1.1 MB, `f_71038ffa80 <- f_71038fedf0 <- f_71038fec40 <- f_7103747820` (`<- nnMain`: the
  main loop, which the safe point's return address 0x710374a0d4 lies in); its neighbour `f_71038fe340` writes
  ~950 KB. It reads thousands of small blocks (40-120 bytes, many 35-55: strings?) all over the heap.
  **Hypothesis: the Lua VM's incremental garbage collector.** main holds Lua ("Lua 5.", "__gc",
  "collectgarbage") and **1,075 exports take a `lua_State*`, the CPU AI (`app::ai::*`)**. Not proven.
- The UI (`nn::ui2d` layout animation) keeps state across frames: state, but not simulation.
- Code 0x7103700000-0x71039c8440 has no anchor (no vtable, no export): the main loop, Lua?, the allocator, libc.

### 2026-11-11 — who consumes the state: code categories and frame phases (runs `m5_*`)

Tracer additions (`hle_memtrace.c`, format MT5): per line, the categories of the code that read a value carried from
an earlier frame (`cat_r`: every such read, not only the first) and of the code that wrote it (`cat_w`), from a
table of ssbu.exe's code (`research/tools/code_cats.py` -> `SSBU_MEMTRACE_CATS`: app, nn, nu, lib, sdk, lua2cpp
scripts 0x7200000000-0x7262000000, plugins 0x7262000000+, and region fallbacks for code with no anchor near,
marked "?": nn? 0x7100000000-0x7100300000, app? 0x7100300000-0x7103600000, nu? 0x7103600000-0x71038f0000, core libs?
0x71038f0000-end, read off the anchors' layout); plus the frame's phase: the logic phase runs from player 1's pad
read (`hle_hid.c` -> `rt_mt_poll`) to the frame end, split into the polling (main) thread and other threads.

The trace is reproducible: the reference match traced twice gave 4,117 and 4,103 KB of state, the same split.

State over 300 frames, by who reads the carried value (KB):

| | Mario vs DK | Castle 64 | Peach vs Snake |
|---|---|---|---|
| read by simulation code (app, app?, lua2cpp) | 240 | 239 | 256 |
| read in the logic phase, main thread, other code | 1,274 | 1,303 | 1,313 |
| read in the logic phase, another thread | 442 | 499 | 552 |
| written in the logic phase (main), read only outside | 385 | 591 | 489 |
| outside the logic phase, other code | 2,054 | 723 | 2,976 |

**[Corrected 2026-11-12 01:48: these figures count 0x7103540000-0x7103600000 (task workers, effects, UI) as app code; with that region apart ("engine?") the same 300-frame window gives 183 KB for Mario vs DK. Whole 60 s fights: 242-251 KB.]**

The logic-phase reads by other code are ~1.16 MB "core libs?" on the main thread and ~0.4 MB on other threads.

**That code is Lua 5.3's garbage collector.** The generated C of `f_71038ffa80` is `propagatemark`: it takes the
gray list's head from the `global_State` (+0x70), sets the object's black bit (`marked |= 4`, +9), switches on its
type tag (+8: 5 table, 6 Lua closure, 8 thread, 9 proto, 0x26 C closure) and, for a table, looks `"__mode"` up in
its metatable (key tag 0x44, a short string). Its caller chain runs from the main loop (`f_7103747820 <- nnMain`).
So ~1.2-1.6 MB of the carried state is **the Lua heap, traversed by the GC each frame**. Lua runs the CPU AI
(1,075 `app::ai::*(lua_State*)` exports). Open: which Lua states, how much is the AI's (every match so far has a CPU
player 2), and what a match without CPUs keeps.

Reading of the numbers: the simulation's own carried state (sim code + logic-phase reads) is ~1.5-2.1 MB, of
which the Lua heap is most; ~240 KB is read by the simulation's code itself. Against ~23 MB of hot CPU pages and
~10 MB of hot GPU pages in the current savestate.

### 2026-11-11 — the Lua heap is not the AI's; the other "core" reader is the audio mixer (run `m6_ai`)

Same match with 0, 1 and 3 CPUs (`research/matrix/trace.txt`: nocpu_mario_dk p2=human, base, cpu3_mario_dk):

| | no CPU | 1 CPU | 3 CPUs (4 players) |
|---|---|---|---|
| read by simulation code | 218 | 241 | 363 |
| logic phase, main thread, other code | 1,243 | 1,279 | 1,509 |
| logic phase, another thread | 418 | 436 | 530 |

- The core-libs state readers split into **Lua's GC (propagatemark and its family, ~1.15 MB whatever the CPUs:
  1,148 / 1,150 / 1,215 KB)** and other code (438 / 475 / 618 KB). No sign of Lua code running on that heap in a
  fight: only the GC walks it. The Lua heap is a permanent one, not the AI's.
- The other core reader runs on its own thread (entry sdk+0x338930 -> sdk+0x334450 -> `f_7103987e40`). Resolving
  main's PLT stubs (adrp + ldr to a GOT slot -> its JUMP_SLOT symbol): `f_7103987e40` calls
  `nn::audio::StartAudioOut / AppendAudioOutBuffer / GetReleasedAudioOutBuffer / Stop / Close`,
  `nn::os::TimedWaitSystemEvent`, `expf / logf / cosf / sqrtf`: **the game's audio mixer thread**. Its state grows
  with the players (more sounds), and is not simulation.

So, for the reference match, the carried state splits into: simulation code ~240 KB; Lua heap (GC bookkeeping,
VM-wide) ~1.15 MB; audio mixer ~0.45 MB; render and UI (outside the logic phase, nu / nn) 0.7-3 MB; the rest small.
Open: what the simulation reads through other libraries (nu calls in the logic phase: ~100 KB), and whether the
Lua heap can be left out of a fight's saves (its GC changes it every frame: marks, sweeps, frees into jemalloc,
whose metadata the simulation's allocations share).

---

## Strict oracle (2026-11-11, runs `m7_*`)

Why: the fight hash covers the fighters' status, motion, position, speed, damage and the script RNG only. A pruned
save that broke a hitbox, an item or a projectile would pass it until the error reached those fields.

1. **A raw full-memory comparison cannot be the oracle.** Upstream's replay check (`SSBU_RB_VERIFY=600,60,3`: save,
   60 frames, reference, then 3 loads and replays) with the full save: the fight hash equal on all 60 frames of each
   replay, but 435-1,053 pages differ per replay (async threads: audio, render, GPU).
2. **Addresses change from run to run** (bomas and modules elsewhere every run, same build and match): the heap's
   layout follows thread timing. The oracle and the trace must therefore run in one process: `build-trace` traces
   frames 300-539 (classes per line), then `SSBU_RB_VERIFY=600,60,3` compares memory line by line and splits each
   differing line by its trace class (`rt_mt_line_class`, hle_memtrace.c; `rb_ref_compare`, hle_rb_state.c ->
   `build\rb_verify_sim_<round>.txt`: the simulation's differing lines with both contents).
3. `research/tools/oracle.py <run>` explains each differing simulation line by a known non-simulation cause, by
   invariants (block type or site, reader / writer code, thread, memory area, bit pattern): **render** (`nu::`
   blocks, readers in nu's code), **sound** (app::SoundModule, its request manager f_71023ef100 / f_71023ef2e0, the
   audio mixer thread's code and lines), **lua-gc** / **gc marks** (Lua's GC readers; words differing only by the
   white bits 0x100 <-> 0x200), **flag flip** (another two-state epoch), **allocator** (readers in jemalloc's code
   0x7103900000-0x7103960000; pointer-only lines outside traced blocks), **thread stack** (the guest stacks' area;
   heap-allocated 64 KB stacks of site 0x710353cf48), **sync** (a lock's owner / count: chains through the SDK's
   `nn::os::LockMutex` / `std::recursive_mutex`, or blocks holding such a lock), **plugin** (code at 0x7262000000+),
   **pool handle** (f_71004ce860, read by its code: a handle release checking a pooled object's generation). What
   is left is UNEXPLAINED; it fails the oracle when it is consumed state (a carried value read by the simulation's
   code or in the logic phase), and is reported as an "unexplained output" otherwise.
4. With the **full save**, 5 matches (Mario vs DK, the same without CPU, 4 players, Castle 64 with hazards and items,
   Peach vs Snake with items), 3 replays each: fight hash equal everywhere, **strict oracle PASS everywhere**.
   Per replay: 26-146 differing simulation lines, all explained (sound and thread stacks the most), plus ~18,000
   "gc marks" lines in the replays where the Lua GC's cycle came out at another point. Unexplained outputs: 0-9.
   Two false alarms on the way: an item match's "RNG-like" block was mutexes (`nn::os::LockMutex` reads them), and a
   counter 2 -> 3 was a pool handle's generation.
5. Caveat: the rules were written from these runs; each new kind of match may bring a new cause. A new
   UNEXPLAINED line is to be understood before a rule is added, never silenced.

This is the reference the pruning experiments are judged by: a pruned save must keep the fight hash and the strict
oracle's PASS on the same matches.

---

## Pruning experiments (2026-11-11)

`SSBU_RB_SKIP_NONSIM` (hle_rb_state.c, `gpu_set_refresh`): once the access trace window is over (`rt_mt_done`), every
alias page with no line the simulation needs joins the left-out set (`sm_skip`: not copied at a save, not put back at
a load). `=1` keeps the pages holding any state line (a carried value, whoever reads it) or a line the simulation
wrote; `=2` keeps only the pages holding consumed state (read by the simulation's code or in the logic phase).
Only the alias area (game heap and GPU memory) is pruned; the heap, stacks, thread-local and module data stay whole.
`research/tools/strict.sh <out> <match> VAR=...` runs one strict-oracle experiment.

| Exp. | Save | Test | Kept (alias) | Result |
|---|---|---|---|---|
| E1 | `NONSIM=1` | replay check, Mario vs DK | 3,356 pages, 13 MB (of 536,337) | hash equal x3, **strict oracle PASS** **[Corrected 2026-11-12 15:15: vacuous. In a replay check the state map is off, and the load copied every written alias page whatever the left-out set (the logs show ~5,400 pages copied back, as without pruning): this pruning was never applied. Fixed in hle_rb_state.c; see the entry of 15:15.]** |
| E2 | `NONSIM=2` | replay check, Mario vs DK | 1,444 pages, 5.6 MB | hash equal x3, **strict oracle PASS** **[Corrected 2026-11-12 15:15: vacuous. In a replay check the state map is off, and the load copied every written alias page whatever the left-out set (the logs show ~5,400 pages copied back, as without pruning): this pruning was never applied. Fixed in hle_rb_state.c; see the entry of 15:15.]** |
| E3 | `NONSIM=2` | ring 600,6,8,150 rotate, 60 s, 6 matches | 1,371-2,000 pages, 5-7 MB | **all 6 crash at the first rollback** |

E3: the main thread reads address 0x7f4 (a null pointer + 0x7f4) in main+0x8dc80 <- 0x89bd0 <- 0x89940 <-
0x356dd50 (the effect emitters' tick, upstream's presentation group 64) <- the main loop: `nn::vfx`'s code. The
effects' state is not consumed by the simulation, so `=2` left it out; after a load the restored simulation and the
effects system (not restored) no longer agree (pointers, lists, recycled objects), and the effects' tick follows a
null pointer. The 60-frame replay check (E2) did not show it; the long rollback test did. **The interdependence **[2026-11-12 15:15: the replay check had not left anything out: see E1 / E2.]**
the user expected: what the simulation does not read can still have to be restored, for the program's consistency.**

Follow-up experiments (ring 600,6,8,150 rotate, 60 s, stock 99, traced build with the window 300-539):

| Exp. | Kept | Result |
|---|---|---|
| E0 control | no pruning | **OK**: 150 loads, 149 re-run frames the same, 0 different |
| E4 | `NONSIM=1` (13-16 MB) | 3 crash in the effects' tick (same place as E3), 3 hang after the first load (no frame shown) |
| E5 | `NONSIM=1` + every GPU page (744-795 MB) | 1 crash (effects' tick), 2 hang |
| E6 | `NONSIM=3`: every page the game's code touched in the window + every GPU page (765-815 MB) | 1 crash, 2 hang |

Diagnosis (`skip_diff_report`, at the first load: the left-out pages that differ from the shadow, which kept them as
they were when left out; the allocation report written at the same moment): Mario vs DK, `NONSIM=3` + GPU,
**667 of 339,488 left-out pages changed** before the first load, 1-21 bytes each; **none GPU memory, none touched by
the game's code in the trace window**. Of them: 301 outside every traced block (jemalloc's and other allocators'
bookkeeping), 136 in the 1.7 MB frame heap made at boot, the rest scattered in pools (128 B and 144 B blocks, some
made in the fight; 100 B blocks of a render site...).

Conclusion: **a page set fixed from a time window is unsound.** Pools (effects, particles, requests) cycle through
their slots: after the window they use pages the window never saw, and the allocators' bookkeeping follows. Leaving
those out breaks the consistency of the subsystems that own them (the effects' tick follows a pointer the restored
simulation no longer agrees with; hangs). The control shows the trace and the ring themselves are fine. A pruned save
has to be decided by invariants that hold over time (allocation sites, pools, sub-heaps, types: whole pools in or
out), or the non-simulation subsystems have to be made to tolerate a load (reset on load), not by pages.

---

## Unidentified zones (2026-11-11, runs `z1`, `z2`)

**The hot heap memory outside every live block** (`research/tools/unknown.py`; the tracer now keeps the pages that
held a block freed since the match set-up: `<prefix>.freed`). Mario vs DK: 6.5 MB of the 24 MB of hot non-GPU pages
lie in no live block. Of it: **4.7 MB on pages where a block was freed during the fight** (churn: memory used and
given back; the last frees' sites are the render engine's per-frame allocations, site 0x710386fd20, 0x71037df790,
and 64 KB thread stacks, site 0x710353cf48); ~0.95 MB a scratch area one render function (`f_710386fba0`) rewrites
every frame; 0.28 MB in the first 64 KB of 2 MB chunks (jemalloc's chunk headers); 5.3 MB of the 6.5 not touched by
the game's code in frames 300-539. So the "5 MB outside any block" of the first attribution is mostly render
churn, not another allocator's objects.

## The reader (2026-11-11, runs `r2`-`r6`)

Runtime `runtime/hle_state_dump.c` (`SSBU_STATE_DUMP=<file>[,<every>[,<first>[,<last>]]]`, `matrix.py --state`): at
each fighter's frame line (where the fight hash reads its values), that fighter's boma, every module (0x900 bytes)
and one level behind the modules' first words; with the first fighter, every other live battle object found in the
battle objects' pools. Tools: `research/tools/fields.py` (the field dictionary), `research/tools/reader.py` (decode,
summary, JSON lines, cross-check with the fight hash log). Map: `research/map/gamestate_map.json` (version 0).

- **Field dictionary from the game's own getters**: each `lua_bind` getter gives a method's vtable slot; the slot's
  function in a module's own vtable, when it is a plain load (`ldr ... [x0, #off]; ret`), names a field. 170 plain
  fields for a fighter's modules (StatusModule status_kind +0x98, situation_kind +0xdc; MotionModule motion_kind
  +0x68, frame +0x70, rate +0x7c; AttackModule active_part_num +0x84, power_mul...; StopModule hit stop; Shield,
  Team, Capture, Control, Search...); 1,500 getters are code. By hand: PostureModule pos at +0x30 (x, y, z),
  DamageModule damage = f32 at [module + 0x18].
- **The dictionary is per class**: a weapon's modules are other classes than a fighter's (same slots, other
  functions): the reader picks the vtable by each module's vptr. (With the fighter's vtable a weapon showed 113
  "active hitboxes".)
- **Battle objects live in pools made once a match** (the map): fighters 24 slots of 63,808 bytes, boma at
  slot + 0x400; weapons in a 6.1 MB pool. A free slot's id is 0x50000000; a fighter's articles are made with it and
  wait with status -1 (28-37 inactive per match). The runtime finds the pools by their allocation site (a light
  path in the allocator's wraps) and scans them by the boma's shape. Asking only the objects the scripts look up
  (`sv_battle_object::module_accessor`) saw 1 weapon; the pools give all.
- **Cross-check: exact.** 6 matches (Link vs Samus, Peach vs Snake, 4 players, Castle 64, Ice Climbers vs
  Villager with Nana as a third fighter, Rosalina vs Inkling), 141 sampled frames each: status, motion, motion
  frame, position x / y and damage of every fighter equal to the game's getters, 0 different (282-568 values per
  field and match). 77-99 named fields per object.
- **Items never appeared in any test match**: captures over 60 s of an "items on" match show none, and a
  whole-heap scan finds no object of category 4 (or 2, 3). `items=on` sets the rule's appearance value only (the
  item list is probably empty). Every "items" run so far was a run without items: to fix before any claim on items.
  The captures also show Castle 64's stage moving: stage state exists and is not read yet.
- Pitfalls: `fseek` / `ftell` take a 32-bit `long` on Windows: patching a record's header in a file past 2 GB
  corrupted its start (records are now put together in memory and written once). A script named `types.py` shadows
  Python's module.

### 2026-11-11 — how much of the simulation's state the reader names (run `c1`)

`research/tools/coverage.py <run>` (one run of build-trace with the access trace, the allocation trace and the state
dump): each line of state read by the simulation's code is placed in a battle object's module (named by the
dictionary or not), elsewhere in a pool slot, or outside the battle objects.

Mario vs DK, frames 300-539, 224 KB of state read by the simulation's code:

| Where | KB |
|---|---|
| outside the battle objects | 190 |
| fighters' modules, not named | 14 |
| fighters' pool slots, outside the modules | 13 |
| fighters' modules, named fields | 5 |

- **The battle objects hold only ~32 KB of it**; the reader names 5 KB. The modules' unnamed state is led by
  KineticModule (3.4 KB: its energies, +0x5c0 to +0xac0), ControlModule (2.8 KB), then Motion, Sound, Ground,
  ColorBlend, Posture, Status...: the targets for the dictionary's next fields (the getters that are code).
- **96 KB of the 190 is one table**: a 426,704-byte block (site 0x71026054bc) reached through the global at
  0x710532f490: 1,024 entries of 0x1a0 bytes (0x68000) and a tail (fields at +0x68090, +0x680e8). One function,
  `f_710260e040` (called from app code, `f_7100522f30`), reads and rewrites a line or two of every entry each frame;
  the rest of the block is constant in the window (160 KB) or output (32 KB). What it is is not known yet (a
  per-slot table ticked every frame: effects, links or hit logs, by its size of 1,024).
- The rest outside the battle objects: 10 KB in no traced block, 9 KB in the 1.7 MB frame heap, 5 KB in a
  104 KB block (site 0x710055d1ac), then small blocks of many sites.

So O4's reader is exact on what it names but names little of the simulation's state yet: the map's next entries
are the 1,024-entry table, the modules' computed fields, the stage, and items (once a match has some).

### 2026-11-11 — the fighters' items: found and read (runs `i1`-`i6`)

The user's question: do a fighter's own items (Diddy Kong's banana, Link's bomb) appear? Test matches
`research/matrix/items.txt` with a new input sequence `research/seq/downb.seq` (down + B, then A, again and again;
`matrix.py --seq downb`).

- **Yes, and they are items (category 4), not weapons.** Captures show Link caught in his bomb's explosion.
- The first scans saw none, for a plain reason: **an item's boma is 8-aligned** (0x...40a8) and the scans stepped
  16 bytes. Found by asking the game: `ItemManager__get_num_of_active_item_all_impl` and
  `ItemManager__get_active_item_impl(manager, index)` (called on the main thread at the first fighter's frame line)
  give each active `app::Item`; its word at +0x20 points to its boma, inside the Item at +0x98 (vptr 0x71050757a0,
  id 0x40000000).
- The state dump now takes the items from the ItemManager (the game's own list) and the other objects from the
  pools (scanned in 8-byte steps, categories 0-3). The reader follows the bomb and the banana: held near the fighter
  (status 2, no hitbox), then thrown (status 5, 1-2 active hitboxes), 40 and 54 samples; the fighters' cross-check
  with the game's getters stays exact (285 values a field).
- A guess that cost time: a "loose" scan for any word that looks like a category 4 id matched floats (0x44200000 =
  640.0) and pointers. Asking the game's own manager was the short way.
- Still open: the stage's items (the rule's item list) never spawn with `items=on`; the reader tolerates a last
  record cut by the run's end.

### 2026-11-11 — the reader on matches it never saw (O3, run `u1`)

`research/matrix/unseen.txt`: 8 matches the reader was never run or tuned on (Pikachu / Fox, Olimar / Steve,
Isabelle / Pac-Man, Ness / Kazuya, Bowser Jr. / Duck Hunt, Sonic / Zelda on Castle 64, Cloud / Ryu, and Kirby /
Ganondorf / Yoshi / Luigi), 142-145 sampled frames each, no setting changed.

- **Cross-check exact on all 8**: status, motion, motion frame, position x / y and damage of every fighter equal
  to the game's getters (284-576 values a field and match, 0 different). With the 6 matches before: 14 matches,
  28 fighters' classes of modules read by the same dictionary.
- Items appear by themselves with Olimar / Steve (9 samples) and Isabelle / Pac-Man (32).
- **Stage objects exist as battle objects**: Castle 64 shows 4 live objects of category 3 (gimmick) a frame. The
  16-byte scans had missed them (8-aligned, as the items): the stage's moving parts can be read as the fighters are.
- The unknown 1,024-entry table (0x1a0 bytes each, global 0x710532f490): every entry has a line or two written
  every frame at fixed offsets (+0x80, +0x140, +0x160) and read the next, in the logic phase, from the battle
  objects' update (`f_710135ca00 <- ... f_710260e040`, which calls fmodf, log2f, sqrtf). Part of the simulation's
  frame by where it runs; what it holds is still not known.

### 2026-11-11 — the 1,024-entry table, stage items, and the automatic check of the named fields

**The 1,024-entry table is the stage's presentation, not gamestate (as far as the fight hash sees).** **[Corrected 2026-11-12 05:18 / 05:44: not presentation: by the code reading a spatial grid of the stage's collision lines; carried from frame to frame; perturbing it changed nothing in the fight.]**
- Its global is read twice by the game: the table is `[[0x710532f490]]` (my first dump followed one load only and
  showed unrelated heap). Dumped whole at the end of three matches (`<dump>.table`): empty entries are all alike
  (-1 sentinels at +0x24, +0x84, +0x94, +0x98, +0xf4, +0x154, +0x164, +0x168); **entries in use: 1 on Final
  Destination, 736 on Castle 64, 728 on Battlefield**, the same with 2 or 4 players: it follows the stage.
- **Perturbation test** (`SSBU_POKE_TABLE=<fight frame>`: every word of its three per-frame lines that is neither 0
  nor -1 gets bit 0x00400000 flipped): 4,043 words changed on Battlefield and 5,458 on Castle 64 at frame 600, and
  **the fight hash log stays identical for the ~850 frames after** (status, motion, position, damage of the fighters,
  the script RNG), fighters standing on Castle 64's moving parts included. Limit: the hash sees the fighters only.
- The functions that use it (10, none exported) lie at 0x7102603310-0x7103180fa0, code with no class names.

**Stage items.** `SSBU_GIVE_ITEM=<fight frame>,<item kind>[,<every>]` hands player 1 an item through the game's own
`ItemModule__have_item_impl(boma, kind, 0, 0, false, false)`. Kinds 1, 5, 9, 14, 20, 30, 45 all work: captures show a
round shield-like item (1), a golden ball (5), and Mario turned to metal at once (20: the metal box, consumed: 2
samples); the reader follows them held (status 2) and thrown (5). An item's boma is taken from the Item's word at
+0x20 with no shape test (an item may lack modules a fighter has: kind 5 failed the posture test). Test matrix
`research/matrix/give.txt`. The rule's own spawning (items falling on the stage) is still not obtained.

**Automatic check of every named field** (`research/tools/verify_fields.sh`; `SSBU_VERIFY_FIELDS`, `reader.py
--verify`). After each object's record the runtime calls the game's getter of each named field (on the main thread,
at the frame line) and writes its answer; the reader compares it with its own reading of the raw bytes.
- A getter is called only when its slot's function **in the object's own class** is a plain load and a return: the
  first try called all 170 getters on every object and crashed (the same getter is other code in a weapon's class).
- **It found a wrong field at once**: `StatusModule.is_situation_changed`, named at +0xdc like `situation_kind`. Its
  getter works on what the slot returns. The dictionary now takes a getter only when it is a pure relay (the slot's
  call is its last act: `br`, or `blr; ldp; ret`): 169 fields.
- After the fix, six matches (fighters, weapons, Castle 64's gimmicks, 4 players, Diddy Kong's banana, a stage item):
  **1,213,479 values equal, 0 different**; 279-420 (class, field) pairs a match, each always equal. The fighters'
  cross-check with the fight hash stays exact.
- Rule from now on: `verify_fields.sh` passes before and after any change to the dictionary.

### 2026-11-11 — naming more fields: patterns give little; the probe (runs `pr1`, `pr2`)

- **Patterns**: of the getters that are not plain loads, only 3 follow "the slot returns an address inside the
  module, the getter loads a member" (PostureModule pos_x / pos_y / pos_z at +0x30 / +0x34 / +0x38: what was entered
  by hand); 5 return a structure's address; ~1,000 slot functions are code.
- **The probe** (`runtime/hle_memtrace.c` `rt_mt_probe_begin / _end`: every access of the calling thread, exactly;
  `SSBU_PROBE_FIELDS=<list>,<fight frame>` in build-trace; `fields.py --probe-list`; `research/tools/probe.py`):
  each read-only getter taking the boma alone (name `get_` / `is_` / `has_` / `can_`, or a known plain field: 294) is
  called once on each fighter and its reads are placed (boma, a module and offset, another block).
  - Getters that are not read-only stop the game: `AreaModule::force_update` (the first list took every method
    taking the boma alone), then LinkModule's getters of a parent or a constraint target (a lone fighter has none),
    `LinkModule::is_change_model_constraint_matrix` (skipped by index: `research/map/probe_skip.txt`).
  - 4 fighters probed (Mario, DK, Link, Samus): **167 fields of the static dictionary found again at the same
    offsets** by observing the reads: an independent confirmation.
  - 11 "new" single-place getters are **not added**: booleans that were 0 at the probe (0 equal to 0 proves nothing)
    and `SlowModule::is_slow`, which reads `rate` (already named) and compares. They would not pass the automatic
    check as it stands (it calls a getter only when its slot is a plain load).
  - What the code getters read: 151 calls read several places of their module, 228 read other blocks. GroundModule's
    getters (`get_down_pos`, `get_touch_flag`, `can_entry_cliff`...) read a 616,000-byte block: the stage's **[Corrected 2026-11-12 02:22: not the stage's collision. The block is a pool of 350 per-object ground-collision records of 0x6E0 bytes; GroundModule + 0x28 points at its object's record (fighter: record 0, weapons: records 1-9, seen in a dump; the code that makes the pool sets 350 and zeroes 350 x 0x6E0 bytes). See the entry of 02:22.]**
    collision data, by what reads it. `research/map/getter_regions.json`: module -> byte offset -> getters reading it.
  - **Reach of this method**: the bytes of a fighter's modules read by at least one such getter total 972 (plain
    fields: ~600), against ~19 KB of module state the simulation reads (coverage run `c1`). The getters that take
    only the boma name about 1 KB. The rest sits behind getters with arguments (WorkModule's ids, KineticModule's
    energies, the hitboxes by index) or behind none.

### 2026-11-11 — the rest of the state outside the battle objects (run `c2`)

`research/tools/outside.py <run>`: Mario vs DK and Castle 64, 96 KB each of state read by "simulation" code outside
the battle objects and the stage table, in ~265 groups (a long tail: the largest 10 KB): 31-32 KB in blocks made at
boot, 53-54 KB at the match load, 10-11 KB in no traced block. The largest readers are not simulation: the effect
emitters' tick (`f_710356dd50`, upstream's presentation group 64) reads 10-11 KB of the 1.7 MB frame heap and 6 KB
of a 104 KB block. **The region heuristic counted 0x7103540000-0x7103600000 as app code**; it holds the task workers'
kick, the effects' tick, the UI and lighting callees upstream leaves out of re-run frames: now its own category
("engine?", `code_cats.py`). The stage's collision block (616,000 bytes, site 0x7102606480) carries 2 KB of state **[Corrected 2026-11-12 02:22: not the stage's collision. The block is a pool of 350 per-object ground-collision records of 0x6E0 bytes; GroundModule + 0x28 points at its object's record (fighter: record 0, weapons: records 1-9, seen in a dump; the code that makes the pool sets 350 and zeroes 350 x 0x6E0 bytes). See the entry of 02:22.]**
on both stages.

## Pruning by invariant (A)

`SSBU_RB_SKIP_SITES=<allocation site>[,...]` (hle_rb_state.c, with a light path in hle_alloc_trace.c's wraps): the
blocks allocated by calls returning to those addresses are left out of a fight's saves and loads, whole pages of
them, from their allocation to their free. A site is an invariant of the code, not a set of pages seen in a window.

| Exp. | Left out | Test | Result |
|---|---|---|---|
| E7 control | nothing | ring 600,6,8,150 rotate, 60 s, 3 matches, one-page groups | 149 same / 0 different each |
| E7 | site 0x7103816ef4: the two 16 MB render command arenas (`nu::RenderCommandBase`), 8,190 pages, 31 MB | same | **149 same / 0 different each, no crash, no hang** |

Cost (normal build, this PC, one run each: timings indicative):

| Match | pages copied a save: control -> E7 | memory part of a save | save mean | load mean |
|---|---|---|---|---|
| Mario vs DK | 1,213 -> 1,180 | 1.59 -> 1.38 ms | 7.77 -> 7.45 ms | 0.84 -> 0.73 ms |
| Link vs Samus | 1,514 -> 977 | 1.79 -> 1.71 ms | 4.81 -> 4.78 ms | 0.87 -> 0.79 ms |
| Castle 64 | 1,331 -> 964 | 1.41 -> 1.36 ms | 3.36 -> 3.37 ms | 0.66 -> 0.63 ms |

- **The first pruning that survives the long rollback test**: what the page-window sets (E3-E6) could not do.
- **The gain is small, and that says where the time is.** Mario vs DK, a catch-up of 1-8 frames: per re-run frame
  the game itself takes 1.7-2.2 ms, the save's memory part 0.45 ms (frames not kept) to 1.67 ms (the last one), the
  rest of a save ~1.1 ms, a load 0.3-1.3 ms; a whole catch-up 11.3 ms (control) against 10.7 ms. **Copying memory is
  a minor share of a rollback here: re-running the frames is the larger one.** A lighter state can win at most the
  memory part (~1.5 ms a save); making rollback much lighter means making the re-run frames cheaper too.
- Not done yet for E7: the strict oracle (build-trace), more matches, 4 players.

| Exp. | Left out | Test | Result |
|---|---|---|---|
| E7 strict | site 0x7103816ef4 | strict oracle (trace 300-539, replay check at 600, 3 replays), Mario vs DK and Castle 64 | fight hash equal x3 each, **strict oracle PASS** on both **[Corrected 2026-11-12 15:15: vacuous. In a replay check the state map is off, and the load copied every written alias page whatever the left-out set (the logs show ~5,400 pages copied back, as without pruning): this pruning was never applied. Fixed in hle_rb_state.c; see the entry of 15:15.]** |
| E8 | + site 0x71037f4e94 (~230 blocks of 131,072 bytes, 60 MB) | ring 600,6,8,150 rotate, 3 matches | **fails**: 1 crash, 2 hangs |
| E9 | + sites 0x71037df790, 0x71037de8d4 (render blocks freed during the fight) | same | stopped: holds E8's site (1 crash seen) |

E8's crash is on the runtime's own GPU thread (host pc ssbu.exe+0x7738, thread "gpu"), reading an address in those
blocks: site 0x71037f4e94 holds data the renderer reads after the load (buffers the queued commands point to). Left
out, the restored state and what the GPU thread follows no longer agree. **Being the render engine's is not enough to
be left out: what the host's GPU thread reads has to stay consistent with the restored commands.** Only the command
arenas (site 0x7103816ef4) are shown safe so far: long rollback test on 3 matches and the strict oracle on 2. **[2026-11-12 15:15: the strict oracle part was vacuous (the replay check left nothing out); only the ring results stand.]**

Where A stands: one site left out (31 MB of address space, 3-36 % fewer pages copied a save, ~0.2 ms off the
memory part). Each further site needs the same two tests, and the gain is bounded by the memory part (~1.5 ms).

## Where a rollback's time goes: the re-run frames (2026-11-11, runs `e7_control`, `lite63`, `lite127`)

Upstream's own profile of the frames run again (ring 600,6,8,150 rotate, 60 s; normal build, this PC, one run each):

| Part of a re-run frame | Mario vs DK (FD) | Link vs Samus (BF) | Castle 64 |
|---|---|---|---|
| safe point -> pad poll | 0.47 ms | 0.36 | 0.30 |
| pad poll -> frame end (the logic frame) | 0.69 | 0.70 | 0.66 |
| the frame end call | 0.60 | 0.23 | 0.10 |
| its save, memory part (frames not kept / the last one) | 0.45 / 1.67 | 0.49 / 1.80 | 0.40 / 1.47 |
| whole catch-up (1-8 frames back, mean) | 11.3 ms | 9.4 | 7.7 |

- **The logic frame is ~0.7 ms**; a re-run frame costs 1.1-1.7 ms of game time, so 40-60 % of it is not the logic
  frame (what runs before the pad poll, and the graphics frame end), and its save adds 0.4-0.5 ms.
- Leaving more of the presentation out of re-run frames (`SSBU_RB_LITE=63`: + UI and lighting; `127`: + the effect
  emitters' tick) **passes the long rollback test on the 3 matches (149 same / 0 different each) but gains
  nothing measurable**: the part before the pad poll stays 0.30-0.46 ms, the catch-up 7.7-11.1 ms. What fills that
  part is not those callees. (Upstream keeps 64 in: effects made in re-run frames and never ticked crashed there;
  not seen in these 3 runs, which proves little.)
- Not known yet: what runs in the 0.3-0.5 ms before the pad poll and in the frame end call (0.1-0.6 ms, the
  largest on Final Destination). A time profile of a re-run frame by function is the next tool.

### 2026-11-11 — a time profile of the re-run frames (runs `prof1`, `hide1`, `prof2`)

Upstream's sampling profiler gated to the frames run again (`SSBU_RB_PROFILE=<seconds>`: every 0.2 ms, only while
`rb_fast` is set), on a rollback-heavy ring (600,3,8,600 rotate). The sampler suspends threads, so shares are
indicative; the ring's own timings below are the measure.

1. **The ring test draws the frames it runs again, and the main thread waits for the GPU.** Without
   `SSBU_RB_RING_HIDE`, 86.9 % of the main thread's samples are inside the graphics frame end (`FRAME_END`
   0x71038701e0 -> sdk+0x427010, an NVN wait loop reading the clock: `NvOsGetTimeUS` 65.7 %, `TickManager::
   ConvertToTimeSpan` 12.7 %) while the runtime's GPU thread draws (38.8 % busy). The game's task tree walk (the
   logic) is 2.8 %, the saves 4.6 %. **My earlier "frame end call 0.10-0.60 ms" was that wait**, not game work.
2. **With `SSBU_RB_RING_HIDE=1`** (catch-up frames not drawn but the last, as a net catch-up), ring 600,6,8,150:

   | Match | catch-up, drawn -> hidden | a re-run frame: before poll / logic / frame end |
   |---|---|---|
   | Mario vs DK | 11.3 -> 8.4 ms | 0.47 / 0.66 / 0.60 -> 0.04 ms |
   | Link vs Samus | 9.4 -> 8.4 ms | 0.35 / 0.70 / 0.23 -> 0.04 ms |
   | Castle 64 | 7.7 -> 7.4 ms | 0.31 / 0.66 / 0.10 -> 0.04 ms |

   149 same / 0 different on each. **Every rollback timing before this entry was taken with the frames drawn: the
   hidden figures are the ones that stand for netplay.**
3. **Profile with the frames hidden** (main thread, inclusive shares): the frame end 36 % (the last frame of each
   catch-up is drawn, and waits for the GPU as above); the saves 25 % (`sync` 23 %, of which `settle_range` 12.7 %:
   pages the game committed or decommitted); the task tree walk (the logic frame) 12 %; the effect emitters' tick
   6.9 %; the task workers' fibers 6.7 %; **Lua's GC step 5.7 %** (`f_71038fec40 -> f_71038fedf0 -> f_71038ffa80`).
   So in a catch-up the simulation proper is about an eighth of the main thread's time; waiting for the GPU on the
   frame shown and saving are the two largest shares.

Levers this points to, none tried yet: the GPU wait at the shown frame's end; the saves' settle work; Lua's GC
step and the effects' tick in frames run again (each changes memory the saves hold: to be judged by the long
rollback test and the strict oracle).

### 2026-11-11 — lever 3: the Lua GC step left out of the frames run again (runs `gc0`-`gc1b`, `gcB`, `gcC`)

`runtime/hle_research_wraps.c`, `SSBU_RB_SKIP_LUA_GC=1`: a wrap of FUN 0x71038fec40 (Lua 5.3's `luaC_step`; 514 call
sites) that returns at once only for the main loop's own call (return address 0x71037480c0) and only in a frame
run again (`rb_fast > 0`). Ring 600,6,8,150 rotate with `SSBU_RB_RING_HIDE=1`, 60 s, 3 matches, each configuration
run twice:

| Match | logic part of a re-run frame: kept -> left out | catch-up: kept -> left out |
|---|---|---|
| Mario vs DK | 0.63 / 0.64 -> 0.50 / 0.52 ms | 8.2 / 8.2 -> 7.5 / 7.7 ms |
| Link vs Samus | 0.69 / 0.68 -> 0.54 / 0.54 ms | 8.5 / 8.3 -> 7.6 / 7.5 ms |
| Castle 64 | 0.66 / 0.66 -> 0.53 / 0.52 ms | 7.4 / 7.3 -> 6.7 / 6.7 ms |

- **About 0.13-0.15 ms off each re-run frame (~20 % of its logic part), ~9 % off a catch-up**, the same in both
  series. The GC step was counted inside the "logic" part: the game's logic proper is ~0.5 ms a frame.
- Correctness: every re-run frame equal to its first pass (149 / 0 on each of the 12 runs). And **the whole fight is
  the same with the step kept or left out**: two runs with the same rollback schedule (`gcC` kept, `gcB` left out)
  give identical fight hash logs over 8,746-8,748 lines (60 s, both fighters, the script RNG) on the 3 matches.
- A comparison that was wrong: a run without rollbacks against a run with them. The hash log numbers the frames
  run again too, so the two files shift at the first rollback and differ from there (5,882 "differences" that
  were an offset). Comparable runs have the same rollback schedule.
- Not done: the strict oracle (its replays do not set `rb_fast`, so the switch would not act there as it is);
  matches with Lua-heavy content, if any; the effect on memory (Lua's heap grows until the next steps catch up).
- In netplay only one game may roll back: its GC then runs behind the other's for a few frames. The fight hashes
  above say the fighters and the RNG do not depend on it; the heap's layout may differ between the two games
  (it already does: addresses differ from run to run).

### 2026-11-11 — the Lua GC trial closed (runs `lua_strict`, `luaheap0/1`, `luaall0/1`)

- **Strict oracle**: the replay check's replays run at normal speed (`rb_fast` 0), so `SSBU_RB_SKIP_LUA_GC=2` also
  leaves the step out there (`rb_verify_replaying`, hle_rb_core.c). Mario vs DK and the 4-player match with three
  level 9 CPUs: fight hash equal on the 3 replays, **strict oracle PASS** on both. The "unexplained outputs" (lines
  the simulation writes and does not read back; reported, not a failure) are 6 and 31 there, against 0-9 with the
  step kept: not looked into.
- **The Lua heap does not grow**: `SSBU_LUA_HEAP_LOG` (global_State's totalbytes + GCdebt at the main loop's call)
  reads **1,656 KB at every sample**, step kept or left out, over 2,050-2,425 rollbacks of 1-8 frames in Mario vs DK
  and the 4-player match (runs stopped by the 900 s limit before their 180 s of fight, two games at a time; every
  re-run frame the same). Nothing allocates on that heap in a fight: the step it runs has nothing to collect.
- **13 matches** (the v1 matrix: 4 players, level 9 CPUs, Nana, Luma, Steve, Castle 64...), ring 600,6,8,150 rotate,
  hidden, 60 s: 149 same / 0 different on all, step kept and left out; and the whole-fight hash logs of the two
  configurations are identical on all 13.
- Verdict: leaving the main loop's Lua GC step out of the frames run again is safe on everything tried, and takes
  ~0.14 ms off each (~9 % of a catch-up). Off by default; a candidate to propose upstream.

### 2026-11-11 — resynchronised with upstream; timings with the catch-up frames hidden (run `t2`)

Merge of upstream/main (22 commits, to f6831ef; among them #305 "the ring's shadow shares the fight's cold pages with
memory" and #306 "input delay: one frame less") into `gamestate-research` (52a4c37): one conflict (hle_hid.c, two
lines added at the same place). No change to recomp.h or the lifter: runtime only recompiled, both builds. After it:
the determinism gate (2,836 lines the same), the rollback oracle (49 / 0), `verify_fields.sh` PASS.

Reference timings from now on: ring 600,6,8,150 rotate, **`SSBU_RB_RING_HIDE=1`**, one-page groups, 60 s, one game at
a time (normal build, this PC, one run each):

| Match | catch-up mean (max) | re-run frame: before poll / logic / frame end | its last frame: game / hold + GPU / memory / rest | normal-frame save mean (max) | load |
|---|---|---|---|---|---|
| Mario vs DK | 8.3 (21.8) ms | 0.46 / 0.65 / 0.05 | 1.22 / 0.22 / 1.59 / 1.05 | 7.62 (24.5) | 0.76 |
| Link vs Samus | 8.5 (23.8) | 0.36 / 0.70 / 0.04 | 1.17 / 0.23 / 1.88 / 0.46 | 4.91 (21.9) | 0.86 |
| Castle 64 | 7.4 (21.0) | 0.30 / 0.67 / 0.04 | 1.09 / 0.23 / 1.40 / 0.27 | 3.33 (19.4) | 0.66 |
| 4 players | 10.7 (33.4) | 0.49 / 0.92 / 0.04 | 1.52 / 0.40 / 2.11 / 0.56 | 6.06 (27.1) | 1.09 |

### 2026-11-12 — the GPU wait is the cost of showing a frame, not of a rollback (runs `feA`-`feD`)

`SSBU_FRAME_END_TIME=1` (hle_research_wraps.c) times the graphics frame end by kind of frame, 40 s fights:

| Run | normal frames | run again unseen | first frame end after a catch-up |
|---|---|---|---|
| no rollback, uncapped: Mario vs DK / Castle 64 | 6.70 / 1.02 ms | - | - |
| ring hidden, uncapped | 4.77 / 0.83 ms | 0.047 / 0.041 ms (max 1.5) | 0.050 / 0.047 ms (max 0.1) |
| ring hidden, normal speed | 13.4 / 14.4 ms | 0.049 / 0.045 ms | 0.047 / 0.049 ms |
| no rollback, normal speed | 15.1 / 15.4 ms | - | - |

- The frame end is where a normal frame waits: for the GPU when uncapped (6.7 ms on Final Destination, 1.0 on
  Castle 64), for the display at normal speed (13-15 ms of a 16.7 ms frame). **In a catch-up it costs 0.05 ms a frame,
  the frame after it included.** The wait is not a rollback cost.
- **The "36 % waiting for the GPU" of the gated profile was an artefact**: the sampler suspends the threads it
  samples, the GPU thread among them, and the main thread then waits for it. The shares of that profile are not to
  be used; the direct timings are. "Lever 1" does not exist. What the profile said of the saves ("settle_range
  12.7 %") is to be checked the same way before any work on it.

### 2026-11-12 — the saves' memory part, measured directly: no commit / decommit work (run `t2`)

The queue's step 4 was to reduce the saves' work on pages allocated and freed every frame, from the gated profile's
"settle_range 12.7 %". The saves' own timings (the logged `SAVE` lines of run `t2`, 13-15 a match) say otherwise:

| Match | pages copied | memory part | write-watch questions | steady pages' comparison | copies | watched areas | (de)commits |
|---|---|---|---|---|---|---|---|
| Mario vs DK | 1,213 | 1.58 ms | 0.73 | 0.36 | 0.11 | 0.10 | 0.007 |
| Link vs Samus | 1,568 | 1.99 ms | 0.91 | 0.45 | 0.20 | 0.10 | 0.000 |
| Castle 64 | 1,104 | 1.40 ms | 0.69 | 0.28 | 0.10 | 0.10 | 0.000 |
| 4 players | 1,812 | 2.19 ms | 0.89 | 0.57 | 0.20 | 0.10 | 0.000 |

- **One logged save of 56 had a commit or a decommit to settle; that work is ~0 ms.** The profile's share was the
  sampler's artefact again (second time: the gated profile is not to be trusted for shares). **Step 4 has no object.**
- What the memory part is made of: **asking the write watch which hot pages changed (0.7-0.9 ms, ~105 calls a
  save) and comparing the steady pages with the shadow (0.3-0.6 ms): 70-80 % of it. Copying the changed pages is
  0.1-0.2 ms.** Finding what changed costs 5-10 times what copying it costs.
- So a smaller state saves little by itself (the copies are already cheap), and E7's gain was small for that
  reason. What would cut the memory part is asking about fewer runs of pages and comparing fewer steady pages: a map
  that says ahead of time which pages can hold changing state, by invariants, is what could do that.

### 2026-11-12 00:26 — the Lua trial's "31 unexplained outputs": two harmless causes, now named (runs `lua2_skip`, `lua2_keep`)

The Lua GC trial (2026-11-11) passed the strict oracle with 31 "unexplained outputs" (differing lines written by the
simulation and not read back) against 9 with the step kept. `oracle.py --outputs --detail` lists them by block,
writer and differing words. Both runs were made again on the current build (Mario vs DK, 3 replays each):

| Run | unexplained outputs, round 1 | in Lua blocks (1264 B, site 0x71038fb578) | outside every traced block |
|---|---|---|---|
| `lua2_skip` (`SSBU_RB_SKIP_LUA_GC=2`) | 22 | 15 | 7 |
| `lua2_keep` (step kept) | 2 | 2 | 0 |

- **The 15 lines in Lua blocks are dead slots of Lua stacks.** The blocks are arrays of 16-byte Lua values (8 bytes
  of value, then a type tag); only the tags differ, nil on one side (0) and a number or boolean on the other
  (0x13, 3, 1), the value untouched, the last writer Lua's GC (`f_71038ffa80`, propagatemark). That is Lua 5.3's
  `traversethread`: in the atomic phase the GC sets to nil the unused part of each coroutine's stack, above its top.
  With the step left out the stale values stay. Lua writes a slot above the top before reading it: no value the
  game computes depends on them. The same lines appear with the step kept (2), when the GC's phase differs at the
  save.
- **The 7 lines outside the blocks are a stack**: return addresses into jemalloc (0x71039327b0...), chained frame
  pointers 0x40-0x50 apart, touched by the guest main thread only, in heap memory (0x60c29af5c0-780) and not in the
  main stack's area (0x77...): the stack of a fiber the game made before the trace began. The frames below the stack
  pointer hold what the last deep call left: without the GC step (which frees through jemalloc) the leftovers differ.
- Two causes added to the oracle, each by an invariant, tried last (they only take lines nothing else explains):
  `lua dead slot` (Lua's site, last written by Lua's GC, only tag words differ, one side nil) and `fiber stack`
  (no traced block, one thread, a page where differing lines hold 16-aligned pointers to less than 64 KB from
  themselves). With them: **0 unexplained output in both runs, all 3 rounds; strict oracle PASS.**
- **The trial's conclusion stands**: leaving out the main loop's Lua GC step in the re-run frames changes no state
  the simulation reads.
- A trap found on the way: `oracle.py` run again on the old runs (`lua_strict`, `m7_strict3`) gave different
  counts than when they were made. The trace's code offsets are those of the `ssbu.exe` that wrote it, and
  `build-trace` had been linked again since: every function name was wrong, silently. `memtrace.load` now stops
  when `ssbu.map` is newer than the trace (`SSBU_STALE_MAP=1` to read it anyway). **A strict run is only to be
  read with the build that made it.**
- `research/tools/now.sh` gives the journal's timestamps (the PC's clock, Paris time, to the minute).

### 2026-11-12 00:31 — the reader across frames: comparison of two frames, summary of a match (run `match1`)

`research/tools/match.py`, on the reader's dump. `reader.records` now maps the file and gives the records one at a
time (a dump of every frame is 8-11 GB for a 24 s match: 6-7 MB a frame, to be deleted after use).

- `match.py diff <dump> A B`: the objects that came, went, woke or fell asleep, and for each object every named field
  that changed. Mario vs DK, frames 721 -> 722 (DK's hit lands): Mario's damage 5.04 -> 12.6, status 0x47 -> 0x48,
  hitstop 0 -> 17, `is_damage` / `is_hit` / `is_stop` 0 -> 1; DK's `active_part_num` 0 -> 3, `get_inflict` 0 -> 2,
  `SlowModule.rate` 1 -> 0.0139. Link vs Samus, 686 -> 687 (Link comes back): damage 24.3 -> 0, position
  (-93.7, -145.5) -> (0, 170), status 0x1d6 -> 0xb6, situation 5 -> 2.
- `match.py summary <dump>`: per fighter the damage taken and the hits, the damage resets (a stock lost), the share
  of time on the ground / in the air, the status changes, the frames with hitboxes out and in hitstop, the distance
  covered; per category of other object how many came to life and for how long; the events in order; `--json`.
  Mario vs DK (1,428 frames): Mario takes 35.0 % in 5 hits, DK 13.5 % in 4; 3 of 23 weapon objects came to life.
  Link vs Samus (1,426 frames): Link takes 28.7 % in 8 hits and loses a stock at frame 687; 10 of 31 weapon objects
  came to life, 15 times.
- **Checked**: on both dumps, at every frame, the fighters' status, motion, motion frame, position and damage equal
  the game's getters (fight hash log): 2,855 and 2,851 values each, 0 different. The summary is counted from those.
- **What the comparison shows of the reader's reach: of the modules' bytes that change between two frames, 1 to 3 %
  lie in named fields** (4,053 bytes changed at the hit, 44 named; 1,243 at the respawn, 40 named). The unnamed
  changes are in KineticModule (614 bytes), WorkModule (607), GroundModule (568), CameraModule (564), ControlModule **[Corrected 2026-11-12 02:03: the dump copies 0x900 bytes of each module; GroundModule's object is 368 bytes, CameraModule's 88, WorkModule's 152: most of these bytes were other objects' memory. `match.py diff` now counts each module's own object only (module_sizes.json).]**
  (489), StatusModule (415), PostureModule (353). That is the next step's list: the getters with an argument (work
  variables, speeds, hitboxes by index).
- Limits: the summary has no stock count nor timer (match-level state, not in the battle objects); a "stock lost" is
  read as damage going from above 0 to 0; the weapons' kinds are not named.

### 2026-11-12 00:54 — fields behind pointers: the getters with arguments, probed (runs `argp1`-`argp3`, `vf_args`, `match2`)

The plain getters name a field of the module object itself. The state that changes most lies behind pointers and is
asked for with an argument: `WorkModule::get_int(id)`, `is_flag(id)`, `AttackModule::is_attack(index)`.
`research/tools/argprobe.py` finds where each (getter, argument) reads its answer, by observation.

- **The probe** (`SSBU_PROBE_FIELDS`, build-trace) now passes arguments, records the word at each address read, and
  can run again every N frames (`<list>,<frame>:<every>`). 1,916 calls (20 getters of 5 modules; `argprobe.py list`)
  on each fighter of 3 matches every 30 frames: 708,920 calls.
- **The method.** A call's reads are followed from the boma as a path of offsets (the module, a pointer word in it,
  a word behind...). Every reading of a value read that gives the call's answer is a hypothesis (the value, "not
  zero", one bit...); the hypotheses are intersected over all the calls. A getter's reading, for a class of module,
  is the plainest one supported by every argument whose value changed; the arguments whose value never changed take
  it "by family" when it is among their hypotheses. A table must be regular: the offset linear in the argument, and
  below the table's own count.
- **What it found.**
  - WorkModule: module + 0x18 -> two tables (+0 the instance's variables, +8 the status's), each {count, pointer}
    three times: floats (4 bytes each, 120 and 40), integers (8 bytes each, 270 and 32), flags (32 a word, 9 and 3
    words). Ids: 0x0nnn floats, 0x1000nnnn integers, 0x2000nnnn flags; the second hex digit 1 for the status's
    table. **846 variables a fighter** (160 floats, 302 integers, 384 flags).
  - ControlModule: [module + 0x110] + 0x7c the buttons held (bit n), + 0x8c released; + 0x91 + 2n the trigger counts.
  - KineticModule: 11 energies, pointers at module + 0x30 + 0x18 n; in each + 0x30 enabled, + 0x31 suspended.
    `get_sum_speed_x / y` are sums over the enabled energies (computed: not fields; the speeds are the two floats at
    + 0x10 of each energy, not named yet).
  - AttackModule: [module + 0x68] + 0x108 + 0x130 n: hitbox n is out when not zero. HitModule: [module + 0x60].
- **951 fields** (251 seen changing, 700 by family) in `research/map/arg_fields.json`; the blocks the dump must
  hold in `research/map/state_paths.txt` (`SSBU_STATE_PATHS`: 23 paths, ~4 KB more a fighter).
- **The automatic check now covers them** (`verify_fields.sh`: the getters with arguments are called by the game at
  every dumped frame, on fighters). First run: **3 values different of 2.2 million, all in
  `ControlModule::check_button_trigger`** (read as "bit n of one word"; at one frame of the four-player match the
  game answered otherwise for buttons 0x9, 0xe, 0x13). The family was left out whole (`REJECTED`). Second run:
  **PASS, 2,166,381 values equal, 0 different, 6 matches**; of the 951 fields, 101 to 232 changed value in a match.
- **Two getters stop the game** when called blindly: `HitModule::get_status(part, index)` on Link (reads through a
  pointer that is not always there), and `WorkModule::get_int` on a weapon not in play. Both left out; the fields
  behind pointers are named and checked **on fighters only**.
- **The frame comparison with them** (`match.py diff`, Mario vs DK 721 -> 722): 52 named values change instead of
  25. The hit is now read from the victim's variables: `get_float(0x11)` 5.04 -> 12.6 (the damage), `0x12`
  25.9 -> 64.5, `0x100000f` 10.4 -> 25.8, `get_int(0x10000004)` 24 -> 30; the attacker's `is_attack(0..2)` 0 -> 1.
  `match.py diff` also counts the bytes that change behind the modules' pointers: 661 in the blocks the dump holds,
  52 named (7 %); WorkModule's tables 101 changed, 48 named (a float changes 1-4 bytes of its 4).
- **What stays unnamed**: the modules' own bytes (4,365 changed at that frame, 44 named: KineticModule 998,
  WorkModule's own 583, GroundModule 568, CameraModule 564, ControlModule 489), the energies' speeds, the hitboxes' **[Corrected 2026-11-12 02:03: the dump copies 0x900 bytes of each module; GroundModule's object is 368 bytes, CameraModule's 88, WorkModule's 152: most of these bytes were other objects' memory. `match.py diff` now counts each module's own object only (module_sizes.json).]**
  data (`get_power` takes a float and two flags: not probed), the weapons' and items' variables. The variables
  have ids, not names: the names are the game's constants (`FIGHTER_INSTANCE_WORK_ID_...`), not in this repo.

### 2026-11-12 00:58 — the speeds: the kinetic energies, checked through the game's own sums (run `vf_args`)

`KineticModule::get_sum_speed_x / _y(mask)` are computed, so the probe gave no field for them. What the calls read
(run `argp4`) gives the formula: the module holds a count (+ 0x20: 11 for a fighter) and, for energy k, a pointer
(+ 0x30 + 0x18 k) and an attribute mask (+ 0x3c + 0x18 k: 1, 1, 1, 1, 2, 4, 8, 4, 0x10, 0x10, 0x10); an energy holds
its speed at + 0x10 (x, y: two floats) and "enabled" at + 0x30. The answer is the sum, in order, of the speeds of
the enabled energies whose mask meets the argument.

- The reader names `energy<k>.speed_x / speed_y` (22 values a fighter) and computes the sums for the masks 1, 2,
  4 and 7 the same way (`reader.Reader.energies`); the automatic check asks the game for the same 8 sums at every
  dumped frame.
- **`verify_fields.sh`: PASS, 2,174,397 values equal, 0 different, 6 matches**; the sums equal the game's to the
  bit. 959 calls of getters with arguments are now checked beside the 169 plain getters.
- Not covered: three energy classes read one more byte before the speed (+ 0x70 or + 0xd0), always 0 in the
  matches probed; what a non-zero value changes is not known (the check would show it as a difference).

### 2026-11-12 01:06 — stage objects: no stable object to name on Castle 64 (runs `gim1`-`gim13`) — contradicts the plan

The step was to name the fields of the stage objects (category 3, "gimmick": 4 seen on Castle 64, run `c2`).

- **Their presence changes from run to run of the same match**: the whole-heap scan counts 0 category-3 objects in
  `gim1`-`gim5`, `gim7`-`gim12`, `p0`, `r5`, `r6`, `t1`, `vf3`; 2 in `gim6`; 4 in `c2`, `p1`, `v1`, `v2`, `vf1`,
  `vf2`, `vf_args`, `gim13`. Same settings (`hazards_castle64`), same fixed seed, and **the same fight**: the first
  1,300 lines of the fight hash log are identical in all of them.
- When they are there (`gim13`, 48 dumps of each): ids 0x30000000-0x30030000, bomas 0x300 apart in the pool of
  site 0x71014f534c (196,624 bytes), 75-77 modules each (three with a class of their own: SearchModule, AttackModule,
  AreaModule), **status -1, position (0, 0), no named field changes in 1,440 frames**; their modules' unnamed bytes
  do change (4,500 to 49,000 bytes differ from the first dump).
- So these four objects are not the stage's moving parts as the fighters see them: a fight is the same with and
  without them. The moving platform and the bumper are not battle objects; what was found of the stage's state is
  elsewhere (the 616,000-byte collision block GroundModule's getters read, site 0x7102606480; the 1,024-entry table). **[Corrected 2026-11-12 02:22: not the stage's collision. The block is a pool of 350 per-object ground-collision records of 0x6E0 bytes; GroundModule + 0x28 points at its object's record (fighter: record 0, weapons: records 1-9, seen in a dump; the code that makes the pool sets 350 and zeroes 350 x 0x6E0 bytes). See the entry of 02:22.]**
- **Two open questions, not followed here** (each is hours): what decides, outside the seed, whether these objects
  are made (a run-to-run difference in a deterministic match: on two machines of a netplay match the object sets
  could differ; no effect on the fight hash was seen in 24 s); and where the stage's moving parts keep their state. **[2026-11-12 02:03: two CPU-against-CPU runs, one with and one without these objects, are identical (hash and 822,520 named values over 50 s): their presence does not change the fight.]**
- No field named for stage objects. The reader still dumps and decodes them when present.

### 2026-11-12 01:14 — items that fall on the stage by themselves: obtained (runs `rule1`, `rule2`, `spawn1`-`spawn3`, `vf_final`)

`items=on` never produced an item: it only sets the rule's appearance value (rule header + 0x54 = 2).

- **Why**: `SSBU_RULE_DUMP=1` (new, `hle_fight_test.c`) prints the rule header at the match set-up. Right after the
  appearance value, + 0x58 to + 0x62 hold 87 bits at 0 followed by bits at 1 to + 0x8f: **the rule's item list, one
  bit an item kind, all off in this save**.
- **`SSBU_RULE_POKE=<offset>:<hex bytes>`** (new) writes bytes into the rule header at the set-up.
  `SSBU_RULE_POKE=58:ffffffffffffffffffffff` with `items=on` turns every item on: items fall from frame ~900.
  `research/matrix/spawn.txt`: Mario vs DK on Battlefield and four players on Final Destination, no fighter that
  makes items of its own.
- 40 s of Mario vs DK: 5 item objects came to life (181 item records in 131 dumps); four players: 26.
- **The reader reads them exactly**: 24,978 and 23,639 item values equal to the game's getters, 0 different.
- **Deterministic**: two runs give the same fight hash log (3,600 lines compared, both matches).
  **Ring rollback oracle with items on the stage: 49 rollbacks the same, 0 different, on both matches.**
- `verify_fields.sh` now runs seven matches (this one added): **PASS, 2,765,679 values equal, 0 different.**
- Limits: every item kind is on at once (which bit is which kind is not mapped); the default appearance level (2)
  only; the item's kind is not among the named fields.

---

## Night of 2026-11-12: the colouring again, wider tests

### 2026-11-12 01:48 — the colouring remeasured on whole fights; one row per allocation site (runs `col1`, `colw300`, `colw1200`)

The user's priorities for the night (journal read whole first): the colouring (O2) on whole fights with the corrected
code categories; a table by allocation site; Final Destination against Castle 64 for the stage's moving parts; the
long tail; the stage table's nature by a perturbation held for seconds and judged by the reader. Tests widened all
night (fighters, stages, CPU against CPU, long fights), with a coverage table in `research/map/coverage.md`.

New tools: `research/tools/sites.py` (one row per (allocation site = first two return addresses, block size), per
run the KB of touched lines by class, the blocks, when made, the guest readers and writers; `research/map/sites.md`
and `.json`), `stage_diff.py` (rows whose state differs between runs that differ by the stage),
`colour_runs.sh` (build-trace runs of `research/matrix/colour.txt`; refuses a `code_cats.bin` older than the map),
`coverage.py --lines` (every line of a fighter's modules with its class, readers, writers, named or not).
`code_cats.bin` and `build-trace` were both of 00:45, so the categories match the build.

**Whole fights** (trace window frames 30-3629, 60 s; Mario vs DK level 9 except FD level 3), KB:

| Run | sim state | logic state | other state | scratch | output | constant |
|---|---|---|---|---|---|---|
| FD, Mario vs DK | 246 | 2,620 | 4,984 | 4,463 | 7,375 | 12,676 |
| Castle 64, hazards on | 251 | 2,726 | 2,297 | 5,049 | 6,164 | 11,402 |
| Castle 64, hazards off | 248 | 2,738 | 3,118 | 4,339 | 6,561 | 11,570 |
| Battlefield, items falling (`SSBU_RULE_POKE`) | 242 | 2,748 | 3,931 | 5,406 | 6,560 | 12,466 |

("sim state": a carried value read by app / lua2cpp code; "logic state": carried, read in the logic phase by other
code, mostly Lua's GC and the audio mixer; "other state": read outside the logic phase only.)

**The window matters** (the same FD match, frames from 300): 300 frames 183 KB read by the simulation (3.9 MB of
state in all), 1,200 frames 218 KB (5.0 MB), 3,600 frames 246 KB (7.8 MB). The part the simulation reads grows
slowly and is close to stable; the whole state keeps growing (slow state shows up only in long windows). **The figure
"240 KB read by simulation" of 2026-11-11 (300 frames) counted 0x7103540000-0x7103600000 as app code; with that region
apart ("engine?") the same window gives 183 KB.** The whole-fight figure happens to come back near 240.

- **A conclusion of 2026-11-11 does not hold over whole fights**: "no hot byte is in a block made during the fight"
  (hot pages, 20 s). Over 60 s, 118-279 KB of state lie in blocks made in the fight, of which 5-9 KB read by the
  simulation, mostly 64 KB fiber stacks (site 0x710353cf48: a suspended fiber keeps its frames from one frame to the
  next), then 1,064-byte blocks of site 0x710373e524. Falling items do not add any: items live in pools made before.
- Site table, 4 runs: 6,005 rows, 1,786 with state. Labels (the main class, the same in every run): constant 4,281,
  logic state 554, mixed 437, other state 232, sim state 223, scratch 182, output 96. The largest rows with state:
  the render command arenas (16 MB, 0x7103816ef4: mixed between other state and scratch by run), memory in no live
  block (1.3 MB, mostly render churn), the 1.7 MB frame heap (0x710355a3b8, other state), 3,657 152-byte blocks of
  0x7103785104 (other state), Lua's 40-byte blocks (logic state), the stage table (constant by bulk, 96 KB sim state).
  Limits written in the file: last reader / writer per line only; a pool is one row whatever its slots hold.
- Run-to-run: the gimmick objects of Castle 64 are there with hazards on (4, every dump) and absent with hazards off;
  noted, since the hazards on / off control then also changes the gimmick pool (open question kept from 01:06).

### 2026-11-12 02:03 — Castle 64: the stage table confirmed not gamestate by a held perturbation; scripted runs are not repeatable, CPU against CPU is (runs `pk_*`, `pkc_*`)

New: `SSBU_POKE_HOLD=<first frame>,<frames>,<target>` (hle_state_dump.c: each frame of the span, bit 0x00400000 set in
every word that is neither 0 nor -1 of the target: `table`, `sites` (the live blocks of `SSBU_POKE_SITES=<allocation
sites>`, registered by hle_alloc_trace.c's wraps; words that look like pointers left alone), `ptr:...`,
`boma:<loads>:<off>:<len>`); `match.py compare <dump A> <dump B>` (every named value of every object present in both
runs, frame by frame); `research/tools/poke.sh`; player 1 as a CPU (`p1type=cpu`, fight_test.h).

1. **Two runs of the scripted match (player 1 on the gate's input sequence) are not the same run.** `pk_ctl1` and
   `pk_ctl2` (Castle 64, hazards, Mario on the sequence against DK level 9, stock 99, 3 games on the PC): fight hash
   logs differ from line 1,329 (fight frame 665: Mario starts a dash one frame earlier in one run), and the reader
   already sees a difference at frame 40 (`ControlModule.get_flick_bonus` 3 against 2, player 1). The sequence's steps
   are regular from its "fight seen" mark (581 polls to step 21 in both), so the cause is how the sequence and the
   menus' last inputs meet the fight's first frames: input state carried into the fight. Not proven further; what
   matters here is that **a scripted player makes two runs differ, so a perturbation must be judged on CPU against
   CPU runs**. (The older `gim*` runs had identical hash logs over 2,400 lines with 0, 2 or 4 gimmick objects:
   repeatability of scripted runs is not always lost, which is why it went unseen.)
2. **CPU against CPU is repeatable, and the gimmick objects do not change the fight.** `pkc_ctl1` / `pkc_ctl2`
   (`castle_cpu`: both players level 9 CPUs, Castle 64 with hazards, 50 s): identical fight hash logs (6,440 lines) and
   **822,520 named values equal, 0 different**, although the gimmick objects were there in one run only. Two methods
   (hash, reader) agree: on 50 s of fight, whether those four objects are made changes nothing a fighter does. The
   question "what decides whether they are made" stays open, but its netplay risk is smaller than feared at 01:06.
3. **Positive control**: `boma:38:30:8` (Mario's position x, y, PostureModule + 0x30) held from frame 600 for 600
   frames: the fight hash differs from frame 601, the reader from frame 600 (16,818 fighter values, then weapons from
   670). The judge sees a perturbation of state.
4. **The 1,024-entry stage table held perturbed for 10 s** (`table`, 5,835 words a frame from frame 600 to 1199):
   **fight hash logs identical, 0 named value different (fighters 128,156, gimmicks 13,803, weapons 694,472)**. With
   the positive control, this confirms 2026-11-11's single-frame test by a second, longer one judged by the reader:
   the table is presentation, not state the fight reads back. **[Corrected 2026-11-12 05:18 / 05:44: not presentation: by the code reading a spatial grid of the stage's collision lines; carried from frame to frame; perturbing it changed nothing in the fight.]**

### 2026-11-12 02:03 — a series of 12 long CPU-against-CPU matches: the automatic check finds a wrong field on the Hero (run `s1_wide`)

`research/tools/series.sh <matrix> <out> <length> [jobs]`: each match alone, 3 minutes of fight (stock 99), the state
dump every 20 frames, `SSBU_VERIFY_FIELDS`, the fight hash; then `reader.py --verify --hash` and the dump removed; one
line a match in `series.txt`. `research/matrix/wide.txt` (12 matches checked first by a 20 s smoke run `smoke_wide`:
every fighter kind and stage id set as asked, `eflame_first` excepted, replaced by Lucario): CPU against CPU,
level 9, 26 fighters never run before (Marth, Mega Man, Squirtle, Lucario, Little Mac, Joker, Hero, Robin, Mr. Game &
Watch, Palutena, Falco, Ike, Corrin, Min Min, Sephiroth, Sora, Wii Fit Trainer, King K. Rool, Simon, Piranha Plant,
Banjo & Kazooie, Terry, Byleth, Dark Samus, Ridley), 6 stages never run (Pokémon Stadium 2, Smashville, Lylat Cruise,
Yoshi's Story, Kalos, Castle 64 without hazards), 3 and 4 players, items on.

- **9 matches: every named value equal to the game's getter** (1.6 to 4.8 million values a match, 0 different), and
  the fighters' status, motion, position and damage equal to the fight hash log at every dumped frame.
- **Hero vs Robin: `HitModule.get_total_status(2)` wrong**: the reader read 0 where the game answered 0x100, at 167 of
  1,098 fighter frames (the Hero). The probe of 2026-11-12 00:54 had read it at the same place as `get_whole(2)`
  ([module + 0x60] + 0x94) on Mario, DK, Link and Samus; the getter combines more than that place. The family is in
  `argprobe.REJECTED` and out of `arg_fields.json` (958 calls of getters with arguments checked now). **Seven matches
  of the automatic check were not enough; this is why the check now runs on the wide series.**
- 2 matches (Game & Watch vs Palutena, Falco vs Ike on Pokémon Stadium 2) not read: I made the getter list again while
  they ran, and the reader stopped on an index the game's list did not have (no false difference). Re-run as
  `s1_rerun`. `series.sh` now copies the list into each run and gives the copy to the game and the reader.
- Pitfall: editing `series.sh` while it ran broke its last line (bash reads a script as it goes). Never edit a running
  script.

**Module sizes** (`research/tools/module_sizes.py` -> `research/map/module_sizes.json`, 64 module classes, from the
allocation trace): the dump copies 0x900 bytes from each module, but the fighter's GroundModule is 368 bytes,
CameraModule 88, WorkModule 152, PostureModule 208, StatusModule 392; KineticModule 3,440 (its 11 energies are
inside it, at + 0x5e0 to + 0xcb0) and ControlModule 2,800 are longer than the copy. **The "unnamed bytes changed" of
2026-11-12 00:31 and 00:54 for GroundModule (568) and CameraModule (564) were mostly other objects' memory** past
the module's end; the counts are to be taken again with the sizes.

### 2026-11-12 02:12 — where the stage's moving parts keep their state: stage objects made at the match load (runs `col1`, `pkc_s1`, `pkc_s2`, `pkf_*`)

Method 1, the traces (`stage_diff.py` on `research/map/sites.json`: Castle 64 with hazards against the same without
hazards and against Final Destination). The rows with more state with hazards on are few (23 rows of 0.3 KB or more,
44 KB). Leaving out the fiber stacks, the Lua and nn / nu rows, the app-read ones are small blocks made at the match
load, read and written by app code (`f_7100522f30`, which also calls the stage table's `f_710260e040`, and
`f_7100533020`):

| site (2 return addresses), size | blocks FD / BF (items) / Castle off / Castle on | state read by the simulation, KB (FD / BF / off / on) |
|---|---|---|
| 0x7100524308 0x7102629cb0, 288 B | 10 / 13 / 25 / 25 | 0.4 / 0.6 / 0.5 / 4.5 |
| 0x710052fe0c 0x71005244dc, 96 B | 9 / 14 / 21 / 26 | 0.1 / 0 / 0 / 0.8 |
| 0x7100523f88 0x7102629cb0, 256 B | 8 / 8 / 4 / 4 | 0.1 / 0.2 / 0.2 / 0.6 |

`outside.py` over the four whole fights gives the same two first sites as the only groups that are Castle 64's alone
in its top list. **The number of blocks follows the stage** (10 on Final Destination, 13 on Battlefield, 25 on Castle
64), **not the hazards**; with hazards on, the same 25 blocks carry nine times more state read by the simulation.

Method 2, held perturbations (`SSBU_POKE_HOLD=600,600,sites`, `SSBU_POKE_SITES=<sites>`: bit 0x00400000 set every
frame in every word of those blocks that is not 0, -1 or a pointer), CPU against CPU, judged against the control:

| Run | words a frame | fight hash | reader |
|---|---|---|---|
| Castle 64, the three sites | 883 | differs from frame 601 | 17,863 fighter values differ from frame 610 |
| Castle 64, 0x7100524308 alone | 434 | from frame 608 | 18,551 from frame 610 |
| Castle 64, 0x710052fe0c alone | 372 | from frame 601 | 16,492 from frame 610 |
| Final Destination, the three sites | 586 | from frame 601 | 9,992 from frame 610 |

- **These blocks are state the fight reads back, on every stage**: perturbed, they change what the fighters do within
  a frame or ten, on Final Destination too. They are not the moving parts' own objects, but per-stage objects (one a
  piece of the stage, by their count) whose state the moving parts drive when the hazards are on.
- What they are is **probable, not established**: their count follows the stage's geometry, they are made at the match
  load and read by app code next to the stage table's: the stage's collision pieces (floors, platforms) are the
  likeliest reading. To be confirmed by the code that makes them (priority 2's reading) or by a pointer from the
  616,000-byte collision block (site 0x7102606480). **[Corrected 2026-11-12 02:22: not the stage's collision. The block is a pool of 350 per-object ground-collision records of 0x6E0 bytes; GroundModule + 0x28 points at its object's record (fighter: record 0, weapons: records 1-9, seen in a dump; the code that makes the pool sets 350 and zeroes 350 x 0x6E0 bytes). See the entry of 02:22.]**
- The map gets these three sites as "stage state" rows; the 1,024-entry table stays "presentation" (02:03).

### 2026-11-12 02:27 — the long tail of the state read by the simulation, by family; the 616,000-byte block is the objects' ground-collision records (runs `col1`)

State read by the simulation's code over whole fights (`research/map/sites.json`), by family of allocation site, KB
(rows):

| Family | FD | Castle 64 on | Castle 64 off | BF items |
|---|---|---|---|---|
| stage table (carried, no effect observed: 02:03, 05:44) | 96.1 (1) | 96.1 | 96.1 | 96.1 |
| no live block (other allocators' memory, by its last reader `f_71039635c0`; the guest stacks) | 26.3 (3) | 26.8 | 32.1 | 27.4 |
| fighters' pool (the modules and the slots) | 16.0 | 15.2 | 16.9 | 15.6 |
| fiber / thread stacks (64 KB blocks) | 3.1 | 7.1 | 4.0 | 4.8 |
| ground-collision records (below) | 2.9 | 3.1 | 3.0 | 2.9 |
| weapons' pool | 2.1 | 2.1 | 2.1 | 2.1 |
| stage objects (02:12) | 0.7 (4) | 7.1 (6) | 1.4 (4) | 0.9 (3) |
| gimmick pool | - | 0.5 | 0.1 | - |
| **the rest: 312-337 rows** | 98.9 | 93.5 | 91.9 | 92.1 |
| all | 246 | 251 | 248 | 242 |

- The tail is long and flat: ~95 KB in 312-337 rows, the largest 5.5 KB (a 104,592-byte block made at boot, site
  0x710055d1ac, read by `f_7100561b60`), then match-load blocks of app code of 1-3 KB each. `outside.py` on the four
  fights: 15 of its top groups are in all four (36 KB at most), 10 in some; the only Castle-64-only groups are the
  stage objects. **The tail is the same set of sites from one match to the next**: it can be described by sites.
- Without the stage table (presentation), the state the simulation reads is ~150 KB a fight: the fighters' and
  weapons' pools ~18 KB, the stage objects 1-7 KB, the records below 3 KB, the stacks 3-7 KB, the tail ~95 KB.

**The 616,000-byte block (site 0x7102606480) is not the stage's collision** (2026-11-11 said so, from what GroundModule's
getters read; four places of this journal are annotated). Reading the code (priority 2): the block is a pool of 350
records of 0x6E0 bytes (350 x 1,760 = 616,000), one record per object with a GroundModule, which keeps its pointer at
GroundModule + 0x28; the code that makes the pool sets the capacity 350 and zeroes 350 x 0x6E0 bytes. **Checked in a
dump** (`col1` Castle 64): the fighter's GroundModule + 0x28 is record 0 of the block, nine weapons' records 1 to 9,
each at an exact multiple of 0x6E0. So the "2-3 KB of stage collision state" is each object's own ground contact state
(touching lines, contact points, ground / air / cliff status, the cliff held), part of the battle objects' state.
The stage's lines and cliffs are other objects, reached from the records.

### 2026-11-12 02:33 — errors injected on purpose: the strict oracle finds them, the hash only some (runs `inj_*`)

`SSBU_RB_VERIFY_INJECT=<round>:<target>` (hle_state_dump.c `research_inject`, the poke targets of 02:03): right after
the replay check's load of that round, bit 0x00400000 is set in the target's words that are neither 0 nor -1. The
strict oracle (`strict.sh`: trace 300-539, replay check at 600, 60 frames, 3 replays, Mario vs DK) must then fail in
that round only.

Two mistakes on the way, both mine: **`rb_load` does not return** (it resumes the saved state's safe point), so a call
written after it never ran (the first `inj_pos` passed with nothing injected: the log had no injection line); the
round is now kept and the error put in at the next safe point. And flipping every word of a target, zeros and -1
included, stopped the game twice (the table's tick followed a corrupted index; a float pointer read as the count):
an error that crashes proves nothing, so the injection now uses the held perturbations' rule (words that are not 0,
-1, nor half of a pointer, in the game's heap only).

| Run | target (replay 2) | words | fight hash | strict oracle |
|---|---|---|---|---|
| `inj_pos` | Mario's position (PostureModule + 0x30, x and y) | 2 | **differs** from the first frame of replay 2 | **FAIL**: replay 2, 65 unexplained lines (+ 76 unexplained outputs); replays 1 and 3: 23 lines, all explained |
| `inj_table` | the stage table's three per-frame lines | 4,086 | **the same** on all 3 replays | **FAIL**: replay 2, 749 unexplained lines, all in the table's block (read and written by `f_710260e040`); replays 1 and 3 clean |
| `inj_work` | WorkModule float 0x11 (a damage copy) | 1 | the same | the injected value was rewritten within the 60 frames: replay 2 clean (the FAIL of this run is 1 line of replay 1, below) |
| `inj_grav` | the gravity energy's brake (KineticModule + 0x6f0) | 1 | the same | PASS: the value was rewritten before the end of the replay |

- **The strict oracle sees an error the fight hash does not** (`inj_table`: 4,086 words different after the replay,
  hash equal on every frame), and places it in the round and the block where it was put. It counts the table as
  consumed state because app code reads it; the held perturbation (02:03) says the fight does not depend on it:
  **the oracle is conservative there**, as it should be.
- Two injections did not survive the replay: the game writes those values again from other state within 60 frames.
  An error that heals is not a detection test; it says these two are derived values.
- **A new unexplained line, not injected** (`inj_work`, replay 1): one u64 in a 24-byte block of site 0x71037fe52c,
  written by SDK code (`f_710900fee0`) and read by the battle objects' update chain, went from 0x100000001 to
  0x200000002 (both 32-bit halves + 1): the shape of a shared pointer's control block {use count, weak count}. Seen
  once in the strict runs so far; **left unexplained** (no rule added on one case): to be watched in the next strict runs.

### 2026-11-12 02:38 — priority 2: KineticModule, ControlModule, GroundModule, CameraModule named by reading the code (runs `s2_wide`, `chk1`)

Three agents read the generated C of the exported getters, the constructors and the per-frame writers, without
running the game; their findings are in `research/map/code_reading/` (offsets, sizes, types, the getter of each field
and how it computes, "certain" when an exported getter returns the field by a plain load, else "probable"; words
only). The fields used by the reader are added to `research/map/arg_fields.json` marked "code" and checked by the
game (the automatic check), the way the probe's were.

- **KineticModule** (3,440 bytes): built by `f_71006882d0`, the 11 energies inside it. Energy k is the entry at
  + 0x30 + 0x18 k (pointer, id, attribute mask); classes by vptr: 0 motion, 1 gravity, 2 controller, 3 stop (?),
  4 damage, 5 jostle (?), 6 ground movement (?), 7 environment (?), 8-10 a second controller, damage, stop. **The
  automatic check now calls the energies' own getters on the energy** (`recv=` in the getter list: the receiver is
  the object reached from the module, hle_state_dump.c): gravity accel / stable speed / brake / limit speed, the
  controller's accel x / y mul / add (energies 2 and 8), motion's chara dir / angle / angle whole / speed mul, and
  `is_consider_ground_normal` on eight energies: 24 calls.
- **The code reading explained a difference the automatic check had just found.** `s2_wide`, Ice Climbers vs Olimar
  with items: at one frame (2,860) the game's speed sums for Popo differed from the reader's (masks 1, 2, 7). The
  reading says an energy's speed is not always + 0x10: the damage energy gives its override speed at + 0xC0 while the
  u32 at + 0xD0 counts down, the gravity energy + 0x60 while + 0x70 does (the "+ 0x70 / + 0xd0, always 0 in the
  probed matches" of 00:58). `reader.Reader.energies` reads them so; the dump copies 0xe0 bytes of each energy.
- **ControlModule** (2,800 bytes): `[module + 0x110]` is the module itself + 0x20 (the constructor stores it; every
  dumped fighter frame has it so). 43 fields added: sticks current and previous (main, sub, unclamped), buttons held
  / previous / newly pressed / released, trigger counts and their previous values for 18 buttons, the flick counters
  and directions (x, y, no-reset, after, sub). `get_lr` is the analog L / R depth, not a direction.
- **GroundModule** (368 bytes) and **CameraModule** (88 bytes): small objects; their state is behind pointers. The
  616,000-byte block is the objects' ground-collision records (02:27). `get_shape_kind` added ([GM + 0x28] + 0x394);
  the contact slots, the status (+ 0x5A0), the collision box points, the held cliff, the flags are "probable" (the
  getters that read them write a shared buffer or take references: not called by the check). The camera's range and
  target are in a global camera manager, not in the module.
- Getters that are not read-only, from the reading: `GroundModule::get_up / down / left / right_pos`,
  `get_touch_pos`, `get_center_pos` (they write a shared buffer), `get_touch_line_raw`, `get_cliff_id_uint32` (they
  take a reference); `KineticModule::get_energy` with an id past the table reads past it. None is called.

**Checked by the game** (`chk1`: six CPU-against-CPU matches of 60 s, Final Destination, Castle 64, Battlefield twice,
Kalos with four players, Yoshi's Story with items; Ice Climbers vs Olimar is the match that showed the difference):
**every match 0 different** (786,423 to 1,714,729 values a match); the 1,026 getters with arguments or another
receiver all compared, 219-259 of them changing value in a match. The other matches of `s2_wide` (8 matches of 3
minutes: Lucina, Wario, Roy, Sheik, Bowser, Greninja, Incineroar, Mewtwo, Lucas, R.O.B., Pit, Dark Pit, Zelda, Wolf,
Steve, Inkling; Town and City, Delfino Plaza, Halberd, Dracula's Castle, Big Battlefield) passed before the fields
were added: 1.6 to 4.6 million values each, 0 different.

### 2026-11-12 03:31 — rollbacks with corrected inputs: harness ready, run blocked by a ring hang; the determinism gate fails, with yesterday's runtime too; invariants for the code-read fields (runs `lfi_*`, `ringctl2`, `old_ringctl`, `inv1`)

**Rollbacks that replay corrected inputs** (what netplay does after a wrong guess). `SSBU_RB_LF_INPUT=<seed>[,1]`
(hle_rb_core.c): player 1's pad is a fixed function P of the logic frame counted from the fight's first read
(20-frame segments of stick and button presses, neutral for 120 frames so the menus' leftovers are gone); with ",1"
the first pass of each frame gets a wrong guess G (P with its buttons dropped every 7th frame) and the ring test
writes P into the tape for the frames it is about to run again. The hash log gets " L <logic frame>";
`research/tools/lfcompare.py` compares two logs by logic frame.
- **The references repeat**: two runs with P and no rollback, 3 games on the PC: identical hash logs (5,234 lines).
  Driving player 1 by logic frame removes the scripted runs' variance (02:03).
- **The negative control discriminates**: G without rollbacks differs from P at 3,742 of 4,798 fighter-frames, from
  logic frame 528.
- **The run with rollbacks could not be made**: the ring `600,6,8,150` (8 frames back every 6, no rotation) stops the
  game (no frame shown for 120 s) during the ring (watchdog: no frame for 120 s; main thread waiting in the task workers' code,
  main+0x354a6d0), **with or without `SSBU_RB_LF_INPUT`, frames hidden or not (`ringctl2`), and with yesterday's
  runtime (45cfef2) put back (`old_ringctl`)**: not a regression of tonight's code. The usual ring `600,10,4,50` runs
  (49 the same, 0 different). Yesterday's long tests used rotation (depths 1-8) or other first frames; this
  configuration was not run before. Stopped there (time box): the next step is a ring that covers every frame with
  a configuration that runs (e.g. 4 back every 3, or rotation with a tape rewrite of every frame since the last load).

**The determinism gate fails tonight** (`baseline.sh`: two scripted runs, Mario vs DK level 3): the logs differ at
fight frame 652 (Mario starts a dash one frame earlier in one run), **also with yesterday's runtime**. Yesterday the
same gate passed (2,836 lines). The game's code and the save are unchanged; the input sequence advances by player 1's
polls, and polls that see no new logic frame happen (192 of 791 at frame 600): the sequence's timing probably depends on the
host's timing. **The game is deterministic where its input is** (CPU against CPU, input by logic frame: identical
runs); the gate's scripted input is not. Recommendation for upstream: key the sequence's fight steps to logic frames.

**Invariants for the code-read fields** (`research/tools/invariants.py`, a dump at every frame, Castle 64 CPU against
CPU, frames 600-900, 2 fighters): ControlModule's previous stick / sub stick / buttons at t equal to the current ones
at t-1 (600 frame pairs each), newly pressed == (previous ^ held) & held and released == (previous ^ held) & previous
(602 each), the energies' classes as the constructor sets them (6,622), the floor contact present whenever the
ground-collision record says ground (394): all hold. **The record's status (+ 0x5A0) is not StatusModule's
situation**: 601 of 602 agree, and the one that does not is understood: at frame 698 DK enters status 0x48 (thrown by
a hit), the record says air for one frame, ground again at 699-701, and both say air from 702: the record is the raw
result of the frame's ground check, the situation follows the status. Named "ground-collision status (raw)".

### 2026-11-12 03:57 — the strict oracle on five matches its rules were not written on; the end of a fight; items falling with CPUs (runs `st_*`, `st2_*`, `end1`, `s3_items`)

**Strict oracle** (`strict.sh`, CPU against CPU, `research/matrix/trace.txt` + 5 lines): Hero vs Robin
(Battlefield), Falco vs Ike (Pokémon Stadium 2, hazards), four players on Kalos (Terry, Byleth, Dark Samus, Ridley),
four players with items on Big Battlefield (Pit, Dark Pit, Zelda, Wolf), Steve vs Inkling. **Fight hash equal on all
15 replays.** First pass: PASS on three, FAIL on two, with 3 unexplained lines; each was looked at:
- Kalos, a float pair and a pointer in blocks of sites 0x71023ef340 / 0x71023f6734: their chains pass through
  `app::sv_animcmd::PLAY_SE` and `PLAY_SEQUENCE` (the scripts' animation commands that play a sound): **sound
  requests**. A pointer in an 80-byte node read by `phx::Fiber::finalize` and written next to `phx::Fiber::status`:
  **the fibers' bookkeeping** (which pooled fiber or stack runs a script), pointers only. Two causes added to
  `oracle.py`, each by an invariant of the code (a function of the chain labelled `sv_animcmd::PLAY_*`; pointers
  only and a `phx::Fiber` method in the chain), tried last. Kalos run again (`st2_`): **PASS**.
- Steve vs Inkling (`st2_` too): **FAIL on one line, the same in the 3 replays**: the u64 at 0x608230e5c0, a 24-byte
  block of site 0x71037fe52c, 0x100000001 -> 0x200000002 (two 32-bit counts, both one more after the replay), read by
  `f_71013b8600` <- `f_710137b3f0` <- `f_710135ca00` (the battle objects' update), written by `f_7101397ae0`. **The
  second time this line is seen** (02:33, `inj_work`, Mario vs DK: same address, same values, another writer). By its
  shape, the use and weak counts of a reference-counted object: the replay ends holding one more reference. Not
  named by any class; **left unexplained** (no rule): it is the strict oracle's one open line. Whatever it is, the
  fighters' state after 60 frames is the same.

**The end of a fight** (`end1`, Marth vs Mega Man, CPU against CPU, stock 1): the match ended on its KO at ~84 s (the
logic frame stops at ~5,035; `SSBU_DEBUG_END` counts shown frames and never came: the run hit its time limit on the
end screens, the dump and hash going on). Over the whole dump (319 s shown, 959 records, the end sequence where both
fighters stay in status 0x107 for 73 % of the records): **3,930,189 named values equal to the game's getters, 0
different**, and the fight hash cross-check equal. The reader holds through a fight's end.

**Items falling, CPU against CPU** (`s3_items`, `SSBU_RULE_POKE` every item on, 3 minutes each): four players on
Battlefield (Mario, Link, Pikachu, Kirby), Samus vs Fox on Castle 64, three players on Pokémon Stadium 2 (Ness,
Peach, Snake): **3.6, 6.0 and 4.9 million values, 0 different.** A Final Smash is likely with every item on for 3
minutes, but none is shown by the logs; not established.

### 2026-11-12 04:20 — rollback oracle on the 12 wide matches; 8 more fighters' pairs; the invariants on three matches (runs `ring_wide`, `s4_wide`, `inv2`, `inv2b`, `inv3`)

- **Rollback ring on `research/matrix/wide.txt`** (12 matches, CPU against CPU, 2-4 players, Pokémon Stadium 2,
  Smashville, Lylat, Yoshi's Story, Kalos, Castle 64 without hazards; ring 600,6,8,150 with rotation, catch-up frames
  hidden, 60 s, stock 99): **150 loads each, 149 frames run again the same, 0 different, on all 12**. 18,780-32,025
  hot pages at the end.
- **`s4_wide`** (`research/matrix/wide3.txt`, 8 matches of 3 minutes: Pichu, Jigglypuff, Young Link, Toon Link,
  Dr. Mario, Daisy, Captain Falcon, Meta Knight, King Dedede, Zero Suit Samus, Charizard, Ivysaur, Chrom, Ken,
  Richter, Shulk; Kalos, Yoshi's Story, Town and City, Lylat, Castle 64, Pokémon Stadium 2, Final Destination,
  Dracula's Castle): **every match 0 different** (1.5 to 2.8 million values), every fighter kind set as asked.
- **The invariants of 03:31 on two more matches**: four players on Kalos (1,200 frame pairs, 13,244 energy class
  checks) and Samus vs Fox with items falling on Castle 64 (600 pairs): ControlModule's previous / pressed / released
  relations and the energies' classes hold everywhere; the floor contact is present whenever the record says ground
  (364, 318). The record's raw status disagrees with the situation once on Kalos, and it is the same case as on Castle
  64 (looked at in a short re-run, `inv2b`): at frame 628 a fighter enters damage status 0x49, the record says air for
  that frame, ground the next. **Three matches now back these code-read fields.**

### 2026-11-12 04:26 — Final Smashes, read exactly; the gimmick objects come and go on Pokémon Stadium 2 too (runs `s5_final`, `s3_items`)

`SSBU_FINAL_LOG=1` (hle_state_dump.c): at the first fighter's frame line, the game's own
`FighterManager::is_final` and `get_final_actor_entry_id`; a line when a Final Smash starts or ends.

- **Final Smashes happen and the reader stays exact through them.** Items falling (every kind on), CPU against CPU,
  3 minutes: four players on Battlefield (Mario, Link, Pikachu, Kirby): one Final Smash, fight frames 8,340-8,779;
  three players on Pokémon Stadium 2 (Ness, Peach, Snake): one at 2,861-3,221 and one starting at 10,785 (still on at
  the end). Over the whole matches, dumps every 20 frames (about 22 and 18 of them inside the two finished Final
  Smashes): **5,986,551 and 4,852,747 named values equal to the game's getters, 0 different**, the fighters'
  status, motion, position and damage equal to the fight hash log at every dumped frame.
- **The same matches run twice** (`s3_items` without the log, `s5_final` with it): the fight hash logs are identical
  (45,131 and 32,955 lines): asking `is_final` every frame changes nothing. On Pokémon Stadium 2 the dumps differ by
  one category only: **gimmick objects** (15,372 values in `s3_items`, none in `s5_final`), the fighters', weapons'
  and items' values the same. So the run-to-run presence of the gimmick objects seen on Castle 64 (01:06, 02:03) also
  happens on a second stage, and there too the fight does not change.

### 2026-11-12 04:36 — rollbacks with items falling pass the ring; the strict oracle with items on the stage finds lines it cannot explain (runs `ring_items`, `st_items4`)

- **Rollback ring with items falling** (`research/matrix/items_cpu.txt`, `SSBU_RULE_POKE` every item on, CPU against
  CPU, ring 600,6,8,150 with rotation, hidden, 60 s: items fall from frame ~900, inside the ring's 600-1,500):
  **149 the same, 0 different, on all three** (four players on Battlefield, Samus vs Fox on Castle 64, three players
  on Pokémon Stadium 2).
- **A vacuous PASS caught**: the first strict run with the replay check moved to frame 1,300 (when items are on the
  stage) printed "PASS" with no replay at all: `strict.sh` leaves the fight at 20 s (1,200 frames), so the check's save
  never came. `oracle.py` now says **NO REPLAYS** when there is no replay to compare.
- **Strict oracle with items on the stage** (`st_items4`: four players, trace 1,000-1,239, replay check at 1,300,
  40 s): **fight hash equal on the 3 replays**, but **FAIL: 17, 40 and 42 unexplained lines**. Most are in 88- and
  96-byte blocks of many sites, read by `f_7101f440a0` <- `f_71015f5b10` <- ... (code with no class name), written by
  `f_7101f451f0` / `f_7101f43df0`; their differing words read as ASCII "effect_E", "effect_I", "sound_Ap" next to
  40-bit values shaped like hash40s and pointers to neighbouring nodes: **the nodes of a container keyed by effect
  and sound names, the same keys placed in other nodes after the replay**. By that, a lookup table of the items'
  effects and sounds (presentation), whose layout follows the allocation order: probable, **not established**, no
  rule added. A few other lines (32- and 24-byte blocks read by `f_71015ac3a0` and `f_7100455b40`, written by
  `lib::L2CAgent` code) are not looked at yet. **Open: the strict oracle is not clean with items on the stage.**

### 2026-11-12 04:42 — GroundModule's contact fields checked by the game; the Miis and Pyra / Mythra cannot be set up (runs `chk2`, `smoke_last`)

- Three of GroundModule's getters are read-only by the code reading: `is_touch(mask)`, `is_attach_cliff`,
  `is_status_cliff`. The first two are "not zero" readings of the object's ground-collision record: `is_touch(1 << k)`
  = [GM + 0x28] + 0x10 + 0x30 k (k 0 up, 1 left, 2 right, 3 down), `is_attach_cliff` = [GM + 0x28] + 0x560. Added to
  `arg_fields.json` (1,031 calls of getters with arguments now) and **checked by the game on four CPU-against-CPU
  matches** (Castle 64, Final Destination, Lylat with Sephiroth and Sora, four players on Kalos): **0 different**
  (850,894 to 1,718,075 values a match). The floor contact also passed the invariants of 03:31 / 04:20 on three
  matches: two methods for it now.
- The Miis (`miifighter`, `miiswordsman`, `miigunner`: kinds 72, 73, 74, known by the game) stop the game at the
  fight's load in a debug match: a Mii fighter needs a Mii chosen on the select screen, which the debug match does
  not give. `element`, like `eflame_first`, `eflame_only`, `elight_only`, is not a name the game knows. **84 of the
  89 fighters are covered**; the 5 missing need the select screens.
- (updated 04:43) The other unexplained lines of `st_items4` are of the same kind: 24- and 32-byte blocks of nodes (pointers to
  neighbouring nodes, pairs shaped like `L2CValue` {value, type}: 0x6000000002 / 0xff), written by `lib::L2CAgent`'s
  code: the scripts' value tables of the items, the same contents in other nodes. **What the strict oracle lacks here
  is a comparison by contents** (following a container's pointers) instead of by bytes: the next tool for it.
- (updated 04:48) CameraModule's subject 0: `get_priority(0)` = [CM + 0x28] + 0x24 and `get_player_no(0)` = [CM + 0x28] + 0x9c
  (records of 0x150 bytes, their count at CM + 0x20), from the code reading; **checked by the game on two matches**
  (Castle 64, four players on Kalos: 0 different; 1,033 calls of getters with arguments in all). Other subjects are
  not called: past the count the getter reads what follows.

### 2026-11-12 04:49 — rollback ring on 16 more matches (run `ring_wide23`)

`research/matrix/wide2.txt` + `wide3.txt` (16 matches, CPU against CPU, the fighters and stages of `s2_wide` and
`s4_wide`; ring 600,6,8,150 with rotation, hidden, 60 s, stock 99): **all 16 OK, 0 different** (149 to 155 frames
run again the same: some safe points hold more than one logic frame). With `ring_wide` (12) and `ring_items` (3), the
rollback oracle has passed on **31 matches tonight** of fighters and stages it had not seen.

### 2026-11-12 04:54 — strict oracle on Castle 64 CPU against CPU (run `st_castle_cpu`)

Hazards on, both players level 9 CPUs: fight hash equal on the 3 replays; 2 unexplained lines a replay, both fiber
objects outside traced blocks read by `phx::Fiber::finalize`: a 64 KB-aligned stack base and a word tagged 0xf1be
("fibe") with a number and a count. The fiber bookkeeping cause of 03:57 now also takes the fiber objects' own tagged
words; with it **PASS**. The other runs were judged again: Kalos PASS, Steve vs Inkling FAIL (the one counter), items
FAIL (the containers): the rule explains nothing more than these lines.
- (updated 04:59) Strict oracle on Samus vs Fox with items falling (Castle 64, same replay check at 1,300, `st_items2`):
  hash equal on the 3 replays, **PASS**, none of the container lines. So they come with the four-player match (more
  items, or some kinds); whether an item was on the stage at frame 1,300 in this run was not checked.

### 2026-11-12 05:18 — the stage objects are the stage's collision geometry; the 1,024-entry table is a per-frame grid of the lines (run `link1`)

A code reading (agent, no game run; `research/map/code_reading/stage_collision.json`) of the three sites of 02:12:
one builder, `f_7100523f10`, called by the stage model's collision loader `f_7102628310`, makes per piece of the
stage: **A** (288 bytes, site 0x7100524308) a line segment (end vertices at + 0x88 / + 0x90, bounding box, normal,
flags at + 0xC4 (bit 13 passable), type + 0xCC, material + 0xD0, id + 0xF8, valid byte + 0x100; sorted into floor,
ceiling or wall by its normal's angle), **B** (96 bytes) a vertex (current, previous and rest positions), **C** (256
bytes) a group of lines (its vertex and segment lists, box, angle), and **D** (0x140 bytes, one a group) the group's
position, angle, pivot, scale. Each frame `f_7100522f30` / `f_7100532810` move the vertices by their group's
transform and `f_7100533020` recomputes each segment's endpoints, box and normal.

- **Checked in a dump** (Castle 64, CPU against CPU, allocation trace and records): **all 29 touched-line pointers of
  the fighters' ground-collision records (+ 0x10 + 0x30 k) point to the start of a 288-byte block of site A** (both
  callers). With the traces (02:12: counts by stage, nine times more state with hazards) and the held perturbations
  (the fight changes), **established: the stage's moving parts keep their state in the collision geometry** (the
  groups' transforms, the vertices' positions, the segments).
- The same reading says `f_710260e040`, which the 1,024-entry table belongs to, **looks like a spatial grid of the
  lines**, not presentation. *[Corrected at 05:44: I first wrote here that the grid is rebuilt each frame. It is not: in
  `inj_table` (02:33) 1,393 words still carried the injected bit 0x00400000 60 frames later, in replay 2 only. What is
  measured: the table is carried from frame to frame and read by app code, and perturbing its non-zero words changed
  neither the fight hash nor any named value (Castle 64, 10 s; a second stage at 05:51). "Presentation" (02:03, 02:27)
  was wrong; "not gamestate" is not shown either: **carried, no effect observed**.]*
- Open from the reading: one vertex per segment in the code, but 9 / 10 measured on Final Destination; the meaning of
  the floor / ceiling / wall flag bits and of the groups' bit 16.

### 2026-11-12 05:28 — six 5-minute four-player matches (run `s6_four5`)

`research/matrix/four5.txt`: CPU against CPU, four players, 5 minutes, hazards on, on Smashville, Pokémon Stadium 2,
Lylat, Castle 64, Dracula's Castle, Halberd (24 fighters: Pikachu, Fox, Inkling, Lucario; Ness, Snake, Cloud, Steve;
Marth, Sheik, Rosalina, Ice Climbers; Bayonetta, Shulk, Olimar, Duck Hunt; Simon, Richter, Sephiroth, Sora; Kirby,
Meta Knight, King Dedede, Mr. Game & Watch): **all six 0 different, 7.1 to 11.8 million named values each** (54.6
million in all), the fighters' values equal to the fight hash log at every dumped frame.

### 2026-11-12 05:38 — end-of-night checks (`research/tools/final_check.sh`, runs `final_*`, `gate1`, `gate2`, `ring`)

- **Normal build**: up to date with the tree (`build_game.py`: nothing to do); build-trace linked again from the same
  runtime, `code_cats.bin` made again.
- **Rollback oracle, full savestate** (`baseline.sh`: ring 600,10,4,50): 50 loads, **49 the same, 0 different**.
- **The control without pruning** (E0: ring 600,6,8,150 rotated, hidden, 60 s, stock 99; Mario vs DK, Link vs Samus,
  Castle 64): **149 the same, 0 different, on all three**.
- **Determinism gate CPU against CPU** (Castle 64, hazards, two runs): **identical fight hash logs (4,028 lines)**.
- **The repo's scripted gate fails** (as at 03:31, with yesterday's runtime too): the scripted input's timing.

- (updated 05:45) **A flaw of the corrected-input test as written** (03:31): the wrong guess G starts at logic frame 120, but the ring
  starts at fight frame 600: the frames before it are never run again, so their wrong input would stay and the
  comparison would fail whatever the rollbacks do. G must start where the ring starts (a runtime change, not made
  tonight). The ring hang is also not shown to be about rotation: every configuration that hung has a depth at least
  its interval (its first load goes back to the ring's first save), every one that ran a smaller depth or rotation
  (first load 1 back): being checked (`ring605`). `4 back every 4` was run with the test's code only.

### 2026-11-12 05:51 — checks before the report: the stage table carried, the ring hang's cause, the contact pointers on a second stage (runs `pkb_*`, `ring605`, `ring606`, `link2`)

- **The stage table is carried from frame to frame** (in `inj_table`, 1,393 words still held the injected bit 60
  frames later, in replay 2 only: not rebuilt each frame, as 05:18 said; corrected there). **Held perturbation on a
  second stage** (Battlefield, CPU against CPU, 5,764 words a frame for 10 s): fight hash log the same, **678,969 named
  values the same, 0 different**. So: carried, read by app code, no effect on the fight observed on two stages; what
  the fight would do with it otherwise is open (map: `carried_no_effect_observed`).
- **The ring hang is the load of the ring's first saved state**, not the lack of rotation: `600,6,5,150` without
  rotation runs (150 loads, 149 the same, 0 different), `600,6,6,150` hangs, as `600,6,8,150` and `600,4,4,300`
  did. With a depth at least the interval, the first load goes back to frame 600, the ring's first save; with a smaller
  depth (or rotation, first load 1 back) it does not. (A passing ring prints no LOAD line either: "before its first
  load", written at 03:31, was not shown; corrected.) Probably an upstream bug; to report.
- **The fighters' contact pointers on a second stage** (Final Destination, `link2`): 32 of 32 point to the start of a
  288-byte segment of site A. The stage collision geometry holds on two stages.
- **The 75 code-read fields on the 5-minute series**: the 1,033 calls were compared on all six matches of `s6_four5`
  (284-336 of them changing value a match): checked on 8 (the camera's) to 18 (ControlModule's, the energies') matches, not 2 to 6.
- **Totals, counted from the series files**: 39 runs of 37 distinct long matches, **161,677,139 named values equal,
  172 different** (167 the Hero's field, 5 Ice Climbers' speed override: both fixed and checked again since).
- The scripted gate (03:31): that the sequence's timing follows the host's is **probable** (polls without a new logic
  frame exist); why the same gate passed yesterday is **not explained**.

### 2026-11-12 05:59 — rollback ring on the six four-player matches (run `ring_four5`)

`research/matrix/four5.txt` (four players, CPU against CPU, Smashville, Pokémon Stadium 2, Lylat, Castle 64, Dracula's
Castle, Halberd), ring 600,6,8,150 with rotation, hidden, 60 s: **all six 149 the same, 0 different**. The rollback
oracle has passed on **37 matches tonight** of fighters and stages it had not seen.

---

## Day of 2026-11-12 (13:11 - 18:00)

### 2026-11-12 14:19 — the user's answers; rollbacks with corrected inputs pass, with a negative control that fails (runs `lf2_*` - `lf4_*`)

The user's answers (13:11): no proposal upstream; the repo's scripted sequence stays as it is and the input driven by
logic frame (`SSBU_RB_LF_INPUT`) becomes our tests' determinism gate; 84 fighters are enough. Order for the day:
rollbacks with corrected inputs, a content comparison in the strict oracle, a sufficiency test of the map, naming
(weapons' and items' variables, the tail's largest sites), lighter saves if time is left. Readings taken: the report
file is `research/MORNING_2026-11-12.md` (the request named `MORNING_{date_prompt}.md`); work until 18:00 (the request
also mentions 21:00 for "if the list is done"; the 18:00 end is read as the binding one).

**Two defects of the upstream repo** (noted, not reported, as asked):
- `research/seq/gate.seq`'s fight steps count player 1's polls, and polls without a new logic frame happen: two runs of
  the repo's gate can differ (2026-11-12 03:31); our gate drives player 1 by logic frame instead.
- The rollback ring stops the game when it loads its first saved state (any ring whose depth is at least its interval).

**The test, as built today** (hle_rb_core.c, `SSBU_RB_LF_INPUT=<seed>,1[,<last fight frame>[,<latency>]]`): player 1's
true input P is a fixed function of the logic frame; on a frame's first read, recorded by the tape, the game gets
netplay's guess, the input of `<latency>` frames before, wherever P changed in between; each wrong guess is found
`<latency>` frames later and the ring loads the state before it; at every load the tape gets P for the frames run
again. The ring's own loads go on beside (9 back every 10: the depth stays under the interval). `SSBU_RB_LF_NOFIX=1`:
the negative control, no correction, no rewrite. The dump numbers its records by logic frame when the test runs.

Three tries that did not discriminate, and why (each understood before the next):
1. Dropping a button every 7th frame (last night's G), 6 guesses: no effect even uncorrected.
2. A one-frame-late change, 8 then 59 guesses: no effect uncorrected either.
3. The negative control stayed identical even with 345 guesses: **last night's code rewrote the tape with P at every
   ring load, periodic ones included**, and the ring runs 9 frames in 10 again: the guesses were corrected anyway.
   Also, a guess must be made where the tape records a frame's first read: a frame read before (a catch-up) kept P.

**Result** (Mario, driven by logic frame, against DK level 3 on Final Destination, 62 s, latency 8, wrong guesses up to
fight frame 2,400; reference: P, no rollback):

| Run | wrong guesses | corrections | fight hash, by logic frame | reader, logic frames 2,700-3,300 |
|---|---|---|---|---|
| `lf4_rb` | 255 | 50 (+ the ring's 350 loads, with P) | **0 different** over 0-2,881 (2,282 frames run again) | **0 different** (158,112 values) |
| `lf4_neg` (no correction) | 345 | 0 | **4,398 different** from logic frame 642 | **5,336 different** (damage among them) |

Two judges, a negative control that fails as it should: **a fight whose wrong guesses are rolled back and replayed with
the true inputs ends exactly as the fight that had the true inputs.** (Two references with P alone are identical too:
the gate.) Extension to three more matches: running (`lf5_*`).

### 2026-11-12 14:42 — corrected-input rollbacks on three more matches; the strict oracle's double counter explained; a comparison by content (runs `lf5_*`, `st3_*`)

**Step 1, extended** (`research/matrix/lfi.txt`, player 1 driven by logic frame, latency 8, ring 9 back every 10, 62 s,
reader every 10 logic frames 2,700-3,300; each against its own reference without rollback):

| Match | wrong guesses / corrections | fight hash, by logic frame | reader |
|---|---|---|---|
| Mario vs DK, Castle 64, hazards | 255 / 50 | 0 different over 0-2,881 (2,282 frames run again) | 0 different (158,112 values; gimmicks in one run only) |
| Link vs Samus, Battlefield | 255 / 50 | 0 different over 0-2,881 | 0 different (218,943 values: fighters, weapons, items) |
| Mario vs DK, Battlefield, items falling | 255 / 50 | 0 different over 0-2,881 | 0 different (171,861 values, 13,749 of them items') |

With Final Destination (14:19): **four matches, two judges, rollbacks that replay corrected inputs end as the fights
that had them** (the guesses and corrections are the same counts because they depend on P only).

**The double counter of the strict oracle** (02:33, 03:57): a code reading (agent) says the 24-byte block is
`android::RefBase::weakref_impl` (strong and weak counts, the object, flags), allocated by the SDK's
`RefBase::RefBase`; `f_710900fee0` is the SDK's `android_atomic_dec`; the game imports no RefBase symbol; the game
functions named as reader and writer only touch the same 64-byte line. **Checked by the allocation**: the block's
second return address is 0x7109033888, inside `RefBase::RefBase` (0x7109033860, 76 bytes), made at frame 5 of the boot.
Two methods: an SDK object's reference count, not the game's. New cause `sdk refcount` in `oracle.py` (a block whose
allocation chain passes through the SDK's `android::RefBase` constructor, resolved by name); Steve vs Inkling: PASS
(on its older trace, read with `SSBU_STALE_MAP=1`; the rule uses allocation addresses only).

**A comparison by content** (step 2). The containers of the items' run, read by an agent
(`research/map/code_reading/`, below): a libc++ `unordered_map` keyed by hash40 (nodes {next, hash, key, 64-byte value
starting with a name}; head in a holder object at + 0x260 .. + 0x280), event subscriber lists (order matters: the
subscribers are called in list order) and `lib::L2CAgent`'s map of function hashes. `oracle.py`'s new last cause,
**moved content**: a line is the same contents in other nodes when each of its differing words, heap pointers masked,
is among the round's differing words after, and its word after among those before. Placing words by their block was
tried first and failed: the blocks known (alive at the run's end) are not the nodes' blocks at the comparison (nodes
are freed and reused).
- On last night's items run (`st_items4`, read with the stale map): unexplained lines 17 / 40 / 42 -> 2 / 2 / 5.
- **It still finds an error**: one hash40 word of one line it explained, changed by one bit in the round-2 file
  (`st3_mut`), and that line is unexplained again (50 moved / 16 unexplained -> 49 / 17).
- An injection in the game (`SSBU_RB_VERIFY_INJECT=2:site1` with `SSBU_POKE_SITES=7101f45450`: one node of the map, 6
  words) left no trace after the 60 frames: the node was written again or freed within the replay. The maps are built
  again from other state; an injected error does not stay in them (like `inj_work`, `inj_grav` of 02:33).
- A fresh run (`st3_items4`, the state dump on): 16-18 unexplained lines a replay, most of them nodes whose last
  reader is `f_7101f440a0`, which by the code reading frees every node of the map: freed memory, probably. To be
  settled with the live blocks at the comparison itself (next).

### 2026-11-12 14:51 — the strict oracle with items: the live blocks at the comparison; 5-8 lines a replay left (runs `st4_items4`, `st5_items4`)

`alloc_trace_snapshot` (hle_alloc_trace.c) writes the live blocks when the replay check captures its reference
(`alloc.live.r0`) and at each comparison (`alloc.live.r<round>`). New cause in `oracle.py`, before moved content:
**free at the comparison**: no block alive at the comparison or at the reference's capture holds the line, while a
traced block holds it at the run's end (jemalloc's heap, free at that moment; memory of other allocators, never in a
traced block, is not taken).

Four players with items falling (`st5_items4`, trace 1,000-1,239, replay check at 1,300, 40 s): fight hash equal on
the 3 replays; per replay 29-39 lines free at the comparison, 20-26 moved content, **5-8 unexplained** (were 17-42 last
night). The ones left: addresses where the reference and the replay hold different live objects (a map node on one
side, a block of another kind on the other: the allocator placed them differently); proving them the same contents
needs a walk of every object, not done. The audio thread found by the oracle here is guest thread 24, not thread 19 as
on other runs: the "sound" cause may take a little more than it should on this run. **Step 2 stops here** (45 min):
the map's maps are rebuilt from other state (an injected error does not stay), the counter is the SDK's, the content
comparison works and still finds an error; the oracle is not clean with items on the stage.

### 2026-11-12 15:15 — step 3, the map's sufficiency: the sites the simulation reads are not enough; three of last night's results were vacuous (runs `suf*`)

`SSBU_RB_ONLY_SITES=<file>` (hle_rb_state.c, hle_alloc_trace.c): the file names allocation sites by their first two
return addresses; their live blocks are tracked from the boot; every other page of the alias area is left out of the
saves and loads (`sm_skip`), so a load puts back only those blocks' pages (and the rest of guest memory: module data,
stacks, thread-local, kernel tables). `SSBU_RB_ONLY_SITES_GPU=1` keeps the GPU's memory too. `research/tools/suffice.sh`:
the replay check (save at fight frame 600, 60 frames, 3 replays) on Castle 64 CPU against CPU, judged by the fight hash
of every replayed frame and by the reader (a dump numbered by logic frame, `SSBU_STATE_DUMP_LF=1`, each replay against
the first pass: `match.py passes`). Lists: `research/map/only_sim_sites.txt` (474 sites: every row of `sites.json`
with state read by the simulation), `..._notable.txt` (without the 1,024-entry table's site).

**The first runs passed, and that was wrong.** Map, map without the table, an empty list, the map without the fighters'
pool: all four identical to the reference. The negative controls showed the test did not discriminate; the loads'
logs showed why: ~5,000 pages copied back in every case. **In a replay check the state map is off, and the load's
copy of the written alias pages did not look at the left-out set at all** (`sync`, the `K_ALIAS` branch without the
state map); an empty list also turned the mode off. So **last night's E1, E2 and E7-strict (pruning "PASS" under the
strict oracle) were vacuous**: nothing had been left out (their logs: ~5,400 pages copied back, as without pruning).
Annotated where they are written; the ring results (E3-E8), made with the state map on, stand. Fixed: the branch
skips the left-out pages, an empty list leaves everything out.

After the fix (`suf3_*`):

| Load puts back | pages copied back (load 1) | result |
|---|---|---|
| everything (control) | 5,031 | 3 replays the same: hash, and 155,520 named values a replay, 0 different |
| nothing of the alias area | 71 | **crash** at the first replay (host exception reading 0xffffffffffffffff) |
| the map's 474 sites (408 MB of pages: whole pages of 122,711 blocks) | 1,258 | **crash**, same place |
| the map + the fibers' sites (the code at 0x710353c000-0x710353e000: phx::Fiber objects, their stacks) | 1,249 | runs 1 frame, then the fighters' ControlModule differs (`get_pad_flag`, flick counters: input state), then a crash |
| + every site of the changed pages left out (825 sites) + the GPU's memory | 3,162 | **crash** (reading 0x10050) |

The crash of the map-only load is in `nn::os` fiber dispatch (`DispatchFiberContext` <- `f_710353c9b0`, the fibers'
code). **Which sites are missing** (`skip_diff_report`, now also for `SSBU_RB_ONLY_SITES`, called after the copy back:
the left-out set is made by the first load; the pages left out that changed since the save, by site, map + fibers):
1,467 pages: **916 GPU memory; Lua's heap (40-byte blocks of 0x71037294a4, 39-60-byte blocks of 0x710391785c:
about 800 pages); 57 pages in no live block (other allocators); the audio mixer's 321,328-byte block; the 1.7 MB frame heap;
1,216-byte blocks of 0x710363f304**; plus the fibers (crash) and the pads' state (the ControlModule difference).

**Reading.** The simulation's state (what its code reads back) does not make a load that works: a load must also put
back what the program's other parts hold consistent with it: fibers and their stacks, the input's state, the Lua heap
(its GC's bookkeeping), the audio and render engines, and memory outside the traced allocator. That is the night's
E3-E6 lesson again, now by site. Step 3 stops here (45 min); the next step would bisect that list with the same tool.

### 2026-11-12 15:24 — step 4: the weapons' and items' work variables, by a safe probe (runs `wv1`, `chkw`, `chkw_items`)

Weapons (category 1) and items (category 4) share one WorkModule class, 0x7104f74738, with the fighters' layout:
[module + 0x18] -> {instance table, status table, vptr, ...}; a table is {vptr, float count, floats, int count, ints,
flag-word count, flags} (seen in a dump: Mega Man's projectiles 20 floats, 32 ints, 6 flag words). The fighters' blind
calls of `WorkModule::get_int` on a weapon not in play had stopped the game (2026-11-12 00:54).

**The safe probe** (hle_state_dump.c): a getter with arguments is called on an object that is not a fighter only with
a guard (` guard=<loads>:<count offset>:<index>` in the getter list) that holds: every load from the module along the
path gives a heap pointer, and the table's count is above the index. 480 entries for the class (instance and status
tables: 64 + 32 floats, 64 + 32 ints, 192 + 96 flags; the guard skips what a given object does not have);
`argprobe.verify_entries` writes the guard; the reader reads the same variables from the dump (no longer fighters
only). 1,513 calls of getters with arguments in the list now.

**Checked by the game, no stop, 0 different, on six CPU-against-CPU matches of 60 s:** Marth vs Mega Man, Hero vs
Robin, Sephiroth vs Sora on Lylat (projectiles: 1.5-4.7 million weapon values a match, ~130,000 before the variables),
and the three item matches with items falling (items' values 117,000-200,000 a match, 13,000-24,000 before).
Two methods: the game's getter answers, and the reader's reading of the same bytes.
- (updated 15:35) **Corrected-input rollbacks on two more matches** (`lf6_*`): Kirby driven by logic frame against three level 9 CPUs
  (Shulk, Cloud, Bayonetta) on Battlefield, and Pikachu vs Fox on Pokémon Stadium 2 (hazards: the stage transforms):
  fight hash 0 different over logic frames 0-2,881 / 0-2,874, reader 0 different (208,498 / 265,472 values, the
  weapons' variables included). **Six matches now.**

### 2026-11-12 15:38 — step 4b: the tail's largest sites read from the code; match-level state checked by the game (run `mc1`)

A code reading (agent; `research/map/code_reading/tail_sites.json`) of the ten largest sites of the 95 KB tail:
- **simulation state**: `app::FighterEntry` (site 0x7100678184, one a player: the entry's FighterInformation, stock
  count, rebirth), the CPU AI's analysis block (0x710030b968, 8 records a fighter) and each CPU's AI context
  (0x71006b7018); probably the battle camera (0x7101346478: limit range, blast zones, target);
- **not simulation**: `lib::EffectManager`'s 104,592-byte block (0x710055d1ac, 128 effect slots: the tail's largest),
  the battle HUD's blocks (0x7101349620, 0x7101399f34, 0x710141fe44, 0x7101415578);
- the ~27 KB "outside every traced block", last read by `f_71039635c0`: the nus3 audio engine's update, its state
  in main's .bss: not jemalloc, not simulation.

**Checked by the game** (`SSBU_MATCH_CHECK=1`, hle_state_dump.c: at the first fighter's dumped frames, the bytes at
the offsets read from the code against the game's own getters): Castle 64, Marth vs Mega Man, four players on Kalos,
90 s each: stock count (entry + 0x1e8) against `FighterInformation::stock_count`, rebirth (+ 0x49c) against
`is_on_rebirth`, `get_fighter_information` = entry + 0xf0: 560-1,116 each, **0 different**; the camera's limit range
(+ 0xc20), dead area (+ 0xc30), target (+ 0xeb0) against `app::camera`'s getters: 279-280 each, **0 different**.
Added to `gamestate_map.json` (`match_state`). Whether a stock count changed in these runs (stock 99) was not looked at: that check may
be weaker than the camera's, whose vectors move.

### 2026-11-12 16:03 — new method, step 1: the community's names, confirmed by the game (run `const`, `names1`)

The user changed the method (15:4x): import the names the Smash Ultimate modding community already published, read
every module's structure from the code with one read-only subagent per module, have the game check all of it, and
report the share of the changing bytes now named.

- **Imported** (`research/map/community/`, sources, commits and licences in `SOURCES.md`): skyline-smash's
  `lua_const.rs` (38,774 constants: status kinds, work ids, object kinds..., MIT), param-labels' `ParamLabels.csv`
  (hash40 labels, MIT), and a port of the crate lua_bind_hash 1.0.1 (MIT; checked against its test vectors).
- **Checked by the game**: `SSBU_CONST_CHECK=<file>` (hle_state_dump.c) asks the game, once at the first dumped frame,
  `lib::lua_bind_get_value<int>` of each name (its xxh64, as lua2cpp_common gets its constants). On Marth–Mega Man:
  **38,579 the same value, 2 different** (`FIGHTER_EFLAME_STATUS_SPECIAL_HI_TERM`, `FIGHTER_STATUS_TRAIL_REBOUND_WORK_TERM`:
  the community's values are off), **193 unknown to the game** (names the game's table does not hold: `APPEAL_HI`,
  `_100_ATTACKER`...). Two methods: the community's value and the game's own answer, independent. Only the 38,579 go
  into `research/map/community/confirmed.csv`. (Aside: `hle_paramconfig.c` falls back to 0x1000000b for
  `FIGHTER_INSTANCE_WORK_ID_INT_COLOR`; the game says 0x10000042. Not changed: upstream code, and the fallback is used
  only when the lookup fails.)
- **In the reader** (`research/tools/community.py`, `reader.py`): a fighter's kind from its work variable
  `FIGHTER_INSTANCE_WORK_ID_INT_KIND` (0x10000001); its work variables by id (instance first, then status: a list when
  several statuses share an id); its status kind (common, else the fighter's own); its motion's hash40 label; a
  weapon's names through its owner's kind (`WEAPON_INSTANCE_WORK_ID_INT_LINK_OWNER`). On Marth–Mega Man (frame 2640):
  `MARTH ... status 0x22 FIGHTER_STATUS_KIND_ESCAPE_AIR ... motion escape_air_slide`, `ROCKMAN ... 0x1e3
  FIGHTER_ROCKMAN_STATUS_KIND_ROCKBUSTER_SHOOT_WAIT ... motion attack1`; 555-559 of a fighter's 846 work variables
  named (11-17 more with several candidates), 33 of a weapon's 332. The automatic check on the same run: 1,380,085
  values equal, 0 different.

### 2026-11-12 16:11 — step 2-3: every module's structure read from the code, then checked by the game's own writes (runs `ww1`, `names1`, `names2`)

- **Code reading** (`research/map/code_reading/modules/<Module>.json`, 38 modules: every module of the dossiers but the
  four already read; and, in `code_reading/objects/`, the weapon and item objects themselves): read-only subagents, one per module (small ones grouped), over the generated C of
  build-trace: constructor, every exported method's slot function for the fighter's class; out: offset, size, type,
  name, getter, how, certain/probable, evidence (function names). Words and offsets only, no code.
  4,518 fields proposed (record arrays counted per record).
- **The game checks it** (`research/tools/verify_reading.py`): three checks, independent of the reading.
  - W, new: `SSBU_WRITE_WATCH=<file>` (hle_memtrace.c, build-trace): while the access trace's window is open, every
    write of the game's code into a module object, or into a block behind one of its first 16 pointers, that the
    state dump registered is noted once per (category, module, block, offset, size, writing function). Three fights
    of 1,800 traced frames (Marth–Mega Man CPUs, Diddy's bananas, Samus–Fox with every item falling): 8,685, 21,694 and
    52,044 distinct writes. A field passes W when the game wrote exactly its span (offset and size); W+ when the writer
    is also one of the functions the reading names.
  - R: the getter's probe (`getter_regions.json`): the getter the reading names reads these bytes.
  - V: the dictionary's plain loads, which the series' automatic check compares with the game every 20 frames.
  - **512 of 4,518 fields pass at least one** (W 330, W+ 101, R 149, V 139); `research/map/code_reading/verified_fields.json`.
    The rest stay proposals. W says where a field lies and how wide it is, not what it means: the name is the
    reading's; W+ ties it to the functions the reading read.
- **The share of the changing bytes named** (`research/tools/named_share.py`: bytes that differ between two
  consecutive dumped frames of an object, counted once per object, in the module objects and the dumped blocks behind
  them). Before = this morning's map (fields with a meaningful name; the work variables were only getter + id).
  After = + the community's names the game confirmed + the reading's fields the game confirmed.

  | match, category | changed bytes | named before | after, R/V/W+ only | after, with W |
  |---|---|---|---|---|
  | Marth–Mega Man, fighters | 10,120 | 5.3 % | 9.9 % | 16.3 % |
  | Marth–Mega Man, weapons | 1,595 | 9.5 % | 10.7 % | 13.7 % |
  | Marth–Mega Man, item | 1,143 | 5.7 % | 6.2 % | 8.7 % |
  | Diddy–Mario, fighters | 6,860 | 5.8 % | 9.2 % | 17.0 % |
  | Diddy–Mario, items (bananas) | 950 | 4.3 % | 4.9 % | 7.7 % |
  | Diddy–Mario, weapons | 402 | 10.4 % | 10.4 % | 15.4 % |

  Where the rest is (fighters, Marth–Mega Man): 72 % of the changed bytes are in blocks behind the modules' pointers
  (the attack records behind AttackModule + 0x68: 600; GroundModule + 0x28: 529; ShadowModule's: 600; the article
  queue; WorkModule's tables' headers), 28 % in the module objects (of them 27 % named after).

### 2026-11-12 16:18 — the write check's negative control; the observable fields; the objects' own kind

- **Negative control of W** (`verify_reading.py --shift <n>` / `--swap`): the same writes, against readings made
  wrong on purpose. Fields passing W (exact span written) / W+ (and by a function the reading names):

  | reading | W | W+ |
  |---|---|---|
  | as read | 330 | 101 |
  | every offset + 1 | 89 | 5 |
  | + 4 | 176 | 12 |
  | + 8 | 161 | 11 |
  | each module against the next module's writes | 74 | 2 |

  W alone does not discriminate enough: fields are packed with neighbours of the same width, which are written
  too (a field moved by 4 lands on its neighbour). **W alone is therefore only an upper bound; the map takes W+, R and
  V** (W+ against wrong readings: 2-12 of 101). This changes the "after" of the previous entry to its middle column.
- **Denominator**: of the 4,518 proposed fields, 1,712 lie where the write watch can see them (a module object's
  first 0x900 bytes; the first 0x100 bytes of a block behind one of its first 16 pointers; record arrays expanded to
  64 records). 230 pass W+, R or V; 512 with W alone.
- **The weapons' and items' own kind**: the reading of the objects (`code_reading/objects/`) puts the BattleObject's
  id at + 0x8 and kind at + 0xc, and the LuaModule holds the object at + 0x220. The state path `190 220 10` dumps those
  16 bytes (`argprobe.py` writes it with the getters' paths); the reader keeps the kind only when the id there is the
  record's, and reports for fighters whether it equals `FIGHTER_INSTANCE_WORK_ID_INT_KIND` (the game's getter): two
  checks by the game. Until then, a weapon-specific name found through the owner's kind is shown as a candidate only
  (it may belong to another of the owner's weapons).

### 2026-11-12 16:29 — the long series and the final named share, strict column (runs `ser_names`, `share`)

- **Series** (`wide.txt`, 12 matches of 120 s, the existing automatic check and the hash cross-check): 12 OK,
  **68,521,909 values equal, 0 different**, 0 hash lines differing. It checks the dictionary's fields (V) and the
  normal build after today's runtime changes; it does not check the reading's W+ fields, which have no getter.
- **Named share of the changing bytes**, strict column (after = community names the game confirmed + the reading's
  fields passing W+, R or V; W alone left out), three fights of 60 s, automatic check 0 different on each:

  | match | category | changed bytes | named before | named after (strict) |
  |---|---|---|---|---|
  | Marth–Mega Man | fighters | 10,156 | 5.3 % | 10.2 % |
  | | weapons | 1,648 | 9.3 % | 10.4 % |
  | | item | 1,276 | 5.5 % | 6.3 % |
  | Diddy–Mario (bananas) | fighters | 7,297 | 5.6 % | 8.9 % |
  | | items | 994 | 4.1 % | 4.7 % |
  | | weapons | 477 | 8.8 % | 8.8 % |
  | Samus–Fox, items falling | fighters | 11,184 | 5.1 % | 9.7 % |
  | | items | 10,646 | 4.1 % | 4.4 % |
  | | weapons | 2,549 | 6.7 % | 7.3 % |

- The object's own kind (path `190 220 10`): the id there is the record's for items only (31, 7, 214 records), never
  for fighters or weapons (their LuaModule + 0x220 is something else): items get their kind's names, weapons keep
  candidates. Not pursued: the user moved the priority to the minimal restore set (next entry).

### 2026-11-12 16:48 — new priority: the minimal restore set by reduction from the full savestate (runs `reduce/`)

The user's new single priority (16:2x, deadline moved to 20:00): find the minimal set of memory a load must put back
for a fight to go on identically, by automatic reduction from the full save (delta debugging), instead of building it
from what the simulation reads (step 3's map-only loads crashed).

- **Mechanism** (`SSBU_RB_UNITS=<file>`, hle_rb_state.c): the runtime keeps every live block the allocation wraps
  see (address, size, site = the allocation's first two return addresses; 2.05 million blocks in a fight) and a
  journal of their coming and going; a load computes the blocks as they lay at its state's save (the table now, the
  journal since undone) and copies each page back through `un_copy`, which leaves alone, **to the byte**, what the
  file says: `site` (a site's blocks; a byte belongs to its innermost block), `rest <lo> <hi>` (bytes in no block),
  `others` (blocks of sites the file does not know), `host <part>` (kernel, fibers, setjmp, vi, audio, net, ipc).
  `mode drop` names what is left alone, `mode keep` what is put back. realloc is now followed too.
- **Units** (`reduce.py inventory`, from `SSBU_RB_UNITS_INV` at the first load of a witness run on Samus–Fox, Castle
  64, hazards, every item falling, two CPUs): a full save puts back **2,168.8 MB** of guest memory = 12,935 sites
  (1,820 MB) + the bytes in no block by 16 MB slices (349 MB in the alias area, 40 MB of the modules' .data/.bss,
  8 MB of stacks, 0.2 MB thread-local) = **100.00 %** of the present memory; plus the gaps between the slices (so
  that the rest units tile the whole address space), `others`, and 7 host parts: 13,161 units, in 27 families.
- **The mandatory control** (judge A: save at fight frame 600, 3 replays of 60 frames, hash and reader identical, no
  crash):
  - witness, nothing removed: passes;
  - every unit kept, everything else left as it is: **first failed (crash)** with only 2,228 bytes left alone in
    135 ranges: blocks of sites the inventory had not seen (sites with no live block at the inventory's moment).
    Units were missing, as the user's rule foresaw: `others` added, and the gaps. **Now passes** (0 bytes left alone);
  - negative controls: empty keep list fails (crash); the fighters' pool (site 0x71014f48c0) removed fails (hash),
    with only 58,560 of its bytes actually different at the load.

### 2026-11-12 17:25 — reduction, by families (judge A, Samus–Fox with items; `research/runs/reduce/trials.jsonl`)

Each family removed alone (a load leaves its bytes as they are):

| family | units | MB | alone |
|---|---|---|---|
| main:mixed (main's sites the access trace labelled differently from run to run) | 3,130 | 757.7 | fails (crash) |
| gpu (sites with more than half their bytes in nvmap allocations) | 38 | 505.8 | passes 2 times of 4, hangs 2 (see below) |
| rest:alias (bytes in no traced block, alias area) | 124 | 348.8 | fails (crash, read at 0x10050) |
| scripts (allocations from lua2cpp / plugin code) | 550 | 214.7 | fails (crash) |
| main:unlabelled (sites the trace never saw) | 8,612 | 153.0 | fails (crash) |
| effects (EffectManager) | 40 | 64.2 | fails (no frame presented) |
| rest:modules (.data/.bss) | 22 | 40.4 | fails (reader differs; no crash) |
| main:other-state | 168 | 34.7 | fails (crash) |
| main:scratch | 123 | 17.3 | fails (crash) |
| pools (battle objects) | 22 | 8.3 | fails (crash) |
| rest:stacks (guest stacks) | 23 | 8.1 | **passes** |
| main:sim (state the simulation reads) | 171 | 6.4 | fails (crash) |
| main:output | 40 | 3.6 | **passes** |
| fibers | 23 | 2.3 | fails (crash) |
| sdk | 12 | 2.2 | **passes** |
| stage (collision records) | 1 | 0.6 | fails (crash) |
| table1024 (main's .bss) | 1 | 0.4 | **passes** |
| rest:tls | 1 | 0.2 | **passes** |
| hud | 5 | 0.0 | **passes** |
| rest:gaps, host: kernel, setjmp, vi, audio, net, ipc | | | **pass** |
| sites:unlisted (transient sites), host:fibers | | | fail (crash) |

- **The 13 families that pass alone, removed together: pass** (135 units, ~15 MB of memory and 6 of the 7 host
  parts: kernel tables, setjmp records, display queue, audio queue, net, ipc).
- **The GPU's memory does not pass**: alone it passed the first time, then with any other family the game hung (no
  frame presented), 3 times of 3 with the 13 families, and alone again 1 pass and 2 hangs. So 2 passes of 4 alone: a
  hang that comes about one time in two, the one SSBU_RB_SKIP_GPU was known for (the CPU's own data in the GPU's
  memory). A single pass of judge A is therefore **not proof** for a unit whose failure is a race: the GPU's units
  need repeated passes (three), and the final set is validated with repeats and the long ring.
- The table of 1,024 entries passes removed: within 60 frames its bytes that differ are not read back (to be
  confirmed by the long ring).
- Search inside the 14 failing families started (bisection by bytes, largest groups first, 3 games at a time,
  resumable: `reduce.py search`).

### 2026-11-12 18:45 — reduction: a first search undone by a pass that was luck; the hang measured; the judge split in two

- **First search** (bisection by bytes, one pass enough, 17:25-18:14): removed 795 units in an hour, among them one
  group of 390 `main:mixed` sites (393 MB), then found nothing more for 27 minutes and "needed" units one after the
  other. **Checked instead of believed**: the base of 795 units alone failed 3 times of 3. Earlier bases, three times
  each: 135 units 4 of 4 (then 2 of 3), 525 units 3 of 4, 555 units 1 of 3, 574 units 2 of 4. Every failure of
  those a hang ("no frame presented"), no crash. The six "needed" units and ~50 trials of that search are void
  (state kept as `research/runs/reduce/search_state.gen1.json`).
- **A cause looked for in my own mechanism**: for a page left whole, `un_copy` rewrote one byte in place so that the
  write watch would see the page; a load beside the GPU's queue runs while the GPU's thread may write that page, and
  the rewrite could undo its write. Made an atomic OR of 0 (generation 2 of the trials; older results are not
  reused). **It did not remove the hang**: the GPU's memory alone still 1 pass of 3 (3 of 7 in all).
- **The 393 MB were the GPU's**: 4 `main:mixed` sites have bytes in nvmap allocations (under half, so the first rule
  missed them). A site with any byte there is now the GPU's family: 54 units, **899.4 MB**.
- **The hang measured** (judge A, three games at a time):

  | removed | passes |
  |---|---|
  | nothing (witness) | 6 of 6 (+ 2 earlier) |
  | the 6 host parts (kernel, setjmp, vi, audio, net, ipc) | 6 of 6 |
  | rest:stacks alone / main:output alone / sdk alone / tls + gaps + table1024 + hud | 6 of 6 each |
  | those memory units together (129) | 5 of 6 |
  | the 13 families together (135) | 6 of 7 |
  | the GPU's memory (38 sites of it) | 3 of 7 |

  So: no hang with nothing removed; none for each small family alone; about one in six once several are removed
  together; one in two with the GPU's memory. Every hang is "no frame presented" with no crash and no difference
  reported before it. Not explained today.
- **The judge, split in two properties**: *state-correct* (no crash; fight hash and reader identical on the three
  replays), which a run that did not hang decides; and *hang-free*, which only repeats can show. `reduce.py` now runs
  a trial again (twice at most) when it hung without a crash, records the hangs, and fails it after three. The
  search restarted so (generation 2), seeded with the groups the first search had passed, the GPU's family left out.

### 2026-11-12 18:52 — a more direct way than the bisection (the user's two suggestions, taken)

1. At a load, the runtime compares each page it copies back with memory and charges every differing byte to its unit
   (`SSBU_RB_UNITS_DIFF`). A unit with no differing byte at any load of the witness is removable **without a trial**:
   leaving it alone gives the witness's own execution.
2. The search then runs only over the units that differ, weighted by their differing bytes, not their size.
3. The hang is diagnosed from the watchdog's thread stacks (a read-only subagent on the freeze reports) instead of
   being worked around by repeats; the working hypothesis is the user's: presentation (GPU, display queue), not state.

### 2026-11-12 19:05 — the differing bytes: 5.5 MB of 2,169 MB; the hang explained; 1.1 GB of sites removed with no hang

- **`SSBU_RB_UNITS_DIFF`** (hle_rb_state.c): at a load, every page copied back is compared with memory first and each
  differing byte is charged to its unit as it lay at the save. On the witness (save at 600, loads 60 frames later):
  **5.49 MB of bytes differ, of the 2,168.8 MB a full save puts back**, in 465 units of 13,161.
- **A unit with no differing byte is removable without a trial, but only in the run that measured it.** The first
  confirmation (every unit with none in one witness run, removed) crashed: measured in the trial itself, 32-110 of
  the removed units did differ there (130-180 KB), mostly `rest` slices. From one launch to the next the heap's
  addresses move, so **the 16 MB slices of bytes in no block are not units that hold from run to run** (which also
  explains the first search's lucky passes on `rest:alias` groups); and rendering and audio make other sites differ.
  Sites (the allocation's two return addresses) do hold.
- **Census over 6 witness runs, 18 loads**: 557 sites differed at least once (385 at every load), 716 MB in size
  (584 MB of it 7 GPU sites) for 4.97 MB of differing bytes; bytes in no block: 0.62 MB in the alias area, 20 KB of
  stacks, 373 bytes of the modules' data, 3 thread-local. 12,383 sites never differed.
- **Removing the 12,383 never-differing sites and 6 host parts** (trials now report the removed units that differed
  in the trial's own run): state-correct 3 of 3, but each after one hang.
- **The hang explained.** (a) The watchdog's stacks (read-only subagent over 55 freeze reports): the load is over
  ("back in the save's frame"), every lock free, the GPU thread idle; in 48 of 55 the main thread spins at the frame
  end in an unexported NVN function of the SDK (`sdk+0x427010`) that polls the clock: a wait on the GPU side that
  never ends. Presentation, not state: the user's hypothesis. (b) The trials' own differences: in the 3 runs that
  hung, and in none of the 3 that passed, the removed units that differed were the blocks allocated from
  **0x710373e524** (three callers, ~128 KB differing). Two methods, same place.
- **With every site allocated from 0x710373e524 put back (91 sites, 2.13 MB): 6 passes of 6, no hang**, removing
  12,303 sites and 6 host parts. In each run 2-15 removed sites still differed (0.5-4.6 KB) and the fight went on
  identically: bytes that differ and are not needed.
- Validation of that set running (long ring, six other matches, corrected-input rollbacks).

### 2026-11-12 19:42 — the never-differing sites removed: 921.7 MB; validated on 7 matches; the ring shows what is still missing

- **The Samus–Fox set did not hold elsewhere**: its 12,303 "static" sites, removed, crashed 5 other matches and the
  ring (other fighters and other moments make other sites differ). A unit that breaks one match comes back: the census
  was widened (`research/tools/reduce_census.py --runs 6 --matches --ring`): 17 witness runs, **639 loads**, the 7
  validation matches (2 and 4 players, items, hazards, a stage that transforms, a moving stage) in replay checks and
  4 of them in the ring (150 loads each). 3,003 sites differed at least once (680 of them unknown to the search
  match's inventory, covered by `others`); bytes in no block: up to 2.3 MB in the alias area at one load.
- **Removed: the 10,548 sites that never differed, 921.7 MB = 42.5 % of what a full save puts back**
  (`research/map/minimal_set.md`, list in `minimal_set_state.json`).
- **Validation**:
  - judge A (3 replays of 60 frames; hash and reader), with the 6 host parts removed too: **7 matches of 7 pass**;
  - the long ring with the 6 host parts removed: hangs at its 2nd load on 3 matches of 3, **with no removed site
    differing**: in the ring the host parts (kernel tables, display queue...) are needed; they stay (glue);
  - the long ring with every host part put back: **the four-player match with items passes: 150 loads, 149 frames
    groups the same / 0 different, reader 1,047 frames run again, 7,508,207 values equal, 0 different**; Samus–Fox
    hangs after 33 and after 63 loads, where 26 and 7 removed sites differed (17 distinct, the largest 656 bytes):
    more sites of the 0x710373e524 kind. They are added to `research/runs/reduce/ever_differ_extra.json` for the
    next run. So the ring is not passed on every match yet, and the corrected-input rollbacks (judge L, in
    `reduce.py validate`) were started but not finished (stopped with the validation at 19:33).
- **Not done**: the search inside the 2,387 kept sites (which of the differing ones are needed), now a bisection
  weighted by differing bytes (`reduce.py search`); the GPU's 13 differing sites (650 MB in size, 5.9 MB differing)
  are kept whole (removed, the game hung 4 times of 7); the bytes in no block (389 MB) are kept whole because their
  slices do not hold from run to run: they need units of their own (the other allocators' blocks, fiber stacks).
- What the method gives, in one line: **the upper bound of what a rollback must put back is what differs at the
  load, a few MB, not the 2.17 GB**; the sites that never differ are proven removable by construction and by the
  fights; the minimal set lies inside the 2,387 sites that do, the bytes in no block and the host state.

### 2026-11-12 19:48 — the ring's candidates put back: the long ring passes on Samus–Fox and Stadium 2; where it stops

- With the 17 sites that differed in the hung ring runs put back (`ever_differ_extra.json`), the set is **10,531
  sites, 921.4 MB**, every host part put back. Long ring (150 loads, 5 back every 6): **Samus–Fox with items: 0
  different, reader 1,047 frames run again, 5,493,221 values equal; Pokémon Stadium 2 (Falco–Ike): 0 different,
  3,089,697 values equal**; replays on Samus–Fox pass. With the four-player items match (passed with the 10,548
  set, of which this one is a part), the ring passes on 3 matches; judge A passed on 7 with the larger set and the 6
  host parts removed. `reduce.py set` now makes this set from the census and the extra list (it was inline scripts).
- **What is and is not shown** (after a review of the day's claims):
  - this is a **candidate set and an upper bound**: in each trial 2 to 37 removed sites still differed in the
    trial's own run, so the census has not converged; a hang names the next sites to put back;
  - the ring was not run on the other 4 matches with this exact set, nor the corrected-input rollbacks (judge L:
    its matches, `lfi.txt`, are not in the census yet, and would likely fail as the other matches did before it
    was widened);
  - the negative controls (empty list, no fighters' pool) last ran at 16:48, before the atomic touch, the
    differing-bytes hook in `un_copy` and the hang-retry judge: to run again first (`reduce.py controls`);
  - "the host parts are needed in the ring" does not say which of kernel and vi; setjmp, audio, net, ipc with
    kernel and vi put back hung too, but in a run where removed sites differed: not separated;
  - the weighted `reduce.py search` (inside the sites that differ) has not run in its new form;
  - the sites' total is 1,770.9 MB by the units file (an earlier entry said 1,820 MB: that added the first
    inventory's rest bytes of the GPU split; the units file is the reference).

### 2026-11-12 19:50 — the controls again, with the day's last runtime and judge

`reduce.py controls`, generation 2 (atomic touch, differing-bytes hook, hang-retry judge): witness passes; every
unit kept passes; empty keep list fails (crash); the fighters' pool removed fails (hash). As expected. End of the
day's work at 20:00; the next steps and their commands are in `research/map/minimal_set.md` ("To go on").

### 2026-11-12 20:02 — the night's run (until 23:00, the user's word): plan

`research/tools/reduce_night.py 22:40`, unattended: (1) judge L's witness on its three matches, whose differing sites
join the census; (2) the census widened (the ring on all 7 matches, a second replay run of each); (3) a loop: the
candidate set from the census, its validation (replays and long ring on 7 matches, corrected inputs, repeats), every
removed site that differed in a failed trial put back, again until all pass; (4) if validated and time is left, the
search inside the sites that differ (first run of its weighted form), validated again or dropped; (5) the report.
Each step is logged in `research/runs/reduce/night.json`. Tomorrow: the reads' tracking (which differing bytes the game
reads before it writes them), with read-only subagents on NVN's wait, the other allocators and the kept sites' labels.

### 2026-11-12 21:29 — the night's run: what it gave before it was stopped (low memory, about 21:25)

- **Judge L's witness** (corrected-input rollbacks, nothing removed, against `research/runs/lf5_ref`): Link–Samus
  passes (0 different over 821 frames run again). My judge first called it a failure: with corrected inputs
  matrix.py's verdict is DESYNC by design; fixed (trial key "L2"). Its negative control (no fighters' pool) fails as
  it must. The two other matches are left out: on `lf_castle` the comparison is 0 different over 725 frames but the
  run does not end (the fight is over before the limit and waits on the results screen); on `lf_items` the witness
  differs from the reference from logic frame 1 (the reference no longer matches: to be made again).
- **Census widened**: 28 witness runs, 1,260 loads (the ring on all 7 matches, a second replay run of each, judge
  L's witness): 3,197 sites differed at least once (794 unknown to the inventory, covered by `others`).
- **The loop** (set, validate, put back the removed sites that differed in a failed trial):
  - 10,458 sites (921.2 MB): 12 trials of 17 pass; 117 sites put back;
  - 10,341 sites (920.4 MB): replays 7 of 7; **long ring passes on 5 matches** (Stadium 2, four players with items,
    Lylat, Hero–Robin, Marth–Mega Man: 150 loads, 0 different, 2.5 to 7.5 million values each); Samus–Fox ran past
    the 330 s limit of then (not a verdict); four_cpu_kalos fails after 125 s and judge L on Link–Samus after 195 s
    (real failures: 3 removed sites differed in each); 24 sites put back;
  - 10,317 sites (920.3 MB): replays 7 of 7; long ring passes on Samus–Fox (5,493,221 values) and Stadium 2; the
    other trials (the ring on 5 matches, judge L, the repeats) had not run when the session's background run was
    **stopped by the system for low memory** (three games of ~9 GB each and the ring's reader). Not started again:
    the note says to wait for the user.
- Two failures of my tools on the way, both fixed: an unreadable dump (a game that crashed early) raised in the
  ring's reader and ended the first night run at 21:1x; the ring's limit of 330 s was under the time three rings in
  parallel take (now 480 s; a trial's reason now tells hang, crash and plain timeout apart).
- **State**: candidate set 10,317 sites, 920.3 MB (42.4 % of a full save), in `research/map/minimal_set_state.json`;
  the validation table of `minimal_set.md` lists the trials of the 10,341 and 10,317 sets. The search inside the
  sites that differ has still not run. To go on: `deps/python/python.exe research/tools/reduce_night.py <HH:MM>`
  (with two games at a time if memory is short: `Args.jobs` in that file).

### 2026-11-12 22:27 — a set that passes the whole judge: 10,283 sites, 920.3 MB (the night's run, two games at a time)

The run was started again at 21:33 on the user's word, with two games at a time (`reduce_night.py 22:40 --jobs 2`).

- 10,317 sites: 16 trials of 17 pass; the one failure, the ring on four_cpu_kalos, was "ring reader": 34 sites put back.
- **10,283 sites, 920.3 MB (42.4 % of what a full save puts back), every host part put back. Every trial passes:**

  | judge | matches | result |
  |---|---|---|
  | A: 3 replays of 60 frames, fight hash and reader | the 7 matches (2 and 4 players, items, hazards, a stage that transforms, a moving stage), + 2 repeats | 9 of 9; 0 different |
  | B: the ring, 150 loads (5 back every 6), hash and reader | the 7 matches | 7 of 7; 0 different; 1,047 frames run again and 2.5 to 7.5 million reader values each |
  | L: rollbacks that replay corrected inputs, against the run with the true inputs | Link–Samus | 0 different over 821 frames run again |

  Negative controls of the day's last tools: empty list fails, no fighters' pool fails (A and L).
- **A tool fault to know**: the "ring reader" failures (four_cpu_kalos at 10,317; items_cpu_four and Stadium 2 at
  10,283) were dumps the reader could not read ("bad record at 4") in runs whose ring was 0 different; run again,
  the two of 10,283 pass with the reader (7,508,207 and 3,089,697 values equal). Cause not found (the dump is now
  kept when it happens). So the 34 and the 28 sites put back after them were put back for nothing: the set is
  smaller than it could be by that much, and `ever_differ_extra.json` holds 28 sites more than the validated set
  leaves out (the validated set itself: `research/runs/reduce/validated_state.json`, `research/map/minimal_set_state.json`).
- **What this is**: a set proven sufficient-to-leave-out on these 7 matches under the three judges; an upper bound
  of the minimal set (the sites that differ, 1,248 MB in size with the GPU's and the bytes in no block, are all
  still put back); and bound to the census: a fighter or stage not in it can make another site differ. Judge L ran
  on one match only (two references to make again).
- Not run: the search inside the sites that differ (no time left after the validation).

### 2026-11-12 23:00 — a step back: what today's result is worth, and tomorrow's plan

- **The ring judge is self-referential.** Judge B and its reader compare each frame run again with its first pass in
  the same run; that first pass already ran after earlier partial loads, so a stale byte read more than 5 frames
  later is in both and is not seen. Judge A is clean but 60 frames long; only judge L compares with an independent
  run, on one match. "Passes the whole judge" (previous entry) is therefore not "proven": tomorrow's first step is
  a no-rollback reference per match, compared by logic frame to the fight's end.
- **No speed gain is shown.** A load already copies only the pages written (about 20 MB); `SSBU_RB_UNITS` masks loads
  and leaves saves as they are; sites that never differ cost next to nothing before. The 920 MB are understanding.
- **Where the minimal set and the gamestate are**: in what differs (2,404 sites, the GPU's memory, the bytes in no
  block). The direct way: the bytes the game reads before it writes them after a load (the trace build sees every
  access of the game's code), validated in the same run (replay 1 records, replay 2 puts back only those, replay 3
  is the negative control), then attributed to modules and fields: "carried" or "recomputed", a property of the
  code, hence the map by invariants. Plan, order, constraints and stop points: `research/PLAN_2026-11-13.md`.

### 2026-11-13 09:48 — the judge repaired: against a launch with no rollback (judge R)

- **What it is.** `research/tools/refjudge.py`: a run with loads is compared with another launch of the same match
  that never loaded anything, logic frame by logic frame: the fight hash's lines (new `SSBU_FIGHT_HASH_LF=1`,
  `hle_fight_test.c`: each line ends with the game's own logic frame counter) and the reader's values
  (`SSBU_STATE_DUMP_LF=1`), the LAST pass of each frame (the state the fight went on from). `reduce.py`: judge "R" =
  the ring (150 loads, 5 frames back every 6) then the fight to its 40th second, about 800 frames after the last
  load; steps `refs` and `judge`. Horizon: hash lines of logic frames 1 to about 2,300 (every frame), reader every
  3rd frame from 591 to 2,148 (a dump of every frame is 23 GB a run).
- **Reference against reference first.** Two launches with no rollback of the search match: 4,912 hash lines and
  8,141,044 reader values, 0 different. One thing found: the dump saw the 4 stage objects in one launch and not in
  the other (it learns of them when a script asks); an object seen by one run's dump only is not compared, and counted.
- **Controls, on the search match** (items_cpu_samus_fox): full restore PASS (4,598 hash lines, 2,734,598 values,
  0 different); the fighters' pool removed FAIL (3,382 hash lines differ, first at logic frame 602); empty list FAIL
  (crash).
- **The set of 2026-11-12 (10,283 sites, 920 MB left alone): PASS** against the run with no rollback (4,602 hash
  lines, 2,712,238 values, 0 different). It stays as stated, now on a judge that is not self-referential, on this
  match; the six other matches are to run (`reduce.py judge --all`).
- Disk: 16 GB were left this morning; two dumps of 23 GB removed. Dumps are deleted after their digest.

### 2026-11-13 10:28 — read before written: what a load must put back, measured to the byte (SSBU_RF)

- **The idea.** A byte a load puts back matters only if the game reads it before writing it. The trace build
  (`SSBU_MEMTRACE`) reports every access of the game's code; new: `SSBU_RF` (`hle_memtrace.c`, `hle_rb_state.c`) keeps,
  from the first load of a run, the first access to each byte (a byte of state per byte, tables of 2 MB), and at the
  second load sorts the bytes that differ from the saved state: read first, written first, written first then read
  by another thread ("handed over"), not touched. Tool: `research/tools/readfirst.py` (ref / run / show).
- **What the trace did not see, and now does** (reader 3's report, checked in the code): the runtime is compiled
  without the trace, so the native libc (memcpy, memset, memcmp, str*: `hle_libc.c`), the pad state (`hle_hid.c`) and the
  kernel's, the IPC services' and the graphics driver's own guest words were invisible. The libc and the pad report
  their accesses by hand (`rt_rf_native`); `SSBU_RT_TRACE=<regex>` (tools/recomp.py) compiles chosen runtime files
  with the trace (kernel, ipc*, hle_nv, hle_fiber, hle_unwind, gpu). The fight hash's own getters are left out.
  Still outside: the GPU thread's reads of buffers through host pointers, the fibers' switch.
- **The numbers** (21 recordings: 7 matches, windows of 6, 10, 20, 60 and 120 frames; trace build's fight = normal
  build's, 4,800 hash lines identical):
  - bytes that differ at the load: 1.2 MB (6 frames after the save) to 4.0 MB (120 frames);
  - **read first: 241,000 to 331,000 bytes in every recording, whatever the window and the match** (6 to 21 %);
  - written first: 64 to 73 %; handed over between threads: about 24 % at 60 frames; not touched: under 1.5 %.
  - Search match, 60 frames (3,112,237 bytes differ): GPU 1,722,891 written first, 0 read first; nvn-sync (the
    blocks of allocator 0x710373e524) 226,050 read first of 257,760; main:mixed 23,175 read first, 517,039 handed
    over; pools 613 read first, main:sim 436, stage 161, effects 194, scripts 109.
  - Reading code of the read-first bytes: one function, f_7103996aa0, reads 198,540 of them (the nvn-sync blocks);
    the game's own classes (app) 484 bytes, the scripts 190.
  - Second method for yesterday's set: in the 10,283 removed sites, 0 byte differs at this load (read first 0,
    written first 0, not touched 0).
- **Validation in the same run, and what it showed.** Second load leaving alone the written-first bytes, the fight
  then judged against the launch with no rollback to its end:
  - negative controls FAIL as they must: the read-first bytes left alone (crash), and those of the pools, main:sim
    and stage only (1,205 bytes: the hash differs);
  - every family alone PASSES (3 or 4 times of 3 or 4: main:mixed, bytes in no block, main:other/scratch/output,
    stacks, pools/sim/stage/effects/scripts, nvn-sync); the fibers FAIL; the GPU's FAILS 5 times of 6 (hang, once a
    different hash);
  - **the union of the families that pass alone hangs about one time in two** (6 passes of 15 trials), with or without the kernel in
    the trace too. When it does not hang, the fight is identical to its end (0 hash line different). The hang is the
    one of 2026-11-12: main thread spinning in f_71037ca7f0 at the frame's end.
  - Reading: "written first in this window" is a fact about one launch. Between threads, which of a write and a
    read comes first is a race: a word a worker writes first in one launch can be read first in the next (a lock
    held at the load). With the bytes written by one thread and read by another kept ("handed over"), the union
    passes 5 times of 6. Not proven further; a single window cannot prove a byte dead.
- **Hence the invariant form** (`research/tools/carried.py`, `research/map/carried_state.json`): a byte is placed by
  (allocation site, block size, offset); over all recordings it is *carried* (read first at least once), *recomputed*
  (written first in every recording, at least 3), *handed over*, *few* (under 3 recordings) or *untouched*. Places
  (not bytes of one load): carried 487,317, recomputed 80,175, handed over 1,034,670, few 340,638. GPU sites, fibers
  and bytes in no block are left out. `research/map/recomputed_parts.txt`: the recomputed ranges as an
  `SSBU_RB_UNITS` file (new line "part <site> <block size> <offset> <length>").
- Stated limits: 21 recordings; the place of a byte is its block's site and size, not yet a module and a field; a
  block reached by a pointer from a module is its own site.

### 2026-11-13 11:49 — judge R on the 7 matches; the recomputed fields fail the ring: one load point is not an invariant

- **Judge R, the 7 validation matches** (`reduce.py judge --all`, normal build): each reference identical to a second
  launch of itself; full restore PASS on the 7; **the set of 2026-11-12 (10,283 sites, 920.3 MB) PASS on the 7**.
- **Generality test of the recomputed fields: FAILS, before reaching the unseen matches.** `reduce.py parts`
  (trace build, `REDUCE_EXE=build-trace`): the 15,049 ranges "written first in every recording" (21 recordings) left
  alone at each load of the ring, search match: hang at the 3rd load, 3 times of 3 (431 KB left alone a load). By
  family: main:mixed hang; scratch/other-state/output hang; the fight's families (pools, main:sim, stage, effects,
  scripts, hud: 2,267 bytes of places, 41.5 KB a load) crash at the 4th load; nvn-sync (20,700) PASS.
- **Why, tested.** Every recording of a match loads the same saved instant (fight frame 600): "written first" was
  measured from one load point. 66 more recordings of the search match, saves from frame 601 to 1,256 (6 frames
  after each): the places written first every time fall from 80,175 to 14,269, the fight's families' from 2,267 to
  692; those still crash the ring at its 4th load; with the ring's own first ten load points recorded as well, the
  ring reaches its 27th load before the crash. At the recorded load point alone (judge A, 3 replays of 60 frames)
  the fight's hash is identical with the parts left alone (the reader differs, as it must: a field left stale until
  its write is read by the reader before the game writes it).
- **Conclusion.** A field is "recomputed" only if the game writes it before reading it starting from every frame;
  sampled load points approach that from above and each new load point removes candidates. `carried_state.json`
  (87 recordings: carried 605,053 places, candidates 25,150, handed over 1,183,378, fewer than 10 recordings
  433,312) is a measurement, its "recomputed" are candidates (the file says so) and the candidates' units file is
  kept out of the map (`research/runs/rf/`). "Carried" is sure by construction (read first at least once) and only
  grows with more recordings.
- Tool change controls: judge R's two negative controls (above); parts: the carried bytes of the pools, main:sim and
  the stage left alone fail (the trial stopped at 42 s without the ring's line: counted as fail, cause not read).
  Normal build after the day's runtime changes: built, witness PASS (3 replays, 304,800 values, 0 different), the
  fighters' pool removed FAIL.
- Not reconciled: yesterday's "5.5 MB differ at a load 60 frames after the save" (normal build, `SSBU_RB_UNITS_DIFF`)
  against 3.1 MB today (trace build, second load). Not looked at.
- Not done from the plan: the incremental block list (step 2), the names of the carried places by module and
  field (step 4: the runtime writes the module objects' bytes by first access, `readfirst.py --modules`, and
  `carried.py` reads them, but no recording was made with it), the speed measurement (step 6), readers 1, 2, 4, 5.


### 2026-11-13 11:58 — checks on the entry above, corrections, and a first table by module

- **Checks made after the entry above.** (1) The nvn-sync parts trial that passed left 75,494 bytes alone at its
  first load: not an empty pass; one run. (2) The parts' negative control did fail by the game itself: after the
  first load, "indirect call to 0x60414ec338, which is outside every module". (3) Judge R skips objects seen by one
  dump only: in the 14 trials of `judge --all` none was skipped; on the search match 4 (the stage's); refjudge.py now
  fails on any object in one run only that is not a stage object.
- **Corrections.** The GPU's scoped trials: 1 pass of 7 (not "5 fails of 6"). "Why, tested" above is "supported":
  the crash moved from the 4th to the 27th load with the ring's first ten load points recorded, loads 12 to 26
  passed without their own recordings, and whether the key (site, block size, offset) puts different kinds of
  objects together was not tested. "Carried is sure" is too strong: read first is an observation of the game's
  code (constants only read are in it; the GPU's and the fibers' readers are not traced); that part of it is
  needed is shown by the negative controls only. The 5.5 MB / 3.1 MB gap: a possible cause is `un_diff_page`, which
  after 64 runs in a page counts the rest of the page as one run (`rf_copy` does not); not checked.
- **The check's own getters were in the recordings.** The replay check's hash (`fight_frame`, hle_rb_core.c) calls
  the game's getters (status, motion, position, damage) at every frame through generated code: they counted as the
  game's reads in every recording above (the "pools 613, main:sim 436, app 484" figures include them). Now paused
  (`rt_rf_pause`); the earlier recordings were not made again.
- **First table by module** (`readfirst.py --modules`, after that fix; 7 matches, save at frame 600, 60 frames; the
  state dump registers the module objects just before the save, and the second load writes each one's bytes by
  first access): fighters' module objects 11,535 bytes read first, 15,427 written first, 74 handed over; of the
  code reading's fields 38 read first (34 verified by the game), 29 written first, 3 handed over, 34 not touched.
  Sanity: pos, status_kind, motion_kind, frame are read first; a module's vptr is read first (a constant: read
  first is not "changes"). `research/map/carried_state.json`, "modules". One load point per match.


### 2026-11-13 12:17 — the table by module on 45 recordings; a counting error corrected

- **Error in the entry before.** `carried.py` counted the fields by class at most once per module: "38 read first,
  29 written first, 3 handed over, 34 not touched" was wrong. Corrected; for the same 7 recordings (one load point a
  match): 703 fields read first (234 verified by the game), 234 written first (162), 4 handed over, 227 not touched.
- **More load points** (38 more recordings with `--modules`: the search match at 20 save frames from 620 to 1,380,
  each other match at 800, 1,000 and 1,200; 30 frames after each): fighters' module objects 57,164 bytes read first,
  228 written first in every recording that touched them; fields: **1,124 read first (379 verified), 44 written first
  every time (41 verified)**, 0 not touched. From 1 to 27 load points the "written first every time" fields fall
  from 234 to 44.
- The 44: ShieldModule's hit log, registered and hit flags (also Reflector, Absorber), ItemModule's pickable item,
  JostleModule contact_state and jostle_kind, SlopeModule floor_diff_l/r, AreaModule's object ids, SearchModule
  is_inflict, CatchModule best_distance, CaptureModule reaction, EffectModule last_handle, LuaModule execute_line.
  Candidates for "recomputed each frame"; not tested by leaving them alone.
- Read first is not "state" alone: a module's vptr and pointers are in it. Separating what also changes is the
  next step. Other categories (weapons 42,704 bytes read first, items 12,264, stage objects 37,986, and a category
  15 the reader does not name, 145,166): bytes only.
- Normal build after the last runtime change (the check's getters paused): witness PASS, the fighters' pool removed
  FAIL, judge R's witness PASS with the stricter rule (4,596 hash lines, 2,712,238 values, 0 different).


### 2026-11-13 14:16 — afternoon: a reassessment, two retractions, the hang read, and a tracker with no load

- **Reassessment (13:40).** The question "is this byte needed by a load" is "after a rollback safe point, is the
  next access a read". That needs no load: in an ordinary fight every frame's safe point is a load point. Sampling
  loads (this morning: one saved instant per launch) was the wrong instrument. And what a save costs is pages, not
  bytes: of the ring's hot pages at the end of a fight (29,000 to 53,000, 114 to 208 MB) 41 to 46 % are the GPU's.
- **RETRACTION 1: the native memchr report was wrong.** `hle_libc.c` reported memchr's length argument as read; the
  game calls it with "no limit" lengths, so gigabytes were marked read first. Every recording of this morning made
  after 09:00 has it. Effect measured: 4.74 % of the bytes the morning's 87 recordings call "read first" are not
  live in a whole-fight run; with two recordings made again after the fix, 21 bytes of 508,547. The morning's
  figures "241,000 to 331,000 bytes read first" stand to a few percent (after the fix: 247,970 and 266,442).
- **RETRACTION 2: this morning's table "by module" was not the fighters' modules.** The ranges it used (the state
  dump's registrations at the frames just before the save, keys of category 0) are four other objects. Found with a
  debug probe: the object taken for a StatusModule is written every frame by ground-collision code and never read,
  while the real fighters' StatusModule (from the frame line's accessor, vptr 0x7104f89e88) has its status_kind read
  by the getter f_71004de560 many times a frame. The figures "1,124 fields read first, 44 written first every time"
  and the examples given with them are void. `research/map/carried_state.json`'s "modules" part is void too.
  The tracker now registers the fighters' modules itself from the frame line's accessors (each pointer of the
  accessor to an object whose vptr is in main's data).
- **The hang, read from the freeze reports and minidumps** (read-only subagent, report kept out of the repository,
  `research/runs/readers/`; 26 hangs sorted):
  - A (17-18 hangs): the main thread polls in `f_7109427010` (sdk+0x427010) until a u32 semaphore W (slot 0 of a
    GPU-memory block, site 71037fe52c 71094538c0) reaches a threshold; in the 14 dumps that hold W it is exactly
    threshold - 1: one release is missing. The guest queues the release command; the runtime's GPU thread writes W
    when it runs it. Reached both with the GPU's memory left alone and with the driver objects' bytes left alone.
    Why the release never runs: not determined.
  - C (7-8 hangs): `f_71037ca7f0` / `f_71037ca180`, the 64 KiB page-range manager under free(): it walks red-black
    trees (statics 0x710593D390..458 in main's .bss, records at 0x6FBF200000, both "bytes in no block"); a stale
    link makes a cycle. Allocator bookkeeping cannot be left half restored.
  - D (1): a first-fit heap walk (`f_7100088c50`) over a list of which 15 parts were left alone.
  - So the morning's hangs were not one cause: partial restore tore three different linked structures or counters.
- **The runtime's own GPU options under judge R** (search match, the ring's 150 loads): `SSBU_RB_SKIP_GPU=1` hangs
  (0 passes of 3; upstream's note says 3 of 7), `SSBU_RB_SKIP_GPU=2` passes 2 times of 3 (0 hash line different
  when it passes) and hangs once in A.
- **SSBU_LIVE** (`hle_memtrace.c`, `research/tools/live.py`): at each safe point (hle_rb_core.c, where the fight
  frame counter moves) every byte's first access starts again; marks per byte over its block's life: L read first
  after some safe point, D written first, H written first then read by another thread, W written at all; added to
  the block's place (site, block size, offset) when it is freed and at the end. A fight of 2,000 frames is 2,000
  load points; it runs in about 3 min 30.
  - Acceptance test (`live.py check`): the bytes two load recordings see read first (508,547) are live in the
    whole-fight run of the same match but 21.
  - First numbers, search match: pages the game's code wrote in 2,000 frames: 7,269 not the GPU's (5,749 with a
    carried byte, 305 handed over only, 1,215 dead) and 3,181 the GPU's (16 with a carried byte, 3,165 dead).


### 2026-11-13 15:07 — the fight's state by first access after every safe point: the map, its test on unseen matches, the ring

- **Runs.** `live.py run`: the 7 validation matches twice (tags a, b: 28,000 safe points), 3 matches never used
  before (tag u: smashville_corrin_mm, yoshistory_wiifit_krool, cpu_mac_joker). The fighters' module objects are
  taken from the frame line's accessors. Product: `research/map/live_state.json` (families, sites, the fighters'
  modules and fields) and the readable `research/map/gamestate_fields.md`.
- **Pages the game's code writes in 2,000 frames** (per match): 5,885 to 11,087 not the GPU's, of which 64 to 80 %
  hold at least one carried byte and 12 to 30 % are dead (every written byte is written before read at every safe
  point); 2,194 to 4,275 the GPU's.
- **The fighters' fields** (code reading's names; 14 runs): **378 carried** (268 verified by the game yesterday),
  **133 recomputed** (100 verified), 456 constant (read, never written in a fight: pointers, tables), 201 not
  touched. Carried: pos, prev_pos, lr, scale; status_kind, situation_kind; motion_kind, frame, rate; damage_log.
  Recomputed: status_kind_next, status_kind_interrupt, kinetic_type, saved_pos, start_pos, prev_frame_2nd.
- **Invariant test on the 3 unseen matches** (`live.py unseen`, no partial restore): of the 133 recomputed fields
  129 are recomputed there too, 3 are not touched, **1 is read first** (SearchModule +0x390 invalid_attack_mask).
  Of the 378 carried: 322 carried, 30 recomputed there, 12 constant, 14 not touched. Of the 2,380 dead sites, 405 are
  seen there and 2 have a carried byte.
- **In the ring (judge R, trace build, 150 loads, against the run with no rollback):**
  - by place (site, block size, offset), the recomputed ranges of the fight's families (9,550 ranges): crash at the
    27th load, an indirect call through a half-restored pointer. Blocks of one site and size hold different kinds of
    objects; cutting them by offset tears values. Dropped (the morning's "parts" trials had the same flaw).
  - by named field of a known object (new units line `modfield <offset in the accessor> <offset> <length>`,
    hle_rb_state.c; the fighters' recomputed bytes, 2,533 bytes of places, 8,299 to 11,216 bytes left alone at a
    load): **6 trials of 6 run the 150 loads with 0 hash line different** to the fight's end: the search match 3
    times, and the 3 unseen matches (other fighters, other stages) once each. The reader counts 939 to 1,428
    different values in them: the fields left alone are stale until the game writes them, and the reader reads
    them in between; not itemised field by field. Negative control, the carried bytes left alone (4,611 bytes of
    places): crash.
- **Whole sites.** Sites with written bytes and none carried or handed over ("dead"): 2,380, of which 2,132 are not in
  yesterday's set: 2,009 sites the inventory never saw (short-lived blocks), 7 GPU sites (44 MB), 114 others (2.6 MB).
  Yesterday's set plus all of them: hang, 2 times of 2 (the GPU's). At the grain of sites, yesterday's set is
  the minimal set to within 2.6 MB, outside the GPU's memory.
- **The GPU's memory, explained.** For the game's code its pages are dead (95 to 99.5 %: it writes them and never
  reads them back). With the GPU thread's reads of the command lists reported to the tracker (gpu.c, `gpu_submit`):
  1,414 of the 3,195 GPU pages the game writes hold bytes written before a safe point and read by the GPU thread
  after it (family gpu: 3.88 MB of carried places against 0.45). Commands queued before the save and run after it
  are state. That is hang A of the entry above (the semaphore one release short), and why `SSBU_RB_SKIP_GPU` hangs.
- **Times, one game alone, normal build** (`matrix.py`, ring 600,6,5,150, search match): a rollback of 5 frames
  costs 89.8 ms: the load 74 ms (the last loads 123 ms, all of it the undo of about 39,000 pages, 152 MB), then 7
  frames run again at 3.2 ms each (their save's memory part 0.8 ms). With `SSBU_RB_SKIP_GPU=2`: the same (73.7 ms;
  36,543 hot pages against 40,403). A sampled save: 30,186 pages copied, 28,896 pages committed or decommitted.
  The game's code writes about 10,500 distinct pages in a whole fight, 7,200 of them with a carried byte; a load
  undoes 39,000. Most of what a load puts back is therefore not the fight's state: the GPU's memory (16,000 hot
  pages) and pages committed and decommitted. Not investigated further; no speed gain is made.
- Normal build after the afternoon's runtime changes: built, witness PASS, the fighters' pool removed FAIL.


### 2026-11-13 15:52 — corrections to the entry of 15:07, the final map on 21 matches, the ring from the repository's tool

- **Corrections to the entry of 15:07.**
  - The first ring trials "by named field" left alone 2,533 bytes of places, of which 458 belong to an accessor
    pointer with no name and a guessed extent; not "the 133 fields". Made again below with the named modules only,
    each cut at its own class's size.
  - "Yesterday's set plus all of them: hang (the GPU's)" was not separated then. Done since: yesterday's set plus the
    114 known dead sites that are not the GPU's hangs too, 2 times of 2. So no site is added, and "never read first
    by the game's code" is not enough to leave a site alone. Why: not read.
  - "The GPU's memory, explained": checked against the objection that the tracker makes no save and the GPU thread
    may simply lag. With the GPU's queue drained at every safe point (`SSBU_LIVE_DRAIN=1`), 1,382 of 3,184 GPU pages
    still hold bytes the GPU thread reads after a later safe point (1,414 without the drain). The claim stands as:
    command memory written before a safe point is read after it; that it is the cause of hang A is consistent, not
    shown by a fix.
  - Times: "most of what a load puts back is not the fight's state" is an inference from two counts that are not
    of the same thing (a save copies about the whole hot set, a load's own writes make pages hot, the loads grew
    from 74 to 123 ms in the run). Kept as an open question; the breakdown is the next step.
- **The map on 21 matches** (28 runs: a, b, u and 11 more matches, tag c; one of the 12 asked did not start):
  fighters' fields 428 carried (276 verified), 135 recomputed (97), 439 constant, 166 not touched. The recomputed
  count as matches are added: 133 (7 matches), 133 (10), 135 (21): it does not fall.
  `research/map/live_state.json`, `research/map/gamestate_fields.md` (`live.py agg --tags a,b,u,c`, `live.py md`).
- **The ring from the repository's tool, normal build** (`reduce.py parts --parts-file <file> --match <name>`; judge R
  with the fields rule: no hash line different, no object in one run only, only fighters' modules differ):
  - the recomputed bytes of the named modules (2,001 bytes of places; 8,476 to 9,728 bytes left alone at a load):
    search match PASS (4,596 hash lines, 0 different), smashville_corrin_mm PASS (4,582), yoshistory_wiifit_krool
    PASS (4,626); modules that differ for the reader: fighter StatusModule, ControlModule, AttackModule only;
  - the map of the first 7 matches only, on a match it never saw (cpu_mac_joker): PASS (4,546 hash lines, 0 different);
  - control, pos and status_kind alone (168 bytes): FAIL, 3,417 hash lines differ; control, the carried bytes: crash.
  - Limit kept: SearchModule's invalid_attack_mask is in the recomputed set of the 7-match map and is read first in an
    unseen match; the ring did not see it. The tracker is the finer judge for one field.
- Normal build after the last runtime change: built, witness and negative control below.


### 2026-11-13 16:07 — where a load's 39,000 pages come from: memory the game gives back and takes again, after loads only

- **In the runtime's own lines of the timing run** (ring 600,6,5,150, one game alone): the first loads undo about
  12,000 pages in 21 ms; from about the 38th load 17,000 pages in 40 ms; the last ones 39,000 pages in 123 ms. The
  saves between them copy 1,100 pages in 2 ms at first, then 16,000 to 30,000 pages in 10 to 25 ms, of which 14,464
  to 29,328 are "pages committed or decommitted" since the save before.
- **What those pages are** (`SSBU_RB_CHANGES_LOG=1`, hle_rb_state.c and kernel.c): at every save the same ranges, e.g.
  0x60caa30000 + 0x1410000 twice and + 0x1600000 (20 and 22 MB), 16,416 pages in all. The calls are the game's:
  MapPhysicalMemory and UnmapPhysicalMemory from `f_71037ca180` / `f_71037ca7f0` (the 64 KiB page-range manager, the
  one of hang C) under `f_7103957ef0` and `f_7103958090`: 20 MB taken, given back, 22 MB taken, every frame.
- **When the game does it** (same match, same build unless said):
  - no rollback: fewer than 400 large memory changes in the whole fight (none logged);
  - `SSBU_RB=1`, no ring: the same;
  - the trace build's tracker, 2,000 frames, no save: 3,456 pages committed and 3,520 decommitted in all (58 ranges),
    no range moving 20 times;
  - a save at every frame, no load (`SSBU_RB_BENCH=300,2000`, trace build): 1,424 pages committed in all; the last
    saves copy 6,100 to 6,800 pages in 2.4 to 2.6 ms, 0 committed or decommitted;
  - the ring (a load every 6 frames): the give-and-take at every frame, from some tens of loads in.
  So it is the loads that bring it, not the saves. Why (the allocator's own state after a load against something a
  load does not put back, a clock for instance): not read.
- **What it costs**: with it a save copies 16,000 to 30,000 pages instead of about 1,100, and a load undoes 39,000
  instead of 12,000 (123 ms against 21). Whether those pages' content is needed across a safe point is not measured
  (the tracker's runs have no load, so they do not have it). This is the first thing to look at for a lighter
  rollback: it is 2/3 of a late load's pages, and it is not the fight's state by its origin (memory just taken from
  the system).
- **Correction to the page counts of 15:07 and 15:52**: they were taken from the bytes' marks at the end of the
  fight, after freed blocks had given theirs away. From marks kept per page for the whole window (new), search
  match: 9,010 pages written not the GPU's (7,171 with a carried byte, 511 handed over only, 1,328 dead) and 3,196
  the GPU's (1,414 with a carried byte through the GPU thread's command reads, 1,779 dead); cpu_marth_megaman: 6,942
  (5,574; 516; 852) and 2,195 (1,191; 1,000). So about 12,200 distinct pages written by the game's code in a fight,
  8,600 with a carried byte, against 12,000 undone by an early load and 39,000 by a late one.
- Normal build with these last changes (two env-gated logs, the tracker's memory notes): built; witness and negative
  control run last.


### 2026-11-13 16:14 — the heavy load is the ring's shape, not the rollback: a load costs 1 to 2 ms

- **Correction to "it is the loads that bring it" (16:07).** One game alone, normal build, the search match, rings
  of several shapes (`matrix.py --ring <from>,<every>,<back>,<loads>`), the runtime's own lines:

  | ring (every / back) | load, mean | a rollback caught up (load + frames run again) | last sampled save: pages copied, of them committed or decommitted |
  |---|---|---|---|
  | 6 / 5 (the judges' ring) | 73.9 ms | 89.8 ms, 7.0 frames | 30,186, 28,896 |
  | 10 / 9 (judge L's ring) | 138.4 ms | 162.6 ms, 10.1 frames | 61,519, 59,584 |
  | 7 / 5 | 1.53 ms | 18.7 ms, 5.0 frames | 1,175, 0 |
  | 8 / 5 | 1.47 ms | 14.9 ms, 5.0 frames | 1,242, 0 |
  | 10 / 5 | 1.24 ms | 13.4 ms, 5.1 frames | 1,093, 0 |
  | 12 / 5 | 1.66 ms | 16.0 ms, 5.1 frames | 1,152, 0 |
  | 30 / 5 | 1.19 ms | 12.7 ms, 5.2 frames | 1,983, 0 |
  | 6 / 2 | 0.79 ms | 5.1 ms, 2.0 frames | 1,598, 0 |

- So the game's give-and-take of 20 MB a frame, and the loads of 74 to 139 ms, belong to the two rings where the
  depth is the interval less one (one ordinary frame between two rollbacks), not to loads as such. With two
  ordinary frames between rollbacks (7 / 5) there is none of it. In the 6 / 5 ring it comes in steps at the same
  load numbers whether the ring starts at fight frame 600 or 900 (loads 36-38, about 58, 79, 108: 12,000, 17,000,
  22,000, 33,000, 37,000 pages undone). Why that shape does it: not read (a reading of the allocator is under way).
- **What a rollback costs, then**: the load 1.2 to 1.7 ms for 5 frames back (0.8 ms for 2), and the frames run
  again about 2.5 to 3.4 ms each. The memory a load puts back is not where the time is; leaving memory out of loads
  cannot gain more than that millisecond or two. The "90 ms" of the 15:07 entry is the 6 / 5 ring's.
- The judges (R, B: 6 / 5; L: 10 / 9) use the heavy shapes. That is a harder test, not a wrong one; their hangs and
  times are those shapes'.

### 2026-11-13 16:15 — the allocator behind the give-and-take, read (a reading, not checked by the game)

- Read-only subagent over the generated C (report kept out of the repository, research/runs/readers/): the functions
  are the game's jemalloc 5.x on top of the 64 KiB page-range manager. f_7103957ef0 = pages_map, f_7103958090 =
  pages_map_slow, f_71039581f0 = pages_unmap, f_7103930540 / f_710392f8f0 = arena_decay_stashed / arena_decay_to_limit.
  "Commit 0x1410000, unmap 0x1410000, commit 0x1600000" is one pages_map of a 20 MiB extent aligned to 2 MiB (first try
  not aligned, slow path maps more and trims). So in the heavy rings a 20 MiB extent is taken from the system each
  frame because the cache of freed extents is empty, and the decay purge unmaps it again each frame.
- The decay reads a clock (gettimeofday, down to the runtime's ticks); with the default fixed clock a load takes the
  clock back with the rest (kernel.c's snapshot), so "the clock is not restored" is not supported by the code. Which
  of the purge's three callers fires, the decay's settings, who asks for the 20 MiB, and why the two ring shapes
  bring it: not determined. Proposed check: log the arguments and the decay's words at f_710392f8f0 in a 6 / 5 ring
  and in a 7 / 5 ring. Not run.


### 2026-11-13 17:02 — STOP POINT: judge R on an ordinary ring contradicts the set of 2026-11-12

- **Why this was run.** The hangs of the partial-restore trials could have been the 6 / 5 ring's doing. `REDUCE_RING`
  (reduce.py) gives judge R another ring; 600,7,5,150 is an ordinary shape (two ordinary frames between rollbacks).
- **On the 7 / 5 ring, search match:**
  - full restore: PASS, 2 times of 2 (0 hash line, 0 reader value different);
  - **the set of 2026-11-12 (10,283 sites left alone): the hash is identical, 35 reader values differ, 2 times of 2**:
    EffectModule of an item (4 object-frames) and of a weapon (3), first at logic frame 1,083;
  - the removed sites that differed at a load of those two runs: 42 (the largest: 71038accac 71035fa41c, 1,888 bytes;
    7101635a50 726501e6ec, 1,740). Put back (10,241 sites left alone): PASS, 2 times of 2, 0 different;
  - that reduced set on a second match (items_cpu_four, 7 / 5): hang at the 20th load; and on the 6 / 5 ring, search
    match: hang at the 145th load. One run each; stopped there.
  - yesterday's set plus the 114 known dead sites: hang on 7 / 5 too (so not the ring's shape);
    `SSBU_RB_SKIP_GPU=1`: hang on 7 / 5 (1 run); `SSBU_RB_SKIP_GPU=2`: PASS on 7 / 5, 2 times of 2.
- **What I had not looked at.** Every judge R trial records the removed sites that differed at a load of that very
  run (`removed_that_differed`). In the seven passes of this morning it is not zero: 2 to 18 sites, 864 to 3,888
  bytes, in each. The loop of 2026-11-12 put sites back only after a failed trial, so the set was never "the sites
  that do not differ": it is "the sites that did not differ in the census's runs", and other runs make others
  differ (which sites differ changes from launch to launch and with the load points).
- **Status of the set of 2026-11-12, corrected.** It passed judge R on the 7 matches with the 6 / 5 ring this morning
  (0 different), with bytes of removed sites differing in every one of those runs. On another ring shape it gives
  reader differences in the effects' modules with an identical fight hash, and a subset of it hung twice this
  afternoon. So: a candidate that usually passes, not a proven set; "42.4 % of a save can be left alone" is not
  established. By the user's rule a unit that breaks one match comes back; doing that run after run does not
  converge by itself (87 and 22 removed sites differed in the two passing runs of the reduced set).
- **What stands from the two days**, by strength: the judge (reference against reference identical on 7 matches;
  full restore passes on both ring shapes); the tracker (`SSBU_LIVE`) and the fighters' field map with its unseen-match
  test; the recomputed fields left alone in the ring on 4 matches with their two controls; the times by ring shape.
- Stopped here: no more trial today. Nothing running. Normal build: the witness and negative control of 16:09 are
  the last (the runtime has not changed since; reduce.py only).


### 2026-11-13 17:12 — last checks: the set's sites differ under full restore too; the recomputed fields on the ordinary ring

- **Why removed sites differ: the census was incomplete, not the removal.** In the 14 judge R trials that restore
  everything (the morning's witnesses on 7 matches, the GPU-option passes, the 7 / 5 witnesses), 3 to 68 sites of the
  set of 2026-11-12 differ at a load in every one (1,216 to 13,820 bytes, the most at one load summed over sites).
  So they differ whatever is left alone; yesterday's 28 census runs did not see them. The sentence of 17:02 ("which
  sites differ changes from launch to launch and with the load points") is now measured for the first half.
- **The recomputed list is nearly stable, not an invariant yet.** The 7-match map (133 recomputed fields) against
  the 14 other matches (`live.py unseen --built _ab --tags u,c`): 127 recomputed there, **6 read first** (WorkModule
  +0x58 and +0x88, PhysicsModule ik_ready, AttackModule speed_auto, DamageModule no_reaction_no_effect, SearchModule
  invalid_attack_mask). 40 constant fields become carried there, 6 carried become recomputed. The counts 133, 133,
  135 hid that. The final map (21 matches) keeps as recomputed only what is recomputed in all of them. Of the 2,380
  dead sites of the 7-match map, 652 are seen in the other matches and 26 have a carried byte there.
- **The recomputed fields on the ordinary ring** (`REDUCE_RING=600,7,5,150 reduce.py parts ...`, normal build): search
  match with the final file PASS (4,596 hash lines, 0 different; fighters' Status, Slope, Control, Attack and Effect
  modules differ for the reader, nothing else); cpu_mac_joker with the 7-match file PASS (4,544, 0 different; the
  same kinds of modules); control, pos and status_kind alone: FAIL, 3,384 hash lines differ. One run each.
  The earlier trials of these fields were all on the 6 / 5 ring.
- Times, added: loads are occasional, a save is paid every frame (1,100 to 2,000 pages, about 2 ms, ordinary
  rings); that is where leaving memory out would act, and it is small. All times: headless, uncapped, one match.
- Docs corrected: the morning report points to the afternoon's stop point; `carried_state.json` says it is
  superseded and carries the memchr error.
- End of the day. Nothing running. Normal build: witness PASS and negative control FAIL at 16:09, runtime unchanged since.


### 2026-11-13 18:11 — a new judge: poison at every safe point, with no load (SSBU_POISON, research/tools/poison.py)

- **Why.** The day's retractions had one root: judges whose sensitivity was unknown. The ring leaves in a field that
  is not restored a slightly old value, often the right one, so a field the game does read passes; and a trial cost
  4 to 12 minutes. The claim to test is "after every safe point these bytes are written before they are read": so
  overwrite them, at every safe point of an ordinary fight, with a value that cannot be right (bytes 0xC1..0xFE: no
  valid pointer, no 0 or 1), and compare the fight's hash lines with the same fight unpoisoned. No load, no rollback;
  a trial is 25 s and tests about 2,100 boundaries. Unheld threads while the poison is written: verdicts repeated
  with two seeds. The reader is not used (a poisoned field differs for it by construction).
- **Predictions written before the runs, and results** (search match unless said):
  - all recomputed fields of the final map (4,002 bytes, 2 fighters) poisoned at every frame: expected SAME; got SAME,
    0 of 4,802 hash lines different, seeds 1 and 2;
  - pos alone: expected DIFFERENT; got 4,202 lines different from logic frame 301;
  - the 7-match map on three matches that the tracker says read some of its "recomputed" fields first: expected
    failure; got CRASH on yoshistory_wiifit_krool (frame 728; the ring had passed that file on that match),
    cpu_ice_olimar_items (367), cpu_richter_shulk (716);
  - the final map on those three: expected SAME; got SAME on yoshistory and richter_shulk, and **DIFFERENT on
    cpu_ice_olimar_items, 188 lines from logic frame 2,308, seeds 1 and 2**. The tracker's window ends at fight frame
    2,300: a field read first after it. Found by the judge; the final map is therefore wrong by at least one field
    on that match.
- **The judge's sensitivity** (16 carried fields verified by the game, poisoned one at a time): 10 detected
  (DIFFERENT: motion_kind, pos, hit_stop_real_frame, group_used_num, no_team, jostle_speed_x; CRASH: status_kind,
  status_kind_que_from_script, joint_srt_count, direct_curve), 6 SAME (prev_pos, no_reaction_forced_state,
  no_reaction_mode, active_group_num, catching, visible_all). So "read first" (the tracker's carried) is not "matters
  to the fight"; and a SAME means "nothing in the set changes this fight's hash lines", no more.
- **By module** (all the carried bytes of one module poisoned, one run each, search match): DIFFERENT: AreaModule, AttackModule, CancelModule, CaptureModule, ControlModule, DamageModule, GroundModule, ItemModule, KineticModule, ModelModule, PhysicsModule, PostureModule, SlowModule, StopModule, TeamModule.
  CRASH: ArticleModule, GrabModule, HitModule, InkPaintModule, JostleModule, LinkModule, LuaModule, MotionModule, SearchModule, SlopeModule, SoundModule, StatusModule, TurnModule. HANG: EffectModule. SAME: CameraModule, CatchModule, ColorBlendModule, ComboModule, ReflectorModule, ShadowModule, ShakeModule, ShieldModule, VisibilityModule, WorkModule.
- Strategy from here: `research/STRATEGY_2026-11-14.md` (the tracker proposes, the poison disposes, the ordinary ring
  only as a last integration check; a fixed bar for every claim; what is dropped).


### 2026-11-13 18:25 — the loop closed: the poison refutes, the tripwire names, the list is corrected and holds on 21 matches

- **Tripwire** (trace build, `SSBU_POISON` with `SSBU_LIVE`; hle_memtrace.c): a poisoned byte whose first access after
  the safe point is a read is printed with the fight frame, the fighter, the field and the reading code. On
  cpu_ice_olimar_items with the final map's recomputed fields: 16 trips, all one read: **KineticModule +0x710, 16
  bytes, fight frame 2,306, fighter 1, read by f_710047a150 < f_71003a9180 < f_71006212f0**. The normal build's hash
  diverged at logic frame 2,308. The tracker's window ended at 2,300 (now `LIVE_TO`, to the fight's end); and the
  read happens once in the fight.
- **Corrected list** (that range removed: `research/runs/live/modfields_recomputed_v2.txt`, 257 ranges, 1,985 bytes a
  fighter): cpu_ice_olimar_items SAME with seeds 1 and 2 (0 of 4,802 lines); then the 20 other matches of the map,
  seed 1, one run each: **20 SAME of 20**, 110,232 hash lines compared, 0 different.
- What this is worth, stated: the judge detects 10 of 16 carried fields poisoned alone; the observables are the
  hash's (status, motion, frame, position, damage, generator, per fighter and frame); threads are not held while
  the poison is written; one seed for 20 of the 21 matches. Weapons, items and stage objects are not in it.
- Time: from the refutation to the validated correction, under ten minutes; the 20-match validation, nine minutes
  with two games. The same question by the ring this morning: 4 to 12 minutes a trial and a wrong answer.
- Normal build with the tripwire's code: built; witness and negative control below this entry's time.
