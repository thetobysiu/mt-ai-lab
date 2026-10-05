"""
Training data generator for Architecture C (Algorithmic Distillation).

Generates (input, output) training pairs by:
  1. Running the BFS solver on each floor to find the optimal route
  2. At each decision point, snapshotting the game state
  3. Building a POI graph + macro-action target from the solver's solution
  4. Optionally augmenting with hero stat variations

Output: JSONL file where each line is {"input": ..., "output": ...}
"""
from __future__ import annotations

import copy
import json
import logging
import random
from pathlib import Path

from ..game.types import Hero, FloorData, Action, Keys
from ..game.state import GameState
from ..game.data import GameData, DEFAULT_GAME_DATA
from ..game import floor_loader
from ..game import hero_loader
from ..game import ai_floor_loader
from ..game.ai_floor_loader import ScenarioConfig, build_item_effects, build_monsters_lookup
from .bfs_solver import BFSSolver, SolverState
from .text_formatter import build_training_pair

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core: generate samples from a single floor + solver route
# ---------------------------------------------------------------------------

def generate_samples_from_floor(
    floor: FloorData,
    hero: Hero,
    game_data: GameData | None = None,
    max_decisions: int = 45,
    goal: str = "clear_all_enemies",
    poi_depth: int = 2,
    poi_top_k: int = 3,
    fmt: str = "json",
    max_states: int = 50_000,
) -> list[dict]:
    """
    Run BFS solver on a floor, then extract one training sample at each
    decision point along the optimal route.

    Returns list of {"input": str, "output": str} dicts.
    """
    gd = game_data or DEFAULT_GAME_DATA

    solver = BFSSolver(floor, hero, game_data=gd, max_decisions=max_decisions, goal=goal,
                       max_states=max_states)
    result = solver.solve()

    if result is None:
        log.warning("No solution found for floor %s", floor.floor_id)
        return []

    log.info(
        "Floor %s solved: %d decisions, final HP=%d (explored %d states)",
        floor.floor_id, result.decisions, result.hero.hp, solver.states_explored,
    )

    # Replay the route to get state snapshots at each decision point
    samples = []
    replay_hero = hero.copy()
    replay_removed: set[tuple[int, int]] = set()
    replay_shop: dict[str, list[str]] = {}

    # Initial greedy pickup (mirrors solver)
    solver._eat_items(replay_hero, replay_removed, replay_shop)

    for i, action in enumerate(result.route):
        # Snapshot BEFORE applying this action
        remaining_actions = result.route[i:]  # actions from here onwards
        pair = build_training_pair(
            floor=floor,
            hero=replay_hero.copy(),
            removed=set(replay_removed),
            optimal_actions=remaining_actions,
            game_data=gd,
            poi_depth=poi_depth,
            poi_top_k=poi_top_k,
            fmt=fmt,
        )
        if pair:
            pair["metadata"] = {
                "floor_id": floor.floor_id,
                "decision_idx": i,
                "total_decisions": result.decisions,
                "solver_hp": result.hero.hp,
            }
            samples.append(pair)

        # Apply the action to advance the replay state
        gs = GameState(
            floor=floor,
            hero=replay_hero,
            goal=goal,
            game_data=gd,
            lookahead_depth=0,
            _removed=replay_removed,
        )
        gs.apply_action(action)
        replay_hero = gs.hero
        replay_removed = gs.removed

        # Greedy pickup after each decision (mirrors solver)
        solver._eat_items(replay_hero, replay_removed, replay_shop)

    log.info("Generated %d training samples from floor %s", len(samples), floor.floor_id)
    return samples


# ---------------------------------------------------------------------------
# Augmentation: vary hero stats to multiply training data
# ---------------------------------------------------------------------------

def augment_sample(
    floor: FloorData,
    base_hero: Hero,
    base_removed: set[tuple[int, int]],
    optimal_actions: list[Action],
    game_data: GameData | None = None,
    n_variations: int = 10,
    poi_depth: int = 2,
    poi_top_k: int = 3,
    fmt: str = "json",
) -> list[dict]:
    """
    Generate augmented samples by varying hero stats around the base.
    Each variation recomputes the POI graph (damage values change with stats).
    """
    gd = game_data or DEFAULT_GAME_DATA
    augmented = []

    for _ in range(n_variations):
        varied_hero = _vary_hero(base_hero)

        pair = build_training_pair(
            floor=floor,
            hero=varied_hero,
            removed=set(base_removed),
            optimal_actions=optimal_actions,
            game_data=gd,
            poi_depth=poi_depth,
            poi_top_k=poi_top_k,
            fmt=fmt,
        )
        if pair:
            pair["metadata"] = {"augmented": True, "floor_id": floor.floor_id}
            augmented.append(pair)

    return augmented


