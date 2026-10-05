"""CLI for constrained GEPA on the final engine stack (see mota/optimizer/constrained_gepa.py).

    python scripts/run_constrained_gepa.py --floor simple --preset qwen3.6-35b --label cgepa_simple_35b
    python scripts/run_constrained_gepa.py --tower MT0 MT23w --preset qwen3.5-397b --rollouts 1 --label cgepa_tower_397b
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from mota.optimizer.constrained_gepa import run_constrained_gepa  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--floor")
ap.add_argument("--tower", nargs=2, metavar=("START", "END"))
ap.add_argument("--preset", default="qwen3.6-35b")
ap.add_argument("--label", required=True)
ap.add_argument("--iterations", type=int, default=4)
ap.add_argument("--rollouts", type=int, default=2)
ap.add_argument("--reflection-model")
ap.add_argument("--seed", help="seed prompt file (default: tower_basic.txt / floor_basic.txt)")
ap.add_argument("--no-validate", action="store_true",
                help="floor-specific mode: teacher may write positions/orders; only the output contract is checked")
ap.add_argument("--select", choices=("current", "best"), default="current")
ap.add_argument("--rich-trace", action="store_true")
a = ap.parse_args()
if bool(a.floor) == bool(a.tower):
    ap.error("give exactly one of --floor / --tower")
seed = a.seed or ("tower_basic.txt" if a.tower else "floor_basic.txt")
res = run_constrained_gepa(floor=a.floor, tower=tuple(a.tower) if a.tower else None, preset=a.preset,
                           seed_file=seed, label=a.label, iterations=a.iterations, rollouts=a.rollouts,
                           reflection_model=a.reflection_model, validate=not a.no_validate, select=a.select,
                           rich_trace=a.rich_trace)
print("best score", res["best_score"])
