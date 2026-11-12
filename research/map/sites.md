# Allocation sites coloured by the access trace

Made by `research/tools/sites.py` from the runs base_mario_dk, castle_haz_mario_dk, castle_nohaz_mario_dk, spawn_mario_dk. One row per (allocation site = first two return addresses of the allocation, block size). KB of the 64-byte lines touched in the trace window, by class: **sim state** (a value carried between frames, read by app / lua2cpp code), **logic state** (carried, read in the logic phase by other code), **other state** (carried, read outside the logic phase only), scratch, output, constant. A row's label is its main class, the same in every run where it appears, else "mixed". Readers and writers are guest functions (`f_<guest address>`): the last one seen per line only. A pool or arena is one row whatever its slots hold. Lines in no live block are grouped by memory area.

## Totals (KB)

| run | sim state | logic state | other state | scratch | output | constant |
|---|---|---|---|---|---|---|
| base_mario_dk | 246 | 2620 | 4984 | 4463 | 7375 | 12676 |
| castle_haz_mario_dk | 251 | 2726 | 2297 | 5049 | 6164 | 11402 |
| castle_nohaz_mario_dk | 248 | 2738 | 3118 | 4339 | 6561 | 11570 |
| spawn_mario_dk | 242 | 2748 | 3931 | 5406 | 6560 | 12466 |

## Rows with state (1786 rows; the 150 largest)

