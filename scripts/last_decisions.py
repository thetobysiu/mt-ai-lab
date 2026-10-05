"""Dump the last N decisions (state excerpt, action list, CoT tail) of a run log."""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
path = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
d = json.load(open(path, encoding="utf-8"))
turns = [t for t in d["turns"] if t["type"] == "turn"]
print("==", path, d.get("task_model"))
for t in turns[-8:]:
    h = t.get("hero", {})
    print(f"  [{t['turn']}] hp={h.get('hp')} atk={h.get('atk')} def={h.get('def')} "
          f"{'F' if t.get('forced') else 'L'} {t['action']}")
for t in turns[-n:]:
    th = [x for x in d["turns"] if x["type"] == "thinking" and x["turn"] == t["turn"]]
    tr = [x for x in d["turns"] if x["type"] == "thinking_result" and x["turn"] == t["turn"]]
    print(f"\n----- turn {t['turn']}: chose {t['action']}")
    if th:
        st = th[0]["state_text"]
        print(st[:st.find("Uncollected")][:400])
        at = th[0]["actions_text"]
        for line in at.splitlines():
            if line.strip().startswith(tuple(f"{i}." for i in range(1, 30))):
                print("   ", line[:200])
    if tr:
        print("  CoT tail:", tr[0]["thinking"][-900:].replace("\n", " "))
