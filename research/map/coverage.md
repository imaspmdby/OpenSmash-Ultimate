# Test coverage

Made by `research/tools/coverage_table.py` from the 320 runs with verdict OK still on this PC (research/runs, git-ignored). Each cell: how many runs of that kind of test included it. A fighter is counted only when the game set it up (a name it does not know leaves Mario). Kinds of test: see the tool's header.

## Fighters (56)

| | rollback ring | strict oracle | access trace | reader | automatic check | probe | automatic check FAILED | plain run |
|---|---|---|---|---|---|---|---|---|
| bayonetta | 9 |  |  | 11 | 8 | 1 |  | 1 |
| brave |  |  |  | 1 |  |  | 1 | 1 |
| buddy |  |  |  |  |  |  |  | 1 |
| cloud | 9 |  |  | 12 | 8 | 1 |  | 1 |
| demon | 4 |  |  | 1 |  |  |  |  |
| diddy |  |  |  | 12 | 7 |  |  |  |
| dolly |  |  |  |  |  |  |  | 1 |
| donkey | 50 | 14 | 42 | 75 | 23 | 5 |  | 9 |
| duckhunt | 4 |  |  | 1 |  |  |  |  |
| edge |  |  |  | 1 | 1 |  |  | 1 |
| falco |  |  |  | 1 |  |  | 1 | 1 |
| fox | 4 | 4 | 5 | 1 |  |  |  |  |
| gamewatch |  |  |  | 1 |  |  | 1 | 1 |
| ganon |  |  |  | 1 |  |  |  |  |
| ice_climber | 4 |  |  | 1 |  |  |  |  |
| ike |  |  |  | 1 |  |  | 1 | 1 |
| inkling | 4 |  |  | 1 |  |  |  |  |
| jack |  |  |  | 1 | 1 |  |  | 1 |
| kamui |  |  |  | 1 | 1 |  |  | 1 |
| kirby | 9 | 4 | 5 | 12 | 8 | 1 |  | 1 |
| koopajr | 4 |  |  | 1 |  |  |  |  |
| krool |  |  |  | 1 | 1 |  |  | 1 |
| link | 22 |  |  | 22 | 7 | 4 |  | 1 |
| littlemac |  |  |  | 1 | 1 |  |  | 1 |
| lucario |  |  |  | 1 | 1 |  |  |  |
| luigi |  |  |  | 1 |  |  |  |  |
| mario | 50 | 14 | 42 | 93 | 30 | 5 |  | 9 |
| marth |  |  |  | 1 | 1 |  |  | 1 |
| master |  |  |  |  |  |  |  | 1 |
| murabito | 4 |  |  | 1 |  |  |  |  |
| ness | 3 |  |  | 1 |  |  |  |  |
| packun |  |  |  |  |  |  |  | 1 |
| pacman | 4 |  |  | 1 |  |  |  |  |
| palutena |  |  |  | 1 |  |  | 1 | 1 |
| peach | 8 | 1 | 7 | 3 |  |  |  | 1 |
| pickel | 4 |  |  | 1 |  |  |  |  |
| pikachu | 4 |  |  | 1 |  |  |  |  |
| pikmin | 3 |  |  | 1 |  |  |  |  |
| pzenigame |  |  |  | 1 | 1 |  |  | 1 |
| reflet |  |  |  | 1 |  |  | 1 | 1 |
| ridley |  |  |  |  |  |  |  | 1 |
| rockman |  |  |  | 1 | 1 |  |  | 1 |
| rosetta | 4 |  |  | 1 |  |  |  |  |
| ryu |  |  |  | 1 |  |  |  |  |
| samus | 22 |  |  | 16 | 7 | 4 |  | 1 |
| samusd |  |  |  |  |  |  |  | 1 |
| shizue | 4 |  |  | 1 |  |  |  |  |
| shulk | 9 |  |  | 11 | 8 | 1 |  | 1 |
| simon |  |  |  |  |  |  |  | 1 |
| snake | 8 | 1 | 7 | 3 |  |  |  | 1 |
| sonic |  |  |  | 1 |  |  |  |  |
| tantan |  |  |  | 1 | 1 |  |  | 1 |
| trail |  |  |  | 1 | 1 |  |  | 1 |
| wiifit |  |  |  | 1 | 1 |  |  | 1 |
| yoshi |  |  |  | 1 |  |  |  |  |
| zelda |  |  |  | 1 |  |  |  |  |

## Stages (9)

| | rollback ring | strict oracle | access trace | reader | automatic check | probe | automatic check FAILED | plain run |
|---|---|---|---|---|---|---|---|---|
| animal_village |  |  |  | 1 | 1 |  |  | 1 |
| battle_field | 47 | 1 | 8 | 38 | 17 | 5 | 1 | 6 |
| end | 50 | 12 | 30 | 64 | 23 | 5 | 1 | 8 |
| fox_lylatcruise |  |  |  | 1 | 1 |  |  | 1 |
| mario_castle64 | 20 | 2 | 10 | 34 | 7 |  |  | 3 |
| mario_castle64 (hazards off) |  |  | 1 | 2 | 1 |  |  | 1 |
| poke_kalos |  |  |  |  |  |  |  | 1 |
| poke_stadium2 |  |  |  | 1 |  |  | 1 | 1 |
| yoshi_story |  |  |  | 1 | 1 |  |  | 1 |

## Situations

| | rollback ring | strict oracle | access trace | reader | automatic check | probe | automatic check FAILED | plain run |
|---|---|---|---|---|---|---|---|---|
| 1 players | 2 |  |  |  |  |  |  | 1 |
| 2 players | 106 | 11 | 44 | 130 | 43 | 9 | 3 | 19 |
| 3 players |  |  |  |  |  |  |  | 1 |
| 4 players | 9 | 4 | 5 | 12 | 8 | 1 |  | 2 |
| CPU against CPU |  |  |  | 11 | 6 |  | 3 | 11 |
| fight of 100 s or more | 2 |  |  | 10 | 7 |  | 3 |  |
| hazards on | 20 | 2 | 10 | 37 | 10 |  | 1 | 8 |
| item handed to player 1 |  |  |  | 17 | 6 |  |  |  |
| items falling (rule item list set) | 2 |  | 1 | 5 | 3 |  |  | 2 |
| items on (rule) | 40 | 3 | 19 | 42 | 11 |  |  | 8 |
| level 9 CPU | 88 | 7 | 24 | 87 | 31 | 5 | 3 | 19 |

## The longest fights

- s1_wide/lylat_sephiroth_sora: 184 s
- s1_wide/cpu_gw_palutena: 184 s
- s1_wide/cpu_marth_megaman: 184 s
- s1_wide/smashville_corrin_mm: 184 s
- s1_wide/yoshistory_wiifit_krool: 184 s
- s1_wide/stadium2_falco_ike: 184 s
- s1_wide/castle_nohaz_mario_dk: 183 s
- s1_wide/cpu_mac_joker: 183 s
- s1_wide/cpu_hero_robin: 183 s
- s1_wide/cpu_squirtle_lucario: 182 s
