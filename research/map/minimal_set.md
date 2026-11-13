# The minimal restore set, by reduction from the full savestate

Written by `research/tools/reduce.py report` at 2026-11-13 11:58 (Paris). Journal: `research/RESEARCH.md`, entries of 2026-11-12 from "new priority: the minimal restore set" on. Every trial: `research/runs/reduce/trials.jsonl`.

## Where it stands

- A full save puts back **2168.8 MB** of guest memory. It is cut into 13161 units that cover 100.00 % of it: 12935 allocation sites (1770.85 MB), the bytes in no traced block, `others` (blocks of sites the inventory did not see), and 7 host parts.
- At a load, only a few MB of bytes differ from the saved state (5.5 MB on the search match 60 frames after the save). Over 28 witness runs and 1260 loads (7 matches, replays and ring), 3197 sites differed at least once.
- **Removed: 10283 sites, 920.29 MB (42.4 % of the memory a full save puts back).** The host parts kernel, setjmp, vi, audio, net, ipc can be left alone in the replay check (judge A) but not in the ring: kept. Validation: **every trial passes**.
- Kept: 1248.52 MB (the sites that differ at some load, the bytes in no block, `others`), the fibers and the threads' host stacks. The search inside them (which of the differing sites are needed) is not done: see "To go on".
- The hang ("no frame presented") seen when units are removed is explained: the blocks allocated from `0x710373e524` (91 sites, 2.13 MB) must be put back, or the main thread spins in an NVN function of the SDK at the frame's end. They are kept (tag: glue).

## 2026-11-13: the repaired judge, and what a load must put back measured by first access

### The judge against a launch with no rollback (judge R)

Yesterday's ring judge compared a frame run again with its first pass in the same launch. Judge R
(`research/tools/refjudge.py`, `reduce.py refs` / `judge`) compares the run with loads against another launch that
never loaded anything, logic frame by logic frame, to the fight's 40th second (about 800 frames after the last of
the 150 loads): the fight hash's lines at every frame, the reader's values every third frame.

| check | result |
|---|---|
| reference against a second launch of itself, 7 matches | identical (search match: 4,912 hash lines, 8,141,044 values, 0 different) |
| full restore, 150 ring loads, 7 matches | PASS on the 7 |
| negative control: the fighters' pool left alone | FAIL (3,382 hash lines differ, first at logic frame 602) |
| negative control: empty list | FAIL (crash) |
| **the set of 2026-11-12 (10,283 sites, 920.3 MB left alone), 7 matches** | **PASS on the 7** (search match: 4,602 hash lines, 2,712,238 values, 0 different) |

So the set of 10,283 sites holds on a judge that is not self-referential. Second method: at a load of the trace
build, no byte of those sites differs from the saved state (0 read first, 0 written first, 0 untouched).

### Read before written (`SSBU_RF`, trace build; `research/tools/readfirst.py`, `carried.py`)

After a load, each byte keeps its first access by the game's code (the native libc, the pad state and the kernel's,
IPC's and graphics driver's own guest words are reported too). At the next load, the bytes that differ from the
saved state are sorted.

- 21 recordings (7 matches; 6, 10, 20, 60 and 120 frames after the save), then 66 more on the search match at as
  many different save frames (6 frames after each): **the bytes read before written are 241,000 to 331,000 at the
  21 loads** (232,000 to 509,000 over the 66 save frames), whatever the match and the distance, of 0.6 to 4.0 MB
  that differ. About 226,000 of them are the blocks of allocator
  `0x710373e524` (tag: glue), read by one function, `f_7103996aa0`.
- Search match, 60 frames (3,112,237 bytes differ): read first 270,321 (8.7 %); written first 2,057,896 (66.1 %), of
  which the GPU's memory 1,722,891; written by one thread then read by another 761,091 (24.5 %); not touched 22,929.
- Of the fight's own families, read first at that load: pools 613 bytes, main:sim 436, stage 161, effects 194,
  scripts 109. Reading code in the game's own classes: 484 bytes; in the scripts: 190.

