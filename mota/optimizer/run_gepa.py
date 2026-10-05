"""
GEPA prompt optimization entry point for MOTA MT3.

Usage:
    python -m mota.optimizer.run_gepa          # Full GEPA optimization
    python -m mota.optimizer.run_gepa --test   # Single eval with seed prompt (no GEPA)
    python -m mota.optimizer.run_gepa --heuristic  # Heuristic-only baseline
    python -m mota.optimizer.run_gepa --test --floor 单层-最简单.txt --task-preset qwen-thinking
"""
from __future__ import annotations
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from .model_config import TASK_MODEL_PRESETS, resolve_task_config

for _s in (sys.stdout, sys.stderr):  # Windows consoles crash on Chinese entity names / arrows otherwise
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def _unwrap_candidate_text(candidate: dict[str, str], str_candidate_key: str | None) -> str | dict[str, str]:
    """Return plain prompt text for string candidates, else the full mapping."""
    if str_candidate_key and str_candidate_key in candidate:
        return candidate[str_candidate_key]
    return candidate


def _build_candidate_history(result) -> list[dict]:
    """Build a JSON-friendly history of every GEPA candidate.

    The GEPAResult object already contains all candidates and lineage. This helper
    exposes that data in a compact structure tailored for thesis workflows.
    """
    history: list[dict] = []
    str_candidate_key = getattr(result, "_str_candidate_key", None)
    best_idx = result.best_idx

    for idx, candidate in enumerate(result.candidates):
        prompt_text = _unwrap_candidate_text(candidate, str_candidate_key)
        history.append(
            {
                "idx": idx,
                "is_best": idx == best_idx,
                "score": result.val_aggregate_scores[idx] if idx < len(result.val_aggregate_scores) else None,
                "val_subscores": result.val_subscores[idx] if idx < len(result.val_subscores) else None,
                "discovery_eval_count": (
                    result.discovery_eval_counts[idx]
                    if idx < len(result.discovery_eval_counts)
                    else None
                ),
                "parents": result.parents[idx] if idx < len(result.parents) else [],
                "prompt": prompt_text,
                "candidate": candidate,
            }
        )
    return history


def _load_env():
    """Load .env from the repository root."""
    for env_dir in [Path(__file__).resolve().parents[2]]:
        env_file = env_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            return
    # Fallback: try current directory
    load_dotenv()


def run_heuristic():
    """Run the pure heuristic baseline (no LLM)."""
    from .evaluator import evaluate_heuristic_only

    print("=" * 60)
    print("HEURISTIC BASELINE (no LLM)")
    print("=" * 60)

    result = evaluate_heuristic_only()
    print(f"\nScore: {result['total']:.3f}")
    print(f"Completion: {result['completion']:.1%}")
    print(f"Final: HP={result['hero']['hp']} ATK={result['hero']['atk']} DEF={result['hero']['def']}")

    print("\nStep trace:")
    for step in result["history"]:
        print(f"  Turn {step['turn']:2d}: {step['action']} → HP={step['hp']}")

    print(f"\nViolations: {result['violations']}")
    return result


def run_single_eval(
    task_model: str | None = None,
    task_mode: str | None = None,
    seed_prompt: str | None = None,
):
    """Run a single evaluation with the seed prompt (LLM, no GEPA)."""
    from .seed_prompt import SEED_PROMPT
    from .evaluator import evaluate

    prompt = seed_prompt if seed_prompt else SEED_PROMPT
    print("=" * 60)
    print(f"SINGLE EVALUATION ({'custom' if seed_prompt else 'default seed'} prompt, {len(prompt)} chars)")
    print("=" * 60)

    score = evaluate(prompt, task_model=task_model, task_mode=task_mode)
    print(f"\nFinal score: {score:.3f}")
    return score


def run_oneshot_eval(task_model: str | None = None, task_mode: str | None = None):
    """Run one-shot holistic planning eval (single LLM call for full floor plan)."""
    from .seed_prompt import SEED_PROMPT
    from .evaluator import evaluate_oneshot

    print("=" * 60)
    print("ONE-SHOT EVALUATION (holistic planning, single LLM call)")
    print("=" * 60)

    score = evaluate_oneshot(SEED_PROMPT, task_model=task_model, task_mode=task_mode)
    print(f"\nFinal score: {score:.3f}")
    return score


def run_multistep_eval(task_model: str | None = None, task_mode: str | None = None, chunk_size: int = 5):
    """Run multi-step (chunked) planning eval."""
    from .seed_prompt import SEED_PROMPT
    from .evaluator import evaluate_multistep

    print("=" * 60)
    print(f"MULTI-STEP EVALUATION (chunk_size={chunk_size})")
    print("=" * 60)

    score = evaluate_multistep(SEED_PROMPT, task_model=task_model, task_mode=task_mode, chunk_size=chunk_size)
    print(f"\nFinal score: {score:.3f}")
    return score


