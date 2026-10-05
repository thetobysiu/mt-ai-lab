"""Floors, maps, floor sequence, walkthrough checkpoints."""
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


async def api_floors(request: Request):
    """List available floors."""
    from ...optimizer.evaluator import list_ai_test_floors
    return JSONResponse(list_ai_test_floors())


async def api_heuristic(request: Request):
    """Run heuristic evaluation (synchronous, non-streaming)."""
    data = await request.json()
    floor_id = data.get("floor", "mt3")

    from ...optimizer.evaluator import evaluate_heuristic_only

    _configure_floor(floor_id)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, evaluate_heuristic_only)
    return JSONResponse(result)


async def api_map(request: Request):
    """Return the rich map grid for the currently configured scenario (`project` = registry id, default 24)."""
    floor_id = request.query_params.get("floor", "mt3")
    project = request.query_params.get("project") or None
    from ...optimizer.evaluator import _create_state, _serialize_rich_map

    try:
        _configure_floor(floor_id, project)
    except (ValueError, FileNotFoundError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    state = _create_state()
    return JSONResponse(_serialize_rich_map(state))


async def api_floor_sequence(request: Request):
    """Return the ordered list of all floor IDs from project/data.js."""
    from ...game.hero_loader import load_floor_sequence
    try:
        floors = load_floor_sequence(_PROJECT_ROOT / "24" / "project" / "data.js")
        return JSONResponse({"floor_ids": floors})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_checkpoints(request: Request):
    """Walkthrough checkpoints usable as tower segment starts (`checkpoint` field on /api/evaluate/multi-floor)."""
    from ...game.data import WALKTHROUGH_CHECKPOINTS
    return JSONResponse(WALKTHROUGH_CHECKPOINTS)


async def api_bfs_reference(request: Request):
    """BFS-optimal targets the two-tier scorer compares against (scorer.BFS_REFERENCE, canonical ids only)."""
    from ...benchmark.scorer import BFS_REFERENCE
    keep = {k: v for k, v in BFS_REFERENCE.items() if not k.endswith(".txt") and not k.startswith("单层")}
    return JSONResponse(keep)


async def api_single_floors(request: Request):
    """Every single-floor boss map with its exact-solver facts: reference, hand-designed, generated."""
    from ...benchmark.scorer import BFS_REFERENCE
    base = _GEPA_ROOT / "data" / "floors"
    groups = [{"group": "reference", "title": "Reference floors (magic-tower-AI)", "floors": []},
              {"group": "hand", "title": "Hand-designed (unique solution)", "floors": []},
              {"group": "gen", "title": "Generated (random rooms)", "floors": []}]
    notes = {"simple": "the floor the prompt work was done on", "complex": "special-ability monsters; published solver said HP 22"}
    for fid in ("simple", "complex"):
        ref = BFS_REFERENCE.get(fid, {})
        groups[0]["floors"].append({"id": fid, "optimum_hp": ref.get("target_hp"), "note": notes[fid],
                                    "heuristic": "fails"})
    for g, sub in ((groups[1], "hand"), (groups[2], "gen")):
        man = base / sub / "manifest.json"
        if not man.exists():
            continue
        for f in json.loads(man.read_text(encoding="utf-8")).get("floors", []):
            h = f.get("heuristic") or {}
            g["floors"].append({"id": f["name"], "optimum_hp": f.get("target_hp"), "solver_states": f.get("solver_states"),
                                "critical": f.get("critical"), "forced": f.get("forced"), "random_win": f.get("random_win"),
                                "winning_sets": f.get("wins"),
                                "heuristic": "kills" if h.get("boss_killed") else "fails"})
    return JSONResponse({"groups": groups})


router.add_api_route("/api/floors", api_floors, methods=["GET"])
router.add_api_route("/api/floor-sequence", api_floor_sequence, methods=["GET"])
router.add_api_route("/api/map", api_map, methods=["GET"])
router.add_api_route("/api/heuristic", api_heuristic, methods=["POST"])
router.add_api_route("/api/bfs-reference", api_bfs_reference, methods=["GET"])
router.add_api_route("/api/single-floors", api_single_floors, methods=["GET"])
router.add_api_route("/api/checkpoints", api_checkpoints, methods=["GET"])