### What is NOT established: leaving the written-first bytes alone

- In the run that measured them (same save, second load), leaving the written-first bytes alone gives a fight
  identical to its end when the game does not hang; each family alone passes (3 or 4 times of 3 or 4); their union
  hangs (6 passes of 15; 5 of 6 once bytes handed over between threads are kept); the GPU's family fails 6 times
  of 7; the fibers fail. The negative controls fail as they must (the read-first bytes left alone: crash; those of
  the pools, main:sim and the stage alone, 1,205 bytes: the hash differs).
- As fields (allocation site, block size, offset) "written first in every recording", left alone at the 150 loads of
  the ring: **fails**. All families: hang at the 3rd load; main:mixed: hang; scratch / other-state / output: hang; the
  fight's families (2,267 bytes of places): crash at the 4th load; only the allocator-0x710373e524 blocks' 20,700
  bytes of places pass (one run, 75,494 bytes left alone at a load).
- Why (supported, not proven): the recordings of a match all load the same instant. With 56 save frames instead of one, the
  places "written first every time" fall from 80,175 to 14,269 (fight's families: 2,267 to 692), and those still
  crash the ring, whose load points are others again; with the ring's first ten load points recorded too, the ring
  goes to its 27th load before the crash instead of its 4th. At the recorded load point itself the fight's hash is
  identical on 3 replays of 60 frames. **"Written first" is a fact about a load point, not yet about the code.**
  A field is recomputed only if it is written before read from every frame; sampled load points do not show that.
- So nothing is added to the removed set today. `research/map/carried_state.json` is a measurement: "carried" places
  are those the game's code read before writing at least once (an observation: constants only read are in it, the
  GPU's and the fibers' readers are not traced); "recomputed" there are candidates, known insufficient. Not tested:
  whether the key (site, block size, offset) puts different kinds of objects together.

### What this changes for the minimal set

