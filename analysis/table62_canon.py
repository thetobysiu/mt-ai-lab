"""Table 6.2 rows from the canonical *_canon result files (k/N, HP/opt of the wins, deaths)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
OPT = {"simple": 13, "complex": 68, "complex_route": 68, "hand01": 14, "hand02": 13, "hand03": 9, "hand04": 3}
MODELS = {"qwen3.5-397b": "Qwen3.5-397B", "deepseek-v4-flash": "DeepSeek-V4-Flash", "qwen3.6-35b": "Qwen3.6-35B",
          "mistral-medium-3.5": "Mistral Medium 3.5"}
suffix = sys.argv[1] if len(sys.argv) > 1 else "canon"
for tag, name in MODELS.items():
    cells = []
    for floor, opt in OPT.items():
        p = ROOT / "results" / "reliability" / f"{floor}_{tag}_{suffix}.json"
        if not p.exists():
            cells.append("—")
            continue
        runs = json.load(open(p, encoding="utf-8"))["runs"]
        wins = [r for r in runs if r.get("success")]
        dead = sum(bool(r.get("died")) for r in runs)
        hp = (f" ({sum(r['final_hp'] for r in wins) / len(wins) / opt:.2f})" if wins else "")
        cells.append(f"{len(wins)}/{len(runs)}{hp}" + (f" †{dead}" if dead else ""))
    print(f"| {name} | " + " | ".join(cells) + " |")
