"""N-repeat reliability harness from the dashboard — same files as run_reliability.py, plus live events."""
from __future__ import annotations

import asyncio
import json
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .. import jobs as J
from ..events import bus
from ...harness import reliability as H
from .state import _eval_state, _reliability_state
from .streaming import sse_headers

router = APIRouter()


def condition_from_body(data: dict, *, source: str = "dashboard") -> H.RunCondition:
    """Map a request body (every run_reliability.py flag as a JSON field) to a RunCondition."""
    import os
    for k in H.DASHBOARD_RUN_ENV:  # a previous dashboard run's plan / stack switches must not leak into this one
        os.environ.pop(k, None)
    tower = bool(data.get("tower")) or data.get("checkpoint") not in (None, "")
    prompt = data.get("prompt") or None
    checkpoint = data.get("checkpoint")
    return H.RunCondition(
        floor=data.get("floor", "simple"),
        tower=tower,
        start=data.get("start_floor", "MT0"),
        end=data.get("end_floor") or "MT23w",
        max_turns=int(data.get("max_turns") or 1500),
        checkpoint=int(checkpoint) if checkpoint not in (None, "") else None,
        prompt=prompt,
        prompt_name=data.get("prompt_name") or ("none" if prompt is None else "dashboard-editor"),
        mode=data.get("mode", "reactive"),
        preset=data.get("task_preset") or "qwen3.5-397b",
        task_model=data.get("task_model"),
        task_mode=data.get("task_mode"),
        repeats=1 if prompt is None else int(data.get("repeats", 3)),
        disable_overrides=bool(data.get("disable_overrides")),
        lookahead=int(data["lookahead_depth"]) if data.get("lookahead_depth") else None,
        structured_output=data.get("structured_output", True) is not False,
        temperature=float(data.get("temperature", 0.0)),
        thinking_max_tokens=int(data["thinking_max_tokens"]) if data.get("thinking_max_tokens") else None,
        label=data.get("label") or None,
        append=bool(data.get("append")),
        source=source,
        plan_steps=int(data.get("plan_steps") or 1),
        one_shot=bool(data.get("one_shot")),
        final_stack=bool(data.get("final_stack")),
    )


async def api_reliability_results(request: Request):
    """Stored results/reliability/*.json with aggregates (+ per-run records when ?runs=1)."""
    rows = H.list_results()
    if request.query_params.get("runs") not in ("1", "true"):
        for r in rows:
            r["run_logs"] = [x["run_log"] for x in r.pop("runs", None) or [] if x.get("run_log")]
    return JSONResponse(rows)


async def api_reliability_stop(request: Request):
    if not _reliability_state["running"]:
        return JSONResponse({"status": "idle"})
    _reliability_state["stop_requested"] = True
    return JSONResponse({"status": "stopping"})


async def api_reliability_stream(request: Request):
    """SSE: N-repeat reliability run from the dashboard.

    Body: every run_reliability.py flag (floor | tower+start_floor/end_floor | checkpoint, prompt (null =
    heuristic), mode, task_preset, repeats, label, append, max_turns, lookahead_depth, temperature,
    disable_overrides, thinking_max_tokens, structured_output, force).
    Events: start{job_id}, run (one per episode), done{aggregate,file} — evaluator turns go to the
    WebSocket topic run:<job_id>. Results land in results/reliability/<label>.json + SUMMARY.md.
    """
    if _reliability_state["running"] or _eval_state["running"]:
        return JSONResponse({"error": "An evaluation is already running"}, status_code=409)
    data = await request.json()
    cond = condition_from_body(data)
    if not cond.heuristic:
        from .streaming import busy_response
        busy = busy_response(bool(data.get("force")))
        if busy is not None:
            return busy
    _reliability_state["running"] = True
    _reliability_state["stop_requested"] = False

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    job_ref: dict = {"id": None}

    def put(ev):
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def on_event(ev: dict):
        if ev.get("type") == "start":
            job_ref["id"] = ev.get("job_id")
        put(ev)
        if job_ref["id"]:
            bus.publish(f"run:{job_ref['id']}", ev, job_id=job_ref["id"])

    def on_turn(ev: dict):
        if job_ref["id"]:
            bus.publish(f"run:{job_ref['id']}", ev, job_id=job_ref["id"])

    def work():
        try:
            H.run_batch(cond, on_event=on_event, on_turn=on_turn,
                        should_stop=lambda: _reliability_state["stop_requested"], log=lambda m: None)
        except Exception as e:
            put({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            _reliability_state["running"] = False
            _reliability_state["stop_requested"] = False
            put(None)

    async def event_gen():
        threading.Thread(target=work, daemon=True).start()
        while True:
            ev = await queue.get()
            if ev is None:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=sse_headers())


router.add_api_route("/api/reliability/stream", api_reliability_stream, methods=["POST"])
router.add_api_route("/api/reliability/stop", api_reliability_stop, methods=["POST"])
router.add_api_route("/api/reliability/results", api_reliability_results, methods=["GET"])
