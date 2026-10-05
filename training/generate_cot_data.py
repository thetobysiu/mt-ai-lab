"""
CoT Distillation Data Generator for Architecture C.

Pipeline:
  1. Run Qwen3.5-397B (teacher) through each floor in reactive mode
  2. Capture full <think>...</think> chain-of-thought + ACTION at each step
  3. Verify each action against the BFS solver's optimal route
  4. Output JSONL training data: {input: state+actions, output: CoT+action}

The idea: the teacher model's reasoning traces contain strategic insights
(key economy, DEF threshold awareness, lookahead interpretation) that a
small student model (LFM2.5-1.2B) can learn to replicate via QLoRA fine-tuning.

Usage:
    python -m training.generate_cot_data --output training/cot_data.jsonl
    python -m training.generate_cot_data --floors MT3 MT5 --model qwen3.5-397b-a17b
    python -m training.generate_cot_data --include-solver-comparison
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root on path
_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FLOORS_DIR = Path(__file__).resolve().parents[1] / "data" / "games" / "24" / "project" / "floors"
_AI_TEST_DIR = Path(__file__).resolve().parents[1] / "data" / "floors"


def _load_env():
    try:
        from dotenv import load_dotenv
        for env_dir in [_root]:
            env_file = env_dir / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                break
    except ImportError:
        pass


def generate_cot_data(
    floors: list[str],
    teacher_model: str = "qwen3.5-397b-a17b",
    prompt_path: str | None = None,
    include_solver: bool = False,
    output_path: str = "training/cot_data.jsonl",
    max_turns_per_floor: int = 100,
) -> list[dict]:
    """
    Generate CoT training data by running a teacher model through game floors.

    For each decision point:
    - Captures the teacher's full reasoning chain
    - Records the chosen action with justification
    - Optionally compares against BFS solver optimal action
    - Labels quality: "correct" if matches solver, "plausible" if reasonable, "wrong" if bad

    Returns list of training samples.
    """
    from mota.optimizer.evaluator import (
        _create_state, _call_llm, _parse_action_id, _heuristic_pick,
        configure_scenario, configure_mt3_scenario,
    )
    from mota.optimizer.seed_prompt import SEED_PROMPT
    from mota.game.state import GameState

    # Load prompt
    if prompt_path:
        prompt = Path(prompt_path).read_text(encoding="utf-8")
    else:
        # Try GEPA v3 first, fall back to seed
        gepa_path = _root / "results" / "gepa_result.json"
        if gepa_path.exists():
            with open(gepa_path, encoding="utf-8") as f:
                prompt = json.load(f)["best_prompt"]
            print(f"Using GEPA v3 prompt from {gepa_path}")
        else:
            prompt = SEED_PROMPT
            print("Using seed prompt (GEPA result not found)")

    all_samples = []

    for floor_id in floors:
        print(f"\n{'='*60}")
        print(f"  Generating CoT data for {floor_id}")
        print(f"{'='*60}")

        # Configure the scenario
        if floor_id == "MT3":
            configure_mt3_scenario()
        else:
            floor_file = _FLOORS_DIR / f"{floor_id}.js"
            if floor_file.exists():
                configure_scenario(str(floor_file))
            else:
                ai_file = _AI_TEST_DIR / f"{floor_id}.txt"
                if ai_file.exists():
                    configure_scenario(str(ai_file))
                else:
                    print(f"  SKIP: Floor file not found for {floor_id}")
                    continue

        # Get solver route if requested
        solver_route = None
        if include_solver:
            solver_route = _get_solver_route(floor_id)
            if solver_route:
                print(f"  BFS solver route: {len(solver_route)} decisions")

        # Run the teacher through the floor
        state = _create_state(lookahead_depth=None)
        floor_map_text = state.format_floor_map()
        runtime_prompt = prompt + "\n\n" + floor_map_text

        conversation_history: list[dict] = []
        decision_idx = 0
        consecutive_errors = 0

        while (not state.goal_reached and not state.failed
               and state.turn < state.max_turns
               and decision_idx < max_turns_per_floor):

            actions = state.get_actions()
            if not actions:
                break

            # Auto-execute forced single actions
            if len(actions) == 1:
                from mota.game.types import ActionType as AT
                only = actions[0]
                if only.type == AT.FIGHT and not only.can_win:
                    break
                state.apply_action(only)
                continue

            # Build LLM input
            state_text = state.format_state()
            actions_text = state.format_actions(actions)
            user_msg = (
                f"{state_text}\n\n{actions_text}\n\n"
                "Choose the best action. Reply: ACTION: <number>"
            )
            valid_ids = {a.action_id for a in actions}

            # Call teacher model
            response = _call_llm(
                runtime_prompt, user_msg,
                task_model=teacher_model,
                task_mode="thinking",
                prior_messages=conversation_history[-12:] if conversation_history else None,
            )

            action_id = _parse_action_id(response, valid_ids=valid_ids)
            if action_id is None or action_id not in valid_ids:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    action_id = _heuristic_pick(actions, state)
                    consecutive_errors = 0
                    if action_id is None:
                        break
                else:
                    continue

            chosen = next(a for a in actions if a.action_id == action_id)

            # Extract thinking and build training sample
            thinking = _extract_thinking(response)
            answer_text = _build_answer_text(response, thinking, chosen, actions)

            # Compare with solver if available
            quality = "unknown"
            solver_action_label = None
            if solver_route and decision_idx < len(solver_route):
                solver_step = solver_route[decision_idx]
                if (chosen.x, chosen.y) == (solver_step["x"], solver_step["y"]):
                    quality = "correct"
                else:
                    # Check if it's at least a reasonable choice
                    if chosen.total_damage == 0 or (hasattr(chosen, "item_tier") and chosen.item_tier):
                        quality = "plausible"
                    else:
                        quality = "divergent"
                solver_action_label = solver_step.get("label", "")

            sample = {
                "input": f"{state_text}\n\n{actions_text}\n\nChoose the best action. Reply: ACTION: <number>",
                "output": answer_text,
                "metadata": {
                    "floor_id": floor_id,
                    "decision_idx": decision_idx,
                    "teacher_model": teacher_model,
                    "chosen_action": chosen.label() if hasattr(chosen, "label") else str(chosen),
                    "chosen_coords": f"({chosen.x},{chosen.y})",
                    "hp_before": state.hero.hp,
                    "hp_after": getattr(chosen, "hp_after", state.hero.hp),
                    "quality": quality,
                    "solver_action": solver_action_label,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
            all_samples.append(sample)

            # Apply action and advance
            trace = state.apply_action(chosen)
            decision_idx += 1
            consecutive_errors = 0

            # Update conversation history
            conversation_history.append({"role": "user", "content": user_msg})
            conversation_history.append({"role": "assistant", "content": response})

            print(f"  T{trace.turn}: {chosen.label() if hasattr(chosen, 'label') else str(chosen)} "
                  f"→ HP={trace.hero_after['hp']} [{quality}]")

        print(f"  Generated {decision_idx} CoT samples for {floor_id}")
        if state.goal_reached:
            print(f"  Floor completed! Final HP={state.hero.hp}")
        elif state.failed:
            print(f"  Floor FAILED: {state.failure_reason}")

    # Save to JSONL
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        for sample in all_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"  Generated {len(all_samples)} total CoT training samples")
    print(f"  Saved to: {output}")
    if include_solver:
        correct = sum(1 for s in all_samples if s["metadata"]["quality"] == "correct")
        divergent = sum(1 for s in all_samples if s["metadata"]["quality"] == "divergent")
        print(f"  Quality: {correct}/{len(all_samples)} match solver, {divergent} divergent")
    print(f"{'='*60}")

    return all_samples


def _extract_thinking(response: str) -> str:
    """Extract the chain-of-thought from <think>...</think> tags."""
    m = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
    return m.group(1).strip() if m else ""


def _build_answer_text(response: str, thinking: str, chosen, actions: list) -> str:
    """Build the training output: CoT reasoning + ACTION: N.

    For the student model, we want it to learn the teacher's reasoning
    style but produce a clean ACTION: N at the end.
    """
    # Clean up the thinking to remove excessive repetition
    if thinking:
        # Truncate very long thinking (>1500 chars) but keep key reasoning
        if len(thinking) > 1500:
            lines = thinking.split("\n")
            # Keep first 10 lines and last 5 lines
            if len(lines) > 15:
                thinking = "\n".join(lines[:10]) + "\n...\n" + "\n".join(lines[-5:])

    # Build clean output
    parts = []
    if thinking:
        parts.append(f"<think>\n{thinking}\n</think>")

    # Extract the non-thinking answer
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    if cleaned:
        parts.append(cleaned)
    else:
        # Generate a clean answer
        action_label = chosen.label() if hasattr(chosen, "label") else f"Action {chosen.action_id}"
        parts.append(f"{action_label} is the best choice. ACTION: {chosen.action_id}")

    return "\n".join(parts)


def _get_solver_route(floor_id: str) -> list[dict] | None:
    """Get the BFS solver's optimal route for comparison."""
    try:
        from mota.optimizer.evaluator import _create_state
        from mota.solver.bfs_solver import BFSSolver

        state = _create_state(lookahead_depth=0)
        solver = BFSSolver(
            state.floor, state.hero,
            game_data=state.gd,
            max_decisions=100,
            goal=getattr(state, "goal_type", "clear_all_enemies"),
        )
        result = solver.solve()
        if result is None:
            return None

        route = []
        for action in result.route:
            route.append({
                "x": action.x,
                "y": action.y,
                "type": action.type.value if hasattr(action.type, "value") else str(action.type),
                "label": action.label() if hasattr(action, "label") else str(action),
            })
        return route
    except Exception as e:
        print(f"  Warning: BFS solver failed for {floor_id}: {e}")
        return None


def main():
    _load_env()

    parser = argparse.ArgumentParser(description="Generate CoT training data from teacher model")
    parser.add_argument("--output", "-o", default="training/cot_data.jsonl",
                       help="Output JSONL file path")
    parser.add_argument("--floors", nargs="+", default=["MT3"],
                       help="Floor IDs to generate data for (e.g., MT3 MT5)")
    parser.add_argument("--model", default="qwen3.5-397b-a17b",
                       help="Teacher model to use")
    parser.add_argument("--prompt", default=None,
                       help="Path to custom prompt file (default: GEPA v3 or seed)")
    parser.add_argument("--include-solver-comparison", action="store_true",
                       help="Compare each action against BFS solver optimal")
    parser.add_argument("--max-turns", type=int, default=100,
                       help="Max decision points per floor")
    args = parser.parse_args()

    generate_cot_data(
        floors=args.floors,
        teacher_model=args.model,
        prompt_path=args.prompt,
        include_solver=args.include_solver_comparison,
        output_path=args.output,
        max_turns_per_floor=args.max_turns,
    )


if __name__ == "__main__":
    main()