| site | size | label | runs | state KB (max) | sim state KB (max) | touched KB (max) | blocks | made | readers | writers |
|---|---|---|---|---|---|---|---|---|---|---|
| 0x7103816ef4 0x710386e6a4 | 16777216 | mixed (runs disagree: other state/scratch) | 4 | 2082.2 | 0 | 2838.8 | 2 | boot / menus 2 | f_7103813150 f_710381fa90 | f_7103815ca0 f_710381a6a0 |
| no live block: alias (game heap, GPU memory) | 0 | mixed (runs disagree: mixed/scratch) | 4 | 1289.1 | 29.8 | 5272.7 | 0 |  | f_710008e590 f_7103816730 | f_710386fba0 f_710008e590 |
| 0x710355a3b8 0x71000a41b8 | 1785680 | other state | 4 | 891.6 | 0 | 1442.9 | 1 | boot / menus 1 | f_710008e590 f_710008dc80 | f_7100087530 f_7100088660 |
| 0x7103785104 0x7103796acc | 152 | other state | 4 | 229.7 | 0.1 | 454.8 | 3657 | boot / menus 7, match load 3650 | f_710003f070 f_71000410a0 | f_71000410a0 f_7100041000 |
| 0x71037f4e94 0x71037f4c0c | 131072 | other state | 4 | 220.1 | 0 | 223.8 | 41 | boot / menus 41 | f_71094250e0 f_71094208b0 | f_71094335d0 f_71094331f0 |
| 0x710355a3b8 0x7100087b14 | 109312 | other state | 1 | 137.2 | 0 | 167.7 | 2 | fight 2 | f_7100095370 f_710008e590 | f_710008fbe0 f_710008e590 |
| 0x71037294a4 0x7103728d9c | 40 | logic state | 4 | 132.1 | 0 | 132.1 | 2114 | boot / menus 2114 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710373e524 0x710373e7d0 | 131112 | other state | 4 | 127.4 | 0.1 | 128.2 | 1 | boot / menus 1 | f_71039635c0 f_710397d630 | rt_ldst_multi f_7103960ed0 |
| 0x71037294a4 0x7103728b74 | 40 | logic state | 4 | 123.2 | 0 | 123.2 | 1972 | boot / menus 1972 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710373e524 0x7103979eb0 | 321328 | logic state | 4 | 119.8 | 0 | 120.2 | 1 | boot / menus 1 | f_7103996aa0 | f_7103996aa0 |
| 0x710373e524 0x7103979eb0 | 160496 | logic state | 4 | 100.3 | 0 | 100.5 | 1 | boot / menus 1 | f_7103996aa0 | f_7103996aa0 |
| 0x71026054bc 0x7101348b98 | 426704 | constant | 4 | 96.1 | 96.1 | 288.5 | 1 | match load 1 | f_710260e040 f_7103236a50 | f_710260e040 f_7103236a50 |
| 0x710355a3b8 0x71000a3f54 | 89632 | logic state | 4 | 87.6 | 0 | 87.6 | 1 | boot / menus 1 | f_7100088f20 f_7100088e50 | f_7100088f20 f_7100088c50 |
| 0x710355a3b8 0x710009a9f4 | 517664 | other state | 4 | 53.8 | 0 | 87.6 | 1 | match load 1 | f_710009f500 f_710009fc60 | f_71000af8c0 f_710009c610 |
| 0x71038fe0f0 0x71039210a4 | 120 | logic state | 4 | 50.2 | 0 | 99.5 | 796 | match load 796 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710360aa14 0x710360a4d4 | 48048 | logic state | 1 | 38.2 | 0 | 72.1 | 2 | match load 2 | f_710360af80 f_71035fbde0 | f_71035fbde0 f_710360b1a0 |
| 0x71037fe52c 0x7109440a44 | 100 | other state | 4 | 35.3 | 0.1 | 40.7 | 369 | boot / menus 11, fight 339, match load 19 | f_7109432860 f_710137b3f0 | f_710943ff10 |
| 0x710373e524 0x7103961dc0 | 368 | mixed | 4 | 34.5 | 0 | 81.0 | 257 | boot / menus 257 | f_710397a8a0 f_71039635c0 | f_710397a8a0 f_71039879f0 |
| 0x710360de40 0x7103600d88 | 61152 | logic state | 1 | 34.0 | 0 | 59.6 | 1 | match load 1 | f_710360af80 f_71035fbde0 | f_71035fbde0 f_710360b1a0 |
| 0x7103925bb0 0x71038f5f94 | 40 | logic state | 4 | 32.0 | 0.6 | 37.4 | 599 | match load 599 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710353cf48 0x720652de54 | 65536 | scratch | 4 | 31.3 | 7.1 | 119.2 | 8 | fight 8 | f_710951ef30 f_710353c9b0 | f_710951f440 f_7109520d08 |
| 0x710391785c 0x71038f4bd8 | 55 | logic state | 4 | 29.1 | 0 | 29.1 | 465 | boot / menus 465 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391785c 0x71038f4bd8 | 54 | logic state | 4 | 28.9 | 0 | 28.9 | 463 | boot / menus 463 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710373e524 0x7103971230 | 492 | logic state | 4 | 28.7 | 0 | 30.0 | 60 | fight 57, match load 3 | f_7103980980 f_7103984c50 | f_71039717d0 f_710396e580 |
| 0x71038ae56c 0x71038acd08 | 3880 | mixed (runs disagree: constant/other state) | 4 | 28.1 | 0 | 54.0 | 148 | match load 124, fight 24 | f_71037d1400 f_71037dbd20 | f_71037d3450 f_71037d1660 |
| 0x710391785c 0x71038f4bd8 | 49 | logic state | 4 | 27.9 | 0 | 27.9 | 447 | boot / menus 447 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710391785c 0x71038f4bd8 | 53 | logic state | 4 | 27.6 | 0 | 27.6 | 442 | boot / menus 442 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391785c 0x71038f4bd8 | 51 | logic state | 4 | 27.5 | 0 | 27.5 | 440 | boot / menus 440 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710391785c 0x71038f4bd8 | 56 | logic state | 4 | 27.1 | 0 | 27.1 | 433 | boot / menus 433 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x71035452cc 0x71093344b8 | 33453584 | constant | 4 | 26.9 | 0 | 772.0 | 1 | boot / menus 1 | f_71000324a0 f_7109432860 | f_71000382a0 f_710943ff10 |
| 0x710391540c 0x710372d15c | 216 | constant | 4 | 26.4 | 1.0 | 55.1 | 249 | boot / menus 15, match load 234 | f_71038ffa80 f_71038fe580 | f_71038ffa80 f_71038fe580 |
| 0x710391785c 0x71038f4bd8 | 50 | logic state | 4 | 26.2 | 0 | 26.2 | 420 | boot / menus 420 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710391785c 0x71038f4bd8 | 52 | logic state | 4 | 25.4 | 0 | 25.4 | 406 | boot / menus 406 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710368458c 0x7103676140 | 4656 | logic state | 4 | 24.5 | 0 | 32.0 | 7 | match load 7 | f_71036a3940 f_71036a1ce0 | f_71036a3940 |
| 0x710355a3b8 0x7100087b14 | 19968 | other state | 1 | 24.4 | 0 | 39.0 | 2 | match load 2 | f_710008e590 f_7100095370 | f_710008e590 f_710008fbe0 |
| 0x710373e524 0x710397c744 | 4208 | logic state | 4 | 24.4 | 0 | 24.8 | 6 | boot / menus 6 | f_7103987e40 f_7103996aa0 | f_7103987e40 |
| 0x71037de8d4 0x71037de350 | 524288 | other state | 1 | 24.0 | 0 | 24.0 | 2 | boot / menus 1, match load 1 | f_71037fb610 | f_71037df4b0 f_71037de610 |
| 0x710368458c 0x7103676140 | 3840 | logic state | 4 | 23.7 | 0 | 29.9 | 8 | match load 8 | f_71036a3940 f_71036a1ce0 | f_71036a3940 |
| 0x710391785c 0x71038f4bd8 | 57 | logic state | 4 | 23.7 | 0 | 23.7 | 379 | boot / menus 379 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710373e524 0x71039623a0 | 1064 | logic state | 4 | 23.0 | 1.4 | 24.1 | 23 | fight 22, match load 1 | f_7103980980 f_71039635c0 | f_7103980980 f_710386fba0 |
| 0x710355a3b8 0x7100099be4 | 258816 | other state | 4 | 22.9 | 0 | 25.8 | 1 | match load 1 | f_7109440d00 f_7109440e50 | f_7109426350 f_7109426320 |
| 0x7103734394 0x7103736388 | 56 | logic state | 4 | 21.4 | 0 | 39.1 | 626 | fight 121, match load 505 | f_7103734300 f_71003e59f0 | f_71003e59f0 f_71037348e0 |
| 0x710355a3b8 0x7100087b14 | 8704 | other state | 1 | 21.2 | 0 | 34.0 | 4 | match load 4 | f_710008e590 f_7100095370 | f_710008e590 f_710008fbe0 |
| 0x710391785c 0x71038f4bd8 | 58 | logic state | 4 | 21.1 | 0 | 21.1 | 337 | boot / menus 337 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391e080 0x710372868c | 56 | logic state | 4 | 21.1 | 0 | 21.1 | 338 | boot / menus 338 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038ffa80 |
| 0x710391785c 0x71038f4bd8 | 63 | logic state | 4 | 19.9 | 0 | 19.9 | 318 | boot / menus 318 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710363e3d4 0x710363e7b8 | 1572864 | mixed (runs disagree: other state/scratch) | 4 | 19.3 | 0 | 33.3 | 1 | boot / menus 1 | f_7109413bb0 f_71094164a0 | f_7109412cf0 f_7109433070 |
| 0x710391785c 0x71038f4bd8 | 59 | logic state | 4 | 19.3 | 0 | 19.3 | 309 | boot / menus 309 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710373e524 0x710396164c | 416 | logic state | 4 | 19.2 | 0 | 24.0 | 60 | boot / menus 60 | f_710396bd20 f_710396c8a0 | f_710396bd20 f_710396c8a0 |
| 0x710391785c 0x71038f4bd8 | 64 | logic state | 4 | 18.8 | 0 | 18.8 | 301 | boot / menus 301 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391785c 0x71038f4bd8 | 60 | logic state | 4 | 18.7 | 0 | 18.7 | 299 | boot / menus 299 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391785c 0x71038f4bd8 | 62 | logic state | 4 | 18.7 | 0 | 18.7 | 299 | boot / menus 299 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x71037d17f0 0x71038ae640 | 536 | mixed (runs disagree: constant/mixed) | 4 | 18.0 | 0 | 85.2 | 346 | match load 250, fight 96 | f_71037ddc40 f_71037d1400 | f_71037df560 |
| 0x71036a3364 0x7103684628 | 12416 | logic state | 4 | 18.0 | 0 | 24.0 | 2 | match load 2 | f_71036a1ce0 f_71038e7e70 | f_71038e34a0 f_71038e26f0 |
| 0x710391785c 0x71038f4bd8 | 61 | logic state | 4 | 17.4 | 0 | 17.4 | 278 | boot / menus 278 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391778c 0x71038f4bd8 | 67 | logic state | 4 | 17.2 | 0 | 20.6 | 259 | boot / menus 259 | f_71038fe580 | f_71038fe580 |
| 0x710391785c 0x71038f4bd8 | 65 | logic state | 4 | 17.1 | 0 | 17.1 | 202 | boot / menus 202 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x71014f48c0 0x710135df60 | 1531408 | mixed | 4 | 16.9 | 16.9 | 37.3 | 1 | match load 1 | f_7100468220 f_71003ce8e0 | f_7100468220 f_71004e4620 |
| 0x710355a3b8 0x710009b000 | 8960 | constant | 4 | 16.7 | 0 | 47.7 | 7 | match load 7 | f_710008dc80 f_710009fd90 | f_710008b350 f_7100039a90 |
| 0x710355a3b8 0x710009a9f4 | 57248 | other state | 4 | 16.6 | 0 | 25.1 | 1 | match load 1 | f_7100088850 f_710009fc60 | f_71000af8c0 f_710009c610 |
| 0x710391778c 0x71038f4bd8 | 69 | logic state | 4 | 16.6 | 0 | 20.7 | 264 | boot / menus 264 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391778c 0x71038f4bd8 | 66 | logic state | 4 | 16.2 | 0 | 20.5 | 263 | boot / menus 263 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710373e524 0x710373f338 | 98304 | other state | 4 | 16.0 | 0 | 16.0 | 1 | boot / menus 1 | f_7103995790 f_7103987e40 | f_7103995790 f_7103996aa0 |
| 0x71036a3364 0x7103684628 | 10240 | logic state | 4 | 15.9 | 0 | 21.8 | 3 | match load 3 | f_71036a1ce0 f_71038e7e70 | f_71038e34a0 f_71038e26f0 |
| 0x710391e080 0x710372d180 | 56 | logic state | 4 | 15.6 | 0 | 15.6 | 249 | match load 234, boot / menus 15 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038ffa80 |
| 0x710391e080 0x710372d1b8 | 56 | logic state | 4 | 15.6 | 0 | 15.6 | 249 | match load 234, boot / menus 15 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038ffa80 |
| 0x710391778c 0x71038f4bd8 | 68 | logic state | 4 | 14.8 | 0 | 18.6 | 236 | boot / menus 236 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x71038d8e00 0x7103689d84 | 11232 | mixed (runs disagree: logic state/mixed) | 4 | 14.7 | 0.1 | 19.2 | 2 | match load 2 | f_71036d6110 f_7103690c60 | f_7103690c60 |
| 0x710391778c 0x71038f4bd8 | 71 | logic state | 4 | 13.5 | 0 | 16.6 | 209 | boot / menus 209 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710355a3b8 0x710009b000 | 5984 | constant | 4 | 13.1 | 0 | 44.1 | 10 | match load 10 | f_710008dc80 f_710009fd90 | f_710008b350 f_7100039a90 |
| 0x710391778c 0x71038f4bd8 | 70 | logic state | 4 | 12.7 | 0 | 15.8 | 204 | boot / menus 204 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710363f304 0x71005600f0 | 1216 | other state | 4 | 12.4 | 0 | 18.4 | 28 | boot / menus 28 | f_7109412920 f_710363fa50 | f_710363fa50 f_7100031d70 |
| 0x710363f304 0x710055ff90 | 1216 | other state | 4 | 12.4 | 0 | 18.4 | 28 | boot / menus 28 | f_7109412920 f_710363fa50 | f_710363fa50 f_7100031d70 |
| 0x710363f304 0x7100560040 | 1216 | other state | 4 | 12.4 | 0 | 18.4 | 28 | boot / menus 28 | f_7109412920 f_710363fa50 | f_710363fa50 f_7100031d70 |
| 0x71037fe52c 0x710941e688 | 100 | mixed (runs disagree: mixed/output) | 4 | 12.3 | 0.1 | 29.2 | 265 | fight 249, boot / menus 8, match load 8 | f_7109432860 f_7101f443d0 | f_710943ff10 |
| 0x710055d1ac 0x71022bb504 | 104592 | mixed (runs disagree: constant/mixed) | 4 | 12.3 | 5.4 | 24.7 | 1 | boot / menus 1 | f_710356dd50 f_7100561b60 | f_7103570a10 f_710374db00 |
| 0x71038d8e00 0x7103689d84 | 9408 | logic state | 4 | 12.3 | 0.1 | 14.2 | 2 | match load 2 | f_71036d6110 f_7103690c60 | f_7103690c60 f_71036d6110 |
| 0x710355a3b8 0x710009b000 | 15904 | constant | 4 | 12.0 | 0 | 36.2 | 3 | match load 3 | f_710008dc80 f_710009fd90 | f_710008b350 f_7100039a90 |
| 0x7103557260 0x7103611240 | 184 | other state | 4 | 11.8 | 0 | 20.0 | 233 | boot / menus 233 | f_7103747820 | f_71035ac600 f_7103747820 |
| 0x710355a3b8 0x7100087b14 | 4608 | other state | 1 | 11.2 | 0 | 18.0 | 4 | match load 4 | f_710008e590 f_7100095370 | f_710008e590 f_710008fbe0 |
| 0x710355a3b8 0x7100087b14 | 17920 | other state | 1 | 10.9 | 0 | 17.5 | 1 | match load 1 | f_710008e590 f_7100095370 | f_710008e590 f_710008fbe0 |
| no live block: guest stacks | 0 | scratch | 4 | 10.8 | 0.1 | 42.5 | 0 |  | f_710395b610 f_7103987e40 | f_7103987e40 f_710397e8c0 |
| 0x7103851b2c 0x710384fdc0 | 168 | mixed (runs disagree: constant/logic state/mixed) | 4 | 10.2 | 0 | 19.2 | 195 | boot / menus 195 | f_71037f0b40 f_71037f4bb0 | f_71037f5710 f_71037f0b40 |
| 0x7103785104 0x71037952fc | 240 | constant | 4 | 9.8 | 0 | 54.4 | 426 | match load 426 | f_7100058700 f_710003f250 | f_7100058700 f_710003f250 |
| 0x710355a3b8 0x710009b000 | 4000 | constant | 4 | 9.7 | 0 | 32.4 | 11 | match load 11 | f_710008dc80 f_710009fd90 | f_710008b350 f_7100039a90 |
| 0x710391778c 0x71038f4bd8 | 72 | logic state | 4 | 9.7 | 0 | 12.6 | 164 | boot / menus 164 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x7103785104 0x7103795444 | 576 | mixed | 4 | 9.4 | 0.2 | 52.2 | 260 | match load 260 | f_7100058700 f_710003f250 | f_7100058700 f_7100058380 |
| 0x71038accac 0x7103605998 | 944 | mixed (runs disagree: constant/logic state) | 4 | 9.4 | 0 | 15.9 | 24 | match load 12, fight 12 | f_7103818540 f_71038af4f0 | f_71038b0a00 f_71038af680 |
| 0x7103613d78 0x71035a496c | 40368 | constant | 4 | 9.2 | 0 | 36.7 | 1 | boot / menus 1 | f_7103572d80 | f_7103572d80 f_7103572d30 |
| 0x710391778c 0x71038f4bd8 | 73 | logic state | 4 | 9.1 | 0 | 11.4 | 144 | boot / menus 144 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| no live block: main's data / bss | 0 | constant | 4 | 9.0 | 2.3 | 278.1 | 0 |  | f_7109330a90 f_7103747820 | f_710933a020 f_7109330b20 |
| 0x710391785c 0x71038f4bd8 | 44 | logic state | 4 | 8.9 | 0 | 8.9 | 143 | boot / menus 143 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710355a3b8 0x710009b000 | 4992 | constant | 4 | 8.8 | 0 | 26.8 | 7 | match load 7 | f_710008dc80 f_710009fd90 | f_710008b350 f_7100039a90 |
| 0x710391778c 0x71038f4bd8 | 74 | logic state | 4 | 8.7 | 0 | 11.3 | 144 | boot / menus 144 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x71037f4c44 0x7103851c34 | 160 | logic state | 4 | 8.6 | 0 | 8.6 | 61 | boot / menus 61 | f_7109412cf0 f_7109412920 | f_7109412cf0 f_7109441770 |
| 0x71038fb578 0x71039001f4 | 544 | output | 4 | 8.4 | 0 | 75.4 | 134 | boot / menus 16, match load 118 | f_71038ffa80 | f_71038ffa80 |
| 0x710391778c 0x71038f4bd8 | 75 | logic state | 4 | 8.3 | 0 | 10.5 | 139 | boot / menus 139 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x7103604f7c 0x71036359e0 | 560 | other state | 4 | 8.3 | 0 | 10.3 | 140 | match load 35, boot / menus 105 | f_7103638ad0 | f_7103638ad0 |
| 0x71035452cc 0x71093344b8 | 11944448 | constant | 4 | 8.2 | 0 | 246.7 | 1 | match load 1 | f_71000324a0 f_7109432860 | f_71000382a0 f_710943ff10 |
| 0x7103785104 0x71037952cc | 224 | mixed | 4 | 8.2 | 0.1 | 42.3 | 321 | boot / menus 1, match load 320 | f_7100058700 f_710003f250 | f_7100058700 f_710003f250 |
| 0x710373e524 0x7103971230 | 484 | logic state | 4 | 8.1 | 0 | 9.8 | 20 | fight 18, match load 2 | f_7103980980 f_710396d260 | f_71039717d0 f_7103980210 |
| 0x71036358b8 0x71035fb190 | 208 | constant | 4 | 8.0 | 0 | 19.6 | 120 | boot / menus 105, match load 15 | f_7103638ad0 f_71035fab50 | f_7103638ad0 f_71035d6c10 |
| 0x710373e524 0x710373eebc | 32808 | mixed (runs disagree: other state/scratch) | 4 | 8.0 | 0 | 14.0 | 1 | boot / menus 1 | f_7103987e40 | f_71039727a0 f_7103987e40 |
| 0x71038d8e00 0x7103685590 | 11232 | other state | 4 | 7.8 | 1.0 | 8.6 | 2 | match load 2 | f_71036a0b00 f_7103698e00 | f_71036a0b00 f_71036c8cc0 |
| 0x71036a3364 0x71036aa314 | 5632 | other state | 4 | 7.7 | 0 | 15.2 | 3 | match load 3 | f_71036a9e50 f_71038e7e70 | f_71038e34a0 f_71038e49c0 |
| 0x710391785c 0x71038f4bd8 | 45 | logic state | 4 | 7.7 | 0 | 7.7 | 123 | boot / menus 123 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391785c 0x71038f4bd8 | 43 | logic state | 4 | 7.6 | 0 | 7.6 | 122 | boot / menus 122 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x71038210c0 0x71038260c4 | 248 | mixed | 4 | 7.5 | 0 | 15.4 | 123 | boot / menus 123 | f_7103864cb0 f_7103856050 | f_7103856fa0 f_7103864cb0 |
| 0x710391785c 0x71038f4bd8 | 46 | logic state | 4 | 7.5 | 0 | 7.5 | 120 | boot / menus 120 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x71038215a8 0x7103826604 | 600 | mixed | 4 | 7.4 | 0 | 14.9 | 140 | boot / menus 140 | f_7103864cb0 f_7103856050 | f_7103864cb0 f_7103856fa0 |
| 0x710355a3b8 0x7100099be4 | 28608 | other state | 4 | 7.4 | 0 | 7.5 | 1 | match load 1 | f_7109440d00 f_7109440e50 | f_7109426350 f_7109426320 |
| 0x710391785c 0x71038f4bd8 | 47 | logic state | 4 | 7.3 | 0 | 7.3 | 117 | boot / menus 117 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710389803c 0x71038964bc | 7488 | other state | 4 | 7.3 | 0 | 7.3 | 1 | match load 1 | f_7103818ed0 f_71035d3f00 | f_71036a0b00 |
| 0x71038fb578 0x71039001f4 | 1264 | output | 4 | 7.2 | 0 | 145.0 | 116 | match load 116 | f_71038ffa80 f_710372e9d0 | f_71038ffa80 f_710372e8d0 |
| 0x710360de40 0x7103600d88 | 8512 | mixed | 4 | 7.1 | 0 | 14.4 | 3 | match load 3 | f_71035fbde0 f_710360af80 | f_71035fbde0 |
| 0x710355a3b8 0x7100087b14 | 11520 | other state | 2 | 7.1 | 0 | 11.3 | 1 | match load 1 | f_710008e590 f_7100095370 | f_710008e590 f_710008fbe0 |
| 0x710391778c 0x71038f4bd8 | 76 | logic state | 4 | 7.0 | 0 | 9.2 | 124 | boot / menus 124 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391785c 0x71038f4bd8 | 40 | logic state | 4 | 7.0 | 0 | 7.0 | 112 | boot / menus 112 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x7103785104 0x7103794e6c | 656 | mixed | 4 | 6.9 | 0 | 32.5 | 103 | match load 103 | f_71037a17f0 f_7100062ff0 | f_71037a17f0 f_7100058700 |
| 0x71036a3364 0x71036aa314 | 4864 | other state | 4 | 6.9 | 0 | 13.8 | 3 | match load 3 | f_71036a9e50 f_71038e7e70 | f_71038e34a0 f_71038e49c0 |
| 0x710391785c 0x71038f4bd8 | 41 | logic state | 4 | 6.9 | 0 | 6.9 | 110 | boot / menus 110 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710391778c 0x71038f4bd8 | 77 | logic state | 4 | 6.8 | 0 | 8.6 | 115 | boot / menus 115 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710391785c 0x71038f4bd8 | 48 | logic state | 4 | 6.8 | 0 | 6.8 | 108 | boot / menus 108 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710355a3b8 0x710009b000 | 6976 | constant | 4 | 6.7 | 0 | 26.6 | 5 | match load 5 | f_710008dc80 f_710009fd90 | f_710008b350 f_7100039a90 |
| 0x71038d8e00 0x7103685590 | 4268 | mixed (runs disagree: mixed/scratch) | 4 | 6.7 | 0.1 | 16.8 | 4 | match load 4 | f_710369f6d0 f_7103690c60 | f_710369f6d0 f_71036a1ce0 |
| no live block: other modules' data | 0 | constant | 4 | 6.6 | 0 | 86.7 | 0 |  | f_710902d9f0 f_7109330c40 | f_710902d900 f_710933a020 |
| 0x71038d8e00 0x7103685590 | 9408 | other state | 4 | 6.6 | 0.8 | 7.2 | 2 | match load 2 | f_71036a0b00 f_710368d6e0 | f_71036a0b00 f_71036c8cc0 |
| 0x710391785c 0x71038f4bd8 | 42 | logic state | 4 | 6.6 | 0 | 6.6 | 105 | boot / menus 105 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710391785c 0x71038f4bd8 | 39 | logic state | 4 | 6.2 | 0 | 6.2 | 99 | boot / menus 99 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x71038a9b44 0x71038b194c | 320 | constant | 4 | 6.1 | 0 | 30.2 | 127 | boot / menus 19, match load 108 | f_71038ac560 f_71038ad1f0 | f_71038ac560 f_71038ad1f0 |
| 0x71038ae650 0x71038acd08 | 112 | other state | 4 | 6.1 | 0.1 | 9.2 | 94 | match load 70, fight 24 | f_71038b0440 f_71038adfe0 | f_71038ac560 f_71038b0440 |
| 0x710391785c 0x71038f4bd8 | 38 | logic state | 4 | 6.1 | 0 | 6.1 | 97 | boot / menus 97 | f_71038ffa80 f_71038fe580 | f_71038fe340 f_71038fe580 |
| 0x710389803c 0x71038964bc | 6272 | other state | 4 | 6.1 | 0 | 6.1 | 1 | match load 1 | f_7103818ed0 f_71036014e0 | f_71036a0b00 |
| 0x71038ab9d4 0x71038a9f00 | 104 | constant | 4 | 5.9 | 0 | 95.9 | 1022 | boot / menus 86, match load 936 | f_7109432860 f_71038ab050 | f_71038aa3a0 f_710943ff10 |
| 0x71036a4d04 0x71036801f8 | 5088 | output | 4 | 5.9 | 0 | 20.0 | 4 | match load 4 | f_71036a4a60 | f_71036a5250 |
| 0x710391778c 0x71038f4bd8 | 78 | logic state | 4 | 5.9 | 0 | 7.1 | 88 | boot / menus 88 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x710355a3b8 0x710009b000 | 10944 | constant | 4 | 5.8 | 0 | 16.5 | 2 | match load 2 | f_710008dc80 f_710009fd90 | f_710008b350 f_7100039a90 |
| 0x710391778c 0x71038f4bd8 | 79 | logic state | 4 | 5.8 | 0 | 7.0 | 89 | boot / menus 89 | f_71038fe580 f_71038ffa80 | f_71038fe580 f_71038fe340 |
| 0x7103785104 0x710003e45c | 48 | mixed (runs disagree: constant/logic state) | 4 | 5.4 | 0 | 7.3 | 117 | match load 117 | f_71038fe580 f_710003f070 | f_71038fe580 |
| 0x710355a3b8 0x710009a9f4 | 31904 | other state | 4 | 5.2 | 0 | 7.8 | 1 | match load 1 | f_710009fc60 f_710009f500 | f_71000af8c0 f_710009c610 |
| 0x71014f4694 0x710135df60 | 288 | sim state | 4 | 4.9 | 4.9 | 9.1 | 29 | match load 29 | f_710034b310 f_7100469cb0 | f_7100468220 f_71003e87a0 |
| 0x71036aa114 0x71036818b0 | 2464 | other state | 4 | 4.8 | 0 | 7.3 | 3 | match load 3 | f_71036a9e50 | f_71036aa440 |
| 0x710355a3b8 0x7100087b14 | 1536 | other state | 4 | 4.6 | 0 | 7.4 | 5 | fight 1, match load 4 | f_710008e590 f_7100095370 | f_710008e590 f_710008fbe0 |
| 0x710355a3b8 0x710009b000 | 2016 | constant | 4 | 4.5 | 0 | 13.6 | 9 | match load 9 | f_710008dc80 f_710009fd90 | f_710008b350 f_7100039a90 |
| 0x7100524308 0x7102629cb0 | 288 | mixed (runs disagree: constant/sim state) | 4 | 4.5 | 4.5 | 7.8 | 25 | match load 25 | f_7100533020 f_71005324f0 | f_7100533020 f_71005324f0 |
| 0x71036a3364 0x71036a511c | 35328 | other state | 4 | 4.5 | 0 | 6.0 | 4 | match load 4 | f_71036a4a60 f_71038e7e70 | f_71038e34a0 f_71038e7190 |
| 0x71035c2b14 0x7102601fbc | 2080 | mixed (runs disagree: constant/mixed) | 4 | 4.4 | 0 | 16.7 | 14 | match load 14 | f_71035d5d50 f_71035d5d80 | f_71035d5d50 f_71035d5d80 |
| 0x710355a3b8 0x710009a9f4 | 46880 | other state | 4 | 4.4 | 0 | 7.5 | 1 | match load 1 | f_7100088850 f_710009fc60 | f_71000af8c0 f_710009c610 |
| 0x7103601104 0x71036002c0 | 14384 | constant | 4 | 4.3 | 0 | 21.7 | 2 | match load 2 | f_71035fbde0 f_710381a6a0 | f_71035fbde0 |
| 0x7103785104 0x710005e228 | 80 | mixed | 4 | 4.3 | 0 | 20.9 | 275 | boot / menus 6, match load 269 | f_7100056550 f_710003fc60 | f_7100053dc0 f_7100056550 |

