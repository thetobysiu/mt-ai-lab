"""Engine-verify every committed plan in stored single-floor runs (the plan_check the loop now emits live).

    python scripts/verify_plans.py simple_deepseek-v4-flash_final2_plan3 [label ...] [--json out.json]

Each LLM turn's post-state is rebuilt from the logged hero + cumulative `removed`; its NEXT line is parsed with
the run's MOTA_PLAN_STEPS and simulated with evaluator._verify_plan.
"""
import argparse, json, os, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from mota.optimizer import evaluator as ev  # noqa: E402

FLOORS = {"simple": "data/floors/simple.txt", "complex": "data/floors/complex.txt"}


def state_from(event: dict):
    s = ev._create_state()
    h, e = s.hero, event["hero"]
    h.hp, h.atk, h.def_, h.mdef, h.money, h.exp, h.x, h.y = (e["hp"], e["atk"], e["def"], e["mdef"], e["money"],
                                                             e["exp"], e["x"], e["y"])
    h.keys.yellow, h.keys.blue, h.keys.red = e["keys"]["yellow"], e["keys"]["blue"], e["keys"]["red"]
    s.removed = {tuple(r) for r in event["removed"]}
    return s


def verify_label(label: str) -> dict:
    res = json.loads((ROOT / "results/reliability" / f"{label}.json").read_text(encoding="utf-8"))
    cfg = res["config"]
    k = int(cfg.get("env", {}).get("MOTA_PLAN_STEPS", "1"))
    ev.configure_scenario(str(ROOT / FLOORS.get(cfg["floor"], cfg["floor"])))
    zero = not cfg.get("overrides_disabled")
    plans = []
    for run in res["runs"]:
        log = json.loads((ROOT / "logs/runs" / run["run_log"]).read_text(encoding="utf-8"))
        for t in log["turns"]:
            if t.get("type") != "turn" or t.get("llm_response") is None or t.get("fallback") or t.get("corrected_from"):
                continue
            plan = ev._parse_next_plan(t["llm_response"], k - 1, t.get("llm_thinking"))
            if not plan:
                plans.append({"run": run["run_idx"], "turn": t["turn"], "entries": 0, "legal": 0, "break": None})
                continue
            v = ev._verify_plan(state_from(t), plan, zero)
            v.update(run=run["run_idx"], turn=t["turn"], budget=plan.budget)
            plans.append(v)
    with_plan = [p for p in plans if p["entries"]]
    n = max(1, len(with_plan))
    return {
        "label": label, "k": k, "llm_turns": len(plans), "plans": len(with_plan),
        "no_plan": len(plans) - len(with_plan),
        "entries_mean": round(sum(p["entries"] for p in with_plan) / n, 2),
        "new_decisions_mean": round(sum(p["entries"] - p["already_cleared"] - p["items"] for p in with_plan) / n, 2),
        "legal_mean": round(sum(p["legal"] for p in with_plan) / n, 2),
        "repeats_first": sum(1 for p in with_plan if p["already_cleared"]),
        "clean": sum(1 for p in with_plan if p["break"] is None),
        "reaches_goal": sum(1 for p in with_plan if p.get("goal_reached")),
        "breaks": dict(Counter(p["break"]["reason"] for p in with_plan if p.get("break"))),
        "detail": plans,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--json")
    a = ap.parse_args()
    out = []
    for lab in a.labels:
        r = verify_label(lab)
        out.append(r)
        print(f"{lab}: k={r['k']} llm_turns={r['llm_turns']} plans={r['plans']} (none {r['no_plan']}) "
              f"entries={r['entries_mean']} new={r['new_decisions_mean']} legal={r['legal_mean']} "
              f"repeat_first={r['repeats_first']} clean={r['clean']}/{r['plans']} "
              f"plan_reaches_goal={r['reaches_goal']} breaks={r['breaks']}")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
