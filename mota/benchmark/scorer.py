"""
Scorer — evaluates a game run against the walkthrough baseline.
Returns a composite score in [0.0, 1.0].
"""
from __future__ import annotations

from ..game.state import GameState
from ..game.types import ActionType, StepTrace
from .walkthrough import MT3_FINAL


# ── BFS reference baselines (Java BFS solver optimal values) ──────────────
# Keys are floor filenames or fixture IDs used by configure_scenario().
# target_hp   = BFS-optimal final HP (upper bound)
# target_atk  = BFS-optimal final ATK
# target_def  = BFS-optimal final DEF
# ref_steps   = number of BFS decision nodes (≈ optimal step count)
# enemies_total = total enemies on the floor
# enemies_killed = enemies killed in BFS solution (some are skipped)
BFS_REFERENCE = {
    "单层-最简单": {
        "target_hp": 13, "target_atk": 13, "target_def": 8,
        # ref_steps = total game actions (fights+collects+doors), NOT BFS nodes.
        # BFS has 12 decision nodes but each bundles eatItem (auto-collect).
        # Actual optimal turn count: 12 fights + 5 keys + 4 doors + 8 potions + 7 gems = 36
        "ref_steps": 36, "enemies_total": 13, "enemies_killed": 12,
    },
    "单层-复杂": {
        # Exact optimum (2026-09-29, tools/java_bfs --summary, route replayed legal in the engine).
        # The published Java run() reported HP 22 / ATK 14 / DEF 17: it keeps the first-popped state per
        # visited set, not the best (thesis §6.6.1).
        "target_hp": 68, "target_atk": 16, "target_def": 20,
        # BFS has 20 decision nodes; estimated game actions ≈ 40
        "ref_steps": 40, "enemies_total": 26, "enemies_killed": 16,
    },
    # 宿命的华音 and 无上之光 have no BFS solution — omitted
}

# Aliases: support English names and various character forms
BFS_REFERENCE["simple"] = BFS_REFERENCE["单层-最简单"]
BFS_REFERENCE["complex"] = BFS_REFERENCE["单层-复杂"]
BFS_REFERENCE["单层-最简单.txt"] = BFS_REFERENCE["单层-最简单"]
BFS_REFERENCE["单层-复杂.txt"] = BFS_REFERENCE["单层-复杂"]
BFS_REFERENCE["simple.txt"] = BFS_REFERENCE["单层-最简单"]
BFS_REFERENCE["complex.txt"] = BFS_REFERENCE["单层-复杂"]


def _load_generated_references() -> None:
    """Solver-verified generated and hand-designed boss floors (data/floors/{gen,hand}/manifest.json)."""
    import json
    from pathlib import Path
    for sub in ("gen", "hand"):
        p = Path(__file__).resolve().parents[2] / "data" / "floors" / sub / "manifest.json"
        if not p.exists():
            continue
        for f in json.loads(p.read_text(encoding="utf-8")).get("floors", []):
            BFS_REFERENCE[f["name"]] = {k: f[k] for k in ("target_hp", "target_atk", "target_def", "ref_steps",
                                                          "enemies_total", "enemies_killed")}


_load_generated_references()


def two_tier_outcome(state: GameState, target_hp: int | None) -> dict:
    """Primary/secondary outcome used for all headline reporting.

    success   : goal reached with the hero alive (a lethal boss fight is a failure).
    hp_ratio  : final_hp / reference_hp, only defined on success.
    goal_score: lexicographic scalar for optimisers that need one number —
                success -> 0.5 + 0.5*min(1, hp_ratio); alive failure -> 0.35*completion;
                death -> 0.15*completion.  Success therefore always outranks failure,
                and surviving always outranks dying, unlike the legacy composite.
    """
    alive = state.hero.hp > 0
    if state.goal in ("boss", "clear_all_enemies", "stairs"):
        success = bool(state.goal_reached) and alive
    else:
        success = alive and state.remaining_enemies() == 0
    killed = state.initial_enemies - state.remaining_enemies()
    completion = min(1.0, killed / max(1, state.initial_enemies))
    hp_ratio = None
    if success and target_hp:
        hp_ratio = round(state.hero.hp / target_hp, 4)
    if success:
        goal_score = 0.5 + 0.5 * min(1.0, hp_ratio if hp_ratio is not None else 1.0)
    elif alive:
        goal_score = 0.35 * completion
    else:
        goal_score = 0.15 * completion
    return {
        "success": success,
        "alive": alive,
        "hp_ratio": hp_ratio,
        "goal_score": round(goal_score, 4),
    }


