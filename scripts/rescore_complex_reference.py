"""Re-express stored complex-floor results against the exact optimum (HP 68, was 22). Success is unchanged;
hp_ratio and goal_score of successful runs are recomputed; the old values are kept as *_ref22."""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
OPT, OLD = 68, 22
for p in sorted(Path("results/reliability").glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        continue
    floor = str((d.get("config") or {}).get("floor", ""))
    if Path(floor).stem not in ("complex", "单层-复杂"):
        continue
    n = 0
    for r in d.get("runs", []):
        if r.get("success") and r.get("final_hp") is not None and "hp_ratio_ref22" not in r:
            r["hp_ratio_ref22"], r["goal_score_ref22"] = r.get("hp_ratio"), r.get("goal_score")
            r["hp_ratio"] = round(min(1.0, r["final_hp"] / OPT), 4)
            r["goal_score"] = round(0.5 + 0.5 * r["hp_ratio"], 4)
            n += 1
    d.setdefault("config", {})["reference_hp"] = OPT
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{p.name}: {n} successful runs re-expressed")
