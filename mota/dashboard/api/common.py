"""Helpers shared by the dashboard routers (floor resolution, run-log summaries, manual-play payloads)."""
from __future__ import annotations

import asyncio
import json
import os
import time
import threading
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, Response

from ..run_logger import RunLogger, GEPASessionLogger
from .paths import HERE as _HERE, GEPA_ROOT as _GEPA_ROOT, PROJECT_ROOT as _PROJECT_ROOT, FLOORS_DIR as _FLOORS_DIR
from . import state as S
from .state import _gepa_state, _eval_state, _matrix_state, _manual_state, _step_gepa_state, _reliability_state



def _configure_floor(floor_id: str | None, project: str | None = None):
    """Configure scenario with special-case handling for MT3/MT4 test presets.

    project: id from the projects registry (api/projects.py); None/"24" = built-in 24-layer tables.
    """
    from ...optimizer.evaluator import configure_scenario, configure_mt3_scenario, configure_mt4_scenario
    if project and project != "24":
        from .projects import registered_projects
        meta = registered_projects().get(project)
        if not meta:
            raise ValueError(f"unknown project '{project}'")
        root = Path(meta["root"])
        return configure_scenario(str(root / "floors" / f"{floor_id}.js"), project_root=root)
    fid_upper = (floor_id or "").upper()
    if fid_upper == "MT3" or floor_id == "mota-floor:MT3":
        return configure_mt3_scenario()
    elif floor_id == "special-floor:MT4" or fid_upper == "MT4":
        return configure_mt4_scenario()
    return configure_scenario(_resolve_floor_path(floor_id))


def _resolve_floor_path(floor_id: str | None) -> str | None:
    """Resolve a dashboard floor ID to a path for configure_scenario().

    - None / "" / "mt3"  → None  (default MT3 walkthrough)
    - "MT3", "MT0", etc. → path to project/floors/{id}.js
    - "simple" / "complex" → resolved later against data/floors
    - Existing file path  → returned as-is (AI test floors)
    """
    if not floor_id or floor_id == "mt3":
        return None
    # MOTA floor ID (e.g. "MT3", "MT0", "MT23w", "MT_1")
    candidate = _FLOORS_DIR / f"{floor_id}.js"
    if candidate.exists():
        return str(candidate)
    # Already a file path (AI test floors)
    return floor_id


def _safe_child_path(base_dir: Path, name: str) -> Path:
    safe_name = Path(name).name
    if not safe_name or safe_name != name:
        raise ValueError("Invalid identifier")
    return base_dir / safe_name


def _load_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_turn_count(payload: dict) -> int:
    res = payload.get("result") or {}
    details = res.get("details") or {}
    if details.get("steps") is not None:
        return int(details["steps"])
    if res.get("decisions") is not None:
        return int(res["decisions"])
    if res.get("turn") is not None:
        return int(res["turn"])
    return sum(1 for event in payload.get("turns", []) if event.get("type") == "turn")


def _run_final_hp(payload: dict):
    result = payload.get("result") or {}
    details = result.get("details") or {}
    hero = result.get("hero") or {}
    return result.get("final_hp") or hero.get("hp") or details.get("final_hp")


def _display_floor_id(floor_id: str | None) -> str:
    raw = str(floor_id or "").replace("\\", "/")
    return raw.split("/")[-1] if raw else ""


BOSS_GOAL_FLOORS = ("simple", "complex")  # AI test floors whose goal is "kill enemy #299"


