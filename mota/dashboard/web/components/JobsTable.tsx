"use client";
import { useMemo, useState } from "react";
import type { Job } from "@/lib/types";
import { ago, dur, shortModel } from "@/lib/format";
import { IconMap, IconPause, IconPlay, IconX } from "./Icons";

const STATUS_COL: Record<string, string> = {
  running: "text-emerald-300", paused: "text-amber-300", queued: "text-sky-300", done: "muted", failed: "text-red-300", killed: "text-orange-300", stopped: "text-orange-300",
};

export function statusDot(status: string) {
  const cls = status === "running" ? "dot-running" : status === "paused" ? "dot-paused" : status === "queued" ? "dot-queued" : status === "done" ? "dot-done" : "dot-bad";
  return <span className={`dot ${cls}`} />;
}

export function isActive(j: Job): boolean {
  return j.status === "running" || j.status === "queued" || j.status === "paused";
}

export function jobScenario(j: Job): string {
  if (j.start) return `${j.start}→${j.end}${j.checkpoint != null ? ` (cp ${j.checkpoint})` : ""}`;
  return j.floor ?? (j.condition?.floors ? String((j.condition.floors as string[]).join(",")) : "–");
}

export function jobProgress(j: Job): string {
  const p = j.progress ?? {};
  const bits: string[] = [];
  if (p.repeats_total != null) bits.push(`run ${p.run_idx ?? p.repeats_done ?? 0}/${p.repeats_total}`);
  if (p.cells_total != null) bits.push(`cell ${p.cells_done ?? 0}/${p.cells_total}`);
  if (p.iteration != null) bits.push(`iter ${p.iteration}${p.max_calls ? `/${p.max_calls}` : ""}`);
  if (p.turn != null) bits.push(`turn ${p.turn}`);
  if (p.floor_id) bits.push(String(p.floor_id));
  if (p.hp != null) bits.push(`HP ${p.hp}`);
  if (p.atk != null) bits.push(`${p.atk}/${p.def}`);
  return bits.join(" · ");
}

const FLOOR_ORDER = [...Array.from({ length: 23 }, (_, i) => `MT${i}`), "MT23w", "MT23e", "MT23s"];
const floorRank = (f: string | null | undefined) => (f ? FLOOR_ORDER.indexOf(f) : -1);

export function jobResult(j: Job): string {  const r = j.result ?? {};
  if (j.error && j.status !== "done") return j.error;
  if (j.kind === "tower" && Array.isArray(r.max_floor_ids) && (r.max_floor_ids as string[]).length) {
    const ids = r.max_floor_ids as string[];
    const best = ids.reduce((a, b) => (floorRank(b) > floorRank(a) ? b : a));
    return ids.length > 1 ? `highest ${best} (${ids.join(", ")})` : `highest ${best}`;
  }
  if (j.kind === "tower" && r.floors_reached_max != null) return `highest ${FLOOR_ORDER[r.floors_reached_max as number] ?? r.floors_reached_max}`;
  if ("success_rate" in r) return `${r.successes}/${r.n} success${(r.success_ci95 as number[] | undefined) ? ` [${(r.success_ci95 as number[]).map((x) => x.toFixed(2)).join(", ")}]` : ""}`;
  if ("success" in r) return `${r.success ? "SUCCESS" : "fail"}${r.hp_ratio != null ? ` HP/opt ${((r.hp_ratio as number) * 100).toFixed(0)}%` : ""}${r.max_floor_id ? ` max ${r.max_floor_id}` : ""}`;
  if ("best_score" in r) return `best ${(r.best_score as number)?.toFixed?.(3)} (${r.iterations} iters)`;
  return "";
}

/** Actions committed per model call: "1 (reactive)", "2", "3", "5", "max" (re-planned) or "max, once" (single call). */
export function jobPlan(j: Job): string {
  if (j.kind !== "reliability" && j.kind !== "tower") return "";
  if (j.mode === "heuristic") return "–";
  const c = (j.condition ?? {}) as Record<string, unknown>;
  const env = (c.env ?? {}) as Record<string, string>;
  let steps = Number(env.MOTA_PLAN_STEPS ?? c.plan_steps ?? NaN);
  let once = env.MOTA_PLAN_NO_REPLAN === "1" || c.one_shot === true;
  if (Number.isNaN(steps)) {  // older manifests carry no env: read the label suffix
    const m = /_plan(\d+)(?:_|$)/.exec(j.label);
    steps = m ? Number(m[1]) : /_(planf|maxsteps|oneshot_plan)/.test(j.label) ? 60 : 1;
    once = once || /_(maxsteps_once|oneshot_plan)/.test(j.label);
  }
  return once ? "max, once" : steps >= 60 ? "max" : steps <= 1 ? "1 (reactive)" : String(steps);
}

