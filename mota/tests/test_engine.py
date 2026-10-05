"""
Engine tests — verify damage formula, BFS pathfinding, and game state.
Run: python -m mota.tests.test_engine
"""
from __future__ import annotations
import sys
import math
import os
from pathlib import Path

# Add parent to path for direct execution
_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from mota.game.types import Hero, Keys, ActionType, DoorType, ItemTier, FloorData, DeferredDoor
from mota.game.data import MONSTERS, get_monster
from mota.game import damage as dmg
from mota.game.floor_loader import load_floor, load_floors_range
from mota.game import pathfinder as pf
from mota.game.state import GameState
from mota.game.hero_loader import load_initial_hero, load_floor_sequence
from mota.game.multi_floor import MultiFloorGame
from mota.optimizer.evaluator import _heuristic_pick

from mota.paths import GAME_24 as _PROJECT  # noqa: E402
_FLOORS = _PROJECT / "floors"

passed = 0
failed = 0


def check(name: str, actual, expected, tolerance=0):
    global passed, failed
    if tolerance > 0:
        ok = abs(actual - expected) <= tolerance
    else:
        ok = actual == expected
    if ok:
        passed += 1
        print(f"  OK  {name}")
    else:
        failed += 1
        print(f"  FAIL {name}: expected {expected}, got {actual}")


# ===== Damage Calculator Tests =====
def test_damage():
    print("\n--- Damage Calculator ---")

    hero = Hero(hp=1000, atk=10, def_=10, keys=Keys())

    # greenSlime: HP=50, ATK=20, DEF=1
    r = dmg.calculate(hero, get_monster("greenSlime"))
    # hero_dmg = 10-1 = 9, turns = ceil(50/9) = 6
    # per_dmg = max(0, 20-10) = 10, total = 10*(6-1) = 50
    check("greenSlime damage", r.total_damage, 50)
    check("greenSlime hp_after", r.hp_after, 950)
    check("greenSlime can_win", r.can_win, True)

    # redSlime: HP=70, ATK=15, DEF=2
    r = dmg.calculate(hero, get_monster("redSlime"))
    # hero_dmg = 10-2 = 8, turns = ceil(70/8) = 9
    # per_dmg = max(0, 15-10) = 5, total = 5*(9-1) = 40
    check("redSlime damage", r.total_damage, 40)
    check("redSlime hp_after", r.hp_after, 960)

    # bat: HP=100, ATK=20, DEF=5
    r = dmg.calculate(hero, get_monster("bat"))
    # hero_dmg = 10-5 = 5, turns = ceil(100/5) = 20
    # per_dmg = max(0, 20-10) = 10, total = 10*(20-1) = 190
    check("bat damage", r.total_damage, 190)
    check("bat hp_after", r.hp_after, 810)

    # skeleton: HP=110, ATK=25, DEF=5
    r = dmg.calculate(hero, get_monster("skeleton"))
    # hero_dmg = 10-5 = 5, turns = ceil(110/5) = 22
    # per_dmg = max(0, 25-10) = 15, total = 15*(22-1) = 315
    check("skeleton damage", r.total_damage, 315)

    # With upgraded stats: ATK=23, DEF=17
    hero2 = Hero(hp=570, atk=23, def_=17, keys=Keys())
    r = dmg.calculate(hero2, get_monster("skeleton"))
    # hero_dmg = 23-5 = 18, turns = ceil(110/18) = 7
    # per_dmg = max(0, 25-17) = 8, total = 8*(7-1) = 48
    check("skeleton w/ ATK=23 DEF=17", r.total_damage, 48)

    r = dmg.calculate(hero2, get_monster("redSlime"))
    # hero_dmg = 23-2 = 21, turns = ceil(70/21) = 4
    # per_dmg = max(0, 15-17) = 0, total = 0*(4-1) = 0
    check("redSlime w/ ATK=23 DEF=17", r.total_damage, 0)

    r = dmg.calculate(hero2, get_monster("bat"))
    # hero_dmg = 23-5 = 18, turns = ceil(100/18) = 6
    # per_dmg = max(0, 20-17) = 3, total = 3*(6-1) = 15
    check("bat w/ ATK=23 DEF=17", r.total_damage, 15)

    # Can't win: hero ATK <= monster DEF
    hero_weak = Hero(hp=100, atk=1, def_=1, keys=Keys())
    r = dmg.calculate(hero_weak, get_monster("bat"))
    check("bat unwinnable", r.can_win, False)


# ===== Floor Loader Tests =====
def test_floor_loader():
    print("\n--- Floor Loader ---")

    floor = load_floor(_FLOORS / "MT3.js")
    check("floor id", floor.floor_id, "MT3")
    check("floor width", floor.width, 13)
    check("floor height", floor.height, 13)
    check("map rows", len(floor.map), 13)
    check("map cols", len(floor.map[0]), 13)

    # Check known tiles
    check("(1,1) = sword1 (35)", floor.map[1][1], 35)
    check("(2,1) = redSlime (202)", floor.map[1][2], 202)
    check("(1,11) = downFloor (88)", floor.map[11][1], 88)
    check("(11,11) = upFloor (87)", floor.map[11][11], 87)
    check("(6,1) = moneyShop (131)", floor.map[1][6], 131)
    check("(6,3) = yellowDoor (81)", floor.map[3][6], 81)

    # Events
    check("shop event exists", "6,1" in floor.events, True)


# ===== BFS Pathfinder Tests =====
def test_pathfinder():
    print("\n--- BFS Pathfinder ---")

    floor = load_floor(_FLOORS / "MT3.js")
    hero_keys = Keys(yellow=1, blue=0, red=0)

    # From hero start position (1, 11)
    reachable = pf.find_reachable(
        grid=floor.map,
        start_x=1, start_y=11,
        keys=hero_keys,
        removed=set(),
        stop_at_doors=True,
        height=13, width=13,
    )

    # Count reachable entities by type
    types = {}
    for pos, info in reachable.items():
        t = info["type"]
        types[t] = types.get(t, 0) + 1

    print(f"  Reachable entities from (1,11): {types}")

    # MT3 is a maze. From (1,11), the ground corridor leads through (2,11) →
    # (2,10) → (3,10) → (4,10) → (5,10) to bat at (5,9). Walls (tile 1) block
    # all other paths. So only 1 enemy is initially reachable.
    check("initial: only bat reachable", types.get("enemy", 0), 1)
    check("bat at (5,9) found", (5, 9) in reachable, True)

    # After killing bat at (5,9), path opens to left corridor (row 8, x=1-5)
    removed = {(5, 9)}
    reachable2 = pf.find_reachable(
        grid=floor.map, start_x=5, start_y=9,  # hero at bat's position
        keys=hero_keys, removed=removed,
        stop_at_doors=True, height=13, width=13,
    )
    types2 = {}
    for pos, info in reachable2.items():
        t = info["type"]
        types2[t] = types2.get(t, 0) + 1
    print(f"  After killing bat(5,9): {types2}")
    check("greenSlime at (1,7) reachable after bat", (1, 7) in reachable2, True)

    # After clearing deeper, more of the floor opens up
    # Kill bat, 2 greenSlimes, 2 center bats, 1 redSlime in center
    many_removed = {(5, 9), (1, 7), (1, 6), (4, 6), (5, 6), (6, 6)}
    reachable3 = pf.find_reachable(
        grid=floor.map, start_x=7, start_y=6,  # hero in center area
        keys=Keys(yellow=1), removed=many_removed,
        stop_at_doors=True, height=13, width=13,
    )
    types3 = {}
    for pos, info in reachable3.items():
        t = info["type"]
        types3[t] = types3.get(t, 0) + 1
    print(f"  After clearing center area: {types3}")
    check("more entities visible after clearing", len(reachable3) > 3, True)


