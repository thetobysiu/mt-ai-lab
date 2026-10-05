"""Seed prompt + prompt version store."""
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


async def api_seed_prompt(request: Request):
    """Return a prompt for the prompt box.

    Without ?floor=, returns the current active prompt from the versioned
    store (used on initial page load).

    With ?floor=<id>, returns the floor-TYPE-appropriate seed:
      - simple / complex (AI test floors, NO shop) -> no-shop seed
      - MT* / *.js (tower floors, WITH shop)        -> shop-aware seed
    The two floor types do not share strategy (shop/DEF economy only exists on
    tower floors), so the prompt box swaps content when the floor type changes.
    """
    floor = request.query_params.get("floor")
    if floor:
        from ...optimizer.seed_prompt import get_seed_for_floor, _is_shop_floor
        is_shop = _is_shop_floor(floor)
        return JSONResponse({
            "prompt": get_seed_for_floor(floor),
            "version_id": None,
            "label": "shop seed (tower)" if is_shop else "no-shop seed (AI floor)",
            "floor_type": "shop" if is_shop else "noshop",
            "floor_default": True,
        })

    from ...optimizer import prompt_store
    prompt_store.init_from_seed()
    current = prompt_store.get_current()
    return JSONResponse({
        "prompt": current["text"],
        "version_id": current["id"],
        "label": current["label"],
    })


async def api_prompt_versions(request: Request):
    """List all prompt versions (metadata only)."""
    from ...optimizer import prompt_store
    prompt_store.init_from_seed()
    return JSONResponse({"versions": prompt_store.list_versions()})


async def api_prompt_load(request: Request):
    """Load a specific prompt version by ID."""
    from ...optimizer import prompt_store
    vid = int(request.query_params.get("id", "0"))
    try:
        v = prompt_store.load_version(vid)
        return JSONResponse(v)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def api_prompt_save(request: Request):
    """Save a new prompt version."""
    from ...optimizer import prompt_store
    data = await request.json()
    text = data.get("text", "")
    label = data.get("label", "")
    source = data.get("source", "manual")
    parent_id = data.get("parent_id")
    floor_id = data.get("floor_id")
    score = data.get("score")
    vid = prompt_store.save_version(
        text=text, label=label, source=source,
        parent_id=parent_id, floor_id=floor_id, score=score,
    )
    return JSONResponse({"version_id": vid})


async def api_prompt_set_current(request: Request):
    """Pin a prompt version as the active one."""
    from ...optimizer import prompt_store
    data = await request.json()
    vid = data.get("version_id")
    if vid is None:
        return JSONResponse({"error": "Missing version_id"}, status_code=400)
    try:
        prompt_store.set_current(int(vid))
        return JSONResponse({"status": "ok", "current_id": int(vid)})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def api_prompt_diff(request: Request):
    """Compute diff between two prompt versions."""
    from ...optimizer import prompt_store
    id_a = int(request.query_params.get("a", "0"))
    id_b = int(request.query_params.get("b", "0"))
    try:
        result = prompt_store.diff_versions(id_a, id_b)
        return JSONResponse(result)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def api_prompt_update_score(request: Request):
    """Update the score of a prompt version for a specific floor."""
    from ...optimizer import prompt_store
    data = await request.json()
    vid = data.get("version_id")
    floor_id = data.get("floor_id")
    score = data.get("score")
    if vid is None or floor_id is None or score is None:
        return JSONResponse({"error": "Missing version_id, floor_id, or score"}, status_code=400)
    try:
        prompt_store.update_score(int(vid), floor_id, float(score))
        return JSONResponse({"status": "ok"})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def api_prompt_delete(request: Request):
    """Delete a prompt version."""
    from ...optimizer import prompt_store
    data = await request.json()
    vid = data.get("version_id")
    if vid is None:
        return JSONResponse({"error": "Missing version_id"}, status_code=400)
    try:
        prompt_store.delete_version(int(vid))
        return JSONResponse({"status": "ok"})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def api_seed_prompt_files(request: Request):
    """seed_prompts/*.txt on disk (name, chars) — the prompt files CLI experiments reference via --prompt-file."""
    seeds = _GEPA_ROOT / "seed_prompts"
    out = [{"name": p.name, "chars": p.stat().st_size} for p in sorted(seeds.glob("*.txt"))] if seeds.is_dir() else []
    return JSONResponse({"files": out})


async def api_seed_prompt_file(request: Request):
    name = Path(request.path_params["name"]).name
    p = _GEPA_ROOT / "seed_prompts" / name
    if not p.is_file() or p.suffix != ".txt":
        return JSONResponse({"error": "unknown prompt file"}, status_code=404)
    return JSONResponse({"name": name, "text": p.read_text(encoding="utf-8")})


router.add_api_route("/api/seed-prompt", api_seed_prompt, methods=["GET"])
router.add_api_route("/api/seed-prompts", api_seed_prompt_files, methods=["GET"])
router.add_api_route("/api/seed-prompts/{name}", api_seed_prompt_file, methods=["GET"])
router.add_api_route("/api/prompt/versions", api_prompt_versions, methods=["GET"])
router.add_api_route("/api/prompt/load", api_prompt_load, methods=["GET"])
router.add_api_route("/api/prompt/save", api_prompt_save, methods=["POST"])
router.add_api_route("/api/prompt/set-current", api_prompt_set_current, methods=["POST"])
router.add_api_route("/api/prompt/diff", api_prompt_diff, methods=["GET"])
router.add_api_route("/api/prompt/update-score", api_prompt_update_score, methods=["POST"])
router.add_api_route("/api/prompt/delete", api_prompt_delete, methods=["POST"])
