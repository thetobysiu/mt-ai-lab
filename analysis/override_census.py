"""Count turns where the LLM's parsed choice != executed action_id (silent _safety_correct overrides)."""
import json, re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
files = [Path(a) for a in sys.argv[1:]] or sorted(list((ROOT / "logs/runs").glob("*simple_llm.json")) + list((ROOT / "_archive").glob("**/logs/runs/*simple_llm.json")), key=lambda p: p.name)
pat = re.compile(r"(?:FINAL_CHOICE|ACTION)\s*:\s*\**\s*(\d+)", re.I)
tot = 0
for p in files:
    d = json.loads(p.read_text(encoding="utf-8"))
    turns = [e for e in d["turns"] if e.get("type") == "turn" and not e.get("forced")]
    last = turns[-1]["hero"]["hp"] if turns else None
    win = any("Boss" in (e.get("action") or "") for e in turns) and (last or 0) > 0
    ov = []
    for e in turns:
        r = e.get("llm_response") or ""
        m = pat.findall(r)
        if not m:
            continue
        said = int(m[-1])
        if said != e.get("action_id") and not e.get("fallback"):
            ov.append(f"T{e['turn']}:{said}->{e['action_id']} {e['action'][:28]}")
    tot += len(ov)
    print(f"{p.name[:34]} {'WIN ' if win else 'fail'} hp={last!s:>4} overrides={len(ov)}  {' | '.join(ov)}")
print("total overrides", tot)