def _summarize_run_log(filename: str, payload: dict) -> dict:
    res = payload.get("result") or {}
    tracking = res.get("tracking") or {}
    violations = [str(v) for v in (res.get("violations") or [])]
    floor_id = _display_floor_id(payload.get("floor_id", ""))
    # "MT0-MT23w" (tower range) vs "simple" / "MT3" (one floor)
    start, _, end = floor_id.partition("-")
    tower = bool(end)
    final_hp = _run_final_hp(payload)
    died = (final_hp is not None and final_hp <= 0) or any("suicide" in v or "died" in v.lower() for v in violations)
    boss_floor = floor_id.lower() in BOSS_GOAL_FLOORS or res.get("goal") == "boss"
    # A stopped/aborted run stores a bare stop event as its result: no score, no outcome.
    scored = any(k in res for k in ("total", "success", "goal_reached"))
    boss_killed = None
    if boss_floor and scored:
        boss_killed = res.get("goal_reached") if res.get("goal_reached") is not None else ("boss_not_killed" not in violations)
    # Safety-override count: turns where the engine executed a different action than the LLM chose
    # (recorded since 2026-09-24 as `corrected_from` on the turn event).
    overrides = sum(1 for e in payload.get("turns", []) if e.get("type") == "turn" and e.get("corrected_from") is not None)
    return {
        "kind": "run",
        "filename": filename,
        "floor_id": floor_id,
        "scenario": "tower" if tower else "floor",
        "has_result": scored,
        "start_floor": start if tower else floor_id,
        "end_floor": end if tower else "",
        "mode": payload.get("mode", ""),
        "task_model": payload.get("task_model", ""),
        "task_mode": payload.get("task_mode", ""),
        "started_at": payload.get("started_at", ""),
        "score": res.get("total"),
        # Two-tier (BFS-relative) outcome, present on results written after 2026-09-21
        "success": res.get("success"),
        "hp_ratio": res.get("hp_ratio"),
        "goal_score": res.get("goal_score"),
        "goal": res.get("goal"),
        "goal_reached": res.get("goal_reached"),
        "boss_floor": boss_floor,
        "boss_killed": boss_killed,
        "died": died,
        "failure_reason": res.get("failure_reason"),
        "max_floor_id": res.get("max_floor_id"),
        "floors_reached": res.get("floors_reached"),
        "turn_count": _run_turn_count(payload),
        "overrides": overrides,
        "final_hp": final_hp,
        "seconds_per_call": tracking.get("seconds_per_call"),
        "download": f"/api/log/download?id={filename}",
    }


def _load_run_log(filename: str) -> tuple[Path, dict]:
    from ..run_logger import _LOGS_DIR
    path = _safe_child_path(_LOGS_DIR / "runs", filename)
    if not path.exists():
        raise ValueError(f"Run log '{filename}' not found")
    return path, _load_json_file(path)


def _load_gepa_session(dir_name: str) -> tuple[Path, dict, dict, list[dict]]:
    from ..run_logger import _LOGS_DIR
    session_dir = _safe_child_path(_LOGS_DIR / "gepa", dir_name)
    if not session_dir.exists() or not session_dir.is_dir():
        raise ValueError(f"GEPA session '{dir_name}' not found")
    session_data = _load_json_file(session_dir / "session.json") if (session_dir / "session.json").exists() else {}
    summary_data = _load_json_file(session_dir / "summary.json") if (session_dir / "summary.json").exists() else {}
    iterations = []
    for path in sorted(session_dir.glob("iter_*.json")):
        try:
            iterations.append(_load_json_file(path))
        except Exception:
            continue
    return session_dir, session_data, summary_data, iterations


def _serialize_trace_history(state, action_ids: list[int] | None = None) -> list[dict]:
    history = []
    for idx, trace in enumerate(state.history):
        hero_after = trace.hero_after or {}
        history.append({
            "turn": trace.turn,
            "action_id": action_ids[idx] if action_ids and idx < len(action_ids) else None,
            "action": trace.action.label(),
            "type": trace.action.type.value,
            "x": trace.action.x,
            "y": trace.action.y,
            "name": trace.action.name,
            "hero_after": {
                "hp": hero_after.get("hp"),
                "atk": hero_after.get("atk"),
                "def": hero_after.get("def"),
            },
        })
    return history


