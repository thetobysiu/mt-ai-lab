"""
BFS pathfinder — finds reachable entities from hero position.
Supports stop_at_doors mode where doors block even with keys.
"""
from __future__ import annotations
from collections import deque
from .types import Hero, Keys, DoorType
from . import data as D
from .data import GameData, DEFAULT_GAME_DATA


# Direction vectors: (dx, dy)
DIRECTIONS = [(0, -1), (0, 1), (-1, 0), (1, 0)]  # up, down, left, right


def find_reachable(
    grid: list[list[int]],
    start_x: int,
    start_y: int,
    keys: Keys,
    removed: set[tuple[int, int]] | None = None,
    stop_at_doors: bool = True,
    height: int = 13,
    width: int = 13,
    pass_through_enemies: bool = False,
    include_paths: bool = False,
    game_data: GameData | None = None,
) -> dict[tuple[int, int], dict]:
    """
    BFS from (start_x, start_y). Returns a dict of reachable entities.
    
    Each entry: (x, y) -> {
        "tile": int,
        "type": "enemy" | "item" | "door" | "stairs" | "npc" | "terrain",
        "entity_id": str,
        "dist": int,
        "accessible": bool,  (True if we can reach it to interact)
        "path": list[(x, y)] (optional shortest 4-dir path from start, excludes start)
    }
    
    Removed tiles are treated as ground (entity was already collected/killed/opened).
    """
    if removed is None:
        removed = set()
    gd = game_data or DEFAULT_GAME_DATA

    visited: set[tuple[int, int]] = set()
    result: dict[tuple[int, int], dict] = {}
    queue: deque[tuple[int, int, int]] = deque()  # (x, y, dist)
    parent: dict[tuple[int, int], tuple[int, int]] = {}

    queue.append((start_x, start_y, 0))
    visited.add((start_x, start_y))

    while queue:
        x, y, dist = queue.popleft()

        for dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy

            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            if (nx, ny) in visited:
                continue

            visited.add((nx, ny))
            parent[(nx, ny)] = (x, y)
            tile = grid[ny][nx]

            # If this entity was removed, treat as ground
            if (nx, ny) in removed:
                queue.append((nx, ny, dist + 1))
                continue

            # Classify tile
            if gd.is_wall(tile):
                # Walls block completely
                continue

            if gd.is_ground(tile) or gd.is_terrain(tile):
                # Walkable, expand
                queue.append((nx, ny, dist + 1))
                continue

            if gd.is_stairs(tile):
                stair_type = gd.get_stairs(tile)
                path = _build_path(parent, (start_x, start_y), (nx, ny)) if include_paths else None
                result[(nx, ny)] = {
                    "tile": tile, "type": "stairs",
                    "entity_id": stair_type, "dist": dist + 1,
                    "accessible": True,
                }
                if path is not None:
                    result[(nx, ny)]["path"] = path
                # Stairs are passable (hero stands on them)
                queue.append((nx, ny, dist + 1))
                continue

            if gd.is_item(tile):
                item_id = gd.get_item_id(tile)
                path = _build_path(parent, (start_x, start_y), (nx, ny)) if include_paths else None
                result[(nx, ny)] = {
                    "tile": tile, "type": "item",
                    "entity_id": item_id, "dist": dist + 1,
                    "accessible": True,
                }
                if path is not None:
                    result[(nx, ny)]["path"] = path
                # Items are picked up on step — tile becomes ground
                queue.append((nx, ny, dist + 1))
                continue

            if gd.is_door(tile):
                door_type = gd.get_door_type(tile)
                has_key = keys.has_key(door_type)
                path = _build_path(parent, (start_x, start_y), (nx, ny)) if include_paths else None
                result[(nx, ny)] = {
                    "tile": tile, "type": "door",
                    "entity_id": door_type.value, "dist": dist + 1,
                    "accessible": has_key,
                    "door_type": door_type,
                }
                if path is not None:
                    result[(nx, ny)]["path"] = path
                if has_key and not stop_at_doors:
                    # If not stopping at doors, expand through
                    queue.append((nx, ny, dist + 1))
                # If stop_at_doors=True, door blocks even with key
                continue

            if gd.is_enemy(tile):
                enemy_id = gd.get_enemy_id(tile) or f"enemy_{tile}"
                path = _build_path(parent, (start_x, start_y), (nx, ny)) if include_paths else None
                result[(nx, ny)] = {
                    "tile": tile, "type": "enemy",
                    "entity_id": enemy_id, "dist": dist + 1,
                    "accessible": True,
                }
                if path is not None:
                    result[(nx, ny)]["path"] = path
                if pass_through_enemies:
                    # Lookahead mode: treat enemies as passable to find items beyond them
                    queue.append((nx, ny, dist + 1))
                # Otherwise enemies block — can interact but can't walk through
                continue

            if gd.is_npc(tile):
                npc_id = gd.get_npc_id(tile)
                path = _build_path(parent, (start_x, start_y), (nx, ny)) if include_paths else None
                result[(nx, ny)] = {
                    "tile": tile, "type": "npc",
                    "entity_id": npc_id, "dist": dist + 1,
                    "accessible": True,
                }
                if path is not None:
                    result[(nx, ny)]["path"] = path
                # NPCs block movement
                continue

            # Unknown tile — block conservatively to avoid invalid "through-object" paths.
            continue

    return result


def _build_path(
    parent: dict[tuple[int, int], tuple[int, int]],
    start: tuple[int, int],
    target: tuple[int, int],
) -> list[tuple[int, int]]:
    """Reconstruct shortest path from start to target (excluding start)."""
    if target == start:
        return []

    path = [target]
    cur = target
    while cur != start:
        cur = parent.get(cur)
        if cur is None:
            return []
        path.append(cur)
    path.reverse()
    return path[1:]
