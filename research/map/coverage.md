# Test coverage

Made by `research/tools/coverage_table.py` from the 302 runs with verdict OK still on this PC (research/runs, git-ignored). Each cell: how many runs of that kind of test included it. A fighter is counted only when the game set it up (a name it does not know leaves Mario). Kinds of test: see the tool's header.

## Fighters (56)

| | rollback ring | strict oracle | access trace | reader | automatic check | probe | plain run |
|---|---|---|---|---|---|---|---|
| bayonetta | 9 |  |  | 11 | 8 | 1 | 1 |
| brave |  |  |  |  |  |  | 1 |
| buddy |  |  |  |  |  |  | 1 |
| cloud | 9 |  |  | 12 | 8 | 1 | 1 |
| demon | 4 |  |  | 1 |  |  |  |
| diddy |  |  |  | 12 | 7 |  |  |
| dolly |  |  |  |  |  |  | 1 |
| donkey | 50 | 14 | 37 | 64 | 22 | 5 | 9 |
| duckhunt | 4 |  |  | 1 |  |  |  |
| edge |  |  |  |  |  |  | 1 |
| falco |  |  |  |  |  |  | 1 |
| fox | 4 | 4 | 5 | 1 |  |  |  |
| gamewatch |  |  |  |  |  |  | 1 |
| ganon |  |  |  | 1 |  |  |  |
| ice_climber | 4 |  |  | 1 |  |  |  |
| ike |  |  |  |  |  |  | 1 |
| inkling | 4 |  |  | 1 |  |  |  |
| jack |  |  |  |  |  |  | 1 |
| kamui |  |  |  |  |  |  | 1 |
| kirby | 9 | 4 | 5 | 12 | 8 | 1 | 1 |
| koopajr | 4 |  |  | 1 |  |  |  |
| krool |  |  |  |  |  |  | 1 |
| link | 22 |  |  | 22 | 7 | 4 | 1 |
| littlemac |  |  |  |  |  |  | 1 |
| lucario |  |  |  | 1 | 1 |  |  |
| luigi |  |  |  | 1 |  |  |  |
| mario | 50 | 14 | 37 | 82 | 29 | 5 | 9 |
| marth |  |  |  | 1 | 1 |  | 1 |
| master |  |  |  |  |  |  | 1 |
| murabito | 4 |  |  | 1 |  |  |  |
| ness | 3 |  |  | 1 |  |  |  |
| packun |  |  |  |  |  |  | 1 |
| pacman | 4 |  |  | 1 |  |  |  |
| palutena |  |  |  |  |  |  | 1 |
| peach | 8 | 1 | 7 | 3 |  |  | 1 |
| pickel | 4 |  |  | 1 |  |  |  |
| pikachu | 4 |  |  | 1 |  |  |  |
| pikmin | 3 |  |  | 1 |  |  |  |
| pzenigame |  |  |  | 1 | 1 |  | 1 |
| reflet |  |  |  |  |  |  | 1 |
| ridley |  |  |  |  |  |  | 1 |
| rockman |  |  |  | 1 | 1 |  | 1 |
| rosetta | 4 |  |  | 1 |  |  |  |
| ryu |  |  |  | 1 |  |  |  |
| samus | 22 |  |  | 16 | 7 | 4 | 1 |
| samusd |  |  |  |  |  |  | 1 |
| shizue | 4 |  |  | 1 |  |  |  |
| shulk | 9 |  |  | 11 | 8 | 1 | 1 |
| simon |  |  |  |  |  |  | 1 |
| snake | 8 | 1 | 7 | 3 |  |  | 1 |
| sonic |  |  |  | 1 |  |  |  |
| tantan |  |  |  |  |  |  | 1 |
| trail |  |  |  |  |  |  | 1 |
| wiifit |  |  |  |  |  |  | 1 |
| yoshi |  |  |  | 1 |  |  |  |
| zelda |  |  |  | 1 |  |  |  |

## Stages (9)

| | rollback ring | strict oracle | access trace | reader | automatic check | probe | plain run |
|---|---|---|---|---|---|---|---|
| animal_village |  |  |  |  |  |  | 1 |
| battle_field | 47 | 1 | 7 | 36 | 17 | 5 | 6 |
| end | 50 | 12 | 28 | 60 | 22 | 5 | 8 |
| fox_lylatcruise |  |  |  |  |  |  | 1 |
| mario_castle64 | 20 | 2 | 9 | 28 | 7 |  | 3 |
| mario_castle64 (hazards off) |  |  |  |  |  |  | 1 |
| poke_kalos |  |  |  |  |  |  | 1 |
| poke_stadium2 |  |  |  |  |  |  | 1 |
| yoshi_story |  |  |  |  |  |  | 1 |

## Situations

| | rollback ring | strict oracle | access trace | reader | automatic check | probe | plain run |
|---|---|---|---|---|---|---|---|
| 1 players | 2 |  |  |  |  |  | 1 |
| 2 players | 106 | 11 | 39 | 112 | 38 | 9 | 19 |
| 3 players |  |  |  |  |  |  | 1 |
| 4 players | 9 | 4 | 5 | 12 | 8 | 1 | 2 |
| CPU against CPU |  |  |  | 2 | 2 |  | 11 |
| fight of 100 s or more | 2 |  |  | 2 | 2 |  |  |
| hazards on | 20 | 2 | 9 | 27 | 7 |  | 8 |
| item handed to player 1 |  |  |  | 17 | 6 |  |  |
| items falling (rule item list set) | 2 |  |  | 4 | 3 |  | 2 |
| items on (rule) | 40 | 3 | 16 | 35 | 10 |  | 8 |
| level 9 CPU | 88 | 7 | 21 | 71 | 26 | 5 | 19 |

## The longest fights

- s1_wide/cpu_marth_megaman: 184 s
- s1_wide/cpu_squirtle_lucario: 182 s
- luaall0/duo_iceclimbers_vill: 109 s
- luaall1/duo_iceclimbers_vill: 109 s
- luaall0/four_players: 73 s
- luaall1/four_players: 73 s
- luaall1/hazards_castle64: 73 s
- gcB/hazards_castle64: 73 s
- gcB/proj_link_samus: 73 s
- gcC/hazards_castle64: 73 s
