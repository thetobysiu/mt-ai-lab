"""Hand-designed boss floors (built by scripts/floor_lab.py build -> data/floors/hand/<name>.txt).

Legend: # wall  . floor  @ hero  B boss  y/b yellow/blue door  k/K yellow/blue key
        a red gem (+ATK)  d blue gem (+DEF)  p red potion  P blue potion  digits = monsters (per design).
Monster entries: char -> (tile, hp, atk, def, effect); effect 1 first strike, 2 magic, 4 double, 5 triple, 7 break armor.
"""

SIMPLE_TABLE = {  # the simple floor's monsters
    "1": (201, 50, 7, 3, 0),   # Green Slime
    "2": (202, 70, 11, 1, 0),  # Red Slime
    "3": (203, 45, 5, 5, 2),   # Black Slime, magic attack
    "4": (204, 80, 10, 5, 0),  # Slime Lord
    "5": (205, 100, 17, 2, 0),  # Bat
}

DESIGNS = [
    {
        "name": "hand01",
        "idea": "key ledger: more doors than keys; wing rooms reachable by a door (key) or a gate monster (HP)",
        "rows": [
            "a.4#.B.#4.d",
            ".a.#.6.#.p.",
            "#y###b###y#",
            ".1.#...#.2.",
            "k.d#.3.#a.k",
            "#2##...##1#",
            "a2..#.#..1.",
            ".a#.#.#.#d.",
            "..5.y.y.3..",
            "##..#.#..##",
            "p.k.#@#.K.p",
        ],
        "monsters": {**SIMPLE_TABLE, "6": (206, 120, 20, 4, 1)},
        "boss": (50, 20, 12, 0),
        "hero": (400, 9, 4, 0, 1, 0, 0),
    },
    {
        "name": "hand02",
        "idea": "DEF thresholds: guards turn free at high DEF, skeletons need ATK; 2 yellow keys for 4 doors",
        "rows": [
            "...#a.d#d.d",
            ".B.7.P.y.a.",
            "...#...#...",
            "#5###b###8#",
            "a.p#.K.#d.p",
            ".1.y.3.7.7.",
            "...#...#...",
            "#7###3###y#",
            "k..#a..#d.k",
            ".@.y.3.1.1.",
            "p..#...#...",
        ],
        "monsters": {
            "1": (201, 50, 7, 3, 0), "3": (203, 45, 5, 5, 2), "5": (205, 100, 17, 2, 0),
            "7": (221, 60, 14, 6, 0),   # guard: free once DEF >= 14
            "8": (209, 40, 12, 8, 1),   # skeleton, first strike: needs ATK
        },
        "boss": (100, 18, 10, 0),
        "hero": (62, 9, 4, 0, 0, 0, 0),
    },
    {
        "name": "hand03",
        "idea": "complex-floor monster table (combos, magic, break armor, first strike) on a new 13x13 layout; green gems = MDEF",
        "rows": [
            "B6..#a.d#.g.P",
            "..7...1.b.#..",
            "####y###.##2#",
            "d.3...#.4.#.a",
            ".#.#.#k#.#.#.",
            "a#g#.2...y..d",
            ".#.#y#.#.###5",
            "5.1.#.@.#p.1.",
            "#y###...###y#",
            ".d.#4.K.4#.a.",
            ".p.#.....#.g.",
            "a.k#.y#y.#k.d",
            "..3..p#p..7..",
        ],
        "monsters": {
            "1": (201, 42, 20, 0, 5), "2": (202, 50, 20, 7, 0), "3": (203, 32, 49, 4, 7),
            "4": (204, 90, 30, 0, 2), "5": (205, 63, 34, 1, 4), "6": (206, 120, 33, 2, 0),
            "7": (207, 54, 56, 3, 1),
        },
        "boss": (178, 26, 0, 6),
        "bonuses": "1 1 5 75 200 0 0 0 0",
        "hero": (649, 10, 10, 0, 0, 0, 0),
    },
    {
        "name": "hand04",
        "idea": "simple x complex: 6 yellow doors for 2 keys, every room reachable by a door or a gate monster; a bat shortcut; boss behind the one blue door",
        "rows": [
            "a.6.#B#.3.d",
            "#y#.#b#.#y#",
            "k.2...y...p",
            "###4###1###",
            "d.p..#..a.k",
            "#3####y##2#",
            "..a.p.....4",
            "#y###5###y#",
            "p..2.@.1..d",
            "#.#######.#",
            "K.4.a.d.3.P",
        ],
        "monsters": {**SIMPLE_TABLE, "6": (209, 60, 15, 7, 0)},
        "boss": (60, 22, 10, 0),
        "hero": (94, 9, 4, 0, 0, 0, 0),
    },
]
