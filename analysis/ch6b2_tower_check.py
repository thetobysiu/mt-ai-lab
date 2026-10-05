"""Table 6.13 cells (designs 5-7, resumed, heuristic) and the design-7b run log."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "results" / "reliability"
LOGS = ROOT / "logs" / "runs"
sys.stdout.reconfigure(encoding="utf-8")

LABELS = [
    "tower_MT0-MT23w_heuristic_final3", "tower_MT0-MT23w_heuristic_final7",
    "tower_deepseek-v4-flash_final9_reactive", "tower_deepseek-v4-flash_final9_noplanmem",
    "tower_deepseek-v4-flash_final10_reactive", "tower_qwen3.5-397b_final10_reactive",
    "tower_qwen3.5-397b_final10_resume",
    "tower_deepseek-v4-flash_final11_reactive", "tower_qwen3.5-397b_final11_reactive",
    "tower_qwen3.6-35b_final11_reactive", "tower_mistral-medium-3.5_final11_reactive",
    "tower_qwen3.5-397b_final11_resume_blue", "tower_deepseek-v4-flash_final11_resume_blue",
    "tower_qwen3.5-397b_final2", "tower_deepseek-v4-flash_final2_reactive",
    "tower_qwen3.5-397b_final3_reactive", "tower_deepseek-v4-flash_final3_reactive",
    "tower_qwen3.5-397b_final4_reactive", "tower_deepseek-v4-flash_final4_reactive",
    "tower_qwen3.5-397b_final5_reactive", "tower_deepseek-v4-flash_final5_reactive",
    "tower_qwen3.5-397b_final4_nohp_reactive", "tower_qwen3.5-397b_final5_nohp_reactive",
]
for lab in LABELS:
    p = REL / f"{lab}.json"
    if not p.exists():
        print(lab, "MISSING")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    for i, r in enumerate(d["runs"]):
        print(f"{lab} run{i}: max={r.get('max_floor_id')} hp={r.get('final_hp')} atk={r.get('hero_atk')} "
              f"def={r.get('hero_def')} steps={r.get('steps')} calls={r.get('llm_calls')} log={r.get('run_log')}")

for lab in ["tower_qwen3.6-35b_final10_reactive", "tower_mistral-medium-3.5_final10_reactive",
            "tower_deepseek-v4-flash_final10_reactive"]:
    p = REL / "_superseded_keyfact" / f"{lab}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    for i, r in enumerate(d["runs"]):
        print(f"SUPERSEDED {lab} run{i}: max={r.get('max_floor_id')} atk={r.get('hero_atk')} def={r.get('hero_def')}")

print("\n=== design 7b run log ===")
log = json.loads((LOGS / "20261005_103430_434741_MT0-MT23w_llm.json").read_text(encoding="utf-8"))
print("top keys:", list(log.keys()))
for k, v in log.items():
    if k != "turns":
        print(k, str(v)[:600])
turns = log["turns"]
tt = [t for t in turns if t.get("type") == "turn"]
print("n turn records:", len(tt), "last turn:", tt[-1].get("turn"))
print("thinking events:", sum(1 for t in turns if t.get("type") == "thinking"))
print("non-forced turns:", sum(1 for t in tt if not t.get("forced")))
print("types:", sorted({t.get("type") for t in turns}))
floors = [t.get("floor_id") for t in tt]
order = ["MT%d" % i for i in range(24)]
def fnum(f):
    try:
        return int(str(f).replace("MT", "").rstrip("wes"))
    except ValueError:
        return -1
print("highest floor:", max(floors, key=fnum), "last floor:", floors[-1])
last = tt[-1]
print("last hero:", last.get("hero"))
print("last action:", last.get("action"))
print("last turn keys:", list(last.keys()))
hi = [t for t in tt if t.get("floor_id") == "MT17"]
print("first MT17 turn:", hi[0].get("turn") if hi else None)
for t in turns[-6:]:
    print("TAIL", t.get("type"), str(t)[:400])