def _score_against_recording(state: GameState, recording: dict) -> dict:
    expected = recording.get("expected") or {}
    violations = _collect_violations(state, is_mt3=False)

    enemies_remaining = state.remaining_enemies()
    expected_remaining = max(0, int(expected.get("enemies_remaining", 0)))
    target_kills = max(1, state.initial_enemies - expected_remaining)
    actual_kills = state.initial_enemies - enemies_remaining
    completion = min(1.0, actual_kills / target_kills)
    if expected.get("goal_reached") and not state.goal_reached:
        violations.append("goal_not_reached")

    target_hp = max(1, int(expected.get("hp", state._initial_hp)))
    if state.hero.hp <= 0:
        hp_score = 0.0
    elif state.hero.hp >= target_hp:
        hp_score = 1.0
    else:
        hp_score = state.hero.hp / target_hp

    target_turns = max(1, int(expected.get("turns", max(1, state.turn))))
    actual_steps = state.turn
    if actual_steps <= target_turns:
        efficiency = 1.0
    else:
        efficiency = max(0.0, 1.0 - (actual_steps - target_turns) / target_turns)

    target_atk = max(1, int(expected.get("atk", max(1, state.hero.atk))))
    target_def = max(1, int(expected.get("def", max(1, state.hero.def_))))
    atk_score = min(1.0, state.hero.atk / target_atk)
    def_score = min(1.0, state.hero.def_ / target_def)
    shop_score = (atk_score + def_score) / 2.0

    violation_penalty = min(1.0, len(violations) * 0.15)
    violation_score = 1.0 - violation_penalty

    total = (
        0.35 * completion +
        0.25 * hp_score +
        0.15 * efficiency +
        0.15 * shop_score +
        0.10 * violation_score
    )

    result = {
        "total": round(total, 4),
        "completion": round(completion, 4),
        "hp_score": round(hp_score, 4),
        "efficiency": round(efficiency, 4),
        "shop_score": round(shop_score, 4),
        "violation_score": round(violation_score, 4),
        "violations": violations,
        "details": {
            "enemies_killed": actual_kills,
            "enemies_total": state.initial_enemies,
            "final_hp": state.hero.hp,
            "target_hp": target_hp,
            "steps": state.turn,
            "ref_steps": target_turns,
            "hero_atk": state.hero.atk,
            "hero_def": state.hero.def_,
            "target_atk": target_atk,
            "target_def": target_def,
            "benchmark_id": recording.get("id"),
            "benchmark_label": recording.get("label"),
            "benchmark_source": recording.get("source", "manual"),
        },
    }
    result.update(two_tier_outcome(state, target_hp))
    result["goal"] = state.goal
    result["goal_reached"] = bool(state.goal_reached)
    return result


