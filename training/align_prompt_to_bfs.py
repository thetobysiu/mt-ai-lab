"""
Phase 2: GEPA Prompt Alignment to BFS Ground Truth.

Iteratively optimizes the teacher system prompt so that the LLM's per-decision
choices match the BFS-optimal walkthrough at close to 100% accuracy.

The key idea: GEPA's fitness function is per-decision BFS match rate, NOT the
composite game-outcome score. This ensures the prompt teaches the LLM to reason
its way to the same choices the BFS solver computes.

Once the aligned prompt achieves high accuracy, Phase 3 collects the LLM's
chain-of-thought reasoning at each decision point — producing training data
where the reasoning naturally explains WHY each BFS-optimal action is correct.

Usage:
    cd mota-gepa
    # Single evaluation (test how well current prompt matches BFS):
    python -m training.align_prompt_to_bfs --test

    # True autonomous rollout (the LLM's chosen actions are executed):
    python -m training.align_prompt_to_bfs --test --free-play

    # Full GEPA optimization (iterate until ~100% BFS match):
    python -m training.align_prompt_to_bfs --gepa --max-calls 30

    # Custom floor:
    python -m training.align_prompt_to_bfs --test --floor simple
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BFS route extraction from game replay
# ---------------------------------------------------------------------------

def _load_floor_scenario(floor_name: str):
    """Load floor scenario and return (GameState, gd, scenario, bfs_hp).

    Returns:
        state: Fresh GameState at the floor start
        gd: GameData for the floor
        scenario: ScenarioConfig
        bfs_hp: Optimal final HP from BFS solver
    """
    from mota.game.state import GameState
    from mota.game.types import Hero, Keys, ActionType
    from mota.game.data import GameData
    from mota.game import ai_floor_loader
    from mota.game.ai_floor_loader import (
        load_ai_floor, build_monsters_lookup, build_item_effects, build_shop_def,
    )
    from mota.solver.bfs_solver import BFSSolver

    # Search directories: local data/floors/ (English names) then magic-tower-AI/test/
    search_dirs = [
        _root / "data" / "floors",
        _root.parent / "magic-tower-AI" / "test",
    ]
    scenario = None

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for txt_file in search_dir.glob("*.txt"):
            if floor_name in txt_file.stem:
                scenario = load_ai_floor(txt_file)
                break
        if scenario is not None:
            break

    if scenario is None:
        raise FileNotFoundError(
            f"Floor not found: {floor_name} (searched: {[str(d) for d in search_dirs]})"
        )

    # Build GameData
    custom_monsters = build_monsters_lookup(scenario.monsters)
    custom_items = build_item_effects(scenario.item_bonuses)
    shops = build_shop_def(scenario.shop, scenario.name)
    from mota.game.data import TILE_ENEMIES
    extra_tiles = {}
    for tile_id, monster in scenario.monsters.items():
        if tile_id not in TILE_ENEMIES:
            extra_tiles[tile_id] = monster.id
    gd = GameData(
        custom_monsters=custom_monsters,
        custom_items=custom_items,
        custom_shops=shops,
        extra_enemy_tiles=extra_tiles,
    )

    # Create game state — use scenario's hero position (not down_floor)
    # For AI test floors, the scenario specifies the correct start position.
    fdata = scenario.floors[0]
    hero = scenario.hero.copy()

    state = GameState(
        floor=fdata,
        hero=hero,
        goal=scenario.goal,
        max_turns=300,
        game_data=gd,
        lookahead_depth=3,
    )

    # Run BFS for optimal HP reference
    # Complex floors need much higher state limits (e.g., 703K for 单层-复杂)
    bfs_max_states = 800_000 if "complex" in floor_name or "複雑" in floor_name else 50_000

    # Known optimal HPs from Java BFS (E8) — skip expensive Python BFS
    _KNOWN_BFS_HP = {
        "simple": 13,
        "complex": 22,
    }
    if floor_name in _KNOWN_BFS_HP:
        bfs_hp = _KNOWN_BFS_HP[floor_name]
        log.info("Floor %s: Using known BFS optimal HP=%d (skipping full BFS)", floor_name, bfs_hp)
    else:
        solver = BFSSolver(
            fdata, hero.copy(),
            game_data=gd,
            max_decisions=100,
            goal=scenario.goal,
            max_states=bfs_max_states,
        )
        result = solver.solve()
        bfs_hp = result.hero.hp if result else 0
        log.info("Floor %s: BFS optimal HP=%d (max_states=%d)", floor_name, bfs_hp, bfs_max_states)

    return state, gd, scenario, bfs_hp, bfs_max_states


def _bfs_optimal_actions(floor, hero, removed, actions, gd, goal, max_states=50_000):
    """Find ALL equally-optimal actions by running mini-BFS after each candidate.

    Returns dict: {action_id: (hp, goal_reached)} for all actions that achieve
    the best possible HP with goal_reached=True (or best fallback if no goal).
    """
    from mota.game.state import GameState
    from mota.solver.bfs_solver import BFSSolver

    # Suppress per-candidate BFS logging (N actions = N "BFS complete" messages)
    bfs_logger = logging.getLogger("mota.solver.bfs_solver")
    prev_level = bfs_logger.level
    bfs_logger.setLevel(logging.WARNING)

    results = {}  # action_id -> (hp, goal_reached)

    for action in actions:
        sim_state = GameState(
            floor=floor,
            hero=hero.copy(),
            goal=goal,
            game_data=gd,
            lookahead_depth=0,
            _removed=set(removed),
        )
        sim_state.apply_action(action)
        solver = BFSSolver(
            floor, sim_state.hero.copy(),
            game_data=gd,
            max_decisions=100,
            goal=goal,
            max_states=max_states,
            initial_removed=sim_state.removed,
        )
        result = solver.solve()
        if result is None:
            continue
        goal_reached = getattr(result, "goal_reached", False)
        results[action.action_id] = (result.hero.hp, goal_reached)

    # Restore BFS logging level
    bfs_logger.setLevel(prev_level)

    # Find best: prefer goal-reached, then highest HP
    goal_results = {k: v for k, v in results.items() if v[1]}
    if goal_results:
        best_hp = max(v[0] for v in goal_results.values())
        return {k: v for k, v in goal_results.items() if v[0] == best_hp}
    elif results:
        best_hp = max(v[0] for v in results.values())
        return {k: v for k, v in results.items() if v[0] == best_hp}
    return {}


def _bfs_optimal_action(floor, hero, removed, actions, gd, goal, max_states=50_000):
    """Find the BFS-optimal action by running mini-BFS after each candidate.

    For each available action, simulates applying it, then runs BFS from the
    resulting state. Prefers actions that lead to goal-reached states. Among
    goal-reached states, picks highest HP. Falls back to non-goal states only
    if no action reaches the goal.

    Returns (best_action_id, best_hp, goal_reached) or (None, -1, False).
    """
    from mota.game.state import GameState
    from mota.solver.bfs_solver import BFSSolver

    # Suppress per-candidate BFS logging
    bfs_logger = logging.getLogger("mota.solver.bfs_solver")
    prev_level = bfs_logger.level
    bfs_logger.setLevel(logging.WARNING)

    best_goal_id = None
    best_goal_hp = -1
    best_fallback_id = None
    best_fallback_hp = -1

    for action in actions:
        # Simulate applying this action
        sim_state = GameState(
            floor=floor,
            hero=hero.copy(),
            goal=goal,
            game_data=gd,
            lookahead_depth=0,
            _removed=set(removed),
        )
        sim_state.apply_action(action)

        # Run BFS from resulting state
        solver = BFSSolver(
            floor, sim_state.hero.copy(),
            game_data=gd,
            max_decisions=100,
            goal=goal,
            max_states=max_states,
            initial_removed=sim_state.removed,
        )
        result = solver.solve()

        if result is None:
            continue

        if getattr(result, "goal_reached", False):
            if result.hero.hp > best_goal_hp:
                best_goal_hp = result.hero.hp
                best_goal_id = action.action_id
        else:
            if result.hero.hp > best_fallback_hp:
                best_fallback_hp = result.hero.hp
                best_fallback_id = action.action_id

    # Restore BFS logging level
    bfs_logger.setLevel(prev_level)

    # Prefer goal-reached over fallback
    if best_goal_id is not None:
        return best_goal_id, best_goal_hp, True
    return best_fallback_id, best_fallback_hp, False


# ---------------------------------------------------------------------------
# Core: replay BFS route and evaluate LLM at each decision
# ---------------------------------------------------------------------------

def evaluate_bfs_alignment(
    candidate_prompt: str,
    floor_name: str = "simple",
    task_model: str | None = None,
    task_mode: str | None = None,
    eval_mode: str = "reactive",
    verbose: bool = False,
    free_play: bool = False,
) -> dict:
    """
    Evaluate per-decision BFS alignment of an LLM with the given prompt.

    Modes:
        reactive   — turn-by-turn with conversation history (default)
        oneshot    — single LLM call producing full plan; compare to BFS
        multistep-N — plan N actions per LLM call, then re-plan

    If free_play=False (default): At each multi-choice decision point, runs
    mini-BFS per candidate action to determine the oracle-optimal action.
    The BFS-optimal action is always executed to keep the state on the optimal path.

    If free_play=True: The LLM's chosen action is executed (no BFS oracle).
    This measures the LLM's actual gameplay outcome on floors where per-decision
    BFS is too expensive (e.g., complex floor with 700K states).

    Returns dict with:
        accuracy: float (matches / total decisions) — only meaningful when free_play=False
        matches: int
        total: int
        decisions: list of per-decision details
        llm_calls: int
    """
    from mota.optimizer.evaluator import _call_llm, _parse_action_id
    from mota.game.types import ActionType

    state, gd, scenario, bfs_hp, bfs_max_states = _load_floor_scenario(floor_name)

    # Build floor map for system prompt
    floor_map_text = state.format_floor_map()
    runtime_prompt = candidate_prompt + "\n\n" + floor_map_text

    matches = 0
    equiv_matches = 0
    total = 0
    decisions = []
    decision_idx = 0
    llm_calls = 0

    # Mode parsing
    chunk_size = 0
    is_map_mode = eval_mode.startswith("map-")
    base_mode = eval_mode[4:] if is_map_mode else eval_mode
    if base_mode.startswith("multistep"):
        parts = base_mode.split("-")
        chunk_size = int(parts[1]) if len(parts) > 1 else 5
        base_mode = "multistep"

    # Conversation history (reactive and multistep modes)
    max_hist_turns = 6
    conversation_history: list[dict] = []

    # Multistep plan buffer
    ms_plan: list[int] = []

    # Map-based modes: use grid + entity details instead of numbered action list
    if is_map_mode:
        return _evaluate_map_mode(
            candidate_prompt, runtime_prompt, floor_name, state,
            bfs_hp, task_model, task_mode, verbose, base_mode, chunk_size,
        )

    # For non-map modes, use base_mode for downstream checks
    eval_mode = base_mode

    # Oneshot: BFS-oracle or free-play (coordinate-based) depending on free_play flag
    if base_mode == "oneshot":
        if free_play:
            return _evaluate_oneshot_free_play(
                candidate_prompt, runtime_prompt, floor_name, state,
                bfs_hp, task_model, task_mode, verbose,
            )
        return _evaluate_oneshot(
            candidate_prompt, runtime_prompt, floor_name, state, gd, scenario,
            bfs_hp, task_model, task_mode, verbose, bfs_max_states,
        )

    while (not state.goal_reached and not state.failed
           and state.turn < state.max_turns):

        actions = state.get_actions()
        if not actions:
            break

        # Auto-execute forced single actions (no LLM call needed)
        if len(actions) == 1:
            only = actions[0]
            if only.type == ActionType.FIGHT and not only.can_win:
                break
            state.apply_action(only)
            continue

        # Multi-choice decision point
        optimal_set = {}
        bfs_action_id = None
        bfs_result_hp = None
        bfs_action = None

        if not free_play:
            # find BFS-optimal action(s) via mini-BFS
            per_decision_max = min(bfs_max_states, 50_000)
            import time as _time
            _bfs_start = _time.time()
            optimal_set = _bfs_optimal_actions(
                state.floor, state.hero, state.removed, actions,
                gd, scenario.goal, max_states=per_decision_max,
            )
            _bfs_elapsed = _time.time() - _bfs_start

            if not optimal_set:
                log.warning("No BFS solution found from decision %d — stopping (BFS took %.1fs)", decision_idx, _bfs_elapsed)
                break

            if verbose and _bfs_elapsed > 2.0:
                log.info("  [BFS D%d: %.1fs for %d actions × %dk max]",
                         decision_idx, _bfs_elapsed, len(actions), per_decision_max // 1000)

            # Pick the primary BFS action (first in optimal set)
            bfs_action_id = next(iter(optimal_set))
            bfs_result_hp = optimal_set[bfs_action_id][0]
            bfs_action = next((a for a in actions if a.action_id == bfs_action_id), None)

        # Format state for LLM
        state_text = state.format_state()
        actions_text = state.format_actions(actions)
        valid_ids = {a.action_id for a in actions}

        # --- Determine LLM action based on mode ---
        llm_action_id = None

        if eval_mode == "multistep" and ms_plan:
            # Consume from buffered plan
            llm_action_id = ms_plan.pop(0)
            if llm_action_id not in valid_ids:
                llm_action_id = None  # plan stale, will re-plan below

        if llm_action_id is None:
            # Need fresh LLM call
            if eval_mode == "multistep":
                user_msg = (
                    f"{state_text}\n\n{actions_text}\n\n"
                    f"Plan the next {chunk_size} actions. Reply: PLAN: id1, id2, ..., id{chunk_size}"
                )
            else:
                user_msg = (
                    f"{state_text}\n\n{actions_text}\n\n"
                    "Choose the best action. Reply: ACTION: <number>"
                )

            prior = conversation_history if conversation_history else None
            llm_calls += 1
            response = _call_llm(
                runtime_prompt, user_msg,
                task_model=task_model,
                task_mode=task_mode,
                prior_messages=prior,
            )

            if eval_mode == "multistep":
                # Parse plan: PLAN: 1, 3, 5, 2 ...
                plan_ids = _parse_plan(response, valid_ids)
                if plan_ids:
                    llm_action_id = plan_ids[0]
                    ms_plan = plan_ids[1:]
                else:
                    llm_action_id = _parse_action_id(response, valid_ids=valid_ids)
            else:
                llm_action_id = _parse_action_id(response, valid_ids=valid_ids)

            # Update conversation history
            conversation_history.append({"role": "user", "content": user_msg})
            conversation_history.append({"role": "assistant", "content": response})
            max_msg = max_hist_turns * 2
            if len(conversation_history) > max_msg:
                conversation_history = conversation_history[-max_msg:]

        is_match = llm_action_id == bfs_action_id if bfs_action_id is not None else False
        is_equiv = llm_action_id in optimal_set and not is_match

        if is_match:
            matches += 1
        elif is_equiv:
            equiv_matches += 1
        total += 1

        llm_action = next((a for a in actions if a.action_id == llm_action_id), None) if llm_action_id else None

        def _action_label(action):
            if action and hasattr(action, "label"):
                return action.label()
            return f"id={getattr(action, 'action_id', '?')}" if action else "None"

        decision_record = {
            "idx": decision_idx,
            "match": is_match,
            "equiv": is_equiv,
            "bfs_action": _action_label(bfs_action),
            "bfs_action_id": bfs_action_id,
            "bfs_result_hp": bfs_result_hp,
            "llm_action": _action_label(llm_action),
            "llm_action_id": llm_action_id,
            "hp_before": state.hero.hp,
            "num_actions": len(actions),
            "n_equiv_optimal": len(optimal_set),
        }
        decisions.append(decision_record)

        if verbose:
            if free_play:
                log.info("  Decision %2d: LLM=%s (HP=%d, %d choices)",
                         decision_idx, decision_record["llm_action"],
                         state.hero.hp, len(actions))
            else:
                status = "✓" if is_match else ("~" if is_equiv else "✗")
                equiv_info = f" [{len(optimal_set)} equiv]" if len(optimal_set) > 1 else ""
                log.info("  Decision %2d: %s BFS=%s LLM=%s (HP=%d, %d choices)%s",
                         decision_idx, status,
                         decision_record["bfs_action"],
                         decision_record["llm_action"],
                         state.hero.hp, len(actions), equiv_info)

        # Execute action: BFS action (oracle path) or LLM action (free play)
        if free_play:
            action_to_execute = llm_action if llm_action else actions[0]
            # Check if fight would kill the hero
            if action_to_execute.type == ActionType.FIGHT and not action_to_execute.can_win:
                log.warning("LLM chose lethal fight at D%d — hero dies", decision_idx)
                state.failed = True
                break
            state.apply_action(action_to_execute)
        else:
            state.apply_action(bfs_action)
        decision_idx += 1

    accuracy = matches / max(1, total)
    equiv_accuracy = (matches + equiv_matches) / max(1, total)

    return {
        "accuracy": accuracy,
        "equiv_accuracy": equiv_accuracy,
        "matches": matches,
        "equiv_matches": equiv_matches,
        "total": total,
        "decisions": decisions,
        "floor": floor_name,
        "final_hp": state.hero.hp,
        "bfs_optimal_hp": bfs_hp,
        "goal_reached": state.goal_reached,
        "eval_mode": eval_mode if eval_mode != "multistep" else f"multistep-{chunk_size}",
        "llm_calls": llm_calls,
    }


def _parse_plan(response: str, valid_ids: set[int]) -> list[int]:
    """Parse PLAN: id1, id2, ... from LLM response. Returns list of valid ids."""
    match = re.search(r"PLAN:\s*([\d,\s]+)", response)
    if not match:
        return []
    ids = []
    for tok in match.group(1).split(","):
        tok = tok.strip()
        if tok.isdigit():
            aid = int(tok)
            ids.append(aid)
    return ids


def _evaluate_map_mode(
    candidate_prompt, runtime_prompt, floor_name, state,
    bfs_hp, task_model, task_mode, verbose, base_mode, chunk_size=0,
):
    """
    Map-based evaluation: LLM sees a text grid + entity details instead of
    a numbered action list. Tests whether the LLM can reason about spatial
    reachability without the pathfinder abstraction.

    base_mode: 'reactive' or 'oneshot'
    """
    from mota.optimizer.evaluator import _call_llm
    from mota.game.types import ActionType

    # Build system prompt with grid map instead of entity-list map
    grid_text = state.format_map_grid_text()
    map_system_prompt = candidate_prompt + "\n\n" + grid_text

    decisions = []
    decision_idx = 0
    llm_calls = 0
    invalid_targets = 0
    conversation_history: list[dict] = []
    max_hist_turns = 6

    if base_mode == "oneshot":
        # Single LLM call with grid + state → coordinate plan
        state_text = state.format_state()
        user_msg = (
            f"{state_text}\n\n"
            "Using the floor grid and entity details above, plan your complete "
            "route through this floor. List every entity coordinate you intend to "
            "act on, in optimal order. Collect free items before fighting.\n"
            "Reply: PLAN: (x1,y1), (x2,y2), (x3,y3), ..."
        )
        llm_calls += 1
        response = _call_llm(
            map_system_prompt, user_msg,
            task_model=task_model, task_mode=task_mode,
        )
        plan_coords = _parse_coord_plan(response)
        plan_queue = list(plan_coords)

        while not state.goal_reached and not state.failed and state.turn < state.max_turns:
            actions = state.get_actions()
            if not actions:
                break
            if len(actions) == 1:
                only = actions[0]
                if only.type == ActionType.FIGHT and not only.can_win:
                    break
                state.apply_action(only)
                continue

            coord_map = {(a.x, a.y): a for a in actions}
            chosen = None
            consumed = 0
            for i, coord in enumerate(plan_queue):
                if coord in coord_map:
                    chosen = coord_map[coord]
                    consumed = i + 1
                    invalid_targets += consumed - 1
                    break
            if chosen is None:
                break
            plan_queue = plan_queue[consumed:]

            if chosen.type == ActionType.FIGHT and not chosen.can_win:
                log.warning("Map-oneshot chose lethal fight at D%d", decision_idx)
                state.failed = True
                decisions.append({
                    "idx": decision_idx, "match": False, "equiv": False,
                    "bfs_action": "None", "bfs_action_id": None, "bfs_result_hp": None,
                    "llm_action": chosen.label() if hasattr(chosen, "label") else f"({chosen.x},{chosen.y})",
                    "llm_action_id": chosen.action_id, "llm_target": [chosen.x, chosen.y],
                    "hp_before": state.hero.hp, "num_actions": len(actions), "n_equiv_optimal": 0,
                })
                break

            if verbose:
                label = chosen.label() if hasattr(chosen, "label") else f"({chosen.x},{chosen.y})"
                log.info("  Decision %2d: LLM=%s (HP=%d, %d choices)", decision_idx, label, state.hero.hp, len(actions))
            decisions.append({
                "idx": decision_idx, "match": False, "equiv": False,
                "bfs_action": "None", "bfs_action_id": None, "bfs_result_hp": None,
                "llm_action": chosen.label() if hasattr(chosen, "label") else f"({chosen.x},{chosen.y})",
                "llm_action_id": chosen.action_id, "llm_target": [chosen.x, chosen.y],
                "hp_before": state.hero.hp, "num_actions": len(actions), "n_equiv_optimal": 0,
            })
            state.apply_action(chosen)
            decision_idx += 1

        return {
            "accuracy": 0.0, "equiv_accuracy": 0.0,
            "matches": 0, "equiv_matches": 0,
            "total": len(decisions), "decision_count": len(decisions),
            "decisions": decisions,
            "floor": floor_name, "final_hp": state.hero.hp,
            "bfs_optimal_hp": bfs_hp, "goal_reached": state.goal_reached,
            "goal_type": "boss",
            "eval_mode": "map-oneshot",
            "llm_calls": llm_calls,
            "plan_coords_count": len(plan_coords),
            "invalid_targets": invalid_targets,
            "note": "Map-grid oneshot: LLM sees text grid, no pathfinder action list.",
        }

    # Reactive map mode
    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        actions = state.get_actions()
        if not actions:
            break
        if len(actions) == 1:
            only = actions[0]
            if only.type == ActionType.FIGHT and not only.can_win:
                break
            state.apply_action(only)
            continue

        # Update grid text for current state (entities removed, hero moved)
        grid_text = state.format_map_grid_text()
        map_system_prompt = candidate_prompt + "\n\n" + grid_text

        state_text = state.format_state()
        coord_map = {(a.x, a.y): a for a in actions}
        reachable_str = ", ".join(f"({a.x},{a.y})" for a in actions)

        user_msg = (
            f"{state_text}\n\n"
            f"You can currently reach these coordinates: {reachable_str}\n"
            "Using the floor grid, entity details, and reachable positions above, "
            "choose the best target. Reply: TARGET: (x,y)"
        )

        prior = conversation_history if conversation_history else None
        llm_calls += 1
        response = _call_llm(
            map_system_prompt, user_msg,
            task_model=task_model, task_mode=task_mode,
            prior_messages=prior,
        )

        # Parse TARGET: (x,y) from response
        target_coords = _parse_coord_plan(response)
        chosen = None
        for coord in target_coords:
            if coord in coord_map:
                chosen = coord_map[coord]
                break
            else:
                invalid_targets += 1

        if chosen is None:
            # LLM couldn't pick a valid reachable target
            if verbose:
                log.warning("  Decision %2d: Map-reactive — no valid target in response", decision_idx)
            invalid_targets += 1
            # Use first available action as fallback
            chosen = actions[0]

        if chosen.type == ActionType.FIGHT and not chosen.can_win:
            log.warning("Map-reactive chose lethal fight at D%d", decision_idx)
            state.failed = True
            decisions.append({
                "idx": decision_idx, "match": False, "equiv": False,
                "bfs_action": "None", "bfs_action_id": None, "bfs_result_hp": None,
                "llm_action": chosen.label() if hasattr(chosen, "label") else f"({chosen.x},{chosen.y})",
                "llm_action_id": chosen.action_id, "llm_target": [chosen.x, chosen.y],
                "hp_before": state.hero.hp, "num_actions": len(actions), "n_equiv_optimal": 0,
            })
            break

        if verbose:
            label = chosen.label() if hasattr(chosen, "label") else f"({chosen.x},{chosen.y})"
            log.info("  Decision %2d: LLM=%s (HP=%d, %d choices)", decision_idx, label, state.hero.hp, len(actions))

        decisions.append({
            "idx": decision_idx, "match": False, "equiv": False,
            "bfs_action": "None", "bfs_action_id": None, "bfs_result_hp": None,
            "llm_action": chosen.label() if hasattr(chosen, "label") else f"({chosen.x},{chosen.y})",
            "llm_action_id": chosen.action_id, "llm_target": [chosen.x, chosen.y],
            "hp_before": state.hero.hp, "num_actions": len(actions), "n_equiv_optimal": 0,
        })

        conversation_history.append({"role": "user", "content": user_msg})
        conversation_history.append({"role": "assistant", "content": response})
        max_msg = max_hist_turns * 2
        if len(conversation_history) > max_msg:
            conversation_history = conversation_history[-max_msg:]

        state.apply_action(chosen)
        decision_idx += 1

    return {
        "accuracy": 0.0, "equiv_accuracy": 0.0,
        "matches": 0, "equiv_matches": 0,
        "total": len(decisions), "decision_count": len(decisions),
        "decisions": decisions,
        "floor": floor_name, "final_hp": state.hero.hp,
        "bfs_optimal_hp": bfs_hp, "goal_reached": state.goal_reached,
        "goal_type": "boss",
        "eval_mode": "map-reactive",
        "llm_calls": llm_calls,
        "invalid_targets": invalid_targets,
        "note": "Map-grid reactive: LLM sees text grid + reachable coords, no numbered action list.",
    }


def _parse_coord_plan(response: str) -> list[tuple[int, int]]:
    """Parse PLAN: (x1,y1), (x2,y2), ... from LLM response."""
    coords = re.findall(r"\((\d+)\s*,\s*(\d+)\)", response)
    return [(int(x), int(y)) for x, y in coords]


def _evaluate_oneshot_free_play(
    candidate_prompt, runtime_prompt, floor_name, state,
    bfs_hp, task_model, task_mode, verbose,
):
    """
    Free-play oneshot: single LLM call produces a coordinate plan,
    executed greedily without Python BFS. For complex floors where
    per-decision BFS is too expensive.
    """
    from mota.optimizer.evaluator import _call_llm
    from mota.game.types import ActionType

    # Build initial state + actions prompt
    initial_actions = state.get_actions()
    if not initial_actions:
        return {
            "accuracy": 0.0, "matches": 0, "total": 0, "decisions": [],
            "floor": floor_name, "final_hp": state.hero.hp,
            "bfs_optimal_hp": bfs_hp, "goal_reached": state.goal_reached,
            "eval_mode": "oneshot", "llm_calls": 0,
        }

    state_text = state.format_state()
    actions_text = state.format_actions(initial_actions)

    # Build coordinate listing for all visible entities
    coord_listing = "\n".join(
        f"  ({a.x},{a.y}) {a.name} [{a.type.value if hasattr(a.type, 'value') else a.type}]"
        + (f" dmg={a.total_damage}" if getattr(a, "total_damage", 0) else "")
        for a in initial_actions
    )

    user_msg = (
        f"{state_text}\n\n{actions_text}\n\n"
        f"Entity coordinates for planning:\n{coord_listing}\n\n"
        "ONE-SHOT PLANNING MODE: Using the floor map and all visible entities above, "
        "output your complete strategic plan for this floor as an ordered list of "
        "entity coordinates to act on in optimal order. Include every entity.\n"
        "Reply: PLAN: (x1,y1), (x2,y2), (x3,y3), ..."
    )

    response = _call_llm(
        runtime_prompt, user_msg,
        task_model=task_model, task_mode=task_mode,
    )
    plan_coords = _parse_coord_plan(response)
    plan_queue = list(plan_coords)

    decisions = []
    decision_idx = 0
    stale_skipped = 0

    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        actions = state.get_actions()
        if not actions:
            break

        # Auto-execute forced single actions
        if len(actions) == 1:
            only = actions[0]
            if only.type == ActionType.FIGHT and not only.can_win:
                break
            state.apply_action(only)
            continue

        # Match next planned coordinate to an available action
        coord_map = {(a.x, a.y): a for a in actions}
        chosen = None
        consumed = 0
        for i, coord in enumerate(plan_queue):
            if coord in coord_map:
                chosen = coord_map[coord]
                consumed = i + 1
                stale_skipped += consumed - 1
                break

        if chosen is None:
            # No more plan coords match available actions — plan exhausted
            break

        plan_queue = plan_queue[consumed:]

        # Check lethal fight
        if chosen.type == ActionType.FIGHT and not chosen.can_win:
            log.warning("LLM chose lethal fight at D%d — hero dies", decision_idx)
            state.failed = True
            decisions.append({
                "idx": decision_idx, "match": False, "equiv": False,
                "bfs_action": "None", "bfs_action_id": None, "bfs_result_hp": None,
                "llm_action": chosen.label() if hasattr(chosen, "label") else f"({chosen.x},{chosen.y})",
                "llm_action_id": chosen.action_id,
                "llm_target": [chosen.x, chosen.y],
                "hp_before": state.hero.hp, "num_actions": len(actions),
                "n_equiv_optimal": 0,
            })
            break

        if verbose:
            label = chosen.label() if hasattr(chosen, "label") else f"({chosen.x},{chosen.y})"
            log.info("  Decision %2d: LLM=%s (HP=%d, %d choices)",
                     decision_idx, label, state.hero.hp, len(actions))

        decisions.append({
            "idx": decision_idx, "match": False, "equiv": False,
            "bfs_action": "None", "bfs_action_id": None, "bfs_result_hp": None,
            "llm_action": chosen.label() if hasattr(chosen, "label") else f"({chosen.x},{chosen.y})",
            "llm_action_id": chosen.action_id,
            "llm_target": [chosen.x, chosen.y],
            "hp_before": state.hero.hp, "num_actions": len(actions),
            "n_equiv_optimal": 0,
        })

        state.apply_action(chosen)
        decision_idx += 1

    return {
        "accuracy": 0.0, "equiv_accuracy": 0.0,
        "matches": 0, "equiv_matches": 0,
        "total": len(decisions),
        "decision_count": len(decisions),
        "decisions": decisions,
        "floor": floor_name,
        "final_hp": state.hero.hp,
        "bfs_optimal_hp": bfs_hp,
        "goal_reached": state.goal_reached,
        "goal_type": "boss",
        "eval_mode": "oneshot",
        "llm_calls": 1,
        "plan_coords_count": len(plan_coords),
        "stale_targets_skipped": stale_skipped,
        "note": "Map-first one-shot coordinate plan: no Python BFS oracle and no action IDs.",
    }


def _evaluate_oneshot(
    candidate_prompt, runtime_prompt, floor_name, state, gd, scenario,
    bfs_hp, task_model, task_mode, verbose, bfs_max_states=50_000,
):
    """Oneshot evaluation: single LLM call produces full plan; compare to BFS."""
    from mota.optimizer.evaluator import _call_llm, _parse_action_id
    from mota.game.types import ActionType

    # First, collect all BFS oracle decisions by simulating
    bfs_decisions = []
    sim_state = state  # state is already fresh from _load_floor_scenario
    decision_idx = 0

    while (not sim_state.goal_reached and not sim_state.failed
           and sim_state.turn < sim_state.max_turns):
        actions = sim_state.get_actions()
        if not actions:
            break
        if len(actions) == 1:
            only = actions[0]
            if only.type == ActionType.FIGHT and not only.can_win:
                break
            sim_state.apply_action(only)
            continue

        per_decision_max = min(bfs_max_states, 50_000)
        optimal_set = _bfs_optimal_actions(
            sim_state.floor, sim_state.hero, sim_state.removed, actions,
            gd, scenario.goal, max_states=per_decision_max,
        )
        if not optimal_set:
            break

        bfs_aid = next(iter(optimal_set))
        bfs_hp_res = optimal_set[bfs_aid][0]

        bfs_action = next(a for a in actions if a.action_id == bfs_aid)
        bfs_decisions.append({
            "idx": decision_idx,
            "state_text": sim_state.format_state(),
            "actions_text": sim_state.format_actions(actions),
            "actions": actions,
            "bfs_action_id": bfs_aid,
            "bfs_action": bfs_action.label() if hasattr(bfs_action, "label") else f"id={bfs_aid}",
            "bfs_result_hp": bfs_hp_res,
            "hp_before": sim_state.hero.hp,
            "num_actions": len(actions),
            "optimal_set": optimal_set,
        })
        sim_state.apply_action(bfs_action)
        decision_idx += 1

    if not bfs_decisions:
        return {
            "accuracy": 0.0, "matches": 0, "total": 0, "decisions": [],
            "floor": floor_name, "final_hp": sim_state.hero.hp,
            "bfs_optimal_hp": bfs_hp, "goal_reached": sim_state.goal_reached,
            "eval_mode": "oneshot", "llm_calls": 0,
        }

    # Build oneshot prompt with all decision states
    full_plan_text = "Below are the sequential game states. Provide the full plan.\n\n"
    for bd in bfs_decisions:
        full_plan_text += f"--- Decision {bd['idx']} ---\n{bd['state_text']}\n{bd['actions_text']}\n\n"
    full_plan_text += (
        f"Reply with PLAN: a comma-separated list of {len(bfs_decisions)} action IDs, "
        f"one per decision above, in order."
    )

    response = _call_llm(
        runtime_prompt, full_plan_text,
        task_model=task_model,
        task_mode=task_mode,
        prior_messages=None,
    )

    # Parse plan: extract all integers
    all_ids = [int(m) for m in re.findall(r"\d+", response)]

    matches = 0
    equiv_matches = 0
    decisions_out = []
    for i, bd in enumerate(bfs_decisions):
        llm_aid = all_ids[i] if i < len(all_ids) else None
        is_match = llm_aid == bd["bfs_action_id"]
        optimal_set = bd.get("optimal_set", {})
        is_equiv = (not is_match) and (llm_aid in optimal_set) if llm_aid is not None else False
        n_equiv = len(optimal_set)
        if is_match:
            matches += 1
        elif is_equiv:
            equiv_matches += 1

        llm_label = "None"
        if llm_aid is not None:
            la = next((a for a in bd["actions"] if a.action_id == llm_aid), None)
            llm_label = la.label() if la and hasattr(la, "label") else f"id={llm_aid}"

        decisions_out.append({
            "idx": bd["idx"],
            "match": is_match,
            "equiv": is_equiv,
            "bfs_action": bd["bfs_action"],
            "bfs_action_id": bd["bfs_action_id"],
            "bfs_result_hp": bd["bfs_result_hp"],
            "llm_action": llm_label,
            "llm_action_id": llm_aid,
            "hp_before": bd["hp_before"],
            "num_actions": bd["num_actions"],
            "n_equiv_optimal": n_equiv,
        })

        if verbose:
            status = "✓" if is_match else ("~" if is_equiv else "✗")
            log.info("  Decision %2d: %s BFS=%s LLM=%s (HP=%d, %d choices, %d equiv)",
                     bd["idx"], status, bd["bfs_action"], llm_label,
                     bd["hp_before"], bd["num_actions"], n_equiv)

    total = len(bfs_decisions)
    return {
        "accuracy": matches / max(1, total),
        "equiv_accuracy": (matches + equiv_matches) / max(1, total),
        "matches": matches,
        "equiv_matches": equiv_matches,
        "total": total,
        "decisions": decisions_out,
        "floor": floor_name,
        "final_hp": sim_state.hero.hp,
        "bfs_optimal_hp": bfs_hp,
        "goal_reached": sim_state.goal_reached,
        "eval_mode": "oneshot",
        "llm_calls": 1,
    }


# ---------------------------------------------------------------------------
# GEPA integration
# ---------------------------------------------------------------------------

def run_gepa_bfs_alignment(
    floor_name: str = "simple",
    task_model: str | None = None,
    task_mode: str | None = None,
    max_calls: int = 30,
    early_stop: float = 1.0,
    seed_prompt: str | None = None,
    eval_mode: str = "reactive",
    experiment_label: str | None = None,
    fitness_mode: str = "equiv",
):
    """Run GEPA optimization with BFS alignment as the fitness metric.

    Uses equiv_accuracy (exact + equivalent-optimal matches) as the default
    fitness signal, since multiple BFS-equivalent actions can be equally optimal.

    ``fitness_mode='hybrid'`` adds an autonomous free-play goal bonus so prompts
    that actually defeat the boss outrank prompts that only align locally under
    the BFS-forced trajectory.
    """
    import datetime

    try:
        from gepa.optimize_anything import (
            optimize_anything, GEPAConfig, EngineConfig, ReflectionConfig,
        )
    except ImportError:
        print("ERROR: gepa not installed. Run: pip install gepa")
        sys.exit(1)

    from mota.optimizer.evaluator import make_rotating_litellm_lm
    from mota.optimizer.seed_prompt import SEED_PROMPT
    from dotenv import load_dotenv

    # Load env
    for env_dir in [_root]:
        env_file = env_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            break

    actual_seed = seed_prompt or _load_best_prompt() or SEED_PROMPT

    # Configure GEPA
    base_url = os.environ.get("SAIA_BASE_URL",
                               "https://chat-ai.academiccloud.de/v1")
    os.environ["OPENAI_API_BASE"] = base_url

    reflection_model_name = os.environ.get("MOTA_REFLECTION_MODEL",
                                            "qwen3.5-397b-a17b")
    raw_reflection_lm = make_rotating_litellm_lm(
        f"openai/{reflection_model_name}",
        base_url=base_url,
    )

    # --- Reflection LM capture wrapper ---
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    label = experiment_label or f"gepa-bfs-{floor_name}"
    traces_dir = _root / "results" / "prompt_history"
    traces_dir.mkdir(parents=True, exist_ok=True)
    traces_file = traces_dir / f"reflection_traces_{label}_{timestamp}.jsonl"

    _reflection_call_count = [0]
    _reflection_start = [time.time()]

    def _capturing_reflection_lm(prompt, **kwargs):
        _reflection_call_count[0] += 1
        call_no = _reflection_call_count[0]
        elapsed = time.time() - _reflection_start[0]
        print(f"  [Reflection #{call_no}] calling ({elapsed:.0f}s elapsed, "
              f"prompt={len(prompt):.0f} chars)...")
        response = raw_reflection_lm(prompt, **kwargs)
        resp_text = str(response) if response else ""
        with open(traces_file, "a", encoding="utf-8") as tf:
            json.dump({
                "call": call_no,
                "timestamp": datetime.datetime.now().isoformat(),
                "elapsed_s": round(elapsed, 1),
                "prompt_chars": len(prompt),
                "response_chars": len(resp_text),
                "prompt": prompt[:8000],
                "response": resp_text[:8000],
            }, tf, ensure_ascii=False)
            tf.write("\n")
        print(f"  [Reflection #{call_no}] done ({len(resp_text)} chars response)")
        return response

    if fitness_mode == "hybrid":
        objective = (
            f"Maximize a hybrid score for an LLM playing the Magic Tower (MOTA) "
            f"game on floor {floor_name}. The candidate text is the LLM's system "
            f"prompt. Half the score comes from BFS-equivalent per-decision "
            f"alignment, and half comes from actually defeating the boss during "
            f"autonomous free play. Prompts that only look correct under a "
            f"BFS-forced trajectory should score lower than prompts that truly "
            f"clear the floor."
        )
    else:
        objective = (
            f"Maximize the per-decision accuracy of an LLM playing the Magic Tower "
            f"(MOTA) game on floor {floor_name}. The candidate text is the LLM's "
            f"system prompt. The score is the fraction of decisions that match "
            f"the BFS-optimal action (including equivalent-optimal alternatives). "
            f"A perfect score is 1.0 (100% of decisions match the provably-optimal "
            f"BFS route). The LLM must reason about damage costs, item priorities, "
            f"and path strategy to match the optimal play."
        )

    config = GEPAConfig(
        engine=EngineConfig(
            max_metric_calls=max_calls,
            parallel=False,
            display_progress_bar=False,
        ),
        reflection=ReflectionConfig(
            reflection_lm=_capturing_reflection_lm,
        ),
    )

    call_count = [0]
    best_score = [0.0]
    best_prompt = [actual_seed]
    eval_history = []

    def _evaluator(candidate_prompt):
        call_count[0] += 1
        print(
            f"\n  [GEPA #{call_count[0]}] evaluating forced BFS alignment "
            f"(prompt={len(candidate_prompt)} chars)..."
        )
        result = evaluate_bfs_alignment(
            candidate_prompt,
            floor_name=floor_name,
            task_model=task_model,
            task_mode=task_mode,
            eval_mode=eval_mode,
            verbose=True,
        )
        exact = result["accuracy"]
        equiv = result.get("equiv_accuracy", exact)
        free_play_result = None
        if fitness_mode == "hybrid":
            print(f"  [GEPA #{call_count[0]}] evaluating autonomous free play...")
            free_play_result = evaluate_bfs_alignment(
                candidate_prompt,
                floor_name=floor_name,
                task_model=task_model,
                task_mode=task_mode,
                eval_mode=eval_mode,
                verbose=False,
                free_play=True,
            )
            score = 0.5 * equiv + 0.5 * float(free_play_result["goal_reached"])
        else:
            score = equiv

        line = (
            f"\n  [GEPA #{call_count[0]}] BFS alignment: "
            f"exact={exact:.1%}  equiv={equiv:.1%}  "
            f"({result['matches']}+{result.get('equiv_matches',0)}/{result['total']})"
        )
        if free_play_result is not None:
            line += (
                f"  |  free_play_goal={free_play_result['goal_reached']} "
                f"hp={free_play_result['final_hp']}  => score={score:.1%}"
            )
        print(line)

        # Log details for GEPA reflection
        try:
            import gepa.optimize_anything as oa
            oa.log(f"BFS alignment: exact={exact:.1%}, equiv={equiv:.1%}")
            for d in result["decisions"]:
                status = "✓" if d["match"] else ("~" if d.get("equiv") else "✗")
                oa.log(f"  {status} Decision {d['idx']}: BFS={d['bfs_action']} LLM={d['llm_action']}")
            if not result["goal_reached"]:
                oa.log("WARNING: Floor not completed on BFS path")
        except (ImportError, AttributeError):
            pass

        eval_history.append({
            "call": call_count[0],
            "exact_accuracy": round(exact, 4),
            "equiv_accuracy": round(equiv, 4),
            "fitness_mode": fitness_mode,
            "score": round(score, 4),
            "matches": result["matches"],
            "equiv_matches": result.get("equiv_matches", 0),
            "total": result["total"],
            "goal_reached": result["goal_reached"],
            "final_hp": result["final_hp"],
            "free_play_goal_reached": free_play_result["goal_reached"] if free_play_result else None,
            "free_play_final_hp": free_play_result["final_hp"] if free_play_result else None,
            "prompt_chars": len(candidate_prompt),
        })

        if score > best_score[0]:
            best_score[0] = score
            best_prompt[0] = candidate_prompt

        return score

    print("=" * 60)
    print(f"GEPA BFS ALIGNMENT — {floor_name}")
    print(f"Experiment: {label}")
    print("=" * 60)
    print(f"Max evaluations: {max_calls}")
    print(f"Task model: {task_model or os.environ.get('MOTA_TASK_MODEL', 'auto')}")
    print(f"Reflection model: {reflection_model_name}")
    if fitness_mode == "hybrid":
        print("Fitness: 50% equiv_accuracy + 50% autonomous free-play goal success")
    else:
        print("Fitness: equiv_accuracy (exact + equivalent-optimal)")
    print(f"Early stop: {early_stop:.0%}")
    print(f"Seed prompt length: {len(actual_seed)} chars")
    print(f"Reflection traces: {traces_file}")
    print()

    run_start = time.time()
    try:
        gepa_result = optimize_anything(
            evaluator=_evaluator,
            seed_candidate=actual_seed,
            objective=objective,
            config=config,
        )

        # Save result
        output_dir = _root / "results"
        output_dir.mkdir(exist_ok=True)
        result_path = output_dir / f"bfs_aligned_prompt_{label}_{timestamp}.json"

        final_prompt = best_prompt[0]
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({
                "experiment_label": label,
                "best_prompt": final_prompt,
                "best_score": best_score[0],
                "seed_prompt": actual_seed,
                "floor": floor_name,
                "evaluations": call_count[0],
                "task_model": task_model,
                "task_mode": task_mode,
                "reflection_model": reflection_model_name,
                "eval_mode": eval_mode,
                "fitness_mode": fitness_mode,
                "objective": objective,
                "reflection_traces_file": str(traces_file),
                "eval_history": eval_history,
                "elapsed_s": round(time.time() - run_start, 1),
                "timestamp": timestamp,
            }, f, ensure_ascii=False, indent=2)

        # Also save as latest for easy loading
        latest_path = output_dir / "bfs_aligned_prompt.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump({
                "best_prompt": final_prompt,
                "best_score": best_score[0],
                "floor": floor_name,
                "evaluations": call_count[0],
                "task_model": task_model,
            }, f, ensure_ascii=False, indent=2)

        print(f"\n{'=' * 60}")
        print(f"GEPA optimization complete!")
        print(f"Best BFS alignment (equiv): {best_score[0]:.1%}")
        print(f"Evaluations used: {call_count[0]}")
        print(f"Elapsed: {time.time() - run_start:.0f}s")
        print(f"Saved to: {result_path}")
        print(f"Reflection traces: {traces_file}")
        print(f"{'=' * 60}")

        return gepa_result

    except Exception as e:
        if "EarlyStop" in type(e).__name__:
            print(f"\nEarly stop reached: {best_score[0]:.1%}")
        else:
            raise


def _load_best_prompt() -> str | None:
    """Load the best available prompt (GEPA-optimized or aligned)."""
    # Try BFS-aligned prompt first
    aligned = _root / "results" / "bfs_aligned_prompt.json"
    if aligned.exists():
        with open(aligned, encoding="utf-8") as f:
            return json.load(f)["best_prompt"]

    # Fall back to GEPA v3
    gepa = _root / "results" / "gepa_result.json"
    if gepa.exists():
        with open(gepa, encoding="utf-8") as f:
            return json.load(f)["best_prompt"]

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Phase 2: Align system prompt to BFS ground truth via GEPA"
    )
    parser.add_argument("--floor", default="simple",
                        help="Floor to align on (default: simple)")
    parser.add_argument("--test", action="store_true",
                        help="Single evaluation (no GEPA optimization)")
    parser.add_argument("--gepa", action="store_true",
                        help="Run full GEPA optimization")
    parser.add_argument("--max-calls", type=int, default=30,
                        help="Max GEPA evaluations")
    parser.add_argument("--early-stop", type=float, default=1.0,
                        help="Stop when accuracy reaches this threshold")
    parser.add_argument("--task-model", default=None,
                        help="LLM model to evaluate")
    parser.add_argument("--task-mode", default=None,
                        help="LLM mode (thinking/instruct)")
    parser.add_argument("--mode", default="reactive",
                        help="Evaluation mode: reactive, oneshot, multistep-N (default: reactive)")
    parser.add_argument("--prompt", default=None,
                        help="Path to custom seed prompt file")
    parser.add_argument("--experiment-label", default=None,
                        help="Label for experiment output files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show per-decision details")
    parser.add_argument("--free-play", action="store_true",
                        help="Execute the LLM's chosen actions instead of forcing the BFS path")
    parser.add_argument("--fitness-mode", default="equiv", choices=["equiv", "hybrid"],
                        help="GEPA fitness: pure BFS-equivalent alignment or hybrid alignment + free-play success")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load env
    from dotenv import load_dotenv
    for env_dir in [_root]:
        if (env_dir / ".env").exists():
            load_dotenv(env_dir / ".env")
            break

    seed = None
    if args.prompt:
        seed = Path(args.prompt).read_text(encoding="utf-8")

    if args.test:
        # Single evaluation
        prompt = seed or _load_best_prompt()
        if prompt is None:
            from mota.optimizer.seed_prompt import SEED_PROMPT
            prompt = SEED_PROMPT

        if args.free_play:
            print(f"Evaluating autonomous free-play on {args.floor} (mode={args.mode})...")
        else:
            print(f"Evaluating BFS alignment on {args.floor} (mode={args.mode})...")
        print(f"Prompt length: {len(prompt)} chars")
        print()

        result = evaluate_bfs_alignment(
            prompt,
            floor_name=args.floor,
            task_model=args.task_model,
            task_mode=args.task_mode,
            eval_mode=args.mode,
            verbose=True,
            free_play=args.free_play,
        )

        print(f"\n{'=' * 60}")
        if args.free_play:
            print("Free-play rollout summary:")
        else:
            print(f"BFS Alignment: {result['matches']}/{result['total']} = {result['accuracy']:.1%} (exact)")
            print(f"BFS Equiv:     {result['matches']+result.get('equiv_matches',0)}/{result['total']} = {result.get('equiv_accuracy', result['accuracy']):.1%} (exact+equiv)")
        print(f"Mode: {result.get('eval_mode', args.mode)}")
        print(f"LLM calls: {result.get('llm_calls', '?')}")
        print(f"Floor completed: {result['goal_reached']}")
        print(f"Final HP: {result['final_hp']} (BFS optimal: {result['bfs_optimal_hp']})")
        if not args.free_play:
            print("Note: alignment mode executes the BFS-optimal action after each decision; completion here does not imply autonomous success.")
        print()
        for d in result["decisions"]:
            if args.free_play:
                print(f"  RUN Decision {d['idx']:2d}: LLM={d['llm_action']}")
            else:
                equiv_tag = "~" if d.get("equiv") else ""
                status = f"Y{equiv_tag}" if d["match"] or d.get("equiv") else "N"
                equiv_info = f" [{d.get('n_equiv_optimal', 1)} equiv]" if d.get('n_equiv_optimal', 1) > 1 else ""
                print(f"  {status:3s} Decision {d['idx']:2d}: "
                      f"BFS={d['bfs_action']:<35s} LLM={d['llm_action']}{equiv_info}")

    elif args.gepa:
        run_gepa_bfs_alignment(
            floor_name=args.floor,
            task_model=args.task_model,
            task_mode=args.task_mode,
            max_calls=args.max_calls,
            early_stop=args.early_stop,
            seed_prompt=seed,
            eval_mode=args.mode,
            experiment_label=args.experiment_label,
            fitness_mode=args.fitness_mode,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