def _build_manual_start_event(state) -> dict:
    from ...optimizer.evaluator import _hero_dict, _serialize_rich_map

    return {
        "type": "start",
        "floor_id": state.floor.floor_id,
        "hero": _hero_dict(state),
        "initial_enemies": state.initial_enemies,
        "state_text": state.format_state(),
        "mode": "manual",
        "map": _serialize_rich_map(state),
    }


def _build_recording_from_manual_state(label: str | None = None) -> dict:
    state = _manual_state.get("state")
    game = _manual_state.get("game")
    is_multi = _manual_state.get("multi_floor", False)

    if state is None and game is None:
        raise ValueError("No manual session available")
    result = _manual_state.get("result")
    if result is None:
        raise ValueError("Manual session has no completed result")

    if is_multi and game is not None:
        return {
            "label": label or f"Manual multi-floor {game.current_floor.floor_id}",
            "floor_id": game.current_floor.floor_id,
            "source": "manual-multifloor",
            "action_ids": list(_manual_state.get("action_ids") or []),
            "history": [],  # multi-floor trace history not serialized yet
            "expected": {
                "hp": game.hero.hp,
                "atk": game.hero.atk,
                "def": game.hero.def_,
                "money": game.hero.money,
                "exp": game.hero.exp,
                "keys": {
                    "yellow": game.hero.keys.yellow,
                    "blue": game.hero.keys.blue,
                    "red": game.hero.keys.red,
                },
                "turns": game.total_turns,
                "goal_reached": game.goal_reached,
                "floors_reached": game.current_floor_idx,
            },
            "result": result,
        }

    return {
        "label": label or f"Manual benchmark {state.floor.floor_id}",
        "floor_id": state.floor.floor_id,
        "source": "manual-session",
        "action_ids": list(_manual_state.get("action_ids") or []),
        "history": _serialize_trace_history(state, _manual_state.get("action_ids") or []),
        "expected": {
            "hp": state.hero.hp,
            "atk": state.hero.atk,
            "def": state.hero.def_,
            "money": state.hero.money,
            "exp": state.hero.exp,
            "keys": {
                "yellow": state.hero.keys.yellow,
                "blue": state.hero.keys.blue,
                "red": state.hero.keys.red,
            },
            "enemies_remaining": state.remaining_enemies(),
            "turns": state.turn,
            "goal_reached": state.goal_reached,
        },
        "result": result,
    }


def _build_recording_from_log_payload(log_payload: dict, label: str | None = None) -> dict:
    turn_events = [event for event in log_payload.get("turns", []) if event.get("type") == "turn"]
    result = log_payload.get("result") or {}
    details = result.get("details") or {}
    hero = result.get("hero") or (turn_events[-1].get("hero") if turn_events else {}) or {}
    enemies_total = details.get("enemies_total")
    enemies_killed = details.get("enemies_killed")
    enemies_remaining = None
    if enemies_total is not None and enemies_killed is not None:
        enemies_remaining = max(0, int(enemies_total) - int(enemies_killed))

    return {
        "label": label or f"Run log benchmark {log_payload.get('floor_id', 'floor')}",
        "floor_id": log_payload.get("floor_id", ""),
        "source": f"log:{log_payload.get('mode', 'manual')}",
        "action_ids": [event.get("action_id") for event in turn_events if event.get("action_id") is not None],
        "history": [
            {
                "turn": event.get("turn"),
                "action_id": event.get("action_id"),
                "action": event.get("action"),
                "type": (event.get("action_detail") or {}).get("type"),
                "x": (event.get("action_detail") or {}).get("x"),
                "y": (event.get("action_detail") or {}).get("y"),
                "name": (event.get("action_detail") or {}).get("name"),
                "hero_after": {
                    "hp": (event.get("hero") or {}).get("hp"),
                    "atk": (event.get("hero") or {}).get("atk"),
                    "def": (event.get("hero") or {}).get("def"),
                },
            }
            for event in turn_events
        ],
        "expected": {
            "hp": hero.get("hp", details.get("final_hp", 0)),
            "atk": hero.get("atk", details.get("hero_atk", 0)),
            "def": hero.get("def", details.get("hero_def", 0)),
            "enemies_remaining": enemies_remaining if enemies_remaining is not None else 0,
            "turns": details.get("steps", len(turn_events)),
            "goal_reached": enemies_remaining == 0 if enemies_remaining is not None else False,
        },
        "result": result,
    }