const planRank = (p: string) => (p === "1 (reactive)" ? 1 : p === "max" ? 60 : p === "max, once" ? 61 : Number(p) || 0);

/** Lookahead depth from the job's command line (`--lookahead N`) or its condition; engine default 3. */
export function jobLookahead(j: Job): string {
  if (j.kind !== "reliability" && j.kind !== "tower") return "";
  const c = (j.condition ?? {}) as Record<string, unknown>;
  for (const args of [j.argv as string[] | undefined, c.args as string[] | undefined]) {
    const i = Array.isArray(args) ? args.indexOf("--lookahead") : -1;
    if (i >= 0 && args![i + 1] != null) return String(args![i + 1]);
  }
  if (c.lookahead != null) return String(c.lookahead);
  const env = (c.env ?? {}) as Record<string, string>;
  return env.LOOKAHEAD_DEPTH ?? "3";
}

type SortKey = "status" | "kind" | "label" | "scenario" | "model" | "mode" | "plan" | "lookahead" | "result" | "src" | "elapsed" | "updated";
const COLUMNS: [SortKey, string][] = [["status", "status"], ["kind", "kind"], ["label", "label"], ["scenario", "scenario"], ["model", "model"],
  ["mode", "mode"], ["plan", "steps / call"], ["lookahead", "lookahead"], ["result", "result"], ["src", "src"], ["elapsed", "elapsed"], ["updated", "updated"]];

function cellText(j: Job, k: SortKey): string {
  switch (k) {
    case "status": return j.status;
    case "kind": return j.kind;
    case "label": return j.label;
    case "scenario": return jobScenario(j);
    case "model": return shortModel(j.model ?? (j.preset === "heuristic" ? null : j.preset)) ?? "";
    case "mode": return j.mode ?? "";
    case "plan": return jobPlan(j);
    case "lookahead": return jobLookahead(j);
    case "result": return `${jobResult(j)} ${isActive(j) ? jobProgress(j) : ""}`;
    case "src": return j.source;
    case "elapsed": return dur(j.started_at, j.finished_at);
    case "updated": return ago(j.updated_at);
  }
}

function sortValue(j: Job, k: SortKey): string | number {
  switch (k) {
    case "status": return j.status;
    case "kind": return j.kind;
    case "label": return j.label;
    case "scenario": return jobScenario(j);
    case "model": return shortModel(j.model ?? j.preset) ?? "";
    case "mode": return j.mode ?? "";
    case "plan": return planRank(jobPlan(j));
    case "lookahead": return Number(jobLookahead(j)) || 0;
    case "result": {
      const ids = (j.result?.max_floor_ids as string[] | undefined) ?? [];
      return j.kind === "tower" && ids.length ? Math.max(...ids.map(floorRank)) : jobResult(j);
    }
    case "src": return j.source;
    case "elapsed": return (j.finished_at ? Date.parse(j.finished_at) : Date.now()) - Date.parse(j.started_at);
    case "updated": return j.updated_at;
  }
}

/** Text filter over label, scenario, model, mode and steps; status filter "active" = queued/running/paused. */
export function jobMatches(j: Job, text: string, status: string): boolean {
  if (status === "active" ? !isActive(j) : status !== "all" && j.status !== status) return false;
  if (!text) return true;
  const hay = `${j.label} ${jobScenario(j)} ${j.model ?? ""} ${j.preset ?? ""} ${j.mode ?? ""} ${j.kind} ${jobPlan(j)}`.toLowerCase();
  return text.toLowerCase().split(/\s+/).every((t) => hay.includes(t));
}

