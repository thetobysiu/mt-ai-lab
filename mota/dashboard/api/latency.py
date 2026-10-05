"""Latency census over stored run logs (same numbers as scripts/latency_census.py)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .paths import GEPA_ROOT

router = APIRouter()


def api_latency(request: Request):
    """Sync handler (runs in the thread pool): a cold census parses every stored run log."""
    from ...analysis.latency import census
    dirs = request.query_params.get("dirs")
    return JSONResponse(census(dirs.split(",") if dirs else None, GEPA_ROOT))


def warm_cache() -> None:
    from ...analysis.latency import census
    census(None, GEPA_ROOT)


router.add_api_route("/api/latency", api_latency, methods=["GET"])
