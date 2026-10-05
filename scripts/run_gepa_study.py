"""GEPA study (2026-09-28): does reflective prompt optimisation improve a weak model that starts from a
core-rules-only prompt, and does the engine's lookahead/annotation layer already do that work?

Per condition (model x observation) this script
  1. runs constrained GEPA from ``seed_prompts/core_rules.txt`` on the TRAIN floors (objective = mean
     two-tier goal score; teacher gets no strategy examples; reflect-from-best selection);
  2. evaluates three prompts - core (seed), gepa (best evolved), basic (hand-written floor_basic.txt) -
     on TRAIN + held-out TEST floors, N=1 each at T=0, interleaved per floor (paired design);
  3. writes results/gepa_study/<label>.json incrementally and the evolved prompt to
     seed_prompts/gepa_study/<label>_best.txt (provenance only, never a default).

Observation (env is set here, before the engine is imported):
  full = final stack: LOOKAHEAD_DEPTH=3, history off, MOTA_ORDER_TWO_SIDED=1, MOTA_FIGHT_KEY_FLOOD=1
  bare = the same engine and assists, but MOTA_BARE_OBS=1: stats, items, boss stats, reachable actions
         with the exact damage; no lookahead tree / effCost / tags / tips / budgets / ORDER / key lines.

    python scripts/run_gepa_study.py --preset llama-3.1-8b --obs full --label gs_llama8b_full
    python scripts/run_gepa_study.py --preset qwen3.5-397b --obs bare --label gs_397b_bare --no-gepa --prompts core basic --train simple --test "" --repeat 3
"""
import argparse
import datetime
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

ap = argparse.ArgumentParser()
ap.add_argument("--preset", required=True)
ap.add_argument("--obs", choices=("full", "bare"), required=True)
ap.add_argument("--label", required=True)
ap.add_argument("--train", default="simple,gen01,gen02")
ap.add_argument("--test", default=",".join(f"gen{i:02d}" for i in range(3, 16)))
ap.add_argument("--iterations", type=int, default=6)
ap.add_argument("--rollouts", type=int, default=1)
ap.add_argument("--repeat", type=int, default=1, help="episodes per (prompt, floor) in the evaluation")
ap.add_argument("--prompts", nargs="+", default=["core", "gepa", "basic"])
ap.add_argument("--no-gepa", action="store_true", help="skip optimisation (evaluate core/basic only)")
ap.add_argument("--gepa-from", help="reuse the best prompt of an existing gepa_result_<label>.json")
ap.add_argument("--thinking-max-tokens", default="16384")
ap.add_argument("--reflection-model", default="qwen3.5-397b-a17b", help="GEPA teacher (SAIA model id)")
ap.add_argument("--rich-trace", action="store_true", help="teacher sees the options offered at each decision")
ap.add_argument("--seed-file", default="core_rules.txt", help="GEPA seed (seed_prompts/); evaluated as arm 'seed'")
ap.add_argument("--loop", choices=("oneplusone", "pareto"), default="oneplusone",
                help="(1+1) loop (--iterations evaluations) or Pareto loop (--iterations candidates, last = merge)")
a = ap.parse_args()

os.environ.update({"CONVERSATION_HISTORY_TURNS": "0", "MOTA_ORDER_TWO_SIDED": "1", "MOTA_FIGHT_KEY_FLOOD": "1",
                   "LOOKAHEAD_DEPTH": "3", "MOTA_EVAL_TEMPERATURE": "0.0",
                   "THINKING_MAX_TOKENS": a.thinking_max_tokens})
if a.obs == "bare":
    os.environ["MOTA_BARE_OBS"] = "1"
else:
    os.environ.pop("MOTA_BARE_OBS", None)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from mota.harness import reliability as H  # noqa: E402
from mota.optimizer.constrained_gepa import run_constrained_gepa, run_pareto_loop  # noqa: E402
from mota.optimizer.model_config import resolve_task_config  # noqa: E402


def floor_arg(name: str) -> str:
    return name if name in ("simple", "complex") else str((ROOT / "data" / "floors" / "gen" / f"{name}.txt").resolve())


train = [f for f in a.train.split(",") if f]
test = [f for f in a.test.split(",") if f and f != "none"]
cfg = resolve_task_config(task_preset=a.preset)
out_dir = ROOT / "results" / "gepa_study"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"{a.label}.json"
result = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
result.update({"label": a.label, "preset": a.preset, "task_model": cfg["task_model"], "task_mode": cfg["task_mode"],
               "obs": a.obs, "train": train, "test": test, "repeat": a.repeat,
               "env": {k: os.environ.get(k) for k in ("CONVERSATION_HISTORY_TURNS", "MOTA_ORDER_TWO_SIDED",
                                                      "MOTA_FIGHT_KEY_FLOOD", "LOOKAHEAD_DEPTH", "MOTA_BARE_OBS",
                                                      "MOTA_EVAL_TEMPERATURE", "THINKING_MAX_TOKENS",
                                                      "MOTA_DISABLE_OVERRIDES", "MOTA_SUPPRESS_HINTS")},
               "overrides": "mechanical-only (dead-end / unwinnable / lethal) + auto-collect + auto-fight-0-HP"})
