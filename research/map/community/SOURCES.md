# Community names: sources and licences

Names of the game's state published by the Smash Ultimate modding community, imported on 2026-11-12. They are
proposals: a name enters the map only after the game confirms it (`SSBU_CONST_CHECK` in runtime/hle_state_dump.c; the confirmed ones in `confirmed.csv`, read by research/tools/community.py).
No game code, no game data: these files are the community's own tables of names and numbers.

| File | Source | Revision | Licence |
|---|---|---|---|
| `lua_const.csv` (38,774 constants: status kinds, work ids, object kinds, flags; values as u32) | https://github.com/ultimate-research/skyline-smash, `src/lua_const.rs` | commit d2ca90d9ecffdf9bf58efe6bcf4dd49f62ea1435 | MIT (`Cargo.toml`: `license = "MIT"`; authors jam1garner and contributors), `LICENSE.skyline-smash` |
| `ParamLabels.csv` (hash40 -> label) | https://github.com/ultimate-research/param-labels, `ParamLabels.csv` | commit 7642f042b192ccfa2e6f5e2f3ab1d5df4c12e038 | MIT, Smash Ultimate Research Group, `LICENSE.param-labels` |
| `research/tools/lua_bind_hash.py` (a port of the community's hash of a constant's name; not used by the game's check, which hashes with the runtime's xxh64) | port of the crate https://crates.io/crates/lua_bind_hash 1.0.1 | 1.0.1 | MIT, jam1garner |

`lua_const.csv` was extracted from `lua_const.rs` by a regular expression (name and value of each constant), nothing else.
