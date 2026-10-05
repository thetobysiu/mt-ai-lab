"""
multi_floor.py — Multi-floor game engine for the MOTA agent.

Orchestrates sequential floor traversal across a range of floors while:
  - Maintaining per-floor removed entity sets (so returning to a floor
    preserves what you already cleared).
  - Tracking deferred locked doors from previous floors (doors that
    couldn't be opened due to missing keys) and surfacing them as
    RETURN_TO_FLOOR actions once the hero has the right keys.
  - Delegating per-turn in-floor mechanics to the existing GameState engine.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .types import (
    Action, ActionType, DeferredDoor, DoorType, FloorData, Hero, ItemTier, Keys, StepTrace,
)
from .state import GameState, hp_rule_pct, key_purchase_hidden
from .data import GameData, DEFAULT_GAME_DATA, shop_unit
from . import pathfinder as pf
from . import data as D
from . import damage as dmg_mod


def _event_way() -> bool:
    return os.environ.get("MOTA_EVENT_WAY") == "1"


class MultiFloorGame:
    """
    Multi-floor game manager. Holds the aggregate hero state and delegates
    per-turn actions to single-floor GameState instances.

    Lifecycle:
        game = MultiFloorGame(floors, hero)
        while not game.goal_reached and not game.failed:
            actions = game.get_actions()
            game.apply_action(chosen)
    """

    def __init__(
        self,
        floors: list[FloorData],
        hero: Hero,
        game_data: GameData | None = None,
        lookahead_depth: int | None = None,
        max_turns_per_floor: int = 300,
        max_total_turns: int = 3000,
        initial_removed: dict[int, set[tuple[int, int]]] | None = None,
    ):
        if not floors:
            raise ValueError("floors list must not be empty")

        self.floors = floors
        self.hero = hero
        self.gd = game_data or DEFAULT_GAME_DATA
        self.lookahead_depth = lookahead_depth
        self.max_turns_per_floor = max_turns_per_floor
        self.max_total_turns = max_total_turns

        # Per-floor removed sets — keyed by floor index
        self.per_floor_removed: dict[int, set[tuple[int, int]]] = {
            i: set() for i in range(len(floors))
        }
        # Merge any pre-seeded removed entities (e.g. MT0 fairy NPC)
        if initial_removed:
            for idx, positions in initial_removed.items():
                if idx in self.per_floor_removed:
                    self.per_floor_removed[idx].update(positions)

        # Deferred locked doors from floors we've visited but couldn't fully clear
        self.deferred_doors: list[DeferredDoor] = []

        # Global shops: once a shop is discovered on any floor, it stays available
        # everywhere. Each entry: {shop_id, floor_id, cost, choices, x, y, name}
        self.global_shops: list[dict] = []

        self.current_floor_idx: int = 0
        self.total_turns: int = 0
        self.visited_floor_idx: set[int] = {0}  # floors the hero has stood on (scouting rule)

        # Overall states
        self.goal_reached: bool = False
        self.failed: bool = False
        self.failure_reason: str = ""
        # Revisit signatures already taken (see _build_revisit_actions)
        self._tried_revisits: set[tuple] = set()
        # (floor, x, y, atk, def) of > 40 % fights already replaced once by the HP floor
        self._hp_floor_gated: set[tuple] = set()
        # MOTA_TOWER_FIDELITY: NPC events already triggered (floor id, x, y) and whether the Cross was handed in
        self._events_done: set[tuple[str, int, int]] = set()
        self._event_hides: dict[tuple[str, int, int], list[tuple[str, list[tuple[int, int]]]]] = {}
        self.cross_given = False
        self._seals: list[dict] = []
        # Tiles that start disabled in the game data ("enable": false) and the events that reveal them (2026-10-04)
        self._hidden: dict[tuple[int, int, int], int] = {}
        self._reveal_reason: dict[tuple[int, int, int], str] = {}
        self._event_shows: dict[tuple[str, int, int], list[tuple[str, list[tuple[int, int]]]]] = {}
        self._cross_shows: list[tuple[str, list[tuple[int, int]]]] = []
        self._items_used: set[str] = set()
        if self.fidelity_on():
            self._init_fidelity_tiles()

        # History across all floors
        self.history: list[StepTrace] = []

        # Track which floor transitions happened for logging
        self.floor_transitions: list[dict] = []

        # Scan the starting floor for already-inaccessible doors to defer
        self._scan_and_defer_doors(self.current_floor_idx)

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    @property
    def current_floor(self) -> FloorData:
        return self.floors[self.current_floor_idx]

    @property
    def is_last_floor(self) -> bool:
        return self.current_floor_idx == len(self.floors) - 1

    def next_floor_unvisited(self) -> bool:
        return not self.is_last_floor and (self.current_floor_idx + 1) not in self.visited_floor_idx

    def mechanical_action(self, actions: list[Action]) -> tuple[Action, str] | None:
        """Engine-side assists that need no judgement (user rules 2026-09-23), in this order:
        collect a stat item / key (potions only if MOTA_POTIONS_ON_DEMAND is unset), fight a
        monster that costs 0 HP, take the up-staircase when the next floor has never been seen
        (scout before spending here). Returns (action, reason) or None.
        """
        import os
        from .types import ItemTier
        on_demand = os.environ.get("MOTA_POTIONS_ON_DEMAND", "").lower() in ("1", "true", "yes")
        collects = [a for a in actions if a.type == ActionType.COLLECT
                    and not (on_demand and a.item_tier == ItemTier.HP)
                    and not (a.remote or a).money_cost  # a trade spends gold/EXP: a decision
                    and getattr(a.remote or a, "item_id", None) != "superPotion"]  # doubling HP: timing is a decision
        if collects:
            return max(collects, key=lambda a: a.item_score), "auto-collect"
        if self.fidelity_on():  # user 2026-10-02: an ice gate needs no key and only frees the way, like an item
            ice = [a for a in actions if a.type == ActionType.OPEN_DOOR and a.door_type == DoorType.ICE]
            if ice:
                return min(ice, key=lambda a: a.path_steps), "auto-open (ice gate, no key)"
        free = [a for a in actions if a.type == ActionType.FIGHT and a.can_win and a.total_damage == 0]
        if free:
            return min(free, key=lambda a: a.path_steps), "auto-fight (0 HP)"
        if self.next_floor_unvisited():
            stairs = next((a for a in actions if a.type == ActionType.USE_STAIRS), None)
            if stairs is not None:
                return stairs, "auto-scout (next floor unvisited)"
        scout = next((a for a in actions if a.remote is not None and a.remote.type == ActionType.USE_STAIRS), None)
        if scout is not None:
            return scout, "auto-scout (next floor unvisited)"
        return None

    @staticmethod
    def remote_actions_on() -> bool:
        """User 2026-10-01: stairs are travel, not a decision. Actions on every visited floor are offered
        directly (walking there is free); stairs only appear to scout an unvisited floor."""
        import os
        return os.environ.get("MOTA_REMOTE_ACTIONS") == "1"

    def get_actions(self) -> list[Action]:
        """
        Return all actions available on the current floor, plus any
        RETURN_TO_FLOOR actions for now-openable deferred doors,
        plus global shop buys from previously discovered shops.
        """
        state = self._make_state()
        actions = state.get_actions()

        # Remove USE_STAIRS upFloor if on the last floor (stairs means goal, not action here)
        # Actually keep it — USE_STAIRS on the last floor means goal reached.

        # Discover shops on the current floor (first contact = quick-shop unlocked, as in the
        # real game). Registration is independent of affordability: reaching the MT3 shop
        # with 24 gold must still unlock it for later floors.
        for s in state.reachable_shops():
            shop = s["shop"]
            for choice in shop["choices"]:
                already = any(
                    gs["floor_id"] == self.current_floor.floor_id and gs["x"] == s["x"] and gs["y"] == s["y"]
                    and gs["shop_choice"] == choice["id"]
                    for gs in self.global_shops
                )
                if not already:
                    self.global_shops.append({
                        "floor_id": self.current_floor.floor_id,
                        "x": s["x"], "y": s["y"],
                        "name": f"{shop['name']}: {choice['label']}",
                        "shop_choice": choice["id"],
                        "stat_changes": choice["changes"],
                        "money_cost": choice.get("cost", shop.get("cost", 0)),
                        "currency": shop.get("currency", "money"),
                        "requires_key": choice.get("requires_key"),
                    })
        shop_actions_on_floor = [a for a in actions if a.type == ActionType.SHOP_BUY]
        on_floor_shop_tiles = {(s["x"], s["y"]) for s in state.reachable_shops()}

        # Inject global shop_buy actions for discovered shops that are NOT reachable on this
        # floor (walking back is free in the real game's quick-shop; here it costs one action).
        if self.global_shops:
            next_id = max(a.action_id for a in actions) + 1 if actions else 1
            for gs in self.global_shops:
                if gs["floor_id"] == self.current_floor.floor_id and (gs["x"], gs["y"]) in on_floor_shop_tiles:
                    continue  # offered as a normal in-floor action (with path) instead
                if D.hero_balance(self.hero, gs["currency"]) < gs["money_cost"]:
                    continue
                if gs["shop_choice"] == "level" and not os.environ.get("MOTA_OFFER_LEVELUPS"):
                    continue
                if key_purchase_hidden(gs["shop_choice"]):
                    continue
                req = gs.get("requires_key")
                if req and getattr(self.hero.keys, req, 0) < 1:
                    continue
                a = Action(
                    action_id=next_id,
                    type=ActionType.SHOP_BUY,
                    x=gs["x"], y=gs["y"],
                    name=f"{gs['name']} (from {gs['floor_id']})",
                    shop_choice=gs["shop_choice"],
                    stat_changes=gs["stat_changes"],
                    money_cost=gs["money_cost"],
                    currency=gs["currency"],
                    path_steps=0,
                    path=[],
                )
                actions.append(a)
                next_id += 1

        if self.remote_actions_on():
            if not self.is_last_floor and (self.current_floor_idx + 1) in self.visited_floor_idx:
                actions = [a for a in actions if a.type != ActionType.USE_STAIRS]
            actions.extend(self._build_remote_actions(max((a.action_id for a in actions), default=0) + 1))
            actions.extend(self._build_fidelity_actions(max((a.action_id for a in actions), default=0) + 1))
            return actions

        # Add RETURN_TO_FLOOR actions for deferred doors openable now
        return_actions = self._build_return_actions(len(actions) + 1)
        actions.extend(return_actions)

        # Add revisit actions for earlier floors that still hold reachable loot or
        # fights that have become winnable (the walkthrough's back-tracking pattern).
        actions.extend(self._build_revisit_actions(len(actions) + 1))

        return actions

    def apply_action(self, action: Action) -> StepTrace:
        """
        Apply an action. Routes USE_STAIRS and RETURN_TO_FLOOR specially;
        all other actions delegate to GameState.
        """
        self.total_turns += 1

        if action.remote is not None:
            return self._apply_remote(action)

        if action.shop_choice in ("event", "event2"):
            return self._apply_event(action)

        if action.type == ActionType.USE_STAIRS:
            return self._apply_stairs(action)

        if action.type == ActionType.RETURN_TO_FLOOR:
            return self._apply_return_to_floor(action)

        # Global shop buy (from a different floor) — apply directly to hero
        if action.type == ActionType.SHOP_BUY and action.path_steps == 0:
            return self._apply_global_shop(action)

        # In-floor action: delegate to a temporary GameState that shares removed set
        state = self._make_state()
        state.turn = self.total_turns - 1
        trace = state.apply_action(action)

        # Sync hero and removed set back
        self.hero = state.hero.copy()
        self.per_floor_removed[self.current_floor_idx] = set(state.removed)
        if action.type == ActionType.FIGHT:
            self._after_battle(self.current_floor_idx, action.x, action.y)
            self._check_win(self.current_floor_idx, action.x, action.y)

        # After every action, scan for newly deferred doors on this floor
        self._scan_and_defer_doors(self.current_floor_idx)

        self.history.append(trace)
        self._check_failure()
        return trace

    def format_state(self) -> str:
        """Format full multi-floor state for the LLM prompt."""
        state = self._make_state()
        base = state.format_state()
        if self.fidelity_on():
            base = base.replace("Hero: HP=", f"Hero: LV={self.hero.lv} HP=", 1)
        lines = [base]
        lines.append(f"Floor progress: {self.current_floor_idx + 1}/{len(self.floors)} "
                     f"({self.current_floor.floor_id})")
        if self.remote_actions_on():
            lines.append(self._tower_key_budget_line())
            needs = self._way_up_line() if self.way_up_on() else self._stat_needs_line()
            if needs:
                lines.append(needs)
            if self.fidelity_on():
                lines.extend(self._events_lines())
                lines.extend(self._seal_lines())
            lines.extend(self._treasure_lines())
        if self.deferred_doors and not self.remote_actions_on():
            lines.append(f"Deferred doors from prev floors: {len(self.deferred_doors)}")
            for dd in self.deferred_doors:
                openable = self.hero.keys.has_key(dd.door_type)
                tag = " [NOW OPENABLE]" if openable else ""
                lines.append(f"  {dd.door_type.value} door @({dd.x},{dd.y}) on {dd.floor_id}{tag}")
        leftovers = [] if self.remote_actions_on() else [
            s for s in (self._floor_leftover_summary(i) for i in range(self.current_floor_idx)) if s]
        if leftovers:
            lines.append("Earlier floors with reachable leftovers (a 'Return to' action re-enters them; "
                         "coming back up costs one stairs action per floor):")
            lines.extend("  " + s for s in leftovers)
        if self.global_shops:
            seen = set()
            names = []
            for gs in self.global_shops:
                base_name = gs["name"].split(":")[0]
                if base_name not in seen:
                    seen.add(base_name)
                    names.append(f"{base_name} on {gs['floor_id']}")
            lines.append("Discovered shops usable from any floor: " + "; ".join(names))
        return "\n".join(lines)

    def format_floor_map(self) -> str:
        """Delegate floor map formatting to current floor's GameState."""
        return self._make_state().format_floor_map()

    def format_actions(self, actions: list[Action]) -> str:
        """Format actions list; delegate to GameState for in-floor actions and add the
        cross-floor lookahead (other floors are part of the decision, not just this one)."""
        state = self._make_state()
        in_floor = [a for a in actions if a.type != ActionType.RETURN_TO_FLOOR and a.remote is None]
        remote = [a for a in actions if a.remote is not None]
        return_actions = [a for a in actions if a.type == ActionType.RETURN_TO_FLOOR and a.remote is None]

        parts = []
        way_fid, way_tiles = self.way_up_tiles() if self.way_up_on() and self.remote_actions_on() else (None, set())
        reserve = self._way_up_doors() if os.environ.get("MOTA_KEY_RESERVE") == "1" else None

        def on_way(fid: str, a: Action) -> list[str]:
            out = self._free_by_purchase(a) + self._shop_rate_line(a) + self._free_rewards_line(fid, a) \
                + self._red_door_line(a) + self._cross_line(a) + self._key_reserve_line(fid, a, reserve)
            if fid == way_fid and (a.x, a.y) in way_tiles and a.type in (ActionType.FIGHT, ActionType.OPEN_DOOR):
                out.append(f" → on the way up to the next unvisited floor (Way up line)")
            return out

        if in_floor:
            text = state.format_actions(in_floor)
            fid_here = self.current_floor.floor_id
            extras = {a.action_id: self._cross_floor_lines(a) + on_way(fid_here, a) for a in in_floor}
            parts.append(self._insert_action_extras(text, extras))
        if remote:
            from .state import _ACTIONS_LEGEND
            legend = set(_ACTIONS_LEGEND) | {"Available actions:"}
            for fid in dict.fromkeys(a.target_floor_id for a in remote):
                group = [a.remote for a in remote if a.target_floor_id == fid]
                probe = getattr(self, "_remote_probes", {}).get(fid)
                if probe is None:
                    continue
                parts.append(f"=== {fid} (visited floor; choosing an action walks there, stairs cost 0 HP) ===")
                block = "\n".join(l for l in probe.format_actions(group).splitlines() if l not in legend)
                block = self._insert_action_extras(block, {a.action_id: on_way(fid, a) for a in group})
                parts.append(block)
        if return_actions:
            parts.append("=== Return to earlier floors (= take the down stairs; climbing back costs one use_stairs per floor, 0 HP) ===")
            for a in return_actions:
                parts.append(f"  {a.action_id}. [return_to_floor] {a.label()}")
                parts.extend(self._return_action_tree(a))
        return "\n".join(parts)

    # -- cross-floor lookahead -------------------------------------------------

    def _free_by_purchase(self, a: Action) -> list[str]:
        """MOTA_FREE_AFFORD=1 (design 5, user 2026-10-02): for a fight that costs HP, what the gold/EXP in hand can do to it
        now: the fewest DEF purchases that make it free, otherwise the DEF-only or ATK-only purchases that make it cheapest
        (design-3 re-run turn 189: two Skeleton Captains at 85 + 75 HP were free at DEF 90, 2x DEF +4 for 50 g with
        176 g in hand; design-5 runs kept fighting 5 %-fights with gold for DEF in hand)."""
        if os.environ.get("MOTA_FREE_AFFORD") != "1" or a.type != ActionType.FIGHT or not a.can_win or a.total_damage <= 0:
            return []
        mon = self.gd.get_monster(a.monster_id) if a.monster_id else None
        opts = self._stat_shop_options()
        if mon is None or not opts:
            return []
        found = {}  # stat -> (damage, n purchases, counts, options)
        for stat in ("def", "atk"):
            options = opts.get(stat, [])
            if not options:
                continue
            attr = "def_" if stat == "def" else "atk"
            bal = {c: D.hero_balance(self.hero, c) for _, _, c in options}
            for gain, (n, counts) in self._gain_table(options, bal, 20).items():
                if not gain:
                    continue
                probe = self.hero.copy()
                setattr(probe, attr, getattr(probe, attr) + gain)
                d = dmg_mod.calculate(probe, mon).total_damage
                key = (d, n)
                if d < a.total_damage and (stat not in found or key < found[stat][:2]):
                    found[stat] = (d, n, counts, options)
        if not found:
            return []
        stat = min(found, key=lambda s: found[s][:2])
        d, _, counts, options = found[stat]
        buys = ", ".join(f"{k}× {stat.upper()} +{g} ({k * p} {shop_unit(c)})" for (g, p, c), k in zip(options, counts) if k)
        if d == 0:
            return [f" → costs 0 HP after purchases you can make now: {buys} (saves {a.total_damage} HP on this fight; "
                    f"{stat.upper()} also lowers every later fight)"]
        return [f" → costs {d} instead of {a.total_damage} HP after purchases you can make now: {buys} "
                f"({stat.upper()} also lowers every later fight)"]

    @staticmethod
    def _gain_table(options: list[tuple[int, int, str]], bal: dict[str, int], cap: int) -> dict[int, tuple[int, tuple]]:
        """{total gain: (fewest purchases, counts per option)} over every combination of `options` (gain, price,
        currency) with each option at most `cap` times and each currency within its balance. Exact; built one currency
        at a time, so it stays small when the balances are large."""
        import itertools
        table = {0: (0, (0,) * len(options))}
        for cur in dict.fromkeys(c for _, _, c in options):
            idx = [i for i, (_, _, c) in enumerate(options) if c == cur]
            local: dict[int, tuple[int, tuple]] = {}
            for ks in itertools.product(*[range(min(cap, bal[cur] // options[i][1]) + 1) for i in idx]):
                if sum(k * options[i][1] for k, i in zip(ks, idx)) > bal[cur]:
                    continue
                g = sum(k * options[i][0] for k, i in zip(ks, idx))
                if g not in local or sum(ks) < local[g][0]:
                    local[g] = (sum(ks), ks)
            new: dict[int, tuple[int, tuple]] = {}
            for g1, (n1, c1) in table.items():
                for g2, (n2, ks) in local.items():
                    if g1 + g2 not in new or n1 + n2 < new[g1 + g2][0]:
                        counts = list(c1)
                        for i, k in zip(idx, ks):
                            counts[i] = k
                        new[g1 + g2] = (n1 + n2, tuple(counts))
            table = new
        return table

    def _shop_rate_line(self, a: Action) -> list[str]:
        """MOTA_FREE_AFFORD=1: price per point of a single-stat purchase, and the better-priced registered option in the same
        currency if there is one (MT11 gold shop +20 for 100 g vs MT3 +4 for 25 g; MT13 EXP +17 for 95 vs MT5 +5 for 30)."""
        if os.environ.get("MOTA_FREE_AFFORD") != "1" or a.type != ActionType.SHOP_BUY or not a.stat_changes:
            return []
        stats = [s for s in ("atk", "def") if a.stat_changes.get(s, 0) > 0]
        if len(stats) != 1 or set(a.stat_changes) != set(stats) or a.money_cost <= 0:
            return []
        stat, gain = stats[0], a.stat_changes[stats[0]]
        unit = shop_unit(a.currency)
        rate = a.money_cost / gain
        better = [(p / g, g, p) for g, p, c in self._stat_shop_options().get(stat, []) if c == a.currency and p / g < rate - 1e-9]
        if not better:
            return [f" → {rate:.2f} {unit} per point of {stat.upper()} (the best price per point open to you)"]
        r, g, p = min(better)
        have = D.hero_balance(self.hero, a.currency)
        need = f"you have {have}" + (f", {p - have} more needed" if have < p else "")
        return [f" → {rate:.2f} {unit} per point of {stat.upper()}; another shop sells +{g} {stat.upper()} for {p} {unit} = "
                f"{r:.2f} {unit} per point ({need})"]

    def _free_rewards_line(self, fid: str, a: Action) -> list[str]:
        """MOTA_FREE_AFFORD=1 (user 2026-10-02): gold and EXP of the 0-HP fights this door/fight makes reachable (run
        083340 turn 157 paid 315 HP while three free fights behind an MT1 door would have paid for DEF first)."""
        if os.environ.get("MOTA_FREE_AFFORD") != "1" or a.type not in (ActionType.OPEN_DOOR, ActionType.FIGHT):
            return []
        if a.type == ActionType.FIGHT and (not a.can_win or a.total_damage >= self.hero.hp):
            return []
        idx = self._floor_index(fid)
        if idx is None:
            return []
        f = self.floors[idx]
        probe = GameState(floor=f, hero=self.hero.copy(), goal="stairs", game_data=self.gd, lookahead_depth=0,
                          _removed=set(self.per_floor_removed[idx]))
        if idx != self.current_floor_idx:
            probe.hero.x, probe.hero.y = self._arrival(idx)

        def free_now() -> list[Action]:
            return [x for x in probe.get_actions() if x.type == ActionType.FIGHT and x.can_win and x.total_damage == 0]

        before = {(x.x, x.y) for x in free_now()}
        mine = next((x for x in probe.get_actions() if x.type == a.type and (x.x, x.y) == (a.x, a.y)), None)
        if mine is None or (a.type == ActionType.OPEN_DOOR and not probe.hero.keys.has_key(a.door_type)):
            return []
        probe.apply_action(mine)
        gold0, exp0, n = probe.hero.money, probe.hero.exp, 0
        for _ in range(25):
            new = [x for x in free_now() if (x.x, x.y) not in before]
            if not new:
                break
            probe.apply_action(new[0])
            n += 1
        g, e = probe.hero.money - gold0, probe.hero.exp - exp0
        if n == 0 or (g <= 0 and e <= 0):
            return []
        return [f" → behind it: {n} fight(s) at 0 HP that pay {g} g and {e} EXP"]

    def _red_door_line(self, a: Action) -> list[str]:
        """MOTA_FREE_AFFORD=1: what a red door needs and what a red key costs (run 083340 spent 3,375 g on stats and left
        the MT6 and MT11 red doors closed)."""
        if os.environ.get("MOTA_FREE_AFFORD") != "1" or a.type != ActionType.OPEN_DOOR or a.door_type != DoorType.RED:
            return []
        seller = next((gs for gs in self.global_shops if gs["shop_choice"] == "buy_red"), None)
        have = self.hero.keys.red
        sale = (f"the {seller['name'].split(':')[0]} on {seller['floor_id']} sells one for {seller['money_cost']} "
                f"{shop_unit(seller['currency'])} (you have {D.hero_balance(self.hero, seller['currency'])})"
                if seller else "no red-key seller reached yet")
        return [f" → needs a red key: you have {have}; {sale}"]

    def _route_key_need(self, route: dict) -> str:
        """MOTA_KEY_RESERVE=1: keys the way up's doors need beyond those in hand, with the seller's price (design-6 runs
        reached MT16 with 0 red keys; without a key the door is not an action, so nothing else said what was missing)."""
        if os.environ.get("MOTA_KEY_RESERVE") != "1":
            return ""
        parts = []
        for colour in dict.fromkeys(c for c, _, _ in route["doors"]):
            need = sum(1 for c, _, _ in route["doors"] if c == colour)
            have = getattr(self.hero.keys, colour, 0)
            if have >= need:
                continue
            seller = next((gs for gs in self.global_shops if gs["shop_choice"] == f"buy_{colour}"), None)
            hidden = key_purchase_hidden(f"buy_{colour}")
            if hidden:
                seller = None
            sale = (f"the {seller['name'].split(':')[0]} on {seller['floor_id']} sells one for {seller['money_cost']} "
                    f"{shop_unit(seller['currency'])} (you have {D.hero_balance(self.hero, seller['currency'])})"
                    if seller else (f"{colour} keys cannot be bought" if hidden and _event_way()
                                    else f"no {colour}-key seller reached yet"))
            parts.append(f"needs {need} {colour} key(s), you have {have}: {sale}")
        return (" [" + "; ".join(parts) + "]") if parts else ""

    def _event_way(self, idx: int, tile: tuple[int, int]) -> str:
        """MOTA_EVENT_WAY=1 (design 7): the way to an event's item or guard with its doors and missing keys (397B design-6
        run 1 spent its last blue keys on MT7 with the Ice Pickaxe and the last White Warrior each behind a blue door)."""
        route = self._way_up_route(idx, self.hero, target=tile)
        if route is None:
            return "no way there from the reachable area"
        fights = ", ".join(f"{n}@({fx},{fy}) " + ("CANNOT WIN" if d is None else str(d))
                           for n, fx, fy, d in route["fights"] if d != 0) or "no paid fights"
        doors = ("; doors " + ", ".join(f"{c} ({x},{y})" for c, x, y in route["doors"])) if route["doors"] else ""
        return f"way there: {fights}{doors}{self._route_key_need(route)}"

    def _way_up_doors(self) -> tuple[str, str, list[tuple[str, int, int]]] | None:
        """(frontier floor id, next floor id, keyed doors on its way up) for MOTA_KEY_RESERVE."""
        idx = self._frontier_idx()
        route = self._way_up_route(idx, self.hero) if idx is not None else None
        if route is None:
            return None
        return self.floors[idx].floor_id, self.floors[idx + 1].floor_id, route["doors"]

    def _key_reserve_line(self, fid: str, a: Action, reserve) -> list[str]:
        """MOTA_KEY_RESERVE=1 (user 2026-10-02): a door off the way up that leaves fewer keys of its colour than the
        way up still needs (run 204754 spent its last red key on MT10 at turn 426 with the MT16 red door (6,4) on the
        way up, and ended with 0 red keys)."""
        if reserve is None or a.type != ActionType.OPEN_DOOR or a.door_type is None or a.door_type == DoorType.ICE:
            return []
        way_fid, nxt, doors = reserve
        colour = a.door_type.value
        need = [(x, y) for c, x, y in doors if c == colour]
        if not need or (fid == way_fid and (a.x, a.y) in need):
            return []
        left = getattr(self.hero.keys, colour, 0) - 1
        if left >= len(need):
            return []
        at = ", ".join(f"({x},{y})" for x, y in need)
        return [f" → not on the way up: leaves {left} {colour} key(s), and the way up from {way_fid} to {nxt} goes "
                f"through {len(need)} {colour} door(s) at {at} on {way_fid}"]

    def _cross_line(self, a: Action) -> list[str]:
        if os.environ.get("MOTA_FREE_AFFORD") != "1" or a.shop_choice != "cross":
            return []
        return [" → the gain is a third of your stats at the moment you hand it in, so it grows with them; "
                "you can keep the Cross and hand it in later"]

    def _treasure_lines(self) -> list[str]:
        """MOTA_FREE_AFFORD=1 (user 2026-10-02): uncollected treasures (equipment, feathers, key boxes, the Cross, Holy
        Water, and characters that hand such items over) on visited floors, each with the in-order cost of the way
        there; at most five, most valuable first (run 083340 reached MT9 at turn 216 and took the Knight Sword at 310)."""
        if os.environ.get("MOTA_FREE_AFFORD") != "1":
            return []
        term = os.environ.get("MOTA_TREASURE_TERM", "Treasures")
        if term == "__off__":  # ablation of the line itself (wording test 2026-10-02)
            return []
        found = []
        opts = self._stat_shop_options()
        for idx in sorted(self.visited_floor_idx):
            f = self.floors[idx]
            probe = GameState(floor=f, hero=self.hero.copy(), goal="stairs", game_data=self.gd, lookahead_depth=0,
                              _removed=set(self.per_floor_removed[idx]))
            for y, row in enumerate(f.map):
                for x, t in enumerate(row):
                    if (x, y) in self.per_floor_removed[idx]:
                        continue
                    iid, who, price_tag = None, "", ""
                    if self.gd.is_item(t):
                        iid = self.gd.get_item_id(t)
                    elif self.gd.is_npc(t):
                        evts = f.events.get(f"{x},{y}", [])
                        iid = probe._npc_gift_item(evts)
                        who = f"{self.gd.get_npc_id(t) or 'NPC'} gives "
                        trade = None if iid else probe._npc_trade(evts)
                        if trade:
                            iid, cur, price = trade
                            who = f"{self.gd.get_npc_id(t) or 'NPC'} trades "
                            price_tag = f" for {price} {shop_unit(cur)} (you have {D.hero_balance(self.hero, cur)})"
                    if not iid or not (iid in D.TREASURE_ITEMS):
                        continue
                    eff = self.gd.get_item_effect(iid)
                    value = eff.get("atk", 0) + eff.get("def", 0) + 15 * eff.get("lv", 0) + eff.get("score", 0) / 10
                    found.append((value, idx, x, y, who + eff.get("name", iid) + price_tag))
        if not found:
            return []
        parts = []
        for _, idx, x, y, name in sorted(found, key=lambda r: -r[0])[:5]:
            route = self._way_up_route(idx, self.hero, target=(x, y))
            fid = self.floors[idx].floor_id
            if route is None:
                way = "no way there from the reachable area yet"
            else:
                way = self._route_in_order(idx, route, opts, where="there").replace(
                    "In order, spending the gold/EXP of each fight before the next: ", "")
                if route["doors"]:
                    way += f" Doors on the way: {', '.join(c for c, _, _ in route['doors'])}."
            parts.append(f"  {name} on {fid} ({x},{y}): {way}")
        return [f"{term} not collected yet on visited floors (the way there in order, spending the gold/EXP of each "
                f"fight before the next):"] + parts

    def _probe(self, floor_idx: int, hero=None, at_arrival_from_below: bool = False) -> GameState:
        """GameState for another floor with the current (or a hypothetical) hero standing on
        its up-stairs (revisit) or its down-stairs arrival tile (climbing)."""
        floor = self.floors[floor_idx]
        probe = GameState(
            floor=floor,
            hero=(hero or self.hero).copy(),
            goal="stairs",
            max_turns=self.max_turns_per_floor,
            game_data=self.gd,
            lookahead_depth=1,
            _removed=set(self.per_floor_removed[floor_idx]),
        )
        probe.hero.x, probe.hero.y = floor.down_floor if at_arrival_from_below else floor.up_floor
        return probe

    @staticmethod
    def _fight_stats(probe_actions: list[Action]) -> dict:
        fights = [a for a in probe_actions if a.type == ActionType.FIGHT]
        win = [a for a in fights if a.can_win]
        return {
            "fights": fights, "win": win,
            "unwin": [a for a in fights if not a.can_win],
            "free": [a for a in win if a.total_damage == 0],
            "items": [a for a in probe_actions if a.type == ActionType.COLLECT],
            "doors": [a for a in probe_actions if a.type == ActionType.OPEN_DOOR and not a.is_dead_end],
            "shops": [a for a in probe_actions if a.type == ActionType.SHOP_BUY],
        }

    def _floor_stats(self, floor_idx: int, hero=None, from_below: bool = False) -> dict:
        probe = self._probe(floor_idx, hero, at_arrival_from_below=from_below)
        st = self._fight_stats(probe.get_actions())
        st["floor_id"] = self.floors[floor_idx].floor_id
        return st

    def _stat_delta(self, a: Action) -> tuple[int, int]:
        """(atk, def) change an action would give the hero, or (0, 0)."""
        if a.type == ActionType.COLLECT and a.item_id:
            eff = self.gd.get_item_effect(a.item_id)
            return int(eff.get("atk", 0)), int(eff.get("def", 0))
        if a.type == ActionType.SHOP_BUY:
            return int(a.stat_changes.get("atk", 0)), int(a.stat_changes.get("def", 0))
        return 0, 0

    def _cross_floor_lines(self, a: Action) -> list[str]:
        lines: list[str] = []
        if a.type == ActionType.SHOP_BUY and a.shop_choice == "cross":
            lines.append(self._cross_timing_line())
        # (1) Climbing: preview what the next floor offers at your current stats.
        if a.type == ActionType.USE_STAIRS and not self.is_last_floor:
            nxt = self._floor_stats(self.current_floor_idx + 1, from_below=True)
            cheapest = min((f.total_damage for f in nxt["win"]), default=None)
            fights = f"{len(nxt['win'])} winnable" + (f" (cheapest {cheapest} HP)" if cheapest is not None else "")
            lines.append(f" → next floor {nxt['floor_id']} from the arrival tile: {fights}, "
                         f"{len(nxt['unwin'])} unwinnable, {len(nxt['items'])} item(s), {len(nxt['doors'])} door(s), "
                         f"{'shop' if nxt['shops'] else 'no shop'} reachable")
            leftovers_here = self._fight_stats(self._make_state().get_actions())
            if leftovers_here["free"] or leftovers_here["items"]:
                lines.append(f"   (you would leave {len(leftovers_here['free'])} FREE fight(s) and "
                             f"{len(leftovers_here['items'])} item(s) behind on this floor)")
        # (2) Stat gains: what they unlock on OTHER floors (earlier floors with leftovers + next floor).
        d_atk, d_def = self._stat_delta(a)
        if d_atk or d_def:
            hero2 = self.hero.copy()
            hero2.atk += d_atk
            hero2.def_ += d_def
            effects = []
            targets = [(i, False) for i in range(self.current_floor_idx)]
            if not self.is_last_floor:
                targets.append((self.current_floor_idx + 1, True))
            if self.remote_actions_on():  # every visited floor, wherever the hero stands
                targets = [(i, i > self.current_floor_idx) for i in sorted(self.visited_floor_idx)
                           if i != self.current_floor_idx]
                here_saved = self._hp_saved_here(d_atk, d_def)
                here_new = len(self._newly_winnable(d_atk, d_def))
                bits = ([f"{here_new} fight(s) become winnable"] if here_new else []) + (
                    [f"saves {here_saved} HP on existing fights"] if here_saved else [])
                if bits:
                    effects.append(f"{self.current_floor.floor_id}: " + ", ".join(bits))
            for idx, from_below in targets:
                before = self._floor_stats(idx, from_below=from_below)
                if not before["fights"]:
                    continue
                after = self._floor_stats(idx, hero2, from_below=from_below)
                new_win = len(after["win"]) - len(before["win"])
                new_free = len(after["free"]) - len(before["free"])
                saved = sum(f.total_damage for f in before["win"]) - sum(
                    f.total_damage for f in after["win"] if (f.x, f.y) in {(g.x, g.y) for g in before["win"]})
                bits = []
                if new_win > 0:
                    bits.append(f"{new_win} fight(s) become winnable")
                if new_free > 0:
                    bits.append(f"{new_free} fight(s) become FREE")
                if saved > 0:
                    bits.append(f"saves {saved} HP on existing fights")
                if bits:
                    effects.append(f"{before['floor_id']}: " + ", ".join(bits))
            if effects:
                lines.append(" → cross-floor value: " + "; ".join(effects))
            # Multi-purchase gate: how many repeats of THIS buy make a currently lethal fight here winnable
            # (single-step lookahead cannot see that ATK 95→112 opens the Red Bat on MT8).
            if a.type == ActionType.SHOP_BUY and d_atk > 0:
                here = self._make_state()
                gates = []
                pool = ([(self.current_floor.floor_id, f) for f in here.get_actions()] if not self.remote_actions_on()
                        else self._visited_fights())
                for fid, f in pool:
                    if f.type != ActionType.FIGHT or not f.monster_id:
                        continue
                    mon = self.gd.get_monster(f.monster_id)
                    where = f"{f.name}@{fid}({f.x},{f.y})" if self.remote_actions_on() else f"{f.name}@({f.x},{f.y})"
                    probe = self.hero.copy()
                    if not f.can_win:
                        for k in range(1, 13):
                            probe.atk = self.hero.atk + k * d_atk
                            if dmg_mod.calculate(probe, mon).can_win:
                                gates.append((k, f"makes {where} winnable"))
                                break
                    if self.remote_actions_on() and (not f.can_win or f.damage_percent > hp_rule_pct()):
                        for k in range(1, 13):
                            probe.atk = self.hero.atk + k * d_atk
                            r = dmg_mod.calculate(probe, mon)
                            if r.can_win and r.total_damage * 100 <= hp_rule_pct() * self.hero.hp:
                                gates.append((k, f"makes {where} cost <= {hp_rule_pct()}% of HP ({r.total_damage})"))
                                break
                if gates:
                    gates.sort()
                    lines.append(" → ATK gate: " + "; ".join(
                        f"{k}× this purchase ({k * a.money_cost} {shop_unit(a.currency)}) {what}"
                        for k, what in gates[:4]))
        lines.extend(self._shop_behind_lines(a))
        return lines

    def _registered_shop_tiles(self) -> set:
        return {(gs["floor_id"], gs["x"], gs["y"]) for gs in self.global_shops}

    def _visited_fights(self) -> list[tuple[str, Action]]:
        """(floor id, fight) for every listed fight on every visited floor (current floor at the hero's position)."""
        out = [(self.current_floor.floor_id, f) for f in self._make_state().get_actions() if f.type == ActionType.FIGHT]
        for idx in sorted(self.visited_floor_idx):
            if idx == self.current_floor_idx:
                continue
            fid = self.floors[idx].floor_id
            probe = getattr(self, "_remote_probes", {}).get(fid) or self._probe(idx, at_arrival_from_below=idx > self.current_floor_idx)
            out += [(fid, f) for f in probe.get_actions() if f.type == ActionType.FIGHT]
        return out

    def _stat_needs_line(self) -> str:
        """The stats the strongest pending monsters ask for: the ATK at which each becomes winnable and the ATK (or
        DEF) at which it costs at most the prompt-rule-4 share of current HP. Pure computation, no recommendation."""
        pct = hp_rule_pct()
        seen, rows = set(), []
        for fid, f in self._visited_fights():
            if not f.monster_id or (f.can_win and f.damage_percent <= pct) or (fid, f.monster_id) in seen:
                continue
            seen.add((fid, f.monster_id))
            mon = self.gd.get_monster(f.monster_id)
            probe = self.hero.copy()
            atk_win = atk40 = def40 = None
            for atk in range(self.hero.atk, self.hero.atk + 401):
                probe.atk = atk
                r = dmg_mod.calculate(probe, mon)
                if r.can_win and atk_win is None:
                    atk_win = atk
                if r.can_win and r.total_damage * 100 <= pct * self.hero.hp:
                    atk40 = atk
                    break
            probe.atk = self.hero.atk
            if f.can_win:
                for d in range(self.hero.def_, self.hero.def_ + 401):
                    probe.def_ = d
                    if dmg_mod.calculate(probe, mon).total_damage * 100 <= pct * self.hero.hp:
                        def40 = d
                        break
            rows.append((atk40 or 10 ** 6, f"{f.name}@{fid} (HP {mon.hp}, ATK {mon.atk}, DEF {mon.def_}): "
                         + ("winnable now" if f.can_win else f"winnable at ATK >= {atk_win}" if atk_win else "not winnable within +400 ATK")
                         + (f"; <= {pct}% of HP at ATK >= {atk40}" if atk40 else "")
                         + (f" or DEF >= {def40}" if def40 else "")))
        if not rows:
            return ""
        rows.sort(key=lambda r: -r[0])
        return (f"Stat needs (strongest pending monsters on visited floors, at HP {self.hero.hp}, ATK {self.hero.atk}, "
                f"DEF {self.hero.def_}): " + "; ".join(r[1] for r in rows[:4]))

    # -- way up (MOTA_WAY_UP) ---------------------------------------------------

    @staticmethod
    def way_up_on() -> bool:
        """User 2026-10-01: the stat reference is the route to the next unvisited floor, not the strongest monsters
        seen (early floors show late-game monsters that are never on the way)."""
        return os.environ.get("MOTA_WAY_UP") == "1"

    def _frontier_idx(self) -> int | None:
        """Highest visited floor whose next floor has not been visited."""
        cand = [i for i in self.visited_floor_idx if i + 1 < len(self.floors) and i + 1 not in self.visited_floor_idx]
        return max(cand) if cand else None

    def _up_stairs_tile(self, idx: int) -> tuple[int, int] | None:
        f = self.floors[idx]
        for y, row in enumerate(f.map):
            for x, tile in enumerate(row):
                if self.gd.is_stairs(tile) and self.gd.get_stairs(tile) == "upFloor":
                    return x, y
        return None

    def _way_up_route(self, idx: int, hero: Hero, blocked: tuple[int, int] | None = None,
                      target: tuple[int, int] | None = None) -> dict | None:
        """Cheapest route from the hero (or the floor's arrival tile) to the up-staircase of floor `idx` (or `target`),
        ordered by (unwinnable fights, HP, doors, steps). Monster costs are exact at `hero`'s stats; items on the way
        are not counted. Returns {"unwinnable", "hp", "fights": [(name, x, y, dmg|None)], "doors": [(colour, x, y)]}."""
        import heapq
        target = target or self._up_stairs_tile(idx)
        if target is None:
            return None
        f, gd = self.floors[idx], self.gd
        removed = self.per_floor_removed[idx]
        start = (self.hero.x, self.hero.y) if idx == self.current_floor_idx else self._arrival(idx)
        costs: dict[tuple[int, int], tuple] = {}
        lethal: dict[tuple[int, int], int] = {}  # winnable at this ATK but costs >= current HP

        def enter(x: int, y: int):
            """(unwinnable, hp, doors) to step onto the tile, or None if impassable."""
            if (x, y) in removed or (x, y) == target:
                return 0, 0, 0
            tile = f.map[y][x]
            if gd.is_wall(tile) or gd.is_npc(tile):
                return None
            if gd.is_door(tile):
                return 0, 0, 0 if gd.get_door_type(tile) == DoorType.ICE else 1
            if gd.is_enemy(tile):
                if (x, y) not in costs:
                    mon = gd.get_monster(gd.get_enemy_id(tile))
                    r = dmg_mod.calculate(hero, mon) if mon else None
                    costs[(x, y)] = (0, r.total_damage, 0) if r and r.can_win else (1, 0, 0)
                    if r and not r.can_win and r.total_damage < 999999999:
                        lethal[(x, y)] = r.total_damage
                return costs[(x, y)]
            if gd.is_ground(tile) or gd.is_terrain(tile) or gd.is_stairs(tile) or gd.is_item(tile):
                return 0, 0, 0
            return None  # special doors and other scripted tiles stay closed, as in the pathfinder

        best = {start: (0, 0, 0, 0)}
        prev: dict[tuple[int, int], tuple[int, int]] = {}
        heap = [(0, 0, 0, 0, start)]
        while heap:
            u, hp, dr, st, (x, y) = heapq.heappop(heap)
            if (x, y) == target:
                break
            if best.get((x, y)) != (u, hp, dr, st):
                continue
            for dx, dy in pf.DIRECTIONS:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < f.width and 0 <= ny < f.height) or (nx, ny) == blocked:
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
        path, cur = [], target
        while cur != start:
            path.append(cur)
            cur = prev[cur]
        fights, doors = [], []
        for x, y in reversed(path):
            if (x, y) in removed:
                continue
            tile = f.map[y][x]
            if gd.is_enemy(tile) and (x, y) in costs:  # a monster target itself is not costed
                u_, dmg, _ = costs[(x, y)]
                mon = gd.get_monster(gd.get_enemy_id(tile))
                fights.append((mon.name if mon else "monster", x, y, None if u_ else dmg))
            elif gd.is_door(tile) and gd.get_door_type(tile) != DoorType.ICE:
                doors.append((gd.get_door_type(tile).value, x, y))
        u, hp, _, _ = best[target]
        return {"unwinnable": u, "hp": hp, "fights": fights, "doors": doors,
                "lethal": {(x, y): d for (x, y), d in lethal.items() if any((fx, fy) == (x, y) for _, fx, fy, _ in fights)}}

    def _stat_shop_options(self) -> dict[str, list[tuple[int, int, str]]]:
        """Registered single-stat purchases per stat, cheapest per point first: {"atk"|"def": [(gain, price, currency)]}."""
        out: dict[str, set[tuple[int, int, str]]] = {}
        for gs in self.global_shops:
            for stat in ("atk", "def"):
                gain = gs["stat_changes"].get(stat, 0)
                if gain > 0 and gs["money_cost"] > 0 and set(gs["stat_changes"]) == {stat}:
                    out.setdefault(stat, set()).add((gain, gs["money_cost"], gs["currency"]))
        return {s: sorted(v, key=lambda o: o[1] / o[0]) for s, v in out.items()}

    def _way_up_line(self) -> str:
        """The route to the next unvisited floor with exact fight costs, and what the affordable ATK / DEF purchases
        do to it. Pure computation, no recommendation; replaces the Stat-needs line under MOTA_WAY_UP=1."""
        idx = self._frontier_idx()
        if idx is None:
            return ""
        nxt = self.floors[idx + 1].floor_id
        fid = self.floors[idx].floor_id
        hidden = self._hidden_up_stairs(idx) if self._up_stairs_tile(idx) is None else None
        if hidden is not None:
            why = self._reveal_reason.get((idx, *hidden), "an event")
            return (f"Way up to {nxt}: the up-staircase of {fid} at {hidden} is hidden until {why} (see the Event line); "
                    f"until then there is no way up from {fid}.")
        route = self._way_up_route(idx, self.hero)
        if route is None:
            return f"Way up to {nxt}: no route from {fid}'s reachable area to its up-staircase."
        hp = max(1, self.hero.hp)
        lethal_words = os.environ.get("MOTA_WAYUP_COMBINED") == "1"

        def fight_str(r: dict, mark_unavoidable: bool) -> str:
            parts, flags = [], []
            free = sum(1 for *_, d in r["fights"] if d == 0)
            for name, x, y, dmg in r["fights"]:
                if dmg == 0:
                    continue
                if dmg is None and lethal_words and (x, y) in r.get("lethal", {}):
                    parts.append(f"{name}@({x},{y}) LETHAL ({r['lethal'][(x, y)]}, you have {hp} HP)")
                else:
                    parts.append(f"{name}@({x},{y}) " + ("CANNOT WIN" if dmg is None else f"{dmg}"))
                flags.append(mark_unavoidable and self._way_up_route(idx, self.hero, blocked=(x, y)) is None)
            tail = f" + {free} fight(s) at 0 HP" if free else ""
            if not parts:
                return ("no fights" + tail) if free else "no fights"
            if all(flags):
                return ", ".join(parts) + " (each of them is on every route)" + tail
            return ", ".join(p + (" [on every route]" if f else "") for p, f in zip(parts, flags)) + tail

        def summary(r: dict) -> str:
            if r["unwinnable"]:
                n_lethal = len(r.get("lethal", {})) if lethal_words else 0
                if n_lethal:
                    worst = max(r["lethal"].values())
                    rest = r["unwinnable"] - n_lethal
                    return (f"{n_lethal} fight(s) LETHAL at your HP (largest {worst})"
                            + (f", {rest} CANNOT WIN at your ATK" if rest > 0 else ""))
                return f"{r['unwinnable']} fight(s) CANNOT WIN yet"
            biggest = max((d for *_, d in r["fights"] if d is not None), default=0)
            return f"{r['hp']} HP total ({r['hp'] * 100 // hp} % of HP), largest fight {biggest} ({biggest * 100 // hp} %)"

        doors = f"; opens {len(route['doors'])} door(s) ({', '.join(c for c, _, _ in route['doors'])})" if route["doors"] else ""
        doors += self._route_key_need(route)
        if not route["unwinnable"] and route["hp"] == 0:
            return f"Way up to {nxt}: no HP needed on {fid} (only 0-HP fights{doors.replace(';', ',')})."
        text = (f"Way up to {nxt} (cheapest route on {fid} to its up-staircase, exact at your stats, items on the way "
                f"not counted): {fight_str(route, True)}{doors} = {summary(route)}")

        pct = hp_rule_pct()

        def affordable(r: dict) -> bool:
            return not r["unwinnable"] and all(d is not None and d * 100 <= pct * hp for *_, d in r["fights"])

        if affordable(route):
            text += f"; every fight on it already costs <= {pct} % of HP"
            # each fight alone may be affordable while the route as a whole is not (MT3: 650 HP at 340 HP)
            return text + ("\n  " + self._route_in_order(idx, route, self._stat_shop_options()) if lethal_words else "")

        need_at = []
        for stat, attr in (("ATK", "atk"), ("DEF", "def_")):
            probe = self.hero.copy()

            def ok_at(v: int) -> bool:
                setattr(probe, attr, v)
                r = self._way_up_route(idx, probe)
                return r is not None and affordable(r)

            lo, hi = getattr(self.hero, attr), getattr(self.hero, attr) + 400
            if ok_at(hi):  # cost falls monotonically with ATK / DEF on the tower floors (no break-armour monsters)
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    lo, hi = (lo, mid) if ok_at(mid) else (mid, hi)
                need_at.append(f"{stat} >= {hi}")
        text += (f"; every fight on it costs <= {pct} % of HP at " + " or ".join(need_at) if need_at
                 else f"; no ATK or DEF within +400 alone brings every fight on it to <= {pct} % of HP")

        opts = self._stat_shop_options()
        ladder = []
        combined = os.environ.get("MOTA_WAYUP_COMBINED") == "1"
        for stat, options in sorted(opts.items()):
            if combined:
                ladder.append(self._combined_ladder(idx, stat, options, summary, affordable, pct))
                continue
            gain, price, cur = options[0]
            bal = D.hero_balance(self.hero, cur)
            kmax = bal // price
            probe = self.hero.copy()
            steps, need = [], None
            for k in range(1, 61):
                setattr(probe, "atk" if stat == "atk" else "def_", getattr(self.hero, "atk" if stat == "atk" else "def_") + k * gain)
                r = self._way_up_route(idx, probe)
                if r is None:
                    break
                ok = affordable(r)
                if k <= kmax and (k <= 3 or k == kmax):
                    steps.append(f"{k}× ({k * price} {shop_unit(cur)}): {summary(r)}")
                if ok:
                    need = k
                    break
            label = f"{stat.upper()} +{gain} for {price} {shop_unit(cur)} (you have {bal})"
            others = [f"{stat.upper()} +{g} for {p} {shop_unit(c)} (you have {D.hero_balance(self.hero, c)})"
                      for g, p, c in options[1:]]
            if others:
                label += "; also " + ", ".join(others)
            tail = (f"; every fight on it <= {pct} % of HP after {need}× ({need * price} {shop_unit(cur)})" if need
                    else f"; no number of these purchases alone brings every fight on it to <= {pct} % of HP")
            ladder.append(f"{label}: " + (" | ".join(steps) if steps else "none affordable now") + tail)
        if ladder:
            text += "\n  With purchases: " + "\n  With purchases: ".join(ladder)
        if combined:
            text += "\n  " + self._route_in_order(idx, route, opts)
        return text

    def _route_in_order(self, idx: int, route: dict, opts: dict, where: str = "at the staircase") -> str:
        """The way up fought in path order, where before each paying fight the gold/EXP in hand (including what the
        earlier fights on it paid) buys the ATK/DEF combination that makes that fight cheapest. A fact about the
        route, not a plan: the hero may spend differently. Items on the way are still not counted."""
        import itertools
        f, gd = self.floors[idx], self.gd
        hero = self.hero.copy()
        flat = [(stat, g, p, c) for stat, options in opts.items() for g, p, c in options]
        bought: dict[str, int] = {}
        for name, x, y, _ in route["fights"]:
            mon = gd.get_monster(gd.get_enemy_id(f.map[y][x]))
            if mon is None:
                continue
            best = (dmg_mod.calculate(hero, mon).total_damage, ())
            ranges = [range(min(10, D.hero_balance(hero, c) // p) + 1) for _, _, p, c in flat]
            n_combos = 1
            for r in ranges:
                n_combos *= len(r)
            # 2026-10-03: a 397B run holding 1,940 g and 3,034 EXP spent 80 min per turn here; above 20,000
            # combinations the line uses the cheapest-making ATK-only or DEF-only purchase (as the fight line does).
            for counts in (itertools.product(*ranges) if n_combos <= 20000 else ()):
                spend: dict[str, int] = {}
                for (_, _, p, c), k in zip(flat, counts):
                    spend[c] = spend.get(c, 0) + k * p
                if any(v > D.hero_balance(hero, c) for c, v in spend.items()):
                    continue
                probe = hero.copy()
                for (stat, g, _, _), k in zip(flat, counts):
                    setattr(probe, "atk" if stat == "atk" else "def_", getattr(probe, "atk" if stat == "atk" else "def_") + k * g)
                d = dmg_mod.calculate(probe, mon).total_damage
                if d < best[0] or (d == best[0] and sum(counts) < sum(best[1] or (0,))):
                    best = (d, counts)
            if n_combos > 20000:
                for stat in ("atk", "def"):
                    sub = [i for i, o in enumerate(flat) if o[0] == stat]
                    options = [(flat[i][1], flat[i][2], flat[i][3]) for i in sub]
                    bal = {c: D.hero_balance(hero, c) for _, _, c in options}
                    for gain, (n, ks) in self._gain_table(options, bal, 10).items():
                        probe = hero.copy()
                        attr = "atk" if stat == "atk" else "def_"
                        setattr(probe, attr, getattr(probe, attr) + gain)
                        d = dmg_mod.calculate(probe, mon).total_damage
                        if d < best[0] or (d == best[0] and n < sum(best[1] or (0,))):
                            counts = [0] * len(flat)
                            for i, k in zip(sub, ks):
                                counts[i] = k
                            best = (d, tuple(counts))
            for (stat, g, p, c), k in zip(flat, best[1]):
                if k:
                    setattr(hero, "atk" if stat == "atk" else "def_", getattr(hero, "atk" if stat == "atk" else "def_") + k * g)
                    if c == "exp":
                        hero.exp -= k * p
                    else:
                        hero.money -= k * p
                    key = f"{stat.upper()} +{g} ({p} {shop_unit(c)})"
                    bought[key] = bought.get(key, 0) + k
            if best[0] >= hero.hp:
                short = "CANNOT WIN at that ATK" if best[0] >= 999999999 else f"needs {best[0]}, has {hero.hp} HP"
                return f"In order, spending the gold/EXP of each fight before the next: not passable — {name}@({x},{y}) {short}."
            hero.hp -= best[0]
            hero.money += mon.money
            hero.exp += mon.exp
        buys = ", ".join(f"{k}× {s}" for s, k in bought.items()) or "no purchases"
        return (f"In order, spending the gold/EXP of each fight before the next: passable, {hero.hp} HP left {where} "
                f"({buys}).")

    def _combined_ladder(self, idx: int, stat: str, options: list[tuple[int, int, str]], summary, affordable, pct: int) -> str:
        """MOTA_WAYUP_COMBINED=1 (design 5): k purchases of one stat drawn from every registered option and currency
        (gold and EXP together), cheapest per point first while affordable. The single-option ladder of design 4
        called a fight unwinnable that one gold and one EXP purchase made winnable (design-3 re-run, MT8 turn 203)."""
        attr = "atk" if stat == "atk" else "def_"
        base = getattr(self.hero, attr)
        bal = {c: D.hero_balance(self.hero, c) for _, _, c in options}
        left, seq = dict(bal), []
        while (pick := next(((g, p, c) for g, p, c in options if left[c] >= p), None)) is not None:
            left[pick[2]] -= pick[1]
            seq.append(pick)

        def spent_str(spent: dict[str, int]) -> str:
            return " + ".join(f"{v} {shop_unit(c)}" for c, v in spent.items())

        probe, gained, spent, steps, need = self.hero.copy(), 0, {}, [], None
        for k in range(1, 61):
            g, p, c = seq[k - 1] if k <= len(seq) else options[0]
            gained += g
            spent[c] = spent.get(c, 0) + p
            setattr(probe, attr, base + gained)
            r = self._way_up_route(idx, probe)
            if r is None:
                break
            if k <= len(seq) and (k <= 3 or k == len(seq)):
                steps.append(f"{k}× (+{gained} {stat.upper()}, {spent_str(spent)}): {summary(r)}")
            if affordable(r):
                need = (k, gained, spent_str(spent))
                break
        label = f"{stat.upper()} " + ", ".join(f"+{g} for {p} {shop_unit(c)}" for g, p, c in options) + \
            " (you have " + ", ".join(f"{v} {shop_unit(c)}" for c, v in bal.items()) + ")"
        tail = (f"; every fight on it <= {pct} % of HP after {need[0]}× (+{need[1]} {stat.upper()}, {need[2]})" if need
                else f"; no number of these purchases alone brings every fight on it to <= {pct} % of HP")
        return f"{label}: " + (" | ".join(steps) if steps else "none affordable now") + tail

    def way_up_tiles(self) -> tuple[str | None, set[tuple[int, int]]]:
        """(frontier floor id, monster/door tiles on its way up), for tagging actions."""
        idx = self._frontier_idx()
        route = self._way_up_route(idx, self.hero) if idx is not None else None
        if route is None:
            return None, set()
        return self.floors[idx].floor_id, {(x, y) for _, x, y, _ in route["fights"]} | {(x, y) for _, x, y in route["doors"]}

    # -- game events (MOTA_TOWER_FIDELITY) ------------------------------------------

    @staticmethod
    def fidelity_on() -> bool:
        """User 2026-10-01: model the MT4 thief (opens MT2 (2,7)), the Cross handed to the MT0 fairy and the items.js
        item values; all three are free or only beneficial, so the thief is auto-taken and the Cross timing is offered."""
        return os.environ.get("MOTA_TOWER_FIDELITY") == "1"

    @staticmethod
    def _first_visit_hides(evts: list) -> list[tuple[str, list[tuple[int, int]]]]:
        """`hide` events that remove tiles on ANOTHER floor in an NPC's first-visit branch (the `false` branch of a
        switch condition): [(floor id, [(x, y), ...])]."""
        out = []
        for evt in evts:
            if not isinstance(evt, dict):
                continue
            if evt.get("type") == "if" and str(evt.get("condition", "")).startswith("switch:"):
                out += MultiFloorGame._first_visit_hides(evt.get("false") or [])
            elif evt.get("type") == "hide" and evt.get("floorId") and evt.get("loc"):
                out.append((evt["floorId"], [tuple(p) for p in evt["loc"]]))
        return out

    @staticmethod
    def _event_list(v) -> list:
        return (v.get("data") or []) if isinstance(v, dict) else (v or [])

    @staticmethod
    def _first_visit_shows(evts: list) -> list[tuple[str | None, list[tuple[int, int]]]]:
        """`show` events of an NPC's first-visit branch: [(floor id or None = same floor, [(x, y), ...])]."""
        out = []
        for evt in evts:
            if not isinstance(evt, dict):
                continue
            if evt.get("type") == "if" and str(evt.get("condition", "")).startswith("switch:"):
                out += MultiFloorGame._first_visit_shows(evt.get("false") or [])
            elif evt.get("type") == "show" and evt.get("loc"):
                out.append((evt.get("floorId"), [tuple(p) for p in evt["loc"]]))
        return out

    @staticmethod
    def _item_gated_hides(evts: list) -> tuple[str, list[tuple[str, list[tuple[int, int]]]], bool] | None:
        """The second-visit branch (`true` of a switch) gated by `if item:X` (MT4 thief + ice pickaxe -> MT18 (6,9),
        (6,10)): (item id, [(floor id, locs)], whether the NPC hides itself), or None."""
        for evt in evts:
            if not (isinstance(evt, dict) and evt.get("type") == "if" and str(evt.get("condition", "")).startswith("switch:")):
                continue
            for e in evt.get("true") or []:
                if isinstance(e, dict) and e.get("type") == "if" and str(e.get("condition", "")).startswith("item:"):
                    br = [x for x in (e.get("true") or []) if isinstance(x, dict)]
                    hides = [(x["floorId"], [tuple(p) for p in x["loc"]]) for x in br
                             if x.get("type") == "hide" and x.get("floorId") and x.get("loc")]
                    if hides:
                        return e["condition"].split(":", 1)[1], hides, any(x.get("type") == "hide" and not x.get("loc") for x in br)
        return None

    @staticmethod
    def _shows_if_item(evts: list, item: str) -> list[tuple[str, list[tuple[int, int]]]]:
        """`show` events on other floors inside an `if item:<item>` branch, anywhere in an event tree."""
        out = []
        for e in evts:
            if not (isinstance(e, dict) and e.get("type") == "if"):
                continue
            if str(e.get("condition", "")).strip() == f"item:{item}":
                out += [(x["floorId"], [tuple(p) for p in x["loc"]]) for x in (e.get("true") or [])
                        if isinstance(x, dict) and x.get("type") == "show" and x.get("floorId") and x.get("loc")]
            out += MultiFloorGame._shows_if_item((e.get("true") or []) + (e.get("false") or []), item)
        return out

    def _shown_desc(self, fid: str, locs: list[tuple[int, int]]) -> str:
        idx = self._floor_index(fid)
        parts = []
        for x, y in locs:
            t = self._hidden.get((idx, x, y))
            kind = "the up-staircase" if t is not None and self.gd.is_stairs(t) and self.gd.get_stairs(t) == "upFloor" else "the tile"
            parts.append(f"{kind} at ({x},{y}) on {fid}")
        return ", ".join(parts)

    def _hidden_up_stairs(self, idx: int) -> tuple[int, int] | None:
        return next(((x, y) for (i, x, y), t in self._hidden.items()
                     if i == idx and self.gd.is_stairs(t) and self.gd.get_stairs(t) == "upFloor"), None)

    def _reveal(self, fid: str, locs: list[tuple[int, int]]) -> None:
        idx = self._floor_index(fid)
        for x, y in locs:
            orig = self._hidden.pop((idx, x, y), None)
            if orig is not None:
                self.floors[idx].map[y][x] = orig

    def _item_tiles(self, item: str, visited_only: bool = True) -> list[tuple[int, int, int]]:
        return [(i, x, y) for i, f in enumerate(self.floors) if not visited_only or i in self.visited_floor_idx
                for y, row in enumerate(f.map) for x, t in enumerate(row) if self.gd.get_item_id(t) == item]

    def _item_held(self, item: str) -> bool:
        return item not in self._items_used and any((x, y) in self.per_floor_removed[i]
                                                    for i, x, y in self._item_tiles(item, visited_only=False))

    def _check_win(self, idx: int, x: int, y: int) -> None:
        """Corrected engine: a fight whose afterBattle script ends the game (`win`, MT21 Nether Demon King = the normal
        ending) reaches the goal; the hidden ending above it is out of scope (user 2026-10-04)."""
        if not self.fidelity_on():
            return
        def has_win(evts) -> bool:
            return any(isinstance(e, dict) and (e.get("type") == "win" or has_win((e.get("true") or []) + (e.get("false") or [])
                                                                                     + (e.get("data") or [])))
                       for e in evts)
        if has_win((self.floors[idx].after_battle or {}).get(f"{x},{y}") or []):
            self.goal_reached = True

    def _init_fidelity_tiles(self) -> None:
        """NPC gifts defined on the tile (maps.js) become ordinary gift events; sealed tiles become walls until their
        guards are dead. Floors are copied first: the scenario's FloorData objects are shared between games."""
        import copy as _copy
        self.floors = [_copy.copy(f) for f in self.floors]
        for idx, f in enumerate(self.floors):
            f.events = dict(f.events)
            for key, v in list(f.events.items()):
                if isinstance(v, dict) and v.get("enable") is False:
                    x, y = map(int, key.split(","))
                    f.map = [list(r) for r in f.map]
                    self._hidden[(idx, x, y)] = f.map[y][x]
                    f.map[y][x] = 0
            for key, v in f.events.items():
                x, y = map(int, key.split(","))
                for fid, locs in self._first_visit_shows(self._event_list(v)):
                    npc = self.gd.get_npc_id(f.map[y][x]) or "a character"
                    target = self._floor_index(fid or f.floor_id)
                    for lx, ly in locs if target is not None else []:
                        self._reveal_reason[(target, lx, ly)] = f"you talk to {npc} on {f.floor_id} ({x},{y})"
                self._cross_shows += [(fid, locs) for fid, locs in self._shows_if_item(self._event_list(v), "cross")
                                      if self._floor_index(fid) is not None]
        for fid, locs in self._cross_shows:
            for lx, ly in locs:
                self._reveal_reason[(self._floor_index(fid), lx, ly)] = "the Cross is handed to the fairy on MT0"
        for idx, f in enumerate(self.floors):
            for y, row in enumerate(f.map):
                for x, t in enumerate(row):
                    item = D.NPC_TILE_GIFTS.get(self.gd.get_npc_id(t) or "") if self.gd.is_npc(t) else None
                    if item and f"{x},{y}" not in f.events:
                        f.events[f"{x},{y}"] = [{"type": "setValue", "name": f"item:{item}", "value": "+1"},
                                                {"type": "hide", "remove": True}]
            seal = D.FLOOR_SEALS.get(f.floor_id)
            if seal:
                sx, sy = seal["tile"]
                guards = {(x, y) for y, row in enumerate(f.map) for x, t in enumerate(row)
                          if self.gd.is_enemy(t) and self.gd.get_enemy_id(t) == seal["monster"]}
                f.map = [list(r) for r in f.map]
                self._seals.append({"idx": idx, "tile": (sx, sy), "orig": f.map[sy][sx], "guards": guards,
                                    "monster": seal["monster"], "behind": seal["behind"], "open": False})
                f.map[sy][sx] = 1

    def _update_seals(self) -> None:
        for s in self._seals:
            if not s["open"] and s["guards"] <= self.per_floor_removed[s["idx"]]:
                sx, sy = s["tile"]
                self.floors[s["idx"]].map[sy][sx] = s["orig"]
                s["open"] = True

    def _seal_lines(self) -> list[str]:
        out = []
        for s in self._seals:
            if s["open"] or s["idx"] not in self.visited_floor_idx:
                continue
            left = len(s["guards"] - self.per_floor_removed[s["idx"]])
            name = self.gd.get_monster(s["monster"]).name
            ways = ""
            if _event_way():
                left_tiles = sorted(s["guards"] - self.per_floor_removed[s["idx"]])
                ways = "".join(f" {name} at ({x},{y}): {self._event_way(s['idx'], (x, y))}." for x, y in left_tiles)
                doors = {d for x, y in left_tiles for d in (self._way_up_route(s["idx"], self.hero, target=(x, y))
                                                             or {"doors": []})["doors"]}
                for colour in sorted({c for c, _, _ in doors}):
                    need, have = sum(1 for c, _, _ in doors if c == colour), getattr(self.hero.keys, colour, 0)
                    if need > have:
                        ways += f" Together they need {need} {colour} key(s); you have {have}."
            out.append(f"Event: the seal at {s['tile']} on {self.floors[s['idx']].floor_id} ({s['behind']} behind it) opens "
                       f"when all {len(s['guards'])} {name}s on that floor are dead ({left} left).{ways}")
        return out

    def _floor_index(self, floor_id: str) -> int | None:
        return next((i for i, f in enumerate(self.floors) if f.floor_id == floor_id), None)

    def _after_battle(self, idx: int, x: int, y: int) -> None:
        """MOTA_AFTER_BATTLE=1 (2026-10-03): the `core.setEnemy` calls of a fight's afterBattle script change those
        monsters for the rest of the run (MT16 Red Demon King -> later Dark Knights, Ghost Skeletons, Black Magicians
        and the King himself; MT19 vampire). Other afterBattle content (dialogue, ending) is not modelled."""
        if os.environ.get("MOTA_AFTER_BATTLE") != "1":
            return
        import copy as _copy
        import dataclasses
        import re
        evts = (self.floors[idx].after_battle or {}).get(f"{x},{y}") or []
        calls = [c for e in evts if isinstance(e, dict) and e.get("type") == "function"
                 for c in re.findall(r"core\.setEnemy\('(\w+)',\s*'(\w+)',\s*(\d+)\)", e.get("function", ""))]
        if not calls:
            return
        if not getattr(self, "_own_gd", False):  # the scenario's GameData is shared between games
            self.gd = _copy.copy(self.gd)
            self.gd._custom_monsters = dict(self.gd._custom_monsters)
            self._own_gd = True
        for mid, attr, val in calls:
            field = {"def": "def_"}.get(attr, attr)
            base = self.gd.get_monster(mid)
            if base is not None and hasattr(base, field):
                self.gd._custom_monsters[mid] = dataclasses.replace(base, **{field: int(val)})

    def _cross_tiles(self) -> list[tuple[int, int, int]]:
        if not hasattr(self, "_cross_tiles_cache"):
            self._cross_tiles_cache = [(i, x, y) for i, f in enumerate(self.floors) for y, row in enumerate(f.map)
                                       for x, t in enumerate(row) if self.gd.get_item_id(t) == "cross"]
        return self._cross_tiles_cache

    def cross_held(self) -> bool:
        return not self.cross_given and any((x, y) in self.per_floor_removed[i] for i, x, y in self._cross_tiles())

    def _build_fidelity_actions(self, start_id: int) -> list[Action]:
        if not self.fidelity_on():
            return []
        out, next_id = [], start_id
        for idx in sorted(self.visited_floor_idx):
            f = self.floors[idx]
            sx, sy = (self.hero.x, self.hero.y) if idx == self.current_floor_idx else self._arrival(idx)
            reach = pf.find_reachable(f.map, sx, sy, self.hero.keys, removed=self.per_floor_removed[idx],
                                      height=f.height, width=f.width, include_paths=True, game_data=self.gd)
            for (x, y), info in reach.items():
                if info["type"] != "npc" or (x, y) in self.per_floor_removed[idx]:
                    continue
                evts = self._event_list(f.events.get(f"{x},{y}", []))
                if (f.floor_id, x, y) in self._events_done:
                    gated = self._item_gated_hides(evts)
                    if gated and (f.floor_id, x, y, "2") not in self._events_done and self._item_held(gated[0]):
                        item, hides, _ = gated
                        self._event_hides[(f.floor_id, x, y, "2")] = [(fid, locs) for fid, locs in hides
                                                                     if self._floor_index(fid) is not None]
                        name = self.gd.get_item_effect(item).get("name", item)
                        opens = "; ".join(f"{fid} " + ", ".join(f"({lx},{ly})" for lx, ly in locs) for fid, locs in hides)
                        out.append(Action(action_id=next_id, type=ActionType.COLLECT, x=x, y=y,
                                          name=f"{info['entity_id']} on {f.floor_id} (talk, give the {name}): removes "
                                               f"the tiles at {opens}",
                                          item_tier=ItemTier.MAJOR_STAT, item_score=99, shop_choice="event2",
                                          path=info.get("path", []), path_steps=len(info.get("path", [])),
                                          target_floor_id=f.floor_id))
                        next_id += 1
                    continue
                hides = [(fid, locs) for fid, locs in self._first_visit_hides(evts)
                         if fid != f.floor_id and self._floor_index(fid) is not None]
                shows = [(fid or f.floor_id, locs) for fid, locs in self._first_visit_shows(evts)
                         if self._floor_index(fid or f.floor_id) is not None
                         and any((self._floor_index(fid or f.floor_id), lx, ly) in self._hidden for lx, ly in locs)]
                if not hides and not shows:
                    continue
                self._event_hides[(f.floor_id, x, y)] = hides
                self._event_shows[(f.floor_id, x, y)] = shows
                parts = []
                if hides:
                    parts.append("removes the tiles at " + "; ".join(
                        f"{fid} " + ", ".join(f"({lx},{ly})" for lx, ly in locs) for fid, locs in hides))
                if shows:
                    parts.append("reveals " + "; ".join(self._shown_desc(fid, locs) for fid, locs in shows))
                out.append(Action(action_id=next_id, type=ActionType.COLLECT, x=x, y=y,
                                  name=f"{info['entity_id']} on {f.floor_id} (talk): {' and '.join(parts)}",
                                  item_tier=ItemTier.MAJOR_STAT, item_score=99, shop_choice="event",
                                  path=info.get("path", []), path_steps=len(info.get("path", [])),
                                  target_floor_id=f.floor_id))
                next_id += 1
        if self.cross_held():
            gain = {"hp": self.hero.hp // 3, "atk": self.hero.atk // 3, "def": self.hero.def_ // 3}
            out.append(Action(action_id=next_id, type=ActionType.SHOP_BUY, x=0, y=0,
                              name=f"Fairy (MT0): give the Cross — HP, ATK and DEF x4/3 (now +{gain['hp']} HP, "
                                   f"+{gain['atk']} ATK, +{gain['def']} DEF)",
                              shop_choice="cross", stat_changes=gain, money_cost=0, currency="money", path_steps=0))
        return out

    def _behind_tiles(self, idx: int, opened: list[tuple[int, int]]) -> list[str]:
        """What removing `opened` on floor `idx` gives access to: items and gift NPCs in the area that only those tiles
        connect to (walls bound the area; doors and monsters inside it are counted as passable)."""
        f, gd = self.floors[idx], self.gd
        removed = self.per_floor_removed[idx]
        start = self._arrival(idx) if idx != self.current_floor_idx else (self.hero.x, self.hero.y)

        def flood(open_set: set) -> set:
            seen, stack = {start}, [start]
            while stack:
                x, y = stack.pop()
                for dx, dy in pf.DIRECTIONS:
                    p = (x + dx, y + dy)
                    if not (0 <= p[0] < f.width and 0 <= p[1] < f.height) or p in seen:
                        continue
                    t = f.map[p[1]][p[0]]
                    walkable = p in removed or p in open_set or gd.is_ground(t) or gd.is_terrain(t) or gd.is_stairs(t) \
                        or gd.is_item(t) or gd.is_door(t) or gd.is_enemy(t) or gd.is_npc(t)
                    if not walkable:
                        continue
                    seen.add(p)
                    if not gd.is_npc(t) or p in removed:
                        stack.append(p)
            return seen

        behind = flood(set(opened)) - flood(set())
        probe = GameState(floor=f, hero=self.hero.copy(), goal="stairs", game_data=gd, lookahead_depth=0, _removed=set(removed))
        names = []
        for x, y in sorted(behind, key=lambda p: (p[1], p[0])):
            t = f.map[y][x]
            if gd.is_item(t):
                names.append(gd.get_item_effect(gd.get_item_id(t)).get("name", "item"))
            elif gd.is_npc(t):
                gift = probe._npc_gift_item(f.events.get(f"{x},{y}", []))
                if gift:
                    names.append(f"{gd.get_npc_id(t)} gives {gd.get_item_effect(gift).get('name', gift)}")
        counts: dict[str, int] = {}
        for n in names:
            counts[n] = counts.get(n, 0) + 1
        return [f"{n} ×{c}" if c > 1 else n for n, c in counts.items()]

    def _events_lines(self) -> list[str]:
        """Untriggered NPC events on visited floors and a held / reachable Cross, with exact routes (pure computation)."""
        lines = []
        for idx in sorted(self.visited_floor_idx):
            f = self.floors[idx]
            for key, evts in f.events.items():
                x, y = map(int, key.split(","))
                if (f.floor_id, x, y) in self._events_done or (x, y) in self.per_floor_removed[idx] \
                        or not self.gd.is_npc(f.map[y][x]):
                    continue
                hides = [(fid, locs) for fid, locs in self._first_visit_hides(evts)
                         if fid != f.floor_id and self._floor_index(fid) is not None]
                for fid, locs in hides:
                    behind = self._behind_tiles(self._floor_index(fid), locs)
                    route = self._way_up_route(idx, self.hero, target=(x, y))
                    if route is None:
                        way = "no route from the reachable area"
                    else:
                        fights = ", ".join(f"{n}@({fx},{fy}) " + ("CANNOT WIN" if d is None else str(d))
                                           for n, fx, fy, d in route["fights"] if d != 0) or "no paid fights"
                        doors = f"; doors {', '.join(c for c, _, _ in route['doors'])}" if route["doors"] else ""
                        cost = "CANNOT WIN yet" if route["unwinnable"] else f"{route['hp']} HP"
                        way = f"way there: {fights}{doors} = {cost}"
                    where = ", ".join(f"({lx},{ly})" for lx, ly in locs)
                    lines.append(f"Event: {self.gd.get_npc_id(f.map[y][x])} on {f.floor_id} ({x},{y}) — talking to "
                                 f"him removes {fid} {where}; behind it: {', '.join(behind) or 'nothing listed'}; {way}")
        if not self.cross_given:
            for i, x, y in self._cross_tiles():
                if i not in self.visited_floor_idx or (x, y) in self.per_floor_removed[i]:
                    continue
                reveals = "".join(f"; it also reveals {self._shown_desc(fid, locs)}" for fid, locs in self._cross_shows
                                  if self._floor_index(fid) in self.visited_floor_idx)
                lines.append(f"Event: Cross on {self.floors[i].floor_id} ({x},{y}) — handed to the fairy on MT0 it "
                             f"multiplies HP, ATK and DEF by 4/3 (now +{self.hero.hp // 3} HP, +{self.hero.atk // 3} ATK, "
                             f"+{self.hero.def_ // 3} DEF){reveals}")
        for idx in sorted(self.visited_floor_idx):
            f = self.floors[idx]
            for key, v in f.events.items():
                x, y = map(int, key.split(","))
                if (x, y) in self.per_floor_removed[idx] or not self.gd.is_npc(f.map[y][x]):
                    continue
                evts = self._event_list(v)
                npc = self.gd.get_npc_id(f.map[y][x])
                if (f.floor_id, x, y) not in self._events_done:
                    for fid, locs in self._first_visit_shows(evts):
                        fid = fid or f.floor_id
                        if not any((self._floor_index(fid), lx, ly) in self._hidden for lx, ly in locs):
                            continue
                        route = self._way_up_route(idx, self.hero, target=(x, y))
                        if route is None:
                            way = "no way there from the reachable area yet" + self._blocked_by_gated(idx)
                        else:
                            way = self._route_in_order(idx, route, self._stat_shop_options(), where="there").replace(
                                "In order, spending the gold/EXP of each fight before the next: ", "way there: ")
                            if route["doors"]:
                                way += f" Doors on the way: {', '.join(c for c, _, _ in route['doors'])}."
                        lines.append(f"Event: {npc} on {f.floor_id} ({x},{y}) — talking to this character reveals "
                                     f"{self._shown_desc(fid, locs)}; {way}")
                elif (f.floor_id, x, y, "2") not in self._events_done:
                    gated = self._item_gated_hides(evts)
                    if gated:
                        item, hides, _ = gated
                        name = self.gd.get_item_effect(item).get("name", item)
                        where = ", ".join(f"{self.floors[i].floor_id} ({ix},{iy})" for i, ix, iy in self._item_tiles(item))
                        held = "you hold it" if self._item_held(item) else (
                            f"it lies on {where}" if where else "not seen on a visited floor yet")
                        opens = "; ".join(f"{fid} " + ", ".join(f"({lx},{ly})" for lx, ly in locs) for fid, locs in hides)
                        way = ""
                        if _event_way() and not self._item_held(item):
                            tiles = [(i, ix, iy) for i, ix, iy in self._item_tiles(item) if i in self.visited_floor_idx]
                            if tiles:
                                way = f"; {self._event_way(tiles[0][0], (tiles[0][1], tiles[0][2]))}"
                        lines.append(f"Event: {npc} on {f.floor_id} ({x},{y}) — talked to again with the {name} "
                                     f"({held}), this character removes {opens}{way}")
        return lines

    def _blocked_by_gated(self, idx: int) -> str:
        """Which item-gated character event removes tiles on floor `idx` (the MT18 path to the princess)."""
        fid = self.floors[idx].floor_id
        for f in self.floors:
            for key, v in f.events.items():
                gated = self._item_gated_hides(self._event_list(v))
                x, y = map(int, key.split(","))
                if not gated or (f.floor_id, x, y, "2") in self._events_done or not any(h == fid for h, _ in gated[1]):
                    continue
                locs = ", ".join(f"({lx},{ly})" for h, ls in gated[1] if h == fid for lx, ly in ls)
                name = self.gd.get_item_effect(gated[0]).get("name", gated[0])
                return (f" (the tiles {locs} on {fid} are removed by {self.gd.get_npc_id(f.map[y][x]) or 'a character'} "
                        f"on {f.floor_id} ({x},{y}) when you bring the {name})")
        return ""

    def _cross_timing_line(self) -> str:
        """Pure computation: the Cross multiplies, so what it adds depends on when it is handed in."""
        bits = []
        for stat, attr in (("atk", "atk"), ("def", "def_")):
            add = 0
            for cur in ("money", "exp"):
                opts = [o for o in self._stat_shop_options().get(stat, []) if o[2] == cur]
                if opts:
                    gain, price, _ = opts[0]
                    add += (D.hero_balance(self.hero, cur) // price) * gain
            if add:
                base = getattr(self.hero, attr)
                bits.append(f"after spending all your gold/EXP on {stat.upper()} first: +{(base + add) // 3} {stat.upper()} "
                            f"instead of +{base // 3}")
        return (" → the Cross multiplies your current stats; " + "; ".join(bits)) if bits else \
            " → the Cross multiplies your current stats (no affordable ATK/DEF purchase changes it now)"

    def _apply_event(self, action: Action) -> StepTrace:
        """Walk to the NPC (travel between floors is free), talk, and remove the tiles its first-visit branch hides."""
        snap = {"hp": self.hero.hp, "atk": self.hero.atk, "def": self.hero.def_, "money": self.hero.money,
                "exp": self.hero.exp, "x": self.hero.x, "y": self.hero.y}
        idx = self._floor_index(action.target_floor_id)
        if idx != self.current_floor_idx:
            self.floor_transitions.append({"from": self.current_floor.floor_id, "to": action.target_floor_id,
                                           "hero_hp": self.hero.hp, "turn": self.total_turns, "type": "remote"})
            self.current_floor_idx = idx
            self.hero.x, self.hero.y = self._arrival(idx)
        if len(action.path) >= 2:
            self.hero.x, self.hero.y = action.path[-2]
        if action.shop_choice == "event2":
            key = (action.target_floor_id, action.x, action.y, "2")
            for fid, locs in self._event_hides.get(key, []):
                self.per_floor_removed[self._floor_index(fid)].update(locs)
            gated = self._item_gated_hides(self._event_list(self.floors[idx].events.get(f"{action.x},{action.y}", [])))
            if gated:
                self._items_used.add(gated[0])
                if gated[2]:  # the character leaves
                    self.per_floor_removed[idx].add((action.x, action.y))
            self._events_done.add(key)
        else:
            for fid, locs in self._event_hides.get((action.target_floor_id, action.x, action.y), []):
                self.per_floor_removed[self._floor_index(fid)].update(locs)
            for fid, locs in self._event_shows.get((action.target_floor_id, action.x, action.y), []):
                self._reveal(fid, locs)
            self._events_done.add((action.target_floor_id, action.x, action.y))
        trace = StepTrace(turn=self.total_turns, action=action, hero_before=snap,
                          hero_after={**snap, "x": self.hero.x, "y": self.hero.y}, note="event")
        self.history.append(trace)
        return trace

    def _unwinnable_here(self) -> list[Action]:
        return [f for f in self._make_state().get_actions()
                if f.type == ActionType.FIGHT and not f.can_win and f.monster_id]

    def _hp_saved_here(self, d_atk: int, d_def: int) -> int:
        """HP that +d_atk/+d_def saves on the fights currently winnable on this floor."""
        hero2 = self.hero.copy()
        hero2.atk += d_atk
        hero2.def_ += d_def
        saved = 0
        for f in self._make_state().get_actions():
            if f.type == ActionType.FIGHT and f.can_win and f.monster_id:
                r = dmg_mod.calculate(hero2, self.gd.get_monster(f.monster_id))
                saved += max(0, f.total_damage - r.total_damage)
        return saved

    def _newly_winnable(self, d_atk: int, d_def: int) -> list[Action]:
        """Fights on this floor that are unwinnable now and winnable after +d_atk/+d_def."""
        hero2 = self.hero.copy()
        hero2.atk += d_atk
        hero2.def_ += d_def
        return [f for f in self._unwinnable_here()
                if dmg_mod.calculate(hero2, self.gd.get_monster(f.monster_id)).can_win]

    def _shop_behind_lines(self, a: Action) -> list[str]:
        """S2: a shop not yet reached, priced in what the hero can buy there right now."""
        if a.type not in (ActionType.FIGHT, ActionType.OPEN_DOOR):
            return []
        shops = self.gd.get_shops()
        registered = self._registered_shop_tiles()
        out = []
        for u in a.unlocks_tree or []:
            sid = u.get("shop_id")
            if u.get("type") != "shop" or not sid or sid not in shops:
                continue
            if (self.current_floor.floor_id, *u["pos"]) in registered:
                continue
            shop = shops[sid]
            cur = shop.get("currency", "money")
            bal = D.hero_balance(self.hero, cur)
            unit = shop_unit(cur)
            opts = []
            for ch in shop["choices"]:
                if ch["id"] not in ("atk", "def"):
                    continue
                cost = ch.get("cost", shop.get("cost", 0))
                k = bal // cost if cost else 0
                if k <= 0:
                    continue
                da = ch["changes"].get("atk", 0) * k
                dd = ch["changes"].get("def", 0) * k
                stat = "ATK" if da else "DEF"
                before = self.hero.atk if da else self.hero.def_
                new = self._newly_winnable(da, dd)
                gain = f": {len(new)} fight(s) here become winnable" + (
                    f" ({', '.join(f'{f.name}@({f.x},{f.y})' for f in new[:3])})" if new else "")
                saved = self._hp_saved_here(da, dd) if os.environ.get("MOTA_SHOP_ROUTE") == "1" else 0
                if saved > 0:
                    gain += f", saves {saved} HP on this floor's winnable fights"
                opts.append(f"{k}× {ch['label']} ({stat} {before}→{before + (da or dd)}){gain}")
            if opts:
                out.append(f" → shop behind it: {shop['name']} — your {bal} {unit} buys " + " | or ".join(opts))
            else:
                out.append(f" → shop behind it: {shop['name']} — you cannot afford anything there yet ({bal} {unit})")
            route = self._shop_route_price(u) if os.environ.get("MOTA_SHOP_ROUTE") == "1" else None
            if route:
                out.append(route)
        return out

    def _shop_route_price(self, u: dict) -> str | None:
        """The monsters on the way to an unreached shop, priced now and after the ATK purchases the hero
        already has access to (MT5's EXP Old Man sits behind a Big Bat: 1,470 HP at ATK 33, 450 at ATK 41)."""
        steps = sorted({(gs["stat_changes"].get("atk", 0), gs["money_cost"], gs["currency"], gs["name"])
                        for gs in self.global_shops if gs["stat_changes"].get("atk", 0) > 0 and gs["money_cost"] > 0})
        parts = []
        for x, y in u.get("via_enemies") or []:
            mid = self.gd.get_enemy_id(self.current_floor.map[y][x])
            mon = self.gd.get_monster(mid) if mid else None
            if mon is None:
                continue
            now = dmg_mod.calculate(self.hero, mon)
            if now.can_win and now.total_damage == 0:
                continue
            cost_now = f"{now.total_damage} HP ({now.total_damage * 100 // max(1, self.hero.hp)} % of HP)" if now.can_win else "CANNOT WIN"
            later = []
            if steps:
                d_atk, price, cur, name = steps[0]
                probe = self.hero.copy()
                for k in (1, 2, 3):
                    probe.atk = self.hero.atk + k * d_atk
                    r = dmg_mod.calculate(probe, mon)
                    if r.can_win:
                        later.append(f"{k}× {name} ({k * price} {shop_unit(cur)}): {r.total_damage}")
            parts.append(f"{mon.name}@({x},{y}) costs {cost_now}" + (f"; after {', '.join(later)}" if later else ""))
        return " → the way there: " + " | ".join(parts) if parts else None

    def unlocks_something_needed(self, a: Action) -> bool:
        """The fight/door leads to an unreached shop, or to stat gems that make an unwinnable fight
        on this floor winnable — the prompt's rule 4/5 exception for paying a large HP price."""
        registered = self._registered_shop_tiles()
        floor_id = a.target_floor_id if a.remote is not None else self.current_floor.floor_id
        d_atk = d_def = 0
        for u in a.unlocks_tree or []:
            if u.get("type") == "shop" and (floor_id, *u["pos"]) not in registered:
                return True
            d_atk += u.get("atk", 0)
            d_def += u.get("def", 0)
        return bool((d_atk or d_def) and self._newly_winnable(d_atk, d_def))

    def hp_floor_alternative(self, chosen: Action, actions: list[Action]) -> Action | None:
        """Prompt rule 4 made mechanical on the tower: a fight costing > 40 % of current HP is
        replaced when a non-lethal progress action exists (not such a fight, not a dead end, not a
        key trade), unless the fight unlocks something needed. Confirmation gate: the same fight at
        the same stats is replaced once and executed if the LLM chooses it again (W1c: 18 repeats
        were each replaced by a key purchase). Returns the replacement or None."""
        if chosen.type != ActionType.FIGHT or chosen.damage_percent <= 40 or not chosen.can_win:
            return None
        if self.unlocks_something_needed(chosen):
            return None
        sig = (self.current_floor.floor_id, chosen.x, chosen.y, self.hero.atk, self.hero.def_)
        if sig in self._hp_floor_gated:
            return None
        allowed = [a for a in actions if a.action_id != chosen.action_id
                   and not (a.type == ActionType.FIGHT and (a.damage_percent > 40 or not a.can_win))
                   and not getattr(a, "is_dead_end", False)
                   and not (a.type == ActionType.SHOP_BUY
                            and not set(a.stat_changes or {}) & {"atk", "def", "mdef"})]
        if not allowed:
            return None
        self._hp_floor_gated.add(sig)
        fights = [a for a in allowed if a.type == ActionType.FIGHT]
        if fights:
            return min(fights, key=lambda a: a.total_damage)
        order = (ActionType.OPEN_DOOR, ActionType.SHOP_BUY, ActionType.RETURN_TO_FLOOR, ActionType.USE_STAIRS)
        return min(allowed, key=lambda a: order.index(a.type) if a.type in order else len(order))

    def _return_action_tree(self, a: Action) -> list[str]:
        """What is actually waiting on the target floor (from its up-stairs) at current stats."""
        idx = next((i for i, f in enumerate(self.floors) if f.floor_id == a.target_floor_id), None)
        if idx is None:
            return []
        st = self._floor_stats(idx)
        lines = []
        for f in sorted(st["win"], key=lambda f: f.total_damage)[:4]:
            unlock = f" → unlocks {', '.join(f.unlocks_items[:4])}" if getattr(f, "unlocks_items", None) else ""
            lines.append(f"     ⚔ {f.name} at ({f.x},{f.y}) dmg={f.total_damage}{unlock}")
        if len(st["win"]) > 4:
            lines.append(f"     … {len(st['win']) - 4} more winnable fight(s)")
        if st["items"]:
            lines.append("     items: " + ", ".join(f"{i.name}@({i.x},{i.y})" for i in st["items"][:6]))
        if st["doors"]:
            lines.append("     openable doors: " + ", ".join(f"{d.name}@({d.x},{d.y})" for d in st["doors"][:4]))
        if st["unwin"]:
            lines.append(f"     {len(st['unwin'])} fight(s) still unwinnable there")
        return lines

    @staticmethod
    def _insert_action_extras(text: str, extras: dict[int, list[str]]) -> str:
        """Insert extra lines after each numbered action's own block (before the next number)."""
        import re
        out: list[str] = []
        pending: list[str] = []
        num_re = re.compile(r"^\s{2}(\d+)\. \[")
        for line in text.splitlines():
            m = num_re.match(line)
            if m:
                out.extend(pending)
                pending = extras.get(int(m.group(1)), [])
            out.append(line)
        out.extend(pending)
        return "\n".join(out)

    def remaining_enemies(self) -> int:
        return self._make_state().remaining_enemies()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _make_state(self) -> GameState:
        """Create a single-floor GameState reflecting current multi-floor context."""
        if self._seals:
            self._update_seals()
        return GameState(
            floor=self.current_floor,
            hero=self.hero.copy(),
            goal="stairs",  # always target stairs in multi-floor
            max_turns=self.max_turns_per_floor,
            game_data=self.gd,
            lookahead_depth=self.lookahead_depth,
            _removed=set(self.per_floor_removed[self.current_floor_idx]),
        )

    def _apply_global_shop(self, action: Action) -> StepTrace:
        """Apply a global shop buy (shop on a different floor) — modify hero stats directly."""
        hero_snap = {
            "hp": self.hero.hp, "atk": self.hero.atk, "def": self.hero.def_,
            "money": self.hero.money, "exp": self.hero.exp,
            "x": self.hero.x, "y": self.hero.y,
        }
        D.apply_shop_effect(self.hero, action)
        if action.shop_choice == "cross":
            self.cross_given = True
            for fid, locs in self._cross_shows:
                self._reveal(fid, locs)
        hero_after = {
            "hp": self.hero.hp, "atk": self.hero.atk, "def": self.hero.def_,
            "money": self.hero.money, "exp": self.hero.exp,
            "x": self.hero.x, "y": self.hero.y,
        }
        trace = StepTrace(
            turn=self.total_turns,
            action=action,
            hero_before=hero_snap,
            hero_after=hero_after,
        )
        self.history.append(trace)
        return trace

    def _apply_stairs(self, action: Action) -> StepTrace:
        """Move hero up to the next floor."""
        hero_snap = {
            "hp": self.hero.hp, "atk": self.hero.atk, "def": self.hero.def_,
            "money": self.hero.money, "exp": self.hero.exp,
            "x": self.hero.x, "y": self.hero.y,
        }

        if self.is_last_floor:
            # Reached the top — goal complete
            self.goal_reached = True
        else:
            prev_floor = self.current_floor
            self.current_floor_idx += 1
            next_floor = self.current_floor
            self.visited_floor_idx.add(self.current_floor_idx)

            # Hero arrives at downFloor arrival pos of the next floor
            arrive_x, arrive_y = next_floor.down_floor
            self.hero.x = arrive_x
            self.hero.y = arrive_y

            self.floor_transitions.append({
                "from": prev_floor.floor_id,
                "to": next_floor.floor_id,
                "hero_hp": self.hero.hp,
                "turn": self.total_turns,
            })

            # Scan the new floor for deferred doors
            self._scan_and_defer_doors(self.current_floor_idx)

        trace = StepTrace(
            turn=self.total_turns,
            action=action,
            hero_before=hero_snap,
            hero_after=hero_snap,
        )
        self.history.append(trace)
        return trace

    def _apply_return_to_floor(self, action: Action) -> StepTrace:
        """Teleport hero back to a previous floor to open a deferred door."""
        hero_snap = {
            "hp": self.hero.hp, "atk": self.hero.atk, "def": self.hero.def_,
            "money": self.hero.money, "exp": self.hero.exp,
            "x": self.hero.x, "y": self.hero.y,
        }

        target_floor_id = action.target_floor_id
        target_idx = next(
            (i for i, f in enumerate(self.floors) if f.floor_id == target_floor_id),
            None,
        )
        if target_idx is None:
            # Shouldn't happen, but gracefully ignore
            return StepTrace(turn=self.total_turns, action=action,
                             hero_before=hero_snap, hero_after=hero_snap)

        prev_floor_id = self.current_floor.floor_id
        if action.name.startswith("revisit"):
            self._tried_revisits.add(self._revisit_signature(target_idx, self._floor_leftovers(target_idx)))
        else:
            self._tried_revisits.add(self._door_return_signature(target_idx, action.x, action.y))
        self.current_floor_idx = target_idx
        target_floor = self.current_floor

        # Hero arrives at upFloor arrival pos of the target floor
        arrive_x, arrive_y = target_floor.up_floor
        self.hero.x = arrive_x
        self.hero.y = arrive_y

        self.floor_transitions.append({
            "from": prev_floor_id,
            "to": target_floor.floor_id,
            "hero_hp": self.hero.hp,
            "turn": self.total_turns,
            "type": "return",
        })
        trace = StepTrace(
            turn=self.total_turns,
            action=action,
            hero_before=hero_snap,
            hero_after=hero_snap,
        )
        self.history.append(trace)
        return trace

    def _tower_key_budget_line(self) -> str:
        """Keys are shared by all floors: keys in hand + keys lying on visited floors vs their closed doors."""
        on, doors = {c: 0 for c in GameState._KEY_COLOURS}, {c: 0 for c in GameState._KEY_COLOURS}
        for idx in sorted(self.visited_floor_idx):
            probe = GameState(floor=self.floors[idx], hero=self.hero.copy(), goal="stairs", game_data=self.gd,
                              lookahead_depth=0, _removed=set(self.per_floor_removed[idx]))
            k, d = probe._key_inventory()
            for c in on:
                on[c] += k[c]
                doors[c] += d[c]
        parts = []
        for c in GameState._KEY_COLOURS:
            have = getattr(self.hero.keys, c)
            if not (have or on[c] or doors[c]):
                continue
            s = f"{c} {have} in hand + {on[c]} on visited floors = {have + on[c]} for {doors[c]} closed {c} door(s)"
            if have + on[c] < doors[c]:
                s += f" → at least {doors[c] - have - on[c]} {c} door(s) will stay closed"
            parts.append(s)
        return "Tower key budget (all visited floors): " + ("; ".join(parts) if parts else "no keys or doors")

    def _arrival(self, floor_idx: int) -> tuple[int, int]:
        """Where the hero stands on entering `floor_idx` from the current floor (down-stairs side when
        coming up, up-stairs side when going down)."""
        f = self.floors[floor_idx]
        if floor_idx == 0 or floor_idx < self.current_floor_idx:
            return f.up_floor
        return f.down_floor

    def _build_remote_actions(self, start_id: int) -> list[Action]:
        """MOTA_REMOTE_ACTIONS: every action of every other visited floor, as that floor's own GameState lists it
        (fights incl. unwinnable ones, doors incl. dead ends, items), plus the up-stairs of a visited floor whose
        next floor is unvisited. Shops are global already; stairs to visited floors are travel, not actions."""
        from dataclasses import replace as dc_replace
        out, next_id = [], start_id
        self._remote_probes = {}
        for idx in sorted(self.visited_floor_idx):
            if idx == self.current_floor_idx:
                continue
            f = self.floors[idx]
            probe = GameState(floor=f, hero=self.hero.copy(), goal="stairs", max_turns=self.max_turns_per_floor,
                              game_data=self.gd, lookahead_depth=self.lookahead_depth,
                              _removed=set(self.per_floor_removed[idx]))
            probe.hero.x, probe.hero.y = self._arrival(idx)
            self._remote_probes[f.floor_id] = probe
            for a in probe.get_actions():
                if a.type == ActionType.SHOP_BUY:
                    continue
                if a.type == ActionType.USE_STAIRS and (idx + 1 >= len(self.floors) or idx + 1 in self.visited_floor_idx):
                    continue
                shown = dc_replace(a, action_id=next_id)
                out.append(dc_replace(a, action_id=next_id, target_floor_id=f.floor_id, remote=shown))
                next_id += 1
        return out

    def _apply_remote(self, action: Action) -> StepTrace:
        """Walk to the action's floor (stairs are free) and perform it there."""
        target_idx = next(i for i, f in enumerate(self.floors) if f.floor_id == action.target_floor_id)
        prev_floor_id = self.current_floor.floor_id
        arrive = self._arrival(target_idx)
        self.current_floor_idx = target_idx
        self.hero.x, self.hero.y = arrive
        self.floor_transitions.append({"from": prev_floor_id, "to": self.current_floor.floor_id,
                                       "hero_hp": self.hero.hp, "turn": self.total_turns, "type": "remote"})
        inner = action.remote
        match = next((a for a in self._make_state().get_actions()
                      if a.type == inner.type and (a.x, a.y) == (inner.x, inner.y)), None)
        if match is None:  # state changed since the list was built: the walk itself is the step
            snap = {"hp": self.hero.hp, "atk": self.hero.atk, "def": self.hero.def_, "money": self.hero.money,
                    "exp": self.hero.exp, "x": self.hero.x, "y": self.hero.y}
            trace = StepTrace(turn=self.total_turns, action=action, hero_before=snap, hero_after=snap)
            self.history.append(trace)
            return trace
        if match.type == ActionType.USE_STAIRS:
            return self._apply_stairs(match)
        state = self._make_state()
        state.turn = self.total_turns - 1
        trace = state.apply_action(match)
        self.hero = state.hero.copy()
        self.per_floor_removed[self.current_floor_idx] = set(state.removed)
        if match.type == ActionType.FIGHT:
            self._after_battle(self.current_floor_idx, match.x, match.y)
            self._check_win(self.current_floor_idx, match.x, match.y)
        self._scan_and_defer_doors(self.current_floor_idx)
        self.history.append(trace)
        self._check_failure()
        return trace

    def _door_return_signature(self, floor_idx: int, x: int, y: int) -> tuple:
        return ("door", floor_idx, x, y, self.hero.atk, self.hero.def_, self.hero.hp,
                self.hero.keys.yellow, self.hero.keys.blue, self.hero.keys.red,
                len(self.per_floor_removed[floor_idx]))

    def _door_return_worthwhile(self, floor_idx: int, x: int, y: int) -> bool:
        """True if the deferred door is reachable from the floor's up-stairs and is not a
        dead end (opening it exposes something other than unwinnable enemies)."""
        floor = self.floors[floor_idx]
        probe = GameState(
            floor=floor,
            hero=self.hero.copy(),
            goal="stairs",
            max_turns=self.max_turns_per_floor,
            game_data=self.gd,
            lookahead_depth=1,
            _removed=set(self.per_floor_removed[floor_idx]),
        )
        probe.hero.x, probe.hero.y = floor.up_floor
        for a in probe.get_actions():
            if a.type == ActionType.OPEN_DOOR and (a.x, a.y) == (x, y):
                return not a.is_dead_end
        return False

    def _build_return_actions(self, start_id: int) -> list[Action]:
        """Build RETURN_TO_FLOOR actions for deferred doors now openable.

        Doors that are unreachable from the arrival stairs or that only expose
        unwinnable enemies are not offered (run 4 spent 300 turns bouncing to a
        [DEAD END] door), and a return that was taken and abandoned with nothing
        changed since is not offered again."""
        actions = []
        action_id = start_id
        seen: set[tuple[str, int, int]] = set()
        for dd in self.deferred_doors:
            key = (dd.floor_id, dd.x, dd.y)
            if key in seen:
                continue
            if not self.hero.keys.has_key(dd.door_type):
                continue
            # Don't offer return actions if we're already on that floor
            if dd.floor_id == self.current_floor.floor_id:
                continue
            seen.add(key)
            floor_idx = next((i for i, f in enumerate(self.floors) if f.floor_id == dd.floor_id), None)
            if floor_idx is None:
                continue
            if self._door_return_signature(floor_idx, dd.x, dd.y) in self._tried_revisits:
                continue
            if not self._door_return_worthwhile(floor_idx, dd.x, dd.y):
                continue
            a = Action(
                action_id=action_id,
                type=ActionType.RETURN_TO_FLOOR,
                x=dd.x,
                y=dd.y,
                name=f"{dd.door_type.value} door on {dd.floor_id}",
                target_floor_id=dd.floor_id,
            )
            actions.append(a)
            action_id += 1
        return actions

    def _floor_leftovers(self, floor_idx: int) -> tuple[int, int, int, int | None]:
        """(winnable fights, unwinnable fights, items, cheapest winnable fight cost) reachable
        on an earlier floor from its up-stairs."""
        floor = self.floors[floor_idx]
        probe = GameState(
            floor=floor,
            hero=self.hero.copy(),
            goal="stairs",
            max_turns=self.max_turns_per_floor,
            game_data=self.gd,
            lookahead_depth=0,
            _removed=set(self.per_floor_removed[floor_idx]),
        )
        probe.hero.x, probe.hero.y = floor.up_floor
        winnable = unwinnable = items = 0
        cheapest: int | None = None
        for a in probe.get_actions():
            if a.type == ActionType.FIGHT:
                if a.can_win:
                    winnable += 1
                    cheapest = a.total_damage if cheapest is None else min(cheapest, a.total_damage)
                else:
                    unwinnable += 1
            elif a.type == ActionType.COLLECT:
                items += 1
        return winnable, unwinnable, items, cheapest

    def _floor_leftover_summary(self, floor_idx: int) -> str:
        w, u, it, cheapest = self._floor_leftovers(floor_idx)
        if not (w or it):
            return ""
        floor = self.floors[floor_idx]
        parts = []
        if w:
            parts.append(f"{w} winnable fight{'s' if w != 1 else ''} (cheapest costs {cheapest} HP)")
        if it:
            parts.append(f"{it} item{'s' if it != 1 else ''}")
        if u:
            parts.append(f"{u} still unwinnable")
        return f"{floor.floor_id}: " + ", ".join(parts)

    def _revisit_signature(self, floor_idx: int, leftovers: tuple) -> tuple:
        w, u, it, cheapest = leftovers
        return (floor_idx, w, it, cheapest, self.hero.atk, self.hero.def_, self.hero.hp,
                self.hero.keys.yellow, self.hero.keys.blue, self.hero.keys.red)

    def _build_revisit_actions(self, start_id: int) -> list[Action]:
        """RETURN_TO_FLOOR actions for earlier floors with reachable items or winnable fights.

        A revisit that was already taken and abandoned with nothing changed since (same
        leftovers, same hero stats/keys) is not offered again — otherwise an agent that
        declines the only expensive fight loops between two floors forever."""
        actions = []
        action_id = start_id
        for idx in range(self.current_floor_idx):
            lo = self._floor_leftovers(idx)
            w, u, it, cheapest = lo
            if not (w or it):
                continue
            if self._revisit_signature(idx, lo) in self._tried_revisits:
                continue
            floor = self.floors[idx]
            fight_part = f"{w} winnable fight(s), cheapest {cheapest} HP" if w else "0 winnable fights"
            a = Action(
                action_id=action_id,
                type=ActionType.RETURN_TO_FLOOR,
                x=floor.up_floor[0], y=floor.up_floor[1],
                name=f"revisit: {fight_part}, {it} item(s) reachable",
                target_floor_id=floor.floor_id,
            )
            actions.append(a)
            action_id += 1
        return actions

    def _scan_and_defer_doors(self, floor_idx: int) -> None:
        """
        Scan a floor for locked doors that are BFS-reachable but can't be opened
        yet (no key). Add new ones to deferred_doors.

        Existing entries for doors that are now removed (opened) are pruned.
        """
        floor = self.floors[floor_idx]
        removed = self.per_floor_removed[floor_idx]

        # Place hero at the floor's downFloor arrival position for pathfinding
        arrive_pos = floor.down_floor
        if floor_idx == 0:
            arrive_pos = (self.hero.x, self.hero.y)

        reachable = pf.find_reachable(
            grid=floor.map,
            start_x=arrive_pos[0],
            start_y=arrive_pos[1],
            keys=self.hero.keys,
            removed=removed,
            stop_at_doors=True,
            height=floor.height,
            width=floor.width,
            include_paths=False,
            game_data=self.gd,
        )

        # Prune already-opened deferred doors (in removed set)
        self.deferred_doors = [
            dd for dd in self.deferred_doors
            if not (dd.floor_id == floor.floor_id and (dd.x, dd.y) in removed)
        ]

        # Collect BFS entries that are doors but inaccessible (key missing)
        existing_keys = {(dd.floor_id, dd.x, dd.y) for dd in self.deferred_doors}
        for (x, y), info in reachable.items():
            if info["type"] != "door":
                continue
            if info.get("accessible"):
                continue  # reachable and openable — not deferred
            key = (floor.floor_id, x, y)
            if key in existing_keys:
                continue
            door_type = info.get("door_type")
            if door_type is None:
                continue
            self.deferred_doors.append(DeferredDoor(
                floor_id=floor.floor_id,
                floor_idx=floor_idx,
                x=x,
                y=y,
                door_type=door_type,
            ))
            existing_keys.add(key)

    def _check_failure(self) -> None:
        if self.hero.hp <= 0:
            self.failed = True
            self.failure_reason = "Hero died"
        elif self.total_turns >= self.max_total_turns:
            self.failed = True
            self.failure_reason = f"Total turn limit ({self.max_total_turns}) exceeded"
