"""Recompute map-enum metrics from stored run logs with the visible-answer parser.
Turns whose reply has a visible answer keep their recorded counts (the last OPTIONS block is the
answer's); truncated turns without a visible answer count as 'listed nothing'.
usage: mapenum_rescore.py <label> [<label> ...]"""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from mota.optimizer import evaluator as ev

R = str(__import__("pathlib").Path(__file__).resolve().parents[1])
for label in sys.argv[1:]:
    d = json.load(open(f"{R}/results/reliability/{label}.json", encoding="utf-8"))
    t = dict(turns=0, answered=0, truncated=0, listed=0, listed_legal=0, legal=0, no_entity=0, unreachable=0,
             choice_illegal=0, choice_unparsed=0, retry_rescued=0, fallback=0)
    for r in d["runs"]:
        log = json.load(open(f"{R}/logs/runs/{r['run_log']}", encoding="utf-8"))
        for e in log["turns"]:
            if e.get("type") != "turn" or e.get("forced") or "map_enum" not in e:
                continue
            m = e["map_enum"]
            first = (e.get("llm_response") or "").split("\n\n[RETRY]\n")[0]
            opts, choice = ev._parse_map_enum(first)
            if m.get("truncated"):  # qwen3.6 spills reasoning into content when cut off
                opts, choice = [], None
            t["turns"] += 1
            t["legal"] += m["legal"]
            t["truncated"] += bool(m.get("truncated"))
            if opts:
                t["answered"] += 1
                t["listed"] += m["listed"]
                t["listed_legal"] += m["listed_legal"]
                t["no_entity"] += m["halluc_no_entity"]
                t["unreachable"] += m["halluc_unreachable"]
            if choice is None:
                t["choice_unparsed"] += 1
            elif m.get("violation") == "illegal":
                t["choice_illegal"] += 1
            t["fallback"] += bool(e.get("fallback"))
            t["retry_rescued"] += bool(m.get("violation")) and not e.get("fallback")
    prec = t["listed_legal"] / t["listed"] if t["listed"] else None
    rec = t["listed_legal"] / t["legal"] if t["legal"] else None
    viol = (t["choice_illegal"] + t["choice_unparsed"]) / t["turns"] if t["turns"] else None
    print(label, t, f"precision={prec and round(prec, 3)} recall={rec and round(rec, 3)} first-answer violation={viol and round(viol, 3)}")