def _finalize_manual_log(result: dict | None = None, reason: str | None = None) -> str | None:
    run_log = _manual_state.get("run_log")
    if run_log is None:
        return None
    if _manual_state.get("log_saved"):
        return _manual_state["log_saved"]
    if result is not None:
        run_log.add_event({"type": "result", **result})
    elif reason:
        state = _manual_state.get("state")
        game = _manual_state.get("game")
        if game is not None:
            run_log.add_event({
                "type": "stopped",
                "reason": reason,
                "turn": game.total_turns,
                "hero": _hero_dict_quick(game.hero),
                "floor_id": game.current_floor.floor_id,
            })
        elif state is not None:
            from ...optimizer.evaluator import _hero_dict
            run_log.add_event({
                "type": "stopped",
                "reason": reason,
                "turn": state.turn,
                "hero": _hero_dict(state),
            })
    log_path = run_log.save()
    _manual_state["log_saved"] = log_path.name
    return log_path.name


def _serialize_map(state) -> dict:
    """Build a JSON-serializable map grid with tile classifications."""
    from ...game import data as D
    gd = state.gd
    floor = state.floor
    grid = []
    for y in range(floor.height):
        row = []
        for x in range(floor.width):
            tile = floor.map[y][x]
            removed = (x, y) in state.removed
            if removed:
                cell = {"t": "ground", "id": 0}
            elif gd.is_enemy(tile):
                eid = gd.get_enemy_id(tile)
                m = gd.get_monster(eid)
                cell = {"t": "enemy", "id": tile, "name": m.name,
                        "hp": m.hp, "atk": m.atk, "def": m.def_}
            elif D.is_item(tile):
                eff = gd.get_item_effect(D.TILE_ITEMS[tile])
                cell = {"t": "item", "id": tile, "name": eff.get("name", D.TILE_ITEMS[tile])}
            elif D.is_door(tile):
                cell = {"t": "door", "id": tile, "color": D.TILE_DOORS[tile].value}
            elif D.is_stairs(tile):
                cell = {"t": "stairs", "id": tile, "dir": D.TILE_STAIRS[tile]}
            elif D.is_npc(tile):
                cell = {"t": "npc", "id": tile, "name": D.TILE_NPCS.get(tile, "NPC")}
            elif D.is_wall(tile):
                cell = {"t": "wall", "id": tile}
            elif D.is_terrain(tile):
                cell = {"t": "terrain", "id": tile}
            elif D.is_ground(tile):
                cell = {"t": "ground", "id": 0}
            else:
                cell = {"t": "unknown", "id": tile}
            row.append(cell)
        grid.append(row)
    return {
        "width": floor.width,
        "height": floor.height,
        "grid": grid,
        "hero": {"x": state.hero.x, "y": state.hero.y},
    }


def _hero_dict_quick(hero) -> dict:
    """Serialize a Hero object to dict (no GameState dependency)."""
    return {
        "hp": hero.hp, "atk": hero.atk, "def": hero.def_, "mdef": hero.mdef,
        "money": hero.money, "exp": hero.exp,
        "keys": {"yellow": hero.keys.yellow, "blue": hero.keys.blue, "red": hero.keys.red},
        "x": hero.x, "y": hero.y,
    }