def _vary_hero(hero: Hero) -> Hero:
    """Create a random stat variation of the hero."""
    h = hero.copy()
    # HP: ±20-50%
    hp_factor = random.uniform(0.5, 1.5)
    h.hp = max(1, int(h.hp * hp_factor))
    # ATK: ±1-5
    h.atk = max(1, h.atk + random.randint(-5, 5))
    # DEF: ±1-5
    h.def_ = max(0, h.def_ + random.randint(-5, 5))
    # MDEF: ±0-3
    h.mdef = max(0, h.mdef + random.randint(-3, 3))
    # Money: ±0-50%
    money_factor = random.uniform(0.5, 1.5)
    h.money = max(0, int(h.money * money_factor))
    # Keys: random 0-3
    h.keys = Keys(
        yellow=random.randint(0, 3),
        blue=random.randint(0, 2),
        red=random.randint(0, 1),
    )
    return h


# ---------------------------------------------------------------------------
# Batch generation: run across multiple floors
# ---------------------------------------------------------------------------

def generate_from_project_floors(
    project_dir: Path,
    floor_ids: list[str] | None = None,
    augment_per_sample: int = 0,
    output_path: Path | None = None,
    poi_depth: int = 2,
    poi_top_k: int = 3,
    fmt: str = "json",
) -> list[dict]:
    """
    Generate training data from the MOTA project floors.

    Args:
        project_dir: Path to the mota24 project root (contains project/ dir)
        floor_ids: Specific floor IDs to process (default: all)
        augment_per_sample: Number of augmented variations per sample (0 = none)
        output_path: Optional path to write JSONL output
        poi_depth: POI graph depth
        poi_top_k: Top-k branches per level
    """
    all_samples = []

    # Load floor sequence and initial hero
    floor_seq = hero_loader.load_floor_sequence(project_dir / "project" / "data.js")
    initial_hero = hero_loader.load_initial_hero(project_dir / "project" / "data.js")

    if floor_ids is None:
        floor_ids = floor_seq

    hero = initial_hero.copy()
    for fid in floor_ids:
        floor_path = project_dir / "project" / "floors" / f"{fid}.js"
        if not floor_path.exists():
            log.warning("Floor file not found: %s", floor_path)
            continue

        try:
            floor_data = floor_loader.load_floor(floor_path)
        except Exception as e:
            log.warning("Failed to load floor %s: %s", fid, e)
            continue

        # Set hero position to floor entrance
        hero.x, hero.y = floor_data.down_floor

        samples = generate_samples_from_floor(
            floor=floor_data,
            hero=hero.copy(),
            poi_depth=poi_depth,
            poi_top_k=poi_top_k,
            fmt=fmt,
        )
        all_samples.extend(samples)

        # Carry hero stats forward: solve the floor and use the final hero
        solver = BFSSolver(floor_data, hero.copy(), max_decisions=45)
        result = solver.solve()
        if result is not None and result.hero.hp > 0:
            hero = result.hero.copy()
            log.info("Floor %s: hero after solve HP=%d ATK=%d DEF=%d",
                     fid, hero.hp, hero.atk, hero.def_)

        # Augmentation
        if augment_per_sample > 0 and samples:
            for sample in samples:
                # Re-derive the state from metadata for augmentation
                # (simplified: augment from the base hero for this floor)
                aug = augment_sample(
                    floor=floor_data,
                    base_hero=hero.copy(),
                    base_removed=set(),
                    optimal_actions=[],  # simplified: POI from scratch
                    n_variations=augment_per_sample,
                    poi_depth=poi_depth,
                    poi_top_k=poi_top_k,
                    fmt=fmt,
                )
                all_samples.extend(aug)

        log.info("Floor %s: %d base samples", fid, len(samples))

    if output_path:
        _write_jsonl(all_samples, output_path)
        log.info("Wrote %d samples to %s", len(all_samples), output_path)

    return all_samples


def generate_from_ai_test_floors(
    test_dir: Path,
    output_path: Path | None = None,
    augment_per_sample: int = 0,
    poi_depth: int = 2,
    poi_top_k: int = 3,
    fmt: str = "json",
) -> list[dict]:
    """
    Generate training data from AI test floor .txt files.
    """
    all_samples = []

    for txt_file in sorted(test_dir.glob("*.txt")):
        if txt_file.name == "ReadMe.txt":
            continue

        try:
            scenario = ai_floor_loader.load_ai_floor(txt_file)
        except Exception as e:
            log.warning("Failed to load AI floor %s: %s", txt_file.name, e)
            continue

        # Build GameData from ScenarioConfig
        custom_monsters = build_monsters_lookup(scenario.monsters)
        custom_items = build_item_effects(scenario.item_bonuses)
        extra_enemy_tiles = {tid: m.id for tid, m in scenario.monsters.items()}
        gd = GameData(
            custom_monsters=custom_monsters,
            custom_items=custom_items,
            extra_enemy_tiles=extra_enemy_tiles,
        )

        for i, floor_data in enumerate(scenario.floors):
            hero = scenario.hero.copy()
            if i == 0:
                hero.x, hero.y = floor_data.down_floor

            samples = generate_samples_from_floor(
                floor=floor_data,
                hero=hero,
                game_data=gd,
                poi_depth=poi_depth,
                poi_top_k=poi_top_k,
                fmt=fmt,
            )
            all_samples.extend(samples)

        log.info("AI floor %s: %d samples", txt_file.name, len(all_samples))

    if output_path:
        _write_jsonl(all_samples, output_path)
        log.info("Wrote %d samples to %s", len(all_samples), output_path)

    return all_samples


