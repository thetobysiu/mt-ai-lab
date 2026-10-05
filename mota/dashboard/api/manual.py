"""Manual play session (human picks engine-enumerated actions)."""
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
from .common import *  # noqa: F401,F403


router = APIRouter()


async def api_manual_start(request: Request):
    """Start or reset a manual-play session for the selected floor (or multi-floor range)."""
    data = await request.json()
    floor_id = data.get("floor", "mt3")
    enable_logging = data.get("enable_logging", True)
    multi_floor = data.get("multi_floor", False)
    end_floor = data.get("end_floor")  # e.g. "MT4" for multi-floor range

    if _manual_state.get("state") is not None or _manual_state.get("game") is not None:
        _finalize_manual_log(reason="Superseded by new manual session")

    if multi_floor:
        # Multi-floor mode: create a MultiFloorGame
        from ...optimizer.evaluator import configure_multi_floor_scenario, _create_multi_floor_game
        start_id = floor_id.upper()
        end_id = (end_floor or "MT23w").upper()
        desc = configure_multi_floor_scenario(start_id, end_id)
        game = _create_multi_floor_game()
        actions = game.get_actions()
        canonical_floor_id = game.current_floor.floor_id
        run_log = None
        if enable_logging:
            run_log = RunLogger(floor_id=f"{start_id}-{end_id}", mode="manual-multifloor")
            run_log.add_event({
                "type": "start", "floor_id": canonical_floor_id,
                "hero": _hero_dict_quick(game.hero),
                "multi_floor": True, "desc": desc,
            })
        S.reset(_manual_state,
            state=None,
            game=game,
            multi_floor=True,
            floor_id=canonical_floor_id,
            run_log=run_log,
            log_saved=None,
            action_ids=[],
            result=None,
            walkthrough_guide=None,
            diverged_at_turn=None,
        )
        return JSONResponse(_manual_payload_multi(game, actions))
    else:
        # Single-floor mode (original behavior)
        from ...optimizer.evaluator import _create_state

        _configure_floor(floor_id, data.get("project") or None)

        state = _create_state()
        actions = state.get_actions()
        canonical_floor_id = state.floor.floor_id
        run_log = None
        if enable_logging:
            run_log = RunLogger(floor_id=canonical_floor_id, mode="manual")
            run_log.add_event(_build_manual_start_event(state))
        S.reset(_manual_state,
            state=state,
            game=None,
            multi_floor=False,
            floor_id=canonical_floor_id,
            run_log=run_log,
            log_saved=None,
            action_ids=[],
            result=None,
            walkthrough_guide=None,
            diverged_at_turn=None,
        )

        # Load active benchmark as walkthrough guide (if available)
        walkthrough_mode = data.get("walkthrough_mode", True)  # default on
        if walkthrough_mode:
            from ...benchmark import recording_store
            active = recording_store.get_active_recording(canonical_floor_id.lower())
            if active and active.get("history"):
                _manual_state["walkthrough_guide"] = active

        return JSONResponse(_manual_payload(state, actions))


async def api_manual_action(request: Request):
    """Apply one manual action by action_id and return updated state."""
    is_multi = _manual_state.get("multi_floor", False)
    state = _manual_state.get("state")
    game = _manual_state.get("game")

    if state is None and game is None:
        return JSONResponse({"error": "No manual session running"}, status_code=409)

    data = await request.json()
    action_id = data.get("action_id")
    if action_id is None:
        return JSONResponse({"error": "Missing action_id"}, status_code=400)

    if is_multi and game is not None:
        # Multi-floor mode
        actions = game.get_actions()
        chosen = next((a for a in actions if a.action_id == int(action_id)), None)
        if chosen is None:
            return JSONResponse({
                "error": f"Invalid action_id {action_id}",
                "valid_ids": [a.action_id for a in actions],
            }, status_code=400)

        prev_floor = game.current_floor.floor_id
        trace = game.apply_action(chosen)
        _manual_state.setdefault("action_ids", []).append(chosen.action_id)

        done = game.goal_reached or game.failed
        next_actions = [] if done else game.get_actions()

        # Detect floor transition
        floor_changed = game.current_floor.floor_id != prev_floor
        if floor_changed:
            _manual_state["floor_id"] = game.current_floor.floor_id

        payload = _manual_payload_multi(game, next_actions, last_action=chosen, last_trace=trace)
        if floor_changed:
            payload["floor_changed"] = True
            payload["new_floor_id"] = game.current_floor.floor_id

        if _manual_state.get("run_log") is not None:
            _manual_state["run_log"].add_event(payload)

        if done:
            from ...optimizer.evaluator import _score_multi_floor
            result = _score_multi_floor(game)
            payload["result"] = result
            _manual_state["result"] = result
            log_name = _finalize_manual_log(result=result)
            if log_name:
                payload["log_saved"] = log_name

        return JSONResponse(payload)
    else:
        # Single-floor mode (original behavior)
        actions = state.get_actions()
        chosen = next((a for a in actions if a.action_id == int(action_id)), None)
        if chosen is None:
            return JSONResponse({
                "error": f"Invalid action_id {action_id}",
                "valid_ids": [a.action_id for a in actions],
            }, status_code=400)

        trace = state.apply_action(chosen)
        _manual_state.setdefault("action_ids", []).append(chosen.action_id)

        # Track walkthrough divergence
        guide = _manual_state.get("walkthrough_guide")
        if guide and _manual_state.get("diverged_at_turn") is None:
            turn_idx = state.turn - 1  # turn already incremented by apply_action
            history = guide.get("history", [])
            if turn_idx < len(history):
                expert_step = history[turn_idx]
                if (chosen.x, chosen.y, chosen.type.value) != (
                    expert_step.get("x"), expert_step.get("y"), expert_step.get("type")
                ):
                    _manual_state["diverged_at_turn"] = state.turn

        next_actions = [] if (state.goal_reached or state.failed) else state.get_actions()
        payload = _manual_payload(state, next_actions, last_trace=trace, last_action=chosen)

        # Include user annotation if provided
        annotation = data.get("annotation")
        if annotation:
            payload["annotation"] = annotation

        if _manual_state.get("run_log") is not None:
            _manual_state["run_log"].add_event(payload)

        if payload["done"]:
            from ...benchmark.scorer import score_run
            result = score_run(state, fixture_id=_manual_state.get("floor_id") or "manual")
            payload["result"] = result
            _manual_state["result"] = result
            log_name = _finalize_manual_log(result=result)
            if log_name:
                payload["log_saved"] = log_name

        return JSONResponse(payload)


async def api_manual_save(request: Request):
    """Save a snapshot of the current manual run log without stopping the session."""
    run_log = _manual_state.get("run_log")
    if run_log is None:
        return JSONResponse({"error": "No active manual session"}, status_code=400)
    log_path = run_log.save()
    return JSONResponse({"log_saved": log_path.name})


async def api_manual_stop(request: Request):
    """Stop manual mode and clear state."""
    log_name = _finalize_manual_log(reason="Stopped by user")
    S.reset_manual()
    payload = {"status": "stopped"}
    if log_name:
        payload["log_saved"] = log_name
    return JSONResponse(payload)


router.add_api_route("/api/manual/start", api_manual_start, methods=["POST"])
router.add_api_route("/api/manual/action", api_manual_action, methods=["POST"])
router.add_api_route("/api/manual/save", api_manual_save, methods=["POST"])
router.add_api_route("/api/manual/stop", api_manual_stop, methods=["POST"])