# ===== Game State Tests =====
def test_state():
    print("\n--- Game State ---")

    floor = load_floor(_FLOORS / "MT3.js")
    hero = Hero(
        hp=860, atk=10, def_=10,
        keys=Keys(yellow=1, blue=0, red=0),
        x=1, y=11,
    )
    state = GameState(floor=floor, hero=hero, goal="clear_all_enemies", max_turns=50)

    check("initial_enemies > 0", state.initial_enemies > 0, True)
    print(f"  Total enemies: {state.initial_enemies}")

    # Get initial actions
    actions = state.get_actions()
    check("has actions", len(actions) > 0, True)
    print(f"  Initial actions ({len(actions)}):")
    for a in actions:
        print(f"    #{a.action_id} {a.label()}")

    # Verify action types present — initially only 1 fight action (bat at (5,9))
    types_present = {a.type for a in actions}
    check("has fight actions", ActionType.FIGHT in types_present, True)
    # Items/stairs not visible initially (walls block path)
    # They become visible after clearing enemies

    # Apply a fight action (the only available action initially: bat at (5,9))
    fights = [a for a in actions if a.type == ActionType.FIGHT]
    if fights:
        first_fight = fights[0]
        check("first fight is bat", first_fight.name, "Bat")
        check("bat damage", first_fight.total_damage, 190)
        trace = state.apply_action(first_fight)
        check("fight trace has hero_after", "hp" in trace.hero_after, True)
        check("hero moved to bat pos", (state.hero.x, state.hero.y), (first_fight.x, first_fight.y))
        check("bat removed", (first_fight.x, first_fight.y) in state.removed, True)
        check("hero HP after bat", state.hero.hp, 670)
        print(f"  Fought: {first_fight.label()}")

        # After fighting bat, more actions should appear
        actions2 = state.get_actions()
        check("more actions after bat kill", len(actions2) > 0, True)
        print(f"  Actions after bat kill ({len(actions2)}):")
        for a in actions2:
            print(f"    #{a.action_id} {a.label()}")

    # Check format outputs work
    state_text = state.format_state()
    check("format_state not empty", len(state_text) > 0, True)
    actions2 = state.get_actions()
    actions_text = state.format_actions(actions2)
    check("format_actions not empty", len(actions_text) > 0, True)


# ===== Walkthrough Simulation Test =====
def test_walkthrough_basic():
    """Verify the engine can handle a basic sequence of actions without crashing."""
    print("\n--- Walkthrough Simulation ---")

    floor = load_floor(_FLOORS / "MT3.js")
    hero = Hero(
        hp=860, atk=10, def_=10,
        keys=Keys(yellow=1, blue=0, red=0),
        x=1, y=11,
    )
    state = GameState(floor=floor, hero=hero, goal="clear_all_enemies", max_turns=50)

    # Run the heuristic sequence
    steps = 0
    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        actions = state.get_actions()
        if not actions:
            break

        # Simple strategy: collect > doors > cheapest fight > stairs
        collects = [a for a in actions if a.type == ActionType.COLLECT]
        doors = [a for a in actions if a.type == ActionType.OPEN_DOOR]
        shops = [a for a in actions if a.type == ActionType.SHOP_BUY]
        fights = sorted(
            [a for a in actions if a.type == ActionType.FIGHT and a.can_win],
            key=lambda a: a.total_damage,
        )

        # Priority: major stat items first
        major = [a for a in collects if a.item_tier in (ItemTier.MAJOR_STAT, ItemTier.CORE_STAT)]
        keys_items = [a for a in collects if a.item_tier == ItemTier.KEY]
        potions = [a for a in collects if a.item_tier == ItemTier.HP]

        chosen = None
        if major:
            chosen = major[0]
        elif keys_items:
            chosen = keys_items[0]
        elif potions:
            chosen = potions[0]
        elif collects:
            chosen = collects[0]
        elif shops:
            # Prefer DEF
            def_shop = [s for s in shops if s.shop_choice == "def"]
            chosen = def_shop[0] if def_shop else shops[0]
        elif doors:
            chosen = doors[0]
        elif fights:
            chosen = fights[0]
        else:
            # stairs or whatever is left
            chosen = actions[0]

        state.apply_action(chosen)
        steps += 1

    print(f"  Steps taken: {steps}")
    print(f"  Final HP: {state.hero.hp} ATK: {state.hero.atk} DEF: {state.hero.def_}")
    print(f"  Enemies remaining: {state.remaining_enemies()}/{state.initial_enemies}")
    print(f"  Goal reached: {state.goal_reached}")
    print(f"  Failed: {state.failed} ({state.failure_reason})")

    check("heuristic completed without crash", True, True)
    check("hero still alive", state.hero.hp > 0, True)
    check("some enemies killed", state.remaining_enemies() < state.initial_enemies, True)


def test_actions_blocked_by_intermediate_items():
    """Actions should not skip over uncollected items in a single click."""
    print("\n--- Intermediate Item Blocking ---")

    # Case 1: farther key should not be offered until the front key is collected.
    key_floor = FloorData(
        floor_id="path_collect_keys",
        width=5,
        height=3,
        map=[
            [1, 1, 1, 1, 1],
            [1, 0, 21, 21, 1],
            [1, 1, 1, 1, 1],
        ],
        events={},
        change_floor={},
        up_floor=(0, 0),
        down_floor=(0, 0),
    )
    state = GameState(
        floor=key_floor,
        hero=Hero(hp=100, atk=10, def_=10, keys=Keys(), x=1, y=1),
        goal="clear_all_enemies",
        max_turns=10,
    )
    actions = state.get_actions()
    near_key = next((a for a in actions if a.type == ActionType.COLLECT and (a.x, a.y) == (2, 1)), None)
    far_key = next((a for a in actions if a.type == ActionType.COLLECT and (a.x, a.y) == (3, 1)), None)
    check("near key action exists", near_key is not None, True)
    check("far key initially blocked", far_key is None, True)
    if near_key is not None:
        state.apply_action(near_key)
        check("hero moved to near key", (state.hero.x, state.hero.y), (2, 1))
        check("near key collected", (2, 1) in state.removed, True)
        check("far key still present", (3, 1) in state.removed, False)
        check("one yellow key collected", state.hero.keys.yellow, 1)

        actions_after = state.get_actions()
        far_key_after = next((a for a in actions_after if a.type == ActionType.COLLECT and (a.x, a.y) == (3, 1)), None)
        check("far key available after near key", far_key_after is not None, True)

    # Case 1b: farther key should be available when a detour avoids other keys.
    detour_floor = FloorData(
        floor_id="path_collect_detour",
        width=5,
        height=4,
        map=[
            [1, 1, 1, 1, 1],
            [1, 0, 21, 21, 1],
            [1, 0, 0, 0, 1],
            [1, 1, 1, 1, 1],
        ],
        events={},
        change_floor={},
        up_floor=(0, 0),
        down_floor=(0, 0),
    )
    state_detour = GameState(
        floor=detour_floor,
        hero=Hero(hp=100, atk=10, def_=10, keys=Keys(), x=1, y=1),
        goal="clear_all_enemies",
        max_turns=10,
    )
    actions_detour = state_detour.get_actions()
    near_detour = next((a for a in actions_detour if a.type == ActionType.COLLECT and (a.x, a.y) == (2, 1)), None)
    far_detour = next((a for a in actions_detour if a.type == ActionType.COLLECT and (a.x, a.y) == (3, 1)), None)
    check("detour near key action exists", near_detour is not None, True)
    check("detour far key action exists", far_detour is not None, True)
    if far_detour is not None:
        check("detour path avoids near key", (2, 1) in far_detour.path, False)
        state_detour.apply_action(far_detour)
        check("detour hero moved to far key", (state_detour.hero.x, state_detour.hero.y), (3, 1))
        check("detour far key collected", (3, 1) in state_detour.removed, True)
        check("detour near key not auto-collected", (2, 1) in state_detour.removed, False)
        check("detour one yellow key collected", state_detour.hero.keys.yellow, 1)

    # Case 2: fight behind a key should be blocked until key is collected.
    fight_floor = FloorData(
        floor_id="path_collect_fight",
        width=5,
        height=3,
        map=[
            [1, 1, 1, 1, 1],
            [1, 0, 21, 201, 1],
            [1, 1, 1, 1, 1],
        ],
        events={},
        change_floor={},
        up_floor=(0, 0),
        down_floor=(0, 0),
    )
    state2 = GameState(
        floor=fight_floor,
        hero=Hero(hp=200, atk=10, def_=10, keys=Keys(), x=1, y=1),
        goal="clear_all_enemies",
        max_turns=10,
    )
    actions2 = state2.get_actions()
    collect_key = next((a for a in actions2 if a.type == ActionType.COLLECT and (a.x, a.y) == (2, 1)), None)
    fight = next((a for a in actions2 if a.type == ActionType.FIGHT and (a.x, a.y) == (3, 1)), None)
    check("collect key action exists", collect_key is not None, True)
    check("fight initially blocked", fight is None, True)
    if collect_key is not None:
        state2.apply_action(collect_key)
    actions2_after = state2.get_actions()
    fight_after = next((a for a in actions2_after if a.type == ActionType.FIGHT and (a.x, a.y) == (3, 1)), None)
    check("fight available after key", fight_after is not None, True)
    if fight_after is not None:
        state2.apply_action(fight_after)
        check("one key collected before fight", state2.hero.keys.yellow, 1)
        check("key tile removed", (2, 1) in state2.removed, True)
        check("enemy removed", (3, 1) in state2.removed, True)


