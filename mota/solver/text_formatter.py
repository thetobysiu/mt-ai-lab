"""
Text formatter for Architecture C training data.

Converts game state → semantic input text,
and POI graph + solver solution → JSON training target.

Output format uses JSON (not XML) because LLMs see far more JSON in
training corpora, and 1.2B models handle JSON structure better than
XML closing-tag tracking.
"""
from __future__ import annotations

import json
from ..game.types import Hero, FloorData, Action, ActionType, Keys
from ..game.state import GameState
from ..game import data as D
from ..game.data import GameData, DEFAULT_GAME_DATA
from ..game import damage as dmg
from .bfs_solver import POINode, extract_poi_graph


# ---------------------------------------------------------------------------
# Input formatter: game state → semantic text for SLM input
# ---------------------------------------------------------------------------

def format_state_input(
    floor: FloorData,
    hero: Hero,
    removed: set[tuple[int, int]] | None = None,
    game_data: GameData | None = None,
) -> str:
    """
    Format current game state as compact semantic text for SLM consumption.

    Layout:
      - Hero stats line
      - Floor metadata
      - Nearby entities (sorted by distance)
      - ASCII minimap
    """
    gd = game_data or DEFAULT_GAME_DATA
    removed = removed or set()

    lines = []

    # Hero stats
    lines.append(
        f"Floor: {floor.floor_id} ({floor.width}x{floor.height}). "
        f"Hero at ({hero.x},{hero.y}). "
        f"HP={hero.hp} ATK={hero.atk} DEF={hero.def_} MDEF={hero.mdef}. "
        f"Gold={hero.money}. Keys: Y={hero.keys.yellow} B={hero.keys.blue} R={hero.keys.red}."
    )

    # Nearby entities — enumerate what the hero can see/reach
    gs = GameState(
        floor=floor,
        hero=hero.copy(),
        goal="clear_all_enemies",
        game_data=gd,
        lookahead_depth=0,
        _removed=removed,
    )
    actions = gs.get_actions()

    entity_lines = []
    for a in actions:
        if a.type == ActionType.FIGHT:
            monster = gd.get_monster(a.monster_id)
            specials = monster.specials
            sp_str = ""
            if specials:
                sp_labels = {
                    1: "first-strike", 2: "magic-atk", 3: "solid",
                    4: "2x-combo", 5: "3x-combo", 6: "Nx-combo",
                    7: "break-armor", 8: "counter", 9: "purify", 10: "mimic",
                    11: "vampire", 22: "fixed-dmg",
                }
                sp_str = " [" + ",".join(sp_labels.get(s, str(s)) for s in specials) + "]"
            entity_lines.append(
                f"  ENEMY {a.name}{sp_str} at ({a.x},{a.y}) "
                f"HP={monster.hp} ATK={monster.atk} DEF={monster.def_} "
                f"dmg={a.total_damage} gold={monster.money}"
                f"{' BLOCKED' if not a.can_win else ''}"
            )
        elif a.type == ActionType.COLLECT:
            entity_lines.append(f"  ITEM {a.name} at ({a.x},{a.y})")
        elif a.type == ActionType.OPEN_DOOR:
            entity_lines.append(f"  DOOR {a.name} at ({a.x},{a.y})")
        elif a.type == ActionType.USE_STAIRS:
            entity_lines.append(f"  STAIRS at ({a.x},{a.y})")
        elif a.type == ActionType.SHOP_BUY:
            entity_lines.append(f"  SHOP {a.name} at ({a.x},{a.y}) cost={a.money_cost}g")

    if entity_lines:
        lines.append("Entities:")
        lines.extend(entity_lines)

    # ASCII minimap
    minimap = _build_minimap(floor, hero, removed, gd)
    lines.append("Map:")
    lines.extend(minimap)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Multiple-choice format — compact alternative for 1.2B SLMs
# ---------------------------------------------------------------------------

