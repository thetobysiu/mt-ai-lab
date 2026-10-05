"""Core data types for the MOTA game engine."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import copy


class ActionType(str, Enum):
    FIGHT = "fight"
    COLLECT = "collect"
    OPEN_DOOR = "open_door"
    USE_STAIRS = "use_stairs"
    SHOP_BUY = "shop_buy"
    TALK_NPC = "talk_npc"
    RETURN_TO_FLOOR = "return_to_floor"


class DoorType(str, Enum):
    YELLOW = "yellow"
    BLUE = "blue"
    RED = "red"
    ICE = "ice"  # maps.js id 6: openDoor trigger with keys={} -> opens for free


class ItemTier(str, Enum):
    MAJOR_STAT = "major_stat"    # Sword, shield
    CORE_STAT = "core_stat"      # Gems
    KEY = "key"
    HP = "hp"                    # Potions
    MISC = "misc"


@dataclass
class Keys:
    yellow: int = 0
    blue: int = 0
    red: int = 0

    def copy(self) -> Keys:
        return Keys(self.yellow, self.blue, self.red)

    def has_key(self, door_type: DoorType) -> bool:
        if door_type == DoorType.ICE:
            return True
        return getattr(self, door_type.value) > 0

    def use_key(self, door_type: DoorType):
        if door_type == DoorType.ICE:
            return
        current = getattr(self, door_type.value)
        if current <= 0:
            raise ValueError(f"No {door_type.value} key to use")
        setattr(self, door_type.value, current - 1)


@dataclass
class Hero:
    hp: int = 1000
    atk: int = 10
    def_: int = 10   # 'def' is reserved in Python
    mdef: int = 0
    money: int = 0
    exp: int = 0
    keys: Keys = field(default_factory=Keys)
    x: int = 0
    y: int = 0
    lv: int = 1

    def copy(self) -> Hero:
        h = Hero(
            hp=self.hp, atk=self.atk, def_=self.def_, mdef=self.mdef,
            money=self.money, exp=self.exp, keys=self.keys.copy(),
            x=self.x, y=self.y, lv=self.lv,
        )
        return h


@dataclass
class Monster:
    id: str            # e.g. "greenSlime"
    name: str          # display name (English by default, see data.display_monster_name)
    hp: int = 0
    atk: int = 0
    def_: int = 0
    money: int = 0
    exp: int = 0
    special: int | list[int] = 0
    damage: int = 0       # Fixed damage (special 22)
    vampire: float = 0.0  # Vampire ratio (special 11)
    n: int = 0            # N-hit count (special 6)
    name_zh: str = ""     # original enemys.js name, e.g. "绿头怪"

    @property
    def specials(self) -> list[int]:
        if isinstance(self.special, list):
            return self.special
        if self.special == 0:
            return []
        return [self.special]


@dataclass
class BattleResult:
    can_win: bool
    total_damage: int
    hp_after: int
    turns: int


@dataclass
class Action:
    action_id: int
    type: ActionType
    x: int
    y: int
    name: str = ""
    # Fight fields
    total_damage: int = 0
    hp_after: int = 0
    can_win: bool = True
    damage_percent: float = 0.0
    monster_id: str = ""
    # Collect fields
    item_id: str = ""
    item_tier: ItemTier = ItemTier.MISC
    item_score: int = 0
    # Door fields
    door_type: Optional[DoorType] = None
    # Shop fields
    shop_choice: str = ""
    stat_changes: dict = field(default_factory=dict)
    money_cost: int = 0          # cost in `currency` units (name kept for compatibility)
    currency: str = "money"      # "money" or "exp"
    can_afford: bool = True
    # Pathfinding
    path_steps: int = 0
    path: list[tuple[int, int]] = field(default_factory=list)
    # Lookahead: items/doors that become accessible after this action
    unlocks_items: list = field(default_factory=list)  # flat label list (legacy display)
    lookahead_value: int = 0
    # Structured lookahead tree: each entry {"label", "depth", "via": [gateway_labels], "value", "type"}
    unlocks_tree: list = field(default_factory=list)
    is_dead_end: bool = False
    # Reachability facts (state._mark_alternative_routes): entities this action alone exposes, and
    # the label of another listed action that exposes all of them (None = this action is needed).
    direct_unlocks: frozenset = frozenset()
    alternative_route: Optional[str] = None
    alternative_route_strict: bool = False
    # D3: stat-only lookahead (gems/keys/doors/stairs/shops) and order-independent potion HP
    stat_lookahead_raw: int = 0
    stat_lookahead: int = 0
    potion_hp: int = 0
    # Multi-floor: target floor id for RETURN_TO_FLOOR actions
    target_floor_id: str = ""
    # MOTA_REMOTE_ACTIONS: an action on another visited floor (target_floor_id); `remote` is the same action as that
    # floor's GameState reports it (renumbered), applying the wrapper walks there first
    remote: Optional["Action"] = None

    def label(self) -> str:
        base = self._base_label()
        return f"[{self.target_floor_id}] {base}" if self.remote is not None else base

    def _base_label(self) -> str:
        if self.type == ActionType.FIGHT:
            return f"Fight {self.name} at ({self.x},{self.y}) dmg={self.total_damage}"
        elif self.type == ActionType.COLLECT:
            return f"Collect {self.name} at ({self.x},{self.y})"
        elif self.type == ActionType.OPEN_DOOR:
            return f"Open {self.door_type.value} door at ({self.x},{self.y})"
        elif self.type == ActionType.USE_STAIRS:
            return f"Use stairs at ({self.x},{self.y})"
        elif self.type == ActionType.SHOP_BUY:
            unit = "exp" if self.currency == "exp" else "g"
            return f"Shop buy {self.shop_choice} for {self.money_cost}{unit}"
        if self.type == ActionType.RETURN_TO_FLOOR:
            if self.name.startswith("revisit"):
                return f"Return to {self.target_floor_id} ({self.name})"
            return f"Return to {self.target_floor_id} to open door at ({self.x},{self.y})"
        return f"{self.type.value} at ({self.x},{self.y})"


@dataclass
class DeferredDoor:
    """A locked door on a previous floor that couldn't be opened at the time."""
    floor_id: str
    floor_idx: int
    x: int
    y: int
    door_type: DoorType
    floor_name: str = ""


@dataclass
class FloorData:
    floor_id: str
    width: int
    height: int
    map: list[list[int]]                          # map[y][x]
    events: dict[str, list[dict]]                  # "x,y" -> event list
    change_floor: dict[str, dict]                  # "x,y" -> floor transition
    up_floor: tuple[int, int] = (0, 0)             # Arrival pos from below
    down_floor: tuple[int, int] = (0, 0)           # Arrival pos from above
    after_battle: dict = None                      # "x,y" -> script run after that fight (afterBattle)


@dataclass
class StepTrace:
    turn: int
    action: Action
    hero_before: dict
    hero_after: dict
    note: str = ""
    sub_steps: list = field(default_factory=list)  # Captured pickups during movement
