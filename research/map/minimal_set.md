# The minimal restore set, by reduction from the full savestate

Written by `research/tools/reduce.py report` at 2026-11-12 21:28 (Paris). Journal: `research/RESEARCH.md`, entries of 2026-11-12 from "new priority: the minimal restore set" on. Every trial: `research/runs/reduce/trials.jsonl`.

## Where it stands

- A full save puts back **2168.8 MB** of guest memory. It is cut into 13161 units that cover 100.00 % of it: 12935 allocation sites (1770.85 MB), the bytes in no traced block, `others` (blocks of sites the inventory did not see), and 7 host parts.
- At a load, only a few MB of bytes differ from the saved state (5.5 MB on the search match 60 frames after the save). Over 28 witness runs and 1260 loads (7 matches, replays and ring), 3197 sites differed at least once.
- **Removed: 10317 sites, 920.31 MB (42.4 % of the memory a full save puts back).** The host parts kernel, setjmp, vi, audio, net, ipc can be left alone in the replay check (judge A) but not in the ring: kept. Validation: see the table below: **not all pass**.
- Kept: 1248.50 MB (the sites that differ at some load, the bytes in no block, `others`), the fibers and the threads' host stacks. The search inside them (which of the differing sites are needed) is not done: see "To go on".
- The hang ("no frame presented") seen when units are removed is explained: the blocks allocated from `0x710373e524` (91 sites, 2.13 MB) must be put back, or the main thread spins in an NVN function of the SDK at the frame's end. They are kept (tag: glue).

## Validation of the removed set

Judge A: save at fight frame 600, 3 replays of 60 frames; B: the ring, 150 loads (5 frames back every 6); L: rollbacks that replay corrected inputs (150 ring loads + corrections), against a run with the true inputs. Each: no crash, fight hash and reader identical.

| judge | match | result | detail |
|---|---|---|---|
| A | items_cpu_samus_fox | passes | set of 10,341 sites; fighter 26400 equal / 0 different, item 9120 equal / 0 different, weap |
| A | items_cpu_four | passes | set of 10,341 sites; fighter 52800 equal / 0 different, weapon 369840 equal / 0 different |
| A | stadium2_falco_ike | passes | set of 10,341 sites; fighter 26400 equal / 0 different, gimmick 2640 equal / 0 different, w |
| A | four_cpu_kalos | passes | set of 10,341 sites; fighter 52800 equal / 0 different, gimmick 15540 equal / 0 different,  |
| A | cpu_marth_megaman | passes | set of 10,341 sites; fighter 26400 equal / 0 different, item 152 equal / 0 different, weapo |
| A | lylat_sephiroth_sora | passes | set of 10,341 sites; fighter 26400 equal / 0 different, weapon 381240 equal / 0 different |
| A | cpu_hero_robin | passes | set of 10,341 sites; fighter 26400 equal / 0 different, weapon 224280 equal / 0 different |
| B | items_cpu_samus_fox | FAILS: crash or timeout | set of 10,341 sites;  |
| B | four_cpu_kalos | FAILS: crash or timeout | set of 10,341 sites;  |
| B | stadium2_falco_ike | passes | set of 10,341 sites; [150, 900, 149, 0] |
| B | items_cpu_four | passes | set of 10,341 sites; [150, 900, 149, 0] |
| B | lylat_sephiroth_sora | passes | set of 10,341 sites; [150, 900, 149, 0] |
| B | cpu_hero_robin | passes | set of 10,341 sites; [150, 900, 149, 0] |
| L | lf_link_samus | FAILS: crash or timeout | set of 10,341 sites; logic frames 0-1282 compared (2564 fighter-frames); frames run again in the test |
| A | items_cpu_samus_fox | passes | set of 10,341 sites; fighter 26400 equal / 0 different, item 9120 equal / 0 different, weap |
| A | items_cpu_samus_fox | passes | set of 10,341 sites; fighter 26400 equal / 0 different, gimmick 2580 equal / 0 different, i |
| B | cpu_marth_megaman | passes | set of 10,341 sites; [150, 900, 149, 0] |
| A | items_cpu_samus_fox | passes | set of 10,317 sites; fighter 26400 equal / 0 different, gimmick 2580 equal / 0 different, i |
| A | items_cpu_four | passes | set of 10,317 sites; fighter 52800 equal / 0 different, weapon 369840 equal / 0 different |
| A | stadium2_falco_ike | passes | set of 10,317 sites; fighter 26400 equal / 0 different, gimmick 2640 equal / 0 different, w |
| A | four_cpu_kalos | passes | set of 10,317 sites; fighter 52800 equal / 0 different, gimmick 4800 equal / 0 different, w |
| A | cpu_marth_megaman | passes | set of 10,317 sites; fighter 26400 equal / 0 different, item 152 equal / 0 different, weapo |
| A | lylat_sephiroth_sora | passes | set of 10,317 sites; fighter 26400 equal / 0 different, weapon 381240 equal / 0 different |
| A | cpu_hero_robin | passes | set of 10,317 sites; fighter 26400 equal / 0 different, weapon 224280 equal / 0 different |
| B | items_cpu_samus_fox | passes | set of 10,317 sites; [150, 900, 149, 0] |
| B | stadium2_falco_ike | passes | set of 10,317 sites; [150, 900, 149, 0] |

## Kept: what a load still puts back

Tags: **gamestate** = read by the simulation's code (the access trace's label, the pools, the stage); **glue** = needed for the fight to go on without being fight information; **unknown** = not decided.

| unit or family | units | size, MB | most bytes differing at one load | tag |
|---|---|---|---|---|
| sites: gpu | 13 | 650.44 | 6,591,597 | unknown |
| sites: main:mixed | 1105 | 98.18 | 5,770,075 | unknown |
| sites: main:other-state | 73 | 34.26 | 722,429 | unknown |
| sites: scripts | 122 | 26.49 | 23,180 | unknown |
| sites: main:unlabelled | 1009 | 14.78 | 1,289,814 | unknown |
| sites: pools | 15 | 8.05 | 104,733 | gamestate |
| sites: main:sim | 88 | 6.36 | 10,293 | gamestate |
| sites: main:output | 18 | 3.56 | 473,744 | unknown |
| sites: main:scratch | 70 | 3.23 | 1,160,489 | unknown |
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
| main:mixed | 1976 | 264.99 |
| gpu | 41 | 248.93 |
| scripts | 428 | 188.17 |
| main:unlabelled | 7557 | 137.35 |
| effects | 36 | 64.05 |
| main:scratch | 52 | 14.07 |
| sdk | 10 | 2.17 |
| pools | 7 | 0.28 |
| main:other-state | 92 | 0.23 |
| main:output | 14 | 0.06 |
| main:sim | 83 | 0.01 |
| hud | 2 | 0.01 |
| fibers | 19 | 0.01 |
| **all** | **10317** | **920.31** |

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
