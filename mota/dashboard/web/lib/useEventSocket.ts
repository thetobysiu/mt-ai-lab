"use client";
// WebSocket event-bus hook with auto-reconnect and dynamic topic (un)subscription.
import { useCallback, useEffect, useRef, useState } from "react";
import { wsUrl } from "./api";
import type { WsEnvelope } from "./types";

export type WsStatus = "connecting" | "open" | "closed";

export function useEventSocket(initialTopics: string[], onMessage: (m: WsEnvelope) => void) {
  const [status, setStatus] = useState<WsStatus>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const topicsRef = useRef<Set<string>>(new Set(initialTopics));
  const cbRef = useRef(onMessage);
  cbRef.current = onMessage;
  const initialKey = initialTopics.join(",");

  useEffect(() => {
    let closed = false;
    let retry = 500;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (closed) return;
      setStatus("connecting");
      const ws = new WebSocket(wsUrl([...topicsRef.current]));
      wsRef.current = ws;
      ws.onopen = () => { setStatus("open"); retry = 500; };
      ws.onmessage = (e) => {
        try { cbRef.current(JSON.parse(e.data)); } catch { /* ignore */ }
      };
      ws.onclose = () => {
        setStatus("closed");
        if (!closed) { timer = setTimeout(connect, retry); retry = Math.min(retry * 2, 10000); }
      };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => { closed = true; if (timer) clearTimeout(timer); wsRef.current?.close(); };
  }, [initialKey]);

  const subscribe = useCallback((topics: string[]) => {
    topics.forEach((t) => topicsRef.current.add(t));
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify({ subscribe: topics }));
  }, []);
  const unsubscribe = useCallback((topics: string[]) => {
    topics.forEach((t) => topicsRef.current.delete(t));
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify({ unsubscribe: topics }));
  }, []);

  return { status, subscribe, unsubscribe };
}
