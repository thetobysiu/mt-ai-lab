// API client: JSON helpers, the `data: {...}\n\n` SSE reader (same wire format as the legacy UI), WS URL.

export const API_BASE: string = (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/$/, "");

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export function wsUrl(topics: string[]): string {
  const base = API_BASE || (typeof window !== "undefined" ? window.location.origin : "");
  const u = new URL("/ws/events", base);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.searchParams.set("topics", topics.join(","));
  return u.toString();
}

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(typeof body === "object" && body && "error" in (body as Record<string, unknown>)
      ? String((body as Record<string, unknown>).error) : `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

export async function getJson<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(apiUrl(path), { cache: "no-store", ...init });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, body);
  return body as T;
}

export async function postJson<T = unknown>(path: string, body: unknown): Promise<T> {
  return getJson<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
}

/** POST a body and stream `data: <json>` frames; resolves when the stream closes. */
export async function readSse(path: string, body: unknown, onEvent: (ev: Record<string, unknown>) => void,
                              signal?: AbortSignal): Promise<void> {
  const r = await fetch(apiUrl(path), {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}), signal,
  });
  if (!r.ok || !r.body) {
    const b = await r.json().catch(() => ({}));
    throw new ApiError(r.status, b);
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (frame.startsWith("data: ")) {
        try { onEvent(JSON.parse(frame.slice(6))); } catch { /* partial frame */ }
      }
    }
  }
}
