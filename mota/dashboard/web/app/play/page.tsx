"use client";
// Play & test lab: one floor (or the tower) with the map as the centre of the screen.
// Modes: watch an agent (heuristic / LLM / BFS) or play it yourself (manual — click a highlighted
// tile on the map to take that action). ?job=<id> follows a job, ?log=<file> replays a run log.
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getJson, postJson } from "@/lib/api";
import type { ManualPayload, MapData, RunEvent } from "@/lib/types";
import { useSseRun } from "@/lib/useSseRun";
import { applyEvent, emptyRun } from "@/lib/run";
import { ConditionForm, DEFAULT_CONDITION, conditionBody, scenarioFromFloorParam, type Condition } from "@/components/ConditionForm";
import { PromptEditor } from "@/components/PromptEditor";
import { RunView } from "@/components/RunView";
import { JobWatch } from "@/components/JobWatch";
import { Widget } from "@/components/Widget";
import { IconPlay, IconSettings, IconStop, IconTarget } from "@/components/Icons";

function PlayInner() {
  const params = useSearchParams();
  const watchJob = params.get("job");   // /play/?job=<id>  → follow a running/finished job full-size
  const replayLog = params.get("log");  // /play/?log=<file> → replay a stored run log
  if (watchJob) return <JobWatch jobId={watchJob} />;
  if (replayLog) return <LogReplay id={replayLog} />;
  return <PlayLab />;
}

function LogReplay({ id }: { id: string }) {
  const { run, loadEvents } = useSseRun();
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getJson<{ payload: { turns: RunEvent[]; result: RunEvent | null } }>(`/api/log/detail?kind=run&id=${encodeURIComponent(id)}`)
      .then((d) => loadEvents(d.payload.turns, d.payload.result)).catch((e) => setErr(String(e)));
  }, [id, loadEvents]);
  return (
    <div className="flex flex-col gap-[var(--gap)] min-h-0 page-fill">
      <RunView run={run} header={
        <Widget title="Replay" className="shrink-0" testId="log-replay">
          <div className="text-xs space-y-1">
            <div className="mono break-all">{id}</div>
            <a className="link" href={`/logs/?id=${encodeURIComponent(id)}`}>open in Logs</a>
            {err && <div className="text-red-300">{err}</div>}
          </div>
        </Widget>
      } />
    </div>
  );
}

