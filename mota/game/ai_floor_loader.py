"""
AI test floor loader — parses the magic-tower-AI .txt format into game objects.

The .txt format from magic-tower-AI/test/ contains:
  - Floor count and dimensions
  - Map grids using MOTA tile IDs (0=ground, 1=wall, 27=redGem, 81=yellowDoor, 201+=enemy, etc.)
  - Custom item bonuses (gem/potion/sword/shield values)
  - Custom enemy definitions (ID, HP, ATK, DEF, coins, effect)
  - Shop config (cost, increment, HP/ATK/DEF/MDEF per purchase)
  - Hero initial stats (HP, ATK, DEF, MDEF, gold, keys, position)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from .types import FloorData, Hero, Keys, Monster, ItemTier


# Effect code → special ability ID mapping (from ReadMe.txt)
_EFFECT_MAP = {
    0: 0,    # None
    1: 1,    # First Strike
    2: 2,    # Magic Attack
    3: 3,    # Solid
    4: 4,    # 2-hit combo
    5: 5,    # 3-hit combo
    6: 6,    # N-hit combo (4)
    7: 7,    # Break Armor
    8: 8,    # Counter Attack
    9: 9,    # Purify
    10: 10,  # Mimic
}


@dataclass
class ScenarioConfig:
    """Complete configuration for a test scenario loaded from an AI .txt file."""
    name: str                                      # Scenario name (from filename)
    floors: list[FloorData]                        # Floor data (map grids)
    hero: Hero                                     # Initial hero state
    monsters: dict[int, Monster]                   # tile_id → Monster
    item_bonuses: ItemBonuses                      # Custom item stat values
    shop: ShopConfig | None                        # Shop config (None if no shop)
    goal: str = "clear_all_enemies"


@dataclass
class ItemBonuses:
    """Custom item stat bonuses from the .txt file."""
    red_gem_atk: int = 3
    blue_gem_def: int = 3
    green_gem_mdef: int = 0
    red_potion_hp: int = 200
    blue_potion_hp: int = 500
    yellow_potion_hp: int = 0
    green_potion_hp: int = 0
    sword_atk: int = 10
    shield_def: int = 10


@dataclass
class ShopConfig:
    """Shop configuration from the .txt file."""
    cost: int = 25
    increment: int = 0
    hp_per_buy: int = 0
    atk_per_buy: int = 0
    def_per_buy: int = 0
    mdef_per_buy: int = 0


def load_ai_floor(file_path: str | Path) -> ScenarioConfig:
    """Load a test scenario from a magic-tower-AI .txt file."""
    path = Path(file_path)
    text = path.read_text(encoding="utf-8")
    name = path.stem

    lines = [line.strip() for line in text.strip().splitlines()]
    # Filter blank lines but track position
    tokens = _Tokenizer(lines)

    # Line 1: number of floors
    num_floors = tokens.next_int()

    # Line 2: width and height
    dims = tokens.next_ints(2)
    width, height = dims[0], dims[1]

    # Next: num_floors maps of height × width
    floors = []
    for floor_idx in range(num_floors):
        grid = []
        for row in range(height):
            row_vals = tokens.next_ints(width)
            grid.append(row_vals)
        floors.append(FloorData(
            floor_id=f"{name}_F{floor_idx + 1}" if num_floors > 1 else name,
            width=width,
            height=height,
            map=grid,
            events={},
            change_floor={},
            up_floor=(0, 0),
            down_floor=(0, 0),
        ))

    # Item bonuses: 9 numbers
    bonus_vals = tokens.next_ints(9)
    item_bonuses = ItemBonuses(
        red_gem_atk=bonus_vals[0],
        blue_gem_def=bonus_vals[1],
        green_gem_mdef=bonus_vals[2],
        red_potion_hp=bonus_vals[3],
        blue_potion_hp=bonus_vals[4],
        yellow_potion_hp=bonus_vals[5],
        green_potion_hp=bonus_vals[6],
        sword_atk=bonus_vals[7],
        shield_def=bonus_vals[8],
    )

    # Enemy definitions
    num_enemies = tokens.next_int()
    monsters: dict[int, Monster] = {}
    from .data import TILE_ENEMIES as _TILE_ENEMIES, get_monster as _get_std_monster
    # English display names for AI test floors (human-readable, not Chinese)
    _ENGLISH_NAMES: dict[int, str] = {
        201: "Green Slime", 202: "Red Slime", 203: "Black Slime",
        204: "Slime Lord", 205: "Bat", 206: "Big Bat",
        207: "Red Bat", 208: "Vampire", 209: "Skeleton",
        210: "Skeleton Soldier", 211: "Skeleton Captain",
        212: "Ghost Skeleton", 213: "Zombie", 214: "Zombie Knight",
        215: "Rock", 216: "Slime Man", 217: "Blue Priest",
        218: "Red Priest", 219: "Brown Wizard", 220: "Red Wizard",
        221: "Yellow Guard", 222: "Blue Guard", 223: "Red Guard",
        224: "Swordsman", 225: "Soldier", 226: "Yellow Knight",
        227: "Red Knight", 228: "Dark Knight", 229: "Black King",
        230: "Yellow King", 231: "Green King", 232: "Blue Knight",
        233: "Gold Slime", 234: "Poison Skeleton", 235: "Poison Bat",
        299: "Boss",
    }
    for _ in range(num_enemies):
        vals = tokens.next_ints(6)
        tile_id, m_hp, m_atk, m_def, m_coins, m_effect = vals
        special = _EFFECT_MAP.get(m_effect, 0)
        # Use English name lookup; fall back to "Enemy #NNN" for unknown IDs
        _display_name = _ENGLISH_NAMES.get(tile_id, f"Enemy #{tile_id}")
        monsters[tile_id] = Monster(
            id=f"enemy_{tile_id}",
            name=_display_name,
            hp=m_hp, atk=m_atk, def_=m_def,
            money=m_coins, exp=0,
            special=special,
        )

    # Shop config: 6 numbers
    shop_vals = tokens.next_ints(6)
    shop = None
    if shop_vals[0] < 999999 and any(shop_vals[2:]):
        shop = ShopConfig(
            cost=shop_vals[0],
            increment=shop_vals[1],
            hp_per_buy=shop_vals[2],
            atk_per_buy=shop_vals[3],
            def_per_buy=shop_vals[4],
            mdef_per_buy=shop_vals[5],
        )

    # Hero initial stats: 11 numbers
    hero_vals = tokens.next_ints(11)
    # hero_vals[8] = starting floor index (0-based)
    # Java AI uses x=row, y=column; our engine uses x=column, y=row → swap
    hero = Hero(
        hp=hero_vals[0],
        atk=hero_vals[1],
        def_=hero_vals[2],
        mdef=hero_vals[3],
        money=hero_vals[4],
        keys=Keys(yellow=hero_vals[5], blue=hero_vals[6], red=hero_vals[7]),
        x=hero_vals[10],
        y=hero_vals[9],
    )

    # Set up_floor to hero start position (for pathfinding initialization)
    start_floor_idx = hero_vals[8]
    if 0 <= start_floor_idx < len(floors):
        floors[start_floor_idx].up_floor = (hero.x, hero.y)

    # Auto-detect boss tile (299) — mirror Java shouldStop() which terminates
    # as soon as the boss is killed, not when all enemies are cleared.
    has_boss = any(
        floors[fi].map[r][c] == 299
        for fi in range(len(floors))
        for r in range(floors[fi].height)
        for c in range(floors[fi].width)
    )
    goal = "boss" if has_boss else "clear_all_enemies"

    return ScenarioConfig(
        name=name,
        floors=floors,
        hero=hero,
        monsters=monsters,
        item_bonuses=item_bonuses,
        shop=shop,
        goal=goal,
    )


def build_item_effects(bonuses: ItemBonuses) -> dict[str, dict]:
    """Build item effects dict from custom bonuses (overrides data.py defaults)."""
    return {
        "yellowKey": {"keys.yellow": 1, "tier": ItemTier.KEY, "score": 80, "name": "Yellow Key"},
        "blueKey":   {"keys.blue": 1,   "tier": ItemTier.KEY, "score": 85, "name": "Blue Key"},
        "redKey":    {"keys.red": 1,    "tier": ItemTier.KEY, "score": 90, "name": "Red Key"},
        "redGem":    {"atk": bonuses.red_gem_atk,  "tier": ItemTier.CORE_STAT, "score": 90,
                      "name": f"Red Gem (+{bonuses.red_gem_atk} ATK)"},
        "blueGem":   {"def": bonuses.blue_gem_def,  "tier": ItemTier.CORE_STAT, "score": 90,
                      "name": f"Blue Gem (+{bonuses.blue_gem_def} DEF)"},
        "greenGem":  {"mdef": bonuses.green_gem_mdef, "tier": ItemTier.CORE_STAT, "score": 85,
                      "name": f"Green Gem (+{bonuses.green_gem_mdef} MDEF)"},
        "redPotion":    {"hp": bonuses.red_potion_hp,    "tier": ItemTier.HP, "score": 60,
                         "name": f"Red Potion (+{bonuses.red_potion_hp} HP)"},
        "bluePotion":   {"hp": bonuses.blue_potion_hp,   "tier": ItemTier.HP, "score": 70,
                         "name": f"Blue Potion (+{bonuses.blue_potion_hp} HP)"},
        "yellowPotion": {"hp": bonuses.yellow_potion_hp, "tier": ItemTier.HP, "score": 65,
                         "name": f"Yellow Potion (+{bonuses.yellow_potion_hp} HP)"},
        "greenPotion":  {"hp": bonuses.green_potion_hp,  "tier": ItemTier.HP, "score": 55,
                         "name": f"Green Potion (+{bonuses.green_potion_hp} HP)"},
        "sword1": {"atk": bonuses.sword_atk, "tier": ItemTier.MAJOR_STAT, "score": 95,
                   "name": f"Iron Sword (+{bonuses.sword_atk} ATK)"},
        "shield1": {"def": bonuses.shield_def, "tier": ItemTier.MAJOR_STAT, "score": 95,
                    "name": f"Iron Shield (+{bonuses.shield_def} DEF)"},
    }


def build_monsters_lookup(monsters: dict[int, Monster]) -> dict[str, Monster]:
    """Build a monster lookup by string ID (matching TILE_ENEMIES mapping)."""
    from . import data as D
    lookup: dict[str, Monster] = {}
    for tile_id, monster in monsters.items():
        # Check if this tile_id maps to a known MOTA enemy name
        mota_id = D.TILE_ENEMIES.get(tile_id)
        if mota_id:
            # Override the existing monster with custom stats, keeping MOTA name mapping
            lookup[mota_id] = monster
            monster.id = mota_id  # Update the ID to match MOTA's lookup
        else:
            # Unknown tile ID — keep the auto-generated ID
            lookup[monster.id] = monster
    return lookup


def build_shop_def(shop: ShopConfig | None, scenario_name: str = "custom") -> dict:
    """Build a shop definition dict compatible with data.py SHOPS format."""
    if shop is None:
        return {}
    choices = []
    if shop.hp_per_buy > 0:
        choices.append({"id": "hp", "label": f"HP +{shop.hp_per_buy}", "changes": {"hp": shop.hp_per_buy}})
    if shop.atk_per_buy > 0:
        choices.append({"id": "atk", "label": f"ATK +{shop.atk_per_buy}", "changes": {"atk": shop.atk_per_buy}})
    if shop.def_per_buy > 0:
        choices.append({"id": "def", "label": f"DEF +{shop.def_per_buy}", "changes": {"def": shop.def_per_buy}})
    if shop.mdef_per_buy > 0:
        choices.append({"id": "mdef", "label": f"MDEF +{shop.mdef_per_buy}", "changes": {"mdef": shop.mdef_per_buy}})
    if not choices:
        return {}
    return {
        f"shop_{scenario_name}": {
            "name": f"Shop ({scenario_name})",
            "cost": shop.cost,
            "choices": choices,
        }
    }


class _Tokenizer:
    """Simple line-based tokenizer that skips blank lines."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self._pos = 0

    def _skip_blank(self):
        while self._pos < len(self._lines) and not self._lines[self._pos].strip():
            self._pos += 1

    def next_int(self) -> int:
        self._skip_blank()
        vals = self._parse_numbers(self._lines[self._pos])
        self._pos += 1
        return vals[0]

    def next_ints(self, count: int) -> list[int]:
        """Read numbers, possibly spanning multiple lines, until `count` numbers collected."""
        self._skip_blank()
        collected: list[int] = []
        while len(collected) < count and self._pos < len(self._lines):
            line = self._lines[self._pos].strip()
            if not line:
                self._pos += 1
                continue
            nums = self._parse_numbers(line)
            collected.extend(nums)
            self._pos += 1
        return collected[:count]

    @staticmethod
    def _parse_numbers(line: str) -> list[int]:
        """Parse space/tab-separated integers from a line."""
        parts = line.replace('\t', ' ').split()
        return [int(p) for p in parts if p.lstrip('-').isdigit()]
