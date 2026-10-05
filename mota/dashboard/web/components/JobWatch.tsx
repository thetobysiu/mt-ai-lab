"use client";
// Follow one job (dashboard or CLI) full-size: map, steps and CoT stream over the WebSocket; pause/resume/kill inline.
// Used by /play/?job=<id>. Replays the run log so far on subscribe, then applies live deltas.
import { useCallback, useEffect, useRef, useState } from "react";
import { getJson, postJson, API_BASE } from "@/lib/api";
import type { Job, RunEvent, WsEnvelope } from "@/lib/types";
import { useEventSocket } from "@/lib/useEventSocket";
import { applyEvent, applyEvents, emptyRun, type RunState } from "@/lib/run";
import { RunView } from "./RunView";
import { Widget } from "./Widget";
import { isActive, jobProgress, jobResult, statusDot } from "./JobsTable";
import { IconDownload, IconPause, IconPlay, IconX } from "./Icons";

export function JobWatch({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [run, setRun] = useState<RunState>(emptyRun());
  const [missing, setMissing] = useState(false);
  const pending = useRef<RunEvent[]>([]);
  const raf = useRef<number | null>(null);
  const topic = `run:${jobId}`;

  const flush = useCallback(() => {
    raf.current = null;
    const evs = pending.current;
    pending.current = [];
    if (evs.length) setRun((s) => applyEvents(s, evs));
  }, []);

  const onMessage = useCallback((m: WsEnvelope) => {
    const ev = m.event;
    if (m.topic === "jobs") {
      if (ev.type === "jobs_snapshot" && ev.jobs) { const j = ev.jobs.find((x) => x.job_id === jobId); if (j) setJob(j); }
      else if (ev.type === "job_update" && ev.job?.job_id === jobId) setJob(ev.job);
      return;
    }
    if (m.topic !== topic) return;
    if (ev.type === "run_snapshot") {
      const snap = ev.snapshot;
      let s = emptyRun();
      if (snap) {
        s = applyEvents(s, snap.turns as RunEvent[]);
        if (snap.result) s = applyEvent(s, snap.result as RunEvent);
      }
      if (ev.job) setJob(ev.job as Job);
      setRun(s);
      return;
    }
    pending.current.push(ev as RunEvent);
    if (raf.current == null) raf.current = window.requestAnimationFrame(flush);
  }, [flush, jobId, topic]);

  const { status } = useEventSocket(["jobs", topic], onMessage);

  useEffect(() => {
    getJson<Job>(`/api/jobs/${encodeURIComponent(jobId)}`).then(setJob).catch(() => setMissing(true));
  }, [jobId]);

  const pause = (paused: boolean) => postJson(`/api/jobs/${jobId}/${paused ? "pause" : "resume"}`, {}).catch(() => {});
  const kill = () => { if (job && confirm(`Kill job ${job.label} (pid ${job.pid})?`)) postJson(`/api/jobs/${jobId}/kill`, {}); };

  if (missing) return <div className="panel p-4 text-xs text-red-300" data-testid="job-missing">Unknown job {jobId}.</div>;
  const pausing = job?.status === "running" && job.pause_requested;

  return (
    <div className="flex flex-col gap-[var(--gap)] min-h-0 page-fill">
      <RunView
        run={run}
        live={!!job && (job.status === "running" || job.status === "paused")}
        header={
          <Widget title="Job" className="shrink-0" testId="job-watch"
                  badge={job ? <span className={`tag ${job.status === "running" ? "tag-ok" : job.status === "paused" ? "tag-warn" : ""}`} data-testid="job-watch-status">
                    {statusDot(job.status)}{pausing ? "pausing…" : job.status}</span> : null}
                  actions={<span className={`tag ${status === "open" ? "tag-ok" : "tag-bad"}`}>ws {status}</span>}>
            {job ? (
              <div className="text-xs space-y-1.5">
                <div className="mono break-words">{job.label}</div>
                <div className="muted">{job.kind} · {job.source} · {job.model ?? job.preset ?? ""}</div>
                <div className="muted mono">{jobProgress(job)}</div>
                {jobResult(job) && <div className="mono">{jobResult(job)}</div>}
                {job.run_logs && job.run_logs.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1" data-testid="job-runs">
                    <span className="muted">runs (one log each):</span>
                    {job.run_logs.map((f, i) => {
                      const live = f === job.current_run_log && isActive(job);
                      return live
                        ? <span key={f} className="tag tag-ok" title={`${f} — shown here`}>run {i + 1} · live</span>
                        : <a key={f} className="btn btn-sm btn-ghost" href={`/play/?log=${encodeURIComponent(f)}`} title={`replay ${f}`}>run {i + 1}</a>;
                    })}
                  </div>
                )}
                <div className="flex flex-wrap gap-1">
                  {isActive(job) && job.status !== "queued" && (
                    job.status === "paused" || pausing
                      ? <button className="btn btn-sm" onClick={() => pause(false)} data-testid="watch-resume"><IconPlay />resume</button>
                      : <button className="btn btn-sm" onClick={() => pause(true)} data-testid="watch-pause"><IconPause />pause</button>
                  )}
                  {isActive(job) && <button className="btn btn-sm btn-danger" onClick={kill}><IconX />kill</button>}
                  <a className="btn btn-sm btn-ghost" href="/live/">all jobs</a>
                  {job.current_run_log && <a className="btn btn-sm btn-ghost" href={`${API_BASE}/api/log/download?id=${encodeURIComponent(job.current_run_log)}`}><IconDownload />log</a>}
                </div>
              </div>
            ) : <span className="muted text-xs">loading job {jobId}…</span>}
          </Widget>
        }
      />
    </div>
  );
}
