"""
Synthetic map generator for Architecture C training data.

Generates random MOTA-style floor maps of varying size and difficulty.
Each map is validated by the BFS solver to ensure solvability before
being included in the training dataset.
"""
from __future__ import annotations

import logging
import random
from ..game.types import Hero, FloorData, Monster, Keys, DoorType
from ..game.data import (
    MONSTERS, TILE_ENEMIES, TILE_ITEMS, TILE_DOORS,
    TILE_GROUND, TILE_WALLS, TILE_STAIRS, GameData,
    get_item_effect,
)
from .bfs_solver import BFSSolver

log = logging.getLogger(__name__)

# Subset of monsters suitable for synthetic maps (by difficulty tier)
EASY_MONSTERS = ["greenSlime", "redSlime", "bat", "skeleton"]
MEDIUM_MONSTERS = ["blackSlime", "bigBat", "skeletonSoilder", "bluePriest"]
HARD_MONSTERS = ["zombie", "rock", "yellowGuard", "skeletonCaptain"]

# Items to place on synthetic maps
ITEM_TILES = {
    "keys": [21, 22],          # yellowKey, blueKey
    "gems": [27, 28],          # redGem (+ATK), blueGem (+DEF)
    "potions": [31, 32],       # redPotion, bluePotion
    "equipment": [35, 36],     # sword1, shield1
}

# Reverse mapping: monster_id -> tile_id
MONSTER_TO_TILE = {v: k for k, v in TILE_ENEMIES.items()}


def generate_random_floor(
    size: int = 11,
    difficulty: str = "easy",
    floor_id: str = "SYN",
    seed: int | None = None,
) -> tuple[FloorData, Hero] | None:
    """
    Generate a random solvable MOTA floor.

    Args:
        size: Map width/height (odd numbers work best for corridors: 5, 7, 9, 11)
        difficulty: "easy", "medium", or "hard"
        floor_id: ID for the generated floor
        seed: Random seed for reproducibility

    Returns:
        (FloorData, Hero) tuple or None if generation failed after retries.
    """
    if seed is not None:
        random.seed(seed)

    for attempt in range(10):
        result = _try_generate(size, difficulty, f"{floor_id}_{attempt}")
        if result is not None:
            return result

    log.warning("Failed to generate solvable floor after 10 attempts")
    return None


def _try_generate(
    size: int,
    difficulty: str,
    floor_id: str,
) -> tuple[FloorData, Hero] | None:
    """Single attempt at generating a solvable floor."""
    # Initialize empty map filled with walls
    grid: list[list[int]] = [[1] * size for _ in range(size)]

    # Carve corridors using simple random walk from center
    center = size // 2
    walkable: set[tuple[int, int]] = set()
    _carve_corridors(grid, walkable, size, center)

    if len(walkable) < 15:
        return None  # too few open tiles

    walkable_list = list(walkable)
    random.shuffle(walkable_list)

    # Place hero start (bottom-center-ish)
    hero_pos = _find_edge_pos(walkable_list, size, "bottom")
    if hero_pos is None:
        return None
    hero_x, hero_y = hero_pos
    grid[hero_y][hero_x] = TILE_GROUND  # ensure ground

    # Place stairs up (top-center-ish)
    stairs_pos = _find_edge_pos(walkable_list, size, "top")
    if stairs_pos is None or stairs_pos == hero_pos:
        return None
    grid[stairs_pos[1]][stairs_pos[0]] = 87  # upFloor

    # Remaining walkable positions (exclude hero + stairs)
    available = [p for p in walkable_list if p != hero_pos and p != stairs_pos]
    random.shuffle(available)

    # Select monster pool based on difficulty
    if difficulty == "easy":
        monster_pool = EASY_MONSTERS
        n_monsters = random.randint(2, 4)
        n_items = random.randint(2, 4)
        n_doors = random.randint(0, 1)
        hero_hp = random.randint(300, 600)
        hero_atk = random.randint(8, 15)
        hero_def = random.randint(3, 8)
    elif difficulty == "medium":
        monster_pool = MEDIUM_MONSTERS
        n_monsters = random.randint(3, 6)
        n_items = random.randint(2, 4)
        n_doors = random.randint(0, 2)
        hero_hp = random.randint(400, 800)
        hero_atk = random.randint(15, 30)
        hero_def = random.randint(10, 20)
    else:  # hard
        monster_pool = HARD_MONSTERS
        n_monsters = random.randint(4, 8)
        n_items = random.randint(3, 5)
        n_doors = random.randint(1, 2)
        hero_hp = random.randint(600, 1200)
        hero_atk = random.randint(25, 50)
        hero_def = random.randint(20, 40)

    idx = 0

    # Place monsters
    for _ in range(min(n_monsters, len(available) - idx)):
        pos = available[idx]; idx += 1
        mid = random.choice(monster_pool)
        tile_id = MONSTER_TO_TILE.get(mid)
        if tile_id:
            grid[pos[1]][pos[0]] = tile_id

    # Place items (mix of gems, potions, keys)
    item_pool = ITEM_TILES["gems"] + ITEM_TILES["potions"]
    if n_doors > 0:
        item_pool += ITEM_TILES["keys"]
    if difficulty != "easy":
        item_pool += ITEM_TILES["equipment"]

    for _ in range(min(n_items, len(available) - idx)):
        pos = available[idx]; idx += 1
        tile = random.choice(item_pool)
        grid[pos[1]][pos[0]] = tile

    # Place doors
    for _ in range(min(n_doors, len(available) - idx)):
        pos = available[idx]; idx += 1
        grid[pos[1]][pos[0]] = 81  # yellowDoor

    # Build FloorData
    floor = FloorData(
        floor_id=floor_id,
        width=size,
        height=size,
        map=grid,
        events={},
        change_floor={},
        up_floor=stairs_pos,
        down_floor=hero_pos,
    )

    hero = Hero(
        hp=hero_hp, atk=hero_atk, def_=hero_def, mdef=0,
        money=0, exp=0,
        keys=Keys(yellow=n_doors, blue=0, red=0),  # give keys for placed doors
        x=hero_x, y=hero_y,
    )

    # Validate: BFS solver must find a solution
    solver = BFSSolver(floor, hero, max_decisions=30)
    result = solver.solve()
    if result is None or result.hero.hp <= 0:
        return None

    log.debug(
        "Generated floor %s (%dx%d, %s): %d decisions, HP=%d",
        floor_id, size, size, difficulty if difficulty else "?",
        result.decisions, result.hero.hp,
    )
    return floor, hero


