# Fields read from the generated C (2026-11-12, priority 2)

Each file: what reading the code of the game's exported getters, constructors and per-frame writers establishes for one
fighter module: offsets, sizes, types, the exported getter that returns each value and how (a plain load or a formula),
and a confidence: **certain** when an exported getter returns the field by a plain load, **probable** when it rests on
writers or constructors only. Descriptions in words; no game code. Read by three agents that did not run the game;
the fields the reader uses from them are in research/map/arg_fields.json (marked "code") and pass the automatic check
(research/RESEARCH.md, 2026-11-12). Probable fields are not used by the reader until a second method backs them.
