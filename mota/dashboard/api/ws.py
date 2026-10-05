"""Job registry routes + the WebSocket event bus endpoint."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .. import jobs
from ..events import bus
from ..watcher import read_run_log_snapshot

router = APIRouter()


async def api_jobs(request: Request):
    """All job manifests, newest first. ?active=1 → only queued/running."""
    active = request.query_params.get("active") in ("1", "true")
    limit = request.query_params.get("limit")
    return JSONResponse({"jobs": jobs.list_jobs(limit=int(limit) if limit else None, active_only=active),
                         "api_busy": [m["job_id"] for m in jobs.api_busy()]})


async def api_job_detail(request: Request):
    job = jobs.Job.load(request.path_params["job_id"])
    if job is None:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    return JSONResponse(job.m)


async def api_job_kill(request: Request):
    job_id = request.path_params["job_id"]
    ok = jobs.kill_job(job_id)
    job = jobs.Job.load(job_id)
    if job:
        bus.publish("jobs", {"type": "job_update", "job": job.m}, job_id=job_id)
    return JSONResponse({"killed": ok, "job": job.m if job else None}, status_code=200 if job else 404)


async def _job_pause(request: Request, paused: bool):
    job_id = request.path_params["job_id"]
    m = jobs.request_pause(job_id, paused)
    if m is None:
        return JSONResponse({"error": "unknown or finished job"}, status_code=404)
    bus.publish("jobs", {"type": "job_update", "job": m}, job_id=job_id)
    return JSONResponse({"pause_requested": paused, "job": m})


async def api_job_pause(request: Request):
    """Ask the owning process to pause after its current turn (status → paused once it complies)."""
    return await _job_pause(request, True)


async def api_job_resume(request: Request):
    return await _job_pause(request, False)


async def api_job_snapshot(request: Request):
    """Run-log events of a job's current episode (initial load for the live view)."""
    job = jobs.Job.load(request.path_params["job_id"])
    if job is None:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    name = request.query_params.get("run_log") or job.m.get("current_run_log")
    snap = read_run_log_snapshot(name) if name else None
    return JSONResponse({"job": job.m, "snapshot": snap})


async def ws_events(ws: WebSocket):
    """`/ws/events?topics=jobs,run:<id>`; client may send {"subscribe":[...]}/{"unsubscribe":[...]}.

    On (re)subscription the server sends a snapshot (jobs list / run-log events so far), then deltas.
    """
    await ws.accept()
    topics = [t for t in (ws.query_params.get("topics") or "jobs").split(",") if t]
    sub = bus.subscribe(topics)

    async def send_snapshot(topic: str):
        if topic == "jobs":
            await ws.send_json({"topic": "jobs", "event": {"type": "jobs_snapshot", "jobs": jobs.list_jobs(limit=200)}})
        elif topic.startswith("run:"):
            jid = topic[4:]
            job = jobs.Job.load(jid)
            snap = read_run_log_snapshot(job.m["current_run_log"]) if job and job.m.get("current_run_log") else None
            if snap:
                from .logs import _enrich_map_cells
                _enrich_map_cells(snap.get("turns") or [])
            await ws.send_json({"topic": topic, "job_id": jid,
                                "event": {"type": "run_snapshot", "job": job.m if job else None, "snapshot": snap}})

    async def reader():
        while True:
            msg = await ws.receive_text()
            try:
                cmd = json.loads(msg)
            except json.JSONDecodeError:
                continue
            for t in cmd.get("subscribe", []) or []:
                sub.topics.add(t)
                await send_snapshot(t)
            for t in cmd.get("unsubscribe", []) or []:
                sub.topics.discard(t)

    reader_task: asyncio.Task | None = None
    try:
        for t in topics:
            await send_snapshot(t)
        reader_task = asyncio.create_task(reader())
        while True:
            if reader_task.done():
                break
            env = await sub.get(timeout=15.0)
            if env is None:
                await ws.send_json({"topic": "sys", "event": {"type": "ping", "dropped": sub.dropped}})
                continue
            await ws.send_text(json.dumps(env, ensure_ascii=False, default=str))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(sub)
        if reader_task is not None:
            reader_task.cancel()


router.add_api_route("/api/jobs", api_jobs, methods=["GET"])
router.add_api_route("/api/jobs/{job_id}", api_job_detail, methods=["GET"])
router.add_api_route("/api/jobs/{job_id}/snapshot", api_job_snapshot, methods=["GET"])
router.add_api_route("/api/jobs/{job_id}/kill", api_job_kill, methods=["POST"])
router.add_api_route("/api/jobs/{job_id}/pause", api_job_pause, methods=["POST"])
router.add_api_route("/api/jobs/{job_id}/resume", api_job_resume, methods=["POST"])
router.add_api_websocket_route("/ws/events", ws_events)
