"""
Reliability harness core — shared by run_reliability.py (CLI) and the dashboard API.

One `RunCondition` describes an experiment cell exactly as the CLI flags do; `run_batch()`
executes N episodes, writes results/reliability/<label>.json after every episode (same
schema as before), regenerates SUMMARY.md, and keeps a job manifest (logs/jobs/) up to date
so the dashboard can show the run live. Evaluator semantics are untouched: single-floor
reactive/oneshot/multistep and tower episodes call the same evaluator functions as before.
"""
from __future__ import annotations

import datetime
import json
import math
import os
import statistics
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

GEPA_ROOT = Path(__file__).resolve().parents[2]
SEEDS = GEPA_ROOT / "seed_prompts"
OUT_DIR = Path(os.environ.get("MOTA_RESULTS_DIR") or GEPA_ROOT / "results") / "reliability"
# The engine configuration of every result from round 5 on (thesis §8.20.11a).
FINAL_STACK_ENV = {"CONVERSATION_HISTORY_TURNS": "0", "MOTA_ORDER_TWO_SIDED": "1", "MOTA_FIGHT_KEY_FLOOD": "1"}
# Env vars a dashboard run sets from its form; cleared before each dashboard run so nothing leaks between runs.
DASHBOARD_RUN_ENV = ("MOTA_PLAN_STEPS", "MOTA_PLAN_NO_REPLAN", "MOTA_PLAN_WORDING", *FINAL_STACK_ENV)

# Default prompt per floor when --prompt-file is not given. None -> engine default (since 2026-09-23
# the basic floor prompt for every single floor; before that the shop / no-shop seeds). The
# BFS-compiled complex prompt is no longer a default: it hard-codes fight choices, which the
# 2026-09-23 prompt rules forbid; pass it explicitly to reproduce the historical complex results.
DEFAULT_PROMPTS: dict[str, str | None] = {
    "simple": None,
    "complex": None,
    "MT3": None,
    "MT4": None,
}
BOSS_FLOORS = {"simple", "complex"}
FLUSH_EVENTS = ("turn", "floor_change", "stuck", "parse_error", "loop_guard")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _mean_sd(values: list[float]) -> tuple[float | None, float | None]:
    vals = [v for v in values if v is not None]
    if not vals:
        return (None, None)
    mean = statistics.fmean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return (round(mean, 4), round(sd, 4))


# ---------------------------------------------------------------------------
# Condition
# ---------------------------------------------------------------------------

@dataclass
class RunCondition:
    """Every knob of run_reliability.py. `prompt=None` means heuristic."""
    floor: str | None = None
    tower: bool = False
    start: str = "MT0"
    end: str = "MT23w"
    max_turns: int = 600
    checkpoint: int | None = None
    prompt: str | None = None
    prompt_name: str = "none"
    mode: str = "reactive"                 # reactive | oneshot | multistep-N
    preset: str = "qwen3.5-397b"
    task_model: str | None = None
    task_mode: str | None = None
    repeats: int = 5
    disable_overrides: bool = False
    lookahead: int | None = None
    structured_output: bool = True
    temperature: float = 0.0
    thinking_max_tokens: int | None = None
    label: str | None = None
    append: bool = False
    source: str = "cli"
    extra_env: dict = field(default_factory=dict)
    plan_steps: int = 1                     # >1: commit to k-1 further actions per call (MOTA_PLAN_STEPS)
    one_shot: bool = False                  # with plan_steps=60: one plan per floor, never re-planned
    final_stack: bool = False               # thesis final stack: history off, two-sided ORDER, key flood

    @property
    def heuristic(self) -> bool:
        return self.prompt is None

    def apply_env(self) -> None:
        """Translate the condition into the env vars the evaluator reads (mirrors the old CLI + _apply_experiment_env)."""
        os.environ["MOTA_EVAL_TEMPERATURE"] = str(float(self.temperature))
        os.environ.setdefault("MOTA_STREAM_REASONING", "1")
        os.environ.setdefault("LLM_TIMEOUT", "300")
        if self.disable_overrides:
            os.environ["MOTA_DISABLE_OVERRIDES"] = "1"
        else:
            os.environ.pop("MOTA_DISABLE_OVERRIDES", None)
        if self.lookahead is not None:
            os.environ["LOOKAHEAD_DEPTH"] = str(int(self.lookahead))
        if not self.structured_output:
            os.environ["MOTA_DISABLE_STRUCTURED_OUTPUT"] = "1"
        else:
            os.environ.pop("MOTA_DISABLE_STRUCTURED_OUTPUT", None)
        if self.thinking_max_tokens:
            os.environ["THINKING_MAX_TOKENS"] = str(int(self.thinking_max_tokens))
        if self.tower:
            os.environ["MOTA_MULTI_FLOOR_MAX_TURNS"] = str(int(self.max_turns))
        # Only set, never cleared: CLI runs pass these through the process env (scripts/run_followups.py).
        if self.plan_steps and self.plan_steps > 1:
            os.environ["MOTA_PLAN_STEPS"] = str(int(self.plan_steps))
        if self.one_shot:
            os.environ["MOTA_PLAN_STEPS"] = "60"
            os.environ["MOTA_PLAN_NO_REPLAN"] = "1"
        if self.final_stack:
            os.environ.update(FINAL_STACK_ENV)
        for k, v in self.extra_env.items():
            os.environ[k] = str(v)


