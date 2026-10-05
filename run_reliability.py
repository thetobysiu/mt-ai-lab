"""
Repeat-run reliability harness (CLI).

Runs the same (floor, prompt, model, mode) condition N times and reports
success rate with a Wilson 95% CI, mean +/- sd score, HP and parse-error rate.
Replaces single-run headline numbers with distributions. The logic lives in
mota/harness/reliability.py and is shared with the dashboard; every run also writes a job
manifest to logs/jobs/ so it is visible live in the dashboard's Live view.

Usage:
    python run_reliability.py --floor simple --repeats 10
    python run_reliability.py --floor complex --preset qwen3.6-35b --disable-overrides --repeats 5
    python run_reliability.py --floor simple --preset qwen3.8-27b --lookahead 2 --repeats 5
    python run_reliability.py --floor MT3 --mode multistep-5 --repeats 5
    python run_reliability.py --floor MT3 --disable-overrides --repeats 5
    python run_reliability.py --floor simple --heuristic
    python run_reliability.py --tower --start MT0 --end MT23w --heuristic
    python run_reliability.py --tower --start MT0 --end MT23w --preset qwen3.5-397b --max-turns 600
    python run_reliability.py --summary                # regenerate results/reliability/SUMMARY.md

Outputs:
    results/reliability/<label>.json      per-run records + aggregate
    results/reliability/SUMMARY.md        one row per label (regenerated each run)
    logs/jobs/<job_id>.json               live job manifest (dashboard)
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# Re-exported for scripts/tests that import run_reliability directly.
from mota.harness.reliability import (  # noqa: E402,F401
    OUT_DIR, SEEDS, DEFAULT_PROMPTS, BOSS_FLOORS, RunCondition, wilson_ci, aggregate,
    write_summary, load_prompt, run_batch, resolve, run_once as _run_once, run_tower_once as _run_tower_once,
    load_existing as _load_existing,
)


def _banner(msg: str):
    print("\n" + "=" * 72 + f"\n{msg}\n" + "=" * 72, flush=True)


def main():
    from mota.optimizer.model_config import TASK_MODEL_PRESETS

    p = argparse.ArgumentParser(description="MOTA repeat-run reliability harness")
    p.add_argument("--floor", help=f"Single floor: {', '.join(sorted(DEFAULT_PROMPTS))} or a .txt floor file "
                                     "(e.g. data/floors/gen/gen01.txt)")
    p.add_argument("--tower", action="store_true", help="Multi-floor tower run (use --start/--end)")
    p.add_argument("--start", default="MT0")
    # Floor 23 is a three-way split (MT23w/e/s); 'MT23' itself does not exist in data.js.
    p.add_argument("--end", default="MT23w")
    p.add_argument("--max-turns", type=int, default=600, help="Total turn cap for tower runs")
    p.add_argument("--checkpoint", type=int,
                   help="Tower segment: start at walkthrough checkpoint N (floor + exact stats from "
                        "data.WALKTHROUGH_CHECKPOINTS); --end defaults to checkpoint N+1's floor")
    p.add_argument("--prompt-file", help="Prompt .txt (path or name in seed_prompts/); default = proven per-floor prompt")
    p.add_argument("--preset", default="qwen3.5-397b", choices=sorted(TASK_MODEL_PRESETS))
    p.add_argument("--task-model", help="Explicit model ID override")
    p.add_argument("--task-mode", choices=["auto", "instruct", "thinking"])
    p.add_argument("--mode", default="reactive", help="reactive | oneshot | multistep-N")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--heuristic", action="store_true", help="No LLM; deterministic baseline (forces repeats=1)")
    p.add_argument("--disable-overrides", action="store_true", help="Set MOTA_DISABLE_OVERRIDES=1")
    p.add_argument("--lookahead", type=int, help="Lookahead tree depth in the action prompt (engine default 3)")
    p.add_argument("--no-structured-output", action="store_true",
                   help="Disable the constrained-decoding repair call on unparseable answers")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--label", help="Output label (default derived from condition)")
    p.add_argument("--append", action="store_true", help="Append to an existing label file instead of overwriting")
    p.add_argument("--summary", action="store_true", help="Only regenerate SUMMARY.md and exit")
    p.add_argument("--job-id", help="Adopt an existing job manifest (used by queue runners)")
    p.add_argument("--force", action="store_true", help="Start even if another API job is running (not recommended)")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.summary:
        print(f"wrote {write_summary()}")
        return
    if not args.floor and not args.tower:
        raise SystemExit("Specify --floor <id> or --tower")
    if args.floor and args.floor not in DEFAULT_PROMPTS and not Path(args.floor).exists():
        raise SystemExit(f"--floor {args.floor}: not a known floor id and no such file")

    preset = TASK_MODEL_PRESETS[args.preset]
    if preset.get("deprecated") and not args.task_model and not args.heuristic:
        print(f"WARNING: preset '{args.preset}' is marked deprecated on SAIA; the call will likely fail.", flush=True)

    if args.tower:
        prompt, prompt_name = (None, "none") if args.heuristic else load_prompt(f"{args.start}-{args.end}", args.prompt_file)
    else:
        prompt, prompt_name = (None, "none") if args.heuristic else load_prompt(
            args.floor, args.prompt_file or DEFAULT_PROMPTS.get(args.floor))

    cond = RunCondition(
        floor=args.floor, tower=args.tower, start=args.start, end=args.end, max_turns=args.max_turns,
        checkpoint=args.checkpoint, prompt=prompt, prompt_name=prompt_name, mode=args.mode,
        preset=args.preset, task_model=args.task_model, task_mode=args.task_mode, repeats=args.repeats,
        disable_overrides=args.disable_overrides, lookahead=args.lookahead,
        structured_output=not args.no_structured_output, temperature=args.temperature,
        thinking_max_tokens=int(os.environ["THINKING_MAX_TOKENS"]) if os.environ.get("THINKING_MAX_TOKENS") else None,
        label=args.label, append=args.append, source="cli",
    )

    from mota.dashboard import jobs as J
    job = None
    if args.job_id:
        job = J.Job.load(args.job_id)
        if job is not None:
            job.adopt_pid(os.getpid())
            job.update(status="running", argv=sys.argv)
    if not args.heuristic and not args.force:
        busy = J.api_busy(exclude_job_id=job.job_id if job else None)
        if busy:
            for b in busy:
                print(f"  API busy: {b['job_id']} {b['label']} (pid {b['pid']})", flush=True)
            if J.exclusive_api():
                raise SystemExit("Another API job is running and MOTA_EXCLUSIVE_API=1 (use --force to override).")
            print("  (running concurrently — set MOTA_EXCLUSIVE_API=1 to forbid this)", flush=True)

    r = resolve(dataclasses.replace(cond))
    _banner(f"RELIABILITY {r.label} | {r.floor_desc} | prompt={prompt_name} | mode={args.mode} | "
            f"model={r.task_model} [{r.task_mode}] | repeats={1 if args.heuristic else args.repeats} | "
            f"lookahead={r.lookahead} | overrides={'off' if args.disable_overrides else 'on'}{r.checkpoint_desc}")

    payload = run_batch(cond, job=job, log=lambda m: _banner(m) if m.startswith("[") else print(m, flush=True),
                        verbose_tower=True)
    runs = payload.get("runs") or []
    if not runs:
        return
    a = payload["aggregate"]
    lo, hi = a["success_ci95"]
    _banner(f"AGGREGATE {payload['label']}: success {a['successes']}/{a['n']} = {a['success_rate']:.2f} "
            f"[{lo:.2f}, {hi:.2f}]  score={a['score_mean']}±{a['score_sd']}  HP={a['final_hp_mean']}  "
            f"parse_err={a['parse_error_rate']}")
    print(f"  saved -> {OUT_DIR / (payload['label'] + '.json')}")
    print(f"  summary -> {OUT_DIR / 'SUMMARY.md'}", flush=True)


if __name__ == "__main__":
    main()
