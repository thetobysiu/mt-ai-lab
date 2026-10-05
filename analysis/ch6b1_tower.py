import json, os, sys
R = os.path.join(os.path.dirname(__file__), "..", "results", "reliability")
files = sys.argv[1:] or ["tower_deepseek-v4-flash_final7_plan3.json", "tower_deepseek-v4-flash_final7_plan5.json",
         "tower_qwen3.5-397b_final7_plan3.json"]
for n in files:
    d = json.load(open(os.path.join(R, n), encoding="utf-8"))
    print("=" * 10, n, d["config"].get("env", {}).get("THINKING_MAX_TOKENS"), d["config"].get("env", {}).get("MOTA_PLAN_STEPS"))
    for e in d.get("runs") or []:
        print("  ", {k: e.get(k) for k in ("max_floor_id", "turns", "forced_turns", "planned_turns", "model_calls", "llm_calls", "hero_atk", "hero_def", "final_hp")})

