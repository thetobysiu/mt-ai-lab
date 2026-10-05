"""
Game state engine — manages the full simulation of a MOTA floor.
Tracks hero stats, removed entities, available actions, and goal progress.
"""
from __future__ import annotations
import copy
import os
from collections import deque
from .types import (
    Hero, Keys, Action, ActionType, DoorType, ItemTier,
    FloorData, BattleResult, StepTrace,
)
from . import data as D
from .data import get_monster, get_item_effect, SHOPS, GameData, DEFAULT_GAME_DATA
from . import damage as dmg
from . import pathfinder as pf


def _hints_suppressed() -> bool:
    """Whether fight lines drop lookahead/effCost/tree/stat annotations.

    `MOTA_SUPPRESS_HINTS=1|0` decides explicitly. Unset: follow `MOTA_DISABLE_OVERRIDES` (the
    historical coupling that every stored "overrides off" complex result was produced with).
    """
    v = os.environ.get("MOTA_SUPPRESS_HINTS", "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return bool(os.environ.get("MOTA_DISABLE_OVERRIDES"))


def _order_two_sided() -> bool:
    """MOTA_ORDER_TWO_SIDED=1: ORDER lines name their fight and also state when this fight first is cheaper."""
    return os.environ.get("MOTA_ORDER_TWO_SIDED", "").strip().lower() in ("1", "true", "yes")


def _fight_key_flood() -> bool:
    """MOTA_FIGHT_KEY_FLOOD=1: fight key line from the flood fill (depth-independent), like doors."""
    return os.environ.get("MOTA_FIGHT_KEY_FLOOD", "").strip().lower() in ("1", "true", "yes")


def _bare_obs() -> bool:
    """MOTA_BARE_OBS=1: the observation a player sees on screen — hero stats, keys, items, the
    reachable actions with monster stats and the exact damage (the in-game monster manual shows it),
    boss stats. No engine analysis: no lookahead tree, effCost, tags (OPTIONAL / DEAD END / FREE /
    RISKY), tips, HP or key budgets, ORDER / stat / key lines, legend. Engine computations (and the
    mechanical safety overrides) are unchanged; only the text differs. GEPA study 2026-09-28."""
    return os.environ.get("MOTA_BARE_OBS", "").strip().lower() in ("1", "true", "yes")


def _compact_prompt() -> bool:
    """MOTA_COMPACT_PROMPT=1: static legend once in the system map instead of every turn; no
    per-turn 'Uncollected items' list (the unlock trees carry the same items per action)."""
    return os.environ.get("MOTA_COMPACT_PROMPT", "").strip().lower() in ("1", "true", "yes")


_HP_RULE_PCT = 40


def hp_rule_pct() -> int:
    """Threshold of prompt rule 4 ("never fight a monster that costs more than X % of current HP") as quoted by the
    engine lines that refer to it. 40 on single floors; the tower scenario sets 60 since 2026-10-02 (user decision
    after the MT3 turn-15 replay). MOTA_HP_RULE_PCT pins it (the design 1-4 re-runs pin 40)."""
    env = os.environ.get("MOTA_HP_RULE_PCT", "").strip()
    return int(env) if env else _HP_RULE_PCT


def set_hp_rule_pct(pct: int) -> None:
    global _HP_RULE_PCT
    _HP_RULE_PCT = pct


def key_purchase_hidden(choice_id: str) -> bool:
    """MOTA_NO_KEY_PURCHASE=1 (user 2026-10-02): yellow and blue keys are not offered for sale; red keys stay (an
    expert buys one or two). MOTA_BLUE_KEY_PURCHASE=1 (grill 10-04, princess-chain test) offers blue keys again."""
    if choice_id == "buy_blue" and os.environ.get("MOTA_BLUE_KEY_PURCHASE") == "1":
        return False
    return os.environ.get("MOTA_NO_KEY_PURCHASE") == "1" and choice_id in ("buy_yellow", "buy_blue")


def _boss_key_reserve() -> bool:
    """MOTA_BOSS_KEY_RESERVE=1 (user 2026-10-04): a door off the cheapest route to the boss that leaves fewer keys of
    its colour than that route still needs says so (16 of 20 complex-floor episodes spent the boss gate's yellow key
    on (10,5)); the single-floor counterpart of the tower's key-reserve line."""
    return os.environ.get("MOTA_BOSS_KEY_RESERVE") == "1"


_ACTIONS_LEGEND = [
    "  (Note: lookahead = total item/stat value unlocked by this action [HP-equivalent].",
    "   effCost = raw damage cost minus lookahead. A 200-damage fight with lookahead=180 costs only 20",
    "   effective HP. For via-chain enemies: fight cost shown with DEF threshold hint — consider",
    "   scouting upstairs/getting more DEF before fighting if the cost is too high.",
    "   min-cost@maxStats = fight cost AFTER collecting all remaining DEF/ATK gems — shows how much HP",
    "   you save by collecting stat gems BEFORE this fight. Large savings = defer this fight.)",
]


class GameState:
    """Mutable game state for a single floor."""

    def __init__(
        self,
        floor: FloorData,
        hero: Hero,
        goal: str = "clear_all_enemies",
        max_turns: int = 300,
        game_data: GameData | None = None,
        lookahead_depth: int | None = None,
        _removed: set[tuple[int, int]] | None = None,
    ):
        self.floor = floor
        self.hero = hero
        self.goal = goal
        self.max_turns = max_turns
        self.gd = game_data or DEFAULT_GAME_DATA
        # Configurable lookahead depth; falls back to env var LOOKAHEAD_DEPTH (default 3)
        import os
        self.lookahead_depth = lookahead_depth if lookahead_depth is not None else int(os.environ.get("LOOKAHEAD_DEPTH", "3"))

        self.turn = 0
        self.removed: set[tuple[int, int]] = set(_removed) if _removed else set()
        self.shop_purchases: dict[str, list[str]] = {}  # shopId -> [choice_ids]
        self.history: list[StepTrace] = []
        self.floor_history: list[str] = []  # compact per-turn log for LLM context

        # Count initial enemies and record starting HP
        self.initial_enemies = self._count_enemies()
        self._initial_hp = hero.hp
        self.goal_reached = False
        self.failed = False
        self.failure_reason = ""

    def _count_enemies(self) -> int:
        count = 0
        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if (x, y) not in self.removed and self.gd.is_enemy(self.floor.map[y][x]):
                    count += 1
        return count

    def remaining_enemies(self) -> int:
        return self._count_enemies()

    def _summarize_remaining_items(self) -> tuple[str, int]:
        """Return a compact pickup summary plus the remaining DEF total."""
        total_def = total_atk = total_hp = total_mdef = total_money = 0
        yellow_keys = blue_keys = red_keys = 0
        misc_counts: dict[str, int] = {}

        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if not self.gd.is_item(tile):
                    continue

                item_id = self.gd.get_item_id(tile)
                if not item_id:
                    continue
                eff = self.gd.get_item_effect(item_id)
                name = eff.get("name", item_id)
                recognised = False

                if eff.get("atk"):
                    total_atk += eff["atk"]
                    recognised = True
                if eff.get("def"):
                    total_def += eff["def"]
                    recognised = True
                if eff.get("hp"):
                    total_hp += eff["hp"]
                    recognised = True
                if eff.get("mdef"):
                    total_mdef += eff["mdef"]
                    recognised = True
                if eff.get("money"):
                    total_money += eff["money"]
                    recognised = True
                if eff.get("keys.yellow"):
                    yellow_keys += eff["keys.yellow"]
                    recognised = True
                if eff.get("keys.blue"):
                    blue_keys += eff["keys.blue"]
                    recognised = True
                if eff.get("keys.red"):
                    red_keys += eff["keys.red"]
                    recognised = True

                if not recognised:
                    misc_counts[name] = misc_counts.get(name, 0) + 1

        parts = []
        if total_atk:
            parts.append(f"ATK+{total_atk}")
        if total_def:
            parts.append(f"DEF+{total_def}")
        if total_hp:
            parts.append(f"HP+{total_hp}")
        if total_mdef:
            parts.append(f"MDEF+{total_mdef}")
        if total_money:
            parts.append(f"Gold+{total_money}")
        if yellow_keys:
            parts.append(f"Y+{yellow_keys}")
        if blue_keys:
            parts.append(f"B+{blue_keys}")
        if red_keys:
            parts.append(f"R+{red_keys}")
        for name, count in sorted(misc_counts.items()):
            parts.append(f"{name} x{count}" if count > 1 else name)

        return (", ".join(parts) if parts else "none", total_def)

    def _path_crosses_uncollected_entity(self, path: list[tuple[int, int]], target_x: int, target_y: int) -> bool:
        """
        Return True when the action path crosses another uncollected entity (item/enemy) before target.

        This keeps click semantics intuitive: one chosen action should resolve the first 
        interactable entity on the route, not skip over it.
        """
        if not path:
            return False

        target = (target_x, target_y)
        for sx, sy in path:
            if (sx, sy) == target:
                break
            if (sx, sy) in self.removed:
                continue
            tile = self.floor.map[sy][sx]
            if self.gd.is_item(tile) or self.gd.is_enemy(tile):
                return True

        return False

    def _find_path_to_target(self, target_x: int, target_y: int, avoid_intermediate_items: bool) -> list[tuple[int, int]] | None:
        """
        Find a shortest path from hero to target with optional intermediate-item avoidance.

        If avoid_intermediate_items is True, all uncollected item tiles are treated as
        blocked except the target itself.
        """
        start = (self.hero.x, self.hero.y)
        target = (target_x, target_y)
        if start == target:
            return []

        queue: deque[tuple[int, int]] = deque([start])
        visited: set[tuple[int, int]] = {start}
        parent: dict[tuple[int, int], tuple[int, int]] = {}

        while queue:
            cx, cy = queue.popleft()
            for dx, dy in pf.DIRECTIONS:
                nx, ny = cx + dx, cy + dy
                pos = (nx, ny)

                if nx < 0 or nx >= self.floor.width or ny < 0 or ny >= self.floor.height:
                    continue
                if pos in visited:
                    continue
                if not self._can_step_for_path(pos, target, avoid_intermediate_items):
                    continue

                visited.add(pos)
                parent[pos] = (cx, cy)

                if pos == target:
                    return self._reconstruct_path(parent, start, target)

                queue.append(pos)

        return None

    def _can_step_for_path(
        self,
        pos: tuple[int, int],
        target: tuple[int, int],
        avoid_intermediate_items: bool,
    ) -> bool:
        if pos == target:
            return True

        x, y = pos
        if pos in self.removed:
            return True

        tile = self.floor.map[y][x]
        if self.gd.is_wall(tile):
            return False
        if self.gd.is_ground(tile) or self.gd.is_terrain(tile) or self.gd.is_stairs(tile):
            return True
        if self.gd.is_item(tile):
            return not avoid_intermediate_items

        # Doors, enemies, NPCs, and unknown tiles block path traversal.
        return False

    @staticmethod
    def _reconstruct_path(
        parent: dict[tuple[int, int], tuple[int, int]],
        start: tuple[int, int],
        target: tuple[int, int],
    ) -> list[tuple[int, int]]:
        path = [target]
        cur = target
        while cur != start:
            cur = parent.get(cur)
            if cur is None:
                return []
            path.append(cur)
        path.reverse()
        return path[1:]

    def reachable_shops(self) -> list[dict]:
        """Shops whose NPC tile is reachable right now: [{x, y, shop_id, shop}].
        Independent of affordability — used for first-contact discovery (quick-shop)."""
        reachable = pf.find_reachable(
            grid=self.floor.map, start_x=self.hero.x, start_y=self.hero.y,
            keys=self.hero.keys, removed=self.removed, stop_at_doors=True,
            height=self.floor.height, width=self.floor.width, include_paths=False,
            game_data=self.gd,
        )
        out = []
        shops = self.gd.get_shops()
        for (x, y), info in reachable.items():
            if not info["accessible"] or info["type"] != "npc":
                continue
            for evt in self.floor.events.get(f"{x},{y}", []):
                if isinstance(evt, dict) and evt.get("type") == "openShop" and evt["id"] in shops:
                    out.append({"x": x, "y": y, "shop_id": evt["id"], "shop": shops[evt["id"]]})
        return out

    def get_actions(self, annotate: bool = True) -> list[Action]:
        """Get all available actions from the current state (annotate=False skips the unlock lookahead)."""
        reachable = pf.find_reachable(
            grid=self.floor.map,
            start_x=self.hero.x,
            start_y=self.hero.y,
            keys=self.hero.keys,
            removed=self.removed,
            stop_at_doors=True,
            height=self.floor.height,
            width=self.floor.width,
            include_paths=True,
            game_data=self.gd,
        )

        actions: list[Action] = []
        action_id = 1

        for (x, y), info in sorted(reachable.items()):
            if not info["accessible"]:
                continue

            path = info.get("path", [])
            safe_path = self._find_path_to_target(x, y, avoid_intermediate_items=True)
            if safe_path is not None:
                path = safe_path
            elif self._path_crosses_uncollected_entity(path, x, y):
                continue

            path_steps = len(path)

            if info["type"] == "enemy":
                monster = self.gd.get_monster(info["entity_id"])
                result = dmg.calculate(self.hero, monster)
                a = Action(
                    action_id=action_id, type=ActionType.FIGHT,
                    x=x, y=y, name=monster.name,
                    total_damage=result.total_damage,
                    hp_after=result.hp_after,
                    can_win=result.can_win,
                    damage_percent=round(result.total_damage / max(1, self.hero.hp) * 100, 1),
                    monster_id=monster.id,
                    path_steps=path_steps,
                    path=path,
                )
                actions.append(a)
                action_id += 1

            elif info["type"] == "item":
                item_id = info["entity_id"]
                effect = self.gd.get_item_effect(item_id)
                a = Action(
                    action_id=action_id, type=ActionType.COLLECT,
                    x=x, y=y, name=effect.get("name", item_id),
                    item_id=item_id,
                    item_tier=effect.get("tier", ItemTier.MISC),
                    item_score=effect.get("score", 10),
                    path_steps=path_steps,
                    path=path,
                )
                actions.append(a)
                action_id += 1

            elif info["type"] == "door":
                door_type = info["door_type"]
                a = Action(
                    action_id=action_id, type=ActionType.OPEN_DOOR,
                    x=x, y=y, name=f"{door_type.value.title()} Door",
                    door_type=door_type,
                    path_steps=path_steps,
                    path=path,
                )
                actions.append(a)
                action_id += 1

            elif info["type"] == "stairs":
                stair_id = info["entity_id"]
                # Only offer "upFloor" as the progression stairs;
                # skip downFloor — the agent should never go backwards.
                if stair_id == "downFloor":
                    continue
                a = Action(
                    action_id=action_id, type=ActionType.USE_STAIRS,
                    x=x, y=y, name=stair_id,
                    path_steps=path_steps,
                    path=path,
                )
                actions.append(a)
                action_id += 1

            elif info["type"] == "npc":
                # Check if NPC has a shop event or hands out an item unconditionally
                coord_key = f"{x},{y}"
                if coord_key in self.floor.events:
                    evts = self.floor.events[coord_key]
                    gift_id = self._npc_gift_item(evts)
                    if gift_id is not None:
                        effect = self.gd.get_item_effect(gift_id)
                        a = Action(
                            action_id=action_id, type=ActionType.COLLECT,
                            x=x, y=y,
                            name=f"{(self.gd.get_npc_id(self.floor.map[y][x]) or 'NPC')} gives {effect.get('name', gift_id)}",
                            item_id=gift_id,
                            item_tier=effect.get("tier", ItemTier.MISC),
                            item_score=effect.get("score", 10),
                            path_steps=path_steps,
                            path=path,
                        )
                        actions.append(a)
                        action_id += 1
                        continue
                    trade = self._npc_trade(evts)
                    if trade is not None:
                        item_id, currency, price = trade
                        if D.hero_balance(self.hero, currency) >= price:
                            effect = self.gd.get_item_effect(item_id)
                            actions.append(Action(
                                action_id=action_id, type=ActionType.COLLECT, x=x, y=y,
                                name=f"{self.gd.get_npc_id(self.floor.map[y][x]) or 'NPC'} trades "
                                     f"{effect.get('name', item_id)} for {price} {D.shop_unit(currency)}",
                                item_id=item_id, item_tier=effect.get("tier", ItemTier.MISC),
                                item_score=effect.get("score", 10), money_cost=price, currency=currency,
                                can_afford=True, path_steps=path_steps, path=path,
                            ))
                            action_id += 1
                        continue
                    for evt in evts:
                        if not isinstance(evt, dict):
                            continue
                        if evt.get("type") == "openShop":
                            shop_id = evt["id"]
                            shops = self.gd.get_shops()
                            shop = shops.get(shop_id)
                            if shop:
                                currency = shop.get("currency", "money")
                                for choice in shop["choices"]:
                                    # Unaffordable purchases are not legal actions: selecting one
                                    # used to be a silent no-op that still consumed a turn (tower
                                    # run 6 "bought" HP twice with 11 gold). The floor map still
                                    # lists the shop and its prices.
                                    if not D.shop_choice_affordable(self.hero, shop, choice):
                                        continue
                                    # S1: level-ups are forbidden by both prompts; W1 bought two anyway.
                                    # Mechanical like auto-fight-0-HP; MOTA_OFFER_LEVELUPS=1 restores them.
                                    if choice["id"] == "level" and not os.environ.get("MOTA_OFFER_LEVELUPS"):
                                        continue
                                    if key_purchase_hidden(choice["id"]):
                                        continue
                                    a = Action(
                                        action_id=action_id,
                                        type=ActionType.SHOP_BUY,
                                        x=x, y=y,
                                        name=f"{shop['name']}: {choice['label']}",
                                        shop_choice=choice["id"],
                                        stat_changes=choice["changes"],
                                        money_cost=choice.get("cost", shop.get("cost", 0)),
                                        currency=currency,
                                        can_afford=True,
                                        path_steps=path_steps,
                                        path=path,
                                    )
                                    actions.append(a)
                                    action_id += 1

        # One-step lookahead: annotate fight actions with what they unlock
        fight_actions = [a for a in actions if a.type == ActionType.FIGHT]
        door_actions = [a for a in actions if a.type == ActionType.OPEN_DOOR]
        if annotate and (fight_actions or door_actions):
            self._compute_unlocks(fight_actions + door_actions, reachable)

        return actions

    @staticmethod
    def _npc_has_cross_floor_event(evts: list) -> bool:
        """An NPC whose script removes tiles on another floor (MT4 thief → MT2 (2,7))."""
        for evt in evts:
            if not isinstance(evt, dict):
                continue
            if evt.get("type") == "hide" and evt.get("floorId"):
                return True
            if evt.get("type") == "if" and GameState._npc_has_cross_floor_event((evt.get("true") or []) + (evt.get("false") or [])):
                return True
        return False

    def _npc_gift_item(self, evts: list) -> str | None:
        """Return the item id an NPC hands out unconditionally (flat event list with
        `setValue item:X += 1` and `hide`), or None for conditional/dialog-only NPCs."""
        gift = None
        hides = False
        for evt in evts:
            if not isinstance(evt, dict):
                continue
            t = evt.get("type")
            if t in ("if", "switch", "choices", "openShop", "changeFloor"):
                return None
            if t == "setValue" and str(evt.get("name", "")).startswith("item:"):
                item_id = evt["name"].split(":", 1)[1]
                eff = self.gd.get_item_effect(item_id)
                if any(k in eff for k in ("hp", "atk", "def", "mdef", "money", "keys.yellow", "keys.blue", "keys.red")):
                    gift = item_id
            elif t == "hide":
                hides = True
        return gift if (gift and hides) else None

    @staticmethod
    def _npc_trade(evts: list) -> tuple[str, str, int] | None:
        """MOTA_NPC_TRADES=1 (user 2026-10-02): a one-off trade NPC, `if (status:exp<N)` / `(status:money<N)` whose
        false branch gives item:X, debits the currency and hides (MT15: Holy Sword for 500 EXP, Holy Shield for
        500 gold). Returns (item id, "exp"|"money", price) or None."""
        if os.environ.get("MOTA_NPC_TRADES") != "1":
            return None
        import re
        for evt in evts:
            if not isinstance(evt, dict) or evt.get("type") != "if":
                continue
            m = re.fullmatch(r"\(?\s*status:(exp|money)\s*<\s*(\d+)\s*\)?", str(evt.get("condition", "")).strip())
            if not m:
                continue
            branch = [e for e in (evt.get("false") or []) if isinstance(e, dict)]
            item = next((e["name"].split(":", 1)[1] for e in branch
                         if e.get("type") == "setValue" and str(e.get("name", "")).startswith("item:")), None)
            paid = any(e.get("type") == "setValue" and e.get("name") == f"status:{m[1]}" and e.get("operator") == "-="
                       for e in branch)
            if item and paid and any(e.get("type") == "hide" for e in branch):
                return item, m[1], int(m[2])
        return None

    def _describe_unlock(self, info: dict) -> str:
        if info["type"] == "item":
            effect = self.gd.get_item_effect(info["entity_id"])
            name = effect.get("name", info["entity_id"])
            tier = effect.get("tier", ItemTier.MISC)
            if tier == ItemTier.MAJOR_STAT:
                return f"{name} [MAJOR]"
            if tier == ItemTier.CORE_STAT:
                return f"{name} [STAT]"
            return name
        if info["type"] == "door":
            return f"{info['door_type'].value} door"
        if info["type"] == "stairs":
            return "stairs"
        if info["type"] == "shop":
            return info.get("label", "Shop [SHOP]")
        return info["type"]

    def _score_unlock(self, info: dict, depth: int, keys_state: Keys) -> int:
        depth_scale = 1.0 if depth == 0 else (0.7 if depth == 1 else (0.5 if depth == 2 else 0.35))
        value = 0

        if info["type"] == "item":
            effect = self.gd.get_item_effect(info["entity_id"])
            value += effect.get("hp", 0)
            value += effect.get("atk", 0) * 70
            value += effect.get("def", 0) * 90
            value += effect.get("mdef", 0) * 45
            value += effect.get("money", 0) // 5
            value += effect.get("keys.yellow", 0) * 60
            value += effect.get("keys.blue", 0) * 90
            value += effect.get("keys.red", 0) * 120
            if value == 0:
                value = effect.get("score", 10) * 4

        elif info["type"] == "door":
            door_type = info["door_type"]
            remaining_keys = getattr(keys_state, door_type.value, 99)
            base_cost = {
                DoorType.YELLOW: 80,
                DoorType.BLUE: 130,
                DoorType.RED: 180,
                DoorType.ICE: 0,
            }[door_type]
            if remaining_keys > 1:
                base_cost = int(base_cost * 0.75)
            value = base_cost

        elif info["type"] == "stairs":
            value = 120

        elif info["type"] == "shop":
            value = info.get("shop_value", 200)

        return int(round(value * depth_scale))

    def _door_has_direct_progress(self, reachable: dict, base_accessible: set, base_enemies: set) -> bool:
        for (x, y), info in reachable.items():
            if not info["accessible"]:
                continue

            pos = (x, y)
            entity_type = info["type"]

            if entity_type in ("item", "door", "stairs") and pos not in base_accessible:
                return True

            if entity_type == "npc" and pos not in base_accessible:
                coord_key = f"{x},{y}"
                if coord_key in self.floor.events:
                    evts = self.floor.events[coord_key]
                    if self._npc_gift_item(evts) or self._npc_has_cross_floor_event(evts) or self._npc_trade(evts):
                        return True
                    for evt in evts:
                        if isinstance(evt, dict) and evt.get("type") == "openShop":
                            return True

            if entity_type == "enemy" and pos not in base_enemies:
                mon = self.gd.get_monster(info["entity_id"])
                if dmg.calculate(self.hero, mon).can_win:
                    return True

        return False

    def _compute_unlocks(self, actions_to_annotate: list[Action], base_reachable: dict) -> None:
        """
        Depth-N lookahead: for each FIGHT or OPEN_DOOR action, find newly exposed entities
        across up to self.lookahead_depth more blockers. Tracks via-chains so the LLM can
        see the full causal path. Also detects shop NPCs as high-value unlocks.

        Mutates action.unlocks_items, action.unlocks_tree, and action.lookahead_value.
        """
        base_accessible = {
            (x, y)
            for (x, y), info in base_reachable.items()
            if info["accessible"] and info["type"] in ("item", "door", "stairs", "npc")
        }
        base_enemies = {
            (x, y)
            for (x, y), info in base_reachable.items()
            if info["accessible"] and info["type"] == "enemy"
        }
        max_depth = self.lookahead_depth
        max_listed_unlocks = 12

        for action in actions_to_annotate:
            action.is_dead_end = False
            lookahead_keys = self.hero.keys.copy()
            if action.type == ActionType.OPEN_DOOR and action.door_type:
                try:
                    lookahead_keys.use_key(action.door_type)
                except ValueError:
                    continue

            initial_removed = frozenset({(action.x, action.y)})
            # frontier entries: (extra_removed, keys_state, depth, via_chain, via_pos)
            # via_chain is a tuple of gateway labels that led to this frontier state;
            # via_pos the same gateways as (x,y) so costs can be recomputed at other stats.
            frontier = [(initial_removed, lookahead_keys, 0, (), ())]
            seen_states = {
                (initial_removed, lookahead_keys.yellow, lookahead_keys.blue, lookahead_keys.red)
            }
            # Map label -> {"value", "depth", "via": tuple, "type"}
            unlock_details: dict[str, dict] = {}
            direct_progress = False

            while frontier:
                extra_removed, keys_state, depth, via_chain, via_pos = frontier.pop()
                reachable = pf.find_reachable(
                    grid=self.floor.map,
                    start_x=self.hero.x,
                    start_y=self.hero.y,
                    keys=keys_state,
                    removed=self.removed | set(extra_removed),
                    stop_at_doors=True,
                    height=self.floor.height,
                    width=self.floor.width,
                    game_data=self.gd,
                )

                if depth == 0 and action.type == ActionType.OPEN_DOOR:
                    direct_progress = self._door_has_direct_progress(
                        reachable,
                        base_accessible,
                        base_enemies,
                    )
                if depth == 0:
                    # Entities this action alone exposes (used for the alternative-route check below).
                    action.direct_unlocks = frozenset(
                        (x, y) for (x, y), info in reachable.items()
                        if info["accessible"] and (x, y) != (action.x, action.y) and (
                            (info["type"] in ("item", "door", "stairs", "npc") and (x, y) not in base_accessible)
                            or (info["type"] == "enemy" and (x, y) not in base_enemies)
                        )
                    )

                for (x, y), info in reachable.items():
                    if not info["accessible"]:
                        continue
                    pos = (x, y)
                    entity_type = info["type"]

                    # Detect newly accessible items / doors / stairs
                    if entity_type in ("item", "door", "stairs") and pos not in base_accessible:
                        label = self._describe_unlock(info)
                        value = self._score_unlock(info, depth, keys_state)
                        # Keyed by (label, pos): two Blue Gems behind one door are two entries, not one.
                        key = (label, pos)
                        existing = unlock_details.get(key)
                        if existing is None or value > existing["value"]:
                            eff = self.gd.get_item_effect(info["entity_id"]) if entity_type == "item" else {}
                            unlock_details[key] = {
                                "value": value, "depth": depth,
                                "via": via_chain, "type": entity_type,
                                "via_pos": via_pos, "pos": pos,
                                "atk": eff.get("atk", 0), "def": eff.get("def", 0),
                                "hp": eff.get("hp", 0) if entity_type == "item" else 0,
                                "keys": {c: eff.get(f"keys.{c}", 0) for c in ("yellow", "blue", "red")
                                         if eff.get(f"keys.{c}", 0)},
                            }

                    # Detect newly accessible enemies (gateway monsters behind doors)
                    # Show them as explicit entries so the LLM knows what's waiting
                    elif entity_type == "enemy" and pos not in base_enemies and pos not in extra_removed:
                        mon = self.gd.get_monster(info["entity_id"])
                        battle = dmg.calculate(self.hero, mon)
                        if battle.can_win:
                            dmg_pct = round(battle.total_damage / max(1, self.hero.hp) * 100, 1)
                            if 2 not in mon.specials:  # not magic-atk
                                def_gap = mon.atk - self.hero.def_
                                if def_gap > 0:
                                    def_note = f", FREE@DEF≥{mon.atk}(+{def_gap})"
                                else:
                                    def_note = ", DEF-immune"
                            else:
                                def_note = ", magic-atk"
                            label = f"⚔ {mon.name}@({x},{y}) dmg={battle.total_damage}({dmg_pct}%){def_note}"
                        else:
                            label = f"⚔ {mon.name}@({x},{y}) CANNOT WIN"
                        # Negative value for enemies (cost, not reward); worse = more negative
                        enemy_value = -battle.total_damage if battle.can_win else -9999
                        existing = unlock_details.get((label, pos))
                        if existing is None:
                            unlock_details[(label, pos)] = {
                                "value": enemy_value, "depth": depth,
                                "via": via_chain, "type": "enemy", "via_pos": via_pos, "pos": pos,
                            }

                    # Detect newly accessible shop NPCs
                    elif entity_type == "npc" and pos not in base_accessible:
                        coord_key = f"{x},{y}"
                        gift_id = self._npc_gift_item(self.floor.events.get(coord_key, []))
                        trade = None if gift_id else self._npc_trade(self.floor.events.get(coord_key, []))
                        if trade:
                            gift_id = trade[0]
                        if gift_id:  # MT2 gift characters: their item counts like an item on the floor
                            eff = self.gd.get_item_effect(gift_id)
                            label = f"{self.gd.get_npc_id(info['tile']) or 'NPC'} gives {eff.get('name', gift_id)}"
                            if trade:
                                label = (f"{self.gd.get_npc_id(info['tile']) or 'NPC'} trades {eff.get('name', gift_id)} "
                                         f"for {trade[2]} {D.shop_unit(trade[1])}")
                            value = self._score_unlock({**info, "type": "item", "entity_id": gift_id}, depth, keys_state)
                            if (label, pos) not in unlock_details or value > unlock_details[(label, pos)]["value"]:
                                unlock_details[(label, pos)] = {
                                    "value": value, "depth": depth, "via": via_chain, "type": "item", "via_pos": via_pos,
                                    "pos": pos, "atk": eff.get("atk", 0), "def": eff.get("def", 0), "hp": eff.get("hp", 0),
                                    "keys": {},
                                }
                        if coord_key in self.floor.events:
                            for evt in self.floor.events[coord_key]:
                                if not isinstance(evt, dict):
                                    continue
                                if evt.get("type") == "openShop":
                                    shop_id = evt["id"]
                                    shops = self.gd.get_shops()
                                    shop = shops.get(shop_id)
                                    if shop:
                                        label = f"{shop['name']} [SHOP]"
                                        # Score: sum stat value across all choices (generous budgeting)
                                        shop_value = sum(
                                            ch["changes"].get("def", 0) * 90
                                            + ch["changes"].get("atk", 0) * 70
                                            + ch["changes"].get("hp", 0)
                                            for ch in shop["choices"]
                                        )
                                        if shop_value == 0:
                                            shop_value = 200
                                        shop_info = {"type": "shop", "label": label, "shop_value": shop_value}
                                        value = self._score_unlock(shop_info, depth, keys_state)
                                        existing = unlock_details.get((label, pos))
                                        if existing is None or value > existing["value"]:
                                            unlock_details[(label, pos)] = {
                                                "value": value, "depth": depth,
                                                "via": via_chain, "type": "shop", "via_pos": via_pos, "pos": pos,
                                                "shop_id": shop_id,
                                            }
                                    break

                    if depth >= max_depth:
                        continue

                    # Expand frontier through newly reachable enemies
                    if entity_type == "enemy" and pos not in base_enemies and pos not in extra_removed:
                        mon = self.gd.get_monster(info["entity_id"])
                        battle = dmg.calculate(self.hero, mon)
                        if not battle.can_win:
                            continue

                        next_removed = frozenset(set(extra_removed) | {pos})
                        signature = (next_removed, keys_state.yellow, keys_state.blue, keys_state.red)
                        if signature not in seen_states:
                            seen_states.add(signature)
                            # Target format: "Enemy #NNN@(x,y) [dmg=N (N%), FREE if DEF≥X (+N needed)]"
                            dmg_pct = round(battle.total_damage / max(1, self.hero.hp) * 100)
                            specials_list = mon.specials
                            if 2 not in specials_list:  # not magic-atk
                                def_gap = mon.atk - self.hero.def_
                                if def_gap > 0:
                                    def_hint = f", FREE if DEF≥{mon.atk} (+{def_gap} needed)"
                                else:
                                    def_hint = ", DEF-immune"
                            else:
                                def_hint = ", magic-atk (DEF irrelevant)"
                            gateway = f"{mon.name}@({x},{y}) [dmg={battle.total_damage} ({dmg_pct}%){def_hint}]"
                            frontier.append((next_removed, keys_state.copy(), depth + 1, via_chain + (gateway,), via_pos + (pos,)))

                    # Expand frontier through newly reachable openable doors
                    elif (
                        entity_type == "door"
                        and pos not in base_accessible
                        and keys_state.has_key(info["door_type"])
                    ):
                        next_keys = keys_state.copy()
                        try:
                            next_keys.use_key(info["door_type"])
                        except ValueError:
                            continue
                        next_removed = frozenset(set(extra_removed) | {pos})
                        signature = (next_removed, next_keys.yellow, next_keys.blue, next_keys.red)
                        if signature not in seen_states:
                            seen_states.add(signature)
                            gateway = f"{info['door_type'].value}Door@({x},{y})"
                            frontier.append((next_removed, next_keys, depth + 1, via_chain + (gateway,), via_pos))

            ordered_unlocks = sorted(unlock_details.items(), key=lambda it: (-it[1]["value"], it[0][0], it[0][1]))
            listed = ordered_unlocks[:max_listed_unlocks]
            # Flat label list keeps one entry per kind with a multiplicity marker.
            label_counts: dict[str, int] = {}
            for (label, _pos), _d in listed:
                label_counts[label] = label_counts.get(label, 0) + 1
            action.unlocks_items = [f"{lb} ×{n}" if n > 1 else lb for lb, n in label_counts.items()]
            # Net lookahead: item/shop/stairs value MINUS unique gateway enemy costs.
            # Gateway enemies appear in via-chains as "MonName@(x,y) [dmg=NNN ...]".
            # Each gateway's damage is counted once (even if shared by multiple items).
            import re as _re
            _gateway_cost_re = _re.compile(r'dmg=(\d+)')
            # The heuristic ranks by lookahead_value; it is a fixed baseline (simple HP 443, MT3 1.0),
            # so those numbers keep the pre-D2 label-deduplicated semantics. Only the LLM-facing
            # quantities below (stat_lookahead, potion_hp, unlocks_tree) see every item.
            legacy_seen: set[str] = set()
            raw_item_value = 0
            unique_gateways: dict[str, int] = {}  # gateway_id → damage
            for (label, _pos), d in listed:
                if d["type"] == "enemy" or label in legacy_seen:
                    continue
                legacy_seen.add(label)
                raw_item_value += d["value"]
                for gw in d["via"]:
                    # gateway id = "MonName@(x,y)" (stable coordinate key)
                    gw_id = gw.split(" [")[0] if " [" in gw else gw
                    if gw_id not in unique_gateways:
                        m = _gateway_cost_re.search(gw)
                        unique_gateways[gw_id] = int(m.group(1)) if m else 0
            total_gateway_cost = sum(unique_gateways.values())
            action.lookahead_value = max(0, raw_item_value - total_gateway_cost)
            action.raw_lookahead = raw_item_value
            action.gateway_cost = total_gateway_cost
            # D3: potions are collected in any order, so they are not fight value. The displayed
            # effCost uses stat_lookahead; potions are listed separately (CB1: effCost=-218 on a 235-HP
            # fight because of a potion behind it; simple T9: effCost=-195 for the same reason).
            stat_raw_value = 0   # everything except potion HP (gems, keys, doors, stairs, shops)
            potion_hp = 0        # undiscounted HP of potions behind this action (order-independent)
            all_gateways: dict[str, int] = {}
            for (label, _pos), d in listed:
                if d["type"] == "enemy":
                    continue
                if d["type"] == "item" and d.get("hp", 0) and not (d.get("atk") or d.get("def")):
                    potion_hp += d["hp"]
                else:
                    stat_raw_value += d["value"]
                for gw in d["via"]:
                    gw_id = gw.split(" [")[0] if " [" in gw else gw
                    if gw_id not in all_gateways:
                        m = _gateway_cost_re.search(gw)
                        all_gateways[gw_id] = int(m.group(1)) if m else 0
            action.stat_lookahead_raw = stat_raw_value
            action.stat_lookahead = max(0, stat_raw_value - sum(all_gateways.values()))
            action.potion_hp = potion_hp
            action.unlocks_tree = [
                {
                    "label": label,
                    "pos": list(pos),
                    "depth": d["depth"],
                    "via": list(d["via"]),
                    "via_enemies": [list(p) for p in d.get("via_pos", ())],
                    "value": d["value"],
                    "type": d["type"],
                    "atk": d.get("atk", 0),
                    "def": d.get("def", 0),
                    "hp": d.get("hp", 0),
                    "keys": dict(d.get("keys") or {}),
                    "shop_id": d.get("shop_id"),
                }
                for (label, pos), d in listed
            ]
            if action.type == ActionType.OPEN_DOOR:
                # Dead-end check uses raw_lookahead (before gateway subtraction) —
                # a door with items behind monsters is NOT a dead end.
                action.is_dead_end = not direct_progress and getattr(action, 'raw_lookahead', action.lookahead_value) <= 0

        self._mark_alternative_routes(actions_to_annotate)

    def _mark_alternative_routes(self, actions: list[Action]) -> None:
        """Pure reachability fact: if everything action A exposes is also exposed by another listed
        action B (B winnable / openable), then A is not needed while B is available. Two actions that
        expose exactly the same set are alternatives to each other. Sets `action.alternative_route`
        to B's label (or None). Motivated by the simple floor: Red Slime (5,3) and Black Slime (6,4)
        both open the Green Slime (5,6) corridor, and the LLM fought both (SIMPLE_FLOOR_PLAN.md §5 C0).
        """
        cands = [a for a in actions
                 if a.type in (ActionType.FIGHT, ActionType.OPEN_DOOR)
                 and getattr(a, "direct_unlocks", None)
                 and (a.type != ActionType.FIGHT or a.can_win)]
        for a in actions:
            a.alternative_route = None
        def cost(x):
            return x.total_damage if x.type == ActionType.FIGHT else 0

        for a in cands:
            best = None
            for b in cands:
                if b is a or not a.direct_unlocks <= b.direct_unlocks:
                    continue
                strict = a.direct_unlocks < b.direct_unlocks
                # Prefer a strict superset (A is redundant); among equals the cheaper action.
                key = (0 if strict else 1, cost(b), b.action_id)
                if best is None or key < best[0]:
                    best = (key, b, strict)
            if best is not None:
                _, b, strict = best
                a.alternative_route = b.label()
                a.alternative_route_strict = strict

    def apply_action(self, action: Action) -> StepTrace:
        """Apply an action and return the step trace."""
        hero_before = self._hero_snapshot()
        self.turn += 1

        # Walk the announced path first and capture intermediate pickups
        sub_steps = self._move_along_path_trace(getattr(action, "path", []))

        if action.type == ActionType.FIGHT:
            self._apply_fight(action)
        elif action.type == ActionType.COLLECT:
            self._apply_collect(action)
        elif action.type == ActionType.OPEN_DOOR:
            self._apply_open_door(action)
        elif action.type == ActionType.USE_STAIRS:
            self._apply_stairs(action)
        elif action.type == ActionType.SHOP_BUY:
            self._apply_shop_buy(action)

        self._update_goal()
        self._check_failure()

        hero_after = self._hero_snapshot()
        trace = StepTrace(
            turn=self.turn,
            action=action,
            hero_before=hero_before,
            hero_after=hero_after,
            sub_steps=sub_steps,
        )
        self.history.append(trace)
        # Compact log entry for LLM floor memory
        hp_delta = hero_after["hp"] - hero_before["hp"]
        delta_str = f" (HP {'+' if hp_delta >= 0 else ''}{hp_delta}→{hero_after['hp']})"
        self.floor_history.append(f"T{self.turn}: {action.label()}{delta_str}")
        return trace

    def apply_action_by_id(self, action_id: int) -> StepTrace | None:
        """Find action by ID in current actions and apply it."""
        actions = self.get_actions()
        for a in actions:
            if a.action_id == action_id:
                return self.apply_action(a)
        return None

    def _apply_item_effect(self, effect: dict):
        if "hp" in effect:
            self.hero.hp += effect["hp"]
        if "atk" in effect:
            self.hero.atk += effect["atk"]
        if "def" in effect:
            self.hero.def_ += effect["def"]
        if "mdef" in effect:
            self.hero.mdef += effect["mdef"]
        if "money" in effect:
            self.hero.money += effect["money"]
        if "keys.yellow" in effect:
            self.hero.keys.yellow += effect["keys.yellow"]
        if "keys.blue" in effect:
            self.hero.keys.blue += effect["keys.blue"]
        if "keys.red" in effect:
            self.hero.keys.red += effect["keys.red"]
        if "lv" in effect:
            self.hero.lv += effect["lv"]
        if "hp_mul" in effect:
            self.hero.hp *= effect["hp_mul"]

    def _collect_item_at(self, x: int, y: int) -> bool:
        """Collect item at (x,y) if present and not already removed."""
        if (x, y) in self.removed:
            return False

        tile = self.floor.map[y][x]
        if not self.gd.is_item(tile):
            return False

        item_id = self.gd.get_item_id(tile)
        if item_id is None:
            return False

        effect = self.gd.get_item_effect(item_id)
        self._apply_item_effect(effect)
        self.removed.add((x, y))
        return True

    def _move_along_path_trace(self, path: list[tuple[int, int]]) -> list[dict]:
        """Move hero step-by-step and capture intermediate item pickups as sub-steps."""
        sub_steps = []
        for step_x, step_y in path:
            self.hero.x = step_x
            self.hero.y = step_y
            
            # Check for item pickup
            if (step_x, step_y) not in self.removed:
                tile = self.floor.map[step_y][step_x]
                if self.gd.is_item(tile):
                    item_id = self.gd.get_item_id(tile)
                    if item_id:
                        eff = self.gd.get_item_effect(item_id)
                        self._apply_item_effect(eff)
                        self.removed.add((step_x, step_y))
                        sub_steps.append({
                            "type": "collect",
                            "x": step_x, "y": step_y,
                            "name": eff.get("name", item_id),
                            "hero": self._hero_snapshot()
                        })
        return sub_steps

    def _move_along_path(self, path: list[tuple[int, int]]) -> None:
        """Legacy method: Move hero and auto-collect."""
        self._move_along_path_trace(path)

    def _apply_fight(self, action: Action):
        monster = self.gd.get_monster(action.monster_id)
        result = dmg.calculate(self.hero, monster)
        self.hero.hp = result.hp_after
        self.hero.money += monster.money
        self.hero.exp += monster.exp
        self.removed.add((action.x, action.y))
        # Move hero to the monster's position
        self.hero.x = action.x
        self.hero.y = action.y

    def _apply_collect(self, action: Action):
        # If the target was already picked up while traversing the path, this is a no-op.
        if not self._collect_item_at(action.x, action.y) and action.item_id \
                and (action.x, action.y) not in self.removed \
                and self.gd.is_npc(self.floor.map[action.y][action.x]):
            # Gift NPC: apply the item effect and remove the NPC tile.
            if action.money_cost:  # trade NPC
                if action.currency == "exp":
                    self.hero.exp -= action.money_cost
                else:
                    self.hero.money -= action.money_cost
            self._apply_item_effect(self.gd.get_item_effect(action.item_id))
            self.removed.add((action.x, action.y))
        self.hero.x = action.x
        self.hero.y = action.y

    def _apply_open_door(self, action: Action):
        if action.door_type:
            self.hero.keys.use_key(action.door_type)
        self.removed.add((action.x, action.y))
        # Move hero to the door tile after opening it.
        self.hero.x = action.x
        self.hero.y = action.y

    def _apply_stairs(self, action: Action):
        self.hero.x = action.x
        self.hero.y = action.y
        # For single-floor simulation, using stairs means floor is done

    def _apply_shop_buy(self, action: Action):
        if not action.can_afford:
            return  # Cannot afford — skip silently
        D.apply_shop_effect(self.hero, action)
        # Buying at a shop implies moving to the shop NPC tile.
        self.hero.x = action.x
        self.hero.y = action.y
        # Track purchase
        shop_coord = f"{action.x},{action.y}"
        self.shop_purchases.setdefault(shop_coord, []).append(action.shop_choice)

    def _update_goal(self):
        if self.goal == "clear_all_enemies":
            if self.remaining_enemies() == 0:
                self.goal_reached = True
        elif self.goal == "boss":
            # Goal reached when boss tile (299) is removed (killed)
            for y in range(self.floor.height):
                for x in range(self.floor.width):
                    if self.floor.map[y][x] == 299 and (x, y) in self.removed:
                        self.goal_reached = True
                        return
        elif self.goal == "stairs":
            last = self.history[-1] if self.history else None
            if last and last.action.type == ActionType.USE_STAIRS:
                self.goal_reached = True

    def _check_failure(self):
        if self.hero.hp <= 0:
            self.failed = True
            self.failure_reason = "Hero died"
        elif self.turn >= self.max_turns:
            if not self.goal_reached:
                self.failed = True
                self.failure_reason = f"Turn limit ({self.max_turns}) exceeded"

    def _hero_snapshot(self) -> dict:
        return {
            "hp": self.hero.hp, "atk": self.hero.atk, "def": self.hero.def_,
            "mdef": self.hero.mdef, "money": self.hero.money, "exp": self.hero.exp,
            "keys_y": self.hero.keys.yellow, "keys_b": self.hero.keys.blue,
            "keys_r": self.hero.keys.red,
            "x": self.hero.x, "y": self.hero.y,
        }

    # Special ability ID → short label
    _SPECIAL_LABELS = {
        1: "first-strike", 2: "magic-atk", 3: "solid",
        4: "2x-combo", 5: "3x-combo", 6: "Nx-combo",
        7: "break-armor", 8: "counter", 9: "purify", 10: "mimic",
    }

    def format_state(self, actions=None) -> str:
        """Format current state for LLM consumption (target format).
        
        Args:
            actions: optional list of current available actions — if provided, the HP budget
                     for boss-goal floors will show boss-path-only cost (excluding optional enemies).
        """
        from . import data as D
        from . import damage as _dmg_mod
        from dataclasses import replace as dc_replace
        lines = []
        lines.append(f"=== Floor: {self.floor.floor_id} | Turn {self.turn}/{self.max_turns} ===")
        hp_pct = round(self.hero.hp / max(1, self._initial_hp) * 100, 1)
        hp_status = "CRITICAL" if hp_pct < 25 else ("LOW" if hp_pct < 50 else "OK")
        lines.append(f"Hero: HP={self.hero.hp} ({hp_pct}% [{hp_status}]) ATK={self.hero.atk} DEF={self.hero.def_} "
                      f"MDEF={self.hero.mdef} Gold={self.hero.money} EXP={self.hero.exp}")
        lines.append(f"Keys: Y={self.hero.keys.yellow} B={self.hero.keys.blue} R={self.hero.keys.red}")
        bare = _bare_obs()
        if not _hints_suppressed() and not bare:
            kb = self._key_budget_line()
            if kb:
                lines.append(kb)
        lines.append(f"Position: ({self.hero.x},{self.hero.y})")
        enemies_left = self.remaining_enemies()
        lines.append(f"Enemies remaining: {enemies_left}/{self.initial_enemies}")

        # List individual uncollected items with locations
        item_parts = []
        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if not self.gd.is_item(tile):
                    continue
                item_id = self.gd.get_item_id(tile)
                if not item_id:
                    continue
                eff = self.gd.get_item_effect(item_id)
                name = eff.get("name", item_id)
                # Compact display: stat gems as "ATK+N" / "DEF+N", potions with HP bonus
                if eff.get("atk"):
                    display = f"ATK+{eff['atk']}@({x},{y})"
                elif eff.get("def"):
                    display = f"DEF+{eff['def']}@({x},{y})"
                elif eff.get("mdef"):
                    display = f"MDEF+{eff['mdef']}@({x},{y})"
                elif eff.get("hp"):
                    display = f"{name}@({x},{y})(+{eff['hp']}HP)"
                elif eff.get("keys.yellow"):
                    display = f"Yellow Key@({x},{y})"
                elif eff.get("keys.blue"):
                    display = f"Blue Key@({x},{y})"
                elif eff.get("keys.red"):
                    display = f"Red Key@({x},{y})"
                else:
                    display = f"{name}@({x},{y})"
                item_parts.append(display)
        if not _compact_prompt():
            if item_parts:
                lines.append(f"Uncollected items still on floor: {', '.join(item_parts)}")
            else:
                lines.append("Uncollected items still on floor: NONE — all collectibles have been picked up")

        # DEF threshold analysis
        total_def = self._compute_remaining_stat_gems()[0]
        if total_def > 0 and not bare:
            self._append_def_threshold_tip(lines, total_def)

        # Goal line
        if bare:
            if self.goal == "boss":
                _bmon = self.gd.get_monster("enemy_299")
                for _by in range(self.floor.height):
                    for _bx in range(self.floor.width):
                        if self.floor.map[_by][_bx] == 299 and (_bx, _by) not in self.removed and _bmon:
                            lines.append(f"Goal: defeat {_bmon.name} at ({_bx},{_by}): ATK={_bmon.atk} "
                                         f"DEF={_bmon.def_} HP={_bmon.hp}")
            elif self.goal == "clear_all_enemies":
                lines.append(f"Objective: Kill all {self.initial_enemies} enemies on this floor")
            else:
                lines.append("Goal: reach the upstairs tile.")
        elif self.goal == "boss":
            # Find boss and show detailed goal
            boss_info = ""
            has_shop = bool(self.gd.get_shops())
            _bmon = self.gd.get_monster("enemy_299")
            _boss_name = _bmon.name if _bmon else "Boss"
            for _by in range(self.floor.height):
                for _bx in range(self.floor.width):
                    if self.floor.map[_by][_bx] == 299 and (_bx, _by) not in self.removed:
                        if _bmon:
                            _bres = _dmg_mod.calculate(self.hero, _bmon)
                            if _bres.can_win:
                                boss_status = f"if fought now: dmg={_bres.total_damage} HP ({_bres.turns} turns)"
                            else:
                                _need = _bmon.def_ + 1
                                boss_status = f"if fought now: UNWINNABLE — need ATK≥{_need} to deal damage (you have ATK={self.hero.atk})"
                            boss_info = (f" {_boss_name} at ({_bx},{_by}): ATK={_bmon.atk} DEF={_bmon.def_} "
                                         f"HP={_bmon.hp} | {boss_status}")
            shop_note = " There is NO shop on this floor." if not has_shop else ""
            lines.append(
                f"Goal: defeat {_boss_name} while keeping maximum HP. "
                f"You do NOT need to kill all enemies — only fight enemies that grant stat gems, "
                f"keys, or HP needed to reach and defeat the boss.{shop_note}{boss_info} "
                f"Use LOOKAHEAD TREE to find the cheapest path to the boss."
            )
            # HP budget for boss floors: compute at best stats
            self._append_boss_hp_budget(lines)
        elif self.goal == "clear_all_enemies":
            lines.append(f"Objective: Kill all {self.initial_enemies} enemies on this floor")
            self._append_hp_budget(lines, actions=actions)
        else:
            lines.append("Goal: reach the upstairs tile; ignore irrelevant enemies.")

        # Recent actions (last 8)
        if self.floor_history:
            lines.append("Recent actions this floor:")
            for entry in self.floor_history[-8:]:
                lines.append(f"  {entry}")

        if os.environ.get("MOTA_GRID_MAP") == "1":
            # Self-lookahead condition: the current grid with walls, so the model can trace what each action opens.
            lines.append("")
            lines.append(self.format_map_grid_text(with_costs=False, xy_labels=True))
        elif os.environ.get("MOTA_BLOCKER_GRAPH") == "1":
            lines.append("")
            lines.append(self.format_blocker_graph())

        return "\n".join(lines)

    def _append_def_threshold_tip(self, lines: list, total_def_on_map: int) -> None:
        """Show DEF threshold tip in target format."""
        from . import damage as dmg_mod
        by_atk: dict[int, dict] = {}
        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if not self.gd.is_enemy(tile):
                    continue
                eid = self.gd.get_enemy_id(tile)
                if eid is None:
                    continue
                mon = self.gd.get_monster(eid)
                if 2 in mon.specials:
                    continue
                if mon.atk <= self.hero.def_:
                    continue
                def_gap = mon.atk - self.hero.def_
                if def_gap > total_def_on_map:
                    continue
                res = dmg_mod.calculate(self.hero, mon)
                key = mon.atk
                if key not in by_atk:
                    by_atk[key] = {"names": {}, "count": 0, "total_savings": 0, "def_gap": def_gap}
                by_atk[key]["count"] += 1
                by_atk[key]["total_savings"] += res.total_damage
                by_atk[key]["names"][mon.name] = by_atk[key]["names"].get(mon.name, 0) + 1
        if not by_atk:
            return
        # Show group with smallest def_gap (most achievable)
        best_key = min(by_atk, key=lambda k: by_atk[k]["def_gap"])
        g = by_atk[best_key]
        names_parts = []
        for n, c in g["names"].items():
            names_parts.append(f"{n} ×{c}")
        names_str = ", ".join(names_parts)
        lines.append(
            f"DEF threshold tip: Collect +{g['def_gap']} more DEF gems → {names_str} become FREE "
            f"(saves {g['total_savings']} HP; +{total_def_on_map} DEF gems remain on map)"
        )

    def _boss_required_monsters(self) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
        """Split remaining monsters into (required, optional) w.r.t. reaching the boss.

        A monster is *required* if the boss tile becomes unreachable from the hero when that
        monster alone is treated as a wall and every other monster and door is passable. This is
        a pure connectivity fact (no key or HP accounting) and therefore a lower bound on what
        must be fought; everything else is optional for *reaching* the boss.
        """
        H, W = self.floor.height, self.floor.width
        boss = None
        monsters: list[tuple[int, int]] = []
        for y in range(H):
            for x in range(W):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if tile == 299:
                    boss = (x, y)
                elif self.gd.is_enemy(tile):
                    monsters.append((x, y))
        if boss is None:
            return set(monsters), set()

        def reachable(blocked: tuple[int, int] | None) -> bool:
            start = (self.hero.x, self.hero.y)
            seen = {start}
            dq = deque([start])
            while dq:
                x, y = dq.popleft()
                if (x, y) == boss:
                    return True
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < W and 0 <= ny < H) or (nx, ny) in seen:
                        continue
                    if (nx, ny) == blocked:
                        continue
                    tile = self.floor.map[ny][nx]
                    if (nx, ny) not in self.removed and self.gd.is_wall(tile):
                        continue
                    seen.add((nx, ny))
                    dq.append((nx, ny))
            return False

        required = {m for m in monsters if not reachable(m)}
        return required, set(monsters) - required

    def _append_boss_hp_budget(self, lines: list) -> None:
        """HP budget for boss floors, split into required and optional monsters.

        D4 (CB1, 2026-09-25): the previous line summed *every* remaining monster at max stats and
        printed "CANNOT WIN even with all gems" on a floor the exact solver clears with 22 HP to
        spare; all five deaths cited it as licence for >40 % fights. Required = cut monsters for
        boss reachability (`_boss_required_monsters`); optional monsters are reported separately.
        """
        from . import damage as dmg_mod
        from dataclasses import replace as dc_replace

        total_potion_hp = 0
        stat_def = stat_atk = stat_mdef = 0
        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if self.gd.is_item(tile):
                    item_id = self.gd.get_item_id(tile)
                    if item_id:
                        eff = self.gd.get_item_effect(item_id)
                        total_potion_hp += eff.get("hp", 0)
                        stat_def += eff.get("def", 0)
                        stat_atk += eff.get("atk", 0)
                        stat_mdef += eff.get("mdef", 0)

        best_hero = dc_replace(
            self.hero,
            def_=self.hero.def_ + stat_def,
            atk=self.hero.atk + stat_atk,
            mdef=self.hero.mdef + stat_mdef,
        )
        required, optional = self._boss_required_monsters()

        def cost(positions) -> tuple[int, bool]:
            total, unwinnable = 0, False
            for (x, y) in positions:
                mon = self.gd.get_monster(self.gd.get_enemy_id(self.floor.map[y][x]))
                if mon is None:
                    continue
                res = dmg_mod.calculate(best_hero, mon)
                # `can_win` means "survives at current HP"; the budget compares against potions too,
                # so only "cannot deal damage" (the 999999999 sentinel) counts as unwinnable here.
                if res.total_damage >= 999999999:
                    unwinnable = True
                else:
                    total += res.total_damage
            return total, unwinnable

        # The boss itself is required by definition (tile 299 is not in either set).
        boss_pos = next(((x, y) for y in range(self.floor.height) for x in range(self.floor.width)
                         if self.floor.map[y][x] == 299 and (x, y) not in self.removed), None)
        req_cost, req_unwinnable = cost(required | ({boss_pos} if boss_pos else set()))
        opt_cost, _ = cost(optional)
        available = self.hero.hp + total_potion_hp
        surplus = available - req_cost
        lines.append(
            f"HP budget at max stats (all {stat_atk} ATK / {stat_def} DEF gems collected): {available} HP available "
            f"(HP + {total_potion_hp} potions) vs {req_cost} HP for the {len(required)} monsters that block the way to the boss + the boss "
            f"→ margin {surplus:+d} HP. {len(optional)} other monsters ({opt_cost} HP at max stats) block nothing on the way to the boss; "
            f"they are not in this budget — fight one only if its tree shows a stat gem or potion you need, and its cost then comes off this margin."
        )
        if req_unwinnable:
            lines.append("  ⚠️ A monster that blocks the boss path cannot be beaten even at max stats — look for another route or more stats.")
        elif surplus <= 0:
            lines.append(f"  ⚠️ Even the required fights exceed the HP available by {-surplus} HP at max stats — every optional fight makes it worse.")
        elif surplus <= 50:
            lines.append(f"  ⚠️ HP TIGHT: {surplus} HP margin on the required fights alone. Every stat gem before a fight is HP saved; skip optional fights.")
        else:
            for (x, y) in required:
                mon = self.gd.get_monster(self.gd.get_enemy_id(self.floor.map[y][x]))
                if mon is not None and not dmg_mod.calculate(self.hero, mon).can_win:
                    lines.append("  ⚠️ At current stats, cannot damage some required enemies. Collect stat gems first!")
                    break

    def format_floor_map(self) -> str:
        """Build a static entity-list map of this floor for the LLM system prompt.

        Called once at run start so the LLM has a full spatial reference even when
        entities are removed mid-game. Returns a compact multi-section text block.
        """
        from . import data as D
        from . import damage as dmg_mod

        enemy_lines = []
        item_lines = []
        door_lines = []
        stair_lines = []
        npc_shop_lines = []

        for y in range(self.floor.height):
            for x in range(self.floor.width):
                tile = self.floor.map[y][x]
                if tile == 0:
                    continue
                if self.gd.is_enemy(tile):
                    eid = self.gd.get_enemy_id(tile)
                    mon = self.gd.get_monster(eid)
                    specials = mon.specials
                    spec_labels = [self._SPECIAL_LABELS[s] for s in specials if s in self._SPECIAL_LABELS]
                    spec_str = f" [{','.join(spec_labels)}]" if spec_labels else ""
                    dmg_result = dmg_mod.calculate(self.hero, mon)
                    enemy_lines.append(
                        f"  {mon.name} at ({x},{y}) | ATK={mon.atk} DEF={mon.def_} HP={mon.hp}"
                        f"{spec_str} | fight_cost={dmg_result.total_damage}"
                    )
                elif self.gd.is_item(tile):
                    item_id = self.gd.get_item_id(tile)
                    eff = self.gd.get_item_effect(item_id)
                    name = eff.get("name", item_id)
                    tier = eff.get("tier", ItemTier.MISC)
                    bonuses = []
                    for k in ("hp", "atk", "def", "mdef", "money"):
                        if eff.get(k):
                            bonuses.append(f"{k}+{eff[k]}")
                    for kk in ("keys.yellow", "keys.blue", "keys.red"):
                        if eff.get(kk):
                            key_color = kk.split(".")[1]
                            bonuses.append(f"{key_color}_key+{eff[kk]}")
                    bonus_str = f" ({', '.join(bonuses)})" if bonuses else ""
                    item_lines.append(f"  {name}{bonus_str} at ({x},{y}) [tier={tier.value}]")
                elif self.gd.is_door(tile):
                    door_type = self.gd.get_door_type(tile).value
                    door_lines.append(f"  {door_type} door at ({x},{y})")
                elif self.gd.is_stairs(tile):
                    stair_dir = (self.gd.get_stairs(tile) or "?")
                    stair_lines.append(f"  Stairs({stair_dir}) at ({x},{y})")
                elif self.gd.is_npc(tile):
                    coord_key = f"{x},{y}"
                    shop_info = ""
                    if coord_key in self.floor.events:
                        for evt in self.floor.events[coord_key]:
                            if not isinstance(evt, dict):
                                continue
                            if evt.get("type") == "openShop":
                                shop_id = evt["id"]
                                shops = self.gd.get_shops()
                                shop = shops.get(shop_id)
                                if shop:
                                    unit = D.shop_unit(shop.get("currency", "money"))
                                    choices_str = ", ".join(
                                        f"{ch['label']} for {ch.get('cost', shop.get('cost', 0))}{unit}"
                                        for ch in shop["choices"]
                                    )
                                    shop_info = f" [SHOP: {choices_str}]"
                                    if os.environ.get("MOTA_TOWER_FIDELITY") == "1":
                                        # 397B design-5 turn 36 read this static entry as an open shop behind a closed door
                                        shop_info += " (usable from any floor only after you have reached it once)"
                                break
                    npc_id = (self.gd.get_npc_id(tile) or "NPC")
                    npc_shop_lines.append(f"  {npc_id} at ({x},{y}){shop_info}")

        sections = [f"=== Floor Layout: {self.floor.floor_id} (static reference) ==="]
        if enemy_lines:
            sections.append("Enemies:")
            sections.extend(sorted(enemy_lines))
        if item_lines:
            sections.append("Items:")
            sections.extend(sorted(item_lines))
        if door_lines:
            sections.append("Doors:")
            sections.extend(sorted(door_lines))
        if stair_lines:
            sections.append("Stairs / Exit:")
            sections.extend(stair_lines)
        if npc_shop_lines:
            sections.append("NPCs / Shops:")
            sections.extend(sorted(npc_shop_lines))
        if _compact_prompt():
            sections.append("How to read the action list:")
            sections.extend(_ACTIONS_LEGEND)
        return "\n".join(sections)

    def format_blocker_graph(self) -> str:
        """MOTA_BLOCKER_GRAPH: the floor as areas (bounded by walls) and the monsters/doors between them. Gives the
        topology without any multi-step lookahead or costs: the model still has to search and compute."""
        gd, f = self.gd, self.floor
        w, h = f.width, f.height

        def tile_at(p):
            return f.map[p[1]][p[0]]

        def is_blocker(p):
            t = tile_at(p)
            return p not in self.removed and (gd.is_enemy(t) or gd.is_door(t) or gd.is_npc(t))

        def passable(p):
            if p in self.removed:
                return True
            t = tile_at(p)
            return gd.is_ground(t) or gd.is_terrain(t) or gd.is_stairs(t) or gd.is_item(t)

        area_of: dict[tuple[int, int], int] = {}
        areas: list[list[tuple[int, int]]] = []
        order = [(self.hero.x, self.hero.y)] + [(x, y) for y in range(h) for x in range(w)]
        for s in order:
            if s in area_of or not passable(s):
                continue
            idx, stack = len(areas), [s]
            area_of[s] = idx
            cells = []
            while stack:
                p = stack.pop()
                cells.append(p)
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    q = (p[0] + dx, p[1] + dy)
                    if 0 <= q[0] < w and 0 <= q[1] < h and q not in area_of and passable(q):
                        area_of[q] = idx
                        stack.append(q)
            areas.append(cells)

        def blocker_name(p):
            t = tile_at(p)
            if gd.is_enemy(t):
                mon = gd.get_monster(gd.get_enemy_id(t))
                spec = [self._SPECIAL_LABELS[s] for s in mon.specials if s in self._SPECIAL_LABELS]
                return f"{mon.name} ({p[0]},{p[1]}) [HP {mon.hp}, ATK {mon.atk}, DEF {mon.def_}{', ' + ', '.join(spec) if spec else ''}]"
            if gd.is_door(t):
                return f"{gd.get_door_type(t).value} door ({p[0]},{p[1]})"
            return f"{gd.get_npc_id(t) or 'NPC'} ({p[0]},{p[1]})"

        lines = ["=== Floor areas ===",
                 "Positions are (x,y). Walls separate the areas; a monster or door stands between the areas or other "
                 "blockers it touches, and fighting it or opening it joins them."]
        for i, cells in enumerate(areas):
            items = []
            for p in sorted(cells, key=lambda c: (c[1], c[0])):
                if p in self.removed:
                    continue
                t = tile_at(p)
                if gd.is_item(t):
                    items.append(f"{gd.get_item_effect(gd.get_item_id(t)).get('name', 'item')} ({p[0]},{p[1]})")
                elif gd.is_stairs(t):
                    items.append(f"stairs ({p[0]},{p[1]})")
            tag = " (you are here)" if (self.hero.x, self.hero.y) in cells else ""
            lines.append(f"A{i + 1}{tag}: " + (", ".join(items) if items else "nothing to collect"))
        lines.append("Blockers:")
        for y in range(h):
            for x in range(w):
                p = (x, y)
                if not is_blocker(p):
                    continue
                sides = []
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    q = (x + dx, y + dy)
                    if not (0 <= q[0] < w and 0 <= q[1] < h):
                        continue
                    if q in area_of:
                        sides.append(f"A{area_of[q] + 1}")
                    elif is_blocker(q):
                        sides.append(blocker_name(q).split(" [")[0])
                lines.append(f"  {blocker_name(p)}: touches {', '.join(dict.fromkeys(sides)) or 'nothing'}")
        return "\n".join(lines)

    def format_map_grid_text(self, with_costs: bool = True, xy_labels: bool = False) -> str:
        """Render the floor as a text grid with legend — for map-based LLM experiments.

        Shows the actual tile layout so the LLM can reason about spatial
        reachability without a pre-computed action list.
        """
        from . import damage as dmg_mod

        w, h = self.floor.width, self.floor.height
        entity_legend: list[str] = []
        grid_labels: dict[tuple[int, int], str] = {}

        enemy_counter = 0
        item_labels_map: dict[int, str] = {}

        for y in range(h):
            for x in range(w):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if tile == 0:
                    continue
                if self.gd.is_enemy(tile):
                    eid = self.gd.get_enemy_id(tile)
                    mon = self.gd.get_monster(eid)
                    enemy_counter += 1
                    marker = f"M{tile}"
                    grid_labels[(x, y)] = marker
                    specials = mon.specials
                    spec_labels = [self._SPECIAL_LABELS[s] for s in specials if s in self._SPECIAL_LABELS]
                    spec_str = f" [{','.join(spec_labels)}]" if spec_labels else ""
                    dr = dmg_mod.calculate(self.hero, mon)
                    cost_str = f" fight_cost={dr.total_damage}" if with_costs else ""
                    entity_legend.append(
                        f"  {marker} at ({x},{y}): {mon.name} ATK={mon.atk} DEF={mon.def_} "
                        f"HP={mon.hp}{spec_str}{cost_str}"
                    )
                elif self.gd.is_item(tile):
                    item_id = self.gd.get_item_id(tile)
                    eff = self.gd.get_item_effect(item_id)
                    name = eff.get("name", item_id)
                    bonuses = []
                    for k in ("hp", "atk", "def", "mdef"):
                        if eff.get(k):
                            bonuses.append(f"+{eff[k]} {k.upper()}")
                    for kk in ("keys.yellow", "keys.blue", "keys.red"):
                        if eff.get(kk):
                            bonuses.append(f"+{eff[kk]} {kk.split('.')[1]}_key")
                    bonus_str = f" ({', '.join(bonuses)})" if bonuses else ""
                    marker = "I"
                    grid_labels[(x, y)] = marker
                    entity_legend.append(f"  I at ({x},{y}): {name}{bonus_str}")
                elif self.gd.is_door(tile):
                    door_type = self.gd.get_door_type(tile).value
                    marker = door_type[0].upper()
                    grid_labels[(x, y)] = marker
                    entity_legend.append(f"  {marker} at ({x},{y}): {door_type} door")
                elif self.gd.is_npc(tile):
                    grid_labels[(x, y)] = "N"
                    entity_legend.append(f"  N at ({x},{y}): NPC/Shop")

        # Build grid text
        header = ("y\\x" if xy_labels else "   ") + " ".join(f"{x:>3}" for x in range(w))
        rows = [f"=== Floor Grid ({w}×{h}) ===", header]
        for y in range(h):
            cells = []
            for x in range(w):
                if x == self.hero.x and y == self.hero.y:
                    cells.append("  @")
                elif (x, y) in grid_labels:
                    cells.append(f"{grid_labels[(x, y)]:>3}")
                elif (x, y) in self.removed:
                    cells.append("  .")
                else:
                    tile = self.floor.map[y][x]
                    if self.gd.is_wall(tile):
                        cells.append("  #")
                    elif self.gd.is_ground(tile) or tile == 0:
                        cells.append("  .")
                    else:
                        cells.append("  ?")
            rows.append(f"{y:>2} " + " ".join(cells))

        rows.append("")
        rows.append("Legend:")
        if xy_labels:
            rows.append("  Every position is written (x,y): x = column number along the top, y = row number on the left. "
                        "(7,5) is column 7 in row 5.")
        rows.append("  @ = Hero   # = Wall   . = Ground/Empty")
        rows.append("  M<id> = Monster (see details below)   I = Item   Y/B/R = Door (yellow/blue/red)")
        rows.append("")
        rows.append("Entity Details:")
        rows.extend(sorted(entity_legend))
        return "\n".join(rows)

    def _append_def_analysis(self, lines: list, total_def_on_map: int) -> None:
        """Compute DEF threshold groups and append actionable savings to lines."""
        from . import damage as dmg_mod
        # Collect remaining monster types grouped by monATK threshold
        by_atk: dict[int, dict] = {}  # monATK -> {names, count, total_savings, def_gap}
        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if not self.gd.is_enemy(tile):
                    continue
                eid = self.gd.get_enemy_id(tile)
                if eid is None:
                    continue
                mon = self.gd.get_monster(eid)
                if 2 in mon.specials:  # magic-atk: DEF useless
                    continue
                if mon.atk <= self.hero.def_:  # already free
                    continue
                def_gap = mon.atk - self.hero.def_
                if def_gap > total_def_on_map:  # not achievable
                    continue
                res = dmg_mod.calculate(self.hero, mon)
                key = mon.atk
                if key not in by_atk:
                    by_atk[key] = {"names": {}, "count": 0, "total_savings": 0, "def_gap": def_gap}
                by_atk[key]["count"] += 1
                by_atk[key]["total_savings"] += res.total_damage
                by_atk[key]["names"][mon.name] = by_atk[key]["names"].get(mon.name, 0) + 1
        if not by_atk:
            return
        # Show the group with highest achievable savings
        best_key = max(by_atk, key=lambda k: by_atk[k]["total_savings"])
        g = by_atk[best_key]
        names = [f"{n} x{c}" for n, c in g["names"].items()]
        if len(names) > 3:
            names = names[:3] + ["..."]
        names_str = ", ".join(names)
        lines.append(
            f"DEF tip: +{g['def_gap']} DEF makes {names_str} free; saves {g['total_savings']} HP"
        )

    def _append_hp_budget(self, lines: list, actions=None) -> None:
        """Show total damage of all remaining enemies vs available HP buffer.
        Warns the LLM when remaining fights exceed available HP (collect potions first).
        
        When goal=="boss" and actions is provided, shows boss-path-only cost (excludes optional
        enemies that aren't required to reach the boss), preventing misleading negative surplus.
        """
        from . import damage as dmg_mod
        from . import data as D
        from dataclasses import replace as dc_replace

        # Collect remaining monsters and items
        monsters_remaining = []
        total_potion_hp = 0
        stat_def = stat_atk = stat_mdef = 0
        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if self.gd.is_enemy(tile):
                    eid = self.gd.get_enemy_id(tile)
                    if eid:
                        monsters_remaining.append(self.gd.get_monster(eid))
                elif self.gd.is_item(tile):
                    item_id = self.gd.get_item_id(tile)
                    if item_id:
                        eff = self.gd.get_item_effect(item_id)
                        if "hp" in eff:
                            total_potion_hp += eff["hp"]
                        elif "def" in eff:
                            stat_def += eff["def"]
                        elif "atk" in eff:
                            stat_atk += eff["atk"]
                        elif "mdef" in eff:
                            stat_mdef += eff["mdef"]

        # For boss goal with current actions: compute boss-path-only cost to accurately convey
        # winnability (all-enemy budget falsely inflates cost with optional skippable enemies).
        if self.goal == "boss" and actions is not None:
            from ..game.types import ActionType as AT
            # Find boss monster on map for direct fight-cost calculation
            boss_mon = None
            boss_can_win_now = False
            for _by in range(self.floor.height):
                for _bx in range(self.floor.width):
                    if self.floor.map[_by][_bx] == 299 and (_bx, _by) not in self.removed:
                        eid = self.gd.get_enemy_id(299) or "enemy_299"
                        boss_mon = self.gd.get_monster(eid)
                        break
                if boss_mon:
                    break
            boss_cost = 0
            if boss_mon:
                boss_dmg_res = dmg_mod.calculate(self.hero, boss_mon)
                boss_can_win_now = boss_dmg_res.can_win
                if boss_can_win_now:
                    boss_cost = min(boss_dmg_res.total_damage, 999999)
            fight_actions = [a for a in actions if a.type == AT.FIGHT]
            boss_chain = [a for a in fight_actions if any(
                u.get("type") == "enemy" and "299" in u.get("label", "")
                for u in a.unlocks_tree
            )]
            # Any fight that doesn't unlock the boss chain AND isn't the boss itself is optional
            optional_fights = [
                a for a in fight_actions
                if a.monster_id != "enemy_299" and a not in boss_chain
            ]
            chain_cost = sum(a.total_damage for a in boss_chain)
            available = self.hero.hp + total_potion_hp
            if boss_can_win_now:
                boss_path_total = chain_cost + boss_cost
                boss_path_surplus = available - boss_path_total
                lines.append(
                    f"Boss-path HP budget: avail={available} need={boss_path_total} surplus={boss_path_surplus}"
                )
            else:
                boss_path_surplus = None
                lines.append(f"Boss-path HP budget: avail={available}; boss still unwinnable at current stats")
            if optional_fights:
                opt_total = sum(a.total_damage for a in optional_fights)
                lines.append(
                    f"Optional off-path fights: {len(optional_fights)} costing {opt_total} HP total"
                )
            if boss_path_surplus is None:
                lines.append("  Collect boss-path stats first; optional fights only burn HP.")
            elif boss_path_surplus < 0:
                lines.append("  Boss not yet winnable; collect more stats or HP first.")
            elif boss_path_surplus < 30:
                lines.append(f"  Tight margin: {boss_path_surplus} HP; skip all optional fights.")
            else:
                lines.append(f"  Boss is winnable with {boss_path_surplus} HP spare.")
            return  # Skip the generic all-enemy budget below

        # Cost at CURRENT stats — cap overflow values to prevent 999999999 from appearing
        current_cost_list = []
        for m in monsters_remaining:
            dmg = dmg_mod.calculate(self.hero, m).total_damage
            # Cap unwinnable fights to a high but readable value
            if dmg >= 999999999:
                current_cost_list.append(999999)  # Cap at 999999 to indicate "too high"
            else:
                current_cost_list.append(dmg)
        current_cost = sum(current_cost_list)

        # Cost at BEST stats (after collecting all remaining gems) — also capped
        best_hero = dc_replace(
            self.hero,
            def_=self.hero.def_ + stat_def,
            atk=self.hero.atk + stat_atk,
            mdef=self.hero.mdef + stat_mdef,
        )
        best_cost_list = []
        for m in monsters_remaining:
            dmg = dmg_mod.calculate(best_hero, m).total_damage
            if dmg >= 999999999:
                best_cost_list.append(999999)
            else:
                best_cost_list.append(dmg)
        best_cost = sum(best_cost_list)

        available = self.hero.hp + total_potion_hp
        surplus_best = available - best_cost
        lines.append(
            f"HP budget at max stats: avail={available} need={best_cost} surplus={surplus_best}"
        )
        if surplus_best < 0:
            lines.append("  Not winnable even after all gems.")
        elif surplus_best < self._initial_hp * 0.15:
            lines.append(f"  Tight margin: only {surplus_best} HP spare after all gems.")
        else:
            # Show readable current cost or warning if unwinnable
            if current_cost >= 999000:
                lines.append("  Current stats cannot damage some enemies; collect stats first.")
            else:
                lines.append(f"  Winnable after gems. Current-stats cost={current_cost}.")

    _KEY_COLOURS = ("yellow", "blue", "red")

    def _key_inventory(self) -> tuple[dict, dict]:
        """(keys lying on this floor, closed doors on this floor) per colour."""
        on_floor = {c: 0 for c in self._KEY_COLOURS}
        doors = {c: 0 for c in self._KEY_COLOURS}
        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if self.gd.is_item(tile):
                    eff = self.gd.get_item_effect(self.gd.get_item_id(tile)) or {}
                    for c in self._KEY_COLOURS:
                        on_floor[c] += eff.get(f"keys.{c}", 0)
                elif self.gd.is_door(tile):
                    dt = self.gd.get_door_type(tile)
                    if dt is not None and dt.value in doors:
                        doors[dt.value] += 1
        return on_floor, doors

    def _key_budget_line(self) -> str:
        """K1: keys are the one resource the annotations never priced (round 2: every residual
        simple/complex failure was a door choice). Pure counting — no door is recommended."""
        on_floor, doors = self._key_inventory()
        parts = []
        for c in self._KEY_COLOURS:
            have = getattr(self.hero.keys, c)
            if doors[c] == 0 and have == 0 and on_floor[c] == 0:
                continue
            total = have + on_floor[c]
            s = f"{c} {have} in hand + {on_floor[c]} on this floor = {total} for {doors[c]} closed {c} door(s)"
            if total < doors[c]:
                s += f" → at least {doors[c] - total} {c} door(s) will stay closed: every {c} door you open decides which"
            parts.append(s)
        return ("Key budget: " + "; ".join(parts)) if parts else ""

    def _keys_behind(self, action) -> dict:
        out = {c: 0 for c in self._KEY_COLOURS}
        for u in action.unlocks_tree or []:
            for c, n in (u.get("keys") or {}).items():
                out[c] = out.get(c, 0) + n
        return out

    def _region_keys(self, removed: set, exclude: set) -> tuple[set, dict, list]:
        """Flood from the hero through items and monsters (fight cost ignored), stopping at doors.
        Returns (entity positions reached, keys lying on newly reached tiles, newly exposed doors)."""
        reach = pf.find_reachable(
            self.floor.map, self.hero.x, self.hero.y, self.hero.keys, removed,
            stop_at_doors=True, height=self.floor.height, width=self.floor.width,
            pass_through_enemies=True, game_data=self.gd,
        )
        keys = {c: 0 for c in self._KEY_COLOURS}
        doors = []
        for pos, info in reach.items():
            if pos in exclude:
                continue
            if info["type"] == "item":
                eff = self.gd.get_item_effect(info["entity_id"]) or {}
                for c in self._KEY_COLOURS:
                    keys[c] += eff.get(f"keys.{c}", 0)
            elif info["type"] == "door" and info["door_type"].value in self._KEY_COLOURS:
                doors.append((pos, info["door_type"].value))
        return set(reach), keys, sorted(doors)

    def _key_hint(self, action) -> str:
        """K1/K2 per action: keys this action spends, the keys lying behind it (past its monsters,
        any depth, fight cost not counted), what the doors it exposes hold, and whether it spends the
        last key of a colour while other doors of that colour stay closed. Counting only."""
        if action.type == ActionType.OPEN_DOOR and action.door_type is not None and action.door_type.value in self._KEY_COLOURS:
            c = action.door_type.value
            have = getattr(self.hero.keys, c)
            base, _, _ = self._region_keys(set(self.removed), set())
            opened = set(self.removed) | {(action.x, action.y)}
            after, behind, exposed = self._region_keys(opened, base)
            fmt = lambda k: ", ".join(f"+{n} {col}" for col, n in k.items() if n) or "none"
            hand = {col: getattr(self.hero.keys, col) for col in self._KEY_COLOURS}
            hand[c] -= 1
            for col, n in behind.items():
                hand[col] += n
            s = f" → keys: uses 1 {c} ({c} {have}→{hand[c]} after collecting what is behind it); behind it: {fmt(behind)}"
            second = {col: 0 for col in self._KEY_COLOURS}
            ex_parts = []
            for pos, dc in exposed:
                pstr = f"({pos[0]},{pos[1]})"
                if hand[dc] <= 0:
                    ex_parts.append(f"{dc} door {pstr} (no {dc} key left for it)")
                    continue
                _, k2, _ = self._region_keys(opened | {pos}, after)
                for col, n in k2.items():
                    second[col] += n
                ex_parts.append(f"{dc} door {pstr} → {fmt(k2)}")
            if ex_parts:
                s += "; it exposes " + "; ".join(ex_parts)
            if have == 1 and behind.get(c, 0) == 0 and second.get(c, 0) == 0:
                _, doors = self._key_inventory()
                others = doors[c] - 1
                if others > 0:
                    s += (f"; this is your last {c} key and nothing behind it returns one — the other {others} "
                          f"closed {c} door(s) on this floor stay locked until you find another")
            if _boss_key_reserve():
                s += self._boss_reserve_hint(action, hand[c] , behind.get(c, 0))
            return s
        if action.type == ActionType.FIGHT and _fight_key_flood():
            return self._fight_key_flood_hint(action)
        gained = ", ".join(f"+{n} {col}" for col, n in self._keys_behind(action).items() if n)
        if gained:
            return f" → keys behind it (see tree): {gained}"
        return ""

    def _boss_route_doors(self) -> list[tuple[str, int, int]] | None:
        """Closed doors (colour, x, y) on the cheapest route from the hero to the boss, ordered by unwinnable fights,
        HP at current stats, doors, steps (as the tower's way-up route); None without a boss or a route."""
        import heapq
        f, gd = self.floor, self.gd
        target = next(((x, y) for y in range(f.height) for x in range(f.width)
                       if f.map[y][x] == 299 and (x, y) not in self.removed), None)
        if target is None:
            return None
        start, best, prev, costs = (self.hero.x, self.hero.y), {}, {}, {}

        def enter(x, y):
            if (x, y) in self.removed or (x, y) == target:
                return 0, 0, 0
            t = f.map[y][x]
            if gd.is_wall(t) or gd.is_npc(t):
                return None
            if gd.is_door(t):
                return 0, 0, 0 if gd.get_door_type(t) == DoorType.ICE else 1
            if gd.is_enemy(t):
                if (x, y) not in costs:
                    mon = gd.get_monster(gd.get_enemy_id(t))
                    r = dmg.calculate(self.hero, mon) if mon else None
                    costs[(x, y)] = (0, r.total_damage, 0) if r and r.total_damage < 999999999 else (1, 0, 0)
                return costs[(x, y)]
            if gd.is_ground(t) or gd.is_terrain(t) or gd.is_stairs(t) or gd.is_item(t):
                return 0, 0, 0
            return None

        best[start] = (0, 0, 0, 0)
        heap = [(0, 0, 0, 0, start)]
        while heap:
            u, hp, dr, st, (x, y) = heapq.heappop(heap)
            if (x, y) == target:
                break
            if best.get((x, y)) != (u, hp, dr, st):
                continue
            for dx, dy in pf.DIRECTIONS:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < f.width and 0 <= ny < f.height):
                    continue
                c = enter(nx, ny)
                if c is None:
                    continue
                key = (u + c[0], hp + c[1], dr + c[2], st + 1)
                if (nx, ny) not in best or key < best[(nx, ny)]:
                    best[(nx, ny)] = key
                    prev[(nx, ny)] = (x, y)
                    heapq.heappush(heap, (*key, (nx, ny)))
        if target not in best:
            return None
        doors, cur = [], target
        while cur != start:
            x, y = cur
            t = f.map[y][x]
            if cur not in self.removed and gd.is_door(t) and gd.get_door_type(t) != DoorType.ICE:
                doors.append((gd.get_door_type(t).value, x, y))
            cur = prev[cur]
        return list(reversed(doors))

    def _boss_reserve_hint(self, action, hand_after: int, behind: int) -> str:
        if getattr(self, "_boss_doors_cache", (None,))[0] != (self.turn, frozenset(self.removed), self.hero.x, self.hero.y):
            self._boss_doors_cache = ((self.turn, frozenset(self.removed), self.hero.x, self.hero.y), self._boss_route_doors())
        doors = self._boss_doors_cache[1]
        c = action.door_type.value
        if not doors:
            return ""
        need = [(x, y) for col, x, y in doors if col == c]
        if not need or (action.x, action.y) in need:
            return ""
        # keys you can still pick up without opening any door (past monsters); keys behind locked doors may be
        # unreachable once the key is spent (complex floor: the last yellow key lies behind (8,4))
        _, region, _ = self._region_keys(set(self.removed), set())
        rest = region.get(c, 0)
        if hand_after + rest >= len(need):
            return ""
        at = ", ".join(f"({x},{y})" for x, y in need)
        return (f"; not on the cheapest route to the boss: afterwards you have {hand_after} {c} key(s), {rest} more "
                f"reachable without opening a door, and that route goes through {len(need)} closed {c} door(s) at {at}")

    def _fight_key_flood_hint(self, action) -> str:
        """F-K3: keys that killing this monster opens up and the doors it exposes (priced one level
        deeper), independent of the lookahead depth. Monsters block here, since only this one dies."""
        def blocked(removed):
            return pf.find_reachable(self.floor.map, self.hero.x, self.hero.y, self.hero.keys, removed,
                                     stop_at_doors=True, height=self.floor.height, width=self.floor.width,
                                     pass_through_enemies=False, game_data=self.gd)
        before = blocked(set(self.removed))
        killed = set(self.removed) | {(action.x, action.y)}
        after = blocked(killed)
        keys = {c: 0 for c in self._KEY_COLOURS}
        exposed = []
        for pos, info in after.items():
            if pos in before:
                continue
            if info["type"] == "item":
                eff = self.gd.get_item_effect(info["entity_id"]) or {}
                for c in self._KEY_COLOURS:
                    keys[c] += eff.get(f"keys.{c}", 0)
            elif info["type"] == "door" and info["door_type"].value in self._KEY_COLOURS:
                exposed.append((pos, info["door_type"].value))
        fmt = lambda k: ", ".join(f"+{n} {col}" for col, n in k.items() if n) or "none"
        hand = {col: getattr(self.hero.keys, col) + keys[col] for col in self._KEY_COLOURS}
        base, _, _ = self._region_keys(killed, set())
        parts = []
        for pos, dc in sorted(exposed):
            pstr = f"({pos[0]},{pos[1]})"
            if hand[dc] <= 0:
                parts.append(f"{dc} door {pstr} (no {dc} key for it)")
                continue
            _, k2, _ = self._region_keys(killed | {pos}, base)
            parts.append(f"{dc} door {pstr} → {fmt(k2)} behind it")
        if not parts and not any(keys.values()):
            return ""
        s = f" → keys: behind this fight {fmt(keys)}"
        if parts:
            s += "; it exposes " + "; ".join(parts)
        return s

    def _alternative_route_tag(self, action) -> str:
        """`[ALTERNATIVE ROUTE — everything this opens is also opened by <B>; not needed while <B> is
        listed]` (strict superset) or `[SAME REGION as <B> — one of the two suffices]` (equal sets)."""
        other = action.alternative_route
        if getattr(action, "alternative_route_strict", False):
            return f"  [ALTERNATIVE ROUTE — everything this opens is also opened by \"{other}\" (which opens more); taking both pays twice for the same access]"
        return f"  [SAME REGION as \"{other}\" — both open exactly the same things; one of the two suffices]"

    def _format_unlocks_tree(self, action) -> str:
        """Render unlocks_tree in target format with → next fight: and → via [...] chains."""
        if not action.unlocks_tree:
            return ""
        # Separate enemies (gateway monsters) from reward unlocks
        enemies = [u for u in action.unlocks_tree if u["type"] == "enemy"]
        rewards = [u for u in action.unlocks_tree if u["type"] != "enemy"]

        # Group reward unlocks by via-chain
        direct = [u for u in rewards if not u["via"]]
        chained: dict[tuple, list] = {}
        for u in rewards:
            if u["via"]:
                key = tuple(u["via"])
                chained.setdefault(key, []).append(u)

        def _labels(items) -> str:
            counts: dict[str, int] = {}
            for u in items:
                counts[u["label"]] = counts.get(u["label"], 0) + 1
            return ", ".join(f"{lb} ×{n}" if n > 1 else lb for lb, n in counts.items())

        parts = []
        # "→ next fight:" line with all downstream enemies
        if enemies:
            enemy_strs = []
            for u in enemies:
                enemy_strs.append(u["label"])
            parts.append(f" → next fight: {', '.join(enemy_strs)}")
        # "→ unlocks:" for direct rewards
        if direct:
            parts.append(f" → unlocks: {_labels(direct)}")
        # "→ via [chain]: items" for chained rewards
        for chain, items in sorted(chained.items(), key=lambda kv: (len(kv[0]), kv[0])):
            via_str = " → ".join(chain)
            indent = " " * (1 + 2 * len(chain))
            parts.append(f"{indent}→ via [{via_str}]: {_labels(items)}")
        return "\n".join(parts)

    def _compute_remaining_stat_gems(self) -> tuple[int, int]:
        """Return (total_def, total_atk) from all uncollected stat items still on the map."""
        from . import data as D
        stat_def = stat_atk = 0
        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if (x, y) in self.removed:
                    continue
                tile = self.floor.map[y][x]
                if self.gd.is_item(tile):
                    item_id = self.gd.get_item_id(tile)
                    if item_id:
                        eff = self.gd.get_item_effect(item_id)
                        if "def" in eff:
                            stat_def += eff["def"]
                        if "atk" in eff:
                            stat_atk += eff["atk"]
        return stat_def, stat_atk

    def _lethal_gate_hint(self, mon) -> str:
        """` [WINNABLE at ATK≥X (+n) | or HP≥Y]` for a fight the hero currently loses."""
        probe = self.hero.copy()
        atk_need = None
        for extra in range(1, 401):
            probe.atk = self.hero.atk + extra
            if dmg.calculate(probe, mon).can_win:
                atk_need = probe.atk
                break
        probe.atk = self.hero.atk
        r = dmg.calculate(probe, mon)
        hp_need = r.total_damage + 1 if r.total_damage < 10 ** 8 else None
        bits = []
        if atk_need is not None:
            bits.append(f"ATK≥{atk_need} (+{atk_need - self.hero.atk})")
        if hp_need is not None:
            bits.append(f"HP≥{hp_need} at current stats")
        if not bits:
            return f" [needs ATK>{mon.def_} to deal damage]"
        return " [WINNABLE at " + " | or ".join(bits) + "]"

    def _stat_route(self, action) -> tuple[int, int, list[tuple[int, int]]]:
        """(+atk, +def, enemies that must die) for the stat gems this action exposes.

        The action itself counts as a gateway when it is a fight; doors cost no HP.
        """
        add_atk = add_def = 0
        gateways: list[tuple[int, int]] = []
        for u in action.unlocks_tree or []:
            if u["type"] != "item" or not (u.get("atk") or u.get("def")):
                continue
            add_atk += u.get("atk", 0)
            add_def += u.get("def", 0)
            for p in u.get("via_enemies") or []:
                pos = (p[0], p[1])
                if pos not in gateways:
                    gateways.append(pos)
        if action.type == ActionType.FIGHT and (add_atk or add_def):
            gateways.insert(0, (action.x, action.y))
        return add_atk, add_def, gateways

    def _kill_cost(self, positions: list[tuple[int, int]], hero) -> int | None:
        """HP to kill these monsters in order at fixed `hero` stats (None if one is unwinnable)."""
        total = 0
        for x, y in positions:
            tile = self.floor.map[y][x]
            if not self.gd.is_enemy(tile):
                continue
            mon = self.gd.get_monster(self.gd.get_enemy_id(tile))
            if mon is None:
                continue
            r = dmg.calculate(hero, mon)
            if not r.can_win:
                return None
            total += r.total_damage
        return total

    def _order_hint(self, action, actions: list) -> str:
        """Exact two-order comparison for a fight: is it cheaper to reach some stat gems first?

        Both orders pay for the same monsters, so the totals are comparable. Computed from the
        damage formula only — it prescribes nothing and names no fixed position.
        """
        if action.type != ActionType.FIGHT or not action.can_win:
            return ""
        mon = self.gd.get_monster(action.monster_id)
        if mon is None:
            return ""
        self_atk, self_def, _ = self._stat_route(action)
        best = None
        first = None
        for other in actions:
            if other is action or other.type not in (ActionType.FIGHT, ActionType.OPEN_DOOR):
                continue
            if other.type == ActionType.FIGHT and not other.can_win:
                continue
            if getattr(other, "is_dead_end", False):
                continue
            o_atk, o_def, route = self._stat_route(other)
            if not route or (o_atk == 0 and o_def == 0):
                continue
            if (action.x, action.y) in route:
                continue
            # D1 (T2, MT3 turn 24): never recommend an order whose first step is itself a fight the
            # prompt's own rule forbids (> 40 % of current HP). Efficiency without affordability
            # cost the tower run a 195-HP Skeleton at 56 % HP.
            if other.type == ActionType.FIGHT and other.damage_percent > hp_rule_pct():
                continue
            route_now = self._kill_cost(route, self.hero)
            if route_now is None:
                continue
            after_route = self.hero.copy()
            after_route.atk += o_atk
            after_route.def_ += o_def
            this_after = dmg.calculate(after_route, mon)
            if not this_after.can_win:
                continue
            after_this = self.hero.copy()
            after_this.atk += self_atk
            after_this.def_ += self_def
            route_later = self._kill_cost(route, after_this)
            if route_later is None:
                continue
            other_first = route_now + this_after.total_damage
            this_first = action.total_damage + route_later
            gain = this_first - other_first
            # Name the cheapest-to-reach route that still yields a gain (most actionable; the
            # biggest-gain route is often the most expensive one to walk).
            if gain >= 5 and (best is None or (route_now, -gain) < (best[6], -best[0])):
                gems = " ".join(s for s in (f"+{o_atk} ATK" if o_atk else "", f"+{o_def} DEF" if o_def else "") if s)
                best = (gain, other.label(), gems, other_first, this_first, this_after.total_damage, route_now)
            elif (gain <= -5 and (self_atk or self_def) and action.damage_percent <= hp_rule_pct()
                  and (first is None or (route_now, gain) < (first[4], first[0]))):
                # Round 5: without the 40 % guard this line told 9/10 35B runs to take the 46 % Bat at T4.
                first = (gain, other.label(), this_first, other_first, route_now)
        where = f" (this {action.name} at ({action.x},{action.y}))" if _order_two_sided() else ""
        if best is None:
            if first is not None and _order_two_sided():
                gain, label, this_first, other_first, _ = first
                return (f" → ORDER{where}: take this fight BEFORE \"{label}\" — this fight then that route: "
                        f"{this_first} HP; that route then this fight: {other_first} HP (saves {-gain})")
            return ""
        gain, label, gems, other_first, this_first, after_cost, route_now = best
        route_pct = round(100 * route_now / max(1, self.hero.hp))
        caveat = ""
        if route_now >= 0.6 * self.hero.hp:
            caveat = f" — but reaching those gems costs {route_now} HP ({route_pct}% of your HP) right now"
        return (f" → ORDER{where}: taking this fight now wastes {gain} HP — after \"{label}\" ({gems}; {route_now} HP of fighting to reach them) "
                f"it costs {after_cost} instead of {action.total_damage}; fight + route together: {other_first} instead of {this_first}{caveat}")

    def _stat_route_numbers(self, action, actions: list) -> tuple[str, int, int] | None:
        """(gems label, HP of fighting to reach the stat gems behind `action` incl. its own fight, HP they save
        on the other winnable fights listed now), or None if no stat gems lie behind it."""
        add_atk, add_def, route = self._stat_route(action)
        if add_atk <= 0 and add_def <= 0:
            return None
        reach = self._kill_cost(route, self.hero)
        if reach is None:
            return None
        boosted = self.hero.copy()
        boosted.atk += add_atk
        boosted.def_ += add_def
        saved = 0
        for other in actions:
            if other.type != ActionType.FIGHT or not other.can_win:
                continue
            if (other.x, other.y) in route:
                continue
            mon = self.gd.get_monster(other.monster_id)
            if mon is None:
                continue
            after = dmg.calculate(boosted, mon)
            if after.can_win:
                saved += max(0, other.total_damage - after.total_damage)
        gems = " ".join(s for s in (f"+{add_atk} ATK" if add_atk else "", f"+{add_def} DEF" if add_def else "") if s)
        return gems, reach, saved

    def _stat_value_hint(self, action, actions: list) -> str:
        """Net value of the stat gems behind this action: what they cost to reach vs what they save.

        Order matters on tight floors, and the saving alone is misleading — a route promising
        "+1 ATK +1 DEF, saves 155" behind three monsters can cost 198 HP to walk, while a cheaper
        route saves less for a fraction of the price. Computed, not scripted: no position is named.
        """
        nums = self._stat_route_numbers(action, actions)
        if nums is None:
            return ""
        gems, reach, saved = nums
        if saved <= 0 and reach <= 0:
            return ""
        net = saved - reach
        return (f" → stat gems behind it ({gems}): {reach} HP of fighting to reach them, "
                f"then they save {saved} HP on the other fights listed now → net {net:+d} HP")

    def _format_actions_bare(self, actions: list[Action]) -> str:
        """MOTA_BARE_OBS action list: what the player can do now and the exact fight damage."""
        from . import data as D
        lines = ["Available actions:"]
        for a in actions:
            if a.type == ActionType.FIGHT:
                mon = self.gd.get_monster(a.monster_id)
                spec = [self._SPECIAL_LABELS[s] for s in mon.specials if s in self._SPECIAL_LABELS]
                spec_str = f" [{','.join(spec)}]" if spec else ""
                if a.can_win:
                    res = f"damage={a.total_damage} hpAfter={a.hp_after}"
                else:
                    res = "you cannot win this fight now"
                lines.append(f"  {a.action_id}. [fight] {a.name} at ({a.x},{a.y}) — ATK={mon.atk} DEF={mon.def_} "
                             f"HP={mon.hp}{spec_str} — {res}")
            elif a.type == ActionType.COLLECT:
                lines.append(f"  {a.action_id}. [collect] {a.name} at ({a.x},{a.y})")
            elif a.type == ActionType.OPEN_DOOR:
                lines.append(f"  {a.action_id}. [open_door] {a.name} at ({a.x},{a.y})")
            elif a.type == ActionType.SHOP_BUY:
                unit = D.shop_unit(a.currency)
                lines.append(f"  {a.action_id}. [shop_buy] {a.name} — cost={a.money_cost}{unit}")
            elif a.type == ActionType.USE_STAIRS:
                lines.append(f"  {a.action_id}. [use_stairs] {a.name} at ({a.x},{a.y})")
        return "\n".join(lines)

    def format_actions(self, actions: list[Action]) -> str:
        """Format available actions for LLM consumption (target format)."""
        from dataclasses import replace as dc_replace
        # Precompute max achievable DEF/ATK from all uncollected stat items still on map.
        rem_def, rem_atk = self._compute_remaining_stat_gems()
        max_hero_def = self.hero.def_ + rem_def
        max_hero_atk = self.hero.atk + rem_atk
        max_hero = dc_replace(self.hero, def_=max_hero_def, atk=max_hero_atk)

        lines = ["Available actions:"]
        if _bare_obs():
            return self._format_actions_bare(actions)
        if not _compact_prompt():
            lines.extend(_ACTIONS_LEGEND)
        # Historical coupling: MOTA_DISABLE_OVERRIDES also hid lookahead/effCost/tree/stat hints
        # on FIGHT lines (doors kept theirs). That removes information, not control — C2
        # (2026-09-24) died 4/5 at a fight whose tree would have shown the guarded DEF gem.
        # MOTA_SUPPRESS_HINTS=0|1 now decides explicitly; unset keeps the old coupling.
        _suppress_hints = _hints_suppressed()
        for a in actions:
            if a.type == ActionType.FIGHT:
                risk = "LETHAL" if not a.can_win else (
                    "RISKY" if a.damage_percent > 30 else
                    "MODERATE" if a.damage_percent > 15 else "SAFE"
                )
                mon = self.gd.get_monster(a.monster_id)
                specials = mon.specials
                spec_labels = [self._SPECIAL_LABELS[s] for s in specials if s in self._SPECIAL_LABELS]

                # DEF threshold hint (verbose format)
                if 2 not in specials:  # not magic-atk
                    def_gap = mon.atk - self.hero.def_
                    if def_gap > 0:
                        threshold_str = f" [FREE if DEF≥{mon.atk}, need +{def_gap} more]"
                    else:
                        threshold_str = " [already immune: DEF≥monATK]"
                else:
                    threshold_str = f" [magic-atk] [magic-atk: DEF useless — only ATK+MDEF reduce cost]"
                if 11 in specials and mon.vampire > 0 and os.environ.get("MOTA_VAMPIRE_TAG") == "1":
                    # design 7: "already immune" was false for the MT7 White Warriors (25 % of current HP, DEF-proof)
                    threshold_str = (f" [vampire: takes {mon.vampire:.0%} of your current HP whatever your DEF, so it "
                                     f"costs less when your HP is lower]")

                # Damage percent
                dmg_pct = round(a.total_damage / max(1, self.hero.hp) * 100, 1)

                # Lookahead and effCost — stat value only (gems, keys, doors, stairs, shops);
                # potions are order-independent and listed separately.
                gw_cost = getattr(a, 'gateway_cost', 0)
                raw_la = getattr(a, 'stat_lookahead_raw', getattr(a, 'raw_lookahead', a.lookahead_value))
                la_val = getattr(a, 'stat_lookahead', a.lookahead_value)
                potion_hp = getattr(a, 'potion_hp', 0)
                net_la_str = None
                if os.environ.get("MOTA_EFFCOST_NET") == "1":
                    # Value = HP the stat gems behind it save on the fights listed now, minus the other fights on the
                    # way to them; keys, doors and item scores count 0 (the tower Skeleton at 92.6 % had effCost -315).
                    nums = self._stat_route_numbers(a, actions)
                    gw_cost = raw_la = 0
                    if nums is None:
                        la_val = 0
                    else:
                        _, reach, saved = nums
                        extra = reach - a.total_damage
                        la_val = max(0, saved - extra)
                        net_la_str = f"lookahead={la_val}(gems save {saved} - other fights to reach them {extra})"
                        gw_cost = extra if la_val == 0 else 0

                if _suppress_hints:
                    la_eff_str = ""
                else:
                    if net_la_str:
                        la_str = net_la_str
                    elif gw_cost:
                        la_str = f"lookahead={la_val}(raw={raw_la}-gw={gw_cost})"
                    elif la_val:
                        la_str = f"lookahead={la_val}"
                    else:
                        if raw_la and raw_la > 0:
                            la_str = f"lookahead=0(raw={raw_la}-gw={gw_cost})"
                        else:
                            la_str = "lookahead=0"

                    # effCost is only defined when the fight unlocks value (lookahead > 0).
                    # A gateway fight with zero net lookahead deliberately shows
                    # "effCost=None": every stored boss kill (Apr–Jun 2026) was produced
                    # with this text and the model reads None as "not recommended yet".
                    # Rendering a number here changed the semantics and dropped the
                    # simple-floor kill rate from 6/14 to 0/20 (2026-09-20).
                    effective_cost = a.total_damage - la_val if la_val else None
                    eff_str = f"effCost={effective_cost}" if effective_cost is not None else ""
                    potion_str = f" | +{potion_hp} HP potions behind it (collect any time)" if potion_hp else ""

                    # Build lookahead + effCost string
                    # When lookahead is 0 with no underlying value, omit entirely
                    # When there's a gateway breakdown, always show effCost (even None)
                    if gw_cost:
                        eff_display = f"effCost={effective_cost}" if effective_cost is not None else "effCost=None"
                        la_eff_str = f" {la_str} {eff_display}{potion_str}"
                    elif la_val:
                        la_eff_str = (f" {la_str} {eff_str}" if eff_str else f" {la_str}") + potion_str
                    elif raw_la and raw_la > 0:
                        la_eff_str = f" {la_str}{potion_str}"
                    else:
                        la_eff_str = potion_str

                # Min-cost at max stats (suppress when MOTA_DISABLE_OVERRIDES is set,
                # since an explicit strategy prompt manages fight order)
                deferred_str = ""
                if 2 not in specials and a.can_win and not _suppress_hints:
                    max_result = dmg.calculate(max_hero, mon)
                    min_cost = max_result.total_damage
                    saving = a.total_damage - min_cost
                    if saving >= 10:
                        deferred_str = (f" | min-cost={min_cost}@maxStats(ATK={max_hero_atk},DEF={max_hero_def}) "
                                        f"save={saving}HP — collect stat gems first")

                # Optional tag for boss floors (verbose)
                optional_tag = ""
                if self.goal == "boss" and a.monster_id != "enemy_299" and not a.unlocks_tree:
                    optional_tag = "  ⚡[OPTIONAL — NOT required for boss, skip to conserve HP]"
                elif getattr(a, "alternative_route", None) and not _suppress_hints:
                    optional_tag = self._alternative_route_tag(a)

                # Stat gate for LETHAL fights: the smallest ATK (at current HP) or HP (at current
                # stats) that flips the fight to winnable. Walkthrough 二 (Red Bat, MT8) is exactly
                # this: ATK 95→112 turns a 7739-HP fight into 1704. Without it neither the heuristic
                # nor the LLM can see that a few ATK purchases open the floor.
                gate_str = ""
                if not a.can_win and not _suppress_hints:
                    gate_str = self._lethal_gate_hint(mon)

                line = (
                    f"  {a.action_id}. [fight] {a.name} at ({a.x},{a.y}) "
                    f"— monATK={mon.atk} monDEF={mon.def_}{threshold_str} "
                    f"— damage={a.total_damage} ({dmg_pct}%) hpAfter={a.hp_after} [{risk}]{gate_str}"
                    f"{la_eff_str}{deferred_str}{optional_tag}"
                )
                if not _suppress_hints:
                    tree_str = self._format_unlocks_tree(a)
                    if tree_str:
                        line += "\n" + tree_str
                    sv = self._stat_value_hint(a, actions)
                    if sv:
                        line += "\n" + sv
                    oh = self._order_hint(a, actions)
                    if oh:
                        line += "\n" + oh
                    kh = self._key_hint(a)
                    if kh:
                        line += "\n" + kh
                lines.append(line)

            elif a.type == ActionType.COLLECT:
                lines.append(
                    f"  {a.action_id}. [collect] {a.name} at ({a.x},{a.y}) "
                    f"— tier={a.item_tier.value} score={a.item_score}"
                )
            elif a.type == ActionType.OPEN_DOOR:
                door_note = " [DEAD END - DO NOT OPEN]" if a.is_dead_end else ""
                gw_cost = getattr(a, 'gateway_cost', 0)
                raw_la = getattr(a, 'stat_lookahead_raw', getattr(a, 'raw_lookahead', a.lookahead_value))
                la_val = getattr(a, 'stat_lookahead', a.lookahead_value)
                potion_hp = getattr(a, 'potion_hp', 0)
                door_net = None
                if os.environ.get("MOTA_EFFCOST_NET") == "1":
                    nums = self._stat_route_numbers(a, actions)
                    raw_la = gw_cost = 0
                    la_val = 0 if nums is None else max(0, nums[2] - nums[1])
                    if nums is not None:
                        door_net = f" — net_lookahead={la_val}(gems save {nums[2]} - fights to reach them {nums[1]})"
                if door_net:
                    la_str = door_net
                elif la_val and gw_cost:
                    la_str = f" — net_lookahead={la_val}(raw={raw_la}-gw_cost={gw_cost})"
                elif la_val:
                    la_str = f" — net_lookahead={la_val}"
                elif raw_la and raw_la > 0 and gw_cost:
                    la_str = f" — net_lookahead=0(raw={raw_la}-gw_cost={gw_cost})"
                else:
                    la_str = ""
                if potion_hp and not a.is_dead_end:
                    la_str += f" | +{potion_hp} HP potions behind it (collect any time)"
                line = f"  {a.action_id}. [open_door] {a.name} at ({a.x},{a.y}){door_note}{la_str}"
                if not a.is_dead_end and getattr(a, "alternative_route", None) and not _suppress_hints:
                    line += self._alternative_route_tag(a)
                tree_str = self._format_unlocks_tree(a)
                if tree_str:
                    line += "\n" + tree_str
                sv = self._stat_value_hint(a, actions)
                if sv:
                    line += "\n" + sv
                if not a.is_dead_end and not _suppress_hints:
                    kh = self._key_hint(a)
                    if kh:
                        line += "\n" + kh
                lines.append(line)
            elif a.type == ActionType.SHOP_BUY:
                unit = D.shop_unit(a.currency)
                short = D.hero_balance(self.hero, a.currency)
                if a.can_afford:
                    afford_tag = ""
                elif a.money_cost > short:
                    afford_tag = f" [LOCKED — need {a.money_cost - short}{unit} more]"
                else:
                    afford_tag = " [LOCKED — no such key to sell]"
                lines.append(
                    f"  {a.action_id}. [shop_buy] {a.name} — cost={a.money_cost}{unit}{afford_tag}"
                )
            elif a.type == ActionType.USE_STAIRS:
                lines.append(
                    f"  {a.action_id}. [use_stairs] {a.name} at ({a.x},{a.y})"
                )
        return "\n".join(lines)