def _carve_corridors(
    grid: list[list[int]],
    walkable: set[tuple[int, int]],
    size: int,
    center: int,
) -> None:
    """Carve walkable paths using random walks from center + cross pattern."""
    # Start with a cross through the center
    for i in range(1, size - 1):
        grid[center][i] = TILE_GROUND
        walkable.add((i, center))
        grid[i][center] = TILE_GROUND
        walkable.add((center, i))

    # Random walks to add branches
    directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    for _ in range(3):
        cx, cy = center, center
        for _ in range(size * 2):
            dx, dy = random.choice(directions)
            nx, ny = cx + dx, cy + dy
            if 1 <= nx < size - 1 and 1 <= ny < size - 1:
                grid[ny][nx] = TILE_GROUND
                walkable.add((nx, ny))
                cx, cy = nx, ny

    # Ensure border is walls
    for i in range(size):
        grid[0][i] = 1
        grid[size-1][i] = 1
        grid[i][0] = 1
        grid[i][size-1] = 1
        walkable.discard((i, 0))
        walkable.discard((i, size-1))
        walkable.discard((0, i))
        walkable.discard((size-1, i))


def _find_edge_pos(
    walkable: list[tuple[int, int]],
    size: int,
    edge: str,
) -> tuple[int, int] | None:
    """Find a walkable position near the specified edge."""
    mid = size // 2
    if edge == "bottom":
        candidates = [(x, y) for x, y in walkable if y > mid]
    elif edge == "top":
        candidates = [(x, y) for x, y in walkable if y < mid]
    else:
        candidates = walkable

    if not candidates:
        return None

    # Prefer positions closer to the vertical center column
    candidates.sort(key=lambda p: abs(p[0] - mid))
    return candidates[0]


# ---------------------------------------------------------------------------
# Batch generation
# ---------------------------------------------------------------------------

def generate_synthetic_dataset(
    n_samples: int = 5000,
    sizes: list[int] | None = None,
    difficulties: list[str] | None = None,
    base_seed: int = 42,
) -> list[tuple[FloorData, Hero]]:
    """
    Generate a batch of random solvable floors.

    Returns list of (FloorData, Hero) pairs.
    """
    if sizes is None:
        sizes = [5, 7, 9, 11]
    if difficulties is None:
        difficulties = ["easy", "medium", "hard"]

    results = []
    attempt = 0
    while len(results) < n_samples and attempt < n_samples * 3:
        size = random.choice(sizes)
        diff = random.choice(difficulties)
        seed = base_seed + attempt
        attempt += 1

        result = generate_random_floor(
            size=size,
            difficulty=diff,
            floor_id=f"SYN{len(results):05d}",
            seed=seed,
        )
        if result is not None:
            results.append(result)

        if len(results) % 100 == 0 and len(results) > 0:
            log.info("Generated %d/%d synthetic floors", len(results), n_samples)

    log.info("Generated %d synthetic floors (from %d attempts)", len(results), attempt)
    return results
