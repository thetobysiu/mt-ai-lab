"""
Phase 1: Generate BFS ground truth for the redesigned fine-tuning pipeline.

Produces per-decision-point game states with BFS-optimal actions for MT3/MT4
floors with stat variations. Output is used for:
  - Phase 2: GEPA prompt alignment (fitness = per-decision BFS match)
  - Phase 3: CoT trace collection (teacher runs through these states)
  - Phase 4: Direct heuristic training baseline

Usage:
    cd mota-gepa
    python -m training.generate_bfs_ground_truth --output training/data/bfs_ground_truth.jsonl
    python -m training.generate_bfs_ground_truth --floors MT3 MT4 --variations 5
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

from mota.game.types import Hero, Keys
from mota.solver.data_generator import (
    generate_samples_from_floor,
    _vary_hero,
    _write_jsonl,
)
from mota.solver.bfs_solver import BFSSolver
from mota.game import floor_loader, hero_loader
from mota.game.data import GameData, DEFAULT_GAME_DATA
from mota.game import ai_floor_loader
from mota.game.ai_floor_loader import (
    ScenarioConfig, build_item_effects, build_monsters_lookup,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hero presets for MT3/MT4 variations
# ---------------------------------------------------------------------------

MT3_BASE_HERO = Hero(hp=860, atk=10, def_=10, mdef=0, money=4,
                     keys=Keys(yellow=1, blue=1, red=1), x=6, y=11)

MT4_BASE_HERO = Hero(hp=610, atk=23, def_=17, mdef=0, money=44,
                     keys=Keys(yellow=4, blue=2, red=1), x=6, y=0)


def _mt3_stat_variations(n: int, seed: int = 100) -> list[Hero]:
    """Generate n stat variations of the MT3 starting hero."""
    rng = random.Random(seed)
    variations = [MT3_BASE_HERO.copy()]  # always include base
    for _ in range(n - 1):
        h = MT3_BASE_HERO.copy()
        h.hp = max(200, int(h.hp * rng.uniform(0.7, 1.3)))
        h.atk = max(5, h.atk + rng.randint(-3, 3))
        h.def_ = max(5, h.def_ + rng.randint(-3, 3))
        h.money = max(0, h.money + rng.randint(-2, 10))
        h.keys = Keys(
            yellow=max(0, h.keys.yellow + rng.randint(-1, 2)),
            blue=max(0, h.keys.blue + rng.randint(-1, 1)),
            red=h.keys.red,
        )
        variations.append(h)
    return variations


def _mt4_stat_variations(n: int, seed: int = 200) -> list[Hero]:
    """Generate n stat variations of the MT4 starting hero (post-MT3 exit)."""
    rng = random.Random(seed)
    variations = [MT4_BASE_HERO.copy()]
    for _ in range(n - 1):
        h = MT4_BASE_HERO.copy()
        h.hp = max(300, int(h.hp * rng.uniform(0.7, 1.3)))
        h.atk = max(15, h.atk + rng.randint(-4, 4))
        h.def_ = max(10, h.def_ + rng.randint(-4, 4))
        h.money = max(0, h.money + rng.randint(-20, 30))
        h.keys = Keys(
            yellow=max(0, h.keys.yellow + rng.randint(-2, 3)),
            blue=max(0, h.keys.blue + rng.randint(-1, 2)),
            red=max(0, h.keys.red + rng.randint(0, 1)),
        )
        variations.append(h)
    return variations


# ---------------------------------------------------------------------------
# Floor loaders
# ---------------------------------------------------------------------------

def load_mt_floor(floor_id: str, project_dir: Path | None = None):
    """Load a project floor by floor_id (e.g. 'MT3')."""
    if project_dir is None:
        project_dir = _root.parent / "24"
    floor_path = project_dir / "project" / "floors" / f"{floor_id}.js"
    return floor_loader.load_floor(floor_path)


def load_ai_floor(name: str, test_dir: Path | None = None):
    """Load an AI test floor by name (e.g. 'simple', 'complex')."""
    search_dirs = [
        _root / "data" / "floors",
        _root.parent / "magic-tower-AI" / "test",
    ]
    if test_dir is not None:
        search_dirs.insert(0, test_dir)
    for d in search_dirs:
        if not d.exists():
            continue
        for txt_file in d.glob("*.txt"):
            if name in txt_file.stem:
                return ai_floor_loader.load_ai_floor(txt_file)
    raise FileNotFoundError(f"AI test floor not found: {name} (searched: {[str(d) for d in search_dirs]})")


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def generate_ground_truth(
    floors: list[str],
    n_variations: int = 5,
    output_path: Path | None = None,
    fmt: str = "json",
) -> list[dict]:
    """
    Generate BFS ground truth for specified floors with stat variations.
    
    Returns list of {input, output, metadata} dicts.
    """
    all_samples = []

    for floor_id in floors:
        log.info("=== Processing floor: %s ===", floor_id)

        if floor_id.startswith("MT"):
            floor_data = load_mt_floor(floor_id)

            if floor_id == "MT3":
                heroes = _mt3_stat_variations(n_variations)
            elif floor_id == "MT4":
                heroes = _mt4_stat_variations(n_variations)
            else:
                log.warning("Floor %s not configured, using base hero", floor_id)
                continue

            for vi, hero in enumerate(heroes):
                var_id = f"{floor_id}_v{vi}"
                hero.x, hero.y = floor_data.down_floor
                log.info("  Variation %s: HP=%d ATK=%d DEF=%d", var_id, hero.hp, hero.atk, hero.def_)

                samples = generate_samples_from_floor(
                    floor=floor_data,
                    hero=hero.copy(),
                    poi_depth=2,
                    poi_top_k=3,
                    fmt=fmt,
                )

                # Tag each sample with variation info
                for s in samples:
                    s["metadata"]["variation_id"] = var_id
                    s["metadata"]["hero_start"] = {
                        "hp": hero.hp, "atk": hero.atk, "def": hero.def_,
                        "money": hero.money,
                        "keys": {"y": hero.keys.yellow, "b": hero.keys.blue, "r": hero.keys.red},
                    }

                all_samples.extend(samples)
                log.info("  %s: %d samples", var_id, len(samples))

        elif floor_id in ("simple", "complex") or "单层" in floor_id or "ai_" in floor_id.lower() or "宿命" in floor_id or "无上" in floor_id:
            try:
                scenario = load_ai_floor(floor_id)
            except FileNotFoundError:
                log.warning("AI floor not found: %s", floor_id)
                continue

            custom_monsters = build_monsters_lookup(scenario.monsters)
            custom_items = build_item_effects(scenario.item_bonuses)
            extra_tiles = {tid: m.id for tid, m in scenario.monsters.items()}
            gd = GameData(
                custom_monsters=custom_monsters,
                custom_items=custom_items,
                extra_enemy_tiles=extra_tiles,
            )

            # AI complex floors need higher state limit (Java BFS: 703K states)
            ai_max_states = 800_000

            for i, fdata in enumerate(scenario.floors):
                hero = scenario.hero.copy()
                if i == 0:
                    hero.x, hero.y = fdata.down_floor

                samples = generate_samples_from_floor(
                    floor=fdata,
                    hero=hero,
                    game_data=gd,
                    poi_depth=2,
                    poi_top_k=3,
                    fmt=fmt,
                    max_states=ai_max_states,
                    goal=scenario.goal,
                )
                for s in samples:
                    s["metadata"]["variation_id"] = f"{floor_id}_f{i}"
                all_samples.extend(samples)
                log.info("  AI floor %s floor %d: %d samples", floor_id, i, len(samples))
        else:
            log.warning("Unknown floor type: %s", floor_id)

    log.info("Total: %d ground truth samples across %d floors", len(all_samples), len(floors))

    if output_path:
        _write_jsonl(all_samples, output_path)
        log.info("Wrote to %s", output_path)

    return all_samples


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: Generate BFS ground truth for fine-tuning pipeline"
    )
    parser.add_argument("--floors", nargs="+", default=["MT3", "MT4"],
                        help="Floors to generate (MT3, MT4, simple, complex)")
    parser.add_argument("--variations", type=int, default=5,
                        help="Number of hero stat variations per floor")
    parser.add_argument("--output", "-o",
                        default="training/data/bfs_ground_truth.jsonl")
    parser.add_argument("--fmt", default="json", choices=["json", "poi"])
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    output_path = Path(args.output)
    generate_ground_truth(
        floors=args.floors,
        n_variations=args.variations,
        output_path=output_path,
        fmt=args.fmt,
    )


if __name__ == "__main__":
    main()