def score_run(state: GameState, fixture_id: str = "mt3-walkthrough") -> dict:
    """
    Score a completed game run. Returns:
    {
        "total": float 0–1,
        "completion": float 0–1,
        "hp_score": float 0–1,
        "efficiency": float 0–1,
        "shop_score": float 0–1,
        "violations": list[str],
        "details": dict,
    }
    """
    # BFS reference takes priority: it provides ground-truth optimal targets.
    # Recording-based targets (expected.hp) reflect a specific manual run and can
    # be stale or suboptimal — they must not override the BFS score gradient.
    _bfs_check = BFS_REFERENCE.get(fixture_id) or BFS_REFERENCE.get(state.floor.floor_id)
    if _bfs_check is None:
        try:
            from . import recording_store
            recording = recording_store.get_active_recording(state.floor.floor_id)
        except Exception:
            recording = None
        if recording is not None:
            return _score_against_recording(state, recording)

    is_mt3 = "mt3" in fixture_id.lower() or state.floor.floor_id.startswith("MT")
    bfs_ref = BFS_REFERENCE.get(fixture_id) or BFS_REFERENCE.get(state.floor.floor_id)
    expected = MT3_FINAL if is_mt3 else None
    violations = []

    # --- Completion (0.35) ---
    enemies_remaining = state.remaining_enemies()
    if bfs_ref:
        # BFS often skips monsters; score against BFS kill count, not total
        target_kills = bfs_ref["enemies_killed"]
        actual_kills = state.initial_enemies - enemies_remaining
        completion = min(1.0, actual_kills / max(1, target_kills))
    elif enemies_remaining == 0:
        completion = 1.0
    else:
        killed = state.initial_enemies - enemies_remaining
        completion = killed / max(1, state.initial_enemies)

    # --- HP Score (0.25) ---
    if bfs_ref:
        target_hp = bfs_ref["target_hp"]
    elif expected:
        target_hp = expected["hp"]  # 448
    else:
        # Generic: score based on HP preservation ratio (starting HP)
        target_hp = state._initial_hp
    if state.hero.hp <= 0:
        hp_score = 0.0
    elif state.hero.hp >= target_hp:
        if bfs_ref:
            # On BFS reference floors, target_hp is the OPTIMAL HP *after* fighting
            # all required enemies (including the boss). Ending with much more HP
            # means the boss was skipped. Penalise: target/actual (e.g. 13/509 = 0.026).
            hp_score = target_hp / state.hero.hp
        else:
            hp_score = 1.0
    else:
        hp_score = state.hero.hp / target_hp

    # --- Step Efficiency (0.15) ---
    if bfs_ref:
        ref_steps = bfs_ref["ref_steps"]
    elif is_mt3:
        ref_steps = 33  # MT3 walkthrough takes ~33 actions
    else:
        ref_steps = max(10, state.initial_enemies * 2)
    actual_steps = state.turn
    if actual_steps <= ref_steps:
        efficiency = 1.0
    else:
        efficiency = max(0.0, 1.0 - (actual_steps - ref_steps) / ref_steps)

    # --- Shop Score (0.15) ---
    if is_mt3:
        shop_score = 0.0
        for purchases in state.shop_purchases.values():
            if "def" in purchases:
                shop_score = 1.0
                break
        if not state.shop_purchases:
            shop_score = 0.3  # Partial credit for not buying wrong thing
    elif bfs_ref:
        # BFS test floors: stat score replaces shop score (no shops on most AI floors)
        target_atk = bfs_ref.get("target_atk", max(1, state.hero.atk))
        target_def = bfs_ref.get("target_def", max(1, state.hero.def_))
        atk_score = min(1.0, state.hero.atk / max(1, target_atk))
        def_score = min(1.0, state.hero.def_ / max(1, target_def))
        shop_score = (atk_score + def_score) / 2.0
    else:
        # Generic scoring: made purchases = good, no shop = neutral
        if state.shop_purchases:
            shop_score = 1.0
        else:
            shop_score = 0.5  # No shop on floor or didn't visit

    # --- Violations (0.10) ---
    violations = _collect_violations(state, is_mt3=is_mt3)
    # A surviving boss is a critical failure on ANY boss-goal floor. This must not
    # depend on the floor being present in BFS_REFERENCE, or an unknown floor would
    # silently report a surviving boss as a clean run.
    boss_goal_failed = state.goal == "boss" and not state.goal_reached
    if boss_goal_failed:
        violations.append("boss_not_killed")
    violation_penalty = min(1.0, len(violations) * 0.15)
    violation_score = 1.0 - violation_penalty

    # --- Composite ---
    total = (
        0.35 * completion +
        0.25 * hp_score +
        0.15 * efficiency +
        0.15 * shop_score +
        0.10 * violation_score
    )

    # --- Boss-kill hard multiplier ---
    # If the floor requires a boss kill (goal="boss") and the boss was not killed,
    # halve the total. This ensures boss-not-killed scores stay below 0.50, cleanly
    # separated from any successful boss-kill run.
    if boss_goal_failed:
        total *= 0.5

    result = {
        "total": round(total, 4),
        "completion": round(completion, 4),
        "hp_score": round(hp_score, 4),
        "efficiency": round(efficiency, 4),
        "shop_score": round(shop_score, 4),
        "violation_score": round(violation_score, 4),
        "violations": violations,
        "goal": state.goal,
        "goal_reached": bool(state.goal_reached),
        "failed": bool(state.failed),
        "details": {
            "enemies_killed": state.initial_enemies - enemies_remaining,
            "enemies_total": state.initial_enemies,
            "final_hp": state.hero.hp,
            "target_hp": target_hp,
            "steps": state.turn,
            "ref_steps": ref_steps,
            "hero_atk": state.hero.atk,
            "hero_def": state.hero.def_,
            "bfs_reference": fixture_id if bfs_ref else None,
        },
    }
    result.update(two_tier_outcome(state, target_hp))
    return result


def _collect_violations(state: GameState, is_mt3: bool = True) -> list[str]:
    """Detect strategic violations in the execution trace."""
    violations = []

    for trace in state.history:
        action = trace.action

        # Suicide fights
        if action.type == ActionType.FIGHT and trace.hero_after["hp"] <= 0:
            violations.append(f"suicide_fight: {action.name} at ({action.x},{action.y})")

        # MT3-specific violations only
        if not is_mt3:
            continue

        # Fighting before collecting major items
        if action.type == ActionType.FIGHT:
            # Check if sword was collected before this fight
            sword_collected_before = any(
                t.action.item_id == "sword1"
                for t in state.history[:state.history.index(trace)]
                if t.action.type == ActionType.COLLECT
            )
            # If ATK is still 10 and fighting expensive monsters
            if trace.hero_before["atk"] <= 10 and action.total_damage > 200:
                # Check if sword is reachable — approximate check
                pass  # We track this but don't penalize harshly

        # Pre-sword corridor fights (center corridor with high damage)
        if (action.type == ActionType.FIGHT and
                trace.hero_before["atk"] < 20 and
                action.x >= 4 and action.y <= 6 and
                action.total_damage > 100):
            violations.append(f"pre_sword_corridor: {action.name} at ({action.x},{action.y})")

        # Wrong shop choice
        if action.type == ActionType.SHOP_BUY and action.shop_choice != "def":
            violations.append(f"wrong_shop: bought {action.shop_choice} instead of def")

    return violations
