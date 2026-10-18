"""Exact value of every alternative at each model decision of a stored simple-floor episode (Table 4.4, Section 6.4).

    python analysis/simple_turn_values.py <result file in results/reliability/> <run index, 1-based> [--all-turns]
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
from floor_lab import Floor, java_solve_many  # noqa: E402
from mota.optimizer import evaluator as ev  # noqa: E402

SIMPLE = ROOT / "data" / "floors" / "simple.txt"
res_path, idx = sys.argv[1], int(sys.argv[2])
all_turns = "--all-turns" in sys.argv
fl = Floor(SIMPLE)
ev.configure_scenario(str(SIMPLE))
res = json.load(open(ROOT / "results" / "reliability" / res_path, encoding="utf-8"))
r = res["runs"][idx - 1]
print("run", idx, "success", r.get("success"), "final_hp", r.get("final_hp"), r.get("run_log"))
turns = [t for t in json.load(open(ROOT / "logs" / "runs" / r["run_log"], encoding="utf-8"))["turns"] if t.get("type") == "turn"]
st = ev._create_state(lookahead_depth=0)
for t in turns:
    acts = st.get_actions(annotate=False)
    chosen = next((x for x in acts if x.label() == t["action"]), None)
    if chosen is None:
        print("not offered", t["turn"], t["action"])
        break
    if not t.get("forced") or all_turns:
        h = st.hero
        rows, txts = [], []
        for a in acts:
            s2 = copy.deepcopy(st)
            s2.apply_action(a)
            rows.append((a.label(), h.hp - s2.hero.hp, s2.hero.hp))
            # dead hero or dead boss: nothing left to solve
            txts.append(None if s2.hero.hp <= 0 or "Boss" in a.label() else fl.state_txt(s2.hero, s2.removed))
        solved = iter(java_solve_many([x for x in txts if x is not None]))
        vals = [next(solved) if x is not None else None for x in txts]
        print(f"\nT{t['turn']} {'FORCED ' if t.get('forced') else ''}pos=({h.x},{h.y}) HP={h.hp} ATK={h.atk} DEF={h.def_} Y={h.keys.yellow}")
        for (lab, cost, hp), v in zip(rows, vals):
            val = (v["hp"] if v["solvable"] else None) if v is not None else hp
            print(f"   {'*' if lab == t['action'] else ' '} {lab[:70]:70s} cost={cost:5d} value={val}")
    st.apply_action(chosen)
print("\nfinal", st.hero.hp, st.hero.atk, st.hero.def_)
