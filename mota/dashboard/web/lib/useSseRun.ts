"use client";
// Drive one SSE run (POST body → events) into a RunState; also used to replay a stored log.
import { useCallback, useRef, useState } from "react";
import { readSse, ApiError } from "./api";
import { applyEvent, applyEvents, emptyRun, type RunState } from "./run";
import type { RunEvent } from "./types";

export function useSseRun() {
  const [run, setRun] = useState<RunState>(emptyRun());
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pending = useRef<RunEvent[]>([]);
  const flushTimer = useRef<number | null>(null);

  // Batch events per animation frame: thinking_chunk arrives at token rate.
  const push = useCallback((ev: RunEvent) => {
    pending.current.push(ev);
    if (flushTimer.current == null) {
      flushTimer.current = window.requestAnimationFrame(() => {
        const evs = pending.current;
        pending.current = [];
        flushTimer.current = null;
        setRun((s) => applyEvents(s, evs));
      });
    }
  }, []);

  const start = useCallback(async (path: string, body: unknown) => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setRun(emptyRun());
    setError(null);
    setRunning(true);
    try {
      await readSse(path, body, (ev) => push(ev as RunEvent), ac.signal);
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        const msg = e instanceof ApiError ? `${e.message}${e.status === 409 ? " (another job holds the API — see Live)" : ""}` : String(e);
        setError(msg);
        push({ type: "error", message: msg });
      }
    } finally {
      setRunning(false);
    }
  }, [push]);

  const stop = useCallback(async (stopPath?: string) => {
    if (stopPath) {
      try { await fetch(stopPath.startsWith("http") ? stopPath : `${process.env.NEXT_PUBLIC_API_BASE || ""}${stopPath}`, { method: "POST" }); } catch { /* ignore */ }
    }
  }, []);

  const abort = useCallback(() => { abortRef.current?.abort(); setRunning(false); }, []);

  const loadEvents = useCallback((evs: RunEvent[], result?: RunEvent | null) => {
    let s = applyEvents(emptyRun(), evs);
    if (result && !s.result) s = applyEvent(s, result);
    s = applyEvent(s, { type: "done" });
    setRun(s);
    setRunning(false);
    setError(null);
  }, []);

  const reset = useCallback(() => { setRun(emptyRun()); setError(null); }, []);

  return { run, running, error, start, stop, abort, loadEvents, reset, push, setRun };
}