# ---------------------------------------------------------------------------
# Synthetic map generation
# ---------------------------------------------------------------------------

def generate_from_synthetic_maps(
    n_maps: int = 500,
    augment_per_sample: int = 0,
    poi_depth: int = 2,
    poi_top_k: int = 3,
    fmt: str = "json",
) -> list[dict]:
    """
    Generate training data from randomly generated solvable maps.
    """
    from .synthetic_maps import generate_random_floor

    all_samples = []
    difficulties = ["easy", "medium", "hard"]
    sizes = [5, 7, 9, 11]
    generated = 0

    for i in range(n_maps):
        diff = difficulties[i % len(difficulties)]
        size = sizes[i % len(sizes)]
        floor_id = f"SYN{i:05d}"

        result = generate_random_floor(
            size=size,
            difficulty=diff,
            floor_id=floor_id,
            seed=42 + i,
        )
        if result is None:
            continue

        floor_data, hero = result
        samples = generate_samples_from_floor(
            floor=floor_data,
            hero=hero,
            poi_depth=poi_depth,
            poi_top_k=poi_top_k,
            fmt=fmt,
        )
        all_samples.extend(samples)
        generated += 1

        if generated % 100 == 0:
            log.info("Synthetic: generated %d maps → %d samples so far",
                     generated, len(all_samples))

    log.info("Synthetic total: %d maps → %d samples", generated, len(all_samples))
    return all_samples


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------

def _write_jsonl(samples: list[dict], path: Path) -> None:
    """Write samples as JSONL (one JSON object per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for sample in samples:
            json.dump(sample, f, ensure_ascii=False)
            f.write("\n")


def load_jsonl(path: Path) -> list[dict]:
    """Load samples from a JSONL file."""
    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Generate Architecture C training data")
    parser.add_argument("--project-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "games" / "24",
                        help="MOTA tower root containing project/ dir (default: 24-layer tower)")
    parser.add_argument("--ai-test-dir", type=Path, default=None,
                        help="Path to AI test floors (data/floors/)")
    parser.add_argument("--output", "-o", type=Path, default=Path("training_data.jsonl"),
                        help="Output JSONL path")
    parser.add_argument("--floors", nargs="*", default=None,
                        help="Specific floor IDs (default: all)")
    parser.add_argument("--augment", type=int, default=0,
                        help="Augmented variations per sample")
    parser.add_argument("--poi-depth", type=int, default=2,
                        help="POI graph depth")
    parser.add_argument("--poi-top-k", type=int, default=3,
                        help="Top-k branches per POI level")
    parser.add_argument("--format", choices=["json", "mc"], default="mc",
                        help="Output format: json (full search tree) or mc (multiple-choice)")
    parser.add_argument("--synthetic", type=int, default=0,
                        help="Number of synthetic maps to generate (0 = none)")
    args = parser.parse_args()

    all_samples = []

    # Generate from project floors
    project_floors = generate_from_project_floors(
        project_dir=args.project_dir,
        floor_ids=args.floors,
        augment_per_sample=args.augment,
        poi_depth=args.poi_depth,
        poi_top_k=args.poi_top_k,
        fmt=args.format,
    )
    all_samples.extend(project_floors)

    # Generate from AI test floors if specified
    if args.ai_test_dir:
        ai_samples = generate_from_ai_test_floors(
            test_dir=args.ai_test_dir,
            augment_per_sample=args.augment,
            poi_depth=args.poi_depth,
            poi_top_k=args.poi_top_k,
            fmt=args.format,
        )
        all_samples.extend(ai_samples)

    # Generate from synthetic maps
    if args.synthetic > 0:
        syn_samples = generate_from_synthetic_maps(
            n_maps=args.synthetic,
            augment_per_sample=args.augment,
            poi_depth=args.poi_depth,
            poi_top_k=args.poi_top_k,
            fmt=args.format,
        )
        all_samples.extend(syn_samples)

    _write_jsonl(all_samples, args.output)
    print(f"Generated {len(all_samples)} training samples → {args.output}")


if __name__ == "__main__":
    main()