@dataclass
class Resolved:
    cond: RunCondition
    label: str
    task_model: str
    task_mode: str
    lookahead: int
    model_label: str
    hero_override: dict | None
    checkpoint_desc: str
    floor_desc: str
    out_path: Path

    def config(self) -> dict:
        c = self.cond
        return {
            "floor": None if c.tower else c.floor,
            "start": c.start if c.tower else None,
            "end": c.end if c.tower else None,
            "max_turns": c.max_turns if c.tower else None,
            "checkpoint": c.checkpoint,
            "hero_override": self.hero_override,
            "prompt_file": c.prompt_name,
            "prompt_chars": len(c.prompt) if c.prompt else 0,
            "model": "heuristic" if c.heuristic else self.task_model,
            "task_mode": "-" if c.heuristic else self.task_mode,
            "preset": self.model_label,
            "mode": "heuristic" if c.heuristic else c.mode,
            "temperature": c.temperature,
            "lookahead": self.lookahead,
            "structured_output": c.structured_output,
            "overrides_disabled": c.disable_overrides,
            # Which engine flags shaped the prompt/loop (so a result file is self-describing).
            "env": {k: os.environ[k] for k in ("MOTA_STRATEGIC_OVERRIDES", "MOTA_SUPPRESS_HINTS", "MOTA_LEGACY_SEEDS",
                                                "MOTA_POTIONS_ON_DEMAND", "THINKING_MAX_TOKENS",
                                                "CONVERSATION_HISTORY_TURNS", "MOTA_OFFER_LEVELUPS",
                                                "MOTA_COMPACT_PROMPT", "MOTA_EXECUTE_LETHAL_ONLY",
                                                "MOTA_TOWER_HP_FLOOR", "MOTA_ORDER_TWO_SIDED",
                                                "MOTA_FIGHT_KEY_FLOOD", "MOTA_PLAN_STEPS", "MOTA_PLAN_NO_REPLAN",
                                                "MOTA_PLAN_WORDING", "MOTA_BARE_OBS", "MOTA_SHOP_ROUTE", "MOTA_REMOTE_ACTIONS", "MOTA_WAY_UP", "MOTA_EFFCOST_NET", "MOTA_TOWER_FIDELITY", "MOTA_GRID_MAP", "MOTA_BLOCKER_GRAPH", "MOTA_TOWER_HP_FLOOR", "MOTA_OFFER_LEVELUPS", "MOTA_PLAN_MEMORY", "MOTA_HP_RULE_PCT", "MOTA_NO_KEY_PURCHASE", "MOTA_WAYUP_COMBINED", "MOTA_FREE_AFFORD", "MOTA_NPC_TRADES", "MOTA_KEY_RESERVE", "MOTA_AFTER_BATTLE", "MOTA_RESUME_LOG", "MOTA_RESUME_BEFORE_TURN", "MOTA_BLUE_KEY_PURCHASE", "MOTA_BOSS_KEY_RESERVE", "MOTA_BUY_QUANTITY", "MOTA_VAMPIRE_TAG", "MOTA_EVENT_WAY", "LLM_TIMEOUT") if k in os.environ},
            "source": c.source,
        }


def load_prompt(floor: str, prompt_file: str | None) -> tuple[str, str]:
    if prompt_file:
        path = Path(prompt_file)
        if not path.exists():
            path = SEEDS / prompt_file
        return path.read_text(encoding="utf-8"), path.name
    from mota.optimizer.seed_prompt import get_seed_for_floor
    # 'MTa-MTb' (tower range) -> tower_basic.txt, any single floor -> floor_basic.txt (since 2026-09-23)
    kind = "tower" if "-" in str(floor) else "floor"
    label = f"engine-default-{kind}-basic"
    if os.environ.get("MOTA_LEGACY_SEEDS", "").strip() in ("1", "true", "yes"):
        label = "engine-legacy-seed"  # pre-2026-09-23 shop / no-shop seed (MOTA_LEGACY_SEEDS=1)
    if os.environ.get("MOTA_STRATEGIC_OVERRIDES", "").strip() in ("1", "true", "yes"):
        label += "+strategic-overrides"
    return get_seed_for_floor(floor), label