def format_multiple_choice_input(
    floor: FloorData,
    hero: Hero,
    removed: set[tuple[int, int]] | None = None,
    game_data: GameData | None = None,
    poi_depth: int = 2,
    poi_top_k: int = 3,
) -> str:
    """
    Format state + lookahead as multiple-choice prompt.

    Free items are auto-collected first (matching BFS solver behavior).
    Only real decision actions (fights, doors, shops) appear as choices.
    """
    gd = game_data or DEFAULT_GAME_DATA
    removed = removed or set()

    # Auto-collect free items first (mirrors BFS solver)
    hero_adj, removed_adj, auto_collected = _auto_collect(floor, hero, removed, gd)

    lines = []
    # Hero stats (after auto-collect)
    lines.append(
        f"Floor: {floor.floor_id} ({floor.width}x{floor.height}). "
        f"Hero at ({hero_adj.x},{hero_adj.y}). "
        f"HP={hero_adj.hp} ATK={hero_adj.atk} DEF={hero_adj.def_}. "
        f"Keys: Y={hero_adj.keys.yellow} B={hero_adj.keys.blue} R={hero_adj.keys.red}."
    )

    if auto_collected:
        lines.append("Auto-collected: " + ", ".join(auto_collected))

    # Minimap (after auto-collect)
    minimap = _build_minimap(floor, hero_adj, removed_adj, gd)
    lines.append("Map:")
    lines.extend(minimap)

    # POI graph from decision-ready state → choices
    poi_roots = extract_poi_graph(floor, hero_adj, removed_adj, gd, depth=poi_depth, top_k=poi_top_k)
    # Filter to decision actions only (no zero-cost collects)
    decision_roots = [r for r in poi_roots if r.hp_cost > 0 or r.action_type in ("open_door", "shop_buy", "use_stairs")]
    if not decision_roots:
        decision_roots = poi_roots  # fallback: keep all if no fights

    lines.append("")
    lines.append("Choose the best action:")
    labels = "ABCDEFGHIJ"
    for i, root in enumerate(decision_roots):
        lbl = labels[i] if i < len(labels) else str(i)
        desc = _describe_poi_choice(root, hero_adj)
        lines.append(f"  {lbl}) {desc}")

    return "\n".join(lines)


def _auto_collect(
    floor: FloorData,
    hero: Hero,
    removed: set[tuple[int, int]],
    gd: GameData,
) -> tuple[Hero, set[tuple[int, int]], list[str]]:
    """Simulate auto-collecting all zero-cost reachable items. Returns (new_hero, new_removed, labels)."""
    from ..game.state import GameState

    hero_adj = hero.copy()
    removed_adj = set(removed)
    collected = []

    for _ in range(50):  # safety limit
        gs = GameState(
            floor=floor, hero=hero_adj.copy(), goal="clear_all_enemies",
            game_data=gd, lookahead_depth=0, _removed=removed_adj,
        )
        actions = gs.get_actions()
        free = [a for a in actions if a.type == ActionType.COLLECT and a.total_damage == 0]
        if not free:
            break
        a = free[0]
        # Apply the collect
        effect = gd.get_item_effect(a.item_id)
        for k, v in effect.items():
            if k in ("tier", "score", "name"):
                continue
            if k == "hp":
                hero_adj.hp += v
            elif k == "atk":
                hero_adj.atk += v
            elif k == "def":
                hero_adj.def_ += v
            elif k == "mdef":
                hero_adj.mdef += v
            elif k == "keys.yellow":
                hero_adj.keys = Keys(hero_adj.keys.yellow + v, hero_adj.keys.blue, hero_adj.keys.red)
            elif k == "keys.blue":
                hero_adj.keys = Keys(hero_adj.keys.yellow, hero_adj.keys.blue + v, hero_adj.keys.red)
            elif k == "keys.red":
                hero_adj.keys = Keys(hero_adj.keys.yellow, hero_adj.keys.blue, hero_adj.keys.red + v)
            elif k == "money":
                hero_adj.money += v
        removed_adj.add((a.x, a.y))
        collected.append(a.name)

    return hero_adj, removed_adj, collected


def format_multiple_choice_output(
    poi_roots: list[POINode],
    optimal_action: Action,
    hero: Hero,
    macro_actions: list[Action],
) -> str:
    """
    Compact output: chosen letter + reasoning + macro-action sequence.
    """
    # Find which choice matches the optimal action
    optimal_label_str = format_action_label(optimal_action)
    labels = "ABCDEFGHIJ"
    choice = "?"
    for i, root in enumerate(poi_roots):
        if root.node_id == optimal_label_str:
            choice = labels[i] if i < len(labels) else str(i)
            break

    reason = generate_decision_text(poi_roots, optimal_action, hero)
    macros = [format_action_label(a) for a in macro_actions[:3]]

    output = {
        "answer": choice,
        "reason": reason,
        "macro_action": macros,
    }
    return json.dumps(output, ensure_ascii=False)


