"""
Run the 2026-09 model x floor x lookahead matrix in one command.

Every cell goes through run_reliability.py, so results land in
results/reliability/<label>.json and results/reliability/SUMMARY.md.
Cells already holding >= the requested number of runs are skipped, so the script
is resumable after a stall or a rate-limit pause.

    python scripts/run_model_matrix.py --check          # verify models + key, run nothing
    python scripts/run_model_matrix.py --repeats 5      # full matrix
    python scripts/run_model_matrix.py --repeats 3 --floors simple
    python scripts/run_model_matrix.py --dry-run        # print the plan
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# 397B first: it is the fastest per call on SAIA despite being the largest, and
# holds the best known simple-floor record, so its cells finish soonest.
PRESETS = ["qwen3.5-397b", "qwen3.6-35b", "qwen3.8-27b"]
FLOORS = ["simple", "complex"]
LOOKAHEADS = [3, 2]
# The two stored complex kills used overrides off (the evaluator's fight deferral
# contradicts the BFS-compiled fight order); simple floor kills used overrides on.
OVERRIDES_OFF = {"complex"}
OUT = ROOT / "results" / "reliability"


def label_for(floor: str, preset: str, lookahead: int) -> str:
    raw = "_raw" if floor in OVERRIDES_OFF else ""
    la = "" if lookahead == 3 else f"_la{lookahead}"
    return f"{floor}_{preset}_reactive{raw}{la}"


def existing_runs(label: str) -> int:
    path = OUT / f"{label}.json"
    if not path.exists():
        return 0
    try:
        return len(json.loads(path.read_text(encoding="utf-8")).get("runs", []))
    except Exception:
        return 0


def check_models(presets) -> bool:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from mota.optimizer.model_config import TASK_MODEL_PRESETS, check_preset_availability
    try:
        avail = check_preset_availability()
    except Exception as e:
        print(f"  API unreachable: {type(e).__name__}: {str(e)[:120]}")
        print("  -> renew SAIA_API_KEY in .env (see .env.example)")
        return False
    ok = True
    for p in presets:
        served = avail.get(p, False)
        print(f"  {p:14s} {TASK_MODEL_PRESETS[p]['model']:22s} {'served' if served else 'NOT SERVED'}")
        ok &= served
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--presets", nargs="+", default=PRESETS)
    ap.add_argument("--floors", nargs="+", default=FLOORS)
    ap.add_argument("--lookaheads", type=int, nargs="+", default=LOOKAHEADS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="Only verify key + model availability")
    args = ap.parse_args()

    print("Model availability:")
    models_ok = check_models(args.presets)
    if args.check:
        return 0 if models_ok else 1
    if not models_ok and not args.dry_run:
        print("\nAborting: requested models are not reachable.")
        return 1

    cells = [(f, p, la) for f in args.floors for p in args.presets for la in args.lookaheads]
    print(f"\n{len(cells)} cells x {args.repeats} runs\n")

    parent = None
    if not args.dry_run:
        from mota.dashboard import jobs as J
        parent = J.Job.start("matrix", f"matrix {'x'.join(map(str, (len(args.floors), len(args.presets), len(args.lookaheads))))} N={args.repeats}",
                             uses_api=False, source="cli",  # the child run_reliability jobs hold the API
                             condition={"presets": args.presets, "floors": args.floors, "lookaheads": args.lookaheads,
                                        "repeats": args.repeats})
        parent.progress(cells_total=len(cells), cells_done=0)

    t0 = time.time()
    for i, (floor, preset, la) in enumerate(cells, 1):
        label = label_for(floor, preset, la)
        have = existing_runs(label)
        todo = max(0, args.repeats - have)
        head = f"[{i}/{len(cells)}] {label}  (have {have}, need {args.repeats})"
        if todo == 0:
            print(f"{head} -> skip")
            if parent is not None:
                parent.progress(cells_done=i, current=label, skipped=True)
            continue
        cmd = [sys.executable, str(ROOT / "run_reliability.py"),
               "--floor", floor, "--preset", preset,
               "--repeats", str(todo), "--lookahead", str(la), "--append"]
        if floor in OVERRIDES_OFF:
            cmd.append("--disable-overrides")
        print(f"{head} -> {' '.join(cmd[1:])}", flush=True)
        if args.dry_run:
            continue
        parent.progress(current=label, cell_index=i)
        subprocess.run(cmd, cwd=ROOT, check=False)
        parent.progress(cells_done=i)

    if not args.dry_run:
        subprocess.run([sys.executable, str(ROOT / "run_reliability.py"), "--summary"], cwd=ROOT, check=False)
        print(f"\nmatrix done in {(time.time() - t0) / 60:.1f} min -> {OUT / 'SUMMARY.md'}")
        parent.finish("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
