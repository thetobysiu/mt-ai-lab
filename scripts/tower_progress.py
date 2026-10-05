"""Summarise a (possibly in-progress) tower run log: floors, hero trajectory, action mix, loops."""
import collections
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
turns = [t for t in d["turns"] if t["type"] == "turn"]
fc = [t for t in d["turns"] if t["type"] == "floor_change"]
pe = [t for t in d["turns"] if t["type"] == "parse_error"]
print("turns", len(turns), "floor_changes", len(fc), "parse_errors", len(pe),
      "truncated", sum(1 for t in pe if t.get("reason") == "truncated"),
      "repaired", sum(1 for t in pe if t.get("repaired_id") is not None))
print("floors visited:", collections.Counter(t["floor_id"] for t in fc))
max_floor = max((int(t["floor_id"][2:].rstrip("wes")) for t in fc), default=0)
print("max floor idx:", max_floor)
kinds = collections.Counter(t["action"].split(" ")[0] + (" revisit" if "revisit" in t["action"] else "") for t in turns)
print("action mix:", kinds)
print("forced:", sum(1 for t in turns if t.get("forced")), "llm:", sum(1 for t in turns if not t.get("forced")))
last = turns[-1]["hero"] if turns else {}
print("hero now:", {k: last.get(k) for k in ("hp", "atk", "def", "money", "exp", "keys")})
# HP trajectory at floor changes
for t in fc[-12:]:
    h = t.get("hero", {})
    print(f"  turn {t['turn']:4d} -> {t['floor_id']:6s} hp={h.get('hp')} atk={h.get('atk')} def={h.get('def')}")
print("last 20 actions:")
for t in turns[-20:]:
    print(f"  [{t['turn']}] {t.get('floor_id')} {'F' if t.get('forced') else 'L'} {t['action'][:80]}")
