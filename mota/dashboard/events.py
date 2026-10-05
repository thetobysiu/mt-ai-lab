"""
In-process pub/sub bridging evaluator worker threads to WebSocket subscribers.

Topics: "jobs" (manifest updates), "run:<job_id>" (evaluator events for one run),
"gepa:<job_id>" (iteration/reflection events). publish() is thread-safe; delivery happens on
the server's event loop. Per-subscriber queues are bounded: when full, the oldest
`thinking_chunk` is dropped first; `turn`/`result`/`floor_change` events are never dropped.
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Iterable

_DROPPABLE = ("thinking_chunk", "thinking")
_NEVER_DROP = ("turn", "result", "floor_change", "stuck", "stopped", "error", "done", "job_update")


class Subscriber:
    def __init__(self, topics: Iterable[str], maxsize: int = 4000):
        self.topics: set[str] = set(topics)
        self._q: deque[dict] = deque()
        self._max = maxsize
        self._ready = asyncio.Event()
        self.dropped = 0

    def put(self, envelope: dict) -> None:
        if len(self._q) >= self._max:
            etype = (envelope.get("event") or {}).get("type") or envelope.get("type")
            victim = next((i for i, e in enumerate(self._q)
                           if ((e.get("event") or {}).get("type") or e.get("type")) in _DROPPABLE), None)
            if victim is not None:
                del self._q[victim]
                self.dropped += 1
            elif etype in _DROPPABLE:
                self.dropped += 1
                return
            else:
                self._q.popleft()
                self.dropped += 1
        self._q.append(envelope)
        self._ready.set()

    async def get(self, timeout: float | None = None) -> dict | None:
        if not self._q:
            self._ready.clear()
            try:
                await asyncio.wait_for(self._ready.wait(), timeout)
            except asyncio.TimeoutError:
                return None
        return self._q.popleft() if self._q else None


class EventBus:
    def __init__(self):
        self._subs: set[Subscriber] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, topics: Iterable[str]) -> Subscriber:
        sub = Subscriber(topics)
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subs.discard(sub)

    def publish(self, topic: str, event: dict, job_id: str | None = None) -> None:
        """Safe from any thread; silently no-op before the loop is bound (CLI processes)."""
        envelope = {"topic": topic, "job_id": job_id, "event": event}
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._dispatch, topic, envelope)
        except RuntimeError:
            pass

    def _dispatch(self, topic: str, envelope: dict) -> None:
        for sub in list(self._subs):
            if topic in sub.topics or "*" in sub.topics:
                sub.put(envelope)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)


bus = EventBus()