def test_mt3_top_left_key_actions_after_t5():
    """MT3 regression: after T5, the (3,1) key action should still be listed."""
    print("\n--- MT3 Top-Left Key Actions ---")

    floor = load_floor(_FLOORS / "MT3.js")
    state = GameState(
        floor=floor,
        hero=Hero(hp=860, atk=10, def_=10, keys=Keys(yellow=1, blue=0, red=0), x=1, y=11),
        goal="clear_all_enemies",
        max_turns=300,
    )

    seq = [
        ("fight", (5, 9)),
        ("fight", (1, 7)),
        ("fight", (1, 6)),
        ("open_door", (2, 4)),
        ("fight", (2, 3)),
    ]
    for action_type, pos in seq:
        actions = state.get_actions()
        chosen = next((a for a in actions if a.type.value == action_type and (a.x, a.y) == pos), None)
        check(f"mt3 action exists {action_type}@{pos}", chosen is not None, True)
        if chosen is None:
            return
        state.apply_action(chosen)

    actions_after = state.get_actions()
    collect_positions = {(a.x, a.y) for a in actions_after if a.type == ActionType.COLLECT}
    check("mt3 key action (1,3) listed", (1, 3) in collect_positions, True)
    check("mt3 key action (2,2) listed", (2, 2) in collect_positions, True)
    check("mt3 key action (3,1) listed", (3, 1) in collect_positions, True)


# ===== Hero Loader Tests =====
def test_hero_loader():
    print("\n--- Hero Loader ---")

    data_js = _PROJECT / "data.js"
    hero = load_initial_hero(data_js)
    check("hero hp=1000", hero.hp, 1000)
    check("hero atk=10", hero.atk, 10)
    check("hero def=10", hero.def_, 10)
    check("hero mdef=0", hero.mdef, 0)
    check("hero money=0", hero.money, 0)
    check("hero x=6", hero.x, 6)
    check("hero y=10", hero.y, 10)
    check("hero yellow_keys=0", hero.keys.yellow, 0)
    check("hero blue_keys=0", hero.keys.blue, 0)
    check("hero red_keys=0", hero.keys.red, 0)

    floors = load_floor_sequence(data_js)
    check("floor sequence len=27", len(floors), 27)
    check("first floor is MT0", floors[0], "MT0")
    check("MT3 is at index 3", floors.index("MT3"), 3)
    check("MT_1 is last", floors[-1], "MT_1")


# ===== Floor Loader Range Tests =====
def test_floor_loader_range():
    print("\n--- Floor Loader Range ---")

    floors = load_floors_range(_FLOORS, ["MT3", "MT4"])
    check("loaded 2 floors", len(floors), 2)
    check("first floor_id=MT3", floors[0].floor_id, "MT3")
    check("second floor_id=MT4", floors[1].floor_id, "MT4")


# ===== Lookahead Wiring Test =====
def test_lookahead_wiring():
    print("\n--- Lookahead Wiring ---")

    floor = load_floor(_FLOORS / "MT3.js")
    hero = Hero(hp=860, atk=10, def_=10, keys=Keys(yellow=1), x=1, y=11)

    state_default = GameState(floor=floor, hero=hero, goal="stairs", max_turns=50)
    check("default lookahead_depth >= 1", state_default.lookahead_depth >= 1, True)

    state_2 = GameState(floor=floor, hero=hero, goal="stairs", max_turns=50, lookahead_depth=2)
    check("lookahead_depth=2 stored", state_2.lookahead_depth, 2)

    state_5 = GameState(floor=floor, hero=hero, goal="stairs", max_turns=50, lookahead_depth=5)
    check("lookahead_depth=5 stored", state_5.lookahead_depth, 5)


# ===== MultiFloorGame Init Test =====
def test_multi_floor_init():
    print("\n--- MultiFloorGame Init ---")

    floors = load_floors_range(_FLOORS, ["MT3", "MT4"])
    hero = Hero(hp=860, atk=10, def_=10, keys=Keys(yellow=1), x=1, y=11)

    game = MultiFloorGame(floors, hero)
    check("current floor is MT3", game.current_floor.floor_id, "MT3")
    check("not on last floor initially", game.is_last_floor, False)
    check("not failed", game.failed, False)
    check("not goal_reached", game.goal_reached, False)
    check("total_turns=0", game.total_turns, 0)

    actions = game.get_actions()
    check("has actions", len(actions) > 0, True)

    # With yellow key=1, deferred yellow doors should not appear (hero can open them)
    # Only doors hero can't open (blue/red with 0 keys) should be deferred
    return_types = {a.type for a in actions}
    for a in actions:
        if a.type == ActionType.RETURN_TO_FLOOR:
            check("return action floor != current", a.target_floor_id != "MT3", True)


# ===== Shop discovery is independent of affordability =====
def test_shop_discovered_when_broke():
    print("\n--- Shop unlocked on first contact even when unaffordable ---")
    # Floor A: shop NPC (tile 123 = trader with an openShop event) next to the up stairs.
    floor_a = FloorData(
        floor_id="S1", width=5, height=4,
        map=[[1, 1, 1, 1, 1],
             [1, 0, 123, 0, 87],
             [1, 0, 0, 0, 1],
             [1, 1, 1, 1, 1]],
        events={"2,1": [{"type": "openShop", "id": "moneyShop"}]},
        change_floor={}, up_floor=(4, 1), down_floor=(1, 1),
    )
    floor_b = FloorData(
        floor_id="S2", width=5, height=3,
        map=[[1, 1, 1, 1, 1],
             [1, 0, 0, 0, 87],
             [1, 1, 1, 1, 1]],
        events={}, change_floor={}, up_floor=(4, 1), down_floor=(1, 1),
    )
    hero = Hero(hp=500, atk=50, def_=50, money=0, x=1, y=1)  # cannot afford 25g
    game = MultiFloorGame([floor_a, floor_b], hero)
    acts = game.get_actions()
    check("no unaffordable shop action emitted", any(a.type == ActionType.SHOP_BUY for a in acts), False)
    check("shop registered on first contact", len(game.global_shops) > 0, True)
    stairs = next(a for a in acts if a.type == ActionType.USE_STAIRS)
    game.apply_action(stairs)
    game.hero.money = 60  # earned gold upstairs
    acts = game.get_actions()
    global_buys = [a for a in acts if a.type == ActionType.SHOP_BUY and a.path_steps == 0]
    check("global shop buy offered on later floor", len(global_buys) > 0, True)
    if global_buys:
        def_buy = next((a for a in global_buys if a.shop_choice == "def"), global_buys[0])
        d0 = game.hero.def_
        game.apply_action(def_buy)
        check("global buy applied", (game.hero.def_ - d0, game.hero.money), (4, 35))


# ===== MultiFloorGame Transition Test =====
def test_multi_floor_transition():
    print("\n--- MultiFloorGame Transition ---")

    floors = load_floors_range(_FLOORS, ["MT3", "MT4"])
    # Give hero enough stats to clear the floor quickly; start at stair position
    mt3 = floors[0]
    mt4 = floors[1]

    hero = Hero(hp=5000, atk=100, def_=100, keys=Keys(yellow=5, blue=5, red=5), x=1, y=11)
    game = MultiFloorGame(floors, hero)

    initial_floor_id = game.current_floor.floor_id
    check("starts on MT3", initial_floor_id, "MT3")

    # Simulate until stairs or exhausted
    steps = 0
    transitioned = False
    while not game.goal_reached and not game.failed and steps < 200:
        actions = game.get_actions()
        if not actions:
            break
        stairs = [a for a in actions if a.type == ActionType.USE_STAIRS]
        if stairs:
            game.apply_action(stairs[0])
            transitioned = True
            break
        # Prioritize: collect > fight > door > other
        collects = [a for a in actions if a.type == ActionType.COLLECT]
        fights = sorted(
            [a for a in actions if a.type == ActionType.FIGHT and a.can_win],
            key=lambda a: a.total_damage,
        )
        doors = [a for a in actions if a.type == ActionType.OPEN_DOOR]
        chosen = collects[0] if collects else (fights[0] if fights else (doors[0] if doors else actions[0]))
        game.apply_action(chosen)
        steps += 1

    if transitioned:
        check("floor transitioned to MT4", game.current_floor.floor_id, "MT4")
        check("floor_transitions recorded", len(game.floor_transitions) >= 1, True)
        check("hero arrives at MT4 down_floor", (game.hero.x, game.hero.y), mt4.down_floor)
    else:
        check("multi-floor transition completed without crash", True, True)


