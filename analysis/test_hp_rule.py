"""Re-ask one stored tower decision with the HP rule of the prompt (and of the annotations) at other thresholds.

    python scratch/test_hp_rule.py --presets qwen3.5-397b deepseek-v4-flash-think --pct 40 60 80 100 --repeats 2
The system prompt is rebuilt exactly as the tower loop builds it (prompt + floor map at arrival on that floor); the user
message is the stored one. Every "40%" / "40 %" in both is replaced by the variant (100 = effectively no rule).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scratch"))
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")
from mota.optimizer import evaluator as ev  # noqa: E402
from mota.optimizer.model_config import TASK_MODEL_PRESETS  # noqa: E402

# (name, run log, turn, engine flags of that run, the choice an expert makes)
CASES = [
    ("design-6 MT3 turn 15 (570 HP: Skeleton 55 % vs Bat 33 %)", "20261001_220503_593390_MT0-MT23w_llm.json", 15,
     {"MOTA_REMOTE_ACTIONS": "1", "MOTA_SHOP_ROUTE": "1", "MOTA_WAY_UP": "1", "MOTA_TOWER_FIDELITY": "1",
      "MOTA_OFFER_LEVELUPS": "1"}, "Skeleton at (2,3)"),
    ("design-3 MT3 turn 17 (340 HP: Skeleton 93 % vs Bat 56 %)", "20261001_084634_705631_MT0-MT23w_llm.json", 17,
     {"MOTA_REMOTE_ACTIONS": "1", "MOTA_SHOP_ROUTE": "1"}, "Bat at (6,6)"),
]
FLAGS = ("MOTA_REMOTE_ACTIONS", "MOTA_SHOP_ROUTE", "MOTA_WAY_UP", "MOTA_TOWER_FIDELITY", "MOTA_OFFER_LEVELUPS")


def build(log: str, turn: int, flags: dict) -> tuple[str, str, dict[int, str]]:
    from replay_tower import replay
    for k in FLAGS:
        os.environ.pop(k, None)
    os.environ.update(flags)
    j = json.loads((ROOT / "logs" / "runs" / log).read_text(encoding="utf-8"))
    n = arrival = 0
    for t in j["turns"]:
        if t["type"] == "turn":
            if int(t["turn"]) >= turn:
                break
            n += 1
        elif t["type"] == "floor_change":
            arrival = n
    system = j["prompt"] + "\n\n" + replay(str(ROOT / "logs" / "runs" / log), arrival).format_floor_map()
    think = next(t for t in j["turns"] if t["type"] == "thinking" and int(t.get("turn") or 0) == turn)
    labels = {int(m.group(1)): m.group(2).split(" — ")[0].split(" ΓÇö")[0]
              for m in re.finditer(r"^\s{2}(\d+)\. \[\w+\] (.+)$", think["actions_text"], re.M)}
    return system, think["user_message"], labels


def variant(text: str, pct: int) -> str:
    return re.sub(r"\b40( ?)%", lambda m: f"{pct}{m.group(1)}%", text)


def ask(preset: str, system: str, user: str) -> tuple[int | None, float, int]:
    p = TASK_MODEL_PRESETS[preset]
    t0 = time.time()
    resp = ev._call_llm(system, user, task_model=p["model"], task_mode=p["mode"], temperature=0.0)
    m = list(re.finditer(r"FINAL_CHOICE:\s*(\d+)", resp or ""))
    return (int(m[-1].group(1)) if m else None), round(time.time() - t0), len(getattr(ev, "_last_llm_reasoning", "") or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--presets", nargs="+", default=["qwen3.5-397b", "deepseek-v4-flash-think"])
    ap.add_argument("--pct", nargs="+", type=int, default=[40, 60, 80, 100])
    ap.add_argument("--repeats", type=int, default=2)
    args = ap.parse_args()
    os.environ["THINKING_MAX_TOKENS"] = "8192"
    built = [(name, *build(log, turn, flags), expert) for name, log, turn, flags, expert in CASES]
    jobs = [(c, preset, pct) for c in built for preset in args.presets for pct in args.pct for _ in range(args.repeats)]

    def run(job):
        (name, system, user, labels, expert), preset, pct = job
        choice, secs, rchars = ask(preset, variant(system, pct), variant(user, pct))
        return name, preset, pct, labels.get(choice, f"#{choice}"), expert, secs, rchars

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(run, jobs))
    out = []
    for name in dict.fromkeys(r[0] for r in rows):
        print(f"\n== {name}  (expert: {next(r[4] for r in rows if r[0] == name)})")
        for preset in args.presets:
            for pct in args.pct:
                picks = [r[3] for r in rows if r[0] == name and r[1] == preset and r[2] == pct]
                print(f"  {preset:24s} rule {pct:>3d} %: {picks}")
                out.append({"case": name, "preset": preset, "pct": pct, "picks": picks})
    (ROOT / "results" / "reliability" / "hp_rule_decision_test.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
