"use client";
// API key for runs started from the dashboard. Sent once to the local server, kept in its memory only;
// the server never returns it (only whether one is set and its last four characters).
import { useCallback, useEffect, useState } from "react";
import { getJson, postJson, apiUrl } from "@/lib/api";

export type Settings = { api_key: { configured: boolean; source: string; hint: string }; base_url: string };

export function useSettings() {
  const [s, setS] = useState<Settings | null>(null);
  const load = useCallback(() => getJson<Settings>("/api/settings").then(setS).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  return { settings: s, reload: load, setSettings: setS };
}

export function ApiKeyPanel({ onChange }: { onChange?: (s: Settings) => void }) {
  const { settings, setSettings } = useSettings();
  const [key, setKey] = useState("");
  const [base, setBase] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    setErr(null);
    try {
      const s = await postJson<Settings>("/api/settings/api-key", { key, base_url: base || undefined });
      setSettings(s); setKey(""); onChange?.(s);
    } catch (e) { setErr((e as Error).message); }
  };
  const clear = async () => {
    const r = await fetch(apiUrl("/api/settings/api-key"), { method: "DELETE" });
    const s = (await r.json()) as Settings;
    setSettings(s); onChange?.(s);
  };
  const k = settings?.api_key;
  return (
    <div className="text-xs space-y-2" data-testid="api-key-panel">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`tag ${k?.configured ? "tag-ok" : "tag-warn"}`} data-testid="api-key-status">
          {k?.configured ? `API key set (from ${k.source})` : "no API key"}
        </span>
        <span className="muted mono break-all">{settings?.base_url}</span>
      </div>
      <div className="flex gap-2 flex-wrap items-center">
        <input className="input w-72" type="password" autoComplete="off" placeholder="paste an OpenAI-compatible API key"
               value={key} onChange={(e) => setKey(e.target.value)} data-testid="api-key-input" />
        <input className="input w-72" placeholder={`endpoint (default ${settings?.base_url ?? "SAIA"})`}
               value={base} onChange={(e) => setBase(e.target.value)} />
        <button className="btn btn-sm btn-primary" onClick={save} disabled={!key} data-testid="api-key-save">Use this key</button>
        {k?.source === "dashboard" && <button className="btn btn-sm btn-ghost" onClick={clear}>forget</button>}
      </div>
      {err && <div className="text-red-300">{err}</div>}
      <div className="muted">Kept in the local server&apos;s memory for this session only; never written to disk or logs. All model presets
        point at the GWDG SAIA endpoint (chat-ai.academiccloud.de); another OpenAI-compatible endpoint works if it serves the same model ids.</div>
    </div>
  );
}
