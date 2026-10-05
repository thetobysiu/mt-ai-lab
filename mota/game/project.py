"""
MotaProject — load any HTML5-mota project (data.js / enemys.js / items.js / maps.js / floors/*.js)
into a GameData the engine can play with.

The built-in 24-layer tables in data.py stay the engine default (all recorded baselines and
the golden prompt depend on them); `GameData.from_project` is opt-in. Coverage is "as far as the
event model goes": tiles, monsters (incl. special ids), numeric item effects (hp/atk/def/mdef,
keys, money), key doors, walls/terrains (maps.js `noPass`), stairs and numeric shop choices.
Flag-gated NPC dialogs, afterBattle scripts and effects written as JS expressions are reported in
`unsupported` and are not simulated.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .types import DoorType, ItemTier, Monster, Hero, Keys
from . import data as D
from .data import GameData


def _js_object(path: Path) -> dict:
    """Parse `var x = {...};` or `main.floors.X = {...}` into a dict (trailing commas tolerated)."""
    text = path.read_text(encoding="utf-8")
    body = text[text.index("{"): text.rindex("}") + 1]
    body = re.sub(r",(\s*[}\]])", r"\1", body)
    return json.loads(body)


_KEY_COLORS = {"yellowKey": DoorType.YELLOW, "blueKey": DoorType.BLUE, "redKey": DoorType.RED}
_STAT_RE = re.compile(r"core\.status\.hero\.(hp|atk|def|mdef|money|exp)\s*\+=\s*(\d+)\s*;?\s*$")
_VALUES_RE = re.compile(r"core\.status\.hero\.(hp|atk|def|mdef)\s*\+=\s*core\.values\.(\w+)(\s*\*\s*core\.status\.thisMap\.ratio)?\s*;?\s*$")
_TOOL_KEYS = {"yellowKey": "keys.yellow", "blueKey": "keys.blue", "redKey": "keys.red"}
_TIER_SCORE = {  # mirrors the built-in table's ordering
    ItemTier.KEY: 85, ItemTier.CORE_STAT: 90, ItemTier.HP: 65, ItemTier.MAJOR_STAT: 97, ItemTier.MISC: 30,
}


@dataclass
class MotaProject:
    root: Path
    name: str
    floor_ids: list[str]
    maps: dict[int, dict]
    enemys: dict[str, dict]
    items: dict[str, dict]
    values: dict[str, float]
    data: dict
    unsupported: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: str | Path) -> "MotaProject":
        root = Path(root)
        data = _js_object(root / "data.js")
        maps = {int(k): v for k, v in _js_object(root / "maps.js").items()}
        enemys = _js_object(root / "enemys.js")
        items = _js_object(root / "items.js")
        return cls(root=root, name=data.get("firstData", {}).get("title") or root.parent.name,
                   floor_ids=list(data["main"]["floorIds"]), maps=maps, enemys=enemys, items=items,
                   values=dict(data.get("values", {})), data=data)

    # -- tables -------------------------------------------------------------------------------
    def monsters(self) -> dict[str, Monster]:
        out: dict[str, Monster] = {}
        for eid, e in self.enemys.items():
            out[eid] = Monster(
                id=eid, name=e.get("name", eid), hp=int(e.get("hp", 0) or 0), atk=int(e.get("atk", 0) or 0),
                def_=int(e.get("def", 0) or 0), money=int(e.get("money", 0) or 0), exp=int(e.get("exp", 0) or 0),
                special=e.get("special", 0) or 0, damage=int(e.get("damage", 0) or 0),
                vampire=float(e.get("vampire", 0) or 0), n=int(e.get("n", 0) or 0),
                name_zh=e.get("name", eid),
            )
        return out

    def item_effects(self) -> dict[str, dict]:
        """Numeric effects only; JS expressions are recorded under unsupported['items']."""
        out: dict[str, dict] = {}
        bad: list[str] = []
        for iid, it in self.items.items():
            name = it.get("name", iid)
            if it.get("cls") == "tools" and iid in _TOOL_KEYS:
                out[iid] = {_TOOL_KEYS[iid]: 1, "tier": ItemTier.KEY, "score": _TIER_SCORE[ItemTier.KEY], "name": name}
                continue
            eff_src = it.get("itemEffect")
            if not eff_src:
                out[iid] = {"tier": ItemTier.MISC, "score": 10, "name": name}
                continue
            changes: dict[str, int] = {}
            for stmt in str(eff_src).split(";"):
                stmt = stmt.strip()
                if not stmt:
                    continue
                m = _STAT_RE.match(stmt + ";")
                if m:
                    changes[m.group(1)] = changes.get(m.group(1), 0) + int(m.group(2))
                    continue
                m = _VALUES_RE.match(stmt + ";")
                if m and m.group(2) in self.values:
                    # per-floor `ratio` is not tracked by FloorData; ratio=1 assumed
                    changes[m.group(1)] = changes.get(m.group(1), 0) + int(self.values[m.group(2)])
                    continue
                bad.append(f"{iid}: {stmt}")
            if not changes:
                out[iid] = {"tier": ItemTier.MISC, "score": 10, "name": name}
                continue
            if "atk" in changes or "def" in changes or "mdef" in changes:
                big = max(changes.get("atk", 0), changes.get("def", 0), changes.get("mdef", 0))
                tier = ItemTier.MAJOR_STAT if big >= 10 else ItemTier.CORE_STAT
            elif "hp" in changes:
                tier = ItemTier.HP
            else:
                tier = ItemTier.MISC
            label = ", ".join(f"+{v} {k.upper()}" for k, v in changes.items())
            out[iid] = {**changes, "tier": tier, "score": _TIER_SCORE[tier], "name": f"{name} ({label})"}
        if bad:
            self.unsupported["items"] = bad
        return out

    def tile_tables(self) -> dict:
        items: dict[int, str] = {}
        enemies: dict[int, str] = {}
        npcs: dict[int, str] = {}
        doors: dict[int, DoorType] = {}
        stairs: dict[int, str] = {}
        walls: set[int] = set()
        terrains: set[int] = set()
        blocked: list[str] = []
        for tid, m in self.maps.items():
            cls, mid = m.get("cls"), m.get("id", "")
            keys = (m.get("doorInfo") or {}).get("keys")
            if keys:  # a real key door
                if len(keys) == 1 and next(iter(keys)) in _KEY_COLORS:
                    doors[tid] = _KEY_COLORS[next(iter(keys))]
                else:
                    walls.add(tid)  # green/special/steel keys are not modelled -> impassable
                    blocked.append(f"{tid}:{mid} needs {keys}")
                continue
            if mid == "ice" or (keys == {} and mid.lower().endswith("door")):
                doors[tid] = DoorType.ICE
                continue
            if cls in ("enemys", "enemy48"):
                enemies[tid] = mid
            elif cls == "items":
                items[tid] = mid
            elif cls in ("npcs", "npc48"):
                npcs[tid] = mid
            elif mid in ("upFloor", "downFloor"):
                stairs[tid] = mid
            elif cls == "animates" or cls == "autotile":
                walls.add(tid)  # walls, fake walls, stars, lava animations: all impassable
            elif cls == "terrains":
                if m.get("noPass"):
                    walls.add(tid)
                else:
                    terrains.add(tid)
        if blocked:
            self.unsupported["doors"] = blocked
        return {"items": items, "enemies": enemies, "npcs": npcs, "doors": doors, "stairs": stairs,
                "walls": walls, "terrains": terrains}

    def shops(self) -> dict[str, dict]:
        """data.js shops with numeric setValue actions -> engine shop dicts."""
        out: dict[str, dict] = {}
        skipped: list[str] = []
        shop_list = self.data.get("shops") or self.data.get("firstData", {}).get("shops") or []
        for shop in shop_list:
            sid = shop.get("id")
            if not sid:
                continue
            choices = []
            currency = "money"
            shop_cost = 0
            for ch in shop.get("choices", []) or []:
                cost = 0
                changes: dict[str, int] = {}
                ok = True
                for a in ch.get("action", []) or []:
                    if a.get("type") != "setValue":
                        continue
                    name, op, val = str(a.get("name", "")), a.get("operator"), a.get("value")
                    try:
                        num = int(float(str(val)))
                    except (TypeError, ValueError):
                        ok = False
                        break
                    if name in ("status:money", "status:exp") and op == "-=":
                        currency = name.split(":")[1]
                        cost = num
                    elif name.startswith("status:") and op == "+=":
                        stat = name.split(":")[1]
                        if stat in ("hp", "atk", "def", "mdef", "money"):
                            changes[stat] = num
                    elif name.startswith("item:") and name.split(":")[1] in _TOOL_KEYS:
                        changes[_TOOL_KEYS[name.split(":")[1]]] = num if op == "+=" else -num
                    # flags are bookkeeping only
                if not ok or not changes:
                    skipped.append(f"{sid}: {ch.get('text', '?')}")
                    continue
                label = re.sub(r"\s+", " ", str(ch.get("text", "")))[:40]
                choices.append({"id": f"c{len(choices)}", "label": label, "cost": cost, "changes": changes})
                shop_cost = shop_cost or cost
            if choices:
                out[sid] = {"name": shop.get("textInList") or sid, "currency": currency, "cost": shop_cost, "choices": choices}
        if skipped:
            self.unsupported["shops"] = skipped
        return out

    # -- engine objects -----------------------------------------------------------------------
    def game_data(self) -> GameData:
        t = self.tile_tables()
        return GameData(
            custom_monsters=self.monsters(), custom_items=self.item_effects(), custom_shops=self.shops(),
            extra_enemy_tiles=t["enemies"], tile_items=t["items"], tile_doors=t["doors"], tile_npcs=t["npcs"],
            tile_stairs=t["stairs"] or None, tile_walls=t["walls"], tile_terrains=t["terrains"],
            source=str(self.root),
        )

    def initial_hero(self) -> Hero:
        h = self.data["firstData"]["hero"]
        tools = h.get("items", {}).get("tools", {})
        loc = h.get("loc", {})
        return Hero(hp=h.get("hp", 1000), atk=h.get("atk", 10), def_=h.get("def", 10), mdef=h.get("mdef", 0),
                    money=h.get("money", 0), exp=h.get("exp", 0),
                    keys=Keys(tools.get("yellowKey", 0), tools.get("blueKey", 0), tools.get("redKey", 0)),
                    x=loc.get("x", 6), y=loc.get("y", 10))

    @property
    def floors_dir(self) -> Path:
        return self.root / "floors"

    @property
    def data_js(self) -> Path:
        return self.root / "data.js"


def from_project(root: str | Path) -> GameData:
    return MotaProject.load(root).game_data()


# Convenience: GameData.from_project(root)
GameData.from_project = staticmethod(from_project)  # type: ignore[attr-defined]


def builtin_root() -> Path:
    from ..paths import GAME_24
    return GAME_24


__all__ = ["MotaProject", "from_project", "builtin_root", "D"]
