"""hand01 canonical Qwen3.5-397B: does the first-decision reasoning cite the Black Slime fight-order line?"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
for m in ["qwen3.5-397b", "qwen3.6-35b", "mistral-medium-3.5", "deepseek-v4-flash"]:
    d = json.load(open(ROOT / "results" / "reliability" / f"hand01_{m}_canon.json", encoding="utf-8"))
    for r in d["runs"]:
        turns = json.loads((ROOT / "logs" / "runs" / r["run_log"]).read_text(encoding="utf-8"))["turns"]
        first = next(t for t in turns if t.get("type") == "turn" and not t.get("forced"))
        idx = turns.index(first)
        tr = [t for t in turns[:idx + 1] if t.get("type") == "thinking_result"]
        blob = " ".join(str(t.get("thinking") or "") for t in tr) + " " + str(first.get("llm_thinking") or "") + " " + str(first.get("llm_response") or "")
        hits = [mm.start() for mm in re.finditer(r"Black Slime|ORDER|before fighting|hint", blob)]
        print(m, r["run_log"][:22], first["action"], "len", len(blob), "hits", len(hits))
        for h in hits[:2]:
            print("    ...", blob[max(0, h - 200): h + 200].replace("\n", " "))
