"""Hand-designed single floors: ASCII design -> .txt, then BFS optimum, heuristic and difficulty metrics.

    python scripts/floor_lab.py build            # write every design in scripts/hand_floor_designs.py
    python scripts/floor_lab.py analyse data/floors/simple.txt [--decisions] [--rollouts 500]
    python scripts/floor_lab.py register hand01 ...   # add to data/floors/hand/manifest.json (scorer targets)

Difficulty metrics (all exact; every solve is the Java reference BFS in tools/java_bfs, `javac -d out *.java`):
  opt HP / states   BFS optimum and states explored; wins = boss-killing terminal states;
  critical          decisions on an optimal route where at least one legal alternative makes the boss unwinnable;
  forced            decisions where the optimal action is the only one that keeps the boss winnable;
  lose share        mean share of legal alternatives (per decision) after which the boss is unwinnable;
  random win        share of uniform-random legal rollouts (never a lethal fight) that kill the boss;
  greedy            one rollout that always takes the action leaving the most HP (items/doors first).
The Python engine only enumerates and applies actions (the same rules the LLM plays under).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from mota.game.ai_floor_loader import load_ai_floor, build_monsters_lookup, build_item_effects, build_shop_def  # noqa: E402
from mota.game.data import GameData, TILE_ENEMIES  # noqa: E402
from mota.solver.bfs_solver import BFSSolver, SolverState  # noqa: E402

HAND = ROOT / "data" / "floors" / "hand"
JAVA_CP = ROOT / "tools" / "java_bfs" / "out"
LEGEND = {"#": 1, ".": 0, "y": 81, "b": 82, "r": 83, "k": 21, "K": 22, "R": 23,
          "a": 27, "d": 28, "g": 29, "p": 31, "P": 32, "B": 299}


def to_txt(design: dict) -> str:
    rows = [r.replace(" ", "") for r in design["rows"]]
    h, w = len(rows), len(rows[0])
    assert all(len(r) == w for r in rows), f"{design['name']}: ragged rows"
    mons = design["monsters"]  # char -> (tile, hp, atk, def, effect)
    grid, hero_xy = [], None
    for y, r in enumerate(rows):
        out = []
        for x, c in enumerate(r):
            if c == "@":
                hero_xy = (x, y)
                out.append(0)
            elif c in mons:
                out.append(mons[c][0])
            else:
                out.append(LEGEND[c])
        grid.append(out)
    assert hero_xy, "no hero"
    boss = design["boss"]  # (hp, atk, def, effect)
    table = {t: (hp, atk, df, eff) for t, hp, atk, df, eff in mons.values()}
    table[299] = boss
    hp, atk, df, mdef, yk, bk, rk = design["hero"]
    lines = ["1", f"{w} {h}", ""] + ["\t".join(map(str, r)) for r in grid] + ["", design.get("bonuses", "1 1 0 75 200 0 0 0 0"),
                                                                            "", str(len(table))]
    lines += [f"{t} {v[0]} {v[1]} {v[2]} 0 {v[3]}" for t, v in sorted(table.items())]
    lines += ["", "0 0 0 0 0 0", "", f"{hp} {atk} {df} {mdef} 0 {yk} {bk} {rk} 0 {hero_xy[1]} {hero_xy[0]}", ""]
    return "\n".join(lines)


def _parse_result(line: str) -> dict:
    r = dict(re.findall(r"(\w+)=(\S+)", line))
    r["solvable"] = r["solvable"] == "true"
    for k in ("hp", "atk", "def", "mdef", "states", "wins", "optimal", "nodes", "hashed", "decisions"):
        r[k] = int(r[k])
    r["time"] = float(r["time"])
    if r["hashed"] > 64:
        raise RuntimeError(f"{r['hashed']} door/monster nodes: the Java 64-bit state hash is no longer exact")
    return r


def java_solve_many(txts: list[str]) -> list[dict]:
    """Solve several maps in ONE JVM (Main --batch): one RESULT line per map, in order."""
    if not txts:
        return []
    out = subprocess.run(["java", "-cp", str(JAVA_CP), "Main", "--batch", "--quiet"], input="\n".join(txts),
                         capture_output=True, text=True, timeout=7200).stdout
    res = [_parse_result(l) for l in out.splitlines() if l.startswith("RESULT ")]
    if len(res) != len(txts):
        raise RuntimeError(f"Java batch returned {len(res)} results for {len(txts)} maps: {out[-500:]}")
    return res


def java_solve(txt: str) -> dict:
    return java_solve_many([txt])[0]


class Floor:
    def __init__(self, path: Path):
        self.path = path
        self.sc = load_ai_floor(str(path))
        extra = {tid: m.id for tid, m in self.sc.monsters.items() if tid not in TILE_ENEMIES}
        self.gd = GameData(custom_monsters=build_monsters_lookup(self.sc.monsters),
                           custom_items=build_item_effects(self.sc.item_bonuses),
                           custom_shops=build_shop_def(self.sc.shop, self.sc.name), extra_enemy_tiles=extra)
        self.floor = self.sc.floors[0]
        self.lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def state_txt(self, hero, removed) -> str:
        """The floor as it stands in a mid-game state: removed tiles cleared, hero line replaced."""
        h = self.floor.height
        grid = [row.split() for row in self.lines[2:2 + h]]
        for (x, y) in removed:
            grid[y][x] = "0"
        hero_line = (f"{hero.hp} {hero.atk} {hero.def_} {hero.mdef} {hero.money} {hero.keys.yellow} {hero.keys.blue} "
                     f"{hero.keys.red} 0 {hero.y} {hero.x}")
        return "\n".join(self.lines[:2] + ["\t".join(r) for r in grid] + self.lines[2 + h:-1] + [hero_line]) + "\n"

    def best(self, hero=None, removed=None) -> dict:
        if hero is None:
            return java_solve(self.path.read_text(encoding="utf-8"))
        return java_solve(self.state_txt(hero, removed or ()))

    def engine(self) -> BFSSolver:
        """Only used for its action enumeration / application helpers, never for search."""
        return BFSSolver(self.floor, self.sc.hero.copy(), game_data=self.gd, goal=self.sc.goal)

    def start(self, s: BFSSolver) -> SolverState:
        hero, removed, shop = s.initial_hero.copy(), set(s.initial_removed), {}
        s._eat_items(hero, removed, shop)
        return SolverState(hero=hero, removed=frozenset(removed), route=[], decisions=0, shop_purchases=shop)


def analyse(path: Path, decisions: bool, rollouts: int, heuristic: bool = True) -> dict:
    f = Floor(path)
    clock = time.perf_counter()
    r = f.best()
    timing = {"java_root": round(time.perf_counter() - clock, 2)}
    rep = {"floor": path.stem, "solvable": r["solvable"], "states": r["states"], "wins": r["wins"],
           "optimal_solutions": r["optimal"], "bfs_s": r["time"]}
    h0 = f.sc.hero
    rep["hero0"] = f"HP {h0.hp} ATK {h0.atk} DEF {h0.def_} keys y{h0.keys.yellow} b{h0.keys.blue} r{h0.keys.red}"
    rep["enemies_total"] = sum(1 for row in f.floor.map for v in row if f.gd.is_enemy(v))
    if r["solvable"]:
        rep.update(target_hp=r["hp"], target_atk=r["atk"], target_def=r["def"], ref_steps=r["decisions"])
    s = f.engine()
    clock = time.perf_counter()
    if r["solvable"] and decisions:
        # Walk an optimal route in engine actions: at every state keep the child whose Java optimum is highest.
        state, per, fights = f.start(s), [], 0
        while not s._is_goal_reached(state):
            kids = []
            for a in s._build_gamestate(state).get_actions(annotate=False):
                ns = s._apply_action(state, a)
                if ns is not None:
                    kids.append([a, ns, None])  # lethal-now children are never real options
            open_ = [k for k in kids if not s._is_goal_reached(k[1])]
            for k, q in zip(open_, java_solve_many([f.state_txt(k[1].hero, k[1].removed) for k in open_])):
                k[2] = q["hp"] if q["solvable"] else None
            for k in kids:
                if s._is_goal_reached(k[1]):
                    k[2] = k[1].hero.hp
            best_hp = max((k[2] for k in kids if k[2] is not None), default=None)
            if best_hp is None:
                rep["route_error"] = f"no winnable child at step {len(per)}"
                break
            a, ns, _ = next(k for k in kids if k[2] == best_hp)
            alts = [(f"{k[0].type.value}({k[0].x},{k[0].y})", k[2]) for k in kids if k[0] is not a]
            per.append({"step": len(per), "action": f"{a.type.value}({a.x},{a.y})", "value": best_hp,
                        "alternatives": len(alts), "losing": sum(hp is None for _, hp in alts),
                        "suboptimal": sum(hp is not None and hp < best_hp for _, hp in alts), "alts": alts})
            fights += a.type.value == "fight"
            state = ns
        rep["decisions"] = per
        rep["enemies_killed"] = fights
        rep["route"] = [d["action"] for d in per]
        drift = {d["value"] for d in per} - {r["hp"]}
        if drift:
            rep["value_drift"] = sorted(drift)  # Java optimum from a mid-state differs from the root optimum
        real = [d for d in per if d["alternatives"]]
        rep["critical"] = sum(d["losing"] > 0 for d in per)
        rep["forced"] = sum(d["alternatives"] > 0 and d["losing"] == d["alternatives"] for d in per)
        rep["lose_share"] = round(sum(d["losing"] / d["alternatives"] for d in real) / max(1, len(real)), 3)
    timing["decisions_java_batched"] = round(time.perf_counter() - clock, 2)
    clock = time.perf_counter()
    if rollouts:
        rng, wins = random.Random(0), 0
        for _ in range(rollouts):
            st = f.start(s)
            while not s._is_goal_reached(st):
                kids = [k for k in (s._apply_action(st, a) for a in s._build_gamestate(st).get_actions(annotate=False)) if k]
                if not kids:
                    break
                st = rng.choice(kids)
            wins += s._is_goal_reached(st)
        rep["random_win"] = round(wins / rollouts, 3)
        st = f.start(s)
        while not s._is_goal_reached(st):
            kids = [k for k in (s._apply_action(st, a) for a in s._build_gamestate(st).get_actions(annotate=False)) if k]
            if not kids:
                break
            st = max(kids, key=lambda k: k.hero.hp)
        rep["greedy"] = {"boss_killed": s._is_goal_reached(st), "hp": st.hero.hp}
    timing["random_rollouts_python"] = round(time.perf_counter() - clock, 2)
    clock = time.perf_counter()
    if heuristic:
        from mota.optimizer import evaluator as ev
        ev.configure_scenario(str(path))
        h = ev.evaluate_heuristic_only()
        rep["heuristic"] = {"boss_killed": bool(h.get("goal_reached")), "final_hp": (h.get("details") or {}).get("final_hp"),
                            "score": h.get("total")}
    timing["heuristic_python"] = round(time.perf_counter() - clock, 2)
    rep["timing_s"] = timing
    return rep


def summary(rep: dict) -> str:
    if not rep["solvable"]:
        return f"{rep['floor']:10s} UNSOLVABLE ({rep['states']} states, {rep['bfs_s']} s)"
    out = (f"{rep['floor']:10s} optHP {rep['target_hp']:4d} (ATK {rep['target_atk']} DEF {rep['target_def']}) "
           f"from {rep['hero0']}; {rep['ref_steps']} decisions, {rep.get('enemies_killed', '?')}/{rep['enemies_total']} fights, "
           f"{rep['states']} states, {rep['wins']} winning sets / {rep['optimal_solutions']} optimal ({rep['bfs_s']} s)")
    if rep.get("timing_s"):
        out += f"\n{'':10s} time: " + ", ".join(f"{k} {v}s" for k, v in rep["timing_s"].items())
    if rep.get("value_drift"):
        out += f"\n{'':10s} WARNING mid-state optimum drift {rep['value_drift']}"
    if rep.get("route_error"):
        out += f"\n{'':10s} WARNING {rep['route_error']}"
    if "critical" in rep:
        out += f"\n{'':10s} critical {rep['critical']}, forced {rep['forced']}, lose share {rep['lose_share']:.2f}"
    if "random_win" in rep:
        g = rep["greedy"]
        out += f"; random win {rep['random_win']:.3f}; greedy {'kill HP ' + str(g['hp']) if g['boss_killed'] else 'fail'}"
    if "heuristic" in rep:
        h = rep["heuristic"]
        out += f"; heuristic {'kill HP ' + str(h['final_hp']) if h['boss_killed'] else 'fail'}"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "analyse", "register", "tune"])
    ap.add_argument("targets", nargs="*")
    ap.add_argument("--decisions", action="store_true")
    ap.add_argument("--rollouts", type=int, default=0)
    ap.add_argument("--no-heuristic", action="store_true")
    ap.add_argument("--json", help="write the full report(s) here")
    a = ap.parse_args()
    HAND.mkdir(parents=True, exist_ok=True)
    if a.cmd == "build":
        sys.path.insert(0, str(ROOT / "scripts"))
        from hand_floor_designs import DESIGNS
        for d in DESIGNS:
            if a.targets and d["name"] not in a.targets:
                continue
            p = HAND / f"{d['name']}.txt"
            p.write_text(to_txt(d), encoding="utf-8")
            print(f"wrote {p.relative_to(ROOT)}")
        return
    if a.cmd == "tune":
        for t in a.targets:
            p = HAND / f"{t}.txt"
            lines = p.read_text(encoding="utf-8").rstrip().splitlines()
            hero = lines[-1].split()

            def solve_at(hps: list[int]) -> list[dict]:
                return java_solve_many(["\n".join(lines[:-1] + [" ".join([str(hp)] + hero[1:])]) + "\n" for hp in hps])
            design = int(hero[0])
            lo, hi = 1, design
            if not solve_at([hi])[0]["solvable"]:
                print(f"{t}: unsolvable at HP {hi}")
                continue
            while lo < hi:
                mid = (lo + hi) // 2
                if solve_at([mid])[0]["solvable"]:
                    hi = mid
                else:
                    lo = mid + 1
            grid = list(range(hi, min(design, hi + 120) + 1))
            res = solve_at(grid)
            unique = [hp for hp, r in zip(grid, res) if r["wins"] == 1]
            print(f"{t}: minimum start HP {hi}; design HP {design}: opt end HP {solve_at([design])[0]['hp']}")
            print("   start HP -> opt end HP / distinct winning sets: " +
                  ", ".join(f"{hp}:{r['hp']}/{r['wins']}" for hp, r in zip(grid, res) if (hp - hi) % 5 == 0))
            print(f"   largest start HP with a UNIQUE winning set (<= min+120): {max(unique) if unique else None}")
        return
    if a.cmd == "analyse":
        reps = []
        for t in a.targets:
            p = Path(t) if Path(t).exists() else HAND / f"{t}.txt"
            rep = analyse(p, a.decisions, a.rollouts, heuristic=not a.no_heuristic)
            reps.append(rep)
            print(summary(rep), flush=True)
            if a.decisions and rep.get("decisions"):
                for d in rep["decisions"]:
                    if d["losing"] or d["suboptimal"]:
                        bad = ", ".join(f"{n}->{'LOSE' if hp is None else hp}" for n, hp in d["alts"] if hp is None or hp < rep["target_hp"])
                        print(f"   {d['step']:2d} {d['action']:22s} {d['losing']}/{d['alternatives']} lose | {bad}")
        if a.json:
            Path(a.json).write_text(json.dumps(reps, indent=1), encoding="utf-8")
        return
    man_p = HAND / "manifest.json"
    man = json.loads(man_p.read_text(encoding="utf-8")) if man_p.exists() else {"generator": "hand-designed (scripts/hand_floor_designs.py)", "floors": []}
    floors = {f["name"]: f for f in man["floors"]}
    for t in a.targets:
        rep = analyse(HAND / f"{t}.txt", True, 500)
        assert rep["solvable"], f"{t} unsolvable"
        floors[t] = {"name": t, "file": f"data/floors/hand/{t}.txt",
                     **{k: rep[k] for k in ("target_hp", "target_atk", "target_def", "ref_steps", "enemies_total",
                                            "enemies_killed", "critical", "forced", "lose_share", "random_win",
                                            "heuristic", "greedy", "wins", "optimal_solutions")},
                     "solver": "java", "solver_states": rep["states"]}
        print(summary(rep))
    man["floors"] = sorted(floors.values(), key=lambda f: f["name"])
    man_p.write_text(json.dumps(man, indent=2), encoding="utf-8")
    print(f"manifest: {man_p.relative_to(ROOT)} ({len(man['floors'])} floors)")


if __name__ == "__main__":
    main()