def _describe_poi_choice(node: POINode, hero: Hero) -> str:
    """Describe a single POI root node as a choice line with lookahead."""
    parts = []
    if node.action_type == "fight":
        parts.append(f"Fight {node.target_name} at ({node.x},{node.y}) dmg={node.hp_cost} hp->{node.hp_after}")
    elif node.action_type == "collect":
        changes = "+".join(f"{v}{k}" for k, v in node.stat_changes.items()) or "item"
        parts.append(f"Collect {node.target_name} at ({node.x},{node.y}) ({changes})")
    elif node.action_type == "open_door":
        parts.append(f"Open {node.target_name} at ({node.x},{node.y})")
    elif node.action_type == "shop_buy":
        parts.append(f"Shop: {node.target_name}")
    else:
        parts.append(f"{node.action_type} {node.target_name} at ({node.x},{node.y})")

    if node.items_unlocked:
        parts.append(f"unlocks [{', '.join(node.items_unlocked[:3])}]")

    if node.children:
        child_strs = []
        for c in node.children[:2]:
            if c.action_type == "fight":
                child_strs.append(f"fight {c.target_name} dmg={c.hp_cost}")
            elif c.action_type == "collect":
                child_strs.append(f"collect {c.target_name}")
            else:
                child_strs.append(f"{c.action_type} {c.target_name}")
        parts.append("then: " + " | ".join(child_strs))

    return " → ".join(parts[:2]) if len(parts) >= 2 else parts[0]


def _build_minimap(
    floor: FloorData,
    hero: Hero,
    removed: set[tuple[int, int]],
    gd: GameData,
) -> list[str]:
    """Build compact ASCII minimap. Symbols: @ hero, M monster, * item, D door, S stairs, # wall, . ground."""
    rows = []
    for y in range(floor.height):
        row = []
        for x in range(floor.width):
            if x == hero.x and y == hero.y:
                row.append("@")
                continue
            if (x, y) in removed:
                row.append(".")
                continue
            tile = floor.map[y][x]
            if gd.is_wall(tile):
                row.append("#")
            elif gd.is_enemy(tile):
                row.append("M")
            elif gd.is_item(tile):
                row.append("*")
            elif gd.is_door(tile):
                row.append("D")
            elif gd.is_stairs(tile):
                row.append("S")
            elif gd.is_npc(tile):
                row.append("N")
            elif gd.is_ground(tile) or gd.is_terrain(tile):
                row.append(".")
            else:
                row.append("?")
        rows.append("".join(row))
    return rows


# ---------------------------------------------------------------------------
# Output formatter: POI graph + decision → JSON training target
# ---------------------------------------------------------------------------

def format_training_output(
    poi_roots: list[POINode],
    decision_text: str,
    macro_actions: list[str],
) -> str:
    """
    Format the training target as a JSON object.

    Structure:
    {
      "search_tree": [ ... POI node dicts ... ],
      "decision": "Path 2 yields higher net HP because ...",
      "macro_action": ["FIGHT_SKELETON_3_4", "COLLECT_RED_GEM_9_1"]
    }
    """
    output = {
        "search_tree": [root.to_dict() for root in poi_roots],
        "decision": decision_text,
        "macro_action": macro_actions,
    }
    return json.dumps(output, ensure_ascii=False)


def format_action_label(action: Action) -> str:
    """Create a stable string label for an action (used in macro_action lists)."""
    return f"{action.type.value}_{action.name}_{action.x}_{action.y}".replace(" ", "_")


# ---------------------------------------------------------------------------
# Decision text generator
# ---------------------------------------------------------------------------

