"""Model calls vs LLM-decided turns for tower runs: python scratch/tower_calls.py <label> ...
The tower result field llm_calls counts every non-forced turn, including executed plan steps; the number of
model calls is the number of 'thinking' events (one per request) in the run log."""
import json
import sys
from pathlib import Path

for lab in sys.argv[1:]:
    d = json.loads((Path("results/reliability") / f"{lab}.json").read_text(encoding="utf-8"))
    for r in d["runs"]:
        log = Path("logs/runs") / r["run_log"]
        if not log.exists():
            print(lab, r["run_log"], "log missing")
            continue
        turns = json.loads(log.read_text(encoding="utf-8"))["turns"]
        calls = sum(1 for t in turns if t["type"] == "thinking")
        planned = sum(1 for t in turns if t["type"] == "turn" and str(t.get("planned")) == "True")
        print(f"{lab}: {r['max_floor_id']} decided={r['llm_calls']} calls={calls} planned={planned} forced={r.get('forced_turns')}")
