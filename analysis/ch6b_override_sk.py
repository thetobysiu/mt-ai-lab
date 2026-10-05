"""Designs 1-4: 40 % override events on the MT3 Skeleton (2,3); MT3 stops with the sequence of events."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "results" / "reliability"
LOGS = ROOT / "logs" / "runs"
DESIGN = {"final2": 1, "final3": 2, "final4": 3, "final5": 4}
out = open(ROOT / "scratch" / "_ch6b_override_sk.txt", "w", encoding="utf-8")
tot = {"runs": 0, "sk_override": 0, "mt3": 0, "mt3_override": 0}
per_design = {}
for f in sorted(REL.glob("tower_*_final[2345]*.json")):
    if "nohp" in f.name:
        continue
    des = DESIGN[[k for k in DESIGN if f"_{k}" in f.name][0]]
    d = json.loads(f.read_text(encoding="utf-8"))
    for i, r in enumerate(d["runs"]):
        if not r.get("run_log"):
            continue
        turns = json.loads((LOGS / r["run_log"]).read_text(encoding="utf-8"))["turns"]
        byturn = {t["turn"]: t for t in turns if t.get("type") == "turn"}
        ovs = [t for t in turns if t.get("type") == "override" and t.get("reason") == "hp_floor_40"]
        sk = [o for o in ovs if "Skeleton at (2,3)" in str(o.get("llm_action")) and "MT" not in str(o.get("llm_action"))[:4]]
        sk_any = [o for o in ovs if "Skeleton at (2,3)" in str(o.get("llm_action"))]
        desc = []
        for o in sk_any:
            t = byturn.get(o["turn"], {})
            prev = byturn.get(o["turn"] - 1, {})
            desc.append(f"T{o['turn']} floor={t.get('floor_id')} hp_before={prev.get('hero', {}).get('hp')} model={o.get('llm_action')!r} -> {o.get('executed_action')!r}")
        ex = [(t["turn"], byturn.get(t["turn"] - 1, {}).get("hero", {}).get("hp"), t["hero"]["hp"]) for t in byturn.values()
              if t.get("floor_id") == "MT3" and "Skeleton at (2,3)" in str(t.get("action"))]
        mt3 = r.get("max_floor_id") == "MT3"
        tot["runs"] += 1
        tot["sk_override"] += bool(sk_any)
        tot["mt3"] += mt3
        tot["mt3_override"] += mt3 and bool(sk_any)
        pd = per_design.setdefault(des, [0, 0, 0, 0])
        pd[0] += 1; pd[1] += bool(sk_any); pd[2] += mt3; pd[3] += mt3 and bool(sk_any)
        other = [f"T{o['turn']} {o.get('llm_action')!r}->{o.get('executed_action')!r}" for o in ovs if o not in sk_any]
        out.write(f"design {des} {f.stem} run{i} max={r.get('max_floor_id')} hp={r.get('final_hp')} "
                  f"sk_override={desc} sk_executed(turn,hp_before,hp_after)={ex} other_hp40={other[:3]}\n")
out.write(f"TOTAL {tot}\nper design [runs, sk_override, mt3, mt3_with_sk_override]: {per_design}\n")
out.close()
