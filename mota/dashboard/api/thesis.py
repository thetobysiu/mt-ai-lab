"""Thesis results: the result files behind every table and paragraph of Chapter 6 (results/thesis_index.json),
with each episode and whether its run log is present for replay."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...paths import REPO_ROOT, RESULTS, RUN_LOGS

router = APIRouter()
_INDEX = RESULTS / "thesis_index.json"


async def api_thesis_results(request: Request):
    if not _INDEX.exists():
        return JSONResponse({"error": "results/thesis_index.json missing (python analysis/thesis_index.py --appendix …)"},
                            status_code=404)
    index = json.loads(_INDEX.read_text(encoding="utf-8"))
    n_logs = sum(1 for _ in RUN_LOGS.glob("*.json")) if RUN_LOGS.is_dir() else 0
    return JSONResponse({"source": index.get("source"), "rows": index["rows"], "run_logs_present": n_logs})


def _episode(r: dict) -> dict:
    log = r.get("run_log")
    return {"run_log": log, "log_present": bool(log) and (RUN_LOGS / log).exists(),
            "success": r.get("success"), "died": r.get("died"), "final_hp": r.get("final_hp"), "hp_ratio": r.get("hp_ratio"),
            "floor": r.get("max_floor_id") or r.get("floor"), "prompt": r.get("prompt"), "split": r.get("split"),
            "rep": r.get("rep", r.get("run_idx"))}


async def api_thesis_result_file(request: Request):
    rel = request.query_params.get("path", "")
    p = (REPO_ROOT / rel).resolve()
    if not rel.startswith("results/") or not p.is_relative_to(RESULTS.resolve()) or p.suffix != ".json" or not p.exists():
        return JSONResponse({"error": "unknown result file"}, status_code=404)
    d = json.loads(p.read_text(encoding="utf-8"))
    episodes = d.get("runs") or d.get("episodes") or []
    return JSONResponse({"path": rel, "label": d.get("label", p.stem), "episodes": [_episode(r) for r in episodes]})


router.add_api_route("/api/thesis-results", api_thesis_results, methods=["GET"])
router.add_api_route("/api/thesis-results/file", api_thesis_result_file, methods=["GET"])
