"""
JobWatcher: background task that turns files on disk into live events.

Every second it (1) reaps dead jobs, (2) publishes changed manifests on topic "jobs", and
(3) for CLI-launched jobs, tails the per-turn-flushed run log they point at and republishes
every new event on "run:<job_id>" — so a `run_reliability.py` started in a terminal streams
into the dashboard without the evaluator knowing anything about WebSockets.
Dashboard-launched jobs publish directly from their worker thread and are skipped in (3).
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from . import jobs
from .api.paths import JOBS_DIR, LOGS_DIR
from .events import bus


class JobWatcher:
    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self._manifest_sig: dict[str, tuple[float, int]] = {}
        # job_id -> (run_log name, mtime, size, events_seen, result_seen)
        self._tail: dict[str, tuple[str, float, int, int, bool]] = {}
        self._last_big: dict[str, float] = {}  # job_id -> last time a >30 MB log was re-parsed
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        bus.bind_loop(asyncio.get_running_loop())
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.tick)
            except Exception as e:  # the watcher must never die silently
                print(f"[JobWatcher] tick failed: {type(e).__name__}: {e}", flush=True)
            await asyncio.sleep(self.interval)

    # -- one scan (sync, runs in a worker thread) ---------------------------------------------
    def tick(self) -> None:
        for m in jobs.mark_dead_jobs():
            bus.publish("jobs", {"type": "job_update", "job": m}, job_id=m["job_id"])
        if not JOBS_DIR.is_dir():
            return
        live: set[str] = set()
        for p in JOBS_DIR.glob("*.json"):
            try:
                st = p.stat()
            except OSError:
                continue
            sig = (st.st_mtime, st.st_size)
            jid = p.stem
            live.add(jid)
            if self._manifest_sig.get(jid) == sig:
                m = None
            else:
                m = jobs._read(p)
                if not m:
                    continue
                self._manifest_sig[jid] = sig
                bus.publish("jobs", {"type": "job_update", "job": m}, job_id=jid)
            if m is None and jid in self._tail:
                m = jobs._read(p)
            if m and m.get("source") == "cli" and m.get("current_run_log"):
                self._tail_run_log(jid, m["current_run_log"])
        for gone in set(self._manifest_sig) - live:
            self._manifest_sig.pop(gone, None)
            self._tail.pop(gone, None)

    def _tail_run_log(self, job_id: str, name: str) -> None:
        path = LOGS_DIR / "runs" / Path(name).name
        try:
            st = path.stat()
        except OSError:
            return
        prev = self._tail.get(job_id)
        if prev and prev[0] == name and prev[1] == st.st_mtime and prev[2] == st.st_size:
            return
        # Re-parsing a huge in-flight log every second starves the event loop (GIL); throttle it.
        if st.st_size > 30_000_000 and prev and prev[0] == name and time.time() - self._last_big.get(job_id, 0) < 30:
            return
        self._last_big[job_id] = time.time()
        seen, result_seen = (prev[3], prev[4]) if prev and prev[0] == name else (0, False)
        payload = jobs._read(path)
        if not payload:
            return
        turns = payload.get("turns") or []
        if seen == 0 and prev is None or (prev and prev[0] != name):
            bus.publish(f"run:{job_id}", {"type": "run_log_opened", "run_log": name,
                                          "floor_id": payload.get("floor_id"), "mode": payload.get("mode"),
                                          "task_model": payload.get("task_model")}, job_id=job_id)
        for ev in turns[seen:]:
            if ev.get("type") == "thinking_chunk":  # legacy logs only; thinking_result carries the text
                continue
            bus.publish(f"run:{job_id}", ev, job_id=job_id)
        if payload.get("result") and not result_seen:
            bus.publish(f"run:{job_id}", payload["result"], job_id=job_id)
            result_seen = True
        self._tail[job_id] = (name, st.st_mtime, st.st_size, len(turns), result_seen)


_BULKY = ("state_text", "actions_text", "llm_response", "user_message", "response", "content")


def compact_events(turns: list[dict], full_tail: int = 60) -> list[dict]:
    """Snapshot-sized view of a run log: no thinking_chunk (thinking_result carries the text) and
    prompt/response text only on the last `full_tail` events. Maps (start/floor_change) are kept whole."""
    keep = [ev for ev in turns if ev.get("type") != "thinking_chunk"]
    cut = len(keep) - full_tail
    out: list[dict] = []
    for i, ev in enumerate(keep):
        if i < cut and ev.get("type") in ("turn", "thinking", "thinking_result", "parse_error", "plan"):
            ev = {k: v for k, v in ev.items() if k not in _BULKY}
            if isinstance(ev.get("thinking"), str) and len(ev["thinking"]) > 1500:
                ev["thinking"] = "…" + ev["thinking"][-1500:]
            if isinstance(ev.get("llm_thinking"), str) and len(ev["llm_thinking"]) > 1500:
                ev["llm_thinking"] = "…" + ev["llm_thinking"][-1500:]
        out.append(ev)
    return out


def read_run_log_snapshot(name: str, max_events: int | None = None) -> dict | None:
    """Compacted events of a run log for a late subscriber."""
    path = LOGS_DIR / "runs" / Path(name).name
    if not path.is_file():
        return None
    payload = jobs._read(path)
    if not payload:
        return None
    turns = compact_events(payload.get("turns") or [])
    if max_events and len(turns) > max_events:
        turns = turns[-max_events:]
    return {"run_log": name, "floor_id": payload.get("floor_id"), "mode": payload.get("mode"),
            "task_model": payload.get("task_model"), "job_id": payload.get("job_id"),
            "turns": turns, "result": payload.get("result"), "raw_events": len(payload.get("turns") or [])}


watcher = JobWatcher()
