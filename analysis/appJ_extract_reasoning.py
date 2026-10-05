"""Write the reasoning of one turn of a run log to a UTF-8 file (verbatim, for Appendix J)."""
import json
import sys
from pathlib import Path

LOGS = Path(__file__).resolve().parents[1] / "logs" / "runs"
name, turn, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
L = json.loads((LOGS / name).read_text(encoding="utf-8"))
matches = [x for x in L["turns"] if x.get("turn") == turn]
t = next((x for x in matches if x.get("llm_thinking")), matches[-1])
text = t.get("llm_thinking") or ""
Path(out).write_text(
    f"chars={len(text)} response={t.get('llm_response')!r} action={t.get('action')}\n"
    f"state:\n{t.get('state_text')}\n----- REASONING -----\n{text}\n",
    encoding="utf-8",
)
