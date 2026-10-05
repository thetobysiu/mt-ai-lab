"""
Project adapter tests — mota/game/project.py (no network).

Gate 1: GameData.from_project(24/project) must reproduce the hard-coded engine tables for every
id they share (monsters, tile->item/enemy/door/stairs maps, numeric item effects, shop choices).
Gate 2: 51/project loads, every floor builds a GameState, and a heuristic episode on its MT1
completes without exception. DEFAULT_GAME_DATA is untouched (baselines stay reproducible).

Run: python -m mota.tests.test_project_adapter
"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from mota.game import data as D  # noqa: E402
from mota.game.data import DEFAULT_GAME_DATA, GameData  # noqa: E402
from mota.game.project import MotaProject, builtin_root  # noqa: E402
from mota.game.floor_loader import load_floor  # noqa: E402
from mota.game.state import GameState  # noqa: E402
from mota.game.types import DoorType  # noqa: E402

PASSED = FAILED = 0


def check(label, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK  {label}")
    else:
        FAILED += 1
        print(f"  FAIL {label} {extra}")


print("\n--- gate 1: 24/project reproduces the built-in tables ---")
p24 = MotaProject.load(builtin_root())
gd24 = p24.game_data()
check("27 floor ids", len(p24.floor_ids) == 27 and p24.floor_ids[0] == "MT0")
mons = p24.monsters()
diff = [(k, (m.hp, m.atk, m.def_, m.money, m.exp), (mons[k].hp, mons[k].atk, mons[k].def_, mons[k].money, mons[k].exp))
        for k, m in D.MONSTERS.items() if k in mons and (m.hp, m.atk, m.def_, m.money, m.exp) != (mons[k].hp, mons[k].atk, mons[k].def_, mons[k].money, mons[k].exp)]
check(f"monster stats identical for {sum(1 for k in D.MONSTERS if k in mons)} shared ids", not diff, str(diff[:3]))
spec_diff = [k for k, m in D.MONSTERS.items() if k in mons and m.specials != mons[k].specials]
check("monster specials identical", not spec_diff, str(spec_diff[:5]))
t = p24.tile_tables()
check("enemy tiles ⊇ built-in TILE_ENEMIES", all(t["enemies"].get(tid) == name for tid, name in D.TILE_ENEMIES.items()),
      str([(tid, name, t["enemies"].get(tid)) for tid, name in D.TILE_ENEMIES.items() if t["enemies"].get(tid) != name][:3]))
check("item tiles ⊇ built-in TILE_ITEMS", all(t["items"].get(tid) == name for tid, name in D.TILE_ITEMS.items()),
      str([(tid, name, t["items"].get(tid)) for tid, name in D.TILE_ITEMS.items() if t["items"].get(tid) != name][:3]))
check("door tiles identical (ICE 6, Y81, B82, R83)", {k: v for k, v in t["doors"].items() if k in D.TILE_DOORS} == D.TILE_DOORS
      and t["doors"].get(6) == DoorType.ICE, str(t["doors"]))
check("stairs 87/88", t["stairs"] == D.TILE_STAIRS)
check("npc tiles ⊇ built-in TILE_NPCS", all(t["npcs"].get(tid) == name for tid, name in D.TILE_NPCS.items()))
check("walls include 1,2,3", D.TILE_WALLS <= t["walls"])
eff = p24.item_effects()
num_keys = ("hp", "atk", "def", "mdef", "money", "keys.yellow", "keys.blue", "keys.red")
# The built-in table was transcribed by hand; items.js (source of truth) differs for these nine.
# Kept in data.py for reproducibility of every recorded baseline — see THESIS_STATE (data-fidelity note).
KNOWN_BUILTIN_DISCREPANCIES = {
    "greenGem": ({"mdef": 3}, {"mdef": 5}),
    "shield2": ({"def": 20}, {"def": 30}),
    "sword3": ({"atk": 40}, {"atk": 70}),
    "shield3": ({"def": 40}, {"def": 85}),
    "sword4": ({"atk": 80}, {"atk": 120}),
    "shield4": ({"def": 80}, {"def": 120}),
    "sword5": ({"atk": 160}, {"atk": 150}),
    "shield5": ({"def": 100}, {"def": 190}),
    "pack": ({"money": 500}, {"money": 300}),
}
eff_diff = {}
for iid, e in D.ITEM_EFFECTS.items():
    want = {k: v for k, v in e.items() if k in num_keys}
    got = {k: v for k, v in eff.get(iid, {}).items() if k in num_keys}
    if want and want != got:
        eff_diff[iid] = (want, got)
check("numeric item effects identical except the 4 known transcription discrepancies",
      eff_diff == KNOWN_BUILTIN_DISCREPANCIES, str({k: v for k, v in eff_diff.items() if KNOWN_BUILTIN_DISCREPANCIES.get(k) != v}))
shops = p24.shops()
check("moneyShop1 parsed: 25g, hp+800 / atk+4 / def+4",
      shops.get("moneyShop1", {}).get("cost") == 25 and shops["moneyShop1"]["currency"] == "money"
      and sorted(str(c["changes"]) for c in shops["moneyShop1"]["choices"]) == sorted(str(c["changes"]) for c in D.SHOPS["moneyShop1"]["choices"]),
      str(shops.get("moneyShop1")))
check("expShop1 parsed with exp currency", shops.get("expShop1", {}).get("currency") == "exp"
      and any(c["changes"].get("atk") == 7 and c["changes"].get("hp") == 1000 for c in shops["expShop1"]["choices"]), str(shops.get("expShop1")))
check("DEFAULT_GAME_DATA untouched (module tables)", DEFAULT_GAME_DATA.tile_items is D.TILE_ITEMS and DEFAULT_GAME_DATA.get_shops() is D.SHOPS)
check("GameData.from_project available", callable(getattr(GameData, "from_project", None)))

print("\n--- gate 1b: 24/project MT3 through the adapter plays like the built-in ---")
mt3 = load_floor(builtin_root() / "floors" / "MT3.js")
hero = p24.initial_hero()
hero.x, hero.y = mt3.down_floor
s_builtin = GameState(floor=mt3, hero=hero.copy(), goal="clear_all_enemies", max_turns=300)
s_adapter = GameState(floor=mt3, hero=hero.copy(), goal="clear_all_enemies", max_turns=300, game_data=gd24)
a1 = sorted(a.label() for a in s_builtin.get_actions())
a2 = sorted(a.label() for a in s_adapter.get_actions())
check("identical initial action set on MT3", a1 == a2, f"{len(a1)} vs {len(a2)}: {set(a1) ^ set(a2)}")
check("same enemy count / map size on MT3", s_builtin.remaining_enemies() == s_adapter.remaining_enemies()
      and len(s_builtin.format_floor_map()) > 0 and len(s_adapter.format_floor_map()) > 0)

from mota.paths import GAME_ROOT  # noqa: E402

root51 = GAME_ROOT / "51" / "project"
if not root51.is_dir():
    print("\n--- gate 2: skipped (data/games/51/project is not distributed) ---")
else:
    print("\n--- gate 2: 51/project loads and plays ---")
    p51 = MotaProject.load(root51)
    gd51 = p51.game_data()
    check("51 floor ids", len(p51.floor_ids) == 51)
    check("51 monsters parsed (stats differ from 24)", len(p51.monsters()) >= 60 and p51.monsters()["greenSlime"].hp == 35)
    check("51 gem effects via core.values (redGem +1 ATK)", gd51.get_item_effect("redGem").get("atk") == 1, str(gd51.get_item_effect("redGem")))
    check("51 unsupported lists populated (doors with green/steel keys)", "doors" in p51.unsupported, str(p51.unsupported.keys()))
    built = 0
    errors = []
    for fid in p51.floor_ids:
        try:
            fl = load_floor(root51 / "floors" / f"{fid}.js")
            h = p51.initial_hero()
            h.x, h.y = fl.down_floor if fid != "MT0" else (h.x, h.y)
            st = GameState(floor=fl, hero=h, goal="clear_all_enemies", max_turns=300, game_data=gd51)
            st.get_actions()
            st.format_state()
            built += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{fid}: {type(e).__name__}: {e}")
    check(f"every 51 floor builds a GameState and enumerates actions ({built}/51)", built == 51, "; ".join(errors[:3]))

    from mota.optimizer import evaluator as ev  # noqa: E402
    desc = ev.configure_scenario(str(root51 / "floors" / "MT1.js"), project_root=root51)
    check("configure_scenario(project_root=51) accepted", "MT1" in desc, desc)
    res = ev.evaluate_with_callback(None)
    check("heuristic episode on 51/MT1 completes", isinstance(res.get("total"), float) and res["details"]["steps"] > 0,
          str({k: res.get(k) for k in ("total", "goal_reached", "failed", "failure_reason")}))
    print(f"     51/MT1 heuristic: total={res['total']:.3f} steps={res['details']['steps']} HP={res['details']['final_hp']} goal={res.get('goal_reached')}")
    ev.configure_scenario(None)

print(f"\nResults: {PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
