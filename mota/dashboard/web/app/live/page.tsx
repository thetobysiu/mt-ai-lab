"use client";
// Live: KPI row + jobs widget + the selected job's run (map/turns/CoT) over the WebSocket.
// Every job (CLI or dashboard) shows up here; pause/resume/kill and "open in Play" are inline.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJson, postJson, API_BASE } from "@/lib/api";
import type { Job, RunEvent, WsEnvelope } from "@/lib/types";
import { useEventSocket } from "@/lib/useEventSocket";
import { applyEvent, applyEvents, emptyRun, type RunState } from "@/lib/run";
import { JobsTable, isActive, jobMatches, jobResult } from "@/components/JobsTable";
import { RunView } from "@/components/RunView";
import { Widget, Stat } from "@/components/Widget";
import { IconDownload, IconMap, IconPause, IconPlay, IconX } from "@/components/Icons";
import { ago, shortModel } from "@/lib/format";

export default function LivePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [run, setRun] = useState<RunState>(emptyRun());
  const [showFinished, setShowFinished] = useState(true);
  const [jobFilter, setJobFilter] = useState("");
  const [jobStatus, setJobStatus] = useState("all");
  const [apiBusy, setApiBusy] = useState<string[]>([]);
  const selectedRef = useRef<string | null>(null);
  selectedRef.current = selected;
  const pending = useRef<RunEvent[]>([]);
  const raf = useRef<number | null>(null);

  const flush = useCallback(() => {
    raf.current = null;
    const evs = pending.current;
    pending.current = [];
    if (evs.length) setRun((s) => applyEvents(s, evs));
  }, []);

  const onMessage = useCallback((m: WsEnvelope) => {
    const ev = m.event;
    if (m.topic === "jobs") {
      if (ev.type === "jobs_snapshot" && ev.jobs) setJobs(ev.jobs);
      else if (ev.type === "job_update" && ev.job) {
        const j = ev.job;
        setJobs((prev) => {
          const i = prev.findIndex((x) => x.job_id === j.job_id);
          const next = i >= 0 ? prev.map((x) => (x.job_id === j.job_id ? j : x)) : [j, ...prev];
          return next.sort((a, b) => (b.started_at > a.started_at ? 1 : -1));
        });
      }
      return;
    }
    if (m.topic === `run:${selectedRef.current}`) {
      if (ev.type === "run_snapshot") {
        const snap = ev.snapshot;
        let s = emptyRun();
        if (snap) {
          s = applyEvents(s, snap.turns as RunEvent[]);
          if (snap.result) s = applyEvent(s, snap.result as RunEvent);
        }
        setRun(s);
        return;
      }
      pending.current.push(ev as RunEvent);
      if (raf.current == null) raf.current = window.requestAnimationFrame(flush);
    }
  }, [flush]);

  const { status, subscribe, unsubscribe } = useEventSocket(["jobs"], onMessage);

  useEffect(() => {
    getJson<{ jobs: Job[]; api_busy: string[] }>("/api/jobs").then((r) => { setJobs(r.jobs); setApiBusy(r.api_busy); }).catch(() => {});
    const t = setInterval(() => getJson<{ jobs: Job[]; api_busy: string[] }>("/api/jobs?active=1").then((r) => setApiBusy(r.api_busy)).catch(() => {}), 5000);
    return () => clearInterval(t);
  }, []);

  const select = useCallback((j: Job) => {
    const prev = selectedRef.current;
    if (prev) unsubscribe([`run:${prev}`]);
    setSelected(j.job_id);
    selectedRef.current = j.job_id;
    setRun(emptyRun());
    subscribe([`run:${j.job_id}`]);
  }, [subscribe, unsubscribe]);

  const kill = useCallback(async (j: Job) => {
    if (!confirm(`Kill job ${j.label} (pid ${j.pid})?`)) return;
    await postJson(`/api/jobs/${j.job_id}/kill`, {});
  }, []);
  const pause = useCallback(async (j: Job, paused: boolean) => {
    await postJson(`/api/jobs/${j.job_id}/${paused ? "pause" : "resume"}`, {}).catch(() => {});
  }, []);

  const sel = jobs.find((j) => j.job_id === selected) ?? null;
  const active = useMemo(() => jobs.filter(isActive), [jobs]);
  const apiHolder = jobs.find((j) => apiBusy.includes(j.job_id)) ?? null;
  const lastDone = useMemo(() => jobs.find((j) => j.status === "done" && j.result), [jobs]);
  const selPausing = sel?.status === "running" && sel.pause_requested;

  return (
    <div className="flex flex-col gap-[var(--gap)] min-h-0 page-fill" data-testid="page-live">
      <div className="stats-row shrink-0">
        <Stat label="Active jobs" value={active.length} sub={`${jobs.length} total`} tone={active.length ? "ok" : undefined} />
        <Stat label="LLM API" value={apiHolder ? "busy" : "free"} tone={apiHolder ? "warn" : "ok"}
              sub={apiHolder ? apiHolder.label : "one API job at a time"} title="Only one job may talk to the SAIA API at a time" />
        <Stat label="Event stream" value={status} tone={status === "open" ? "ok" : "bad"} sub="WebSocket /ws/events" />
        <Stat label="Last result" value={lastDone ? (jobResult(lastDone) || "–") : "–"} sub={lastDone ? `${lastDone.label} · ${ago(lastDone.updated_at)}` : "no finished job yet"} />
        <Stat label="Watching" value={sel ? shortModel(sel.model ?? sel.preset) || sel.kind : "–"}
              sub={sel ? `${run.turnCount} turns · ${run.llmTurns} LLM` : "select a job below"} />
      </div>

      <Widget title="Jobs" badge={<span className="tag">{active.length} active · {jobs.filter((j) => (showFinished || isActive(j)) && jobMatches(j, jobFilter, jobStatus)).length} shown</span>}
              actions={<>
                <input className="input w-52" placeholder="filter label / floor / model / steps" value={jobFilter} onChange={(e) => setJobFilter(e.target.value)} data-testid="job-filter" />
                <select className="input" value={jobStatus} onChange={(e) => setJobStatus(e.target.value)} aria-label="status" data-testid="job-status-filter">
                  {["all", "active", "running", "queued", "paused", "done", "failed", "killed", "stopped"].map((s) => <option key={s}>{s}</option>)}
                </select>
                <label className="flex items-center gap-1 text-[11px]"><input type="checkbox" checked={showFinished} onChange={(e) => setShowFinished(e.target.checked)} /> show finished</label>
              </>}
              bodyClass="max-h-[32vh] overflow-auto scroll-x" flush className="shrink-0">
        <JobsTable jobs={jobs} selected={selected} onSelect={select} onKill={kill} onPause={pause} showFinished={showFinished} filter={jobFilter} status={jobStatus} />
      </Widget>

      {sel ? (
        <RunView
          run={run}
          live={sel.status === "running" || sel.status === "paused"}
          header={
            <Widget title="Selected job" className="shrink-0" testId="selected-job"
                    badge={<span className={`tag ${sel.status === "running" ? "tag-ok" : sel.status === "paused" ? "tag-warn" : ""}`} data-testid="selected-status">{selPausing ? "pausing…" : sel.status}</span>}>
              <div className="text-xs space-y-1.5">
                <div className="mono break-words">{sel.label}</div>
                <div className="muted">{sel.kind} · {sel.source} · pid {sel.pid}</div>
                <div className="flex flex-wrap gap-1">
                  {isActive(sel) && sel.status !== "queued" && (
                    sel.status === "paused" || selPausing
                      ? <button className="btn btn-sm" onClick={() => pause(sel, false)} data-testid="sel-resume"><IconPlay />resume</button>
                      : <button className="btn btn-sm" onClick={() => pause(sel, true)} data-testid="sel-pause"><IconPause />pause</button>
                  )}
                  {isActive(sel) && <button className="btn btn-sm btn-danger" onClick={() => kill(sel)}><IconX />kill</button>}
                  <a className="btn btn-sm" href={`/play/?job=${encodeURIComponent(sel.job_id)}`} data-testid="sel-open-play" title="Full-size map, steps and CoT"><IconMap />Play</a>
                  {sel.current_run_log && <a className="btn btn-sm btn-ghost" href={`${API_BASE}/api/log/download?id=${encodeURIComponent(sel.current_run_log)}`}><IconDownload />log</a>}
                </div>
                {sel.current_run_log && <a className="link mono block break-all" href={`/logs/?id=${encodeURIComponent(sel.current_run_log)}`}>{sel.current_run_log}</a>}
                {sel.run_logs.length > 1 && <div className="muted">{sel.run_logs.length} episodes</div>}
                {sel.error && <div className="text-red-300 break-words">{sel.error}</div>}
                <details><summary className="muted">condition / argv</summary>
                  <pre className="pre mt-1 max-h-40">{JSON.stringify({ condition: sel.condition, argv: sel.argv }, null, 1)}</pre>
                </details>
              </div>
            </Widget>
          }
        />
      ) : (
        <Widget title="No job selected" className="flex-1 min-h-0">
          <div className="text-xs space-y-3 max-w-prose">
            <p className="muted">Select a job above to watch its map, turns and reasoning live. CLI runs (<span className="mono">run_reliability.py</span>, <span className="mono">run_followups.py</span>, <span className="mono">run_model_matrix.py</span>) appear here automatically — they register a job manifest and the server tails their run logs onto the event bus.</p>
            <p className="muted">Pause takes effect after the current turn and keeps the API lock; resume continues the same episode.</p>
            <div className="flex flex-wrap gap-2">
              <a className="btn btn-sm btn-primary" href="/play/?floor=simple"><IconMap />Play a floor</a>
              <a className="btn btn-sm" href="/experiments/">Start a reliability run</a>
              <a className="btn btn-sm" href="/logs/">Browse past runs</a>
            </div>
          </div>
        </Widget>
      )}
    </div>
  );
}
