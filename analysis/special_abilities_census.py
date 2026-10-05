"""Which monster special abilities occur where: single-floor test maps and tower floors MT0–MT23 (engine tables)."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from mota.game.ai_floor_loader import load_ai_floor  # noqa: E402
from mota.game.data import TILE_ENEMIES, get_monster  # noqa: E402
from mota.game.floor_loader import load_floors_dir  # noqa: E402

NAMES = {1: "first strike", 2: "magic attack", 3: "solid", 4: "double attack", 5: "triple attack",
         6: "N-hit attack", 7: "break armour", 8: "counter attack", 9: "purify", 10: "mimic",
         11: "vampire", 12: "poison", 13: "weaken", 14: "curse", 18: "untargetable", 22: "fixed damage"}


def specials(s):
    return [x for x in (s if isinstance(s, list) else [s]) if x]


ROOT = Path("data/floors")
maps = [ROOT / "simple.txt", ROOT / "complex.txt", *sorted((ROOT / "hand").glob("hand*.txt")), *sorted((ROOT / "gen").glob("gen*.txt"))]
print("== single-floor test maps (monsters on the grid) ==")
for f in maps:
    sc = load_ai_floor(f)
    found = defaultdict(set)
    for row in sc.floors[0].map:
        for t in row:
            m = sc.monsters.get(t)
            if m:
                for s in specials(m.special):
                    found[NAMES.get(s, s)].add(f"{m.name}{' (boss)' if t == 299 else ''}")
    print(f"{f.stem:8s}", "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in sorted(found.items())) or "none")

print("\n== tower floors (engine monster table) ==")
floors = load_floors_dir(Path(__file__).resolve().parents[1] / "data" / "games" / "24" / "project" / "floors")
by_ability = defaultdict(lambda: defaultdict(set))
for fid, fl in floors.items():
    for row in fl.map:
        for t in row:
            mid = TILE_ENEMIES.get(t)
            if not mid:
                continue
            m = get_monster(mid)
            for s in specials(m.special):
                by_ability[NAMES.get(s, s)][mid].add(fid)
order = lambda fid: (int("".join(c for c in fid[2:] if c.isdigit()) or 0), fid)  # noqa: E731
for ab, mons in sorted(by_ability.items()):
    for mid, fids in sorted(mons.items()):
        print(f"{ab:15s} {mid:16s} {', '.join(sorted(fids, key=order))}")
