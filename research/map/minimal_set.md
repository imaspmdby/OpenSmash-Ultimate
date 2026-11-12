# The minimal restore set, by reduction from the full savestate

Written by `research/tools/reduce.py report` at 2026-11-12 19:50 (Paris). Journal: `research/RESEARCH.md`, entries of 2026-11-12 from "new priority: the minimal restore set" on. Every trial: `research/runs/reduce/trials.jsonl`.

## Where it stands

- A full save puts back **2168.8 MB** of guest memory. It is cut into 13161 units that cover 100.00 % of it: 12935 allocation sites (1770.85 MB), the bytes in no traced block, `others` (blocks of sites the inventory did not see), and 7 host parts.
- At a load, only a few MB of bytes differ from the saved state (5.5 MB on the search match 60 frames after the save). Over 17 witness runs and 639 loads (7 matches, replays and ring), 3003 sites differed at least once.
- **Removed: 10531 sites, 921.42 MB (42.5 % of the memory a full save puts back).** The host parts kernel, setjmp, vi, audio, net, ipc can be left alone in the replay check (judge A) but not in the ring: kept. Validation: see the table below: **not all pass**.
- Kept: 1247.40 MB (the sites that differ at some load, the bytes in no block, `others`), the fibers and the threads' host stacks. The search inside them (which of the differing sites are needed) is not done: see "To go on".
- The hang ("no frame presented") seen when units are removed is explained: the blocks allocated from `0x710373e524` (91 sites, 2.13 MB) must be put back, or the main thread spins in an NVN function of the SDK at the frame's end. They are kept (tag: glue).

## Validation of the removed set

Judge A: save at fight frame 600, 3 replays of 60 frames; B: the ring, 150 loads (5 frames back every 6); L: rollbacks that replay corrected inputs (150 ring loads + corrections), against a run with the true inputs. Each: no crash, fight hash and reader identical.

| judge | match | result | detail |
|---|---|---|---|
| A | items_cpu_samus_fox | passes | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; fighter 26400 equal / 0 different |
| A | items_cpu_four | passes | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; fighter 52800 equal / 0 different |
| A | stadium2_falco_ike | passes | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; fighter 26400 equal / 0 different |
| A | four_cpu_kalos | passes | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; fighter 52800 equal / 0 different |
| A | cpu_marth_megaman | passes | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; fighter 26400 equal / 0 different |
| A | cpu_hero_robin | passes | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; fighter 26400 equal / 0 different |
| A | lylat_sephiroth_sora | passes | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; fighter 26400 equal / 0 different |
| B | items_cpu_samus_fox | FAILS: hang after the 2nd load (no frame presented); no removed site differed: the host parts left alone | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; removed sites that differed in th |
| B | items_cpu_four | FAILS: hang after the 2nd load (no frame presented); no removed site differed: the host parts left alone | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; removed sites that differed in th |
| B | stadium2_falco_ike | FAILS: hang after the 2nd load (no frame presented); no removed site differed: the host parts left alone | earlier set (10,548 sites, of which this one is a part): 10,548 sites + 6 host parts removed; removed sites that differed in th |
| B | items_cpu_samus_fox | FAILS: hang (no frame presented) after 33 / 63 loads; removed sites differed there: candidates kept for the next run | earlier set (10,548 sites, of which this one is a part): the 10548 never-differing sites, every host part put back |
| B | items_cpu_four | passes | earlier set (10,548 sites, of which this one is a part): the 10548 never-differing sites, every host part put back; ring [150,  |
| B | items_cpu_samus_fox | FAILS: hang (no frame presented) after 33 / 63 loads; removed sites differed there: candidates kept for the next run | earlier set (10,548 sites, of which this one is a part): the sites and host setjmp, audio, net, ipc (kernel and vi put back) |
| B | items_cpu_samus_fox | passes | this set (10,531 sites), every host part put back; ring [150, 900, 149, 0], reader [1047, 5493221, 0]; removed sites that differed in the run: [18, 2848] |
| B | stadium2_falco_ike | passes | this set (10,531 sites), every host part put back; ring [150, 900, 149, 0], reader [1047, 3089697, 0]; removed sites that differed in the run: [4, 2288] |
| A | items_cpu_samus_fox | passes | this set (10,531 sites), every host part put back; replays; removed sites that differed in the run: [2, 1156] |

## Kept: what a load still puts back

Tags: **gamestate** = read by the simulation's code (the access trace's label, the pools, the stage); **glue** = needed for the fight to go on without being fight information; **unknown** = not decided.

| unit or family | units | size, MB | most bytes differing at one load | tag |
|---|---|---|---|---|
| sites: gpu | 13 | 650.44 | 5,927,451 | unknown |
| sites: main:mixed | 1043 | 97.35 | 3,913,453 | unknown |
| sites: main:other-state | 73 | 34.26 | 590,326 | unknown |
| sites: scripts | 113 | 26.49 | 22,272 | unknown |
| sites: main:unlabelled | 874 | 14.55 | 1,257,584 | unknown |
| sites: pools | 14 | 8.03 | 99,971 | gamestate |
| sites: main:sim | 83 | 6.36 | 7,214 | gamestate |
| sites: main:output | 17 | 3.55 | 426,776 | unknown |
| sites: main:scratch | 70 | 3.23 | 1,095,773 | unknown |
| sites: fibers | 4 | 2.32 | 41,018 | glue |
| sites: nvn-sync | 91 | 2.13 | 1,298,594 | glue |
| sites: stage | 1 | 0.59 | 3,102 | gamestate |
| sites: effects | 4 | 0.11 | 9,892 | unknown |
| sites: hud | 2 | 0.02 | 1,243 | unknown |
| sites: sdk | 2 | 0.02 | 3,438 | unknown |
| bytes in no traced block: alias | 124 slices | 348.84 | 2,327,146 | unknown |
| bytes in no traced block: modules | 23 slices | 40.83 | 1,557 | unknown |
| bytes in no traced block: stacks | 23 slices | 8.09 | 57,761 | glue |
| bytes in no traced block: tls | 1 slices | 0.20 | 15 | glue |
| `others`: blocks of sites the inventory did not see (680 such sites differed) | 1 | - | - | unknown |
| host: fibers (removed alone: crash) | 1 | - | - | glue |
| host: kernel, setjmp, vi, audio, net, ipc (kernel, setjmp, vi, audio, net, ipc: removed, judge A passes (6 of 6 alone, 7 matches with the sites); the long ring hangs at its 2nd load with no removed site differing: kept) | 6 | - | - | glue |
| host: the threads' stacks and registers (the load itself; not removable) | 1 | - | - | glue |

The GPU's family (sites with bytes in nvmap allocations) is kept whole: its sites that differ, removed, hung the game 4 times of 7.

## Removed: proven not needed

| family | sites | MB |
|---|---|---|
| main:mixed | 2038 | 265.82 |
| gpu | 41 | 248.93 |
| scripts | 437 | 188.17 |
| main:unlabelled | 7692 | 137.58 |
| effects | 36 | 64.05 |
| main:scratch | 52 | 14.07 |
| sdk | 10 | 2.17 |
| pools | 8 | 0.31 |
| main:other-state | 92 | 0.23 |
| main:output | 15 | 0.06 |
| main:sim | 88 | 0.01 |
| hud | 3 | 0.01 |
| fibers | 19 | 0.01 |
| **all** | **10531** | **921.42** |

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
