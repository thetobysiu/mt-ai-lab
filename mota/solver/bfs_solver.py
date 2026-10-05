"""
BFS state-space solver for MOTA floors.

Ports the reference Java BFS AI (magic-tower-AI/AI/src/Graph.java) to Python,
reusing the existing mota.game engine (GameState, pathfinder, damage calculator).

The solver finds the optimal action sequence (maximising remaining HP) for a
single floor by exploring all meaningful orderings of fights, door openings,
and item pickups via a priority-queue BFS with hash-based pruning.

Key design decisions mirroring the reference AI:
  - Priority queue orders by (decision_count ASC, hero_hp DESC)
  - After each decision, greedily collect all free items and zero-cost monsters
  - States are hashed by (frozenset(removed), hero_stats_tuple) for pruning
  - Dominated states (same visited set, <= HP) are discarded
"""
from __future__ import annotations

import copy
import heapq
import logging
from dataclasses import dataclass, field

from ..game.types import Hero, Action, ActionType, FloorData, DoorType, ItemTier
from ..game.state import GameState
from ..game import damage as dmg
from ..game.data import GameData, DEFAULT_GAME_DATA

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Solver state
# ---------------------------------------------------------------------------

@dataclass
class SolverState:
    """Immutable snapshot of the game at one BFS node."""
    hero: Hero
    removed: frozenset[tuple[int, int]]
    route: list[Action]   # decisions taken so far (not free pickups)
    decisions: int        # len(route), cached for priority
    shop_purchases: dict[str, list[str]] = field(default_factory=dict)

    # For priority queue ordering: (decisions, -hp)
    def __lt__(self, other: SolverState) -> bool:
        if self.decisions != other.decisions:
            return self.decisions < other.decisions
        return self.hero.hp > other.hero.hp   # prefer higher HP

    def state_hash(self) -> tuple:
        """Hash for pruning: same removed set + same-or-worse stats → dominated."""
        return (
            self.removed,
            self.hero.hp,
            self.hero.atk,
            self.hero.def_,
            self.hero.mdef,
            self.hero.money,
            self.hero.keys.yellow,
            self.hero.keys.blue,
            self.hero.keys.red,
        )

    def prune_key(self) -> tuple:
        """Key for dominance check: same visited set → compare HP."""
        return self.removed


# ---------------------------------------------------------------------------
# BFS Solver
# ---------------------------------------------------------------------------

