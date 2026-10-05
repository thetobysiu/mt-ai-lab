"""Run-log listing, detail, compare, download, CoT export."""
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


async def api_log_download(request: Request):
    """Serve the raw run-log JSON (logs/runs/<file>) as a download."""
    identifier = request.query_params.get("id") or request.query_params.get("filename")
    if not identifier:
        return JSONResponse({"error": "Missing log identifier"}, status_code=400)
    try:
        path, _ = _load_run_log(identifier)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return FileResponse(path, media_type="application/json", filename=path.name)


_SUMMARY_CACHE_NAME = "runs_summary_cache.json"  # lives in logs/, NOT logs/runs (consumers glob that folder)
_SUMMARY_SCHEMA = 5  # bump when _summarize_run_log gains fields, otherwise cached rows keep the old shape
_summary_cache: dict | None = None


def _load_summary_cache(runs_dir: Path) -> dict:
    global _summary_cache
    if _summary_cache is None:
        p = runs_dir.parent / _SUMMARY_CACHE_NAME
        try:
            _summary_cache = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        except Exception:
            _summary_cache = {}
    return _summary_cache


def _save_summary_cache(runs_dir: Path, cache: dict) -> None:
    try:
        tmp = runs_dir.parent / (_SUMMARY_CACHE_NAME + ".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, runs_dir.parent / _SUMMARY_CACHE_NAME)
    except OSError:
        pass


def _run_summaries(runs_dir: Path) -> list[dict]:
    """Summaries for every run log, re-parsing only files whose (mtime, size) changed.

    The corpus is hundreds of MB (tower logs > 200 MB each); parsing everything per request took ~15 s.
    """
    cache = _load_summary_cache(runs_dir)
    out: list[dict] = []
    dirty = False
    seen: set[str] = set()
    for f in sorted(runs_dir.glob("*.json"), reverse=True):
        seen.add(f.name)
        try:
            st = f.stat()
        except OSError:
            continue
        sig = [st.st_mtime, st.st_size]
        ent = cache.get(f.name)
        if ent and ent.get("sig") == sig and ent.get("v") == _SUMMARY_SCHEMA:
            out.append(ent["summary"])
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            summary = _summarize_run_log(f.name, data)
            summary["size_mb"] = round(st.st_size / 1e6, 1)
            summary["job_id"] = data.get("job_id")
        except Exception:
            summary = {"kind": "run", "filename": f.name, "floor_id": "", "mode": "", "error": "parse failed",
                       "size_mb": round(st.st_size / 1e6, 1)}
        cache[f.name] = {"sig": sig, "v": _SUMMARY_SCHEMA, "summary": summary}
        dirty = True
        out.append(summary)
    for gone in [k for k in cache if k not in seen]:
        cache.pop(gone, None)
        dirty = True
    if dirty:
        _save_summary_cache(runs_dir, cache)
    return out


async def api_logs(request: Request):
    """List saved run logs (cached summaries; only changed files are re-parsed)."""
    from ..run_logger import _LOGS_DIR
    mode_filter = (request.query_params.get("mode") or "all").strip().lower()
    floor_filter = (request.query_params.get("floor") or "").strip().lower()
    scenario_filter = (request.query_params.get("scenario") or "all").strip().lower()  # all | floor | tower
    limit = int(request.query_params.get("limit", "200"))

    logs = []
    runs_dir = _LOGS_DIR / "runs"
    if runs_dir.exists():
        for summary in _run_summaries(runs_dir):
            mode = str(summary.get("mode", "")).lower()
            if mode_filter not in ("", "all") and mode != mode_filter and not (mode_filter == "llm-plan" and mode.startswith("llm-plan")):
                continue
            if scenario_filter not in ("", "all") and str(summary.get("scenario", "")).lower() != scenario_filter:
                continue
            if floor_filter and floor_filter not in str(summary.get("floor_id", "")).lower():
                continue
            logs.append(summary)
    # GEPA sessions
    gepa_dir = _LOGS_DIR / "gepa"
    gepa_sessions = []
    if gepa_dir.exists():
        for d in sorted(gepa_dir.iterdir(), reverse=True):
            if d.is_dir():
                summary = d / "summary.json"
                if summary.exists():
                    try:
                        data = json.loads(summary.read_text(encoding="utf-8"))
                        session_summary = {
                            "kind": "gepa",
                            "dir": d.name,
                            "floor_id": data.get("floor_id", ""),
                            "best_score": data.get("best_score", 0),
                            "task_model": data.get("task_model", ""),
                            "task_mode": data.get("task_mode", ""),
                            "iterations": data.get("total_iterations", 0),
                        }
                        if mode_filter not in ("", "all", "gepa"):
                            continue
                        if floor_filter and floor_filter not in session_summary["floor_id"].lower():
                            continue
                        gepa_sessions.append(session_summary)
                    except Exception:
                        gepa_sessions.append({"dir": d.name, "error": "parse failed"})
    return JSONResponse({
        "runs": logs[:limit],
        "gepa_sessions": gepa_sessions[:limit],
    })


def _enrich_map_cells(turns: list) -> None:
    """Logs written before 2026-10-02 store enemy cells without fixed damage / vampire / N-hit, so the map overlay
    under-counted e.g. the Hemp-Robe Mage's 100 fixed damage. Fill them from the 24-floor tables (by tile id)."""
    from ...game.data import DEFAULT_GAME_DATA as gd
    for ev in turns:
        grid = (ev.get("map") or {}).get("grid") if isinstance(ev, dict) else None
        for row in grid or []:
            for c in row:
                if isinstance(c, dict) and c.get("t") == "E" and "fixed" not in c and isinstance(c.get("id"), int):
                    eid = gd.get_enemy_id(c["id"])
                    m = gd.get_monster(eid) if eid else None
                    if m is not None and m.name == c.get("name"):
                        c.update(fixed=m.damage, vampire=m.vampire, n=m.n)


async def api_log_detail(request: Request):
    """Return full detail for a run log or GEPA session."""
    kind = (request.query_params.get("kind") or "run").strip().lower()
    identifier = request.query_params.get("id") or request.query_params.get("filename") or request.query_params.get("dir")
    if not identifier:
        return JSONResponse({"error": "Missing log identifier"}, status_code=400)

    try:
        if kind == "gepa":
            _, session_data, summary_data, iterations = _load_gepa_session(identifier)
            return JSONResponse({
                "kind": "gepa",
                "id": identifier,
                "session": session_data,
                "summary": summary_data,
                "iterations": iterations,
            })

        _, payload = _load_run_log(identifier)
        _enrich_map_cells(payload.get("turns") or [])
        if request.query_params.get("full") not in ("1", "true"):
            # Replay needs turns + CoT text, not the token-level thinking_chunk stream (that is
            # what makes tower logs 200+ MB). Full payload remains available with ?full=1 / download.
            from ..watcher import compact_events
            payload = {**payload, "turns": compact_events(payload.get("turns") or [], full_tail=10_000),
                       "raw_events": len(payload.get("turns") or []), "compacted": True}
        return JSONResponse({
            "kind": "run",
            "id": identifier,
            "summary": _summarize_run_log(identifier, payload),
            "payload": payload,
        })
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def api_log_compare(request: Request):
    """Compare two run logs by score, HP, turn count, and action divergence."""
    left_id = request.query_params.get("a")
    right_id = request.query_params.get("b")
    if not left_id or not right_id:
        return JSONResponse({"error": "Missing a or b"}, status_code=400)

    try:
        _, left_payload = _load_run_log(left_id)
        _, right_payload = _load_run_log(right_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)

    left_summary = _summarize_run_log(left_id, left_payload)
    right_summary = _summarize_run_log(right_id, right_payload)
    left_turns = [event.get("action") for event in left_payload.get("turns", []) if event.get("type") == "turn"]
    right_turns = [event.get("action") for event in right_payload.get("turns", []) if event.get("type") == "turn"]

    shared_prefix = 0
    for left_action, right_action in zip(left_turns, right_turns):
        if left_action != right_action:
            break
        shared_prefix += 1

    first_divergence = None
    if shared_prefix < max(len(left_turns), len(right_turns)):
        first_divergence = {
            "turn": shared_prefix + 1,
            "left": left_turns[shared_prefix] if shared_prefix < len(left_turns) else None,
            "right": right_turns[shared_prefix] if shared_prefix < len(right_turns) else None,
        }

    return JSONResponse({
        "left": left_summary,
        "right": right_summary,
        "diff": {
            "score_delta": round((left_summary.get("score") or 0) - (right_summary.get("score") or 0), 4),
            "final_hp_delta": (left_summary.get("final_hp") or 0) - (right_summary.get("final_hp") or 0),
            "turn_delta": left_summary.get("turn_count", 0) - right_summary.get("turn_count", 0),
            "shared_prefix_turns": shared_prefix,
            "first_divergence": first_divergence,
        },
    })


async def api_cot_export(request: Request):
    """Export chain-of-thought traces from run logs for fine-tuning.

    Query params:
      id       – single log filename (optional; exports all LLM runs if omitted)
      min_score – minimum score threshold (default 0.0)
    Returns JSONL-style array: [{input, thinking, action, score, floor_id, turn}, ...]
    """
    from ..run_logger import _LOGS_DIR
    min_score = float(request.query_params.get("min_score", 0.0))
    single_id = request.query_params.get("id")

    runs_dir = _LOGS_DIR / "runs"
    if not runs_dir.exists():
        return JSONResponse({"traces": [], "count": 0})

    files = [runs_dir / single_id] if single_id else sorted(runs_dir.glob("*.json"))
    traces = []
    for fpath in files:
        if not fpath.exists():
            continue
        try:
            payload = _load_json_file(fpath)
        except Exception:
            continue
        if payload.get("mode") != "llm":
            continue
        result = payload.get("result", {})
        score = result.get("total", 0.0)
        if score < min_score:
            continue
        floor_id = payload.get("floor_id", "")
        for event in payload.get("turns", []):
            if event.get("type") != "turn":
                continue
            thinking = event.get("llm_thinking") or ""
            if not thinking:
                continue
            traces.append({
                "input": event.get("state_text", "") + "\n" + event.get("actions_text", ""),
                "thinking": thinking,
                "action_id": event.get("action_id"),
                "action": event.get("action", ""),
                "score": score,
                "floor_id": floor_id,
                "turn": event.get("turn"),
                "log_file": fpath.name,
            })

    return JSONResponse({"traces": traces, "count": len(traces)})


router.add_api_route("/api/logs", api_logs, methods=["GET"])
router.add_api_route("/api/log/detail", api_log_detail, methods=["GET"])
router.add_api_route("/api/log/download", api_log_download, methods=["GET"])
router.add_api_route("/api/logs/compare", api_log_compare, methods=["GET"])
router.add_api_route("/api/cot/export", api_cot_export, methods=["GET"])