def _manual_payload_multi(game, actions: list, last_trace=None, last_action=None) -> dict:
    """Build response payload for multi-floor manual mode."""
    from ...optimizer.evaluator import _serialize_rich_map

    state = game._make_state()
    rich_map = _serialize_rich_map(state)

    payload = {
        "type": "manual_state",
        "floor_id": game.current_floor.floor_id,
        "multi_floor": True,
        "floor_progress": f"{game.current_floor_idx + 1}/{len(game.floors)}",
        "floor_index": game.current_floor_idx,
        "total_floors": len(game.floors),
        "turn": game.total_turns,
        "hero": _hero_dict_quick(game.hero),
        "map": rich_map,
        "removed": [list(r) for r in game.per_floor_removed.get(game.current_floor_idx, set())],
        "state_text": game.format_state(),
        "actions_text": game.format_actions(actions),
        "actions": [_serialize_action(a) for a in actions],
        "goal_reached": game.goal_reached,
        "failed": game.failed,
        "failure_reason": game.failure_reason,
        "done": bool(game.goal_reached or game.failed),
        "deferred_doors": len(game.deferred_doors),
    }

    if last_trace is not None and last_action is not None:
        payload.update({
            "type": "turn",
            "action": last_action.label(),
            "action_id": last_action.action_id,
            "forced": False,
            "action_detail": {
                "type": last_action.type.value,
                "x": last_action.x,
                "y": last_action.y,
                "name": last_action.name,
                "is_dead_end": bool(getattr(last_action, "is_dead_end", False)),
            },
            "action_path": [list(p) for p in getattr(last_action, "path", [])],
        })

    return payload


def _serialize_action(action) -> dict:
    """Serialize a GameState action for dashboard/manual mode."""
    payload = {
        "action_id": action.action_id,
        "type": action.type.value,
        "label": action.label(),
        "x": action.x,
        "y": action.y,
        "name": action.name,
        "is_dead_end": bool(getattr(action, "is_dead_end", False)),
        "path_steps": action.path_steps,
        "path": [list(p) for p in getattr(action, "path", [])],
    }
    if action.type.value == "fight":
        payload.update({
            "can_win": action.can_win,
            "total_damage": action.total_damage,
            "hp_after": action.hp_after,
            "damage_percent": action.damage_percent,
        })
    if action.type.value == "collect":
        payload.update({
            "item_tier": action.item_tier.value,
            "item_score": action.item_score,
        })
    if action.type.value == "open_door" and action.door_type:
        payload["door_type"] = action.door_type.value
    if action.type.value == "shop_buy":
        payload.update({
            "shop_choice": action.shop_choice,
            "money_cost": action.money_cost,
            "stat_changes": action.stat_changes,
            "can_afford": getattr(action, "can_afford", True),
        })
    if action.unlocks_items:
        payload["unlocks"] = list(action.unlocks_items)
    if getattr(action, "lookahead_value", 0):
        payload["lookahead_value"] = int(action.lookahead_value)
    return payload


def _manual_payload(state, actions: list, last_trace=None, last_action=None) -> dict:
    """Build a consistent response payload for manual mode."""
    from ...optimizer.evaluator import _serialize_rich_map, _hero_dict

    payload = {
        "type": "manual_state",
        "floor_id": state.floor.floor_id,
        "turn": state.turn,
        "hero": _hero_dict(state),
        "map": _serialize_rich_map(state),
        "removed": [list(r) for r in state.removed],
        "state_text": state.format_state(),
        "actions_text": state.format_actions(actions),
        "actions": [_serialize_action(a) for a in actions],
        "goal_reached": state.goal_reached,
        "failed": state.failed,
        "failure_reason": state.failure_reason,
        "done": bool(state.goal_reached or state.failed),
    }

    if last_trace is not None and last_action is not None:
        payload.update({
            "type": "turn",
            "action": last_action.label(),
            "action_id": last_action.action_id,
            "forced": False,
            "action_detail": {
                "type": last_action.type.value,
                "x": last_action.x,
                "y": last_action.y,
                "name": last_action.name,
                "is_dead_end": bool(getattr(last_action, "is_dead_end", False)),
            },
            "action_path": [list(p) for p in getattr(last_action, "path", [])],
        })

    # --- Walkthrough guide: inject expert recommendation ---
    guide = _manual_state.get("walkthrough_guide")
    if guide is not None and not payload.get("done"):
        turn_idx = state.turn  # 0-based: turn 0 = first action to choose
        history = guide.get("history", [])
        if turn_idx < len(history):
            expert_step = history[turn_idx]
            # Match expert action to current available actions by (x, y, type)
            ex = expert_step.get("x"), expert_step.get("y"), expert_step.get("type")
            matched_id = None
            for a in actions:
                if (a.x, a.y, a.type.value) == ex:
                    matched_id = a.action_id
                    break
            payload["expert_recommendation"] = {
                "action_id": matched_id,
                "x": expert_step.get("x"),
                "y": expert_step.get("y"),
                "type": expert_step.get("type"),
                "name": expert_step.get("name"),
                "label": expert_step.get("label", ""),
                "turn": turn_idx + 1,
                "total_turns": len(history),
            }
        # Track divergence from expert path
        diverged_at = _manual_state.get("diverged_at_turn")
        if diverged_at is not None:
            payload["walkthrough_diverged"] = True
            payload["walkthrough_diverged_at"] = diverged_at

    return payload