result.setdefault("episodes", [])
result.setdefault("started", datetime.datetime.now().isoformat())


def save():
    result["updated"] = datetime.datetime.now().isoformat()
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


prompts = {"core": (ROOT / "seed_prompts" / "core_rules.txt").read_text(encoding="utf-8"),
           "basic": (ROOT / "seed_prompts" / "floor_basic.txt").read_text(encoding="utf-8"),
           "seed": (ROOT / "seed_prompts" / a.seed_file).read_text(encoding="utf-8")}

# 1. optimisation
if "gepa" in a.prompts and not a.no_gepa:
    if a.gepa_from:
        g = json.loads((ROOT / "results" / "gepa" / f"gepa_result_{a.gepa_from}.json").read_text(encoding="utf-8"))
    elif result.get("gepa", {}).get("finished"):
        g = json.loads((ROOT / "results" / "gepa" / f"gepa_result_{a.label}.json").read_text(encoding="utf-8"))
    else:
        print(f"[{a.label}] {a.loop} loop on {train} ({a.iterations} evaluations x {a.rollouts} rollouts)", flush=True)
        if a.loop == "pareto":
            g = run_pareto_loop(floors=[floor_arg(f) for f in train], preset=a.preset, seed_file=a.seed_file,
                                label=a.label, candidates=a.iterations, rollouts=a.rollouts, bare=a.obs == "bare",
                                reflection_model=a.reflection_model, rich_trace=a.rich_trace)
        else:
            g = run_constrained_gepa(floor=None, floors=[floor_arg(f) for f in train], tower=None, preset=a.preset,
                                     seed_file=a.seed_file, label=a.label, iterations=a.iterations,
                                     rollouts=a.rollouts, bare=a.obs == "bare", strategy_examples=False,
                                     select="best", reflection_model=a.reflection_model, rich_trace=a.rich_trace)
    prompts["gepa"] = g["best_prompt"]
    steps = g.get("iterations") or g.get("population") or []
    result["gepa"] = {"result_file": f"results/gepa/gepa_result_{a.gepa_from or a.label}.json", "loop": a.loop,
                      "reflection_model": g.get("reflection_model"), "rich_trace": g.get("rich_trace", False),
                      "best_score": g["best_score"], "trajectory": [it["score"] for it in steps],
                      "accepted": [it.get("accepted", True) for it in steps],
                      "best_is_seed": g["best_prompt"].strip() == prompts["seed"].strip(),
                      "finished": g.get("finished") or datetime.datetime.now().isoformat()}
    pdir = ROOT / "seed_prompts" / "gepa_study"
    pdir.mkdir(exist_ok=True)
    (pdir / f"{a.label}_best.txt").write_text(g["best_prompt"], encoding="utf-8")
    save()
    print(f"[{a.label}] GEPA done: trajectory {result['gepa']['trajectory']} best {g['best_score']:.4f}"
          f"{' (= seed)' if result['gepa']['best_is_seed'] else ''}", flush=True)

# 2. evaluation, paired per floor
done = {(e["prompt"], e["floor"], e["rep"]) for e in result["episodes"]}
for fl in train + test:
    for rep in range(a.repeat):
        for pname in a.prompts:
            if pname not in prompts or (pname, fl, rep) in done:
                continue
            r = H.run_once(floor_arg(fl), prompts[pname], "reactive", cfg["task_model"], cfg["task_mode"])
            rec = {"prompt": pname, "floor": fl, "split": "train" if fl in train else "test", "rep": rep,
                   **{k: r.get(k) for k in ("goal_score", "success", "hp_ratio", "died", "final_hp", "hero_atk",
                                            "hero_def", "enemies_killed", "enemies_total", "llm_calls", "parse_errors",
                                            "forced_turns", "lethal_only_stop", "run_log", "elapsed_s")}}
            result["episodes"].append(rec)
            save()
            print(f"  {fl:7s} {pname:5s} rep{rep}: goal={rec['goal_score']} success={rec['success']} "
                  f"hp={rec['final_hp']} died={rec['died']} calls={rec['llm_calls']} ({rec['elapsed_s']} s)", flush=True)

# 3. summary
summ = {}
for split in ("train", "test", "all"):
    for pname in a.prompts:
        eps = [e for e in result["episodes"] if e["prompt"] == pname and (split == "all" or e["split"] == split)]
        if eps:
            summ[f"{split}/{pname}"] = {"n": len(eps), "success": sum(bool(e["success"]) for e in eps),
                                        "deaths": sum(bool(e["died"]) for e in eps),
                                        "goal_mean": round(statistics.fmean(e["goal_score"] or 0 for e in eps), 4)}
result["summary"] = summ
result["finished"] = datetime.datetime.now().isoformat()
save()
for k, v in summ.items():
    print(f"{k:12s} {v}")
