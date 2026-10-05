"""Generate solver-verified boss floors → data/floors/gen/genNN.txt + manifest.json.

A floor is kept when the BFS solver kills the boss and the solver's end HP is in [min_hp, max_hp]
(tight enough that fight order matters). The heuristic baseline result is recorded too.

    python scripts/generate_boss_floors.py --n 5 --seed 100
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from mota.solver import boss_floor_gen as G  # noqa: E402
from mota.optimizer import evaluator as ev  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=5)
ap.add_argument("--seed", type=int, default=100)
ap.add_argument("--max-tries", type=int, default=400)
ap.add_argument("--min-hp", type=int, default=1)
ap.add_argument("--max-hp", type=int, default=250)
ap.add_argument("--append", action="store_true", help="keep existing manifest floors; number new ones after them")
a = ap.parse_args()

out = ROOT / "data" / "floors" / "gen"
out.mkdir(parents=True, exist_ok=True)
existing = []
if a.append and (out / "manifest.json").exists():
    existing = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["floors"]
used_seeds = {f["seed"] for f in existing}
tmp = out / "_candidate.txt"
kept = []
for s in range(a.seed, a.seed + a.max_tries):
    if len(kept) >= a.n:
        break
    if s in used_seeds:
        continue
    g = G.generate(s)
    tmp.write_text(G.to_txt(g), encoding="utf-8")
    res, total, states = G.solve(tmp)
    if res is None or not (a.min_hp <= res.hero.hp <= a.max_hp):
        print(f"seed {s}: {'unsolvable' if res is None else f'solver HP {res.hero.hp} out of range'} ({states} states)")
        continue
    name = f"gen{len(existing) + len(kept) + 1:02d}"
    path = out / f"{name}.txt"
    path.write_text(G.to_txt(g), encoding="utf-8")
    ev.configure_scenario(str(path))
    h = ev.evaluate_heuristic_only()
    kills = sum(1 for x in res.route if x.type.value == "fight")
    rec = {"name": name, "file": f"data/floors/gen/{name}.txt", "seed": s, "doors": g["doors"], "links": g["links"],
           "target_hp": res.hero.hp, "target_atk": res.hero.atk, "target_def": res.hero.def_,
           "ref_steps": len(res.route), "enemies_total": total, "enemies_killed": kills, "solver_states": states,
           "heuristic": {"boss_killed": bool(h.get("goal_reached")), "final_hp": (h.get("details") or {}).get("final_hp"),
                         "score": h.get("total")}}
    kept.append(rec)
    print(f"KEEP {name}: seed {s}, solver HP {res.hero.hp} ATK {res.hero.atk} DEF {res.hero.def_}, {kills}/{total} fights, "
          f"{g['doors']} doors, heuristic boss_killed={rec['heuristic']['boss_killed']} hp={rec['heuristic']['final_hp']}")
tmp.unlink(missing_ok=True)
(out / "manifest.json").write_text(json.dumps({"generator": "mota/solver/boss_floor_gen.py", "floors": existing + kept},
                                              indent=2), encoding="utf-8")
print(f"kept {len(kept)} floors -> {out}")