class _EarlyStopReached(Exception):
    """Raised inside the evaluator when the early-stop threshold is met."""
    def __init__(self, score: float, call_count: int):
        self.score = score
        self.call_count = call_count
        super().__init__(f"Early stop: score {score:.4f} after {call_count} evaluations")


# ---------------------------------------------------------------------------
# Custom GEPA reflection template (MOTA domain-specific)
# ---------------------------------------------------------------------------
# Replaces GEPA's generic default with a template that tells the 397B reflection
# model exactly what the scoring function measures, what expert play looks like,
# and what common failure patterns to diagnose from the game trace.
#
# Placeholder markers used by the GEPA library:
#   <curr_param>  — the current candidate system prompt being mutated
#   <side_info>   — the accumulated game-trace log from oa.log() calls
# ---------------------------------------------------------------------------

def _build_reflection_prompt(scenario_name: str, bfs_ref: dict | None, has_shop: bool | None = None) -> str:
    """Build a floor-specific GEPA reflection prompt from BFS reference data.

    `has_shop` should be passed explicitly from the active scenario
    (`_scenario.shop is not None`). Only tower floors (MT*) have shops; the AI
    test floors (simple / 单层-最简单, complex / 单层-复杂) have shop=None. When
    `has_shop` is None we fall back to a name heuristic for backward compat,
    but callers should always pass the real flag.
    """
    if bfs_ref:
        target_hp = bfs_ref["target_hp"]
        ref_steps = bfs_ref["ref_steps"]
        enemies_total = bfs_ref["enemies_total"]
        enemies_killed = bfs_ref["enemies_killed"]
        target_atk = bfs_ref.get("target_atk", "?")
        target_def = bfs_ref.get("target_def", "?")
    else:
        # Fallback for unknown floors
        target_hp, ref_steps, enemies_total, enemies_killed = 448, 33, 17, 17
        target_atk, target_def = 23, 17

    # Determine if floor has a shop. Only tower floors (MT*) have shops; the AI
    # test floors (单层-最简单 / simple, 单层-复杂 / complex) have shop=None. The
    # name 复杂 ("complex") does NOT imply a shop — that earlier heuristic was a
    # bug that made GEPA hallucinate shop mechanics on the no-shop complex floor.
    if has_shop is None:
        has_shop = scenario_name.startswith("MT")

    # Build scoring section
    if has_shop:
        scoring = f"""\
SCORING FUNCTION the agent is evaluated on (composite S ∈ [0, 1]):
  S = 0.35 × completion + 0.25 × HP_score + 0.15 × efficiency + 0.15 × shop_score + 0.10 × violation_score
  • completion   — fraction of floor enemies killed ({enemies_total} enemies; killing all = 1.0)
  • HP_score     — 1.0 if final_HP ≥ {target_hp} (expert target); 0.0 if agent died; proportional in between
  • efficiency   — step count vs reference {ref_steps} steps (fewer steps = higher score)
  • shop_score   — 1.0 if DEF purchased at shop; 0.3 if shop skipped entirely; 0.0 if only HP bought
  • violation    — 1.0 for zero strategic violations"""
    else:
        scoring = f"""\
SCORING FUNCTION the agent is evaluated on (composite S ∈ [0, 1]):
  S = 0.35 × completion + 0.25 × HP_score + 0.15 × efficiency + 0.15 × stat_score + 0.10 × violation_score
  • completion   — fraction of floor enemies killed ({enemies_killed}/{enemies_total} required for max)
  • HP_score     — 1.0 if final_HP ≥ {target_hp} (BFS-optimal); 0.0 if agent died; proportional in between
  • efficiency   — step count vs reference {ref_steps} steps (fewer steps = higher score)
  • stat_score   — ATK/DEF optimality vs target ATK={target_atk}, DEF={target_def}
  • violation    — 1.0 for zero strategic violations
  NOTE: This floor has NO SHOP. Do NOT mention shops in the prompt."""

    # Build expert reference
    if has_shop:
        expert_ref = f"""\
EXPERT REFERENCE (score = 1.0 on floor {scenario_name}):
  - All {enemies_killed} enemies defeated; final HP ≥ {target_hp}
  - ATK = {target_atk}, DEF = {target_def} — achieved by buying DEF upgrade at shop
  - ~{ref_steps} steps total; no strategic violations"""
    else:
        expert_ref = f"""\
EXPERT REFERENCE (score = 1.0 on floor '{scenario_name}'):
  - {enemies_killed}/{enemies_total} enemies defeated including BOSS; final HP = {target_hp} (BFS-optimal)
  - Final stats: ATK = {target_atk}, DEF = {target_def}
  - ~{ref_steps} steps total; no strategic violations
  - Key insight: fight ordering determines if boss is killable — collect DEF/ATK gems
    BEFORE expensive fights to reduce cumulative damage"""

    # Build failure patterns
    if has_shop:
        failures = """\
COMMON FAILURE PATTERNS — identify which ones appear in the trace, then add rules to prevent them:
  1. DIED: fought expensive enemy before buying DEF at shop → HP = 0
  2. SHOP SKIPPED: agent used stairs before visiting shop (permanent stat loss)
  3. WRONG SHOP BUY: bought HP at shop instead of DEF
  4. ITEMS IGNORED: fought enemies while free DEF/ATK items were available to collect first
  5. KEY WASTE: spent key on dead-end door with no payoff
  6. HP RESERVE IGNORED: fought expensive enemy when HP < 20% of maximum"""
    else:
        failures = f"""\
COMMON FAILURE PATTERNS — identify which ones appear in the trace, then add rules to prevent them:
  1. BOSS NOT KILLED: agent killed all non-boss enemies but ran out of HP for boss fight.
     Root cause: fought enemies in wrong order, accumulating excess damage that left
     insufficient HP for the final boss. SOLUTION: collect gems/potions first, defer
     expensive fights until ATK/DEF are higher.
  2. WRONG FIGHT ORDER: fought high-cost enemies BEFORE collecting available DEF/ATK gems.
     Each +1 DEF reduces damage from EVERY future fight. Gems are free. Fight order matters enormously.
  3. DOOR SEQUENCING: opened doors in suboptimal order — failed to reach items that would
     reduce subsequent fight costs.
  4. UNNECESSARY FIGHTS: killed enemies that are NOT required to reach the boss.
     Only {enemies_killed}/{enemies_total} enemies need to die for optimal score.
  5. HP BUDGET VIOLATION: fought an enemy when remaining HP was insufficient for
     boss fight cost. Boss typically costs 500-600 HP at expected stats.
  NOTE: This floor has NO SHOP and NO STAIRS. Do NOT add rules about shops or stairs."""

    return f"""\
You are optimising the system prompt for an LLM agent that plays Magic Tower (MOTA), \
a deterministic turn-based dungeon RPG.

{scoring}

{expert_ref}

{failures}

The agent currently uses this system prompt:
```<curr_param>
```
Game execution traces (turn-by-turn actions, hero stats after each turn, score breakdown at the end):
```<side_info>
```

Write an improved system prompt:
- Keep every rule that worked correctly. Only modify or add rules for observed failures.
- Add specific, actionable rules that reference the exact failure seen in the trace.
- The agent receives ONLY this prompt plus a live numbered action list each turn.
- Response format must be preserved: agent responds with exactly "ACTION: <number>".
- Target length: ~1000–2000 characters (concise but complete).
- IMPORTANT: Only reference game mechanics that ACTUALLY EXIST on this floor.
  Do NOT invent shops, stairs, or enemies that are not in the trace.
- LANGUAGE STYLE: Use IMPERATIVE commands (NEVER, ALWAYS, MUST, DO NOT).
  Advisory language (prefer, consider, try, compare) is INEFFECTIVE for this model.
  Every rule must be a hard constraint, not a suggestion.

Provide the improved prompt inside ``` code fences.
"""