class BFSSolver:
    """
    State-space BFS solver for a single MOTA floor.

    Usage:
        solver = BFSSolver(floor, hero)
        result = solver.solve()
        print(result.route)      # list[Action]
        print(result.hero.hp)    # remaining HP
    """

    def __init__(
        self,
        floor: FloorData,
        hero: Hero,
        game_data: GameData | None = None,
        max_decisions: int = 45,
        max_states: int = 1_000_000,
        goal: str = "clear_all_enemies",
        initial_removed: set[tuple[int, int]] | None = None,
    ):
        self.floor = floor
        self.initial_hero = hero.copy()
        self.gd = game_data or DEFAULT_GAME_DATA
        self.max_decisions = max_decisions
        self.max_states = max_states
        self.goal = goal
        self.initial_removed = initial_removed or set()

        # Statistics
        self.states_explored = 0
        self.states_pruned = 0

    def solve(self) -> SolverState | None:
        """
        Run BFS and return the best terminal state (highest HP), or None if
        no solution found.
        """
        # Build initial state: greedily collect free items first
        init_hero = self.initial_hero.copy()
        init_removed: set[tuple[int, int]] = set(self.initial_removed)
        init_shop: dict[str, list[str]] = {}

        self._eat_items(init_hero, init_removed, init_shop)

        start = SolverState(
            hero=init_hero,
            removed=frozenset(init_removed),
            route=[],
            decisions=0,
            shop_purchases=copy.deepcopy(init_shop),
        )

        # Priority queue: (decisions, -hp, state)
        pq: list[SolverState] = [start]
        heapq.heapify(pq)

        # Pruning: prune_key (removed set) -> best HP seen
        best_hp: dict[frozenset, int] = {start.removed: start.hero.hp}

        # Mirroring Java shouldStop() semantics:
        #   best_goal_terminal — state where the goal was truly reached (boss killed /
        #     all enemies cleared).  Always preferred over fallback states.
        #   best_fallback_terminal — best HP among dead-end states (no actions, hero
        #     stuck) and decision-limit exceeded states.  Returned only when no true
        #     goal terminal was found (e.g., floor is unsolvable).
        # This prevents a high-HP dead-end state (boss alive, fight would kill hero)
        # from outcompeting a low-HP but goal-reached state (boss killed, HP=13).
        # Java silently drops dead-end states; it only records answer on shouldStop().
        best_goal_terminal: SolverState | None = None
        best_fallback_terminal: SolverState | None = None

        def _update_goal(s: SolverState) -> None:
            nonlocal best_goal_terminal
            if best_goal_terminal is None or s.hero.hp > best_goal_terminal.hero.hp:
                best_goal_terminal = s

        def _update_fallback(s: SolverState) -> None:
            nonlocal best_fallback_terminal
            if best_fallback_terminal is None or s.hero.hp > best_fallback_terminal.hero.hp:
                best_fallback_terminal = s

        while pq:
            if self.states_explored >= self.max_states:
                log.warning("BFS hit state limit (%d), returning best so far",
                            self.max_states)
                break

            state = heapq.heappop(pq)
            self.states_explored += 1

            if self.states_explored % 100_000 == 0:
                log.info("BFS progress: %d states explored, %d pruned, queue=%d",
                         self.states_explored, self.states_pruned, len(pq))

            # Java cnt>45 fallback: record but don't commit as a goal-reached result
            if state.decisions > self.max_decisions:
                _update_fallback(state)
                continue

            if self._is_goal_reached(state):
                _update_goal(state)
                continue

            # Enumerate available actions from this state
            gs = self._build_gamestate(state)
            actions = gs.get_actions(annotate=False)

            if not actions:
                # Dead end: hero stuck, no valid moves — silently drop (Java behaviour).
                # Record only as fallback in case no goal terminal is ever found.
                _update_fallback(state)
                continue

            any_child = False
            for action in actions:
                new_state = self._apply_action(state, action)
                if new_state is None:
                    continue  # hero died or invalid (e.g., no key)
                any_child = True

                # Dominance pruning
                pk = new_state.prune_key()
                prev_best = best_hp.get(pk, -1)
                if new_state.hero.hp <= prev_best:
                    self.states_pruned += 1
                    continue

                best_hp[pk] = new_state.hero.hp
                heapq.heappush(pq, new_state)

            if not any_child:
                # All children killed hero or were invalid — dead end, same logic above.
                _update_fallback(state)

        best_terminal = best_goal_terminal if best_goal_terminal is not None else best_fallback_terminal
        if best_terminal:
            best_terminal.goal_reached = (best_goal_terminal is not None)
            log.info(
                "BFS complete: %d states explored, %d pruned, "
                "best HP=%d after %d decisions (goal_reached=%s)",
                self.states_explored, self.states_pruned,
                best_terminal.hero.hp, best_terminal.decisions,
                best_terminal.goal_reached,
            )
        else:
            log.warning("BFS found no solution")

        return best_terminal

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_gamestate(self, state: SolverState) -> GameState:
        """Create a GameState from solver state for action enumeration."""
        return GameState(
            floor=self.floor,
            hero=state.hero.copy(),
            goal=self.goal,
            game_data=self.gd,
            lookahead_depth=0,   # no lookahead needed for solver
            _removed=set(state.removed),
        )

    def _apply_action(self, state: SolverState, action: Action) -> SolverState | None:
        """
        Apply an action to a solver state, returning the new state or None if
        the hero dies or the action is invalid.
        """
        hero = state.hero.copy()
        removed = set(state.removed)
        shop_purchases = copy.deepcopy(state.shop_purchases)

        # Apply action effects
        if action.type == ActionType.FIGHT:
            monster = self.gd.get_monster(action.monster_id)
            result = dmg.calculate(hero, monster)
            if not result.can_win:
                return None
            hero.hp = result.hp_after
            hero.money += monster.money
            hero.exp += monster.exp
            removed.add((action.x, action.y))
            hero.x = action.x
            hero.y = action.y

        elif action.type == ActionType.COLLECT:
            effect = self.gd.get_item_effect(action.item_id)
            self._apply_item_effect(hero, effect)
            removed.add((action.x, action.y))
            hero.x = action.x
            hero.y = action.y

        elif action.type == ActionType.OPEN_DOOR:
            if not action.door_type:
                return None
            if not hero.keys.has_key(action.door_type):
                return None
            hero.keys.use_key(action.door_type)
            removed.add((action.x, action.y))
            hero.x = action.x
            hero.y = action.y

        elif action.type == ActionType.USE_STAIRS:
            hero.x = action.x
            hero.y = action.y

        elif action.type == ActionType.SHOP_BUY:
            if hero.money < action.money_cost:
                return None
            hero.money -= action.money_cost
            for stat, val in action.stat_changes.items():
                if stat == "hp":
                    hero.hp += val
                elif stat == "atk":
                    hero.atk += val
                elif stat == "def":
                    hero.def_ += val
                elif stat == "mdef":
                    hero.mdef += val
            hero.x = action.x
            hero.y = action.y
            coord_key = f"{action.x},{action.y}"
            shop_purchases.setdefault(coord_key, []).append(action.shop_choice)

        else:
            return None

        if hero.hp <= 0:
            return None

        # Auto-collect items along the path (items hero walks over)
        for (px, py) in action.path:
            if (px, py) not in removed:
                tile = self.floor.map[py][px]
                from ..game import data as D
                if D.is_item(tile):
                    item_id = D.TILE_ITEMS.get(tile)
                    if item_id:
                        effect = self.gd.get_item_effect(item_id)
                        self._apply_item_effect(hero, effect)
                        removed.add((px, py))

        # Greedy: eat all free items and zero-cost monsters
        self._eat_items(hero, removed, shop_purchases)

        route = state.route + [action]

        return SolverState(
            hero=hero,
            removed=frozenset(removed),
            route=route,
            decisions=state.decisions + 1,
            shop_purchases=shop_purchases,
        )

    def _eat_items(
        self,
        hero: Hero,
        removed: set[tuple[int, int]],
        shop_purchases: dict[str, list[str]],
    ) -> None:
        """
        Greedily collect all reachable free items and zero-cost monsters.
        Mirrors reference AI's eatItem() + auto-shop loop.
        """
        from ..game import pathfinder as pf
        from ..game import data as D

        changed = True
        while changed:
            changed = False
            reachable = pf.find_reachable(
                grid=self.floor.map,
                start_x=hero.x,
                start_y=hero.y,
                keys=hero.keys,
                removed=removed,
                stop_at_doors=True,
                height=self.floor.height,
                width=self.floor.width,
                game_data=self.gd,
            )

            for (x, y), info in reachable.items():
                if not info["accessible"]:
                    continue
                if (x, y) in removed:
                    continue

                if info["type"] == "item":
                    item_id = info["entity_id"]
                    effect = self.gd.get_item_effect(item_id)
                    self._apply_item_effect(hero, effect)
                    removed.add((x, y))
                    hero.x = x
                    hero.y = y
                    changed = True
                    break  # restart scan after each collect

                if info["type"] == "enemy":
                    monster = self.gd.get_monster(info["entity_id"])
                    result = dmg.calculate(hero, monster)
                    if result.can_win and result.total_damage == 0:
                        # Zero-cost fight = free money/exp
                        hero.hp = result.hp_after
                        hero.money += monster.money
                        hero.exp += monster.exp
                        removed.add((x, y))
                        hero.x = x
                        hero.y = y
                        changed = True
                        break

        # Auto-shop: spend gold at accessible shops (buy ATK then DEF)
        self._auto_shop(hero, removed, shop_purchases)

    def _auto_shop(
        self,
        hero: Hero,
        removed: set[tuple[int, int]],
        shop_purchases: dict[str, list[str]],
    ) -> None:
        """Buy stats at accessible shops. Prioritise DEF (threshold-aware), then ATK."""
        if not self._has_shops():
            return
        from ..game import pathfinder as pf

        reachable = pf.find_reachable(
            grid=self.floor.map,
            start_x=hero.x,
            start_y=hero.y,
            keys=hero.keys,
            removed=removed,
            stop_at_doors=True,
            height=self.floor.height,
            width=self.floor.width,
            game_data=self.gd,
        )

        for (x, y), info in reachable.items():
            if info["type"] != "npc" or not info["accessible"]:
                continue
            coord_key = f"{x},{y}"
            gs_floor = self.floor
            if coord_key not in gs_floor.events:
                continue
            for evt in gs_floor.events[coord_key]:
                if not isinstance(evt, dict) or evt.get("type") != "openShop":
                    continue
                shop_id = evt["id"]
                shops = self.gd.get_shops()
                shop = shops.get(shop_id)
                if not shop:
                    continue

                # Buy DEF first, then ATK, skip HP (reference AI strategy)
                buy_order = ["def", "atk"]
                purchased = True
                while purchased:
                    purchased = False
                    for choice_id in buy_order:
                        choice = next((c for c in shop["choices"] if c["id"] == choice_id), None)
                        if choice and hero.money >= shop["cost"]:
                            hero.money -= shop["cost"]
                            for stat, val in choice["changes"].items():
                                if stat == "hp":
                                    hero.hp += val
                                elif stat == "atk":
                                    hero.atk += val
                                elif stat == "def":
                                    hero.def_ += val
                                elif stat == "mdef":
                                    hero.mdef += val
                            shop_purchases.setdefault(coord_key, []).append(choice_id)
                            purchased = True
                            break  # restart buy loop (price may have changed)

    def _has_shops(self) -> bool:
        if not hasattr(self, "_shops_cached"):
            self._shops_cached = any(isinstance(e, dict) and e.get("type") == "openShop"
                                     for evts in self.floor.events.values() for e in evts)
        return self._shops_cached

    def _is_goal_reached(self, state: SolverState) -> bool:
        """Check if the solver goal is met."""
        if self.goal == "clear_all_enemies":
            for y in range(self.floor.height):
                for x in range(self.floor.width):
                    if (x, y) not in state.removed and self.gd.is_enemy(self.floor.map[y][x]):
                        return False
            return True
        elif self.goal == "boss":
            # Mirror Java shouldStop(): terminate as soon as the boss tile (299) is killed.
            # The boss is the last fight — like Java, we stop immediately on its removal.
            for y in range(self.floor.height):
                for x in range(self.floor.width):
                    if self.floor.map[y][x] == 299 and (x, y) in state.removed:
                        return True
            return False
        elif self.goal == "stairs":
            if state.route:
                last = state.route[-1]
                return last.type == ActionType.USE_STAIRS
        return False

    @staticmethod
    def _apply_item_effect(hero: Hero, effect: dict) -> None:
        """Apply an item effect dict to a hero."""
        if "hp" in effect:
            hero.hp += effect["hp"]
        if "atk" in effect:
            hero.atk += effect["atk"]
        if "def" in effect:
            hero.def_ += effect["def"]
        if "mdef" in effect:
            hero.mdef += effect["mdef"]
        if "money" in effect:
            hero.money += effect["money"]
        if "keys.yellow" in effect:
            hero.keys.yellow += effect["keys.yellow"]
        if "keys.blue" in effect:
            hero.keys.blue += effect["keys.blue"]
        if "keys.red" in effect:
            hero.keys.red += effect["keys.red"]


