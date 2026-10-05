"""Find the system prompt stored in a tower run log (design 2 = final3) and measure it."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOGS = Path(__file__).resolve().parents[1] / "logs" / "runs"
for name in sys.argv[1:]:
    p = LOGS / name
    if not p.exists():
        print(name, "MISSING")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    print(name, "top keys:", list(d.keys())[:30])
    cands = []

    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o[:3]):
                walk(v, f"{path}[{i}]")
        elif isinstance(o, str) and "Magic Tower" in o and len(o) > 2000:
            cands.append((path, len(o), len(o.strip())))

    walk(d)
    for c in cands[:6]:
        print("  ", c)
