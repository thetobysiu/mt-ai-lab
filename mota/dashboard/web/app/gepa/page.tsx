"use client";
// GEPA: the prompt-optimisation runs of the thesis, iteration by iteration, plus the pre-registered study.
// A constrained-GEPA iteration = (1) the current prompt is played on the training floors; (2) if it beats the best so far
// it becomes the parent, else it is dropped; (3) a teacher model reads the episodes and writes a new prompt; (4) a
// validator rejects prompts that break the two-prompt rules (positions, allow-lists, …). Thesis §5.2.1b, §8.20.12.
import { useCallback, useEffect, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import { useCatalog } from "@/components/ConditionForm";
import { Widget } from "@/components/Widget";
import { num } from "@/lib/format";

type RunRow = { label: string; kind: "constrained" | "historical"; model?: string; teacher?: string; floors: string[]; seed?: string; obs?: string;
  iterations?: number; seed_score?: number | null; best_score?: number | null; kept_seed?: boolean; started?: string; finished?: boolean; study?: boolean };
type Proc = { pid: number; title: string; running: boolean; exit_code: number | null; log: string; tail: string[] };
type Episode = { floor: string; success: boolean | null; final_hp: number | null; objective: number | null; run_log: string | null; failure?: string | null };
type Iter = { iteration: number; score: number; new_best: boolean; best_so_far: number; dropped: boolean; eval_s: number; prompt: string; prev_prompt: string;
  episodes: Episode[]; teacher: null | { seconds: number; diagnosis: string; violations: string[]; retry_violations?: string[] | null; accepted: boolean | null } };
type Arm = { prompt: string; split: string; n: number; kills: number; goal: number | null };
type Study = { label: string; preset: string; obs: string; train: string[]; test: string[]; repeat: number; arms: Arm[];
  grid: Record<string, Record<string, { success: boolean; hp: number }[]>>; file?: string };
type Detail = { label: string; kind: "constrained"; model: string; teacher: string; floors: string[]; tower: [string, string] | null; seed: string; obs: string;
  rollouts: number; select: string; rich_trace: boolean; env: Record<string, string>; best_score: number; best_prompt: string; iterations: Iter[]; study: Study | null }
  | { label: string; kind: "historical"; config: Record<string, unknown>; objective: string; seed_prompt: string; best_prompt: string; best_score: number; scores: number[]; early_stopped: boolean };

export default function GepaPage() {
  const [tab, setTab] = useState<"runs" | "study" | "new">("runs");
  return (
    <div className="flex flex-col gap-[var(--gap)] min-h-0" data-testid="page-gepa">
      <div className="toolbar">
        {([["runs", "Runs, iteration by iteration"], ["study", "Pre-registered study (§8.20.12)"], ["new", "Start a run"]] as const).map(([t, l]) => (
          <button key={t} className={`btn btn-sm ${tab === t ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab(t)} data-testid={`gepa-tab-${t}`}>{l}</button>
        ))}
        <span className="muted text-[11px] ml-auto">An iteration plays the current prompt, keeps it if it beats the best so far, then a teacher model reads the episodes and writes the next prompt.</span>
      </div>
      {tab === "runs" && <Runs />}
      {tab === "study" && <StudyView />}
      {tab === "new" && <NewRun onStarted={() => setTab("runs")} />}
    </div>
  );
}

function Runs() {
  const [rows, setRows] = useState<RunRow[]>([]);
  const [active, setActive] = useState<Proc[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const load = useCallback(() => getJson<{ runs: RunRow[]; active: Proc[] }>("/api/gepa/runs").then((r) => { setRows(r.runs); setActive(r.active); }).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
  useEffect(() => {
    if (!sel) return;
    const f = () => getJson<Detail>(`/api/gepa/run?label=${encodeURIComponent(sel)}`).then(setDetail).catch(() => {});
    f(); const t = setInterval(f, 15000); return () => clearInterval(t);
  }, [sel]);
  const constrained = rows.filter((r) => r.kind === "constrained");
  const historical = rows.filter((r) => r.kind === "historical");
  return (
    <div className="grid gap-[var(--gap)] grid-cols-[minmax(320px,420px)_minmax(0,1fr)] min-h-0">
      <div className="flex flex-col gap-[var(--gap)] min-h-0">
        {active.length > 0 && <Widget title="Running" testId="gepa-active">{active.map((p) => <ProcLine key={p.pid} p={p} />)}</Widget>}
        <Widget title="Constrained GEPA (Sept 2026, the thesis method)" testId="gepa-runs" badge={<span className="tag">{constrained.length}</span>} bodyClass="text-xs" flush
                footer={<>score = mean two-tier goal score over the training floors (tower: floors reached). “seed kept” = no rewrite beat the seed.</>}>
          <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>run</th><th>model</th><th>obs</th><th>floors</th><th>iters</th><th>seed → best</th><th></th></tr></thead>
            <tbody>{constrained.map((r) => (
              <tr key={r.label} className={`clickable ${sel === r.label ? "selected" : ""}`} onClick={() => setSel(r.label)} data-testid="gepa-run-row">
                <td className="mono">{r.label}{!r.finished && <span className="tag tag-warn ml-1">partial</span>}</td><td>{r.model}</td><td>{r.obs}</td>
                <td className="muted">{r.floors.join(", ")}</td><td>{r.iterations}</td>
                <td>{num(r.seed_score, 3)} → <b>{num(r.best_score, 3)}</b></td>
                <td>{r.kept_seed ? <span className="tag">seed kept</span> : <span className="tag tag-ok">rewrite</span>}{r.study && <span className="tag tag-info ml-1">study</span>}</td>
              </tr>))}</tbody></table></div>
        </Widget>
        <Widget title="Historical GEPA (April–May 2026, gepa library)" badge={<span className="tag">{historical.length}</span>} bodyClass="text-xs" flush
                footer={<>Single episodes on the early, unannotated stack; composite score. Only seed, best prompt and candidate scores were stored.</>}>
          <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>run</th><th>model</th><th>candidates</th><th>seed → best</th></tr></thead>
            <tbody>{historical.map((r) => (
              <tr key={r.label} className={`clickable ${sel === r.label ? "selected" : ""}`} onClick={() => setSel(r.label)} data-testid="gepa-run-row">
                <td className="mono">{r.label}</td><td className="muted">{r.model}</td><td>{r.iterations}</td><td>{num(r.seed_score, 3)} → <b>{num(r.best_score, 3)}</b></td>
              </tr>))}</tbody></table></div>
        </Widget>
      </div>
      <div className="min-h-0 overflow-auto">
        {!detail ? <Widget title="Select a run"><span className="muted text-xs">Pick a run on the left to see what each iteration evaluated, what the teacher diagnosed, and how the prompt changed.</span></Widget>
          : detail.kind === "historical" ? <HistoricalDetail d={detail} /> : <ConstrainedDetail d={detail} />}
      </div>
    </div>
  );
}

function ProcLine({ p }: { p: Proc }) {
  return (
    <div className="text-xs space-y-1">
      <div className="flex gap-2 items-center"><span className={`tag ${p.running ? "tag-ok" : ""}`}>{p.running ? "running" : `exit ${p.exit_code}`}</span><b>{p.title}</b>
        {p.running && <button className="btn btn-sm btn-ghost ml-auto" onClick={() => postJson("/api/procs/stop", { pid: p.pid })}>stop</button>}</div>
      <pre className="pre max-h-24">{p.tail.join("\n")}</pre>
      <div className="muted mono">{p.log}</div>
    </div>
  );
}

function ConstrainedDetail({ d }: { d: Extract<Detail, { kind: "constrained" }> }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="flex flex-col gap-[var(--gap)]" data-testid="gepa-detail">
      <Widget title={d.label} badge={<span className="tag">{d.obs} observation</span>}>
        <div className="text-xs grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
          <span className="muted">task model</span><span>{d.model}</span>
          <span className="muted">teacher</span><span>{d.teacher}{d.rich_trace ? " (sees the options offered at each decision)" : ""}</span>
          <span className="muted">training</span><span>{d.tower ? `tower ${d.tower[0]}→${d.tower[1]}` : d.floors.join(", ")} × {d.rollouts} episode(s) per candidate</span>
          <span className="muted">seed prompt</span><span className="mono">{d.seed}</span>
          <span className="muted">parent rule</span><span>{d.select === "best" ? "reflect from the best prompt so far (worse rewrites are dropped)" : "reflect from the latest prompt"}</span>
          <span className="muted">best score</span><b>{num(d.best_score, 3)}</b>
        </div>
      </Widget>
      <Widget title="Iterations" testId="gepa-iterations" bodyClass="text-xs" flush
              footer={<>Row = one candidate prompt played on the training floors. ★ = new best. The teacher column is the rewrite proposed <i>after</i> seeing these episodes (it becomes the next row if the validator accepts it).</>}>
        <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>#</th><th>score</th><th>episodes (floor: ✓/✗ HP)</th><th>kept?</th><th>teacher → next prompt</th><th></th></tr></thead>
          <tbody>{d.iterations.map((it) => (
            <tr key={it.iteration} className={open === it.iteration ? "selected" : ""}>
              <td>{it.iteration}{it.iteration === 0 ? " (seed)" : ""}</td>
              <td className={it.new_best ? "text-emerald-300" : ""}>{num(it.score, 3)}{it.new_best ? " ★" : ""}</td>
              <td className="mono">{it.episodes.map((e, i) => <span key={i} className={`mr-2 ${e.success ? "text-emerald-300" : "text-red-300"}`}>{e.floor}:{e.success ? "✓" : "✗"}{e.final_hp ?? ""}</span>)}</td>
              <td>{it.dropped ? <span className="tag tag-bad">dropped (worse)</span> : it.new_best ? <span className="tag tag-ok">best</span> : <span className="tag">tie/kept</span>}</td>
              <td>{!it.teacher ? <span className="muted">— (last iteration)</span> : it.teacher.accepted
                ? <span className="tag tag-ok">rewrite accepted</span>
                : <span className="tag tag-bad" title={[...it.teacher.violations, ...(it.teacher.retry_violations ?? [])].join("; ")}>rejected by validator</span>}
                {it.teacher && <span className="muted ml-1">{num(it.teacher.seconds, 0)} s</span>}</td>
              <td><button className="btn btn-sm" onClick={() => setOpen(open === it.iteration ? null : it.iteration)} data-testid="gepa-iter-open">{open === it.iteration ? "hide" : "details"}</button></td>
            </tr>))}</tbody></table></div>
      </Widget>
      {open != null && (() => {
        const it = d.iterations.find((x) => x.iteration === open)!;
        return (
          <div className="grid md:grid-cols-2 gap-[var(--gap)]">
            <Widget title={`Prompt evaluated in iteration ${it.iteration}`} badge={<span className="tag">{it.prompt.length} chars</span>}
                    footer={it.iteration === 0 ? <>the seed prompt</> : <>green = added, red = removed, relative to the previous iteration&apos;s prompt</>}>
              {it.iteration === 0 ? <pre className="pre max-h-[60vh]">{it.prompt}</pre> : <PromptDiff a={it.prev_prompt} b={it.prompt} />}
            </Widget>
            <Widget title="Teacher's diagnosis of these episodes" footer={<>the teacher&apos;s reply up to the rewritten prompt; episodes open in Logs</>}>
              {it.teacher ? <>
                {(it.teacher.violations.length > 0 || (it.teacher.retry_violations ?? []).length > 0) &&
                  <div className="text-red-300 text-xs mb-2">validator: {[...it.teacher.violations, ...(it.teacher.retry_violations ?? [])].join("; ")}</div>}
                <pre className="pre max-h-[50vh] whitespace-pre-wrap">{it.teacher.diagnosis || "(no text before the prompt)"}</pre>
              </> : <span className="muted text-xs">last iteration — no rewrite requested</span>}
              <div className="text-xs mt-2 flex flex-wrap gap-2">{it.episodes.filter((e) => e.run_log).map((e, i) =>
                <a key={i} className="link" href={`/play/?log=${encodeURIComponent(e.run_log!)}`}>replay {e.floor}</a>)}</div>
            </Widget>
          </div>
        );
      })()}
      {d.study && <StudyCard s={d.study} />}
    </div>
  );
}

function HistoricalDetail({ d }: { d: Extract<Detail, { kind: "historical" }> }) {
  return (
    <div className="flex flex-col gap-[var(--gap)]" data-testid="gepa-detail">
      <Widget title={d.label} badge={<span className="tag">historical</span>}>
        <div className="text-xs space-y-1">
          <div>candidate scores: <span className="mono">{(d.scores ?? []).map((s) => s.toFixed(3)).join("  ")}</span>{d.early_stopped ? " · early stop" : ""}</div>
          <div className="muted">{String((d.config ?? {}).task_model ?? "")} · teacher {String((d.config ?? {}).reflection_model ?? "")}</div>
        </div>
      </Widget>
      <Widget title="Seed → best prompt" footer={<>green = added by the optimiser, red = removed</>}><PromptDiff a={d.seed_prompt ?? ""} b={d.best_prompt ?? ""} /></Widget>
    </div>
  );
}

function StudyCard({ s }: { s: Study }) {
  const prompts = Array.from(new Set(s.arms.map((a) => a.prompt)));
  const floors = Object.keys(s.grid);
  return (
    <Widget title={`Paired evaluation · ${s.preset} · ${s.obs} observation`} testId="gepa-study-card" bodyClass="text-xs space-y-2"
            footer={<>core = rules-only prompt; gepa = the evolved prompt; basic = the hand-written floor prompt. Train = floors GEPA optimised on; test = held-out floors.</>}>
      <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>prompt</th><th>train kills</th><th>train goal</th><th>test kills</th><th>test goal</th></tr></thead>
        <tbody>{prompts.map((p) => {
          const tr = s.arms.find((a) => a.prompt === p && a.split === "train"), te = s.arms.find((a) => a.prompt === p && a.split === "test");
          return <tr key={p}><td className="mono">{p}</td><td>{tr ? `${tr.kills}/${tr.n}` : ""}</td><td>{num(tr?.goal, 3)}</td><td><b>{te ? `${te.kills}/${te.n}` : ""}</b></td><td>{num(te?.goal, 3)}</td></tr>;
        })}</tbody></table></div>
      <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>floor</th>{prompts.map((p) => <th key={p}>{p}</th>)}</tr></thead>
        <tbody>{floors.map((f) => <tr key={f}><td className="mono">{f}</td>{prompts.map((p) => <td key={p}>{(s.grid[f][p] ?? []).map((e, i) =>
          <span key={i} className={`mr-1 ${e.success ? "text-emerald-300" : "text-red-300"}`}>{e.success ? "✓" : "✗"}</span>)}</td>)}</tr>)}</tbody></table></div>
    </Widget>
  );
}

function StudyView() {
  const [rows, setRows] = useState<Study[]>([]);
  useEffect(() => { getJson<{ studies: Study[] }>("/api/gepa/study").then((r) => setRows(r.studies)).catch(() => {}); }, []);
  return (
    <div className="grid gap-[var(--gap)] md:grid-cols-2" data-testid="gepa-study">
      {rows.map((s) => <StudyCard key={s.file ?? s.label} s={s} />)}
      {rows.length === 0 && <span className="muted text-xs">no study files in results/gepa_study/</span>}
    </div>
  );
}

function NewRun({ onStarted }: { onStarted: () => void }) {
  const { presets, singleFloors } = useCatalog();
  const [label, setLabel] = useState("");
  const [preset, setPreset] = useState("qwen3.6-35b");
  const [floor, setFloor] = useState("simple");
  const [tower, setTower] = useState(false);
  const [iterations, setIterations] = useState(4);
  const [rollouts, setRollouts] = useState(2);
  const [teacher, setTeacher] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const start = async () => {
    setErr(null);
    try { await postJson("/api/gepa/start", { label, preset, floor, tower, start: "MT0", end: "MT23w", iterations, rollouts, teacher: teacher || undefined }); onStarted(); }
    catch (e) { setErr((e as Error).message); }
  };
  return (
    <Widget title="Start constrained GEPA" testId="gepa-new" bodyClass="text-xs space-y-2"
            footer={<>Runs scripts/run_constrained_gepa.py with the final engine stack, seeded with floor_basic.txt (tower: tower_basic.txt).
              Each iteration costs {rollouts} episode(s) per training floor plus one teacher call. Uses the API key from the top bar.</>}>
      <div className="grid md:grid-cols-4 gap-2">
        <label className="flex flex-col gap-0.5"><span className="muted">label (new)</span><input className="input" value={label} onChange={(e) => setLabel(e.target.value)} data-testid="gepa-label" /></label>
        <label className="flex flex-col gap-0.5"><span className="muted">task model</span>
          <select className="input" value={preset} onChange={(e) => setPreset(e.target.value)}>{presets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
        <label className="flex flex-col gap-0.5"><span className="muted">training</span>
          <select className="input" value={tower ? "tower" : floor} onChange={(e) => { if (e.target.value === "tower") setTower(true); else { setTower(false); setFloor(e.target.value); } }}>
            {singleFloors.flatMap((g) => g.floors).map((f) => <option key={f.id} value={f.id}>{f.id}</option>)}
            <option value="tower">tower MT0 → MT23w</option>
          </select></label>
        <label className="flex flex-col gap-0.5"><span className="muted">teacher (model id)</span>
          <select className="input" value={teacher} onChange={(e) => setTeacher(e.target.value)}>
            <option value="">default (qwen3.5-397b-a17b)</option>{presets.map((p) => <option key={p.id} value={p.model}>{p.model}</option>)}</select></label>
        <label className="flex flex-col gap-0.5"><span className="muted">iterations</span><input className="input" type="number" min={2} max={12} value={iterations} onChange={(e) => setIterations(Number(e.target.value))} /></label>
        <label className="flex flex-col gap-0.5"><span className="muted">episodes per candidate</span><input className="input" type="number" min={1} max={5} value={rollouts} onChange={(e) => setRollouts(Number(e.target.value))} /></label>
      </div>
      <div className="flex gap-2 items-center"><button className="btn btn-primary" onClick={start} disabled={!label} data-testid="btn-gepa-start">Start</button>{err && <span className="text-red-300">{err}</span>}</div>
    </Widget>
  );
}

/** Line-level diff (LCS), enough for prompt evolution. */
function PromptDiff({ a, b }: { a: string; b: string }) {
  const A = a.split("\n"), B = b.split("\n");
  const n = A.length, m = B.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: { t: " " | "+" | "-"; s: string }[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) { out.push({ t: " ", s: A[i] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ t: "-", s: A[i++] }); }
    else { out.push({ t: "+", s: B[j++] }); }
  }
  while (i < n) out.push({ t: "-", s: A[i++] });
  while (j < m) out.push({ t: "+", s: B[j++] });
  return (
    <pre className="pre max-h-[60vh]" data-testid="prompt-diff">
      {out.map((l, k) => <div key={k} className={l.t === "+" ? "text-emerald-300" : l.t === "-" ? "text-red-300 line-through opacity-70" : "muted"}>{l.t} {l.s}</div>)}
    </pre>
  );
}