def resolve(cond: RunCondition) -> Resolved:
    from mota.optimizer.model_config import resolve_task_config
    cfg = resolve_task_config(task_model=cond.task_model, task_mode=cond.task_mode, task_preset=cond.preset)
    task_model, task_mode = cfg["task_model"], cfg["task_mode"]
    cond.apply_env()
    lookahead = int(os.environ.get("LOOKAHEAD_DEPTH", "3"))
    model_label = "heuristic" if cond.heuristic else cond.preset
    hero_override = None
    checkpoint_desc = ""
    if cond.checkpoint is not None:
        from mota.game.data import WALKTHROUGH_CHECKPOINTS
        if not cond.tower:
            raise ValueError("checkpoint requires tower mode")
        if not 0 <= cond.checkpoint < len(WALKTHROUGH_CHECKPOINTS):
            raise ValueError(f"checkpoint must be 0..{len(WALKTHROUGH_CHECKPOINTS) - 1}")
        cp = WALKTHROUGH_CHECKPOINTS[cond.checkpoint]
        cond.start = cp["floor"]
        if not cond.end or cond.end == "MT23w":
            cond.end = cp["target"]
        hero_override = dict(cp["hero"])
        checkpoint_desc = f" | checkpoint {cp['id']} ({cp['section']}) hero={cp['hero']}"
    if cond.tower:
        label = cond.label or (f"segment{cond.checkpoint}_{cond.start}-{cond.end}_{model_label}" if cond.checkpoint is not None
                               else f"tower_{cond.start}-{cond.end}_{model_label}")
        floor_desc = f"{cond.start}→{cond.end}"
    else:
        if not cond.floor:
            raise ValueError("floor required for single-floor runs")
        plan = "_maxsteps_once" if cond.one_shot else ("_maxsteps" if cond.plan_steps >= 60 else
                                                        f"_plan{cond.plan_steps}" if cond.plan_steps > 1 else "")
        label = cond.label or (f"{cond.floor}_{model_label}_{cond.mode}{plan}{'_final' if cond.final_stack else ''}"
                               f"{'_raw' if cond.disable_overrides else ''}{'' if lookahead == 3 else f'_la{lookahead}'}")
        floor_desc = cond.floor
    return Resolved(cond, label, task_model, task_mode, lookahead, model_label, hero_override,
                    checkpoint_desc, floor_desc, OUT_DIR / f"{label}.json")


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------

def configure_floor(floor: str) -> None:
    from mota.optimizer import evaluator as ev
    if floor == "MT3":
        ev.configure_mt3_scenario()
    elif floor == "MT4":
        ev.configure_mt4_scenario()
    elif floor in ("simple", "complex"):
        ev.configure_scenario(str((GEPA_ROOT / "data" / "floors" / f"{floor}.txt").resolve()))
    else:
        ev.configure_scenario(floor)


def _make_logger_hook(run_log, on_turn: Callable[[dict], None] | None, on_log_saved: Callable[[str], None] | None,
                      flush_per_turn: bool, job_id: str | None = None):
    """Compose: record → (flush) → notify → pause gate.

    Flushing per turn leaves a replayable partial log and feeds the live view. With a job id the hook
    also honours ``pause_requested`` in the job manifest (dashboard pause/resume) between turns.
    """
    announced = {"done": False}
    job = None
    if job_id:
        from mota.dashboard import jobs as J
        job = J.Job.load(job_id)

    def hook(ev_dict: dict):
        run_log.add_event(ev_dict)
        if flush_per_turn and ev_dict.get("type") in FLUSH_EVENTS + ("thinking",):  # thinking: pending step visible live
            try:
                p = run_log.save()
                if not announced["done"] and on_log_saved:
                    announced["done"] = True
                    on_log_saved(p.name)
            except Exception:
                pass
        if on_turn:
            on_turn(ev_dict)
        if job is not None and ev_dict.get("type") in ("turn", "floor_change"):
            from mota.dashboard import jobs as J
            J.pause_gate(job, on_state=lambda st: st in ("paused", "running") and hook(
                {"type": "paused" if st == "paused" else "resumed", "turn": ev_dict.get("turn"), "reason": f"{st} from dashboard"}))
    return hook


