"""
Scorer guarantees for boss floors — no network.

The boss-kill penalty must not depend on the floor appearing in BFS_REFERENCE:
an unknown boss floor whose boss survives must still be penalised, otherwise the
reliability harness would count it as a clean success.

Run: python -m mota.tests.test_boss_scoring
"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from mota.benchmark.scorer import score_run, BFS_REFERENCE
from mota.optimizer import evaluator as ev

PASSED = FAILED = 0


def check(label, cond):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK  {label}")
    else:
        FAILED += 1
        print(f"  FAIL {label}")


def fresh(floor: str):
    ev.configure_scenario(str(_root / "data" / "floors" / f"{floor}.txt"))
    return ev._create_state()


print("\n--- boss-goal scoring ---")
for floor in ("simple", "complex"):
    state = fresh(floor)
    check(f"{floor}: goal is boss", state.goal == "boss")
    check(f"{floor}: boss alive at start", not state.goal_reached)

    r = score_run(state, fixture_id=floor)
    check(f"{floor}: reports goal_reached", r.get("goal_reached") is False)
    check(f"{floor}: boss_not_killed recorded", "boss_not_killed" in r["violations"])
    check(f"{floor}: score halved below 0.5", r["total"] < 0.5)

    # Unknown fixture id => not in BFS_REFERENCE by that key. The penalty must persist.
    unknown = "some-unregistered-floor-id"
    check(f"{floor}: fixture id genuinely unknown", unknown not in BFS_REFERENCE)
    r2 = score_run(state, fixture_id=unknown)
    check(f"{floor}: boss_not_killed survives unknown fixture", "boss_not_killed" in r2["violations"])
    check(f"{floor}: halving survives unknown fixture", r2["total"] < 0.5)

print("\n--- harness success criterion ---")
import run_reliability as rr  # noqa: E402

check("simple/complex are treated as boss floors", set(rr.BOSS_FLOORS) == {"simple", "complex"})

state = fresh("simple")
res = score_run(state, fixture_id="simple")
# Mirror the harness decision without an API call.
died = (res["details"]["final_hp"] or 0) <= 0
boss_killed = res.get("goal_reached")
check("surviving boss is NOT a success", not (bool(boss_killed) and not died))

state2 = fresh("simple")
state2.goal_reached = True  # simulate the boss dying
res2 = score_run(state2, fixture_id="simple")
check("killed boss has no boss_not_killed", "boss_not_killed" not in res2["violations"])
check("killed boss reports goal_reached", res2.get("goal_reached") is True)
check("killed boss is not halved", res2["total"] > res["total"])

print("\n--- two-tier outcome (success > alive failure > death; hp_ratio only on success) ---")
safe = fresh("simple")                       # boss alive, hero alive
r_safe = score_run(safe, fixture_id="simple")
check("safe non-kill: success False", r_safe["success"] is False)
check("safe non-kill: hp_ratio None", r_safe["hp_ratio"] is None)
check("safe non-kill: goal_score < 0.5", r_safe["goal_score"] < 0.5)

kill = fresh("simple")
kill.goal_reached = True
kill.hero.hp = 2                             # the observed kill state
r_kill = score_run(kill, fixture_id="simple")
check("kill at HP=2: success True", r_kill["success"] is True)
check("kill at HP=2: hp_ratio = 2/13", abs(r_kill["hp_ratio"] - 2 / 13) < 1e-3)
check("kill at HP=2: goal_score in [0.5, 1]", 0.5 <= r_kill["goal_score"] <= 1.0)

opt = fresh("simple")
opt.goal_reached = True
opt.hero.hp = 13                             # BFS optimum
r_opt = score_run(opt, fixture_id="simple")
check("BFS-optimal kill: goal_score = 1.0", abs(r_opt["goal_score"] - 1.0) < 1e-9)
check("BFS-optimal kill outranks HP=2 kill", r_opt["goal_score"] > r_kill["goal_score"])

def _kill_n(state, n: int):
    """Mark the first n enemy tiles as removed (simulates kills without fighting)."""
    done = 0
    for y in range(state.floor.height):
        for x in range(state.floor.width):
            if done >= n:
                return
            if state.gd.is_enemy(state.floor.map[y][x]) and (x, y) not in state.removed:
                state.removed.add((x, y))
                done += 1


lethal = fresh("complex")
_kill_n(lethal, 14)                          # the observed 35B trajectory: 14 kills ...
lethal.goal_reached = True                   # ... killing blow on the boss landed ...
lethal.hero.hp = -82                         # ... but the hero died
r_lethal = score_run(lethal, fixture_id="complex")
csafe = fresh("complex")
_kill_n(csafe, 10)                           # heuristic baseline: 10 kills, alive, boss untouched
r_csafe = score_run(csafe, fixture_id="complex")
check("lethal boss attempt: success False", r_lethal["success"] is False)
check("lethal boss attempt: hp_ratio None", r_lethal["hp_ratio"] is None)
check("legacy composite INVERTS order (documents the bug)", r_lethal["total"] > r_csafe["total"])
check("goal_score ranks death below safe failure", r_lethal["goal_score"] < r_csafe["goal_score"])
check("goal_score ranks any success above any failure",
      min(r_kill["goal_score"], r_opt["goal_score"]) > max(r_safe["goal_score"], r_csafe["goal_score"], r_lethal["goal_score"]))

print(f"\nResults: {PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
