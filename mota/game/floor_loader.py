"""
Floor data loader — parses MOTA floor .js files into FloorData objects.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from .types import FloorData


def load_floor(floor_path: str | Path) -> FloorData:
    """Load a MOTA floor from its JS file (project/floors/MT*.js)."""
    path = Path(floor_path)
    text = path.read_text(encoding="utf-8")

    # Strip the JS assignment: main.floors.MT3= { ... }
    # Find the first '{' and take everything from there
    brace_idx = text.index("{")
    json_text = text[brace_idx:]

    # The JS object may have trailing commas — strip them for JSON
    json_text = _strip_trailing_commas(json_text)

    data = json.loads(json_text)

    # Floors without stairs (MT_1, the hidden boss floor) store "upFloor": null.
    up_pos = tuple(data.get("upFloor") or [0, 0])
    down_pos = tuple(data.get("downFloor") or [0, 0])

    return FloorData(
        floor_id=data["floorId"],
        width=data.get("width", 13),
        height=data.get("height", 13),
        map=data["map"],
        events=data.get("events", {}),
        change_floor=data.get("changeFloor", {}),
        up_floor=up_pos,
        down_floor=down_pos,
        after_battle=data.get("afterBattle") or {},
    )


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ] to make valid JSON."""
    # Remove trailing commas before closing bracket/brace
    text = re.sub(r',\s*([\]}])', r'\1', text)
    return text


def load_floors_dir(floors_dir: str | Path) -> dict[str, FloorData]:
    """Load all MT*.js floors from a directory."""
    d = Path(floors_dir)
    floors = {}
    for f in sorted(d.glob("MT*.js")):
        try:
            floor = load_floor(f)
            floors[floor.floor_id] = floor
        except Exception as e:
            print(f"Warning: could not load {f.name}: {e}")
    return floors


def load_floors_range(floors_dir: str | Path, floor_ids: list[str]) -> list[FloorData]:
    """Load a specific ordered list of floor IDs from a directory.

    Args:
        floors_dir: Directory containing MT*.js files.
        floor_ids: Ordered list of floor IDs to load (e.g. ["MT0", "MT1", "MT2"]).

    Returns:
        List of FloorData in the same order as floor_ids.

    Raises:
        FileNotFoundError: If a floor file is not found.
    """
    d = Path(floors_dir)
    result = []
    for fid in floor_ids:
        path = d / f"{fid}.js"
        if not path.exists():
            raise FileNotFoundError(f"Floor file not found: {path}")
        result.append(load_floor(path))
    return result