# Keep the old constant as fallback for imports
MOTA_REFLECTION_PROMPT = _build_reflection_prompt("MT3", {
    "target_hp": 448, "target_atk": 23, "target_def": 17,
    "ref_steps": 33, "enemies_total": 17, "enemies_killed": 17,
})

# ---------------------------------------------------------------------------
# Multi-floor variant of the reflection template
# ---------------------------------------------------------------------------
MOTA_MULTIFLOOR_REFLECTION_PROMPT = """\
You are optimising the system prompt for an LLM agent that plays Magic Tower (MOTA), \
a deterministic turn-based dungeon RPG across multiple sequential floors.

SCORING FUNCTION the agent is evaluated on (composite S \u2208 [0, 1]):
  S = 0.50 \u00d7 floor_progress + 0.30 \u00d7 goal_bonus + 0.20 \u00d7 hp_ratio
  \u2022 floor_progress \u2014 fraction of floors reached (e.g. 0.5 if reaching floor 2 of 2)
  \u2022 goal_bonus    \u2014 1.0 if the agent used the exit stairs on the final floor; else 0.0
  \u2022 hp_ratio      \u2014 final_HP / 1000 (proportional, capped at 0.20 contribution)

EXPERT REFERENCE (score = 1.0 across MT3 \u2192 MT4):
  - Both floors cleared; final stairs used; hero alive throughout
  - Each floor: all enemies killed before advancing; DEF upgrade purchased at shop
  - Key economy preserved (blue/red keys NOT regenerated between floors)

COMMON FAILURE PATTERNS \u2014 identify which ones appear in the trace, then add rules to prevent them:
  1. DIED ON FLOOR 1: fought \u9ab7\u9ac5\u4eba (315 HP damage at low DEF) before buying DEF at shop
  2. SHOP SKIPPED: used stairs before visiting shop \u2014 permanent stat loss for ALL future floors
  3. KEY SHORTAGE: wasted blue/red key on dead-end door; no key left for next floor
  4. STUCK ON FLOOR 1: agent keeps fighting but never uses stairs to advance to floor 2
  5. ARRIVED WEAK: advanced to next floor with HP < 20% \u2014 died immediately on first fight

The agent currently uses this system prompt:
```<curr_param>
```
Game execution traces (per-turn actions, floor transitions, floor reached, final score):
```<side_info>
```

Write an improved system prompt:
- Keep every rule that worked correctly. Only modify or add rules for observed failures.
- Add a rule for stair-advance timing: complete each floor (buy DEF, kill all enemies) BEFORE using stairs.
- Ensure HP-preservation rule covers arrival on the next floor (maintain \u226520% HP before using stairs).
- Response format must be preserved: agent responds with exactly \"ACTION: <number>\".
- Target length: ~1000\u20132000 characters (concise but complete).

Provide the improved prompt inside ``` code fences.
"""