## The largest rows without state (40)

| site | size | label | runs | touched KB (max) |
|---|---|---|---|---|
| 0x71037fe52c 0x71094538c0 | 2101255 | output | 4 | 1935.3 |
| 0x710363ea28 0x710363eee0 | 18874368 | output | 4 | 1414.6 |
| 0x71037f5214 0x71037f4c30 | 32768 | output | 4 | 1216.9 |
| 0x71035452cc 0x71093344b8 | 2793792 | constant | 1 | 1053.6 |
| 0x71035452cc 0x71093344b8 | 19651696 | constant | 4 | 838.7 |
| 0x71035452cc 0x71093344b8 | 779776 | constant | 1 | 615.2 |
| 0x710355a3b8 0x710009a9f4 | 614400 | output | 4 | 450.0 |
| 0x71035452cc 0x71093344b8 | 453056 | constant | 2 | 442.0 |
| 0x71037d17f0 0x7103597704 | 536 | constant | 4 | 375.0 |
| 0x71037f5214 0x71037f5674 | 65536 | output | 4 | 365.1 |
| 0x71035452cc 0x71093344b8 | 914736 | constant | 4 | 338.6 |
| 0x71035fe534 0x71036029cc | 1104 | constant | 4 | 303.3 |
| 0x710363ea28 0x710363eee0 | 150994944 | output | 4 | 281.0 |
| 0x71035452cc 0x71093344b8 | 423208 | constant | 1 | 272.3 |
| 0x710391d68c 0x710391dd78 | 262144 | constant | 4 | 256.0 |
| 0x71035452cc 0x71093344b8 | 228376 | constant | 1 | 213.9 |
| 0x710388ad68 0x71038892b0 | 448 | constant | 4 | 161.3 |
| 0x71037df790 0x71037d8924 | 962560 | output | 4 | 145.6 |
| 0x71035452cc 0x71093344b8 | 145704 | constant | 1 | 135.0 |
| 0x710391d68c 0x710391dd78 | 131072 | constant | 4 | 128.0 |
| 0x71035452cc 0x71093344b8 | 198512 | constant | 1 | 123.4 |
| 0x71035452cc 0x71093344b8 | 264720 | constant | 1 | 109.1 |
| 0x71035452cc 0x71093344b8 | 799760 | constant | 4 | 95.7 |
| 0x71037f5214 0x71037f4c30 | 57344 | output | 3 | 92.1 |
| 0x7103601104 0x71036002c0 | 94888 | constant | 1 | 91.9 |
| 0x71035452cc 0x71093344b8 | 381376 | constant | 4 | 79.8 |
| 0x710391d68c 0x710391dd78 | 16384 | constant | 4 | 64.0 |
| 0x710391d68c 0x710391dd78 | 65536 | constant | 4 | 64.0 |
| 0x71035452cc 0x71093344b8 | 69592 | constant | 4 | 61.4 |
| 0x71035452cc 0x71093344b8 | 39323 | constant | 4 | 61.4 |
| 0x71035b7d98 0x710364a9d8 | 163840 | scratch | 4 | 61.2 |
| 0x71035452cc 0x71093344b8 | 68888 | constant | 2 | 60.4 |
| 0x71037e9548 0x71037e7c78 | 88 | constant | 4 | 57.7 |
| 0x710391d68c 0x710391dd78 | 1024 | constant | 4 | 55.0 |
| 0x7103785104 0x7103796120 | 184 | constant | 4 | 53.6 |
| 0x71035452cc 0x71093344b8 | 642048 | constant | 4 | 53.5 |
| 0x710355a3b8 0x71000a3fd8 | 8388608 | output | 4 | 53.2 |
| 0x710391d68c 0x710391dd78 | 2048 | constant | 4 | 52.0 |
| 0x71035452cc 0x71093344b8 | 59043 | constant | 2 | 51.4 |
| 0x71035452cc 0x71093344b8 | 59560 | constant | 2 | 51.1 |
