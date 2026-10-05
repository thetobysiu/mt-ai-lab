"""Exact value of every state along stored complex-floor runs (Java reference solver, one JVM per run).

V(t) = best final HP the exact solver can still reach from the state before decision t (None = boss no longer
winnable). The regret of decision t is V(t) - V(t+1); the crucial point of a failed run is the decision after which
V becomes None.

    python scratch/complex_value_trace.py "complex_*_canon.json" [--runs 1,2] [--out results/reliability/complex_value_trace.json]
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
from floor_lab import Floor, java_solve_many  # noqa: E402
from mota.optimizer import evaluator as ev  # noqa: E402

COMPLEX = ROOT / "data" / "floors" / "complex.txt"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
runs_sel = next((set(map(int, a.split("=", 1)[1].split(","))) for a in sys.argv if a.startswith("--runs=")), None)
out_path = ROOT / next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")),
                       "results/reliability/complex_value_trace.json")
fl = Floor(COMPLEX)
ev.configure_scenario(str(COMPLEX))
report = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
for path in sorted({p for pat in args for p in glob.glob(str(ROOT / "results" / "reliability" / pat))}):
    res = json.load(open(path, encoding="utf-8"))
    label = Path(path).stem
    for i, r in enumerate(res.get("runs", []), 1):
        key = f"{label}#{i}"
        if (runs_sel and i not in runs_sel) or key in report or not r.get("run_log"):
            continue
        turns = [t for t in json.load(open(ROOT / "logs" / "runs" / r["run_log"], encoding="utf-8"))["turns"]
                 if t.get("type") == "turn"]
        st = ev._create_state(lookahead_depth=0)
        txts, rows = [fl.state_txt(st.hero, st.removed)], []
        for t in turns:
            a = next((x for x in st.get_actions() if x.label() == t["action"]), None)
            if a is None:
                rows.append({"turn": t["turn"], "action": t["action"], "error": "not offered on replay"})
                break
            st.apply_action(a)
            rows.append({"turn": t["turn"], "action": t["action"], "forced": bool(t.get("forced")), "hp": st.hero.hp})
            # dead hero or dead boss: no map to solve (the solver needs a live hero and a live boss)
            txts.append(None if st.hero.hp <= 0 or "Boss" in t["action"] else fl.state_txt(st.hero, st.removed))
        solved = iter(java_solve_many([x for x in txts if x is not None]))
        vals = [next(solved) if x is not None else None for x in txts]
        v = [(x["hp"] if x["solvable"] else None) if x is not None else None for x in vals]
        for k, row in enumerate(rows):
            if txts[k + 1] is None and "Boss" in row["action"] and st.hero.hp > 0:
                v[k + 1] = st.hero.hp  # the boss fight itself: the value after it is the final HP
        for k, row in enumerate(rows):
            if "error" in row:
                continue
            row["v_before"], row["v_after"] = v[k], v[k + 1]
            row["regret"] = (None if v[k] is None else (v[k] if v[k + 1] is None else v[k] - v[k + 1]))
        crucial = next((row for row in rows if row.get("v_before") is not None and row.get("v_after") is None), None)
        report[key] = {"label": label, "run": i, "success": r.get("success"), "died": r.get("died"),
                       "final_hp": r.get("final_hp"), "v_start": v[0], "crucial": crucial, "turns": rows}
        worst = sorted((row for row in rows if row.get("regret")), key=lambda row: -(row["regret"] or 0))[:3]
        print(f"{key}: {'WIN' if r.get('success') else 'fail'} HP {r.get('final_hp')} | crucial: "
              f"{(crucial['turn'], crucial['action']) if crucial else None} | biggest regrets: "
              f"{[(w['turn'], w['action'][:40], w['regret']) for w in worst]}", flush=True)
        out_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
