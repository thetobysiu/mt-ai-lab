"""Design-6 Qwen3.5-397B run: hero at MT17 entry and at turn 708; final7 reactive runs (development design 5)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
turns = json.loads((ROOT / "logs" / "runs" / "20261004_052939_498308_MT0-MT23w_llm.json").read_text(encoding="utf-8"))["turns"]
tt = [t for t in turns if t.get("type") == "turn"]
seen = set()
for t in tt:
    f = t.get("floor_id")
    if f in ("MT16", "MT17", "MT18", "MT19") and f not in seen:
        seen.add(f)
        print("first", f, "turn", t["turn"], t["hero"])
for t in tt:
    if t["turn"] in (706, 707, 708):
        print("turn", t["turn"], t.get("floor_id"), t.get("action"), t["hero"])
blue = [(t["turn"], t.get("floor_id"), t.get("action")) for t in tt if "blue door" in str(t.get("action")).lower()]
print("blue doors opened (last 5):", blue[-5:])

for lab in ["tower_deepseek-v4-flash_final7_reactive", "tower_qwen3.5-397b_final7_reactive",
            "tower_deepseek-v4-flash_final7_plan3", "tower_deepseek-v4-flash_final7_plan5",
            "tower_qwen3.5-397b_final7_plan3", "tower_deepseek-v4-flash_final8_reactive", "tower_qwen3.5-397b_final8_reactive"]:
    d = json.loads((ROOT / "results" / "reliability" / f"{lab}.json").read_text(encoding="utf-8"))
    print(lab, [(r.get("max_floor_id"), r.get("final_hp"), r.get("hero_atk"), r.get("hero_def"), r.get("llm_calls")) for r in d["runs"]])