function PlayLab() {
  const params = useSearchParams();
  const project = params.get("project") || null; // foreign HTML5-mota project id (see /projects); null = built-in 24-layer
  const [cond, setCond] = useState<Condition>(() => {
    const sc = scenarioFromFloorParam(params.get("floor"));
    return { ...DEFAULT_CONDITION, scenario: sc ?? DEFAULT_CONDITION.scenario, repeats: 1 };
  });
  const [prompt, setPrompt] = useState("");
  const [promptVersion, setPromptVersion] = useState<number | null>(null);
  const [panel, setPanel] = useState<"none" | "setup" | "prompt">("none");
  const { run, running, error, start, abort, reset, setRun } = useSseRun();
  const [manual, setManual] = useState<ManualPayload | null>(null);
  const [busy, setBusy] = useState(false);
  // Wide screens can afford the setup panel next to a full-size map; narrow ones keep the map first.
  useEffect(() => { if (window.innerWidth >= 1500) setPanel("setup"); }, []);

  const floorKey = cond.scenario.kind === "floor" ? cond.scenario.floor : cond.scenario.start;
  // Load the floor-type seed whenever the floor type changes (shop vs no-shop), as the legacy UI did.
  useEffect(() => {
    getJson<{ prompt: string; version_id: number | null }>(`/api/seed-prompt?floor=${encodeURIComponent(floorKey)}`)
      .then((s) => { setPrompt(s.prompt); setPromptVersion(s.version_id); }).catch(() => {});
  }, [floorKey]);
  const idle = !running && run.snapshots.length === 0;
  useEffect(() => { if (!running) { reset(); setManual(null); } }, [floorKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!idle) return;
    getJson<MapData>(`/api/map?floor=${encodeURIComponent(floorKey)}${project ? `&project=${encodeURIComponent(project)}` : ""}`)
      .then((m) => setRun(applyEvent(emptyRun(), { type: "start", floor_id: m.floor_id ?? floorKey, hero: m.hero, map: m, mode: "preview" } as RunEvent)))
      .catch(() => {});
  }, [floorKey, idle, setRun, project]);

  const tower = cond.scenario.kind === "tower";
  const evalPath = tower ? "/api/evaluate/multi-floor" : "/api/evaluate/stream";
  const projExtra = project ? { project } : {};

  const runHeuristic = () => { setManual(null); setPanel("none"); start(evalPath, conditionBody(cond, null, { mode: "heuristic", ...projExtra })); };
  const runLlm = () => {
    setManual(null);
    setPanel("none");
    const body = conditionBody(cond, prompt, { mode: "llm", prompt_version_id: promptVersion, ...projExtra });
    start(evalPath, body);
  };
  const runJavaBfs = () => { setManual(null); setPanel("none"); start("/api/replay_bfs", { floor: floorKey }); };
  const runPyBfs = () => { setManual(null); setPanel("none"); start("/api/bfs/solve-stream", { floor: floorKey, max_states: 1000000, step_delay_ms: 0 }); };
  const stop = async () => { await postJson("/api/evaluate/stop", {}).catch(() => {}); };

  const applyManual = useCallback((p: ManualPayload, first: boolean) => {
    setManual(p);
    setRun((s) => {
      let n = first ? emptyRun() : s;
      if (first) n = applyEvent(n, { type: "start", floor_id: p.floor_id, hero: p.hero, map: p.map, mode: "manual", initial_enemies: undefined } as RunEvent);
      else if (p.map && n.currentFloor !== p.floor_id) n = applyEvent(n, { type: "floor_change", floor_id: p.floor_id, hero: p.hero, map: p.map, turn: p.turn } as RunEvent);
      if (!first && p.type === "turn" && p.action) {
        n = applyEvent(n, { type: "turn", turn: p.turn, action: p.action, action_id: p.action_id, hero: p.hero, removed: p.removed, floor_id: p.floor_id,
                            state_text: p.state_text, actions_text: p.actions_text, forced: false, action_detail: p.action_detail, action_path: p.action_path } as RunEvent);
      }
      if (p.result) n = applyEvent(n, p.result);
      n.status = p.done ? (p.goal_reached ? "Manual: goal reached" : `Manual: ${p.failure_reason ?? "finished"}`) : `Your turn — pick an action on the map (turn ${p.turn})`;
      return n;
    });
  }, [setRun]);

  const startManual = async () => {
    setBusy(true);
    setPanel("none");
    try {
      const body = tower
        ? { floor: cond.scenario.kind === "tower" ? cond.scenario.start : "MT0", multi_floor: true, end_floor: cond.scenario.kind === "tower" ? cond.scenario.end : "MT4", enable_logging: cond.enableLogging, ...projExtra }
        : { floor: floorKey, enable_logging: cond.enableLogging, ...projExtra };
      const p = await postJson<ManualPayload>("/api/manual/start", body);
      reset();
      applyManual(p, true);
    } finally { setBusy(false); }
  };
  const manualAct = useCallback(async (id: number) => {
    setBusy(true);
    try { applyManual(await postJson<ManualPayload>("/api/manual/action", { action_id: id }), false); } finally { setBusy(false); }
  }, [applyManual]);
  const stopManual = async () => { await postJson("/api/manual/stop", {}).catch(() => {}); setManual(null); };

  const actions = useMemo(() => (manual && !manual.done ? manual.actions : []), [manual]);
  const highlight = useMemo(() => new Set(actions.map((a) => `${a.x},${a.y}`)), [actions]);
  const labels = useMemo(() => Object.fromEntries(actions.map((a) => [`${a.x},${a.y}`, String(a.action_id)])), [actions]);
  const byCell = useMemo(() => new Map(actions.map((a) => [`${a.x},${a.y}`, a])), [actions]);
  const onCellClick = useCallback((x: number, y: number) => {
    const a = byCell.get(`${x},${y}`);
    if (a && !busy) manualAct(a.action_id);
  }, [byCell, busy, manualAct]);

  const scenarioLabel = tower ? `${cond.scenario.kind === "tower" ? cond.scenario.start : ""}→${cond.scenario.kind === "tower" ? cond.scenario.end : ""}` : floorKey;

  return (
    <div className="flex flex-col gap-[var(--gap)] min-h-0 page-fill" data-testid="page-play">
      <div className="toolbar" data-testid="play-toolbar">
        <span className={`tag ${tower ? "tag-info" : ""}`} title={tower
          ? "Tower: several floors, stairs, shops (gold + EXP), tower system prompt"
          : "Single floor: one map, no shop economy, goal = kill the boss"}>{tower ? "tower" : "single floor"}</span>
        <span className="tag" title="scenario">{scenarioLabel}</span>
        {project && <span className="tag tag-warn" data-testid="project-banner" title="tables loaded from the project's data.js/enemys.js/items.js/maps.js; scripted events not simulated">project {project}</span>}
        <span className="muted text-[11px] mono">{cond.preset} · {cond.planning} · LA{cond.lookahead} · T{cond.temperature}{cond.finalStack ? " · final configuration" : ""}{cond.disableOverrides ? " · raw" : ""}</span>
        <span className="sep" />
        <button className="btn btn-sm" onClick={runHeuristic} disabled={running || busy} data-testid="btn-heuristic" title="Greedy rule-based baseline">Heuristic</button>
        <button className="btn btn-sm btn-primary" onClick={runLlm} disabled={running || busy || !prompt} data-testid="btn-llm"><IconPlay />LLM {cond.planning}</button>
        {!tower && <button className="btn btn-sm" onClick={runJavaBfs} disabled={running || busy} data-testid="btn-java-bfs" title="Java BFS reference solver replay">Java BFS</button>}
        {!tower && <button className="btn btn-sm" onClick={runPyBfs} disabled={running || busy} data-testid="btn-py-bfs" title="Python BFS solver (state-space)">Python BFS</button>}
        <button className="btn btn-sm" onClick={startManual} disabled={running || busy} data-testid="btn-manual" title="Play the floor yourself: click highlighted tiles"><IconTarget />Play it yourself</button>
        {running && <button className="btn btn-sm btn-danger" onClick={stop} data-testid="btn-stop"><IconStop />Stop</button>}
        {running && <button className="btn btn-sm btn-ghost" onClick={abort}>Disconnect</button>}
        {manual && <button className="btn btn-sm btn-ghost" onClick={stopManual}>End manual</button>}
        <span className="sep" />
        <button className={`btn btn-sm ${panel === "setup" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPanel((p) => (p === "setup" ? "none" : "setup"))} data-testid="btn-setup"><IconSettings />setup</button>
        <button className={`btn btn-sm ${panel === "prompt" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPanel((p) => (p === "prompt" ? "none" : "prompt"))} data-testid="btn-toggle-prompt">prompt ({prompt.length})</button>
        {error && <span className="tag tag-bad" data-testid="run-error">{error}</span>}
      </div>

      {panel === "setup" && (
        <Widget title="Run setup" actions={<button className="btn btn-sm btn-ghost" onClick={() => setPanel("none")}>hide</button>}>
          <ConditionForm value={cond} onChange={setCond} showRepeats={false} />
        </Widget>
      )}
      {panel === "prompt" && (
        <Widget title="System prompt" actions={<button className="btn btn-sm btn-ghost" onClick={() => setPanel("none")}>hide</button>}>
          <PromptEditor value={prompt} onChange={setPrompt} floorId={floorKey} onVersion={setPromptVersion} />
        </Widget>
      )}

      <RunView
        run={run}
        live={running}
        onCellClick={manual && !manual.done ? onCellClick : undefined}
        highlight={manual && !manual.done ? highlight : undefined}
        labels={manual && !manual.done ? labels : undefined}
        mapExtra={manual && !manual.done ? (
          <div className="text-[11px] muted flex items-center gap-2 flex-wrap" data-testid="manual-hint">
            <span className="tag tag-ok"><IconTarget />your turn</span>
            {actions.length} legal actions — click a highlighted tile, or use the list on the left.
            {manual.floor_progress && <span className="ml-auto">{manual.floor_progress}</span>}
          </div>
        ) : null}
        extra={manual && !manual.done ? (
          <Widget title="Legal actions" className="min-h-0" badge={<span className="tag">{actions.length}</span>}
                  actions={<span className="muted text-[11px]">engine-enumerated</span>} bodyClass="max-h-[36vh] overflow-auto" flush>
            <div className="p-1 space-y-1" data-testid="manual-actions">
              {actions.map((a) => (
                <button key={a.action_id} className="btn btn-sm w-full text-left justify-start" disabled={busy}
                        onClick={() => manualAct(a.action_id)} data-testid="manual-action">
                  <span className="mono muted mr-1">#{a.action_id}</span>
                  <span className="truncate">{a.label}</span>
                  {a.type === "fight" && <span className={`ml-auto ${a.can_win ? "text-emerald-300" : "text-red-300"}`}>{a.can_win ? `−${a.total_damage}` : "lethal"}</span>}
                  {a.is_dead_end && <span className="tag tag-bad ml-1">dead end</span>}
                </button>
              ))}
            </div>
          </Widget>
        ) : null}
      />

      {manual && (
        <Widget title="Prompt text the LLM would see for this turn" className="shrink-0"
                actions={<span className="muted text-[11px]">state + actions, exactly as sent</span>}>
          <details>
            <summary className="muted text-[11px]">show ({(manual.state_text?.length ?? 0) + (manual.actions_text?.length ?? 0)} chars)</summary>
            <pre className="pre max-h-60 mt-1">{manual.state_text}{"\n\n"}{manual.actions_text}</pre>
          </details>
        </Widget>
      )}
    </div>
  );
}

export default function PlayPage() {
  return <Suspense fallback={<p className="muted">Loading…</p>}><PlayInner /></Suspense>;
}
