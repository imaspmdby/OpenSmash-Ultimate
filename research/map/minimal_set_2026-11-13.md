## STATUS, 2026-11-13 17:05: the removed set below is a candidate, not a proven set

Judge R with an ordinary ring (600,7,5,150, `REDUCE_RING`): full restore passes (2 of 2); **the set of 10,283 sites
gives an identical fight hash and 35 different reader values (2 of 2)**, in the EffectModule of an item and a weapon.
With the 42 removed sites that differed at a load of those runs put back, it passes (2 of 2); that reduced set then
hung once on another match and once on the 6 / 5 ring. And in every judge R trial, the seven passes of the morning
included, some removed sites differ at a load (2 to 18 sites, 0.9 to 3.9 KB): the set is "the sites that did not
differ in the census's runs", not "the sites that do not differ". "42.4 % of a save can be left alone" is not
established. Everything below this section about the set is to be read with that.

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

## 2026-11-13 afternoon: first access after every safe point of whole fights (`SSBU_LIVE`, `research/tools/live.py`)

The right question needs no load: after each rollback safe point of an ordinary fight, is a byte's next access a
read (it carries state across that boundary) or a write (dead there)? One fight of 2,000 frames is 2,000 load
points. Classes: carried (read first after some safe point, and written in the fight), recomputed (written first
after every safe point), constant (read, never written), handed over (written by one thread, read by another
before the next safe point; kept). Acceptance: the bytes two load recordings see read first (508,547) are live in
the whole-fight run but 21. 28 runs: 21 matches, 7 of them twice. `research/map/live_state.json`,
`research/map/gamestate_fields.md`.

| what | result |
|---|---|
| fighters' fields (code reading's 1,168) | 428 carried (276 verified by the game), 135 recomputed (97), 439 constant, 166 not touched |
| recomputed fields as matches are added | 133 (7 matches), 133 (10), 135 (21) |
| map of 7 matches against 3 unseen matches, no load | of 133 recomputed: 129 recomputed, 3 not touched, 1 read first |
| ring, 150 loads, recomputed fields of named modules left alone (8,476 to 12,062 bytes a load) | 4 matches of 4: 0 hash line different; only fighters' Status, Control and Attack modules differ for the reader |
| the same on the ordinary ring 7 / 5 (one run each) | search match and cpu_mac_joker: 0 hash line different, only fighters' modules differ; control: 3,384 hash lines differ |
| the 7-match map's 133 recomputed fields in 14 other matches | 127 recomputed, 6 read first |
| control: pos and status_kind alone left alone (168 bytes) | 3,417 hash lines differ |
| control: the carried fields left alone | crash |
| pages the game's code writes in a fight, not the GPU's | 5,400 to 11,100; 64 to 80 % hold a carried byte |
| pages the game's code writes in a fight, the GPU's | 2,100 to 4,300; dead for the game's code (95 to 99.5 %), but 1,400 of 3,200 hold commands the GPU thread reads after a later safe point |
| whole sites dead and not in the set of 2026-11-12 | 5 GPU sites (35 MB), 110 known sites (2.6 MB), 3,525 short-lived sites |

The set of 2026-11-12 plus the dead sites hangs the game: 2 times of 2 with all of them, 2 times of 2 with the 114
known sites that are not the GPU's alone (the map of 7 matches). "Never read first by the game's code" is not enough to
leave a whole site alone; the cause was not read.

What this says about the minimal set:
- at the grain of allocation sites, nothing was added to the set of 2026-11-12: the sites the tracker calls dead
  (under 3 MB outside the GPU's memory) hang the game when left alone;
- below that grain the removable part is fields of known objects (a few KB per fighter: it checks the map, it does
  not lighten a load); cutting blocks by offset tears values (a crash at the 27th load);
- the GPU's memory is the only large part left, and its command memory is state across a safe point (the hang read
  from the dumps: a semaphore one release short); the runtime's `SSBU_RB_SKIP_GPU=1` hangs (0 of 3), `=2` passes 2 of 3;
- times, one game alone: a load costs 1.2 to 1.7 ms for 5 frames back (rings 7/5, 8/5, 10/5, 12/5, 30/5), 0.8 ms for
  2; a whole rollback of 5 frames 13 to 19 ms, most of it the frames run again. Only the rings whose depth is the
  interval less one (6/5, the judges'; 10/9) are heavy (74 and 138 ms a load): there the game gives back and takes
  again 20 to 60 MB of memory at every frame, which every save copies whole. So the memory a load puts back is not
  where a rollback's time is: leaving memory out can gain a millisecond or two at most. The game's code writes
  about 12,200 distinct pages in a whole fight, 8,600 with a carried byte; an ordinary save copies 1,100 to 2,000.
