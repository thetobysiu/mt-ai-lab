"use client";
// System-prompt editor with the versioned prompt store (list / load / save / pin / diff / delete) and seed-prompt files.
import { useCallback, useEffect, useState } from "react";
import { getJson, postJson } from "@/lib/api";

type Version = { id: number; parent_id: number | null; label: string; source?: string; timestamp?: string; created_at?: string; floor_id?: string | null;
  score?: number | null; scores?: Record<string, number>; is_current?: boolean; chars?: number; length?: number };

export function PromptEditor({ value, onChange, floorId, onVersion }: {
  value: string; onChange: (t: string) => void; floorId?: string; onVersion?: (id: number | null) => void;
}) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [current, setCurrent] = useState<number | null>(null);
  const [label, setLabel] = useState("");
  const [diff, setDiff] = useState<string | null>(null);
  const [diffWith, setDiffWith] = useState<number | "">("");
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const v = await getJson<{ versions: Version[] }>("/api/prompt/versions").catch(() => ({ versions: [] }));
    setVersions(v.versions);
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const load = async (id: number) => {
    const v = await getJson<{ text: string; id: number }>(`/api/prompt/load?id=${id}`);
    onChange(v.text);
    setCurrent(v.id);
    onVersion?.(v.id);
  };
  const loadSeed = async () => {
    const q = floorId ? `?floor=${encodeURIComponent(floorId)}` : "";
    const s = await getJson<{ prompt: string; label: string; version_id: number | null }>(`/api/seed-prompt${q}`);
    onChange(s.prompt);
    setCurrent(s.version_id);
    onVersion?.(s.version_id);
    setMsg(`loaded ${s.label}`);
  };
  const save = async () => {
    const r = await postJson<{ version_id: number }>("/api/prompt/save", { text: value, label: label || `manual ${new Date().toISOString().slice(0, 16)}`, source: "manual", parent_id: current, floor_id: floorId });
    setCurrent(r.version_id);
    onVersion?.(r.version_id);
    setMsg(`saved as v${r.version_id}`);
    setLabel("");
    refresh();
  };
  const pin = async () => { if (current != null) { await postJson("/api/prompt/set-current", { version_id: current }); setMsg(`v${current} pinned as active`); refresh(); } };
  const del = async (id: number) => { if (confirm(`Delete prompt v${id}?`)) { await postJson("/api/prompt/delete", { version_id: id }); refresh(); } };
  const showDiff = async () => {
    if (current == null || diffWith === "") return;
    const d = await getJson<{ diff?: string; unified?: string; lines?: string[] }>(`/api/prompt/diff?a=${diffWith}&b=${current}`);
    setDiff(d.diff ?? d.unified ?? (d.lines ? d.lines.join("\n") : JSON.stringify(d, null, 1)));
  };

  return (
    <div className="space-y-2 text-xs" data-testid="prompt-editor">
      <div className="flex flex-wrap gap-2 items-center">
        <span className="muted">System prompt</span>
        {current != null && <span className="tag">v{current}</span>}
        <span className="muted">{value.length.toLocaleString()} chars</span>
        <button className="btn" onClick={loadSeed} data-testid="prompt-load-seed" title="engine default seed for this floor type (no-shop for simple/complex, shop for MT*)">floor seed</button>
        <select className="input" value="" onChange={(e) => e.target.value && load(Number(e.target.value))} data-testid="prompt-version-select">
          <option value="">load version…</option>
          {versions.map((v) => <option key={v.id} value={v.id}>v{v.id} {v.is_current ? "★ " : ""}{v.label}{v.score != null ? ` (${v.score.toFixed(3)})` : ""}</option>)}
        </select>
        <input className="input w-44" placeholder="label for save" value={label} onChange={(e) => setLabel(e.target.value)} />
        <button className="btn" onClick={save} data-testid="prompt-save">save version</button>
        <button className="btn" onClick={pin} disabled={current == null} title="make this the active prompt">pin</button>
        <select className="input" value={diffWith} onChange={(e) => setDiffWith(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">diff against…</option>
          {versions.filter((v) => v.id !== current).map((v) => <option key={v.id} value={v.id}>v{v.id} {v.label}</option>)}
        </select>
        <button className="btn" onClick={showDiff} disabled={current == null || diffWith === ""}>diff</button>
        {msg && <span className="text-emerald-300">{msg}</span>}
      </div>
      <textarea className="input w-full mono text-[11px] leading-snug" rows={14} value={value} onChange={(e) => { onChange(e.target.value); }} data-testid="prompt-text" />
      {diff && (
        <details open><summary className="muted">diff v{String(diffWith)} → v{current}</summary>
          <pre className="pre max-h-80">
            {diff.split("\n").map((l, i) => <div key={i} className={l.startsWith("+") ? "text-emerald-300" : l.startsWith("-") ? "text-red-300" : "muted"}>{l}</div>)}
          </pre>
        </details>
      )}
      <details><summary className="muted">versions ({versions.length})</summary>
        <table className="tbl mt-1"><tbody>
          {versions.map((v) => (
            <tr key={v.id}>
              <td className="py-0.5 mono">v{v.id}{v.is_current ? " ★" : ""}</td><td>{v.label}</td><td className="muted">{v.source}</td>
              <td className="muted">{v.floor_id ?? ""}</td><td className="mono">{v.score != null ? v.score.toFixed(3) : (v.scores ? Object.entries(v.scores).map(([f, s]) => `${f}:${s.toFixed(2)}`).join(" ") : "")}</td>
              <td className="muted">{(v.timestamp ?? v.created_at ?? "").slice(0, 16)}</td>
              <td><button className="btn" onClick={() => load(v.id)}>load</button> <button className="btn text-red-300" onClick={() => del(v.id)}>del</button></td>
            </tr>
          ))}
        </tbody></table>
      </details>
    </div>
  );
}