export function JobsTable({ jobs, selected, onSelect, onKill, onPause, showFinished = true, filter = "", status = "all" }: {
  jobs: Job[]; selected?: string | null; onSelect?: (j: Job) => void; onKill?: (j: Job) => void;
  onPause?: (j: Job, paused: boolean) => void; showFinished?: boolean; filter?: string; status?: string;
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 } | null>(null);  // null = newest first (server order)
  const [colFilter, setColFilter] = useState<Partial<Record<SortKey, string>>>({});
  const rows = useMemo(() => {
    const active = Object.entries(colFilter).filter(([, v]) => v && v.trim()) as [SortKey, string][];
    const r = (showFinished ? jobs : jobs.filter(isActive)).filter((j) => jobMatches(j, filter, status))
      .filter((j) => active.every(([k, v]) => v.toLowerCase().split(/\s+/).every((t) => cellText(j, k).toLowerCase().includes(t))));
    if (!sort) return r;
    return [...r].sort((a, b) => {
      const x = sortValue(a, sort.key), y = sortValue(b, sort.key);
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * sort.dir;
    });
  }, [jobs, showFinished, filter, status, sort, colFilter]);
  const clickHeader = (key: SortKey) =>
    setSort((s) => (!s || s.key !== key ? { key, dir: 1 } : s.dir === 1 ? { key, dir: -1 } : null));
  return (
    <table className="tbl" data-testid="jobs-table">
      <thead>
        <tr>
          {COLUMNS.map(([key, name]) => (
            <th key={key} className="cursor-pointer select-none whitespace-nowrap" onClick={() => clickHeader(key)} data-testid={`job-sort-${key}`}
                title="click to sort (again: descending, third click: newest first)" aria-sort={sort?.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
              {name}<span className={sort?.key === key ? "" : "muted opacity-50"}>{sort?.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : " ⇅"}</span>
            </th>
          ))}
          <th></th>
        </tr>
        <tr>
          {COLUMNS.map(([key]) => (
            <th key={key} className="py-1">
              <input className="input w-full min-w-[4rem] text-[11px] py-0.5" placeholder="filter" value={colFilter[key] ?? ""}
                     data-testid={`job-filter-${key}`} onChange={(e) => setColFilter((f) => ({ ...f, [key]: e.target.value }))} />
            </th>
          ))}
          <th>{Object.values(colFilter).some((v) => v) && <button className="btn btn-sm" onClick={() => setColFilter({})}>clear</button>}</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && <tr><td colSpan={13} className="muted py-4 text-center">no jobs</td></tr>}
        {rows.map((j) => {
          const pausing = j.status === "running" && j.pause_requested;
          return (
            <tr key={j.job_id} data-testid="job-row" data-status={j.status}
                className={`clickable ${selected === j.job_id ? "selected" : ""}`} onClick={() => onSelect?.(j)}>
              <td className={`whitespace-nowrap ${STATUS_COL[j.status] ?? ""}`}>
                {statusDot(j.status)}{pausing ? "pausing…" : j.status}
                {j.uses_api && (j.status === "running" || j.status === "paused") ? <span className="tag tag-warn ml-1" title="holds the LLM API">API</span> : null}
              </td>
              <td>{j.kind}</td>
              <td className="mono max-w-[16rem] truncate" title={j.label}>{j.label}</td>
              <td className="mono">{jobScenario(j)}</td>
              <td title={j.model ?? ""}>{shortModel(j.model ?? (j.preset === "heuristic" ? null : j.preset))}</td>
              <td>{j.mode ?? ""}</td>
              <td className="whitespace-nowrap" data-testid="job-plan">{jobPlan(j)}</td>
              <td className="whitespace-nowrap" data-testid="job-lookahead">{jobLookahead(j)}</td>
              <td className="max-w-[16rem]" title={jobResult(j)}>
                <div className="truncate">{jobResult(j)}</div>
                {isActive(j) && jobProgress(j) && <div className="mono muted truncate">{jobProgress(j)}</div>}
              </td>
              <td className="muted">{j.source}</td>
              <td className="mono muted">{dur(j.started_at, j.finished_at)}</td>
              <td className="mono muted">{ago(j.updated_at)}</td>
              <td className="whitespace-nowrap">
                <span className="inline-flex gap-1" onClick={(e) => e.stopPropagation()}>
                  {isActive(j) && onPause && j.status !== "queued" && (
                    j.status === "paused" || pausing
                      ? <button className="btn btn-sm" onClick={() => onPause(j, false)} data-testid="job-resume" title="Resume"><IconPlay />resume</button>
                      : <button className="btn btn-sm" onClick={() => onPause(j, true)} data-testid="job-pause" title="Pause after the current turn"><IconPause />pause</button>
                  )}
                  <a className="btn btn-sm" href={`/play/?job=${encodeURIComponent(j.job_id)}`} data-testid="job-open-play" title="Open in Play (map, steps, CoT)"><IconMap />play</a>
                  {j.run_logs && j.run_logs.length > 1 && (
                    <select className="btn btn-sm" value="" data-testid="job-run-select" title="Replay one run of this job (each run has its own log)"
                            onChange={(e) => { if (e.target.value) window.location.href = `/play/?log=${encodeURIComponent(e.target.value)}`; }}>
                      <option value="">runs ({j.run_logs.length})</option>
                      {j.run_logs.map((f, i) => <option key={f} value={f}>run {i + 1}{f === j.current_run_log && isActive(j) ? " (live)" : ""}</option>)}
                    </select>
                  )}
                  {isActive(j) && onKill && (
                    <button className="btn btn-sm btn-danger" onClick={() => onKill(j)} data-testid="job-kill" title="Kill the process"><IconX />kill</button>
                  )}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
