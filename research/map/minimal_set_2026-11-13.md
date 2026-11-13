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

### RETRACTED (2026-11-13 afternoon): the morning's table "the fighters' modules by first access"

The table that stood here (1,124 fields read first, 44 written first every time) was wrong twice: the objects it
measured were not the fighters' modules (the state dump's registrations at those frames are four other objects),
and the native memchr reported its length argument as read, which marked far more bytes "read first" than the game
reads (4.74 % of the morning's read-first bytes are not live in a whole-fight run). See the afternoon's section.
