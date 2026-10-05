"""Thread → asyncio.Queue → SSE bridge shared by every streaming route, with job + bus hooks."""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Callable

from fastapi.responses import StreamingResponse

from .. import jobs as J
from ..events import bus


def sse_headers() -> dict:
    return {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}


def _progress(ev: dict) -> dict:
    hero = ev.get("hero") or {}
    p = {"turn": ev.get("turn"), "floor_id": ev.get("floor_id"), "hp": hero.get("hp"),
         "atk": hero.get("atk"), "def": hero.get("def")}
    if ev.get("type") == "turn":
        p["last_action"] = ev.get("action")
        p["forced"] = bool(ev.get("forced"))
    return {k: v for k, v in p.items() if v is not None}


def threaded_sse(worker: Callable[[Callable[[dict], None]], None], *, run_log=None, job: J.Job | None = None,
                 on_finish: Callable[[], None] | None = None, publish_topic: str | None = None) -> StreamingResponse:
    """Run `worker(on_event)` in a thread; stream every event as SSE.

    Side effects per event: append to `run_log`, update `job` progress, publish on the bus
    (topic run:<job_id> by default). After the worker: save the run log (emits log_saved),
    finish the job, emit done.
    """
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    topic = publish_topic or (f"run:{job.job_id}" if job else None)
    last_result: dict = {}
    every = {"n": 0}

    def on_event(event: dict | None):
        if event is None:
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        _emit(event)
        # Pause point: after a turn has been recorded, before the next LLM call. Runs on the worker thread.
        if job is not None and event.get("type") in ("turn", "floor_change"):
            J.pause_gate(job, on_state=lambda st: st in ("paused", "running") and _emit(
                {"type": "paused" if st == "paused" else "resumed", "turn": event.get("turn"), "reason": f"{st} from dashboard"}))

    def _emit(event: dict):
        if run_log is not None:
            run_log.add_event(event)
        if job is not None and event.get("type") in ("turn", "floor_change", "start"):
            every["n"] += 1
            if every["n"] % 3 == 0 or event.get("type") != "turn":  # manifest writes are cheap but not free
                job.progress(**_progress(event))
        if event.get("type") == "result":
            last_result.update(event)
        if topic:
            bus.publish(topic, event, job_id=job.job_id if job else None)
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def run():
        status = "done"
        try:
            worker(on_event)
        except Exception as e:
            status = "failed"
            on_event({"type": "error", "message": f"{type(e).__name__}: {e}"})
            if job is not None:
                job.finish("failed", error=f"{type(e).__name__}: {e}")
        finally:
            if job is not None and job.m.get("status") in ("running", "queued", "paused"):
                summary = {k: last_result.get(k) for k in ("total", "success", "hp_ratio", "goal_score", "goal_reached",
                                                           "max_floor_id", "floors_reached", "failure_reason")}
                job.finish(status, result={k: v for k, v in summary.items() if v is not None})
            if on_finish:
                try:
                    on_finish()
                except Exception:
                    pass
            loop.call_soon_threadsafe(queue.put_nowait, None)

    async def event_gen():
        threading.Thread(target=run, daemon=True).start()
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        if run_log is not None:
            try:
                log_path = run_log.save()
                if job is not None:
                    job.set_run_log(log_path.name)
                ev = {"type": "log_saved", "path": log_path.name}
                if topic:
                    bus.publish(topic, ev, job_id=job.job_id if job else None)
                yield f"data: {json.dumps(ev)}\n\n"
            except Exception:
                pass
        done = {"type": "done"}
        if topic:
            bus.publish(topic, done, job_id=job.job_id if job else None)
        yield f"data: {json.dumps(done)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=sse_headers())


def busy_response(force: bool):
    """409 payload when another job holds the LLM API and MOTA_EXCLUSIVE_API=1; else None."""
    from fastapi.responses import JSONResponse
    if force or not J.exclusive_api():
        return None
    busy = J.api_busy()
    if not busy:
        return None
    return JSONResponse({"error": "api_busy", "message": "Another job is using the LLM API (MOTA_EXCLUSIVE_API=1).",
                         "jobs": busy}, status_code=409)
