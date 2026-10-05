"""
Benchmark fixtures — test scenarios with known start states and expected outcomes.
"""
from __future__ import annotations
from ..game.types import Hero, Keys


def create_mt3_hero() -> Hero:
    """Create the hero entering MT3 from the walkthrough (after clearing 1F)."""
    return Hero(
        hp=860, atk=10, def_=10, mdef=0,
        money=5, exp=4,
        keys=Keys(yellow=1, blue=0, red=0),
        x=1, y=11,
    )


def create_mt3_hero_advantaged() -> Hero:
    """Easier start for testing — more HP and keys."""
    return Hero(
        hp=900, atk=10, def_=10, mdef=0,
        money=25, exp=4,
        keys=Keys(yellow=2, blue=1, red=1),
        x=1, y=11,
    )


def create_danceng_zuijiandan_hero() -> Hero:
    """Create hero for 单层-最简单 AI test floor (from .txt header)."""
    return Hero(
        hp=470, atk=9, def_=4, mdef=0,
        money=0, exp=0,
        keys=Keys(yellow=0, blue=0, red=0),
        x=0, y=5,
    )


def create_mt4_hero() -> Hero:
    """Create hero entering MT4 with ideal MT3-finish stats."""
    return Hero(
        hp=448, atk=23, def_=17, mdef=0,
        money=23, exp=46,
        keys=Keys(yellow=6, blue=1, red=1),
        x=1, y=11,
    )


FIXTURES = {
    "mt3-walkthrough": {
        "floor_id": "MT3",
        "hero_factory": create_mt3_hero,
        "goal": "clear_all_enemies",
        "max_turns": 50,
        "expected": {
            "hp": 448,
            "atk": 23,
            "def": 17,
            "enemies_remaining": 0,
        },
        "description": "MT3 full-clear following expert walkthrough route",
    },
    "mt3-advantaged": {
        "floor_id": "MT3",
        "hero_factory": create_mt3_hero_advantaged,
        "goal": "clear_all_enemies",
        "max_turns": 50,
        "expected": {
            "enemies_remaining": 0,
        },
        "description": "MT3 with extra resources — tests basic completion",
    },
    "mt4-stairs": {
        "floor_id": "MT4",
        "hero_factory": create_mt4_hero,
        "goal": "stairs",
        "max_turns": 50,
        "expected": {
            "hp": 444,
            "atk": 23,
            "def": 25,
        },
        "description": "MT4 reach stairs from ideal MT3-finish state",
    },
    "danceng-zuijiandan": {
        "floor_path": "magic-tower-AI/test/单层-最简单.txt",
        "floor_id": "单层-最简单",
        "hero_factory": create_danceng_zuijiandan_hero,
        "goal": "clear_all_enemies",
        "max_turns": 30,
        "expected": {
            "enemies_remaining": 0,
        },
        "description": "Single-floor minimal test (Java AI reference floor)",
    },
}