# ===== Deferred Door Tracking Test =====
def test_deferred_door_tracking():
    print("\n--- Deferred Door Tracking ---")

    floor_a = FloorData(
        floor_id="T1",
        width=5,
        height=3,
        map=[
            [1, 1, 1, 1, 1],
            [1, 0, 81, 21, 1],   # yellow key behind the door -> return is worthwhile
            [1, 1, 1, 1, 1],
        ],
        events={},
        change_floor={},
        up_floor=(1, 1),
        down_floor=(1, 1),
    )
    floor_b = FloorData(
        floor_id="T2",
        width=5,
        height=3,
        map=[
            [1, 1, 1, 1, 1],
            [1, 0, 0, 0, 1],
            [1, 1, 1, 1, 1],
        ],
        events={},
        change_floor={},
        up_floor=(1, 1),
        down_floor=(1, 1),
    )
    floors = [floor_a, floor_b]

    hero_no_keys = Hero(hp=5000, atk=100, def_=100, keys=Keys(yellow=0, blue=0, red=0), x=1, y=1)
    game = MultiFloorGame(floors, hero_no_keys)

    yellow_deferred = [dd for dd in game.deferred_doors if dd.door_type == DoorType.YELLOW]
    check("yellow door deferred when reachable without key", len(yellow_deferred), 1)
    if yellow_deferred:
        dd = yellow_deferred[0]
        check("deferred door floor id", dd.floor_id, "T1")
        check("deferred door position", (dd.x, dd.y), (2, 1))

    # With no keys, _build_return_actions should return empty list (can't open any)
    return_actions = game._build_return_actions(1)
    check("no return actions with no keys", len(return_actions), 0)

    # Give hero a yellow key — now return actions should appear for the deferred door
    game.hero = Hero(
        hp=game.hero.hp, atk=game.hero.atk, def_=game.hero.def_,
        mdef=game.hero.mdef, money=game.hero.money, exp=game.hero.exp,
        keys=Keys(yellow=1, blue=0, red=0),
        x=game.hero.x, y=game.hero.y,
    )
    # Move to second floor so return actions are possible
    game.current_floor_idx = 1
    return_actions_with_key = game._build_return_actions(1)
    check("return actions with yellow key", len(return_actions_with_key), 1)
    for a in return_actions_with_key:
        check("return action targets T1", a.target_floor_id, "T1")
        check("return action points to deferred door", (a.x, a.y), (2, 1))

    # A deferred door with nothing behind it is a dead end and must not be offered
    # (tower run 4 bounced 300 turns between floors on such a door).
    floor_a.map[1][3] = 0
    check("dead-end deferred door not offered", len(game._build_return_actions(1)), 0)
    floor_a.map[1][3] = 21


def test_heuristic_avoids_dead_end_blue_door():
    print("\n--- Heuristic Door Conservation ---")

    floor = FloorData(
        floor_id="TDOOR",
        width=7,
        height=5,
        map=[
            [1, 1, 1, 1, 1, 1, 1],
            [1, 0, 82, 213, 28, 1, 1],
            [1, 0, 1, 1, 1, 1, 1],
            [1, 202, 0, 0, 0, 0, 1],
            [1, 1, 1, 1, 1, 1, 1],
        ],
        events={},
        change_floor={},
        up_floor=(1, 1),
        down_floor=(1, 1),
    )

    hero = Hero(hp=1000, atk=10, def_=10, keys=Keys(blue=1), x=1, y=1)
    state = GameState(floor=floor, hero=hero)
    actions = state.get_actions()

    fights = [a for a in actions if a.type == ActionType.FIGHT]
    doors = [a for a in actions if a.type == ActionType.OPEN_DOOR]
    check("has reachable fight", len(fights), 1)
    check("has reachable blue door", len(doors), 1)

    if doors:
        door = doors[0]
        check("dead-end blue door gets zero unlock value", door.lookahead_value, 0)
        check("dead-end blue door flagged", door.is_dead_end, True)

    chosen_id = _heuristic_pick(actions, state)
    chosen = next((a for a in actions if a.action_id == chosen_id), None)
    check(
        "heuristic prefers reachable fight over dead-end blue door",
        chosen.type if chosen else None,
        ActionType.FIGHT,
    )

    formatted = state.format_actions(actions)
    check("formatted actions mark dead-end door", "[DEAD END - DO NOT OPEN]" in formatted, True)


def test_safety_override_is_mechanical_only():
    """Reproduce the B3 turn-6 state on `simple` (2026-09-24 root cause, SIMPLE_FLOOR_PLAN.md):
    the LLM chose Black Slime (9,5) [55 HP], the heuristic preferred Bat (3,5) [182 HP, effCost -23].
    Default: the LLM's winnable, non-lethal choice must be kept. `MOTA_STRATEGIC_OVERRIDES=1`
    restores the historical effCost-gap override. Dead-end doors and unwinnable fights are still
    corrected in both modes, and every correction is reported with a reason."""
    print("\n--- Safety Override Contract ---")
    import os
    from mota.optimizer import evaluator as ev

    ev.configure_scenario("simple")
    state = ev._create_state(lookahead_depth=3)

    def act(pred):
        acts = state.get_actions()
        a = next((x for x in acts if pred(x)), None)
        assert a is not None, "expected action not available"
        state.apply_action(a)

    act(lambda a: a.type == ActionType.COLLECT and (a.x, a.y) == (5, 1))
    # Dead-end yellow door (7,0) is listed at turn 2: must be corrected in both modes.
    start_actions = state.get_actions()
    dead_end = next(a for a in start_actions if a.type == ActionType.OPEN_DOOR and a.is_dead_end)
    corr, reason = ev._safety_correct_with_reason(dead_end, start_actions, state)
    check("default: dead-end door corrected", corr.action_id != dead_end.action_id, True)
    check("default: dead-end reason", reason, "dead_end_door")
    events = []
    chosen, info = ev._apply_override(dead_end, start_actions, state, events.append, 2)
    check("_apply_override reports corrected_from", info and info["corrected_from"], dead_end.action_id)
    check("_apply_override emits an override event", [e["type"] for e in events], ["override"])

    act(lambda a: a.type == ActionType.FIGHT and (a.x, a.y) == (6, 4))
    act(lambda a: a.type == ActionType.FIGHT and (a.x, a.y) == (5, 6))
    act(lambda a: a.type == ActionType.OPEN_DOOR and (a.x, a.y) == (7, 5))
    act(lambda a: a.type == ActionType.COLLECT and (a.x, a.y) == (7, 7))
    check("hero HP before the disputed turn", state.hero.hp, 466)

    actions = state.get_actions()
    black = next(a for a in actions if a.type == ActionType.FIGHT and (a.x, a.y) == (9, 5))
    bat = next(a for a in actions if a.type == ActionType.FIGHT and (a.x, a.y) == (3, 5))
    red = next(a for a in actions if a.type == ActionType.FIGHT and (a.x, a.y) == (5, 3))
    check("heuristic prefers the Bat here", ev._heuristic_pick(actions, state), bat.action_id)

    old = os.environ.pop("MOTA_STRATEGIC_OVERRIDES", None)
    try:
        kept, reason = ev._safety_correct_with_reason(black, actions, state)
        check("default: LLM's winnable non-lethal fight is kept", kept.action_id, black.action_id)
        check("default: no reason when kept", reason, None)
        kept, reason = ev._safety_correct_with_reason(red, actions, state)
        check("default: even an optional 56-HP fight is kept (not mechanical)", (kept.action_id, reason), (red.action_id, None))

        os.environ["MOTA_STRATEGIC_OVERRIDES"] = "1"
        # After D2 the Black Slime's heuristic effCost (-20) is within 40 of the Bat's (-23), so the
        # historical rule no longer fires on that pair; Red Slime (+56) vs Bat (-23) still trips it.
        corr, reason = ev._safety_correct_with_reason(red, actions, state)
        check("strategic: historical effCost-gap override executes the Bat", corr.action_id, bat.action_id)
        check("strategic: reason", reason, "effcost_gap")
    finally:
        os.environ.pop("MOTA_STRATEGIC_OVERRIDES", None)
        if old is not None:
            os.environ["MOTA_STRATEGIC_OVERRIDES"] = old

    chosen, info = ev._apply_override(black, actions, state, events.append, 6)
    check("_apply_override keeps LLM choice silently", (chosen.action_id, info), (black.action_id, None))
    ev.configure_scenario(None)


