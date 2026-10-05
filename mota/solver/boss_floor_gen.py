"""Procedurally generated boss floors for a held-out test set (2026-09-28).

Layout: an 11x11 grid of nine 3x3 rooms separated by wall lines (x=3,7 / y=3,7). Rooms are joined
by a random spanning tree plus one or two extra links (so there are real choices); every link is
one tile in the separator — open, a yellow door, or a gate monster. The hero starts in a bottom
room, the boss sits in a top room. Rooms hold ATK/DEF gems, potions, keys and extra monsters.
Monster/item tables are those of the `simple` test floor, so the combat numbers are familiar and
only the topology is new. A floor is kept only if the Python BFS solver kills the boss.
"""
from __future__ import annotations

import random
from pathlib import Path

WALL, GROUND, YDOOR, YKEY, RGEM, BGEM, RPOT, BPOT, BOSS = 1, 0, 81, 21, 27, 28, 31, 32, 299
MONSTERS = {  # tile: (hp, atk, def, coins, effect) — the simple floor's table
    201: (50, 7, 3, 0, 0), 202: (70, 11, 1, 0, 0), 203: (45, 5, 5, 0, 2),
    204: (80, 10, 5, 0, 0), 205: (100, 17, 2, 0, 0), 299: (50, 20, 12, 0, 0),
}
BONUSES = "1 1 0 75 200 0 0 0 0"
ROOM_ORIGINS = [(cx * 4, cy * 4) for cy in range(3) for cx in range(3)]  # room index = cy*3+cx


def _neighbours(r: int) -> list[int]:
    cx, cy = r % 3, r // 3
    out = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = cx + dx, cy + dy
        if 0 <= nx < 3 and 0 <= ny < 3:
            out.append(ny * 3 + nx)
    return out


def _link_tile(a: int, b: int, rng: random.Random) -> tuple[int, int]:
    (ax, ay), (bx, by) = ROOM_ORIGINS[a], ROOM_ORIGINS[b]
    if ay == by:  # horizontal neighbours: separator column between them
        return (max(ax, bx) - 1, ay + rng.randint(0, 2))
    return (ax + rng.randint(0, 2), max(ay, by) - 1)


def generate(seed: int) -> dict:
    rng = random.Random(seed)
    grid = [[WALL] * 11 for _ in range(11)]
    for ox, oy in ROOM_ORIGINS:
        for y in range(oy, oy + 3):
            for x in range(ox, ox + 3):
                grid[y][x] = GROUND
    # spanning tree (random DFS) + extra links
    start_room = rng.choice([6, 7, 8])
    boss_room = rng.choice([r for r in (0, 1, 2) if abs(r % 3 - start_room % 3) >= 0])
    seen, stack, links = {start_room}, [start_room], []
    while stack:
        r = stack[-1]
        nxt = [n for n in _neighbours(r) if n not in seen]
        if not nxt:
            stack.pop()
            continue
        n = rng.choice(nxt)
        seen.add(n)
        links.append((r, n))
        stack.append(n)
    extra = [(a, b) for a in range(9) for b in _neighbours(a) if a < b and (a, b) not in links and (b, a) not in links]
    rng.shuffle(extra)
    links += extra[:rng.randint(1, 2)]

    free = {r: [(x, y) for y in range(ROOM_ORIGINS[r][1], ROOM_ORIGINS[r][1] + 3)
                for x in range(ROOM_ORIGINS[r][0], ROOM_ORIGINS[r][0] + 3)] for r in range(9)}
    for r in free:
        rng.shuffle(free[r])
    hx, hy = free[start_room].pop()
    bx, by = free[boss_room].pop()
    grid[by][bx] = BOSS

    n_doors = 0
    for a, b in links:
        x, y = _link_tile(a, b, rng)
        if boss_room in (a, b):
            grid[y][x] = rng.choice([204, 205])  # the boss room is always guarded
            continue
        roll = rng.random()
        if roll < 0.35:
            grid[y][x] = YDOOR
            n_doors += 1
        elif roll < 0.8:
            grid[y][x] = rng.choice([201, 202, 203, 204, 205])
        else:
            grid[y][x] = GROUND

    rooms = [r for r in range(9) if r != boss_room]
    def place(tile, count, pool=rooms):
        for _ in range(count):
            cands = [r for r in pool if free[r]]
            if not cands:
                return
            r = rng.choice(cands)
            x, y = free[r].pop()
            grid[y][x] = tile
    place(RGEM, rng.randint(5, 6), [r for r in rooms if r != start_room])
    place(BGEM, rng.randint(3, 5))
    place(RPOT, rng.randint(3, 5))
    place(BPOT, rng.randint(1, 2), [r for r in rooms if r != start_room])
    place(YKEY, max(1, n_doors - rng.randint(0, 1)))
    for _ in range(rng.randint(3, 5)):
        place(rng.choice([201, 202, 203, 204, 205]), 1, [r for r in rooms if r != start_room])
    return {"grid": grid, "hero": (hx, hy), "doors": n_doors, "links": len(links), "seed": seed}


def to_txt(g: dict, hero_hp: int = 470, hero_atk: int = 9, hero_def: int = 4) -> str:
    rows = "\n".join("\t".join(str(v) for v in row) for row in g["grid"])
    mons = "\n".join(f"{t} {' '.join(str(v) for v in s)}" for t, s in MONSTERS.items())
    hx, hy = g["hero"]
    # hero line: hp atk def mdef gold yellow blue red floor row col (row = y, col = x)
    return (f"1\n11 11\n\n{rows}\n\n\n{BONUSES}\n\n{len(MONSTERS)}\n{mons}\n\n0 0 0 0 0 0\n\n"
            f"{hero_hp} {hero_atk} {hero_def} 0 0 0 0 0 0 {hy} {hx}\n")


def solve(path: Path, max_states: int = 400_000):
    from ..game.ai_floor_loader import load_ai_floor, build_monsters_lookup, build_item_effects, build_shop_def
    from ..game.data import GameData, TILE_ENEMIES
    from .bfs_solver import BFSSolver
    sc = load_ai_floor(str(path))
    extra = {tid: m.id for tid, m in sc.monsters.items() if tid not in TILE_ENEMIES}
    gd = GameData(custom_monsters=build_monsters_lookup(sc.monsters), custom_items=build_item_effects(sc.item_bonuses),
                  custom_shops=build_shop_def(sc.shop, sc.name), extra_enemy_tiles=extra)
    solver = BFSSolver(sc.floors[0], sc.hero.copy(), game_data=gd, goal=sc.goal, max_states=max_states)
    res = solver.solve()
    if res is not None and not solver._is_goal_reached(res):
        res = None  # solve() returns the best partial state when the boss cannot be killed
    total = sum(1 for row in sc.floors[0].map for v in row if 201 <= v <= 299)
    return res, total, solver.states_explored