def generate_decision_text(
    poi_roots: list[POINode],
    optimal_action: Action,
    hero: Hero,
) -> str:
    """
    Generate a natural-language decision explanation based on the POI graph
    and the optimal action chosen by the BFS solver.
    """
    if not poi_roots:
        return "No viable actions available."

    # Find the optimal path in the POI tree
    optimal_label = format_action_label(optimal_action)
    optimal_node = None
    for i, root in enumerate(poi_roots):
        if root.node_id == optimal_label:
            optimal_node = root
            break

    parts = []

    if optimal_node:
        if optimal_node.action_type == "fight":
            parts.append(
                f"Fight {optimal_node.target_name} at ({optimal_node.x},{optimal_node.y}) "
                f"costs {optimal_node.hp_cost} HP, leaving {optimal_node.hp_after} HP."
            )
            if optimal_node.gold_gain:
                parts.append(f"Earns {optimal_node.gold_gain} gold.")
        elif optimal_node.action_type == "collect":
            changes = ", ".join(f"+{v} {k}" for k, v in optimal_node.stat_changes.items())
            parts.append(
                f"Collect {optimal_node.target_name} at ({optimal_node.x},{optimal_node.y})"
                f"{': ' + changes if changes else ''}."
            )
        elif optimal_node.action_type == "open_door":
            parts.append(f"Open {optimal_node.target_name} at ({optimal_node.x},{optimal_node.y}).")
        elif optimal_node.action_type == "shop_buy":
            parts.append(f"Buy {optimal_node.target_name} at shop.")

        if optimal_node.items_unlocked:
            parts.append(f"Unlocks: {', '.join(optimal_node.items_unlocked[:4])}.")

        if optimal_node.children:
            best_child = min(
                optimal_node.children,
                key=lambda c: c.hp_cost - sum(c.stat_changes.get(k, 0) * (90 if k == "def" else 70) for k in ("atk", "def")),
            )
            parts.append(
                f"Best follow-up: {best_child.target_name} "
                f"(cost {best_child.hp_cost} HP)."
            )
    else:
        # Optimal action not in top-k POI — just describe it
        parts.append(f"Optimal: {optimal_action.label()}.")

    # Compare with alternatives
    alternatives = [r for r in poi_roots if r.node_id != optimal_label]
    if alternatives:
        worst = max(alternatives, key=lambda n: n.hp_cost)
        if worst.hp_cost > 0 and optimal_node and worst.hp_cost > optimal_node.hp_cost:
            parts.append(
                f"Avoiding {worst.target_name} (costs {worst.hp_cost} HP) preserves "
                f"{worst.hp_cost - (optimal_node.hp_cost if optimal_node else 0)} more HP."
            )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Full training pair builder
# ---------------------------------------------------------------------------

def build_training_pair(
    floor: FloorData,
    hero: Hero,
    removed: set[tuple[int, int]],
    optimal_actions: list[Action],
    game_data: GameData | None = None,
    poi_depth: int = 2,
    poi_top_k: int = 3,
    fmt: str = "json",
) -> dict | None:
    """
    Build one (input, output) training pair from a game state snapshot +
    the solver's optimal next actions.

    Args:
        fmt: "json" for full search-tree target, "mc" for multiple-choice.

    Returns {"input": str, "output": str} or None if the state has no actions.
    """
    if not optimal_actions:
        return None

    gd = game_data or DEFAULT_GAME_DATA

    if fmt == "mc":
        input_text = format_multiple_choice_input(
            floor, hero, removed, gd,
            poi_depth=poi_depth, poi_top_k=poi_top_k,
        )
        # Re-derive auto-collected state for output matching
        hero_adj, removed_adj, _ = _auto_collect(floor, hero, removed, gd)
        poi_roots = extract_poi_graph(floor, hero_adj, removed_adj, gd, depth=poi_depth, top_k=poi_top_k)
        decision_roots = [r for r in poi_roots if r.hp_cost > 0 or r.action_type in ("open_door", "shop_buy", "use_stairs")]
        if not decision_roots:
            decision_roots = poi_roots
        output_text = format_multiple_choice_output(
            decision_roots, optimal_actions[0], hero_adj, optimal_actions,
        )
    else:
        # Original JSON format
        input_text = format_state_input(floor, hero, removed, gd)
        poi_roots = extract_poi_graph(
            floor, hero, removed, gd,
            depth=poi_depth, top_k=poi_top_k,
        )
        decision = generate_decision_text(poi_roots, optimal_actions[0], hero)
        macro = [format_action_label(a) for a in optimal_actions[:3]]
        output_text = format_training_output(poi_roots, decision, macro)

    return {"input": input_text, "output": output_text}
