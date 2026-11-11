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
  The fight fills pools and arenas made before it: the set of blocks is fixed when the fight starts.
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
| E1 | `NONSIM=1` | replay check, Mario vs DK | 3,356 pages, 13 MB (of 536,337) | hash equal x3, **strict oracle PASS** |
| E2 | `NONSIM=2` | replay check, Mario vs DK | 1,444 pages, 5.6 MB | hash equal x3, **strict oracle PASS** |
| E3 | `NONSIM=2` | ring 600,6,8,150 rotate, 60 s, 6 matches | 1,371-2,000 pages, 5-7 MB | **all 6 crash at the first rollback** |

E3: the main thread reads address 0x7f4 (a null pointer + 0x7f4) in main+0x8dc80 <- 0x89bd0 <- 0x89940 <-
0x356dd50 (the effect emitters' tick, upstream's presentation group 64) <- the main loop: `nn::vfx`'s code. The
effects' state is not consumed by the simulation, so `=2` left it out; after a load the restored simulation and the
effects system (not restored) no longer agree (pointers, lists, recycled objects), and the effects' tick follows a
null pointer. The 60-frame replay check (E2) did not show it; the long rollback test did. **The interdependence
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
