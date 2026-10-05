"use client";
// Reference: the exact solver's optima and difficulty of every single floor, model latency, a model ping.
import { useCallback, useEffect, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import { useCatalog, type SingleFloorGroup } from "@/components/ConditionForm";
import { Widget } from "@/components/Widget";
import { num } from "@/lib/format";

type Lat = { n_logs: number; rows: { model: string; mode: string; episodes: number; calls: number; median: number; mean: number; p90: number; chars_mean: number; calls_per_episode: number; min_per_episode: number }[] };

export default function ReferencePage() {
  const [groups, setGroups] = useState<SingleFloorGroup[]>([]);
  const [lat, setLat] = useState<Lat | null>(null);
  const [ping, setPing] = useState<Record<string, unknown>[] | null>(null);
  const [pinging, setPinging] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { presets } = useCatalog();

  const load = useCallback(() => {
    getJson<{ groups: SingleFloorGroup[] }>("/api/single-floors").then((r) => setGroups(r.groups)).catch(() => {});
    getJson<Lat>("/api/latency").then(setLat).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const doPing = async () => {
    if (!confirm("This sends one tiny request per model preset with the configured API key. Continue?")) return;
    setPinging(true); setErr(null);
    try { setPing((await postJson<{ results: Record<string, unknown>[] }>("/api/models/ping", { models: presets.map((p) => p.id) })).results); }
    catch (e) { setErr((e as Error).message); } finally { setPinging(false); }
  };

  return (
    <div className="grid gap-[var(--gap)] text-xs" data-testid="page-reference">
      <Widget title="Single floors: exact optimum and difficulty" testId="floor-reference"
              footer={<>Exact search solver (a corrected copy of the published Java solver, thesis §6.6.1; the published one reported
                HP 22 for complex). <b>Critical</b> = decisions on an optimal route where some alternative makes the boss unwinnable;
                <b> forced</b> = decisions where only the optimal action keeps it winnable. Random = share of 500 random play-throughs that win.</>}>
        <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>floor</th><th>set</th><th>optimum HP</th><th>winning sets</th><th>critical / forced</th><th>random wins</th><th>solver states</th><th>heuristic</th><th>note</th></tr></thead>
          <tbody>{groups.flatMap((g) => g.floors.map((f) => (
            <tr key={f.id}>
              <td className="mono"><a className="link" href={`/maps/?floor=${encodeURIComponent(f.id)}`}>{f.id}</a></td><td className="muted">{g.group}</td>
              <td><b>{f.optimum_hp ?? ""}</b></td><td>{f.winning_sets ?? ""}</td>
              <td>{f.critical != null ? `${f.critical} / ${f.forced}` : ""}</td>
              <td>{f.random_win != null ? `${(f.random_win * 100).toFixed(0)} %` : ""}</td>
              <td>{f.solver_states ?? ""}</td>
              <td className={f.heuristic === "kills" ? "text-emerald-300" : "text-red-300"}>{f.heuristic}</td>
              <td className="muted">{f.note ?? ""}</td>
            </tr>)))}</tbody></table></div>
      </Widget>
      <Widget title="Model latency (from stored run logs)" testId="latency-census"
              badge={<span className="tag">{lat?.n_logs ?? 0} logs</span>}
              actions={<button className="btn btn-sm" onClick={doPing} disabled={pinging} data-testid="btn-llm-ping">{pinging ? "pinging…" : "ping every model (1 call each)"}</button>}
              footer={<>One call = one model decision (a non-forced, non-committed turn). Median seconds per call, per model and request mode.</>}>
        <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>model</th><th>mode</th><th>episodes</th><th>calls</th><th>s/call median</th><th>mean</th><th>p90</th><th>reasoning chars</th><th>calls/episode</th><th>min/episode</th></tr></thead>
          <tbody>{(lat?.rows ?? []).map((r) => <tr key={r.model + r.mode}><td className="mono">{r.model}</td><td>{r.mode}</td><td>{r.episodes}</td><td>{r.calls}</td><td><b>{num(r.median, 1)}</b></td><td>{num(r.mean, 1)}</td><td>{num(r.p90, 1)}</td><td>{r.chars_mean}</td><td>{num(r.calls_per_episode, 1)}</td><td>{num(r.min_per_episode, 1)}</td></tr>)}</tbody></table></div>
        {err && <div className="text-red-300 mt-2">{err}</div>}
        {ping && <div className="scroll-x mt-2"><table className="tbl min-w-max"><thead><tr><th>preset</th><th>model</th><th>latency ms</th><th>response</th><th>error</th></tr></thead>
          <tbody>{ping.map((p, i) => <tr key={i}><td>{String(p.preset_id)}</td><td className="mono">{String(p.model ?? "")}</td><td>{String(p.latency_ms)}</td><td>{String(p.response ?? "")}</td><td className="text-red-300">{String(p.error ?? "")}</td></tr>)}</tbody></table></div>}
      </Widget>
    </div>
  );
}