# ---------------------------------------------------------------------------
# POI Graph Extractor
# ---------------------------------------------------------------------------

@dataclass
class POINode:
    """A node in the Point of Interest look-ahead graph."""
    node_id: str             # e.g. "fight_greenSlime_3_4"
    action_type: str         # fight | collect | open_door | shop_buy | use_stairs
    target_name: str         # e.g. "绿头怪" or "Red Gem (+3 ATK)"
    x: int
    y: int
    hp_cost: int             # damage taken (0 for items/stairs)
    hp_after: int            # hero HP after this action
    gold_gain: int           # money earned (fights)
    stat_changes: dict       # {"atk": +3, "def": +10, ...}
    items_unlocked: list[str]  # labels of items that become accessible
    children: list[POINode] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to JSON-serialisable dict."""
        d = {
            "id": self.node_id,
            "action": self.action_type,
            "target": self.target_name,
            "pos": [self.x, self.y],
            "hp_cost": self.hp_cost,
            "hp_after": self.hp_after,
        }
        if self.gold_gain:
            d["gold_gain"] = self.gold_gain
        if self.stat_changes:
            d["stat_changes"] = self.stat_changes
        if self.items_unlocked:
            d["unlocks"] = self.items_unlocked
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


def extract_poi_graph(
    floor: FloorData,
    hero: Hero,
    removed: set[tuple[int, int]] | None = None,
    game_data: GameData | None = None,
    depth: int = 2,
    top_k: int = 3,
) -> list[POINode]:
    """
    Extract a pruned Point of Interest look-ahead graph from the current state.

    For each available action (depth 0), simulates it, then enumerates the next
    actions (depth 1), and so on up to `depth`. Only the top-k actions per level
    (by net value = lookahead_value - damage) are kept.

    Returns a list of POINode trees (depth-0 roots).
    """
    gd = game_data or DEFAULT_GAME_DATA
    removed = removed or set()

    gs = GameState(
        floor=floor,
        hero=hero.copy(),
        goal="clear_all_enemies",
        game_data=gd,
        lookahead_depth=0,
        _removed=removed,
    )
    actions = gs.get_actions()

    # Score and sort actions for top-k selection
    scored = _score_actions(actions, hero)
    scored.sort(key=lambda x: x[0], reverse=True)

    roots: list[POINode] = []
    for _, action in scored[:top_k]:
        node = _action_to_poi_node(action, hero, gd)

        if depth > 1:
            # Simulate this action and get next-level actions
            child_hero, child_removed = _simulate_action(
                floor, hero, removed, action, gd
            )
            if child_hero and child_hero.hp > 0:
                node.children = _expand_children(
                    floor, child_hero, child_removed, gd,
                    current_depth=1, max_depth=depth, top_k=top_k,
                )

        roots.append(node)

    return roots


def _score_actions(actions: list[Action], hero: Hero) -> list[tuple[float, Action]]:
    """Score actions for pruning. Higher = more promising."""
    scored = []
    for a in actions:
        if a.type == ActionType.FIGHT:
            if not a.can_win:
                continue
            # Net value: items behind this monster minus damage cost
            value = a.lookahead_value - a.total_damage
            scored.append((value, a))
        elif a.type == ActionType.COLLECT:
            scored.append((a.item_score * 10 + a.lookahead_value, a))
        elif a.type == ActionType.OPEN_DOOR:
            if a.is_dead_end:
                scored.append((-100, a))
            else:
                scored.append((a.lookahead_value + 50, a))
        elif a.type == ActionType.SHOP_BUY:
            scored.append((200, a))
        elif a.type == ActionType.USE_STAIRS:
            scored.append((-50, a))  # stairs last
        else:
            scored.append((0, a))
    return scored


def _action_to_poi_node(action: Action, hero: Hero, gd: GameData) -> POINode:
    """Convert an Action to a POINode."""
    hp_cost = 0
    gold_gain = 0
    stat_changes = {}
    hp_after = hero.hp

    if action.type == ActionType.FIGHT:
        hp_cost = action.total_damage
        hp_after = action.hp_after
        monster = gd.get_monster(action.monster_id)
        gold_gain = monster.money
    elif action.type == ActionType.COLLECT:
        effect = gd.get_item_effect(action.item_id)
        for k, v in effect.items():
            if k in ("tier", "score", "name"):
                continue
            if k.startswith("keys."):
                stat_changes[k] = v
            elif k in ("hp", "atk", "def", "mdef", "money"):
                stat_changes[k] = v
                if k == "hp":
                    hp_after = hero.hp + v
    elif action.type == ActionType.OPEN_DOOR:
        stat_changes = {f"keys.{action.door_type.value}": -1} if action.door_type else {}
    elif action.type == ActionType.SHOP_BUY:
        stat_changes = dict(action.stat_changes)
        stat_changes["money"] = -action.money_cost
        for k, v in action.stat_changes.items():
            if k == "hp":
                hp_after = hero.hp + v

    node_id = f"{action.type.value}_{action.name}_{action.x}_{action.y}".replace(" ", "_")

    return POINode(
        node_id=node_id,
        action_type=action.type.value,
        target_name=action.name,
        x=action.x,
        y=action.y,
        hp_cost=hp_cost,
        hp_after=hp_after,
        gold_gain=gold_gain,
        stat_changes=stat_changes,
        items_unlocked=list(action.unlocks_items) if action.unlocks_items else [],
    )


def _simulate_action(
    floor: FloorData,
    hero: Hero,
    removed: set[tuple[int, int]],
    action: Action,
    gd: GameData,
) -> tuple[Hero | None, set[tuple[int, int]]]:
    """
    Simulate an action returning (new_hero, new_removed). Returns (None, ...)
    if the action kills the hero.
    """
    gs = GameState(
        floor=floor,
        hero=hero.copy(),
        goal="clear_all_enemies",
        game_data=gd,
        lookahead_depth=0,
        _removed=set(removed),
    )
    try:
        gs.apply_action(action)
    except (ValueError, KeyError):
        return None, removed
    if gs.hero.hp <= 0:
        return None, removed
    return gs.hero, gs.removed


def _expand_children(
    floor: FloorData,
    hero: Hero,
    removed: set[tuple[int, int]],
    gd: GameData,
    current_depth: int,
    max_depth: int,
    top_k: int,
) -> list[POINode]:
    """Recursively expand child POI nodes."""
    gs = GameState(
        floor=floor,
        hero=hero.copy(),
        goal="clear_all_enemies",
        game_data=gd,
        lookahead_depth=0,
        _removed=removed,
    )
    actions = gs.get_actions()
    scored = _score_actions(actions, hero)
    scored.sort(key=lambda x: x[0], reverse=True)

    children: list[POINode] = []
    for _, action in scored[:top_k]:
        node = _action_to_poi_node(action, hero, gd)

        if current_depth + 1 < max_depth:
            child_hero, child_removed = _simulate_action(floor, hero, removed, action, gd)
            if child_hero and child_hero.hp > 0:
                node.children = _expand_children(
                    floor, child_hero, child_removed, gd,
                    current_depth + 1, max_depth, top_k,
                )

        children.append(node)

    return children
