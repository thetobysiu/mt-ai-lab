"""Design-6 Qwen3.5-397B run: blue keys and blue doors before turn 708."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
turns = json.loads((ROOT / "logs" / "runs" / "20261004_052939_498308_MT0-MT23w_llm.json").read_text(encoding="utf-8"))["turns"]
tt = [t for t in turns if t.get("type") == "turn" and t["turn"] <= 708]
prev = None
for t in tt:
    b = t["hero"]["keys"]["blue"]
    if "blue" in str(t.get("action")).lower() or (prev is not None and b != prev):
        print(t["turn"], t.get("floor_id"), t.get("action"), "blue", prev, "->", b)
    prev = b
