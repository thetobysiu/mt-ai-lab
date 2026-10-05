"""
Batch experiment runner for thesis experiments E1-E6.

All experiments use temperature=0.0 (deterministic), so N=1 per condition.
Results are saved as JSON to results/experiments/.

Usage:
    python -m mota.optimizer.run_experiments --experiment E1
    python -m mota.optimizer.run_experiments --experiment E2
    python -m mota.optimizer.run_experiments --experiment E5
    python -m mota.optimizer.run_experiments --experiment E6
    python -m mota.optimizer.run_experiments --experiment all
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Load .env from the repository root
try:
    from dotenv import load_dotenv
    _root_tmp = Path(__file__).resolve().parents[2]
    for env_dir in [_root_tmp]:
        env_file = env_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            break
except ImportError:
    pass

# Ensure project root on path
_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))

_RESULTS_DIR = _root / "results" / "experiments"
from mota.paths import FLOORS_24 as _FLOORS_DIR, SINGLE_FLOORS  # noqa: E402


def _save_result(experiment: str, condition: str, result: dict):
    """Save a single experiment condition result to JSON."""
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{experiment}_{condition}_{ts}.json"
    path = _RESULTS_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Saved: {path.name}")
    return path


def _load_gepa_v3_prompt() -> str:
    """Load the GEPA-optimized v3 prompt from results/gepa_result.json."""
    gepa_path = _root / "results" / "gepa_result.json"
    if not gepa_path.exists():
        raise FileNotFoundError(
            f"GEPA result not found: {gepa_path}\n"
            "Run GEPA optimization first: python -m mota.optimizer.run_gepa"
        )
    with open(gepa_path, encoding="utf-8") as f:
        data = json.load(f)
    return data["best_prompt"]


def _run_condition(
    label: str,
    mode: str,
    prompt: str | None = None,
    task_model: str | None = None,
    task_mode: str | None = None,
    floor_path: str | None = None,
) -> dict:
    """Run a single evaluation condition and return the full result dict."""
    from .evaluator import (
        configure_scenario, evaluate, evaluate_oneshot, evaluate_multistep,
        evaluate_heuristic_only, get_last_eval_result,
    )

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    # Configure scenario (None = default MT3)
    desc = configure_scenario(floor_path)
    print(f"  Scenario: {desc}")

    if mode == "heuristic":
        result = evaluate_heuristic_only()
        result["mode"] = "heuristic"
    elif mode == "reactive":
        score = evaluate(prompt, task_model=task_model, task_mode=task_mode)
        result = get_last_eval_result()
        result["mode"] = "reactive"
    elif mode == "oneshot":
        score = evaluate_oneshot(prompt, task_model=task_model, task_mode=task_mode)
        result = get_last_eval_result()
        result["mode"] = "oneshot"
    elif mode.startswith("multistep"):
        # mode can be "multistep" (default 5) or "multistep-N" for chunk size N
        chunk = 5
        if "-" in mode:
            try:
                chunk = int(mode.split("-", 1)[1])
            except ValueError:
                pass
        score = evaluate_multistep(prompt, task_model=task_model, task_mode=task_mode, chunk_size=chunk)
        result = get_last_eval_result()
        result["mode"] = mode
    else:
        raise ValueError(f"Unknown mode: {mode}")

    result["label"] = label
    result["task_model"] = task_model or os.environ.get("MOTA_TASK_MODEL", "qwen3.5-397b-a17b")
    result["task_mode"] = task_mode or "thinking"
    result["timestamp"] = datetime.now(timezone.utc).isoformat()

    print(f"  Score: {result['total']:.4f}")
    print(f"  Components: C={result.get('completion',0):.3f} "
          f"H={result.get('hp_score',0):.3f} "
          f"E={result.get('efficiency',0):.3f} "
          f"S={result.get('shop_score',0):.3f} "
          f"V={result.get('violation_score',0):.3f}")
    if result.get("tracking"):
        t = result["tracking"]
        llm_calls = t.get('llm_calls', 0)
        elapsed = t.get('elapsed_seconds', 0)
        per_call = round(elapsed / llm_calls, 2) if llm_calls else 0
        t["seconds_per_call"] = per_call
        print(f"  LLM calls: {llm_calls}, "
              f"Fallbacks: {t.get('heuristic_fallbacks', 0)}, "
              f"Parse errors: {t.get('parse_errors', 0)}, "
              f"Time: {elapsed}s ({per_call}s/call)")
    return result


def run_e1():
    """E1: Baseline evaluation — heuristic + Arch A seed v1."""
    from .seed_prompt import SEED_PROMPT

    print("\n" + "=" * 60)
    print("  EXPERIMENT E1: Baseline Evaluation")
    print("=" * 60)

    results = {}

    # Heuristic baseline
    r = _run_condition("E1-heuristic", mode="heuristic")
    results["heuristic"] = r
    _save_result("E1", "heuristic", r)

    # Arch A + seed prompt v1
    r = _run_condition("E1-archA-seed-v1", mode="reactive", prompt=SEED_PROMPT)
    results["archA_v1"] = r
    _save_result("E1", "archA_seed_v1", r)

    _print_summary("E1", results)
    return results


def run_e2():
    """E2: Architecture comparison — Arch A (GEPA v3), Arch B (oneshot v1), heuristic."""
    from .seed_prompt import SEED_PROMPT

    print("\n" + "=" * 60)
    print("  EXPERIMENT E2: Architecture Comparison")
    print("=" * 60)

    v3_prompt = _load_gepa_v3_prompt()
    results = {}

    # Arch A + GEPA v3 prompt (reactive, multi-call)
    r = _run_condition("E2-archA-gepa-v3", mode="reactive", prompt=v3_prompt)
    results["archA_v3"] = r
    _save_result("E2", "archA_gepa_v3", r)

    # Arch B + seed prompt v1 (oneshot, single call)
    r = _run_condition("E2-archB-oneshot-v1", mode="oneshot", prompt=SEED_PROMPT)
    results["archB_v1"] = r
    _save_result("E2", "archB_oneshot_v1", r)

    _print_summary("E2", results)
    return results


def run_e5():
    """E5: Model comparison — same prompt, different models."""
    from .seed_prompt import SEED_PROMPT

    print("\n" + "=" * 60)
    print("  EXPERIMENT E5: Model Comparison")
    print("=" * 60)

    models = [
        ("qwen3-30b", "qwen3-30b-a3b-thinking-2507", "thinking"),
        ("deepseek-r1-70b", "deepseek-r1-distill-llama-70b", "thinking"),
        ("qwen3-235b", "qwen3-235b-a22b", "thinking"),
    ]
    results = {}

    for model_label, model_name, mode in models:
        try:
            r = _run_condition(
                f"E5-{model_label}",
                mode="reactive",
                prompt=SEED_PROMPT,
                task_model=model_name,
                task_mode=mode,
            )
            results[model_label] = r
            _save_result("E5", model_label, r)
        except Exception as e:
            print(f"  ERROR running {model_label}: {e}")
            results[model_label] = {"error": str(e)}
            _save_result("E5", f"{model_label}_error", {"error": str(e)})

    _print_summary("E5", results)
    return results


def run_e6():
    """E6: Transfer evaluation — GEPA v3 prompt on unseen floors MT0-MT4."""
    from .seed_prompt import SEED_PROMPT

    print("\n" + "=" * 60)
    print("  EXPERIMENT E6: Transfer Evaluation")
    print("=" * 60)

    v3_prompt = _load_gepa_v3_prompt()
    floors = ["MT0", "MT1", "MT2", "MT3", "MT4"]
    results = {}

    for floor_id in floors:
        floor_file = str(_FLOORS_DIR / f"{floor_id}.js")
        if not Path(floor_file).exists():
            print(f"  SKIP {floor_id}: floor file not found")
            continue

        # Heuristic baseline for this floor
        try:
            r = _run_condition(
                f"E6-{floor_id}-heuristic",
                mode="heuristic",
                floor_path=floor_file,
            )
            results[f"{floor_id}_heuristic"] = r
            _save_result("E6", f"{floor_id}_heuristic", r)
        except Exception as e:
            print(f"  ERROR heuristic {floor_id}: {e}")
            results[f"{floor_id}_heuristic"] = {"error": str(e)}

        # GEPA v3 prompt on this floor
        try:
            r = _run_condition(
                f"E6-{floor_id}-gepa-v3",
                mode="reactive",
                prompt=v3_prompt,
                floor_path=floor_file,
            )
            results[f"{floor_id}_v3"] = r
            _save_result("E6", f"{floor_id}_v3", r)
        except Exception as e:
            print(f"  ERROR v3 {floor_id}: {e}")
            results[f"{floor_id}_v3"] = {"error": str(e)}

    _print_summary("E6", results)
    return results


def run_e7():
    """E7: Qwen3.5 Model Benchmark — compare new SAIA models with GEPA v3 prompt on MT3."""
    print("\n" + "=" * 60)
    print("  EXPERIMENT E7: Qwen3.5 Model Benchmark")
    print("=" * 60)

    v3_prompt = _load_gepa_v3_prompt()
    models = [
        # Baseline (old default)
        ("qwen3-30b", "qwen3-30b-a3b-thinking-2507", "thinking"),
        # Qwen 3.5 family (27b-dense removed: 20.4s/call, use 397b-moe at 5.9s/call)
        ("qwen3.5-35b-moe", "qwen3.5-35b-a3b", "thinking"),
        ("qwen3.5-122b-moe", "qwen3.5-122b-a10b", "thinking"),
        ("qwen3.5-397b-moe", "qwen3.5-397b-a17b", "thinking"),
    ]
    results = {}

    # Heuristic baseline
    r = _run_condition("E7-heuristic", mode="heuristic")
    results["heuristic"] = r
    _save_result("E7", "heuristic", r)

    for model_label, model_name, mode in models:
        try:
            r = _run_condition(
                f"E7-{model_label}",
                mode="reactive",
                prompt=v3_prompt,
                task_model=model_name,
                task_mode=mode,
            )
            results[model_label] = r
            _save_result("E7", model_label, r)
        except Exception as e:
            print(f"  ERROR running {model_label}: {e}")
            results[model_label] = {"error": str(e)}
            _save_result("E7", f"{model_label}_error", {"error": str(e)})

    _print_summary("E7", results)

    # Additional latency comparison table
    print(f"\n  {'Model':<25s} {'Score':>7s} {'LLM Calls':>10s} {'Time (s)':>10s} {'s/call':>8s}")
    print(f"  {'-'*25} {'-'*7} {'-'*10} {'-'*10} {'-'*8}")
    for label, r in results.items():
        if "error" in r or label == "heuristic":
            continue
        t = r.get("tracking", {})
        calls = t.get("llm_calls", 0)
        elapsed = t.get("elapsed_seconds", 0)
        per_call = elapsed / max(1, calls)
        print(f"  {label:<25s} {r['total']:7.4f} {calls:10d} {elapsed:10.1f} {per_call:8.1f}")

    return results


_AI_TEST_DIR = SINGLE_FLOORS


def run_e8():
    """E8: 单层-最简单 benchmark — Qwen3.5 models on the simplest AI test floor."""
    print("\n" + "=" * 60)
    print("  EXPERIMENT E8: 单層-最簡單 (Simplest Floor) Benchmark")
    print("=" * 60)

    floor_path = str(_AI_TEST_DIR / "单层-最简单.txt")
    v3_prompt = _load_gepa_v3_prompt()
    models = [
        # Qwen 3.5 family (27b-dense excluded: too slow)
        ("qwen3.5-35b-moe", "qwen3.5-35b-a3b", "thinking"),
        ("qwen3.5-122b-moe", "qwen3.5-122b-a10b", "thinking"),
        ("qwen3.5-397b-moe", "qwen3.5-397b-a17b", "thinking"),
    ]
    results = {}

    # Heuristic baseline
    r = _run_condition("E8-heuristic", mode="heuristic", floor_path=floor_path)
    results["heuristic"] = r
    _save_result("E8", "heuristic", r)

    for model_label, model_name, mode in models:
        try:
            r = _run_condition(
                f"E8-{model_label}",
                mode="reactive",
                prompt=v3_prompt,
                task_model=model_name,
                task_mode=mode,
                floor_path=floor_path,
            )
            results[model_label] = r
            _save_result("E8", model_label, r)
        except Exception as e:
            print(f"  ERROR running {model_label}: {e}")
            results[model_label] = {"error": str(e)}
            _save_result("E8", f"{model_label}_error", {"error": str(e)})

    _print_summary("E8", results)
    return results


def run_e9():
    """E9: Long-Horizon Planning — compare reactive vs chunked (5-step, 10-step) vs one-shot."""
    print("\n" + "=" * 60)
    print("  EXPERIMENT E9: Long-Horizon Planning Comparison")
    print("=" * 60)

    v3_prompt = _load_gepa_v3_prompt()
    default_model = os.environ.get("MOTA_TASK_MODEL", "qwen3.5-397b-a17b")
    results = {}

    # Heuristic baseline
    r = _run_condition("E9-heuristic", mode="heuristic")
    results["heuristic"] = r
    _save_result("E9", "heuristic", r)

    # Reactive (1 action per call) — Architecture A
    r = _run_condition(
        "E9-reactive",
        mode="reactive",
        prompt=v3_prompt,
        task_model=default_model,
        task_mode="thinking",
    )
    results["reactive"] = r
    _save_result("E9", "reactive", r)

    # Chunked planning — 5-step chunks
    r = _run_condition(
        "E9-multistep-5",
        mode="multistep-5",
        prompt=v3_prompt,
        task_model=default_model,
        task_mode="thinking",
    )
    results["multistep_5"] = r
    _save_result("E9", "multistep_5", r)

    # Chunked planning — 10-step chunks
    r = _run_condition(
        "E9-multistep-10",
        mode="multistep-10",
        prompt=v3_prompt,
        task_model=default_model,
        task_mode="thinking",
    )
    results["multistep_10"] = r
    _save_result("E9", "multistep_10", r)

    # Chunked planning — 99 (effectively whole-floor with re-plan)
    r = _run_condition(
        "E9-multistep-99",
        mode="multistep-99",
        prompt=v3_prompt,
        task_model=default_model,
        task_mode="thinking",
    )
    results["multistep_99"] = r
    _save_result("E9", "multistep_99", r)

    # One-shot (Architecture B — coordinate plan)
    r = _run_condition(
        "E9-oneshot",
        mode="oneshot",
        prompt=v3_prompt,
        task_model=default_model,
        task_mode="thinking",
    )
    results["oneshot"] = r
    _save_result("E9", "oneshot", r)

    _print_summary("E9", results)

    # Planning efficiency table
    print(f"\n  {'Mode':<20s} {'Score':>7s} {'LLM Calls':>10s} {'Plan Acts':>10s} {'Time (s)':>10s} {'s/call':>8s}")
    print(f"  {'-'*20} {'-'*7} {'-'*10} {'-'*10} {'-'*10} {'-'*8}")
    for label, r in results.items():
        if "error" in r or label == "heuristic":
            continue
        t = r.get("tracking", {})
        calls = t.get("llm_calls", 0)
        plan_acts = t.get("plan_actions_executed", "—")
        elapsed = t.get("elapsed_seconds", 0)
        per_call = elapsed / max(1, calls)
        print(f"  {label:<20s} {r['total']:7.4f} {calls:10d} {str(plan_acts):>10s} {elapsed:10.1f} {per_call:8.1f}")

    return results


def _print_summary(experiment, results):
    print(f"\n{'='*60}")
    print(f"  {experiment} SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Condition':<30s} {'Score':>7s} {'C':>6s} {'H':>6s} {'E':>6s} {'S':>6s} {'V':>6s}")
    print(f"  {'-'*30} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
    for label, r in results.items():
        if "error" in r:
            print(f"  {label:<30s} ERROR: {r['error'][:40]}")
            continue
        print(f"  {label:<30s} {r['total']:7.4f} "
              f"{r.get('completion',0):6.3f} "
              f"{r.get('hp_score',0):6.3f} "
              f"{r.get('efficiency',0):6.3f} "
              f"{r.get('shop_score',0):6.3f} "
              f"{r.get('violation_score',0):6.3f}")


def main():
    parser = argparse.ArgumentParser(description="Run thesis experiments")
    parser.add_argument(
        "--experiment", "-e",
        choices=["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "all"],
        required=True,
        help="Which experiment to run",
    )
    args = parser.parse_args()

    start = time.time()
    exp = args.experiment.upper()

    if exp in ("E1", "ALL"):
        run_e1()
    if exp in ("E2", "ALL"):
        run_e2()
    if exp in ("E5", "ALL"):
        run_e5()
    if exp in ("E6", "ALL"):
        run_e6()
    if exp in ("E7", "ALL"):
        run_e7()
    if exp in ("E8", "ALL"):
        run_e8()
    if exp in ("E9", "ALL"):
        run_e9()
    if exp in ("E3", "E4"):
        print(f"\n{exp} requires GEPA optimization run. Use:")
        print("  python -m mota.optimizer.run_gepa")
        print("Then analyze results with the component breakdown.")

    elapsed = time.time() - start
    print(f"\nTotal time: {elapsed:.0f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    main()
