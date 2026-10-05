"""CoT integrity audit for stored run logs: per LLM turn, was the response truncated, was the
action repaired/fallback, how long was the reasoning, did the CoT end coherently?

    python scripts/audit_cot.py <runlog> [<runlog> ...]
    python scripts/audit_cot.py --kills            # all stored simple/complex kills
"""
import glob
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]

CUT_MARKERS = ("Wait", "Let me", "Actually", "Hmm", "But", "So", "The player", "Option")


def audit(path: str) -> None:
    d = json.load(open(path, encoding="utf-8"))
    turns = [t for t in d["turns"] if t["type"] == "turn"]
    llm_turns = [t for t in turns if not t.get("forced")]
    pe = [t for t in d["turns"] if t["type"] == "parse_error"]
    tr = {t["turn"]: t for t in d["turns"] if t["type"] == "thinking_result"}
    res = d.get("result") or {}
    hp = (res.get("details") or {}).get("final_hp")
    print(f"\n== {Path(path).name}  model={d.get('task_model')}  goal_reached={res.get('goal_reached')} hp={hp}")
    print(f"   turns={len(turns)} llm={len(llm_turns)} forced={len(turns)-len(llm_turns)} parse_errors={len(pe)} "
          f"truncated={sum(1 for p in pe if p.get('reason')=='truncated')} repaired={sum(1 for p in pe if p.get('repaired_id') is not None)} "
          f"fallback_turns={sum(1 for t in llm_turns if t.get('fallback'))}")
    lens = [len(tr[t["turn"]]["thinking"]) for t in llm_turns if t["turn"] in tr]
    if lens:
        print(f"   reasoning chars: n={len(lens)} min={min(lens)} median={sorted(lens)[len(lens)//2]} max={max(lens)}")
    # Coherence: does the CoT end with a decision statement?
    incoherent = []
    for t in llm_turns:
        th = tr.get(t["turn"])
        if not th:
            continue
        tail = th["thinking"][-400:]
        decided = re.search(r"(FINAL_CHOICE|ACTION|choose|choice|pick|select|go with|answer)\D{0,20}\d", tail, re.I)
        if not decided:
            incoherent.append((t["turn"], tail[-120:].replace("\n", " ")))
    print(f"   CoT tails without an explicit decision: {len(incoherent)}/{len(lens)}")
    for turn, tail in incoherent[:5]:
        print(f"     T{turn}: …{tail}")
    for p in pe[:6]:
        print(f"   parse_error T{p['turn']} reason={p.get('reason')} parsed={p.get('parsed_id')} repaired={p.get('repaired_id')}")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--kills":
        files = []
        for p in sorted(set(glob.glob(str(ROOT / "logs" / "runs" / "*.json"))
                            + glob.glob(str(ROOT / "_archive" / "**" / "logs" / "runs" / "*.json"), recursive=True))):
            try:
                d = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            if d.get("mode") != "llm":
                continue
            fid = str(d.get("floor_id", "")).lower()
            if not any(k in fid for k in ("simple", "complex", "最简单", "复杂")):
                continue
            res = d.get("result") or {}
            if res.get("goal_reached") and ((res.get("details") or {}).get("final_hp") or 0) > 0:
                files.append(p)
        print(f"{len(files)} stored kills")
    else:
        files = args
    for f in files:
        audit(f)


if __name__ == "__main__":
    main()
