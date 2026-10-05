# -*- coding: utf-8 -*-
"""
Linear (non-Pareto) GEPA reflection loop.

This is a deliberately simplified alternative to the external ``gepa`` library's
``optimize_anything`` (which maintains a Pareto candidate pool and chooses which
candidate to mutate next). The user does NOT need candidate-pool / Pareto
variation selection — only a straight-line reflective loop:

    for each iteration:
        1. evaluate the current prompt   -> score + turn-by-turn game trace
        2. feed (current prompt + trace) into the reflection ("teacher") prompt
        3. the reflection model returns an improved prompt
        4. the improved prompt becomes the current prompt for the next iteration

The best-scoring prompt seen across all iterations is returned. The reflection
("teacher") template is the floor-aware ``_build_reflection_prompt`` defined in
``run_gepa`` — it already adapts to shop vs no-shop floors.

The original Pareto-based ``run_gepa`` is kept for thesis comparison.
"""
from __future__ import annotations

import datetime
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable

# Reuse the teacher-prompt template and multi-floor variant from run_gepa.
from .run_gepa import _build_reflection_prompt, MOTA_MULTIFLOOR_REFLECTION_PROMPT


# ---------------------------------------------------------------------------
# stdout capture — the evaluator writes its turn-by-turn trace to sys.stdout
# (via sys.stdout.buffer) when NOT running inside the gepa library. We capture
# that text so it can be fed into the reflection template's <side_info> slot.
# ---------------------------------------------------------------------------
class _StdoutCapture:
    """A minimal stdout replacement exposing a ``.buffer`` like the real one."""

    class _Buffer:
        def __init__(self, outer: "_StdoutCapture"):
            self._outer = outer

        def write(self, b):
            if isinstance(b, (bytes, bytearray)):
                self._outer._raw.write(bytes(b))
            else:
                self._outer._raw.write(str(b).encode("utf-8", "replace"))
            return len(b)

        def flush(self):
            pass

    def __init__(self, mirror: bool = True):
        self._raw = io.BytesIO()
        self._mirror = mirror
        self._real = sys.__stdout__
        self.buffer = _StdoutCapture._Buffer(self)

    def write(self, s):
        self._raw.write(str(s).encode("utf-8", "replace"))
        if self._mirror and self._real is not None:
            try:
                self._real.write(str(s))
            except Exception:
                pass
        return len(s)

    def flush(self):
        if self._mirror and self._real is not None:
            try:
                self._real.flush()
            except Exception:
                pass

    def getvalue(self) -> str:
        return self._raw.getvalue().decode("utf-8", "replace")


def _extract_prompt(reflection_response: str) -> str | None:
    """Extract the improved prompt from a reflection response.

    The teacher prompt instructs the model to wrap the improved prompt in
    triple-backtick fences. Return the content of the LAST fenced block; fall
    back to the whole response if no fences are found.
    """
    if not isinstance(reflection_response, str):
        return None
    # Find all fenced blocks (optionally tagged, e.g. ```text).
    blocks = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", reflection_response, re.DOTALL)
    if blocks:
        candidate = blocks[-1].strip()
        return candidate or None
    # No fences — use the raw response if it looks like a prompt.
    stripped = reflection_response.strip()
    return stripped or None


