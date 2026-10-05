"""Model latency + answer quality on a REAL decision prompt (not a ping).

Takes the system prompt and one mid-game user message (state + numbered actions with lookahead
annotations) from a stored run log, sends it to each preset through the evaluator's own _call_llm
(same max_tokens / thinking settings as an experiment), and reports wall time, reasoning length,
whether the answer parsed, and which action was chosen. Runs presets concurrently (one thread each).

    python scripts/bench_decision_latency.py --presets qwen3.5-397b qwen3.6-35b qwen3.8-27b glm-5.3-flash --repeats 2
    python scripts/bench_decision_latency.py --log logs/runs/<file>.json --turn 15
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from mota.optimizer import evaluator as ev  # noqa: E402
from mota.optimizer.model_config import TASK_MODEL_PRESETS  # noqa: E402

DEFAULT_LOG = ROOT / "logs" / "runs" / "20260923_165759_089758_simple_llm.json"


def pick_turn(log: Path, turn: int | None):
    d = json.loads(log.read_text(encoding="utf-8"))
    turns = [e for e in d["turns"] if e.get("type") == "turn" and not e.get("forced") and e.get("actions_text")]
    if turn is not None:
        e = next((t for t in turns if t.get("turn") == turn), None)
        if e is None:
            raise SystemExit(f"turn {turn} not found / not an LLM turn")
    else:  # the LLM turn with the most options
        e = max(turns, key=lambda t: t["actions_text"].count("\n  "))
    system = d.get("runtime_prompt") or d.get("prompt") or ""
    n_opts = len(re.findall(r"^\s*\d+\. \[", e["actions_text"], re.M))
    return system, e, n_opts


def one_call(preset: str, system: str, user: str, thinking_cap: int) -> dict:
    p = TASK_MODEL_PRESETS[preset]
    import os
    os.environ["THINKING_MAX_TOKENS"] = str(thinking_cap)
    t0 = time.time()
    err = None
    try:
        resp = ev._call_llm(system, user, task_model=p["model"], task_mode=p["mode"], temperature=0.0)
    except Exception as e:  # report, don't abort the table
        resp, err = "", f"{type(e).__name__}: {str(e)[:120]}"
    dt = time.time() - t0
    reasoning = getattr(ev, "_last_llm_reasoning", "") or ""
    truncated = bool(getattr(ev, "_last_llm_truncated", False))
    m = re.search(r"FINAL_CHOICE:\s*(\d+)", resp) or re.search(r"ACTION:\s*(\d+)", resp)
    return {"preset": preset, "model": p["model"], "mode": p["mode"], "seconds": round(dt, 1),
            "reasoning_chars": len(reasoning), "answer_chars": len(resp), "parsed": bool(m),
            "choice": int(m.group(1)) if m else None, "truncated": truncated, "error": err}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--presets", nargs="+", default=["qwen3.5-397b", "qwen3.6-35b", "qwen3.8-27b", "glm-5.3-flash"])
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--turn", type=int, default=None)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--thinking-cap", type=int, default=8192)
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "reliability" / "decision_latency.json")
    args = ap.parse_args()

    system, e, n_opts = pick_turn(args.log, args.turn)
    user = ev._build_user_msg(e["state_text"], e["actions_text"]) if hasattr(ev, "_build_user_msg") else e["state_text"] + "\n\n" + e["actions_text"]
    print(f"prompt: {args.log.name} turn {e['turn']} — {n_opts} actions, system {len(system)} chars, user {len(user)} chars, "
          f"thinking cap {args.thinking_cap}; the episode picked: {e.get('action')}")
    print("(one thread per preset, repeats run sequentially per preset)\n")

    def run_preset(preset):
        return [one_call(preset, system, user, args.thinking_cap) for _ in range(args.repeats)]

    with ThreadPoolExecutor(max_workers=len(args.presets)) as pool:
        results = {p: r for p, r in zip(args.presets, pool.map(run_preset, args.presets))}

    rows = []
    print(f"{'preset':16s} {'mode':9s} {'s/call med':>10s} {'min':>6s} {'max':>6s} {'reason chars':>13s} {'parsed':>7s} {'trunc':>6s}  choices")
    for p, rs in results.items():
        secs = [r["seconds"] for r in rs]
        row = {"preset": p, "model": rs[0]["model"], "mode": rs[0]["mode"], "n": len(rs),
               "seconds_median": statistics.median(secs), "seconds_min": min(secs), "seconds_max": max(secs),
               "reasoning_chars_median": statistics.median(r["reasoning_chars"] for r in rs),
               "parsed": sum(r["parsed"] for r in rs), "truncated": sum(r["truncated"] for r in rs),
               "choices": [r["choice"] for r in rs], "errors": [r["error"] for r in rs if r["error"]]}
        rows.append(row)
        print(f"{p:16s} {row['mode']:9s} {row['seconds_median']:10.1f} {row['seconds_min']:6.1f} {row['seconds_max']:6.1f} "
              f"{row['reasoning_chars_median']:13.0f} {row['parsed']:>4d}/{row['n']:<2d} {row['truncated']:>6d}  {row['choices']}"
              + (f"  ERR {row['errors'][0]}" if row["errors"] else ""))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"prompt": {"log": args.log.name, "turn": e["turn"], "n_actions": n_opts,
                                                "system_chars": len(system), "user_chars": len(user), "thinking_cap": args.thinking_cap,
                                                "episode_choice": e.get("action")},
                                     "rows": rows, "timestamp": time.strftime("%Y-%m-%d %H:%M")}, indent=1), encoding="utf-8")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
