# Solver and floors

## The floors

| Floor | File | Optimum (HP) | Notes |
|---|---|---|---|
| simple | `data/floors/simple.txt` | 13 | 11 × 11, the floor on which the observation was developed; test map of the published solver |
| complex | `data/floors/complex.txt` | 68 | 13 × 13, six special abilities; the published solver reports 22 |
| hand01–hand04 | `data/floors/hand/` | 14, 13, 9, 3 | hand-designed with exactly one winning set of fights each |
| gen01–gen15 | `data/floors/gen/` | 13–250 | generated and solver-verified; gen03–gen15 are the held-out floors |
| MT0–MT23w | `data/games/24/project/floors/` | – | the 24-floor tower (MT23 is split into MT23w, MT23e, MT23s) |

`manifest.json` in `hand/` and `gen/` records the exact optimum of each floor, which the scorer uses as
the reference for HP/opt.

### Single-floor file format

The format of the published solver's test maps (parsed by `mota/game/ai_floor_loader.py`), all
numbers separated by whitespace:

1. number of floors, then width and height;
2. one grid per floor of tile ids (0 floor, 1 wall, 21/22 yellow/blue key, 27/28 red/blue gem,
   31/32 red/blue potion, 81/82 yellow/blue door, 201+ monsters as defined below, …);
3. nine item values: red gem ATK, blue gem DEF, green gem MDEF, red/blue/yellow/green potion HP,
   sword ATK, shield DEF;
4. the number of monsters, then one line per monster: `id HP ATK DEF gold ability`
   (abilities: 1 first strike, 2 magic attack, 3 solid, 4/5/6 double/triple/four-strike attack,
   7 break armour, 8 counter attack, 9 purify, 10 mimic);
5. the shop: cost, increment, HP/ATK/DEF/MDEF per purchase (`999999 …` = no shop);
6. the hero: HP, ATK, DEF, MDEF, gold, yellow/blue/red keys, starting floor, position (row, column).

## The exact solver

`tools/java_bfs` is the breadth-first solver of ckcz123/magic-tower-AI with a corrected dominance test.
It turns the grid into a graph of regions and obstacles (monsters, doors, items), merges
neighbouring nodes that can be taken together without cost, and searches over sets of removed
obstacles. The published solver kept the first state it reached for each set; the corrected test keeps
a state unless another state with the same set is at least as good in every attribute. With the
correction the complex floor's optimum is 68 HP instead of 22.

```bash
python scripts/build_solver.py                                   # javac -d tools/java_bfs/out
java -cp tools/java_bfs/out Main --summary < data/floors/complex.txt
# RESULT solvable=true hp=68 atk=16 def=20 mdef=20 ... states=729953 wins=32 optimal=2 decisions=20
java -cp tools/java_bfs/out Main < data/floors/simple.txt         # published search with its route print-out
java -cp tools/java_bfs/out Main --batch --quiet < many_floors.txt  # one RESULT line per floor
```

`--summary` runs the exact search; without it, `Main` prints the graph and the route of the published
search (used by the platform's solver replay). `--nomerge` disables node merging.
`mota/solver/bfs_solver.py` is a Python port of the published search.

## Analysing and designing floors

```bash
python scripts/floor_lab.py analyse data/floors/hand/hand01.txt --decisions --rollouts 500
python scripts/floor_lab.py build              # write every design of scripts/hand_floor_designs.py
python scripts/floor_lab.py register hand05    # add to data/floors/hand/manifest.json
python analysis/tune_sweep.py hand02 50 400 25 # start HP against optimum and number of winning sets
python scripts/generate_boss_floors.py --n 5 --seed 100
```

`floor_lab.py analyse` reports the optimum, the number of winning sets, the *critical* decisions
(where a legal alternative makes the boss unwinnable), the *forced* decisions, the heuristic's result
and the win rate of random play. Hand floors are designed in ASCII in `scripts/hand_floor_designs.py`
(legend at the top of the file); the design rule of the thesis is exactly one winning set of fights.

## Other game projects

`mota.game.project.MotaProject` loads any HTML5 Magic Tower project (`data.js`, `maps.js`, `enemys.js`,
`items.js`, `floors/*.js`). Put a project under `data/games/<id>/project` or register it in
`data/projects.json`; it then appears on the Projects page and can be played with
`configure_scenario(path, project_root=...)`. Scripted events beyond plain item gifts are not
modelled; the Projects page lists them per floor.