- Upper bound unchanged: 10,283 sites, 920.3 MB left alone, now on judge R.
- What the game's code reads first is small and now measured: about a quarter of a MB per load, nine tenths of it glue of
  one allocator. Between the two: 1 to 4 MB per load that the game overwrites before reading *at that load point*
  (the GPU's memory first), which no method here can yet leave alone safely.
- No speed claim: not measured (plan, step 6 not reached).

### The fighters' modules by first access (first table, one load point)

`readfirst.py --modules` (7 matches, save at fight frame 600, 60 frames): every byte of the battle objects' module
objects the game touched, differing or not. Fighters: 11,535 bytes read first, 15,427 written first (candidates),
74 handed over. Of the code reading's fields of the fighter's modules: 38 read first (34 of them verified by the game
yesterday), 29 written first, 3 handed over, 34 not touched in the window. Examples read first: PostureModule pos,
prev_pos, lr, scale; StatusModule status_kind, situation_kind; MotionModule motion_kind, frame, rate; DamageModule
damage_log. Written first here: StatusModule status_kind_next, is_changing, prev_situation_kind; MotionModule
prev_frame_2nd. In `research/map/carried_state.json`, "modules". One load point per match: "read first" stands (and
includes pointers and constants that are only read); "written first" is a candidate, as above.

## Validation of the removed set

Judge A: save at fight frame 600, 3 replays of 60 frames; B: the ring, 150 loads (5 frames back every 6); L: rollbacks that replay corrected inputs (150 ring loads + corrections), against a run with the true inputs. Each: no crash, fight hash and reader identical.

| judge | match | result | detail |
|---|---|---|---|
| B | items_cpu_samus_fox | passes | [150, 900, 149, 0] |
| A | items_cpu_samus_fox | passes | ['fighter 26400 equal / 0 different, item 9120 equal / 0 different, weapon 269280 equal / 0 different', 'fighter 26400 equal / 0 different, item 9120 equal / 0 different, weapon 269280 equal / 0 diffe |
| A | items_cpu_four | passes | ['fighter 52800 equal / 0 different, weapon 369840 equal / 0 different', 'fighter 52800 equal / 0 different, weapon 369840 equal / 0 different', 'fighter 52800 equal / 0 different, weapon 369840 equal |
| A | stadium2_falco_ike | passes | ['fighter 26400 equal / 0 different, weapon 148020 equal / 0 different', 'fighter 26400 equal / 0 different, weapon 148020 equal / 0 different', 'fighter 26400 equal / 0 different, weapon 148020 equal |
| A | four_cpu_kalos | passes | ['fighter 52800 equal / 0 different, gimmick 15540 equal / 0 different, weapon 272760 equal / 0 different', 'fighter 52800 equal / 0 different, gimmick 15540 equal / 0 different, weapon 272760 equal / |
| A | cpu_marth_megaman | passes | ['fighter 26400 equal / 0 different, item 152 equal / 0 different, weapon 113100 equal / 0 different', 'fighter 26400 equal / 0 different, item 152 equal / 0 different, weapon 113100 equal / 0 differe |
| A | lylat_sephiroth_sora | passes | ['fighter 26400 equal / 0 different, gimmick 660 equal / 0 different, weapon 381240 equal / 0 different', 'fighter 26400 equal / 0 different, gimmick 660 equal / 0 different, weapon 381240 equal / 0 d |
| A | cpu_hero_robin | passes | ['fighter 26400 equal / 0 different, weapon 224280 equal / 0 different', 'fighter 26400 equal / 0 different, weapon 224280 equal / 0 different', 'fighter 26400 equal / 0 different, weapon 224280 equal |
| B | items_cpu_four | passes | ring [150, 900, 149, 0], reader [1047, 7508207, 0] (second run: in the first the ring was 0 different too but its dump could not be read, a tool fault) |
| B | stadium2_falco_ike | passes | ring [150, 900, 149, 0], reader [1047, 3089697, 0] (second run: in the first the ring was 0 different too but its dump could not be read, a tool fault) |
| B | four_cpu_kalos | passes | [150, 900, 149, 0] |
| B | cpu_marth_megaman | passes | [150, 900, 149, 0] |
| B | lylat_sephiroth_sora | passes | [150, 900, 149, 0] |
| B | cpu_hero_robin | passes | [150, 900, 149, 0] |
| L | lf_link_samus | passes | logic frames 0-1420 compared (2840 fighter-frames); frames run again in the test: 821 (from 600 to 1420); different: 0 |
| A | items_cpu_samus_fox | passes | ['fighter 26400 equal / 0 different, gimmick 2580 equal / 0 different, item 9120 equal / 0 different, weapon 269280 equal / 0 different', 'fighter 26400 equal / 0 different, gimmick 2580 equal / 0 dif |
| A | items_cpu_samus_fox | passes | ['fighter 26400 equal / 0 different, item 9120 equal / 0 different, weapon 269280 equal / 0 different', 'fighter 26400 equal / 0 different, item 9120 equal / 0 different, weapon 269280 equal / 0 diffe |

## Kept: what a load still puts back

Tags: **gamestate** = read by the simulation's code (the access trace's label, the pools, the stage); **glue** = needed for the fight to go on without being fight information; **unknown** = not decided.

| unit or family | units | size, MB | most bytes differing at one load | tag |
|---|---|---|---|---|
| sites: gpu | 13 | 650.44 | 6,591,597 | unknown |
| sites: main:mixed | 1107 | 98.19 | 5,770,075 | unknown |
| sites: main:other-state | 73 | 34.26 | 722,429 | unknown |
| sites: scripts | 122 | 26.49 | 23,180 | unknown |
| sites: main:unlabelled | 1020 | 14.79 | 1,289,814 | unknown |
| sites: pools | 16 | 8.05 | 104,733 | gamestate |
| sites: main:sim | 92 | 6.36 | 10,293 | gamestate |
| sites: main:output | 18 | 3.56 | 473,744 | unknown |
| sites: main:scratch | 86 | 3.24 | 1,160,489 | unknown |
| sites: fibers | 4 | 2.32 | 43,448 | glue |
| sites: nvn-sync | 91 | 2.13 | 1,882,733 | glue |
| sites: stage | 1 | 0.59 | 5,187 | gamestate |
| sites: effects | 4 | 0.11 | 10,002 | unknown |
| sites: hud | 3 | 0.02 | 1,243 | unknown |
| sites: sdk | 2 | 0.02 | 3,438 | unknown |
| bytes in no traced block: alias | 124 slices | 348.84 | 2,327,146 | unknown |
| bytes in no traced block: modules | 23 slices | 40.83 | 2,203 | unknown |
| bytes in no traced block: stacks | 23 slices | 8.09 | 57,761 | glue |
| bytes in no traced block: tls | 1 slices | 0.20 | 23 | glue |
| `others`: blocks of sites the inventory did not see (794 such sites differed) | 1 | - | - | unknown |
| host: fibers (removed alone: crash) | 1 | - | - | glue |
| host: kernel, setjmp, vi, audio, net, ipc (kernel, setjmp, vi, audio, net, ipc: removed, judge A passes (6 of 6 alone, 7 matches with the sites); the long ring hangs at its 2nd load with no removed site differing: kept) | 6 | - | - | glue |
| host: the threads' stacks and registers (the load itself; not removable) | 1 | - | - | glue |

The GPU's family (sites with bytes in nvmap allocations) is kept whole: its sites that differ, removed, hung the game 4 times of 7.

## Removed: proven not needed

| family | sites | MB |
|---|---|---|
| main:mixed | 1974 | 264.98 |
| gpu | 41 | 248.93 |
| scripts | 428 | 188.17 |
| main:unlabelled | 7546 | 137.34 |
| effects | 36 | 64.05 |
| main:scratch | 36 | 14.06 |
| sdk | 10 | 2.17 |
| pools | 6 | 0.28 |
| main:other-state | 92 | 0.23 |
| main:output | 14 | 0.06 |
| main:sim | 79 | 0.01 |
| hud | 2 | 0.01 |
| fibers | 19 | 0.01 |
| **all** | **10283** | **920.29** |

Read "proven" as: an upper bound that the replays confirm on 7 matches and the ring on one of two so far. In each trial 2 to 37 of the removed sites still differed in the trial's own run (the census has not converged), and the long ring is not passed on every match: until it is, this is a candidate set.

The list of the sites: `research/map/minimal_set_state.json` (`removed`).
What "proven" means here: no byte of these sites differed at any of the census's loads, so leaving them alone changes nothing there; and the validation above ran the fights with them left alone. A site that differs in a situation none of these runs met (another fighter, another stage) would have to come back: the census is to be widened with every new match.

## To go on (everything restarts where it was)

```
deps/python/python.exe research/tools/reduce.py controls --jobs 3    # (after any change of the runtime or the judge: bump GEN in reduce.py first)
# widen the census: add matches to VALIDATE in reduce.py (the lfi.txt matches of judge L are not in it yet), then
# (runs whose census_*.txt exists are not made again: delete research/runs/reduce/census_*.txt to make them anew)
deps/python/python.exe research/tools/reduce_census.py --runs 6 --matches --ring
deps/python/python.exe research/tools/reduce.py set                  # the candidate set from the census (+ ever_differ_extra.json)
deps/python/python.exe research/tools/reduce.py validate --jobs 3    # a trial that hangs lists the removed sites that differed: add them to ever_differ_extra.json, set, validate again
# the search inside the sites that differ (bisection weighted by differing bytes; a hang is run again). Not run yet in this form: untested
deps/python/python.exe research/tools/reduce.py search --jobs 3 --minutes 480
deps/python/python.exe research/tools/reduce.py report
```
