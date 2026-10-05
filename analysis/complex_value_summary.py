"""Summarise the exact value traces of the complex floor (complex_value_trace_[a-d].json).

    python scratch/complex_value_summary.py
"""
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
runs = {}
for p in sorted(glob.glob(str(ROOT / "results" / "reliability" / "complex_value_trace_*.json"))):
    runs.update(json.load(open(p, encoding="utf-8")))


def short(a):
    return re.sub(r" dmg=\d+", "", a.replace("Open ", "").replace("Fight ", "")).replace(" door at ", " door ")


by_label = defaultdict(list)
classes = Counter()
for key, r in sorted(runs.items()):
    rows = [t for t in r["turns"] if "v_before" in t]
    win = bool(r["success"])
    lost = None if win else next((t for t in rows if t["v_before"] is not None and t["v_after"] is None), None)
    drops = [(t["turn"], short(t["action"]), t["v_before"], t["v_after"]) for t in rows
             if t["v_before"] is not None and t["v_after"] is not None and t["v_after"] < t["v_before"]
             and "Boss" not in t["action"]]
    end_v = next((t["v_after"] for t in reversed(rows) if t.get("v_after") is not None), None)
    by_label[r["label"]].append((r["run"], win, r["final_hp"], lost, drops))
    if lost:
        classes[short(lost["action"])] += 1
for label, items in by_label.items():
    print(f"\n== {label}")
    for run, win, hp, lost, drops in items:
        d = "; ".join(f"t{t} {a} {b}->{c}" for t, a, b, c in drops)
        what = (f"lost at t{lost['turn']} {short(lost['action'])} (V {lost['v_before']} -> unwinnable)" if lost
                else "WIN" if win else "never winnable after start?")
        print(f"  run {run}: {'WIN ' if win else 'fail'} HP {hp}: {what}; HP-losing decisions before: {d or 'none'}")
print("\nDECISION THAT MADE THE BOSS UNWINNABLE (failed runs):")
for a, n in classes.most_common():
    print(f"  {n:2d}  {a}")