def run_once(floor: str, prompt: str | None, mode: str, task_model: str, task_mode: str, *,
             on_turn: Callable[[dict], None] | None = None, on_log_saved: Callable[[str], None] | None = None,
             job_id: str | None = None) -> dict:
    from mota.optimizer import evaluator as ev
    from mota.dashboard.run_logger import RunLogger

    configure_floor(floor)  # fresh scenario per run: no state leakage between repeats
    log_path = None
    t0 = time.time()
    if prompt is None:
        res = ev.evaluate_heuristic_only()
        score = float(res["total"])
    else:
        if mode == "reactive" or mode.startswith("map-") or mode == "oneshot":
            # Same loop as evaluate(), but every turn (state text, action tree, LLM
            # response, CoT) is persisted as a dashboard-replayable run log so an
            # episode can be diffed against a stored kill afterwards.
            run_log = RunLogger(floor_id=floor, mode="llm", prompt=prompt,
                                task_model=task_model, task_mode=task_mode, job_id=job_id)
            hook = _make_logger_hook(run_log, on_turn, on_log_saved, flush_per_turn=True, job_id=job_id)
            temp = float(os.environ.get("MOTA_EVAL_TEMPERATURE", "0.0"))
            if mode == "reactive":
                res = ev.evaluate_with_callback(
                    candidate_prompt=prompt, on_event=hook,
                    task_model=task_model, task_mode=task_mode, temperature=temp,
                )
            elif mode == "map-graph":
                res = ev.evaluate_map_graph(prompt, on_event=hook, task_model=task_model, task_mode=task_mode,
                                            temperature=temp)
            elif mode == "oneshot":
                ev.evaluate_oneshot(prompt, task_model=task_model, task_mode=task_mode, on_event=hook)
                res = ev.get_last_eval_result() or {}
                res.setdefault("tracking", {})["llm_calls"] = 1
                res["tracking"]["fallback_turns"] = sum(1 for t in run_log.turns if t.get("type") == "turn" and t.get("fallback"))
            else:
                res = ev.evaluate_map_enumerate(
                    prompt, on_event=hook, task_model=task_model, task_mode=task_mode,
                    temperature=temp, with_costs=mode == "map-enum-costs",
                )
            score = float(res.get("total", 0.0))
            # evaluate_with_callback() carries no "tracking" block; derive the call
            # split from the persisted turn events instead.
            turn_events = [t for t in run_log.turns if t.get("type") == "turn"]
            res.setdefault("tracking", {})
            res["tracking"].setdefault("forced_turns", sum(1 for t in turn_events if t.get("forced")))
            res["tracking"].setdefault("llm_calls", sum(1 for t in turn_events if not t.get("forced") and not t.get("planned")
                                                    and (t.get("llm_response") is not None or not t.get("fallback"))))
            res["tracking"].setdefault("planned_turns", sum(1 for t in turn_events if t.get("planned")))
            res["tracking"].setdefault("fallback_turns", sum(1 for t in turn_events if t.get("fallback")))
            res["tracking"].setdefault("parse_errors", sum(1 for t in run_log.turns if t.get("type") == "parse_error"))
            try:
                log_path = run_log.save().name
            except Exception as e:  # logging must never fail the experiment
                print(f"  (run log not saved: {e})", flush=True)
        elif mode.startswith("multistep"):
            chunk = int(mode.split("-")[1]) if "-" in mode else 5
            score = ev.evaluate_multistep(prompt, task_model=task_model, task_mode=task_mode, chunk_size=chunk)
            res = ev.get_last_eval_result() or {}
        else:
            raise ValueError(f"unknown mode {mode}")
    elapsed = round(time.time() - t0, 1)

    details = res.get("details", {}) or {}
    violations = [str(v) for v in res.get("violations", [])]
    tracking = res.get("tracking", {}) or {}
    died = any("suicide" in v or "died" in v.lower() for v in violations) or (details.get("final_hp") or 0) <= 0
    goal = res.get("goal")
    goal_reached = res.get("goal_reached")
    if floor in BOSS_FLOORS or res.get("goal") == "boss":
        # boss_fight_won is True even when the killing blow was lethal for the hero;
        # success additionally requires the hero to be alive.
        boss_fight_won = goal_reached if goal_reached is not None else ("boss_not_killed" not in violations)
        if goal is not None and goal != "boss":
            raise RuntimeError(f"{floor}: expected a boss-goal scenario but got goal={goal!r} — "
                               "the floor is misconfigured and results would be meaningless")
        success = bool(boss_fight_won) and not died
    else:
        # Non-boss floors: success = full clear while alive.
        ek, et = details.get("enemies_killed"), details.get("enemies_total")
        boss_fight_won = None
        success = (not died) and ek is not None and et is not None and ek >= et
    # Prefer the scorer's two-tier verdict when present (identical rule, single source of truth).
    if res.get("success") is not None:
        success = bool(res["success"])
    target_hp = details.get("target_hp")
    hp_ratio = res.get("hp_ratio")
    if hp_ratio is None and success and target_hp and details.get("final_hp") is not None:
        hp_ratio = round(details["final_hp"] / target_hp, 4)

    return {
        "score": round(float(score), 4),
        "goal_score": res.get("goal_score"),
        "success": bool(success),
        "hp_ratio": hp_ratio,
        "boss_fight_won": boss_fight_won,
        "goal": goal,
        "goal_reached": goal_reached,
        "died": bool(died),
        "final_hp": details.get("final_hp"),
        "hero_atk": details.get("hero_atk"),
        "hero_def": details.get("hero_def"),
        "enemies_killed": details.get("enemies_killed"),
        "enemies_total": details.get("enemies_total"),
        "steps": details.get("steps"),
        "violations": violations,
        "llm_calls": tracking.get("llm_calls"),
        "parse_errors": tracking.get("parse_errors"),
        "forced_turns": tracking.get("forced_turns"),
        "planned_turns": tracking.get("planned_turns"),
        "lethal_only_stop": res.get("lethal_only_stop"),
        "map_enum": res.get("map_enum"),
        "map_graph": res.get("map_graph"),
        "run_log": log_path,
        "elapsed_s": elapsed,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def run_tower_once(start: str, end: str, prompt: str | None, task_model: str, task_mode: str,
                   hero_override: dict | None = None, *,
                   on_turn: Callable[[dict], None] | None = None, on_log_saved: Callable[[str], None] | None = None,
                   job_id: str | None = None, verbose: bool = False) -> dict:
    from mota.optimizer import evaluator as ev
    from mota.dashboard.run_logger import RunLogger

    ev.configure_multi_floor_scenario(start, end, hero_override=hero_override)
    log_path = None
    run_log = None
    on_event = None
    if prompt is not None:
        run_log = RunLogger(floor_id=f"{start}-{end}", mode="llm", prompt=prompt,
                            task_model=task_model, task_mode=task_mode, job_id=job_id)
        inner = _make_logger_hook(run_log, on_turn, on_log_saved, flush_per_turn=True, job_id=job_id)

        def on_event(ev_dict, _inner=inner, _log=run_log):
            _inner(ev_dict)
            if verbose and ev_dict.get("type") in FLUSH_EVENTS:
                print(f"  [{ev_dict.get('type')}] turn={ev_dict.get('turn')} floor={ev_dict.get('floor_id', '')} "
                      f"{ev_dict.get('action', ev_dict.get('reason', ''))} -> {_log.path.name if _log.path else ''}", flush=True)
    elif on_turn is not None:
        on_event = on_turn
    t0 = time.time()
    res = ev.evaluate_multi_floor_with_callback(
        candidate_prompt=prompt, on_event=on_event,
        task_model=task_model, task_mode=task_mode,
        temperature=float(os.environ.get("MOTA_EVAL_TEMPERATURE", "0.0")),
    )
    elapsed = round(time.time() - t0, 1)
    llm_calls = parse_errors = forced_turns = model_calls = planned_turns = None
    if run_log is not None:
        turn_events = [t for t in run_log.turns if t.get("type") == "turn"]
        forced_turns = sum(1 for t in turn_events if t.get("forced"))
        llm_calls = sum(1 for t in turn_events if not t.get("forced"))  # LLM-decided turns, incl. executed plan steps
        planned_turns = sum(1 for t in turn_events if t.get("planned"))
        model_calls = sum(1 for t in run_log.turns if t.get("type") == "thinking")
        parse_errors = sum(1 for t in run_log.turns if t.get("type") == "parse_error")
        try:
            log_path = run_log.save().name
        except Exception as e:  # logging must never fail the experiment
            print(f"  (run log not saved: {e})", flush=True)
    hero = res.get("hero", {}) or {}
    transitions = res.get("floor_transitions", []) or []
    return {
        "score": round(float(res.get("total", 0.0)), 4),
        "success": bool(res.get("goal_reached")),
        "died": bool(res.get("failed")) and "died" in str(res.get("failure_reason", "")).lower(),
        "floors_reached": res.get("floors_reached"),
        "max_floor_id": res.get("max_floor_id"),
        "total_floors": res.get("total_floors"),
        "final_floor_id": res.get("final_floor_id"),
        "failure_reason": res.get("failure_reason"),
        "final_hp": hero.get("hp"),
        "hero_atk": hero.get("atk"),
        "hero_def": hero.get("def"),
        "keys": hero.get("keys"),
        "money": hero.get("money"),
        "exp": hero.get("exp"),
        "turns": res.get("turn_count"),
        "llm_calls": llm_calls,
        "model_calls": model_calls,
        "planned_turns": planned_turns,
        "parse_errors": parse_errors,
        "forced_turns": forced_turns,
        "lethal_only_stop": res.get("lethal_only_stop"),
        "run_log": log_path,
        "floor_transitions": transitions,
        "elapsed_s": elapsed,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# Aggregation / persistence
# ---------------------------------------------------------------------------

def aggregate(runs: list[dict]) -> dict:
    n = len(runs)
    succ = sum(1 for r in runs if r.get("success"))
    lo, hi = wilson_ci(succ, n)
    score_mean, score_sd = _mean_sd([r.get("score") for r in runs])
    goal_scores = [r.get("goal_score") for r in runs if r.get("goal_score") is not None]
    goal_mean, goal_sd = _mean_sd(goal_scores) if goal_scores else (None, None)
    ratios = [r.get("hp_ratio") for r in runs if r.get("success") and r.get("hp_ratio") is not None]
    hp_ratio_mean, hp_ratio_sd = _mean_sd(ratios) if ratios else (None, None)
    hp_mean, hp_sd = _mean_sd([r.get("final_hp") for r in runs if r.get("final_hp") is not None])
    total_calls = sum(r.get("llm_calls") or 0 for r in runs)
    total_parse = sum(r.get("parse_errors") or 0 for r in runs)
    total_elapsed = sum(r.get("elapsed_s") or 0 for r in runs)
    agg = {
        "n": n,
        "successes": succ,
        "success_rate": round(succ / n, 4) if n else None,
        "success_ci95": [round(lo, 4), round(hi, 4)],
        "died": sum(1 for r in runs if r.get("died")),
        # would have died had the lethal-only position been executed (pre-2026-09-26 label)
        "lethal_only_stops": sum(1 for r in runs if r.get("lethal_only_stop")),
        "hp_ratio_mean": hp_ratio_mean,
        "hp_ratio_sd": hp_ratio_sd,
        "goal_score_mean": goal_mean,
        "goal_score_sd": goal_sd,
        "score_mean": score_mean,
        "score_sd": score_sd,
        "score_min": min((r["score"] for r in runs), default=None),
        "score_max": max((r["score"] for r in runs), default=None),
        "final_hp_mean": hp_mean,
        "final_hp_sd": hp_sd,
        "llm_calls_total": total_calls,
        "seconds_per_call": round(total_elapsed / total_calls, 2) if total_calls else None,
        "parse_error_rate": round(total_parse / total_calls, 4) if total_calls else None,
        "elapsed_s_total": round(total_elapsed, 1),
    }
    if runs and "floors_reached" in runs[0]:
        fr = [r["floors_reached"] for r in runs if r.get("floors_reached") is not None]
        agg["floors_reached_mean"] = round(statistics.fmean(fr), 2) if fr else None
        agg["floors_reached_max"] = max(fr) if fr else None
        agg["max_floor_ids"] = [r.get("max_floor_id") for r in runs]
    me = [r["map_enum"] for r in runs if r.get("map_enum")]
    if me:
        tot = {k: sum(m.get(k) or 0 for m in me) for k in me[0] if isinstance(me[0][k], int)}
        agg["map_enum"] = {
            **tot,
            "precision": round(tot["options_legal"] / tot["options_listed"], 4) if tot.get("options_listed") else None,
            "recall": round(tot["legal_found"] / tot["legal_total"], 4) if tot.get("legal_total") else None,
            "choice_violation_rate": round((tot["choice_illegal"] + tot["choice_parse_fail"]) / tot["llm_turns"], 4)
            if tot.get("llm_turns") else None,
        }
    return agg


def load_existing(path: Path) -> dict | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _backfill_two_tier(d: dict, path: Path) -> dict:
    """Result files written before the two-tier fields existed: derive hp_ratio from the
    BFS reference HP and re-aggregate, persisting the upgrade so it happens once."""
    if "hp_ratio_mean" in d.get("aggregate", {}):
        return d
    from mota.benchmark.scorer import BFS_REFERENCE
    ref = BFS_REFERENCE.get(d.get("config", {}).get("floor") or "")
    target_hp = ref["target_hp"] if ref else None
    for r in d.get("runs", []):
        if "boss_killed" in r and "boss_fight_won" not in r:
            r["boss_fight_won"] = r.pop("boss_killed")
        if r.get("hp_ratio") is None and r.get("success") and target_hp and r.get("final_hp") is not None:
            r["hp_ratio"] = round(r["final_hp"] / target_hp, 4)
    d["aggregate"] = aggregate(d["runs"])
    path.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return d


def list_results() -> list[dict]:
    """Every results/reliability/<label>.json (skipping _-prefixed scratch labels) with its aggregate."""
    out = []
    if not OUT_DIR.is_dir():
        return out
    thesis_file = OUT_DIR / "_thesis_labels.json"  # written by scripts/thesis_labels.py
    thesis = set(json.loads(thesis_file.read_text(encoding="utf-8"))) if thesis_file.exists() else set()
    for p in sorted(OUT_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "runs" not in d:
            continue  # census / auxiliary files share the folder
        out.append({"label": d.get("label", p.stem), "config": d.get("config", {}),
                    "aggregate": d.get("aggregate", {}), "n": len(d.get("runs", [])),
                    "runs": d.get("runs", []), "updated": d.get("updated"), "file": p.name,
                    "thesis": d.get("label", p.stem) in thesis})
    return out


def write_summary() -> Path:
    rows = []
    for path in sorted(OUT_DIR.glob("*.json")):
        d = load_existing(path)
        if not d or "aggregate" not in d:
            continue
        d = _backfill_two_tier(d, path)
        a, c = d["aggregate"], d["config"]
        lo, hi = a["success_ci95"]
        extra = ""
        if "floors_reached_mean" in a:
            extra = f" floors={a['floors_reached_mean']} (max {a['floors_reached_max']})"
        hp_ratio = a.get("hp_ratio_mean")
        hp_ratio_s = f"{hp_ratio:.2f}" if hp_ratio is not None else "-"
        rows.append(
            f"| {d['label']} | {c.get('floor') or c.get('start') + '→' + c.get('end')} | {c['model']} [{c['task_mode']}] "
            f"| {c['mode']} | {c.get('lookahead', 3)} | {'off' if c.get('overrides_disabled') else 'on'} | {a['n']} "
            f"| {a['successes']}/{a['n']} = {a['success_rate']:.2f} [{lo:.2f}, {hi:.2f}] "
            f"| {hp_ratio_s} | {a.get('died', '-')} "
            f"| {a['score_mean']} ± {a['score_sd']} | {a['final_hp_mean']} "
            f"| {a.get('seconds_per_call') if a.get('seconds_per_call') is not None else '-'} "
            f"| {a['parse_error_rate'] if a['parse_error_rate'] is not None else '-'}{extra} | {d['updated']} |"
        )
    header = (
        "# Reliability summary\n\n"
        "Two-tier reporting. **success** = goal reached with the hero alive (boss killed on simple/complex, "
        "full clear on MT3/MT4, tower goal reached); CI = Wilson 95%. **HP/opt** = final HP / BFS-optimal HP, "
        "mean over successes only. **died** = episodes ending with HP <= 0. The legacy composite score is kept "
        "only for comparison with earlier E-tables; it inverts outcome order (a lethal boss attempt scores ~0.70, "
        "a safe non-kill ~0.37).\n\n"
        "| label | floor | model | mode | LA | overrides | N | success [CI] | HP/opt | died | legacy score mean ± sd | HP mean | s/call | parse-err rate | updated |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "SUMMARY.md"
    out.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def _progress_from_event(ev: dict) -> dict:
    p: dict = {}
    if ev.get("type") in ("turn", "floor_change", "start"):
        hero = ev.get("hero") or {}
        p.update({"turn": ev.get("turn"), "floor_id": ev.get("floor_id"),
                  "hp": hero.get("hp"), "atk": hero.get("atk"), "def": hero.get("def")})
        if ev.get("type") == "turn":
            p["last_action"] = ev.get("action")
            p["forced"] = bool(ev.get("forced"))
    elif ev.get("type") == "parse_error":
        p["last_parse_error_turn"] = ev.get("turn")
    return {k: v for k, v in p.items() if v is not None}


def run_batch(cond: RunCondition, *, on_event: Callable[[dict], None] | None = None,
              on_turn: Callable[[dict], None] | None = None, should_stop: Callable[[], bool] | None = None,
              job=None, register_job: bool = True, log: Callable[[str], None] = print,
              verbose_tower: bool = False) -> dict:
    """Execute `cond.repeats` episodes; returns the final results payload (same schema as the JSON file).

    on_event: harness-level events {start, run, stopped, done, error}.
    on_turn:  every evaluator event of every episode (for live streaming).
    job:      an existing jobs.Job to update (else one is created when register_job).
    """
    from mota.dashboard import jobs as J

    r = resolve(cond)
    c = r.cond
    repeats = 1 if c.heuristic else int(c.repeats)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_existing(r.out_path) if c.append else None
    runs: list[dict] = list(existing["runs"]) if existing else []

    if job is None and register_job:
        job = J.Job.start(
            "tower" if c.tower else "reliability", r.label, uses_api=not c.heuristic, source=c.source,
            condition={**{k: v for k, v in asdict(c).items() if k not in ("prompt", "extra_env")}, "env": r.config()["env"]},
            floor=None if c.tower else c.floor, start=c.start if c.tower else None, end=c.end if c.tower else None,
            checkpoint=c.checkpoint, model=None if c.heuristic else r.task_model, preset=r.model_label,
            mode="heuristic" if c.heuristic else c.mode,
        )
        job.progress(repeats_total=len(runs) + repeats, repeats_done=len(runs), out_file=str(r.out_path))
    job_id = job.job_id if job else None

    def emit(ev: dict):
        if on_event:
            on_event(ev)

    def turn_hook(ev: dict):
        if job is not None:
            p = _progress_from_event(ev)
            if p:
                job.progress(**p)
        if on_turn:
            on_turn(ev)

    def log_saved(name: str):
        if job is not None:
            job.set_run_log(name)

    payload: dict = {"label": r.label, "config": r.config(), "runs": runs, "aggregate": aggregate(runs) if runs else {},
                     "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    status = "done"
    try:
        emit({"type": "start", "label": r.label, "repeats": repeats, "tower": c.tower, "floor": r.floor_desc,
              "model": r.task_model if not c.heuristic else "heuristic", "mode": c.mode, "job_id": job_id,
              "prompt": c.prompt_name, "lookahead": r.lookahead, "overrides": "off" if c.disable_overrides else "on",
              "checkpoint": r.checkpoint_desc})
        for i in range(repeats):
            if should_stop and should_stop():
                status = "stopped"
                emit({"type": "stopped"})
                break
            log(f"[{r.label}] run {len(runs) + 1} (this session {i + 1}/{repeats})")
            if job is not None:
                job.progress(run_idx=len(runs) + 1, episode_started=datetime.datetime.now().isoformat(timespec="seconds"))
            try:
                if c.tower:
                    rec = run_tower_once(c.start, c.end, c.prompt, r.task_model, r.task_mode, hero_override=r.hero_override,
                                         on_turn=turn_hook, on_log_saved=log_saved, job_id=job_id, verbose=verbose_tower)
                else:
                    rec = run_once(c.floor, c.prompt, c.mode, r.task_model, r.task_mode,
                                   on_turn=turn_hook, on_log_saved=log_saved, job_id=job_id)
            except KeyboardInterrupt:
                log("\ninterrupted — saving partial results")
                status = "stopped"
                break
            except Exception as e:  # noqa: BLE001 — record the failure and continue the batch
                rec = {"score": 0.0, "success": False, "died": False, "error": f"{type(e).__name__}: {e}",
                       "elapsed_s": None, "timestamp": datetime.datetime.now().isoformat(timespec="seconds")}
                log(f"  run failed: {rec['error']}")
            rec["run_idx"] = len(runs) + 1
            runs.append(rec)
            if rec.get("run_log") and job is not None:
                job.set_run_log(rec["run_log"])
            bits = f"success={rec.get('success')} HP={rec.get('final_hp')}"
            if rec.get("hp_ratio") is not None:
                bits += f" HP/opt={rec['hp_ratio']:.2f}"
            if rec.get("goal_score") is not None:
                bits += f" goal_score={rec['goal_score']}"
            bits += f" legacy={rec.get('score')}"
            if c.tower:
                bits += f" floor={rec.get('max_floor_id') or rec.get('final_floor_id')} reason={rec.get('failure_reason')}"
            log(f"  -> {bits}")
            payload = {"label": r.label, "config": r.config(), "runs": runs, "aggregate": aggregate(runs),
                       "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
            r.out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            if job is not None:
                job.progress(repeats_done=len(runs), last_record={k: rec.get(k) for k in
                             ("success", "final_hp", "hp_ratio", "score", "max_floor_id", "failure_reason", "error")},
                             aggregate=payload["aggregate"])
            emit({"type": "run", "index": i, "record": rec, "aggregate": payload["aggregate"], "job_id": job_id})
        try:
            write_summary()
        except Exception as e:
            log(f"  (summary not written: {e})")
        emit({"type": "done", "label": r.label, "aggregate": payload.get("aggregate", {}), "file": str(r.out_path),
              "job_id": job_id})
    except Exception as e:
        status = "failed"
        emit({"type": "error", "message": f"{type(e).__name__}: {e}", "job_id": job_id})
        if job is not None:
            job.finish("failed", error=f"{type(e).__name__}: {e}")
        raise
    if job is not None:
        job.finish(status, result=payload.get("aggregate"))
    return payload
