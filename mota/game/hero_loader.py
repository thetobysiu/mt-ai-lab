"""
hero_loader.py — Parse project/data.js for initial hero stats and floor sequence.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from .types import Hero, Keys


def _extract_json_object(js_text: str) -> dict:
    """Strip 'var identifier = ' wrapper and return the JSON dict."""
    # Remove the JS variable declaration preamble and trailing semicolon
    text = re.sub(r'^\s*var\s+\w+\s*=\s*', '', js_text.strip())
    text = text.rstrip().rstrip(';')
    return json.loads(text)


def load_initial_hero(project_data_js: Path) -> Hero:
    """Parse project/data.js and return the initial hero stats."""
    text = project_data_js.read_text(encoding="utf-8")
    data = _extract_json_object(text)

    hero_raw = data["firstData"]["hero"]
    loc = hero_raw.get("loc", {})
    keys_data = hero_raw.get("items", {}).get("tools", {})

    return Hero(
        hp=hero_raw.get("hp", 1000),
        atk=hero_raw.get("atk", 10),
        def_=hero_raw.get("def", 10),
        mdef=hero_raw.get("mdef", 0),
        money=hero_raw.get("money", 0),
        exp=hero_raw.get("exp", 0),
        keys=Keys(
            yellow=keys_data.get("yellowKey", 0),
            blue=keys_data.get("blueKey", 0),
            red=keys_data.get("redKey", 0),
        ),
        x=loc.get("x", 6),
        y=loc.get("y", 10),
    )


def load_floor_sequence(project_data_js: Path) -> list[str]:
    """Parse project/data.js and return the ordered list of floor IDs."""
    text = project_data_js.read_text(encoding="utf-8")
    data = _extract_json_object(text)
    return list(data["main"]["floorIds"])
