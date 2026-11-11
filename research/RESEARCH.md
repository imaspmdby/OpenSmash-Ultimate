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

**The 1,024-entry table is the stage's presentation, not gamestate (as far as the fight hash sees).**
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
    getters (`get_down_pos`, `get_touch_flag`, `can_entry_cliff`...) read a 616,000-byte block: the stage's
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
("engine?", `code_cats.py`). The stage's collision block (616,000 bytes, site 0x7102606480) carries 2 KB of state
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
| E7 strict | site 0x7103816ef4 | strict oracle (trace 300-539, replay check at 600, 3 replays), Mario vs DK and Castle 64 | fight hash equal x3 each, **strict oracle PASS** on both |
| E8 | + site 0x71037f4e94 (~230 blocks of 131,072 bytes, 60 MB) | ring 600,6,8,150 rotate, 3 matches | **fails**: 1 crash, 2 hangs |
| E9 | + sites 0x71037df790, 0x71037de8d4 (render blocks freed during the fight) | same | stopped: holds E8's site (1 crash seen) |

E8's crash is on the runtime's own GPU thread (host pc ssbu.exe+0x7738, thread "gpu"), reading an address in those
blocks: site 0x71037f4e94 holds data the renderer reads after the load (buffers the queued commands point to). Left
out, the restored state and what the GPU thread follows no longer agree. **Being the render engine's is not enough to
be left out: what the host's GPU thread reads has to stay consistent with the restored commands.** Only the command
arenas (site 0x7103816ef4) are shown safe so far: long rollback test on 3 matches and the strict oracle on 2.

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