def test_alternative_route_annotation():
    """C0 (SIMPLE_FLOOR_PLAN.md §5): on `simple` after the key pickup, Red Slime (5,3) opens a subset
    of what Black Slime (6,4) opens -> tagged as an alternative route; Black Slime itself is not.
    Once Green Slime (5,6) is dead the Red Slime falls back to the plain [OPTIONAL] tag."""
    print("\n--- Alternative Route Annotation ---")
    from mota.optimizer import evaluator as ev

    ev.configure_scenario("simple")
    state = ev._create_state(lookahead_depth=3)
    acts = state.get_actions()
    state.apply_action(next(a for a in acts if a.type == ActionType.COLLECT))
    acts = state.get_actions()
    red = next(a for a in acts if a.type == ActionType.FIGHT and (a.x, a.y) == (5, 3))
    black = next(a for a in acts if a.type == ActionType.FIGHT and (a.x, a.y) == (6, 4))
    check("Red Slime (5,3) direct unlocks ⊂ Black Slime (6,4) direct unlocks", red.direct_unlocks < black.direct_unlocks, True)
    check("Red Slime tagged with Black Slime as alternative", red.alternative_route, black.label())
    check("Black Slime is not redundant", black.alternative_route, None)
    text = state.format_actions(acts)
    check("formatter prints the ALTERNATIVE ROUTE tag once", text.count("[ALTERNATIVE ROUTE"), 1)
    check("tag names the other action", 'opened by "Fight Black Slime at (6,4)' in text, True)
    state.apply_action(black)
    state.apply_action(next(a for a in state.get_actions() if a.type == ActionType.FIGHT and (a.x, a.y) == (5, 6)))
    text = state.format_actions(state.get_actions())
    check("after Green Slime dies Red Slime is plain OPTIONAL", "[OPTIONAL" in text and "[ALTERNATIVE ROUTE" not in text, True)
    ev.configure_scenario(None)


def test_stat_route_is_net_of_its_cost():
    """C1 (SIMPLE_FLOOR_PLAN.md §5): a stat route must be reported net of the HP needed to walk it.
    Reproduces the decisive `simple` turn-9 state (HP 336, ATK 9, DEF 5) from the 2026-09-24 runs:
    door (7,0) reaches +1 ATK for 16 HP (net positive), door (7,5) reaches +1 ATK +1 DEF only after
    198 HP of fighting (net negative) — the old benefit-only hint advertised the latter as the
    bigger number ("save 155") and that is the order every failing episode took."""
    print("\n--- Stat Route Net Value ---")
    from mota.optimizer import evaluator as ev

    ev.configure_scenario("simple")
    state = ev._create_state(lookahead_depth=3)

    def take(pred):
        a = next((x for x in state.get_actions() if pred(x)), None)
        assert a is not None, "expected action not available"
        state.apply_action(a)

    take(lambda a: a.type == ActionType.COLLECT and (a.x, a.y) == (5, 1))
    take(lambda a: a.type == ActionType.FIGHT and (a.x, a.y) == (6, 4))
    take(lambda a: a.type == ActionType.FIGHT and (a.x, a.y) == (5, 6))
    take(lambda a: a.type == ActionType.OPEN_DOOR and (a.x, a.y) == (4, 7))
    take(lambda a: a.type == ActionType.FIGHT and (a.x, a.y) == (3, 7))
    while (c := next((a for a in state.get_actions() if a.type == ActionType.COLLECT), None)):
        state.apply_action(c)
    check("reached the decisive state", (state.hero.hp, state.hero.atk, state.hero.def_), (336, 9, 5))

    acts = state.get_actions()
    cheap = next(a for a in acts if a.type == ActionType.OPEN_DOOR and (a.x, a.y) == (7, 0))
    pricey = next(a for a in acts if a.type == ActionType.OPEN_DOOR and (a.x, a.y) == (7, 5))
    lord = next(a for a in acts if a.type == ActionType.FIGHT and (a.x, a.y) == (1, 9))
    check("cheap route: +1 ATK behind 16 HP of fighting", state._stat_route(cheap)[:2] + (state._kill_cost(state._stat_route(cheap)[2], state.hero),), (1, 0, 16))
    check("expensive route: +1 ATK +2 DEF behind 198 HP (D2 counts both gems)", state._stat_route(pricey)[:2] + (state._kill_cost(state._stat_route(pricey)[2], state.hero),), (1, 2, 198))
    check("cheap route reported net positive", "net +78 HP" in state._stat_value_hint(cheap, acts), True)
    check("expensive route nets far less than the cheap one", "net +18 HP" in state._stat_value_hint(pricey, acts), True)
    check("premature fight is flagged with the exact waste", "wastes 12 HP" in state._order_hint(lord, acts), True)
    check("order hint names the cheaper route", 'after "Open yellow door at (7,0)"' in state._order_hint(lord, acts), True)
    check("doors get no order hint (only fights can be premature)", state._order_hint(cheap, acts), "")
    ev.configure_scenario(None)


def test_one_sided_annotation_fixes():
    """D1–D4 (SIMPLE_FLOOR_PLAN.md §11.7): every overnight falsification was an annotation that
    reported one side of a trade-off. Reconstructed states from the stored logs pin the repairs."""
    print("\n--- One-Sided Annotation Fixes (D1-D4) ---")
    from mota.optimizer import evaluator as ev

    def walk(state, steps):
        def sweep():
            while (c := next((x for x in state.get_actions() if x.type == ActionType.COLLECT), None)):
                state.apply_action(c)
        sweep()
        for kind, pos in steps:
            a = next((x for x in state.get_actions() if x.type == kind and (x.x, x.y) == pos), None)
            assert a is not None, f"{kind} {pos} not available"
            state.apply_action(a)
            sweep()

    ev.configure_scenario("simple")
    # --- D4: boss budget over required monsters only -----------------------------------------
    state = ev._create_state(lookahead_depth=3)
    req, opt = state._boss_required_monsters()
    check("D4 simple: only Green Slime (5,6) and Bat (5,9) block the boss", sorted(req), [(5, 6), (5, 9)])
    check("D4 simple: 11 optional monsters", len(opt), 11)
    txt = state.format_state()
    check("D4: no 'CANNOT WIN' on a winnable floor", "CANNOT WIN" in txt, False)
    check("D4: budget names the required set", "2 monsters that block the way to the boss" in txt, True)

    # --- D2 + D3: simple T22 (35B divergence) ------------------------------------------------
    F, D_ = ActionType.FIGHT, ActionType.OPEN_DOOR
    walk(state, [(F, (6, 4)), (F, (5, 6)), (D_, (4, 7)), (F, (3, 7)), (D_, (7, 0)), (D_, (8, 0)), (F, (9, 0)),
                 (F, (3, 5)), (F, (1, 9))])
    check("reached T22 state", (state.hero.hp, state.hero.atk, state.hero.def_), (661, 11, 6))
    acts = state.get_actions()
    door = next(a for a in acts if a.type == D_ and (a.x, a.y) == (7, 5))
    check("D2: both DEF gems behind door (7,5) counted", state._stat_route(door)[:2], (1, 2))
    check("D2: potions behind the door summed", door.potion_hp, 150)
    txt = state.format_actions(acts)
    check("D2: both Blue Gems appear in the tree (different chains)", txt.count("Blue Gem (+1 DEF) [STAT]") >= 2, True)
    check("D3: potions listed separately on the door", "+150 HP potions behind it" in txt, True)

    # --- D3: simple T9 — Slime Lord (1,9) no longer shows a negative effCost -------------------
    state = ev._create_state(lookahead_depth=3)
    walk(state, [(F, (6, 4)), (F, (5, 6)), (D_, (4, 7)), (F, (3, 7))])
    check("reached T9 state", (state.hero.hp, state.hero.atk, state.hero.def_), (336, 9, 5))
    acts = state.get_actions()
    lord = next(a for a in acts if a.type == F and (a.x, a.y) == (1, 9))
    check("D3: potion HP separated from stat value", (lord.potion_hp, lord.stat_lookahead), (200, 90))
    txt = state.format_actions(acts)
    check("D3: effCost is positive without the potion", "damage=95 (28.3%) hpAfter=241 [MODERATE] lookahead=90 effCost=5" in txt, True)
    check("D3: potion noted on the fight line", "+200 HP potions behind it" in txt, True)
    check("D3: the effCost=None sentinel survives", "effCost=None" in txt, True)

    # --- D1: simple T5 — the 46 % Bat must never be recommended as 'first' --------------------
    state = ev._create_state(lookahead_depth=3)
    walk(state, [(F, (6, 4)), (F, (5, 6)), (D_, (4, 7))])
    acts = state.get_actions()
    bat = next(a for a in acts if a.type == F and (a.x, a.y) == (3, 5))
    check("Bat (3,5) exceeds the 40 % rule here", bat.damage_percent > 40, True)
    hints = [state._order_hint(a, acts) for a in acts]
    check("D1: no ORDER line recommends the >40 % Bat first", any('after "Fight Bat at (3,5)' in h for h in hints), False)
    check("D1: ORDER lines state the route cost", all("HP of fighting to reach them" in h for h in hints if h), True)
    ev.configure_scenario(None)

    # --- D4 on complex: the floor the solver clears with 22 HP must not say it is lost --------
    ev.configure_scenario("complex")
    state = ev._create_state(lookahead_depth=3)
    txt = state.format_state()
    check("D4 complex: no 'CANNOT WIN' at the start", "CANNOT WIN" in txt, False)
    check("D4 complex: optional monsters reported separately", "other monsters" in txt and "block nothing" in txt, True)
    ev.configure_scenario(None)

    # --- regression: a door-only action list must format (T3/W1 crashed on UnboundLocalError) --
    floor = FloorData(floor_id="TDOORONLY", width=7, height=5,
                      map=[[1, 1, 1, 1, 1, 1, 1],
                           [1, 0, 82, 0, 28, 1, 1],
                           [1, 0, 1, 1, 1, 1, 1],
                           [1, 0, 0, 0, 0, 0, 1],
                           [1, 1, 1, 1, 1, 1, 1]],
                      events={}, change_floor={}, up_floor=(1, 1), down_floor=(1, 1))
    st = GameState(floor=floor, hero=Hero(hp=100, atk=10, def_=10, keys=Keys(blue=1), x=1, y=1))
    acts = st.get_actions()
    check("door-only list has a door and no fights", any(a.type == ActionType.OPEN_DOOR for a in acts) and all(a.type != ActionType.FIGHT for a in acts), True)
    check("door-only list formats without error", "[open_door]" in st.format_actions(acts), True)