def run_gepa(
    task_model: str | None = None,
    task_mode: str | None = None,
    reflection_model_override: str | None = None,
    seed_prompt_override: str | None = None,
    experiment_label: str | None = None,
    early_stop: float = 0.0,
    multi_floor: bool = False,
    start_floor: str = "MT3",
    end_floor: str = "MT4",
    eval_mode: str = "reactive",
    instances: list[int] | None = None,
):
    """Run full GEPA optimization.

    instances: walkthrough checkpoint ids (data.WALKTHROUGH_CHECKPOINTS) used as GEPA task
    instances ("curriculum"). Each evaluation re-configures the tower segment of that checkpoint
    (floor + exact hero stats) before running evaluate_multi_floor; with >1 instance GEPA runs in
    multi-task mode, so `pareto` and `current_best` selection genuinely differ.
    """
    try:
        from gepa.optimize_anything import (
            optimize_anything, GEPAConfig, EngineConfig, ReflectionConfig,
            make_litellm_lm,
        )
    except ImportError:
        print("ERROR: gepa not installed. Run: pip install gepa")
        sys.exit(1)

    from .seed_prompt import SEED_PROMPT
    from .evaluator import (
        evaluate,
        evaluate_multistep,
        evaluate_oneshot,
        evaluate_multi_floor,
        configure_multi_floor_scenario,
        make_rotating_litellm_lm,
    )

    # Use override or default seed prompt
    actual_seed = seed_prompt_override if seed_prompt_override else SEED_PROMPT

    # GEPA config
    max_calls = int(os.environ.get("GEPA_MAX_CALLS", "50"))
    reflection_model = reflection_model_override or os.environ.get("MOTA_REFLECTION_MODEL", "qwen3.5-397b-a17b")
    base_url = os.environ.get("SAIA_BASE_URL") or os.environ.get("OPENAI_API_BASE",
                              "https://chat-ai.academiccloud.de/v1")

    # Build floor-aware objective from BFS reference data (if available)
    curriculum = None
    if instances:
        from ..game.data import WALKTHROUGH_CHECKPOINTS
        curriculum = [WALKTHROUGH_CHECKPOINTS[i] for i in instances]
        multi_floor = True
        segs = ", ".join(f"{cp['id']}:{cp['floor']}→{cp['target']}" for cp in curriculum)
        objective = (
            "Maximize how far an LLM agent advances in the 24-floor Magic Tower (MOTA) from several "
            f"expert-walkthrough checkpoints ({segs}), each starting with that checkpoint's exact hero stats. "
            "Score per segment = 0.50×floor_progress + 0.30×goal_bonus + 0.20×hp_ratio; the candidate text is "
            "the agent's system prompt and must work for every segment."
        )
    elif multi_floor:
        objective = (
            f"Maximize the composite score of an LLM agent playing Magic Tower (MOTA) "
            f"across floors {start_floor}\u2192{end_floor} sequentially. "
            f"Score = 0.50\u00d7floor_progress + 0.30\u00d7goal_bonus + 0.20\u00d7hp_ratio. "
            f"Goal: reach and complete floor {end_floor} (use exit stairs) while staying alive."
        )
    else:
        from .evaluator import _scenario, _floor_data
        from ..benchmark.scorer import BFS_REFERENCE
        scenario_name = _scenario.name if _scenario else (_floor_data.floor_id if _floor_data else "MT3")
        bfs_ref = BFS_REFERENCE.get(scenario_name)
        if bfs_ref:
            objective = (
                f"Maximize the composite score of an LLM playing the Magic Tower (MOTA) "
                f"game on floor '{scenario_name}'. The score combines: enemy completion (35%), "
                f"final HP vs BFS-optimal target of {bfs_ref['target_hp']} (25%), step efficiency "
                f"vs reference {bfs_ref['ref_steps']} steps (15%), stat optimization (15%), "
                f"and strategic violation avoidance (10%). The candidate text is the LLM's "
                f"system prompt. A perfect game kills {bfs_ref['enemies_killed']}/{bfs_ref['enemies_total']} "
                f"enemies in ~{bfs_ref['ref_steps']} steps with final HP={bfs_ref['target_hp']}."
            )
        else:
            objective = (
                "Maximize the composite score of an LLM playing the Magic Tower (MOTA) "
                "game on floor MT3. The score combines: enemy completion (35%), final HP "
                "vs target of 448 (25%), step efficiency (15%), shop optimization (15%), "
                "and strategic violation avoidance (10%). The candidate text is the LLM's "
                "system prompt. A perfect game clears all enemies in ~33 steps with HP=448."
            )

    print("=" * 60)
    print("GEPA PROMPT OPTIMIZATION")
    print("=" * 60)
    print(f"Max evaluations: {max_calls}")
    print(f"Reflection model: {reflection_model}")
    print(f"Task model: {task_model or os.environ.get('MOTA_TASK_MODEL', 'qwen3.5-397b-a17b')} [{task_mode or os.environ.get('MOTA_TASK_MODE', 'auto')}]")
    print(f"Eval mode: {eval_mode}")
    if multi_floor:
        print(f"Mode: MULTI-FLOOR ({start_floor} → {end_floor})" if not curriculum else
              f"Mode: CHECKPOINT CURRICULUM ({len(curriculum)} instances: {[cp['id'] for cp in curriculum]})")
    if seed_prompt_override:
        print(f"Seed prompt: CUSTOM ({len(actual_seed)} chars)")
    if experiment_label:
        print(f"Experiment: {experiment_label}")
    if early_stop > 0:
        print(f"Early stop: >= {early_stop:.2f}")
    print()

    # Preserve the configured endpoint without collapsing a key pool down to a single key.
    os.environ["OPENAI_API_BASE"] = base_url

    # Gemini models (gemini/...) route to Google AI API, not the SAIA endpoint.
    # LiteLLM uses GEMINI_API_KEY for gemini/ prefix models.
    reflection_max_tokens = int(os.environ.get("MOTA_REFLECTION_MAX_TOKENS", "8000"))

    if reflection_model.startswith("gemini/"):
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
        reflection_lm = make_litellm_lm(reflection_model)
    else:
        reflection_lm = make_rotating_litellm_lm(
            f"openai/{reflection_model}",
            base_url=base_url,
            max_tokens=reflection_max_tokens,
        )

    # --- Reflection LM capture wrapper ---
    # Wraps the reflection LM to log each mutation's input/output for thesis analysis.
    _reflection_traces_path = (
        Path(__file__).resolve().parents[2] / "results" / "prompt_history"
        / f"reflection_traces_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    _reflection_traces_path.parent.mkdir(parents=True, exist_ok=True)
    _reflection_call_count = [0]
    _raw_reflection_lm = reflection_lm

    def _capturing_reflection_lm(prompt):
        _reflection_call_count[0] += 1
        call_num = _reflection_call_count[0]
        t0 = time.time()
        response = _raw_reflection_lm(prompt)
        elapsed = round(time.time() - t0, 1)
        # Log the prompt and response
        entry = {
            "call": call_num,
            "timestamp": datetime.datetime.now().isoformat(),
            "elapsed_s": elapsed,
            "prompt_chars": len(str(prompt)),
            "response_chars": len(response) if isinstance(response, str) else 0,
            "prompt": str(prompt)[:8000],
            "response": response[:8000] if isinstance(response, str) else str(response)[:8000],
        }
        with open(_reflection_traces_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"  [Reflection #{call_num}] {elapsed}s, response={len(response) if isinstance(response, str) else '?'} chars")
        return response

    reflection_lm = _capturing_reflection_lm

    # Select evaluate function and reflection template based on mode
    # Build floor-aware reflection prompt from BFS reference data
    from .evaluator import _scenario, _floor_data
    from ..benchmark.scorer import BFS_REFERENCE
    _active_scenario_name = _scenario.name if _scenario else (_floor_data.floor_id if _floor_data else "MT3")
    _active_bfs_ref = BFS_REFERENCE.get(_active_scenario_name)
    # Real shop flag: AI test floors have shop=None; tower floors load .js with shops.
    _active_has_shop = (_scenario.shop is not None) if _scenario else True

    if curriculum:
        def _active_evaluate(p, example=None):
            cp = example if isinstance(example, dict) and "floor" in example else curriculum[0]
            configure_multi_floor_scenario(cp["floor"], cp["target"], hero_override=dict(cp["hero"]))
            return evaluate_multi_floor(p, task_model=task_model, task_mode=task_mode)
        _reflection_template = MOTA_MULTIFLOOR_REFLECTION_PROMPT
    elif multi_floor:
        configure_multi_floor_scenario(start_floor, end_floor)
        def _active_evaluate(p):
            return evaluate_multi_floor(p, task_model=task_model, task_mode=task_mode)
        _reflection_template = MOTA_MULTIFLOOR_REFLECTION_PROMPT
    elif eval_mode.startswith("multistep"):
        # Parse chunk size from eval_mode (e.g. "multistep-3" -> 3)
        parts = eval_mode.split("-")
        ms_chunk = int(parts[1]) if len(parts) > 1 else 5
        def _active_evaluate(p):
            return evaluate_multistep(p, task_model=task_model, task_mode=task_mode, chunk_size=ms_chunk)
        _reflection_template = _build_reflection_prompt(_active_scenario_name, _active_bfs_ref, _active_has_shop)
    elif eval_mode == "oneshot":
        def _active_evaluate(p):
            return evaluate_oneshot(p, task_model=task_model, task_mode=task_mode)
        _reflection_template = _build_reflection_prompt(_active_scenario_name, _active_bfs_ref, _active_has_shop)
    else:
        def _active_evaluate(p):
            return evaluate(p, task_model=task_model, task_mode=task_mode)
        _reflection_template = _build_reflection_prompt(_active_scenario_name, _active_bfs_ref, _active_has_shop)

    # 'pareto' (library default) vs 'current_best' (greedy single lineage). With one task
    # instance the Pareto frontier has one entry, so the two coincide; the knob exists for
    # the K-candidate ablation on multi-instance runs and to make the choice explicit.
    candidate_selection = os.environ.get("GEPA_CANDIDATE_SELECTION", "pareto")
    config = GEPAConfig(
        engine=EngineConfig(
            max_metric_calls=max_calls,
            candidate_selection_strategy=candidate_selection,
            parallel=False,  # Sequential \u2014 LLM calls must be serial to avoid rate limits
            display_progress_bar=True,
        ),
        reflection=ReflectionConfig(
            reflection_lm=reflection_lm,
            reflection_prompt_template=_reflection_template,
        ),
    )

    # Early-stop wrapper: track best score and raise if threshold met
    _early_stop_state = {"best": 0.0, "calls": 0, "best_prompt": actual_seed, "per_instance": []}

    def _evaluator(candidate_prompt, example=None):
        call_num = _early_stop_state["calls"] + 1
        tag = f" [cp {example['id']} {example['floor']}→{example['target']}]" if isinstance(example, dict) and "id" in example else ""
        print(f"\n  [GEPA] Eval #{call_num}/{max_calls}{tag} starting ...", flush=True)
        score = _active_evaluate(candidate_prompt, example) if curriculum else _active_evaluate(candidate_prompt)
        _early_stop_state["calls"] = call_num
        if curriculum:
            _early_stop_state["per_instance"].append({"call": call_num, "checkpoint": example.get("id") if isinstance(example, dict) else None,
                                                      "score": score, "prompt_chars": len(candidate_prompt)})
        if score > _early_stop_state["best"]:
            _early_stop_state["best"] = score
            _early_stop_state["best_prompt"] = candidate_prompt
        print(f"  [GEPA] Eval #{call_num}{tag}: score={score:.4f}  best={_early_stop_state['best']:.4f}", flush=True)
        if early_stop > 0 and score >= early_stop and not curriculum:
            raise _EarlyStopReached(score, call_num)
        return score

    early_stopped = False
    try:
        result = optimize_anything(
            seed_candidate=actual_seed,
            evaluator=_evaluator,
            dataset=curriculum if curriculum else None,
            config=config,
        )
    except _EarlyStopReached as e:
        early_stopped = True
        result = None
        print(f"\n  *** Early stop: score {e.score:.4f} >= {early_stop:.2f} after {e.call_count} evaluations ***")

    # Save results
    output_dir = Path(__file__).resolve().parents[2] / "results"
    output_dir.mkdir(exist_ok=True)

    if early_stopped:
        best_prompt = _early_stop_state["best_prompt"]
        best_score = _early_stop_state["best"]
        candidate_history = []
    else:
        best_prompt = result.best_candidate
        best_score = result.val_aggregate_scores[result.best_idx] if result.val_aggregate_scores else None
        candidate_history = _build_candidate_history(result)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    output = {
        "format_version": 3,
        "timestamp": timestamp,
        "experiment_label": experiment_label,
        "seed_prompt": actual_seed,
        "seed_was_custom": bool(seed_prompt_override),
        "early_stopped": early_stopped,
        "best_prompt": best_prompt,
        "best_idx": result.best_idx if result else 0,
        "best_score": best_score,
        "all_scores": result.val_aggregate_scores if result else [best_score],
        "num_candidates": len(result.candidates) if result else _early_stop_state["calls"],
        "candidate_history": candidate_history,
        "parents": result.parents if result else [],
        "val_subscores": result.val_subscores if result else [],
        "per_val_instance_best_candidates": {
            str(k): sorted(v) for k, v in result.per_val_instance_best_candidates.items()
        } if result else {},
        "discovery_eval_counts": result.discovery_eval_counts if result else [],
        "total_metric_calls": result.total_metric_calls if result else _early_stop_state["calls"],
        "num_full_val_evals": result.num_full_val_evals if result else 0,
        "run_dir": result.run_dir if result else None,
        "seed": result.seed if result else 0,
        "config": {
            "max_metric_calls": max_calls,
            "candidate_selection_strategy": candidate_selection,
            "rollouts_per_candidate": int(os.environ.get("GEPA_ROLLOUTS_PER_CANDIDATE", "1")),
            "reflection_model": reflection_model,
            "task_model": task_model or os.environ.get("MOTA_TASK_MODEL", ""),
            "task_mode": task_mode or os.environ.get("MOTA_TASK_MODE", ""),
            "instances": instances,
            "curriculum": [{"id": cp["id"], "section": cp["section"], "floor": cp["floor"], "target": cp["target"]} for cp in curriculum] if curriculum else None,
        },
        "per_instance_scores": _early_stop_state["per_instance"] if curriculum else None,
        "reflection_traces_file": str(_reflection_traces_path),
        "objective": objective,
    }
    # Save to a labelled file so runs don't overwrite each other
    label_slug = (experiment_label or "gepa").replace(" ", "_").replace("/", "-")
    output_path = output_dir / f"gepa_result_{label_slug}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    # Also keep a generic copy for backwards-compatible tooling
    generic_path = output_dir / "gepa_result.json"
    with open(generic_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # --- Prompt History: append every candidate to a persistent history ---
    history_dir = output_dir / "prompt_history"
    history_dir.mkdir(exist_ok=True)

    # Save per-run snapshot
    run_history_path = history_dir / f"gepa_run_{timestamp}.json"
    with open(run_history_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Append to master prompt index
    master_index_path = history_dir / "prompt_index.json"
    master_index: list = []
    if master_index_path.exists():
        master_index = json.loads(master_index_path.read_text(encoding="utf-8"))

    for cand in candidate_history:
        entry = {
            "timestamp": timestamp,
            "experiment": experiment_label,
            "idx": cand["idx"],
            "score": cand["score"],
            "is_best": cand["is_best"],
            "parents": cand["parents"],
            "prompt_length": len(cand["prompt"]) if isinstance(cand["prompt"], str) else None,
            "run_file": run_history_path.name,
        }
        master_index.append(entry)

    with open(master_index_path, "w", encoding="utf-8") as f:
        json.dump(master_index, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"Results saved to: {output_path}")
    print(f"Generic copy:     {generic_path}")
    print(f"Best score: {best_score:.4f}" if best_score is not None else "Best score: N/A")
    num_explored = len(result.candidates) if result is not None else _early_stop_state.get("calls", 0)
    print(f"Candidates explored: {num_explored}")
    if isinstance(best_prompt, str):
        print(f"\nBest prompt ({len(best_prompt)} chars):")
        print(best_prompt[:500].encode('ascii', errors='replace').decode('ascii'))

    return result


def main():
    from .evaluator import configure_scenario, list_ai_test_floors

    _load_env()

    parser = argparse.ArgumentParser(description="MOTA GEPA Prompt Optimizer")
    parser.add_argument("--test", action="store_true", help="Single eval with seed prompt")
    parser.add_argument("--heuristic", action="store_true", help="Heuristic-only baseline")
    parser.add_argument("--floor", help="Floor file path or AI test floor filename")
    parser.add_argument("--task-preset", choices=sorted(TASK_MODEL_PRESETS), help="Built-in task-model preset")
    parser.add_argument("--task-model", help="Explicit task-model ID override")
    parser.add_argument("--task-mode", choices=["auto", "instruct", "thinking"], help="Force thinking/instruct request mode")
    parser.add_argument("--reflection-model", help="Override GEPA reflection model")
    parser.add_argument("--seed-prompt", help="Path to a .txt file with custom seed prompt (replaces default)")
    parser.add_argument("--experiment-label", help="Label for this GEPA run (stored in results)")
    parser.add_argument("--oneshot", action="store_true", help="One-shot holistic planning eval (single LLM call)")
    parser.add_argument("--multistep", action="store_true", help="Multi-step chunked planning eval")
    parser.add_argument("--chunk-size", type=int, default=5, help="Actions per LLM call for --multistep (default: 5)")
    parser.add_argument("--eval-mode", default="reactive",
                        help="Evaluation mode for GEPA runs: reactive (default), multistep-3, multistep-5, oneshot")
    parser.add_argument("--early-stop", type=float, default=0.9, help="Stop GEPA when score >= threshold (0 = disabled, default: 0.9)")
    parser.add_argument("--multi-floor", action="store_true", help="Multi-floor GEPA: evaluate across start-floor \u2192 end-floor")
    parser.add_argument("--start-floor", default="MT3", help="First floor for multi-floor mode (default: MT3)")
    parser.add_argument("--end-floor", default="MT4", help="Last floor for multi-floor mode (default: MT4)")
    parser.add_argument("--instances", type=int, nargs="+",
                        help="Checkpoint curriculum: walkthrough checkpoint ids used as GEPA task instances "
                             "(e.g. --instances 1 5 6). Implies multi-floor; each eval starts at that checkpoint.")
    parser.add_argument("--list-floors", action="store_true", help="List available AI test floors and exit")
    parser.add_argument("--list-task-presets", action="store_true", help="List built-in task-model presets and exit")
    args = parser.parse_args()

    if args.list_task_presets:
        print("Available task model presets:")
        for preset_id, preset in TASK_MODEL_PRESETS.items():
            print(f"  {preset_id:17s} {preset['model']} [{preset['mode']}]")
        return

    if args.list_floors:
        print("Available AI test floors:")
        for floor in list_ai_test_floors():
            print(f"  {Path(floor['path']).name:16s} {floor.get('size', '?')}  enemies={floor.get('enemies', '?')}  heroHP={floor.get('hero_hp', '?')}")
        return

    if args.instances:
        from .evaluator import configure_multi_floor_scenario
        from ..game.data import WALKTHROUGH_CHECKPOINTS
        cp0 = WALKTHROUGH_CHECKPOINTS[args.instances[0]]
        scenario_desc = configure_multi_floor_scenario(cp0["floor"], cp0["target"], hero_override=dict(cp0["hero"]))
        scenario_desc += f" (curriculum instances {args.instances})"
    elif args.multi_floor:
        from .evaluator import configure_multi_floor_scenario
        scenario_desc = configure_multi_floor_scenario(args.start_floor, args.end_floor)
    else:
        scenario_desc = configure_scenario(args.floor if args.floor else None)
    task_config = resolve_task_config(
        task_model=args.task_model,
        task_mode=args.task_mode,
        task_preset=args.task_preset,
    )
    os.environ["MOTA_TASK_MODEL"] = task_config["task_model"]
    os.environ["MOTA_TASK_MODE"] = task_config["task_mode"]

    print(f"Scenario: {scenario_desc}")
    print(f"Task model: {task_config['task_model']} [{task_config['task_mode']}]")

    # Load custom seed prompt if provided (shared across test/gepa)
    seed_override = None
    if args.seed_prompt:
        seed_path = Path(args.seed_prompt)
        if not seed_path.exists():
            print(f"ERROR: Seed prompt file not found: {seed_path}")
            sys.exit(1)
        seed_override = seed_path.read_text(encoding="utf-8").strip()
        print(f"Using custom seed prompt from: {seed_path} ({len(seed_override)} chars)")

    if args.heuristic:
        run_heuristic()
    elif args.test:
        run_single_eval(
            task_model=task_config["task_model"],
            task_mode=task_config["task_mode"],
            seed_prompt=seed_override,
        )
    elif args.oneshot:
        run_oneshot_eval(task_model=task_config["task_model"], task_mode=task_config["task_mode"])
    elif args.multistep:
        run_multistep_eval(task_model=task_config["task_model"], task_mode=task_config["task_mode"], chunk_size=args.chunk_size)
    else:
        run_gepa(
            task_model=task_config["task_model"],
            task_mode=task_config["task_mode"],
            reflection_model_override=args.reflection_model,
            seed_prompt_override=seed_override,
            experiment_label=args.experiment_label,
            early_stop=args.early_stop,
            multi_floor=args.multi_floor or bool(args.instances),
            start_floor=args.start_floor,
            end_floor=args.end_floor,
            eval_mode=args.eval_mode,
            instances=args.instances,
        )


if __name__ == "__main__":
    main()
