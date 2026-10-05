"""
Deterministic ablation: how lookahead depth changes the action-tree prompt.

No API calls — measures prompt size and via-chain count at the first multi-way
decision of a floor, so the cost side of the lookahead trade-off can be reported
independently of any model run.

    python scripts/lookahead_prompt_ablation.py [--floor simple] [--depths 1 2 3 4]
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def first_decision_prompt(floor: str, depth: int):
    os.environ["LOOKAHEAD_DEPTH"] = str(depth)
    import mota.optimizer.evaluator as ev
    importlib.reload(ev)
    ev.configure_scenario(str(ROOT / "data" / "floors" / f"{floor}.txt"))
    state = ev._create_state()
    while True:
        actions = state.get_actions()
        if len(actions) >= 3:
            break
        state.apply_action(actions[0])
    return state, actions, state.format_actions(actions)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", default="simple")
    ap.add_argument("--depths", type=int, nargs="+", default=[1, 2, 3, 4])
    args = ap.parse_args()

    print(f"Floor: {args.floor} — action-tree prompt at the first multi-way decision\n")
    print(f"{'depth':>5} {'engine':>7} {'chars':>7} {'lines':>6} {'via-chains':>11} {'~tokens':>8}")
    rows = []
    for d in args.depths:
        state, actions, text = first_decision_prompt(args.floor, d)
        chars = len(text)
        rows.append((d, state.lookahead_depth, chars, text.count("\n") + 1, text.count("via ["), chars // 4))
        print(f"{rows[-1][0]:>5} {rows[-1][1]:>7} {rows[-1][2]:>7} {rows[-1][3]:>6} {rows[-1][4]:>11} {rows[-1][5]:>8}")

    base = next((r for r in rows if r[0] == 3), rows[-1])
    print(f"\nRelative to depth {base[0]}:")
    for r in rows:
        print(f"  depth {r[0]}: {r[2] / base[2]:.2f}x chars, {r[4]} via-chains (vs {base[4]})")
    print(f"\nTurn {state.turn}, {len(actions)} legal actions.")


if __name__ == "__main__":
    main()