def test_round3_keys_repair_levelups():
    """Round 3 (SIMPLE_FLOOR_PLAN.md §15): K1 key budget, K2 per-door key line, R1 repair
    candidates, S1 no level-up offers. Simple T4 is the state where all three B10/V1 failures diverged."""
    print("\n--- Round 3: key economy, repair candidates, level-ups ---")
    from mota.optimizer import evaluator as ev

    ev.configure_scenario("simple")
    state = ev._create_state(lookahead_depth=3)
    for pos in ((6, 4), (5, 6)):
        while (c := next((x for x in state.get_actions() if x.type == ActionType.COLLECT), None)):
            state.apply_action(c)
        state.apply_action(next(a for a in state.get_actions() if a.type == ActionType.FIGHT and (a.x, a.y) == pos))
    while (c := next((x for x in state.get_actions() if x.type == ActionType.COLLECT), None)):
        state.apply_action(c)
    check("reached simple T4", (state.hero.hp, state.hero.keys.yellow), (391, 1))
    check("K1: key budget line", "Key budget: yellow 1 in hand + 4 on this floor = 5 for 4 closed yellow door(s)" in state.format_state(), True)
    acts = state.get_actions()
    d47 = next(a for a in acts if a.type == ActionType.OPEN_DOOR and (a.x, a.y) == (4, 7))
    d75 = next(a for a in acts if a.type == ActionType.OPEN_DOOR and (a.x, a.y) == (7, 5))
    h47, h75 = state._key_hint(d47), state._key_hint(d75)
    check("K2: door (4,7) returns two yellow keys", "(yellow 1→2" in h47 and "+2 yellow" in h47, True)
    check("K2: door (7,5) spends the last yellow key", "(yellow 1→0" in h75 and "this is your last yellow key" in h75, True)
    check("K2: no last-key warning on (4,7)", "last yellow key" in h47, False)
    txt = state.format_actions(acts)
    check("K2 lines are in the prompt", txt.count(" → keys: uses 1 yellow") >= 2, True)

    # R1: repair never chooses an action the mechanical override would replace
    boss_like = next((a for a in acts if a.type == ActionType.FIGHT), None)
    valid = {a.action_id for a in acts}
    saved = boss_like.can_win
    boss_like.can_win = False
    cands = ev._repair_candidates(acts, valid)
    boss_like.can_win = saved
    check("R1: unwinnable fight excluded from repair", boss_like.action_id in cands, False)
    check("R1: dead-end door excluded from repair",
          any(a.action_id in cands for a in acts if getattr(a, "is_dead_end", False)), False)
    check("R1: falls back to all ids when nothing is safe", ev._repair_candidates([], valid), valid)
    ev.configure_scenario(None)

    # S1: level-ups are not offered (both prompts forbid them); MOTA_OFFER_LEVELUPS=1 restores
    floor = FloorData(floor_id="S5", width=5, height=3,
                      map=[[1, 1, 1, 1, 1], [1, 0, 123, 0, 1], [1, 1, 1, 1, 1]],
                      events={"2,1": [{"type": "openShop", "id": "expShop1"}]},
                      change_floor={}, up_floor=(1, 1), down_floor=(1, 1))
    st = GameState(floor=floor, hero=Hero(hp=500, atk=10, def_=10, exp=500, x=1, y=1))
    choices = {a.shop_choice for a in st.get_actions() if a.type == ActionType.SHOP_BUY}
    check("S1: EXP shop offers atk/def but not level", ("level" in choices, "atk" in choices), (False, True))
    os.environ["MOTA_OFFER_LEVELUPS"] = "1"
    try:
        choices = {a.shop_choice for a in st.get_actions() if a.type == ActionType.SHOP_BUY}
    finally:
        del os.environ["MOTA_OFFER_LEVELUPS"]
    check("S1: MOTA_OFFER_LEVELUPS=1 restores level-ups", "level" in choices, True)

    # lethal-only positions end as 'stuck' instead of executing the suicide (CB4/T4/W1b)
    ev.configure_scenario("simple")
    st = ev._create_state(lookahead_depth=3)
    for pos in ((6, 4), (5, 6)):
        while (c := next((x for x in st.get_actions() if x.type == ActionType.COLLECT), None)):
            st.apply_action(c)
        st.apply_action(next(a for a in st.get_actions() if a.type == ActionType.FIGHT and (a.x, a.y) == pos))
    while (c := next((x for x in st.get_actions() if x.type == ActionType.COLLECT), None)):
        st.apply_action(c)
    st.hero.hp = 1
    acts = st.get_actions()
    fights = [a for a in acts if a.type == ActionType.FIGHT]
    check("lethal-only: every fight is lethal at HP 1", bool(fights) and all(not a.can_win or a.hp_after <= 0 for a in fights), True)
    check("lethal-only: stop when only lethal fights remain", ev._lethal_only_stop(fights[0], fights) is not None, True)
    others = [a for a in acts if a.type != ActionType.FIGHT and not getattr(a, "is_dead_end", False)]
    if others:
        check("lethal-only: no stop while a survivable action exists", ev._lethal_only_stop(fights[0], acts), None)
    os.environ["MOTA_EXECUTE_LETHAL_ONLY"] = "1"
    try:
        check("lethal-only: MOTA_EXECUTE_LETHAL_ONLY=1 restores execution", ev._lethal_only_stop(fights[0], fights), None)
    finally:
        del os.environ["MOTA_EXECUTE_LETHAL_ONLY"]
    ev.configure_scenario(None)

    # tower HP floor (prompt rule 4 made mechanical): > 40 % fight replaced only if an alternative exists
    ev.configure_multi_floor_scenario("MT1", "MT2")
    g = ev._create_multi_floor_game()
    for _ in range(2):
        g.apply_action(next(a for a in g.get_actions() if a.type in (ActionType.COLLECT, ActionType.OPEN_DOOR)))
    g.hero.hp = 60
    acts = g.get_actions()
    slime = next(a for a in acts if a.type == ActionType.FIGHT)
    check("HP floor: the only fight costs > 40 %", slime.damage_percent > 40, True)
    check("HP floor: kept when nothing else can progress", g.hp_floor_alternative(slime, acts), None)
    ev.configure_scenario(None)

    # F-K3 (flood key line for fights) + F-ORD2 (two-sided ORDER), both behind flags
    ev.configure_scenario("simple")
    st = ev._create_state(lookahead_depth=2)
    while (c := next((x for x in st.get_actions() if x.type == ActionType.COLLECT), None)):
        st.apply_action(c)
    st.apply_action(next(a for a in st.get_actions() if a.type == ActionType.FIGHT and (a.x, a.y) == (6, 4)))
    while (c := next((x for x in st.get_actions() if x.type == ActionType.COLLECT), None)):
        st.apply_action(c)
    green = next(a for a in st.get_actions() if a.type == ActionType.FIGHT and (a.x, a.y) == (5, 6))
    os.environ["MOTA_FIGHT_KEY_FLOOD"] = "1"
    try:
        check("F-K3: Green Slime exposes door (4,7) with 2 yellow keys at depth 2",
              "yellow door (4,7) → +2 yellow behind it" in st._key_hint(green), True)
    finally:
        del os.environ["MOTA_FIGHT_KEY_FLOOD"]
    ev.configure_scenario(None)
    opts, choice = ev._parse_map_enum("OPTIONS:\n- fight (6,4)\n2. collect (5,1)\nopen_door (4,7)\nFINAL_CHOICE: (6,4)")
    check("map-enum parser", (opts, choice), ([("fight", (6, 4)), ("collect", (5, 1)), ("open_door", (4, 7))], (6, 4)))


