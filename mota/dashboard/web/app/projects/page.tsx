"use client";
// Game-data projects (24/project = engine default; 51/project + registered roots via the adapter) and their floors.
import { useEffect, useState } from "react";
import { getJson } from "@/lib/api";
import { Widget } from "@/components/Widget";

type Project = { id: string; root: string; builtin: boolean; engine_default: boolean; name: string | null; floors: number; floor_ids: string[]; has: Record<string, boolean> };
type FloorRow = { floor_id: string; title: string; width: number | null; height: number | null; scripted_events: string[] };

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [floors, setFloors] = useState<FloorRow[] | null>(null);
  useEffect(() => { getJson<Project[]>("/api/projects").then((p) => { setProjects(p); if (p[0]) setSel(p[0].id); }).catch(() => {}); }, []);
  useEffect(() => { if (sel) getJson<{ floors: FloorRow[] }>(`/api/projects/${sel}/floors`).then((r) => setFloors(r.floors)).catch(() => setFloors(null)); }, [sel]);
  const p = projects.find((x) => x.id === sel);
  return (
    <div className="grid gap-[var(--gap)] text-xs min-w-0" style={{ gridTemplateColumns: "minmax(240px, 26%) minmax(0, 1fr)" }} data-testid="page-projects">
      <Widget title="HTML5-mota projects" badge={<span className="tag">{projects.length}</span>}
              footer={<>Register more roots in <span className="mono">data/projects.json</span> (id → path). Flag-gated NPC dialogs / afterBattle scripts are listed but not simulated.</>}>
        <div className="space-y-1.5">
        {projects.map((pr) => (
          <div key={pr.id} className={`p-2 rounded cursor-pointer border transition-colors ${sel === pr.id ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--border-soft)] hover:border-[var(--border)] hover:bg-[var(--panel-2)]"}`} onClick={() => setSel(pr.id)} data-testid="project-card">
            <div className="flex gap-2 items-baseline"><b>{pr.name ?? pr.id}</b><span className="muted">{pr.floors} floors</span>{pr.engine_default && <span className="tag tag-ok">engine default</span>}</div>
            <div className="mono muted truncate" title={pr.root}>{pr.root}</div>
            <div className="muted">{Object.entries(pr.has).map(([f, ok]) => <span key={f} className={ok ? "" : "text-red-300"}>{f}{ok ? "✓" : "✗"} </span>)}</div>
          </div>
        ))}
        </div>
      </Widget>
      <Widget title={p?.name ?? sel ?? "floors"} badge={<span className="tag">{floors?.length ?? 0} floors</span>} bodyClass="max-h-[calc(100vh-8rem)] overflow-auto" flush>
        <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>floor</th><th>title</th><th>size</th><th>scripted events (unmodelled)</th><th></th></tr></thead>
          <tbody>{(floors ?? []).map((f) => (
            <tr key={f.floor_id} data-testid="project-floor">
              <td className="mono">{f.floor_id}</td><td className="whitespace-nowrap">{f.title}</td><td className="whitespace-nowrap">{f.width}×{f.height}</td>
              <td className="muted">{f.scripted_events.join(", ")}</td>
              <td>{p?.engine_default && <a className="btn btn-sm" href={`/play/?floor=${encodeURIComponent(f.floor_id === "MT3" ? "mota-floor:MT3" : f.floor_id === "MT4" ? "special-floor:MT4" : f.floor_id)}`}>play</a>}
                  {!p?.engine_default && <a className="btn btn-sm" href={`/play/?floor=${encodeURIComponent(f.floor_id)}&project=${sel}`}>play</a>}</td>
            </tr>))}</tbody></table></div>
      </Widget>
    </div>
  );
}