def _apply_experiment_env(data: dict) -> None:
    """Translate request-body experiment switches into the env vars the evaluator reads.

    Mirrors run_reliability.py so a dashboard run and a CLI run are the same condition:
      disable_overrides      -> MOTA_DISABLE_OVERRIDES=1 (raw LLM, needed for the BFS-compiled complex prompt)
      thinking_max_tokens    -> THINKING_MAX_TOKENS (8192 recommended for tower runs)
      structured_output=False-> MOTA_DISABLE_STRUCTURED_OUTPUT=1
      plan_steps / one_shot  -> MOTA_PLAN_STEPS (+ MOTA_PLAN_NO_REPLAN)
      final_stack            -> CONVERSATION_HISTORY_TURNS=0, MOTA_ORDER_TWO_SIDED=1, MOTA_FIGHT_KEY_FLOOD=1
    Absent keys reset the corresponding env var so a previous run cannot leak into this one.
    """
    if data.get("disable_overrides"):
        os.environ["MOTA_DISABLE_OVERRIDES"] = "1"
    else:
        os.environ.pop("MOTA_DISABLE_OVERRIDES", None)
    if data.get("thinking_max_tokens"):
        os.environ["THINKING_MAX_TOKENS"] = str(int(data["thinking_max_tokens"]))
    if data.get("structured_output") is False:
        os.environ["MOTA_DISABLE_STRUCTURED_OUTPUT"] = "1"
    else:
        os.environ.pop("MOTA_DISABLE_STRUCTURED_OUTPUT", None)
    # Planning granularity and the final engine stack (thesis §7.3.6, §8.20.11a); reset every run.
    from ...harness.reliability import DASHBOARD_RUN_ENV, FINAL_STACK_ENV
    for k in DASHBOARD_RUN_ENV:
        os.environ.pop(k, None)
    steps = int(data.get("plan_steps") or 1)
    if data.get("one_shot"):
        os.environ["MOTA_PLAN_STEPS"], os.environ["MOTA_PLAN_NO_REPLAN"] = "60", "1"
    elif steps > 1:
        os.environ["MOTA_PLAN_STEPS"] = str(steps)
    if data.get("final_stack"):
        os.environ.update(FINAL_STACK_ENV)


__all__ = [
    "_configure_floor",
    "_resolve_floor_path",
    "_safe_child_path",
    "_load_json_file",
    "_run_turn_count",
    "_run_final_hp",
    "_display_floor_id",
    "_summarize_run_log",
    "_load_run_log",
    "_load_gepa_session",
    "_serialize_trace_history",
    "_build_manual_start_event",
    "_build_recording_from_manual_state",
    "_build_recording_from_log_payload",
    "_finalize_manual_log",
    "_serialize_map",
    "_hero_dict_quick",
    "_manual_payload_multi",
    "_serialize_action",
    "_manual_payload",
    "_apply_experiment_env",
]