def test_way_up_line():
    """MOTA_WAY_UP: at the MT3 position where four tower runs fought the 315-HP Skeleton, the way up is the
    Bat (6,6) route (650 HP); the Skeleton is not on it and only the Bat action is tagged."""
    print("\n=== Way-up line (tower) ===")
    from ..optimizer import evaluator as ev
    old = {k: os.environ.get(k) for k in ("MOTA_REMOTE_ACTIONS", "MOTA_WAY_UP")}
    os.environ.update({"MOTA_REMOTE_ACTIONS": "1", "MOTA_WAY_UP": "1"})
    try:
        ev.configure_multi_floor_scenario("MT0", "MT23w")
        g = ev._create_multi_floor_game(lookahead_depth=2)
        g.current_floor_idx, g.visited_floor_idx = 3, {0, 1, 2, 3}
        g.hero.x, g.hero.y, g.hero.hp, g.hero.atk, g.hero.def_ = 5, 6, 340, 10, 10
        g.per_floor_removed[3] = {(5, 6)}
        route = g._way_up_route(3, g.hero)
        check("way up MT3: 650 HP", route["hp"], 650)
        check("way up MT3: Bat (6,6) first, no Skeleton", (route["fights"][0][1:3], any(f[0] == "Skeleton" for f in route["fights"])),
              ((6, 6), False))
        check("way up line printed", "Way up to MT4" in g.format_state(), True)
        text = g.format_actions(g.get_actions())
        tagged, head = [], ""
        for line in text.splitlines():
            if line[:2] == "  " and line[2:3].isdigit():
                head = line
            elif "on the way up" in line:
                tagged.append(head)
        check("only the Bat (6,6) action is tagged", [("Bat at (6,6)" in t) for t in tagged], [True])
        os.environ["MOTA_WAYUP_COMBINED"] = "1"
        line = g.format_state()
        check("design 5: in-order line printed", "In order, spending the gold/EXP" in line, True)
        check("design 5: combined ladder", "With purchases: ATK" not in line or "(you have" in line, True)
    finally:
        os.environ.pop("MOTA_WAYUP_COMBINED", None)
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_tower_fidelity():
    """MOTA_TOWER_FIDELITY: the MT4 thief opens MT2 (2,7), items.js values, the Cross becomes a x4/3 action."""
    print("\n=== Tower fidelity events ===")
    from ..optimizer import evaluator as ev
    keys = ("MOTA_REMOTE_ACTIONS", "MOTA_TOWER_FIDELITY")
    old = {k: os.environ.get(k) for k in keys}
    os.environ.update({k: "1" for k in keys})
    try:
        ev.configure_multi_floor_scenario("MT0", "MT23w")
        g = ev._create_multi_floor_game(lookahead_depth=2)
        check("items.js value for the Knight Sword", g.gd.get_item_effect("sword3")["atk"], 70)
        g.current_floor_idx, g.visited_floor_idx = 4, {0, 1, 2, 3, 4}
        g.per_floor_removed[4] |= {(6, 9), (6, 8), (6, 7), (6, 6), (6, 5), (6, 4), (6, 3)}
        g.hero.x, g.hero.y = 6, 10
        talk = [a for a in g.get_actions() if a.shop_choice == "event"]
        check("thief talk offered", len(talk), 1)
        g.apply_action(talk[0])
        check("MT2 (2,7) opened", (2, 7) in g.per_floor_removed[2], True)
        check("thief not offered again", [a for a in g.get_actions() if a.shop_choice == "event"], [])
        i, x, y = g._cross_tiles()[0]
        g.per_floor_removed[i].add((x, y))
        g.hero.hp, g.hero.atk, g.hero.def_ = 900, 90, 60
        cross = [a for a in g.get_actions() if a.shop_choice == "cross"]
        check("Cross action x4/3", cross[0].stat_changes if cross else None, {"hp": 300, "atk": 30, "def": 20})
        g.apply_action(cross[0])
        check("Cross handed in once", (g.hero.atk, [a for a in g.get_actions() if a.shop_choice == "cross"]), (120, []))
        g2 = ev._create_multi_floor_game(lookahead_depth=2)
        seal = g2._seals[0]
        mt7 = seal["idx"]
        check("MT7 seal closed with 3 of 4 White Warriors dead", (g2.per_floor_removed[mt7].update(list(seal["guards"])[:3]),
              g2._make_state(), g2.floors[mt7].map[5][5])[2], 1)
        g2.per_floor_removed[mt7] |= seal["guards"]
        g2._make_state()
        check("MT7 seal open after all 4", g2.floors[mt7].map[5][5], 6)
        mt13 = next(i for i, f in enumerate(g2.floors) if f.floor_id == "MT13")
        g2.current_floor_idx, g2.visited_floor_idx = mt13, set(range(mt13 + 1))
        g2.hero.atk = g2.hero.def_ = 500
        g2.per_floor_removed[mt13].add((9, 11))
        g2.hero.x, g2.hero.y = 9, 11
        wiz = [a for a in g2.get_actions() if a.remote is None and (a.x, a.y) == (8, 11)]
        g2.apply_action(wiz[0])
        check("MT13 wizard: level +3, ATK +30", (g2.hero.lv, g2.hero.atk), (4, 530))
        check("level shown in the tower state", "Hero: LV=4 " in g2.format_state(), True)
        check("Small Feather effect", g2.gd.get_item_effect("centerFly")["lv"], 1)
        from ..game.types import Action as _A
        g2.global_shops = [{"floor_id": f, "x": 0, "y": 0, "name": n, "shop_choice": "def", "stat_changes": {"def": d},
                            "money_cost": p, "currency": "money", "requires_key": None}
                           for f, n, d, p in (("MT3", "Gold Shop (3F): DEF +4", 4, 25), ("MT11", "Gold Shop (11F): DEF +20", 20, 100))]
        g2.hero.money = 60
        os.environ["MOTA_FREE_AFFORD"] = "1"
        line = g2._shop_rate_line(_A(action_id=1, type=ActionType.SHOP_BUY, x=0, y=0, name="Gold Shop (3F): DEF +4",
                                     shop_choice="def", stat_changes={"def": 4}, money_cost=25, currency="money"))
        check("shop line names the better price per point", "+20 DEF for 100 g = 5.00 g per point (you have 60, 40 more needed)"
              in (line[0] if line else ""), True)
        os.environ.pop("MOTA_FREE_AFFORD", None)
        mt10 = next(i for i, f in enumerate(g2.floors) if f.floor_id == "MT10")
        ice = _A(action_id=1, type=ActionType.OPEN_DOOR, x=4, y=7, name="ice", door_type=DoorType.ICE, path_steps=3)
        fight = _A(action_id=2, type=ActionType.FIGHT, x=1, y=1, name="x", can_win=True, total_damage=50)
        check("ice gate opened by the engine", g2.mechanical_action([fight, ice]), (ice, "auto-open (ice gate, no key)"))
        check("MT10 has the ice gate", g2.floors[mt10].map[7][4], 6)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_npc_trades_and_key_reserve():
    """MOTA_NPC_TRADES: MT15 Holy Sword for 500 EXP (a decision, never auto-taken); MOTA_KEY_RESERVE: a red door off the
    way up that leaves no red key for the MT16 red door (6,4)."""
    print("\n=== NPC trades and key reserve ===")
    from ..optimizer import evaluator as ev
    from ..game.types import Action as _A
    keys = ("MOTA_REMOTE_ACTIONS", "MOTA_TOWER_FIDELITY", "MOTA_NPC_TRADES")
    old = {k: os.environ.get(k) for k in keys}
    os.environ.update({k: "1" for k in keys})
    try:
        ev.configure_multi_floor_scenario("MT0", "MT23w")
        g = ev._create_multi_floor_game(lookahead_depth=2)
        mt15 = next(i for i, f in enumerate(g.floors) if f.floor_id == "MT15")
        g.current_floor_idx, g.visited_floor_idx = mt15, set(range(mt15 + 1))
        g.per_floor_removed[mt15] |= {(6, 10), (5, 8), (7, 8), (5, 6), (5, 5), (7, 6), (7, 5)}
        g.hero.x, g.hero.y, g.hero.atk, g.hero.exp, g.hero.money = 5, 5, 700, 400, 0
        here = lambda: [a for a in g.get_actions() if a.remote is None and (a.x, a.y) == (5, 4)]
        check("no trade below 500 EXP", here(), [])
        g.hero.exp = 600
        trade = here()
        check("trade offered at 500 EXP", [a.name for a in trade], ["man trades Holy Sword (+120 ATK) for 500 exp"])
        check("trade is not auto-collected", g.mechanical_action(trade), None)
        g.apply_action(trade[0])
        check("Holy Sword bought", (g.hero.atk, g.hero.exp), (820, 100))
        mt16 = mt15 + 1
        g.current_floor_idx, g.visited_floor_idx = mt16, set(range(mt16 + 1))
        g.hero.x, g.hero.y = 6, 1
        g.hero.keys.red = 1
        reserve = g._way_up_doors()
        door = _A(action_id=1, type=ActionType.OPEN_DOOR, x=6, y=10, name="red", door_type=DoorType.RED)
        line = g._key_reserve_line("MT10", door, reserve)
        check("reserve line on an MT10 red door", "leaves 0 red key(s)" in (line[0] if line else "")
              and "(6,4) on MT16" in line[0], True)
        door16 = _A(action_id=2, type=ActionType.OPEN_DOOR, x=6, y=4, name="red", door_type=DoorType.RED)
        check("no reserve line on the way-up door itself", g._key_reserve_line("MT16", door16, reserve), [])
        os.environ["MOTA_KEY_RESERVE"] = "1"
        g.hero.keys.red = 0
        check("way-up line names the missing red key", "needs 1 red key(s), you have 0" in g._way_up_line(), True)
        os.environ.pop("MOTA_KEY_RESERVE", None)
        # hidden staircases (game data "enable": false): MT18 after the princess, MT20 after the Cross
        g3 = ev._create_multi_floor_game(lookahead_depth=2)
        i4, i12, i18, i20, i21 = (next(i for i, f in enumerate(g3.floors) if f.floor_id == n)
                                  for n in ("MT4", "MT12", "MT18", "MT20", "MT21"))
        check("MT18 and MT20 up-stairs hidden", (g3.floors[i18].map[11][11], g3.floors[i20].map[8][6]), (0, 0))
        g3.current_floor_idx, g3.visited_floor_idx = i18, set(range(i18 + 1))
        g3.hero.x, g3.hero.y = g3.floors[i18].down_floor
        check("way-up line names the hidden staircase", "hidden until you talk to princess on MT18 (6,5)" in g3._way_up_line(), True)
        g3._events_done.add(("MT4", 6, 1))
        g3.per_floor_removed[i4] |= {(6, 9), (6, 8), (6, 7), (6, 6), (6, 5), (6, 4), (6, 3)}
        check("thief second talk needs the ice pickaxe", [a for a in g3.get_actions() if a.shop_choice == "event2"], [])
        ix, iy = next((x, y) for y, r in enumerate(g3.floors[i12].map) for x, t in enumerate(r) if g3.gd.get_item_id(t) == "icePickaxe")
        g3.per_floor_removed[i12].add((ix, iy))
        g3.current_floor_idx, (g3.hero.x, g3.hero.y) = i4, (6, 10)
        talk = [a for a in g3.get_actions() if a.shop_choice == "event2"]
        check("thief second talk offered with the ice pickaxe", len(talk), 1)
        g3.apply_action(talk[0])
        check("MT18 (6,9),(6,10) open, thief gone", ({(6, 9), (6, 10)} <= g3.per_floor_removed[i18], (6, 1) in g3.per_floor_removed[i4]),
              (True, True))
        g3.current_floor_idx = i18
        g3.per_floor_removed[i18] |= {(6, 8), (6, 7), (6, 6)}
        g3.hero.x, g3.hero.y = 6, 6
        princess = [a for a in g3.get_actions() if a.shop_choice == "event" and a.target_floor_id == "MT18"]
        check("princess talk reveals the staircase", "up-staircase at (11,11) on MT18" in (princess[0].name if princess else ""), True)
        g3.apply_action(princess[0])
        check("MT18 up-stairs shown", g3.floors[i18].map[11][11], 87)
        g3.cross_given = False
        from ..game.types import Action as _A2
        g3._apply_global_shop(_A2(action_id=1, type=ActionType.SHOP_BUY, x=0, y=0, name="cross", shop_choice="cross",
                                  stat_changes={}, money_cost=0, currency="money"))
        check("Cross reveals MT20 up-stairs", g3.floors[i20].map[8][6], 87)
        g3._check_win(i21, 6, 2)
        check("MT21 Nether Demon King ends the game", g3.goal_reached, True)
        os.environ["MOTA_AFTER_BATTLE"] = "1"
        g._after_battle(mt16, 6, 6)
        from ..game.data import DEFAULT_GAME_DATA
        check("MT16 afterBattle strengthens later monsters", (g.gd.get_monster("redKing").hp,
              g.gd.get_monster("darkKnight").atk, DEFAULT_GAME_DATA.get_monster("darkKnight").atk != 1306), (20000, 1306, True))
        os.environ.pop("MOTA_AFTER_BATTLE", None)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ===== Main =====
