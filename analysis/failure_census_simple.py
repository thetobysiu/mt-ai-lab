"""Failure census of the simple floor (thesis §6.4.1): first departure of every failed reactive episode
with mechanical-only assists from the canonical winning trajectory (Qwen3.5-397B, first episode of the
net stat-route / fight-order configuration)."""
import collections
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "results" / "reliability"
CELLS = [  # (label, table row / condition)
    ("simple_qwen3.5-397b_basic_mechanical_override", "row 2"),
    ("simple_qwen3.5-397b_basic_mech_altroute", "row 3"),
    ("simple_qwen3.5-397b_basic_order_aware", "row 4"),
    ("simple_qwen3.5-397b_basic_order_aware_la1", "row 4, depth 1"),
    ("simple_qwen3.5-397b_basic_order_aware_la2", "row 4, depth 2"),
    ("simple_qwen3.6-35b_basic_order_aware", "row 4"),
    ("simple_qwen3.5-397b_basic_d1d4", "row 5"),
    ("simple_qwen3.5-397b_basic_d1d4_t06", "row 5, T=0.6"),
    ("simple_qwen3.6-35b_basic_d1d4", "row 5"),
    ("simple_qwen3.8-27b_basic_d1d4", "row 5"),
    ("simple_qwen3.5-397b_basic_k1k2", "row 6"),
    ("simple_qwen3.5-397b_basic_k1k2_la0", "row 6, depth 0"),
    ("simple_qwen3.5-397b_basic_k1k2_la1", "row 6, depth 1"),
    ("simple_qwen3.5-397b_basic_k1k2_la2", "row 6, depth 2"),
    ("simple_qwen3.6-35b_basic_k1k2_16k", "row 6"),
    ("simple_qwen3.5-397b_basic_k1k2_hist0", "row 7"),
    ("simple_qwen3.5-397b_basic_k1k2_hist0_compact", "row 7, compact"),
    ("simple_qwen3.6-35b_basic_k1k2_16k_hist0", "row 7"),
    ("simple_qwen3.5-397b_final_la3", "row 8"),
    ("simple_qwen3.6-35b_final_la3", "row 8"),
    ("simple_qwen3.5-397b_final2_la3", "row 9"),
    ("simple_qwen3.5-397b_final2_la2", "row 9, depth 2"),
    ("simple_qwen3.5-397b_final2_la1", "row 9, depth 1"),
    ("simple_qwen3.5-397b_final2_la0", "row 9, depth 0"),
    ("simple_qwen3.6-35b_final2_la3", "row 9"),
    ("simple_qwen3.6-35b_final2_la2", "row 9, depth 2"),
    ("simple_qwen3.6-35b_final2_la1", "row 9, depth 1"),
    ("simple_qwen3.6-35b_final2_la0", "row 9, depth 0"),
    ("simple_qwen3.8-27b_final2_reactive", "row 9"),
    ("simple_deepseek-v4-flash_final2_reactive", "row 9"),
    ("simple_deepseek-v4-flash_final2_reactive_t32", "row 9, 32K cap"),
]


def actions(run_log):
    d = json.load(open(ROOT / "logs" / "runs" / run_log, encoding="utf-8"))
    return [e for e in d["turns"] if e.get("type") == "turn"]


def canon():
    rec = json.load(open(R / "simple_qwen3.5-397b_basic_order_aware.json", encoding="utf-8"))["runs"][0]
    return [e["action"].split(" dmg=")[0] for e in actions(rec["run_log"])]


WIN = canon()
rows, by_point, total = [], collections.Counter(), 0
for label, cond in CELLS:
    p = R / f"{label}.json"
    if not p.exists():
        print("missing", label)
        continue
    for i, rec in enumerate(json.load(open(p, encoding="utf-8"))["runs"], 1):
        if rec["success"] or not rec.get("run_log"):
            continue
        total += 1
        acts = actions(rec["run_log"])
        k = next((j for j, e in enumerate(acts) if j >= len(WIN) or e["action"].split(" dmg=")[0] != WIN[j]), None)
        if k is None:
            rows.append((label, cond, i, None, "", "", rec)); continue
        e = acts[k]
        chosen = (e.get("corrected_from_label") or "")
        key = (e["turn"], e["action"].split(" dmg=")[0], WIN[k] if k < len(WIN) else "-")
        by_point[key] += 1
        rows.append((label, cond, i, e["turn"], e["action"], WIN[k] if k < len(WIN) else "-", rec, e.get("forced"), chosen,
                     rec.get("parse_errors", 0)))
print(f"failed episodes: {total}\n")
for (t, fa, wa), n in sorted(by_point.items(), key=lambda x: (x[0][0], -x[1])):
    print(f"T{t:>2}  {n:>2}x  took: {fa:<36} winning route: {wa}")
print()
for r in rows:
    label, cond, i, t = r[:4]
    extra = f" forced={r[7]} llm_chose={r[8]!r} parse_err={r[9]}" if len(r) > 7 else ""
    print(f"{label:<48} {cond:<16} r{i}  T{t}  {r[4][:38]:<38} | win {r[5][:30]}{extra}  HP {r[6]['final_hp']} died {r[6]['died']}")
