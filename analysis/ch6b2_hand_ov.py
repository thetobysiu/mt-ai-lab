"""hand03/hand04 canonical runs: mechanical overrides per model and reason; reasoning caps of the canonical hand runs."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
MODELS = ["qwen3.5-397b", "deepseek-v4-flash", "qwen3.6-35b", "mistral-medium-3.5"]

for floor in ["hand01", "hand02", "hand03", "hand04"]:
    for m in MODELS:
        d = json.load(open(ROOT / "results" / "reliability" / f"{floor}_{m}_canon.json", encoding="utf-8"))
        cap = d["config"]["env"].get("THINKING_MAX_TOKENS")
        if floor in ("hand01", "hand02"):
            print(f"{floor} {m}: cap={cap}")
            continue
        tot = Counter()
        per = []
        for r in d["runs"]:
            turns = json.loads((ROOT / "logs" / "runs" / r["run_log"]).read_text(encoding="utf-8"))["turns"]
            corr = [t for t in turns if t.get("type") == "turn" and t.get("corrected_from") is not None]
            c = Counter((t.get("corrected_reason") or "?").split(":")[0][:30] for t in corr)
            tot.update(c)
            per.append(len(corr))
        print(f"{floor} {m}: cap={cap} corrected per run={per} total={sum(per)} reasons={dict(tot)}")