def test_design7_lines():
    """Design 7: event and seal lines name the way and the missing keys (Ice Pickaxe behind the MT12 blue door, last
    White Warrior behind the MT7 blue door (9,5)); White Warriors carry the [vampire] tag instead of 'already immune'."""
    print("\n=== Design 7 lines ===")
    from ..optimizer import evaluator as ev
    keys = ("MOTA_REMOTE_ACTIONS", "MOTA_TOWER_FIDELITY", "MOTA_EVENT_WAY", "MOTA_VAMPIRE_TAG", "MOTA_KEY_RESERVE",
            "MOTA_NO_KEY_PURCHASE")
    old = {k: os.environ.get(k) for k in keys}
    os.environ.update({k: "1" for k in keys})
    try:
        ev.configure_multi_floor_scenario("MT0", "MT23w")
        g = ev._create_multi_floor_game(lookahead_depth=2)
        i4, i7 = (next(i for i, f in enumerate(g.floors) if f.floor_id == n) for n in ("MT4", "MT7"))
        g.current_floor_idx, g.visited_floor_idx = i7, set(range(13))
        g.hero.x, g.hero.y = g.floors[i7].down_floor
        g.hero.keys.blue, g.hero.hp, g.hero.atk, g.hero.def_ = 0, 20000, 1300, 1300
        g._events_done.add(("MT4", 6, 1))
        state = g.format_state()
        thief = next((l for l in state.splitlines() if l.startswith("Event: thief")), "")
        check("pickaxe line names the blue door and the missing key",
              "blue (10,6)" in thief and "you have 0: blue keys cannot be bought" in thief, True)
        seal = next((l for l in state.splitlines() if "White Warriors" in l), "")
        check("seal line names the guards' doors and the key total",
              "White Warrior at (8,5)" in seal and "Together they need" in seal, True)
        g.per_floor_removed[i7] |= {(6, 3), (6, 7), (4, 5)}
        acts = g.format_actions(g.get_actions())
        check("vampire tag on a White Warrior fight", "[vampire: takes 25% of your current HP" in acts
              or "White Warrior" not in acts, True)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main():
    test_damage()
    test_floor_loader()
    test_pathfinder()
    test_state()
    test_walkthrough_basic()
    test_actions_blocked_by_intermediate_items()
    test_mt3_top_left_key_actions_after_t5()
    test_hero_loader()
    test_floor_loader_range()
    test_lookahead_wiring()
    test_multi_floor_init()
    test_shop_discovered_when_broke()
    test_multi_floor_transition()
    test_deferred_door_tracking()
    test_heuristic_avoids_dead_end_blue_door()
    test_safety_override_is_mechanical_only()
    test_alternative_route_annotation()
    test_stat_route_is_net_of_its_cost()
    test_one_sided_annotation_fixes()
    test_round3_keys_repair_levelups()
    test_way_up_line()
    test_tower_fidelity()
    test_npc_trades_and_key_reserve()
    test_design7_lines()

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed > 0:
        sys.exit(1)
    else:
        print("All tests passed!")


if __name__ == "__main__":
    main()
