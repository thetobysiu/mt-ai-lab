"""Quick test: BFS on 单层-复杂 with goal='boss' and 200K state limit."""
import logging
import sys
import time
import json
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

from mota.game.ai_floor_loader import load_ai_floor, build_monsters_lookup, build_item_effects
from mota.game.data import GameData
from mota.solver.data_generator import generate_samples_from_floor

scenario = load_ai_floor(str(_root / ".." / "magic-tower-AI" / "test" / "单层-复杂.txt"))
custom_monsters = build_monsters_lookup(scenario.monsters)
custom_items = build_item_effects(scenario.item_bonuses)
extra_tiles = {tid: m.id for tid, m in scenario.monsters.items()}
gd = GameData(
    custom_monsters=custom_monsters,
    custom_items=custom_items,
    extra_enemy_tiles=extra_tiles,
)
hero = scenario.hero.copy()
fdata = scenario.floors[0]
hero.x, hero.y = fdata.down_floor

print(f"Goal: {scenario.goal}")
print(f"Hero: HP={hero.hp} ATK={hero.atk} DEF={hero.def_}")
print(f"Max states: 50000")

t0 = time.time()
samples = generate_samples_from_floor(
    floor=fdata,
    hero=hero,
    game_data=gd,
    poi_depth=2,
    poi_top_k=3,
    fmt="json",
    max_states=50_000,
    goal=scenario.goal,
)
elapsed = time.time() - t0

print(f"\nTime: {elapsed:.1f}s, Samples: {len(samples)}")
for s in samples:
    meta = s["metadata"]
    out = json.loads(s["output"])
    answer = out.get("answer", "?")
    print(f"  Decision {meta['decision_idx']}: answer={answer}, solver_hp={meta['solver_hp']}")

# Write to file
outpath = _root / "training" / "data" / "bfs_complex.jsonl"
with open(outpath, "w", encoding="utf-8") as f:
    for s in samples:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")
print(f"\nWrote {len(samples)} samples to {outpath}")