def run_linear_gepa(
    *,
    seed_prompt: str,
    task_model: str | None = None,
    task_mode: str | None = None,
    reflection_model: str | None = None,
    experiment_label: str | None = None,
    eval_mode: str = "reactive",
    max_iters: int = 5,
    early_stop: float = 0.0,
    multi_floor: bool = False,
    start_floor: str = "MT3",
    end_floor: str = "MT4",
    progress_cb: Callable[[dict], None] | None = None,
    save_result: bool = True,
    stop_flag: Callable[[], bool] | None = None,
    instances: list[int] | None = None,
) -> dict:
    """Run the linear reflection loop and return a result dict.

    Parameters mirror the dashboard's GEPA-start payload so it can be wired in
    directly. ``progress_cb`` is called once per evaluation with the iteration
    record (for live dashboard streaming). ``stop_flag`` is polled between
    iterations so the dashboard can request an early stop. ``instances`` = walkthrough
    checkpoint ids (curriculum): each candidate is scored on every checkpoint segment
    and the mean is used; per-instance scores are attached to the record.
    """
    from .evaluator import (
        evaluate,
        evaluate_multistep,
        evaluate_oneshot,
        evaluate_multi_floor,
        configure_multi_floor_scenario,
        make_rotating_litellm_lm,
        get_last_eval_result,
        _scenario,
        _floor_data,
    )
    from ..benchmark.scorer import BFS_REFERENCE

    base_url = (os.environ.get("SAIA_BASE_URL")
                or os.environ.get("OPENAI_API_BASE", "https://chat-ai.academiccloud.de/v1"))
    os.environ["OPENAI_API_BASE"] = base_url

    reflection_model = reflection_model or os.environ.get("MOTA_REFLECTION_MODEL", "qwen3.5-397b-a17b")
    reflection_max_tokens = int(os.environ.get("MOTA_REFLECTION_MAX_TOKENS", "8000"))
    reflection_lm = make_rotating_litellm_lm(
        f"openai/{reflection_model}",
        base_url=base_url,
        max_tokens=reflection_max_tokens,
    )

    # Select the evaluate function and floor-aware teacher template.
    scenario_name = _scenario.name if _scenario else (_floor_data.floor_id if _floor_data else "MT3")
    bfs_ref = BFS_REFERENCE.get(scenario_name)
    has_shop = (_scenario.shop is not None) if _scenario else True

    last_instance_scores: list[dict] = []
    if instances:
        from ..game.data import WALKTHROUGH_CHECKPOINTS
        curriculum = [WALKTHROUGH_CHECKPOINTS[i] for i in instances]
        multi_floor = True

        def _eval(p):
            last_instance_scores.clear()
            for cp in curriculum:
                configure_multi_floor_scenario(cp["floor"], cp["target"], hero_override=dict(cp["hero"]))
                s = evaluate_multi_floor(p, task_model=task_model, task_mode=task_mode)
                r = get_last_eval_result() or {}
                last_instance_scores.append({"checkpoint": cp["id"], "section": cp["section"], "floor": cp["floor"],
                                             "target": cp["target"], "score": s, "max_floor_id": r.get("max_floor_id"),
                                             "failure_reason": r.get("failure_reason")})
            return sum(x["score"] for x in last_instance_scores) / len(last_instance_scores)
        template = MOTA_MULTIFLOOR_REFLECTION_PROMPT
        scenario_name = "curriculum " + ",".join(str(cp["id"]) for cp in curriculum)
    elif multi_floor:
        configure_multi_floor_scenario(start_floor, end_floor)
        def _eval(p):
            return evaluate_multi_floor(p, task_model=task_model, task_mode=task_mode)
        template = MOTA_MULTIFLOOR_REFLECTION_PROMPT
    elif eval_mode.startswith("multistep"):
        parts = eval_mode.split("-")
        ms_chunk = int(parts[1]) if len(parts) > 1 else 5
        def _eval(p):
            return evaluate_multistep(p, task_model=task_model, task_mode=task_mode, chunk_size=ms_chunk)
        template = _build_reflection_prompt(scenario_name, bfs_ref, has_shop)
    elif eval_mode == "oneshot":
        def _eval(p):
            return evaluate_oneshot(p, task_model=task_model, task_mode=task_mode)
        template = _build_reflection_prompt(scenario_name, bfs_ref, has_shop)
    else:
        def _eval(p):
            return evaluate(p, task_model=task_model, task_mode=task_mode)
        template = _build_reflection_prompt(scenario_name, bfs_ref, has_shop)

    def _eval_with_trace(prompt: str) -> tuple[float, str]:
        cap = _StdoutCapture(mirror=True)
        old = sys.stdout
        sys.stdout = cap
        try:
            score = _eval(prompt)
        finally:
            sys.stdout = old
        return score, cap.getvalue()

    print("=" * 60)
    print("LINEAR GEPA (no Pareto / single-candidate reflection)")
    print("=" * 60)
    print(f"Floor:            {scenario_name} (has_shop={has_shop})")
    print(f"Task model:       {task_model or os.environ.get('MOTA_TASK_MODEL', 'qwen3.5-397b-a17b')} [{task_mode or 'auto'}]")
    print(f"Reflection model: {reflection_model}")
    print(f"Eval mode:        {eval_mode}")
    print(f"Max iterations:   {max_iters}")
    print()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    traces_dir = Path(__file__).resolve().parents[2] / "results" / "prompt_history"
    traces_dir.mkdir(parents=True, exist_ok=True)
    reflection_traces_path = traces_dir / f"linear_reflection_{timestamp}.jsonl"

    current = seed_prompt
    best_score = -1.0
    best_prompt = seed_prompt
    iterations: list[dict] = []

    for it in range(1, max_iters + 1):
        if stop_flag is not None and stop_flag():
            print("  [linear-gepa] stop requested — halting loop")
            break

        print(f"\n  [linear-gepa] iteration {it}/{max_iters} — evaluating ...", flush=True)
        t0 = time.time()
        score, trace = _eval_with_trace(current)
        elapsed = round(time.time() - t0, 1)

        result = get_last_eval_result() or {}
        details = result.get("details", {})
        iter_data = {
            "iteration": it,
            "prompt": current,
            "score": score,
            "elapsed_s": elapsed,
            "enemies_killed": details.get("enemies_killed", 0),
            "enemies_total": details.get("enemies_total", 0),
            "final_hp": details.get("final_hp", 0),
            "hero_atk": details.get("hero_atk", 0),
            "hero_def": details.get("hero_def", 0),
            "violations": result.get("violations", []),
            "is_seed": it == 1,
            "instance_scores": list(last_instance_scores) if instances else None,
        }
        iterations.append(iter_data)

        if score > best_score:
            best_score = score
            best_prompt = current

        print(f"  [linear-gepa] iteration {it}: score={score:.4f}  best={best_score:.4f}  ({elapsed}s)", flush=True)

        if progress_cb is not None:
            try:
                progress_cb(dict(iter_data, best_score=best_score))
            except Exception:
                pass

        if early_stop > 0 and score >= early_stop:
            print(f"  [linear-gepa] early stop: {score:.4f} >= {early_stop:.2f}")
            break
        if it == max_iters:
            break  # no reflection needed after the final evaluation

        # --- Reflection step: current prompt + game trace -> improved prompt ---
        reflection_input = template.replace("<curr_param>", current).replace("<side_info>", trace)
        t0 = time.time()
        response = reflection_lm(reflection_input)
        refl_elapsed = round(time.time() - t0, 1)
        with open(reflection_traces_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "iteration": it,
                "timestamp": datetime.datetime.now().isoformat(),
                "elapsed_s": refl_elapsed,
                "input_chars": len(reflection_input),
                "response": (response if isinstance(response, str) else str(response))[:12000],
            }, ensure_ascii=False) + "\n")

        improved = _extract_prompt(response)
        if not improved:
            print("  [linear-gepa] reflection produced no usable prompt — keeping current")
        else:
            current = improved
            print(f"  [linear-gepa] reflection #{it}: {refl_elapsed}s, new prompt = {len(current)} chars")

    # Build a candidate_history compatible with the dashboard's GEPA viewer.
    best_idx = max(range(len(iterations)), key=lambda i: iterations[i]["score"]) if iterations else 0
    candidate_history = [
        {
            "idx": i,
            "score": rec["score"],
            "parents": [i - 1] if i > 0 else [],
            "prompt": rec["prompt"],
            "is_best": (i == best_idx),
        }
        for i, rec in enumerate(iterations)
    ]

    output = {
        "format_version": 4,
        "method": "linear",
        "timestamp": timestamp,
        "experiment_label": experiment_label,
        "seed_prompt": seed_prompt,
        "best_prompt": best_prompt,
        "best_idx": best_idx,
        "best_score": best_score if best_score >= 0 else None,
        "all_scores": [rec["score"] for rec in iterations],
        "num_candidates": len(iterations),
        "candidate_history": candidate_history,
        "iterations": iterations,
        "config": {
            "max_iters": max_iters,
            "eval_mode": eval_mode,
            "reflection_model": reflection_model,
            "task_model": task_model or os.environ.get("MOTA_TASK_MODEL", ""),
            "task_mode": task_mode or os.environ.get("MOTA_TASK_MODE", ""),
            "floor": scenario_name,
            "has_shop": has_shop,
            "multi_floor": multi_floor,
            "instances": instances,
        },
        "reflection_traces_file": str(reflection_traces_path),
    }

    if save_result:
        output_dir = Path(__file__).resolve().parents[2] / "results"
        output_dir.mkdir(exist_ok=True)
        raw_label = experiment_label or "linear_gepa"
        # Reduce any path-like label (AI test floors pass a full path) to a safe token.
        raw_label = Path(raw_label).name or "linear_gepa"
        label_slug = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", raw_label)
        output_path = output_dir / f"gepa_result_{label_slug}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\n{'=' * 60}")
        print(f"Results saved to: {output_path}")
        print(f"Best score: {best_score:.4f}" if best_score >= 0 else "Best score: N/A")

    return output
