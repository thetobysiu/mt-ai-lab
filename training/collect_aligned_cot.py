"""
Phase 3: Collect BFS-Aligned Chain-of-Thought Training Data.

Assumes Phase 2 has produced an aligned system prompt (or the user accepts
the current prompt's alignment level).  Replays the BFS-optimal route and
builds STRUCTURED CoT reasoning at each decision point using BFS outcome data.

TWO MODES:
  --cot-mode teacher   (legacy) Use 397B teacher's <think> reasoning — prone to
                        vague/generic output that doesn't teach real strategy.
  --cot-mode bfs       (NEW, default) Build structured decision-tree CoT from
                        BFS outcome projections. Each candidate action is analysed
                        with its projected HP and goal-reachability. No LLM call
                        needed — pure BFS data → training signal.

Output format: <think>\\n...structured reasoning...\\n</think>\\nACTION: N

Usage:
    cd mota-gepa
    # BFS-structured CoT (no API calls, fast):
    python -m training.collect_aligned_cot --floor simple --cot-mode bfs

    # Teacher CoT (uses 397B API, slower):
    python -m training.collect_aligned_cot --floor simple --cot-mode teacher

    # Use specific prompt file (teacher mode):
    python -m training.collect_aligned_cot --prompt results/bfs_aligned_prompt.json --cot-mode teacher
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

log = logging.getLogger(__name__)


def collect_aligned_cot(
    floor_name: str = "simple",
    teacher_model: str | None = None,
    prompt: str | None = None,
    output_path: str = "training/data/bfs_aligned_cot.jsonl",
    require_match: bool = True,
    cot_mode: str = "bfs",
) -> list[dict]:
    """
    Collect CoT reasoning traces aligned to the BFS-optimal route.

    cot_mode="bfs" (default):
      Build structured decision-tree CoT from BFS outcome projections.
      For each candidate action, analyse projected HP and goal-reachability.
      No LLM API call needed — all reasoning is derived from BFS data.
      Every sample is automatically BFS-aligned (no filtering needed).

    cot_mode="teacher":
      Call the teacher LLM and capture its <think> reasoning.
      Requires API calls. Quality depends on teacher + prompt quality.

    Returns list of training samples: {input, output, metadata}
    """
    from mota.game.types import ActionType
    from training.align_prompt_to_bfs import (
        _load_floor_scenario, _bfs_optimal_action, _bfs_optimal_actions,
    )

    state, gd, scenario, bfs_hp = _load_floor_scenario(floor_name)

    if cot_mode == "bfs":
        return _collect_bfs_cot(
            state, gd, scenario, bfs_hp, floor_name, output_path,
        )
    else:
        return _collect_teacher_cot(
            state, gd, scenario, bfs_hp, floor_name,
            teacher_model, prompt, output_path, require_match,
        )


# ---------------------------------------------------------------------------
# BFS-Structured CoT Mode (no LLM calls)
# ---------------------------------------------------------------------------

def _collect_bfs_cot(
    state, gd, scenario, bfs_hp: int,
    floor_name: str, output_path: str,
) -> list[dict]:
    """Build structured decision-tree CoT from BFS outcome projections.

    For each multi-choice decision on the BFS path:
    1. Run mini-BFS after EACH candidate action
    2. Build structured reasoning comparing outcomes
    3. Select the BFS-optimal action with explicit justification

    This produces higher-quality CoT than teacher mode because every reasoning
    step is grounded in actual projected outcomes, not LLM guesswork.
    """
    from mota.game.types import ActionType
    from training.align_prompt_to_bfs import _bfs_optimal_actions

    # Suppress BFS solver INFO logging during mass mini-BFS runs
    logging.getLogger("mota.solver.bfs_solver").setLevel(logging.WARNING)

    samples = []
    decision_idx = 0

    print(f"Collecting BFS-structured CoT for {floor_name} (BFS optimal HP={bfs_hp})")
    print(f"Mode: bfs (no API calls)\n")

    while (not state.goal_reached and not state.failed
           and state.turn < state.max_turns):

        actions = state.get_actions()
        if not actions:
            break

        if len(actions) == 1:
            only = actions[0]
            if only.type == ActionType.FIGHT and not only.can_win:
                break
            state.apply_action(only)
            continue

        # Get BFS projections for ALL candidate actions
        optimal_set = _bfs_optimal_actions(
            state.floor, state.hero, state.removed, actions,
            gd, scenario.goal,
        )
        if not optimal_set:
            log.warning("No BFS solution from decision %d — stopping", decision_idx)
            break

        # Get FULL BFS results (not just optimal) for decision tree
        all_bfs_results = _get_all_bfs_results(
            state, actions, gd, scenario.goal,
        )

        bfs_action_id = max(optimal_set.keys())
        bfs_result_hp, bfs_goal = optimal_set[bfs_action_id]
        bfs_action = next(a for a in actions if a.action_id == bfs_action_id)

        # Build structured CoT from BFS outcomes
        cot_text = _build_bfs_cot(
            state, actions, all_bfs_results, optimal_set,
            bfs_action, bfs_action_id, gd,
        )

        # Format state for model input
        state_text = state.format_state()
        actions_text = state.format_actions(actions)
        user_msg = (
            f"{state_text}\n\n{actions_text}\n\n"
            "Choose the best action. Reply: ACTION: <number>"
        )

        output_text = f"<think>\n{cot_text}\n</think>\nACTION: {bfs_action_id}"

        sample = {
            "input": user_msg,
            "output": output_text,
            "metadata": {
                "floor_id": floor_name,
                "decision_idx": decision_idx,
                "cot_mode": "bfs",
                "bfs_action": bfs_action.label() if hasattr(bfs_action, "label") else str(bfs_action_id),
                "bfs_action_id": bfs_action_id,
                "bfs_result_hp": bfs_result_hp,
                "n_equiv_optimal": len(optimal_set),
                "hp_before": state.hero.hp,
                "hp_after": getattr(bfs_action, "hp_after", state.hero.hp),
                "num_actions": len(actions),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        samples.append(sample)

        bfs_label = bfs_action.label() if hasattr(bfs_action, 'label') else str(bfs_action_id)
        n_equiv = len(optimal_set)
        equiv_info = f" [{n_equiv} equiv]" if n_equiv > 1 else ""
        print(f"  Decision {decision_idx:2d}: {bfs_label}{equiv_info} (HP={state.hero.hp})")

        state.apply_action(bfs_action)
        decision_idx += 1

    # Save
    _save_samples(samples, output_path)
    print(f"\n{'=' * 60}")
    print(f"BFS-Structured CoT Complete -- {floor_name}")
    print(f"Samples: {len(samples)} (all BFS-aligned by construction)")
    print(f"Final HP: {state.hero.hp}")
    print(f"Goal reached: {state.goal_reached}")
    print(f"Saved to: {output_path}")
    print(f"{'=' * 60}")

    return samples


def _get_all_bfs_results(state, actions, gd, goal, max_states=50_000):
    """Run mini-BFS after each candidate action, return ALL results.

    Returns dict: {action_id: (hp, goal_reached)} for every action (not just optimal).
    """
    from mota.game.state import GameState
    from mota.solver.bfs_solver import BFSSolver

    # Suppress BFS log spam during mass mini-BFS
    bfs_logger = logging.getLogger("mota.solver.bfs_solver")
    prev_level = bfs_logger.level
    bfs_logger.setLevel(logging.WARNING)

    results = {}
    for action in actions:
        sim = GameState(
            floor=state.floor,
            hero=state.hero.copy(),
            goal=goal,
            game_data=gd,
            lookahead_depth=0,
            _removed=set(state.removed),
        )
        sim.apply_action(action)
        solver = BFSSolver(
            state.floor, sim.hero.copy(),
            game_data=gd,
            max_decisions=100,
            goal=goal,
            max_states=max_states,
            initial_removed=sim.removed,
        )
        result = solver.solve()
        if result is not None:
            goal_reached = getattr(result, "goal_reached", False)
            results[action.action_id] = (result.hero.hp, goal_reached)
        else:
            results[action.action_id] = (None, False)

    bfs_logger.setLevel(prev_level)
    return results


def _build_bfs_cot(state, actions, all_bfs_results, optimal_set,
                    bfs_action, bfs_action_id, gd) -> str:
    """Build structured decision-tree CoT from BFS projections and unlock trees.

    The reasoning uses the same tree structure visible in the model input
    (from format_actions) and explains WHY some actions reach the boss while
    others are dead ends, referencing what each action unlocks.
    """
    from mota.game.types import ActionType

    lines = []

    # 1. State summary
    lines.append(
        f"State: HP={state.hero.hp} ATK={state.hero.atk} DEF={state.hero.def_}"
        f" | {state.remaining_enemies()} enemies remaining"
    )
    lines.append("")

    # 2. Categorise actions
    free_items = [a for a in actions if a.type == ActionType.COLLECT]
    fights = [a for a in actions if a.type == ActionType.FIGHT]
    doors = [a for a in actions if a.type == ActionType.OPEN_DOOR]
    other = [a for a in actions if a.type not in
             (ActionType.COLLECT, ActionType.FIGHT, ActionType.OPEN_DOOR)]

    # 3. Free items — always best to collect first
    if free_items:
        names = ", ".join(f"{a.name}" for a in free_items)
        lines.append(f"Free items available: {names}")
        lines.append("Rule: always collect free items first — DEF compounds, ATK reduces fight turns.")
        lines.append("")

    # 4. Analyse each action with BFS projection + unlock tree
    lines.append(f"Evaluating {len(actions)} choices (BFS projection after each):")
    for a in actions:
        bfs_hp, bfs_goal = all_bfs_results.get(a.action_id, (None, False))
        is_opt = a.action_id in optimal_set

        # Build action descriptor
        if a.type == ActionType.FIGHT:
            desc = f"Fight {a.name} at ({a.x},{a.y}), damage={a.total_damage} ({a.damage_percent}% HP)"
        elif a.type == ActionType.COLLECT:
            desc = f"Collect {a.name} (free)"
        elif a.type == ActionType.OPEN_DOOR:
            desc = f"Open {a.name} at ({a.x},{a.y})"
        else:
            desc = f"{a.type.value} {a.name}"

        # BFS outcome
        if bfs_hp is None or (hasattr(a, 'can_win') and not a.can_win):
            outcome = "DEAD END — no path to boss"
        elif bfs_goal:
            tag = " ** BEST **" if is_opt else ""
            outcome = f"final HP={bfs_hp}, boss reachable{tag}"
        else:
            outcome = f"final HP={bfs_hp}, boss UNREACHABLE"

        lines.append(f"  {a.action_id}. {desc} -> {outcome}")

        # Unlock tree analysis (what this action opens up)
        tree = getattr(a, 'unlocks_tree', None)
        if tree:
            reward_items = [u for u in tree if u["type"] != "enemy"]
            gateway_enemies = [u for u in tree if u["type"] == "enemy"]
            direct = [u for u in reward_items if not u.get("via")]
            chained = [u for u in reward_items if u.get("via")]

            if gateway_enemies:
                enemy_names = ", ".join(u["label"].split("@")[0].strip() for u in gateway_enemies[:3])
                lines.append(f"     Enemies behind: {enemy_names}")
            if direct:
                item_names = ", ".join(u["label"] for u in direct[:4])
                lines.append(f"     Directly unlocks: {item_names}")
            if chained:
                # Group by via chain for readability
                for u in chained[:3]:
                    via_str = " -> ".join(v.split("[")[0].strip() for v in u["via"])
                    lines.append(f"     Via [{via_str}]: {u['label']}")

        # Dead-end door warning
        if a.type == ActionType.OPEN_DOOR and getattr(a, 'is_dead_end', False):
            lines.append("     WARNING: dead-end door, wastes a key")

    lines.append("")

    # 5. Decision justification
    bfs_hp_best, _ = all_bfs_results.get(bfs_action_id, (None, False))
    n_opt = len(optimal_set)

    if bfs_action.type == ActionType.COLLECT:
        lines.append(
            f"Best: Action {bfs_action_id} — collect {bfs_action.name} (free)."
        )
        lines.append(
            "Free stat pickups before fights reduce total damage taken."
        )
    elif bfs_action.type == ActionType.FIGHT:
        lines.append(
            f"Best: Action {bfs_action_id} — fight {bfs_action.name} "
            f"(cost={bfs_action.total_damage} HP, final HP={bfs_hp_best})."
        )
        # Explain what this fight enables
        tree = getattr(bfs_action, 'unlocks_tree', None)
        if tree:
            rewards = [u["label"] for u in tree if u["type"] != "enemy"][:4]
            if rewards:
                lines.append(f"This fight unlocks: {', '.join(rewards)}.")
        # Note dead-end alternatives
        dead_alts = [
            a for a in actions
            if a.action_id != bfs_action_id
            and not all_bfs_results.get(a.action_id, (None, False))[1]
        ]
        if dead_alts:
            dead_names = ", ".join(
                f"Action {a.action_id} ({a.name})" for a in dead_alts[:3]
            )
            lines.append(f"Avoid: {dead_names} — boss unreachable after those.")
    elif bfs_action.type == ActionType.OPEN_DOOR:
        lines.append(
            f"Best: Action {bfs_action_id} — open {bfs_action.name} "
            f"(final HP={bfs_hp_best})."
        )
        tree = getattr(bfs_action, 'unlocks_tree', None)
        if tree:
            rewards = [u["label"] for u in tree if u["type"] != "enemy"][:4]
            if rewards:
                lines.append(f"Opens path to: {', '.join(rewards)}.")
    else:
        lines.append(f"Best: Action {bfs_action_id} — {bfs_action.name}.")

    if n_opt > 1:
        alt_ids = [aid for aid in optimal_set if aid != bfs_action_id]
        lines.append(
            f"Note: {n_opt} equally optimal choices "
            f"(Actions {', '.join(str(i) for i in alt_ids)} also yield HP={bfs_hp_best})."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Teacher CoT Mode (LLM calls)
# ---------------------------------------------------------------------------

def _collect_teacher_cot(
    state, gd, scenario, bfs_hp: int,
    floor_name: str, teacher_model: str | None,
    prompt: str | None, output_path: str,
    require_match: bool,
) -> list[dict]:
    """Original teacher-based CoT collection (calls 397B teacher LLM)."""
    from mota.optimizer.evaluator import _call_llm, _parse_action_id
    from mota.game.types import ActionType
    from training.align_prompt_to_bfs import _bfs_optimal_actions

    # Use provided prompt or load best available
    if prompt is None:
        prompt = _load_best_prompt()
    if prompt is None:
        from mota.optimizer.seed_prompt import SEED_PROMPT
        prompt = SEED_PROMPT
        log.warning("No aligned prompt found, using seed prompt")

    # Build system prompt with floor map
    floor_map_text = state.format_floor_map()
    runtime_prompt = prompt + "\n\n" + floor_map_text

    model = teacher_model or os.environ.get("MOTA_TASK_MODEL", "qwen3.5-397b-a17b")
    mode = "thinking"  # Always use thinking mode for CoT

    samples = []
    decision_idx = 0
    matches = 0
    equiv_matches = 0
    total = 0

    print(f"Collecting CoT for {floor_name} (BFS optimal HP={bfs_hp})")
    print(f"Teacher: {model}")
    print(f"Require BFS match: {require_match}")
    print()

    while (not state.goal_reached and not state.failed
           and state.turn < state.max_turns):

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

        # Multi-choice decision point: find ALL equally-optimal BFS actions
        optimal_set = _bfs_optimal_actions(
            state.floor, state.hero, state.removed, actions,
            gd, scenario.goal,
        )
        if not optimal_set:
            log.warning("No BFS solution from decision %d — stopping", decision_idx)
            break

        # Pick one canonical BFS action (highest action_id for determinism)
        bfs_action_id = max(optimal_set.keys())
        bfs_result_hp, bfs_goal = optimal_set[bfs_action_id]
        bfs_action = next(a for a in actions if a.action_id == bfs_action_id)

        # Format state for LLM
        state_text = state.format_state()
        actions_text = state.format_actions(actions)
        user_msg = (
            f"{state_text}\n\n{actions_text}\n\n"
            "Choose the best action. Reply: ACTION: <number>"
        )

        valid_ids = {a.action_id for a in actions}

        # Call teacher (stateless — no conversation history)
        response = _call_llm(
            runtime_prompt, user_msg,
            task_model=model,
            task_mode=mode,
            prior_messages=None,
        )

        llm_action_id = _parse_action_id(response, valid_ids=valid_ids)
        is_exact_match = llm_action_id == bfs_action_id
        is_equiv_match = llm_action_id in optimal_set
        is_match = is_exact_match or is_equiv_match
        total += 1
        if is_exact_match:
            matches += 1
        if is_equiv_match and not is_exact_match:
            equiv_matches += 1
            matches += 1  # count equiv as match

        llm_action = next((a for a in actions if a.action_id == llm_action_id), None) if llm_action_id else None
        equiv_tag = "~" if is_equiv_match and not is_exact_match else ""
        status = f"Y{equiv_tag}" if is_match else "N"
        n_equiv = len(optimal_set)
        bfs_label = bfs_action.label() if hasattr(bfs_action, 'label') else str(bfs_action_id)
        llm_label = llm_action.label() if llm_action and hasattr(llm_action, 'label') else f'id={llm_action_id}'
        equiv_info = f" [{n_equiv} equiv]" if n_equiv > 1 else ""
        print(f"  {status:3s} Decision {decision_idx:2d}: BFS={bfs_label:<35s} LLM={llm_label}{equiv_info}")

        # Extract reasoning and build training sample
        thinking = _extract_thinking(response)

        if is_match or not require_match:
            # Build the training output
            # When teacher matched (exact or equiv): use teacher's reasoning + teacher's action
            # When teacher didn't match (and require_match=False):
            #   override the action to BFS, keep reasoning as context
            if is_match:
                # Teacher chose an equally-optimal action — use their reasoning + their action
                teacher_action = llm_action if llm_action else bfs_action
                output_text = _build_training_output(
                    thinking, teacher_action, actions, override_action=False
                )
            else:
                # Teacher reasoning was for wrong action — override answer
                output_text = _build_training_output(
                    thinking, bfs_action, actions, override_action=True
                )

            sample = {
                "input": user_msg,
                "output": output_text,
                "metadata": {
                    "floor_id": floor_name,
                    "decision_idx": decision_idx,
                    "teacher_model": model,
                    "bfs_action": bfs_action.label() if hasattr(bfs_action, "label") else str(bfs_action_id),
                    "bfs_action_id": bfs_action_id,
                    "bfs_result_hp": bfs_result_hp,
                    "teacher_matched_bfs": is_exact_match,
                    "teacher_equiv_optimal": is_equiv_match and not is_exact_match,
                    "n_equiv_optimal": len(optimal_set),
                    "hp_before": state.hero.hp,
                    "hp_after": getattr(bfs_action, "hp_after", state.hero.hp),
                    "num_actions": len(actions),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
            samples.append(sample)

        # Always execute BFS action (stay on optimal path)
        state.apply_action(bfs_action)
        decision_idx += 1

    # Save
    _save_samples(samples, output_path)

    accuracy = matches / max(1, total)
    print(f"\n{'=' * 60}")
    print(f"CoT Collection Complete -- {floor_name}")
    print(f"BFS alignment: {matches}/{total} = {accuracy:.1%}")
    if equiv_matches:
        print(f"  (exact: {matches - equiv_matches}, equiv-optimal: {equiv_matches})")
    print(f"Training samples: {len(samples)} (require_match={require_match})")
    print(f"Final HP: {state.hero.hp}")
    print(f"Goal reached: {state.goal_reached}")
    print(f"Saved to: {output_path}")
    print(f"{'=' * 60}")

    return samples


def _extract_thinking(response: str) -> str:
    """Extract chain-of-thought from <think>...</think> tags."""
    m = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
    return m.group(1).strip() if m else ""


def _build_training_output(
    thinking: str,
    bfs_action,
    actions: list,
    override_action: bool = False,
) -> str:
    """Build the training output: <think>reasoning</think> + ACTION: N.

    When override_action=True, the teacher chose wrong but we output the BFS
    action anyway.  The thinking may not perfectly justify the BFS action in
    this case — in Phase 2 alignment, we improve the prompt until the teacher
    naturally reasons its way to the BFS action (no overrides needed).
    """
    parts = []

    if thinking:
        # Clean up overly long thinking
        if len(thinking) > 2000:
            lines = thinking.split("\n")
            if len(lines) > 20:
                thinking = "\n".join(lines[:12]) + "\n...\n" + "\n".join(lines[-6:])
        parts.append(f"<think>\n{thinking}\n</think>")

    # Build clean action line
    action_label = (bfs_action.label()
                    if hasattr(bfs_action, "label")
                    else f"Action {bfs_action.action_id}")

    if override_action:
        parts.append(f"The best action is {action_label}. ACTION: {bfs_action.action_id}")
    else:
        parts.append(f"ACTION: {bfs_action.action_id}")

    return "\n".join(parts)


def _save_samples(samples: list[dict], output_path: str) -> None:
    """Save training samples to JSONL file."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _load_best_prompt() -> str | None:
    """Load the best available aligned prompt."""
    # BFS-aligned prompt (from Phase 2)
    aligned = _root / "results" / "bfs_aligned_prompt.json"
    if aligned.exists():
        with open(aligned, encoding="utf-8") as f:
            data = json.load(f)
            print(f"Using BFS-aligned prompt (score={data.get('best_score', '?')})")
            return data["best_prompt"]

    # GEPA v3 prompt
    gepa = _root / "results" / "gepa_result.json"
    if gepa.exists():
        with open(gepa, encoding="utf-8") as f:
            print("Using GEPA v3 prompt (alignment unknown)")
            return json.load(f)["best_prompt"]

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Phase 3: Collect BFS-aligned CoT training data"
    )
    parser.add_argument("--floor", default="simple",
                        help="Floor to collect CoT for")
    parser.add_argument("--model", default=None,
                        help="Teacher model (default: env or qwen3.5-397b-a17b)")
    parser.add_argument("--prompt", default=None,
                        help="Path to prompt JSON or text file")
    parser.add_argument("--output", "-o", default="training/data/bfs_aligned_cot.jsonl",
                        help="Output JSONL path")
    parser.add_argument("--cot-mode", default="bfs", choices=["bfs", "teacher"],
                        help="CoT mode: bfs (structured, no API), teacher (397B LLM)")
    parser.add_argument("--include-mismatches", action="store_true",
                        help="Include samples where teacher didn't match BFS (teacher mode)")
    parser.add_argument("--verbose", "-v", action="store_true")
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

    # Load prompt
    prompt_text = None
    if args.prompt:
        p = Path(args.prompt)
        if p.suffix == ".json":
            with open(p, encoding="utf-8") as f:
                prompt_text = json.load(f)["best_prompt"]
        else:
            prompt_text = p.read_text(encoding="utf-8")

    collect_aligned_cot(
        floor_name=args.floor,
        teacher_model=args.model,
        prompt=prompt_text,
        output_path=args.output,
        require_match=not args.include_mismatches,
        cot_mode=args.cot_mode,
    )


if __name__ == "__main__":
    main()
