"use client";
// Experiments: (1) the thesis experiments as a catalog you can re-run with your own API key, (2) a custom
// condition run ×N through the same harness as the CLI, (3) every stored result with its Wilson interval.
import { useCallback, useEffect, useState } from "react";
import { getJson, postJson, readSse, API_BASE } from "@/lib/api";
import type { ReliabilityResult } from "@/lib/types";
import { ci, num, pct } from "@/lib/format";
import { ConditionForm, DEFAULT_CONDITION, conditionBody, harnessFloor, type Condition } from "@/components/ConditionForm";
import { Widget } from "@/components/Widget";
import { ApiKeyPanel } from "@/components/ApiKeyPanel";

type PromptSource = { kind: "default" } | { kind: "file"; name: string } | { kind: "text"; text: string };
type ResultRef = { label: string; n: number | null; successes: number | null; ci: [number, number] | null; hp_ratio: number | null; died: number | null; floors_max: number | null; updated: string | null };
type Cell = { code: string; label: string; scenario: string; preset: string; repeats: number; lookahead: number; prompt_file: string | null;
  overrides_off: boolean; checkpoint: string | null; mode: string; plan_steps: number; one_shot: boolean; final_stack: boolean; flags?: string[]; env: Record<string, string>;
  thesis: ResultRef | null; reruns: ResultRef[] };
type Entry = { group: string; section: string; id: string; title: string; what: string; cells: Cell[]; script: string[] | null };
type Proc = { pid: number; title: string; running: boolean; exit_code: number | null; log: string; tail: string[]; started: string };

export default function ExperimentsPage() {
  const [tab, setTab] = useState<"thesis" | "catalog" | "custom" | "results">("thesis");
  return (
    <div className="flex flex-col gap-[var(--gap)] min-h-0" data-testid="page-experiments">
      <div className="toolbar">
        {([["thesis", "Thesis results"], ["catalog", "Re-run thesis experiments"], ["custom", "Custom run ×N"], ["results", "All stored results"]] as const).map(([t, l]) => (
          <button key={t} className={`btn btn-sm ${tab === t ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab(t)} data-testid={`tab-${t}`}>{l}</button>
        ))}
        <a className="btn btn-sm btn-ghost ml-auto" href="/live/">watch runs in Live →</a>
      </div>
      {tab === "thesis" && <ThesisResults />}
      {tab === "catalog" && <Catalog />}
      {tab === "custom" && <ReliabilityBuilder />}
      {tab === "results" && <ResultsTable />}
    </div>
  );
}

type IndexItem = { path: string; kind: "reliability" | "gepa_study" | "other"; label: string; n?: number | null; successes?: number | null;
  ci?: [number, number] | null; hp_ratio?: number | null; died?: number | null; floors_max?: number | null; logs?: number;
  groups?: { group: string; successes: number; n: number }[] };
type IndexRow = { result: string; files_cell: string; items: IndexItem[] };
type Episode = { run_log: string | null; log_present: boolean; success: boolean | null; died: boolean | null; final_hp: number | null;
  hp_ratio: number | null; floor: string | null; prompt: string | null; split: string | null; rep: number | null };

function itemOutcome(it: IndexItem) {
  if (it.kind === "gepa_study") return <span className="muted">{(it.groups ?? []).map((g) => `${g.group} ${g.successes}/${g.n}`).join(" · ")}</span>;
  if (it.kind !== "reliability") return <span className="muted">analysis file</span>;
  return outcome({ label: it.label, n: it.n ?? null, successes: it.successes ?? null, ci: it.ci ?? null, hp_ratio: it.hp_ratio ?? null,
    died: it.died ?? null, floors_max: it.floors_max ?? null, updated: null });
}

// Table D.4 of the thesis, row by row: every number in Chapter 6 leads to its result files and their episodes.
function ThesisResults() {
  const [data, setData] = useState<{ rows: IndexRow[]; run_logs_present: number; source: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, Episode[] | "loading">>({});
  const [filter, setFilter] = useState("");
  useEffect(() => { getJson<{ rows: IndexRow[]; run_logs_present: number; source: string }>("/api/thesis-results").then(setData).catch((e) => setError(String(e))); }, []);
  const toggle = (path: string) => {
    if (open[path]) { const o = { ...open }; delete o[path]; setOpen(o); return; }
    setOpen({ ...open, [path]: "loading" });
    getJson<{ episodes: Episode[] }>(`/api/thesis-results/file?path=${encodeURIComponent(path)}`)
      .then((r) => setOpen((o) => ({ ...o, [path]: r.episodes }))).catch(() => setOpen((o) => ({ ...o, [path]: [] })));
  };
  if (error) return <Widget title="Thesis results" testId="thesis-results"><span className="text-red-300 text-xs">{error}</span></Widget>;
  if (!data) return <Widget title="Thesis results" testId="thesis-results"><span className="muted text-xs">loading…</span></Widget>;
  const rows = data.rows.filter((r) => !filter || r.result.toLowerCase().includes(filter.toLowerCase()) || r.items.some((i) => i.label.includes(filter)));
  return (
    <Widget title="Thesis results" testId="thesis-results" className="min-h-0" bodyClass="text-xs space-y-3 max-h-[calc(100vh-11rem)] overflow-auto"
            badge={<span className="tag">{data.rows.length} tables and paragraphs</span>}
            actions={<input className="input w-64" placeholder="filter: Table 6.2, hand01, tower …" value={filter} onChange={(e) => setFilter(e.target.value)} data-testid="thesis-filter" />}
            footer={<>Follows Table D.4 of the thesis (Appendix D): each table, figure or paragraph of Chapter 6 with the result files it reports.
              Success = k/N with the Wilson 95% interval; HP/opt = final HP relative to the exact optimum among successes. Click a file to list its episodes.</>}>
      {data.run_logs_present === 0 && (
        <div className="panel p-2 text-amber-300" data-testid="thesis-no-logs">
          The run logs are not downloaded, so episodes cannot be replayed yet. Run <span className="mono">python scripts/fetch_run_logs.py</span> (about 150 MB) and reload.
        </div>
      )}
      {rows.map((row) => (
        <div key={row.result} className="border-t border-[var(--border-soft)] pt-2 first:border-0 first:pt-0" data-testid="thesis-row">
          <div className="font-semibold">{row.result.replace(/\$/g, "")}</div>
          {row.items.length === 0 && <div className="muted">no result file (computed by a script or from the run logs)</div>}
          {row.items.map((it) => {
            const eps = open[it.path];
            return (
              <div key={it.path} className="ml-2">
                <button className="btn btn-sm btn-ghost mono" onClick={() => toggle(it.path)} data-testid="thesis-item">{eps ? "▾" : "▸"} {it.label}</button>
                <span className="ml-2">{itemOutcome(it)}</span>
                {eps === "loading" && <div className="muted ml-6">loading…</div>}
                {Array.isArray(eps) && eps.length > 0 && (
                  <div className="scroll-x ml-6"><table className="tbl min-w-max"><thead><tr><th>#</th><th>prompt / split</th><th>outcome</th><th>HP</th><th>HP/opt</th><th>floor</th><th>run log</th></tr></thead>
                    <tbody>{eps.map((e, i) => (
                      <tr key={i} data-testid="thesis-episode">
                        <td>{e.rep ?? i + 1}</td><td>{e.prompt ? `${e.prompt} · ${e.split}` : ""}</td>
                        <td className={e.success ? "text-emerald-300" : e.died ? "text-red-300" : ""}>{e.success ? "win" : e.died ? "died" : "no win"}</td>
                        <td>{e.final_hp ?? ""}</td><td>{num(e.hp_ratio, 2)}</td><td>{e.floor ?? ""}</td>
                        <td>{!e.run_log ? <span className="muted">none</span> : e.log_present
                          ? <a className="link" href={`/play/?log=${encodeURIComponent(e.run_log)}`}>replay</a>
                          : <span className="muted" title={e.run_log}>log not downloaded</span>}</td>
                      </tr>
                    ))}</tbody></table></div>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </Widget>
  );
}

function outcome(r: ResultRef | null) {
  if (!r || r.n == null) return <span className="muted">—</span>;
  const tower = r.floors_max != null;
  return (
    <span>
      <b className={r.successes ? "text-emerald-300" : ""}>{tower ? `max floor MT${r.floors_max}` : `${r.successes}/${r.n}`}</b>
      {!tower && r.ci && <span className="muted"> {ci(r.ci)}</span>}
      {r.hp_ratio != null && <span className="muted"> · HP/opt {num(r.hp_ratio, 2)}</span>}
      {r.died ? <span className="text-red-300"> · {r.died} died</span> : null}
    </span>
  );
}

// thesis names for the prompt files and floor paths that the catalogue cells store
function promptText(c: Cell) {
  const f = c.prompt_file;
  if (f?.includes("bfs_strategy_survival")) return "solver-route prompt";
  if (f?.includes("exact68")) return "exact-route prompt";
  if (f) return f;
  if (c.env?.MOTA_LEGACY_SEEDS === "1") return "earlier hand-written prompt";
  return c.scenario?.startsWith("tower") ? "tower prompt" : "single-floor prompt";
}

function condText(c: Cell) {
  const longPlan = c.env?.MOTA_PLAN_WORDING === "floor" ? "whole-floor plan" : "max-steps plan";
  const plan = c.one_shot ? `${longPlan}, single call` : c.plan_steps >= 60 ? `${longPlan}, re-planned` : c.plan_steps > 1 ? `commit ${c.plan_steps}` : c.mode === "reactive" ? "reactive" : c.mode;
  const scenario = c.scenario?.replace(/^.*[\\/]/, "").replace(/\.txt$/, "");
  const flags = (c.flags ?? []).filter((f) => f !== "legacy seed prompt");
  return [scenario, c.preset, plan, `LA${c.lookahead}`, promptText(c), c.overrides_off ? "overrides off" : null,
    c.final_stack ? "final configuration" : null, ...flags, c.checkpoint ? `checkpoint ${c.checkpoint}` : null, `N=${c.repeats}`].filter(Boolean).join(" · ");
}

function Catalog() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [repeats, setRepeats] = useState<number | "">(1);
  const [procs, setProcs] = useState<Proc[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => {
    getJson<{ entries: Entry[] }>("/api/catalog").then((r) => setEntries(r.entries)).catch(() => {});
    getJson<Proc[]>("/api/procs?kind=catalog").then(setProcs).catch(() => {});
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [load]);
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const run = async () => {
    setErr(null);
    try { await postJson("/api/catalog/run", { ids: picked, repeats: repeats || undefined }); setPicked([]); load(); }
    catch (e) { setErr((e as Error).message); }
  };
  const groups = Array.from(new Set(entries.map((e) => e.group)));
  const episodes = entries.filter((e) => picked.includes(e.id)).reduce((s, e) => s + e.cells.reduce((t, c) => t + (repeats ? Math.min(c.repeats, Number(repeats)) : c.repeats), 0), 0);
  return (
    <div className="grid gap-[var(--gap)] grid-cols-[minmax(0,1fr)_minmax(320px,420px)] min-h-0" data-testid="catalog">
      <div className="flex flex-col gap-[var(--gap)] min-h-0 overflow-auto">
        {groups.map((g) => (
          <Widget key={g} title={g} bodyClass="text-xs space-y-3">
            {entries.filter((e) => e.group === g).map((e) => (
              <div key={e.id} className="border-t border-[var(--border-soft)] pt-2 first:border-0 first:pt-0" data-testid="catalog-entry" data-id={e.id}>
                <label className="flex items-baseline gap-2 cursor-pointer">
                  <input type="checkbox" checked={picked.includes(e.id)} onChange={() => toggle(e.id)} data-testid="catalog-pick" />
                  <b>{e.title}</b><span className="tag">{e.section}</span>
                </label>
                <div className="muted ml-5">{e.what}</div>
                {e.cells.length > 0 && (
                  <div className="scroll-x ml-5 mt-1"><table className="tbl min-w-max"><thead><tr><th>cell</th><th>condition</th><th>thesis result</th><th>your re-runs</th></tr></thead>
                    <tbody>{e.cells.map((c) => (
                      <tr key={c.code}>
                        <td className="mono" title={c.label}>{c.code}</td>
                        <td className="muted">{condText(c)}</td>
                        <td>{outcome(c.thesis)}</td>
                        <td>{c.reruns.length === 0 ? <span className="muted">—</span> : c.reruns.map((r) => <div key={r.label}>{outcome(r)}</div>)}</td>
                      </tr>))}</tbody></table></div>
                )}
                {e.script && <div className="ml-5 mt-1 mono muted">python {e.script.join(" ")} --label rerun_…</div>}
              </div>
            ))}
          </Widget>
        ))}
      </div>
      <div className="flex flex-col gap-[var(--gap)] min-h-0 overflow-auto">
        <Widget title="1 · API key"><ApiKeyPanel /></Widget>
        <Widget title="2 · Re-run the selected experiments" testId="catalog-run" bodyClass="text-xs space-y-2"
                footer={<>Each cell runs run_reliability.py with the thesis cell&apos;s exact arguments and engine flags, under the label
                  rerun_&lt;time&gt;_&lt;label&gt;, so the thesis results are never overwritten. Episodes appear in Live as they run.</>}>
          <div>{picked.length === 0 ? <span className="muted">tick experiments on the left</span> : picked.join(", ")}</div>
          <label className="flex items-center gap-2"><span className="muted">episodes per cell (cap)</span>
            <input className="input w-16" type="number" min={1} max={20} value={repeats} onChange={(e) => setRepeats(e.target.value === "" ? "" : Number(e.target.value))} data-testid="catalog-repeats" />
            <span className="muted">empty = the thesis N</span></label>
          <div className="flex gap-2 items-center">
            <button className="btn btn-primary" disabled={picked.length === 0} onClick={run} data-testid="btn-catalog-run">Run {episodes} episode(s)</button>
            {err && <span className="text-red-300">{err}</span>}
          </div>
        </Widget>
        {procs.length > 0 && (
          <Widget title="Your re-runs" bodyClass="text-xs space-y-3">
            {procs.map((p) => (
              <div key={p.pid} className="space-y-1">
                <div className="flex gap-2 items-center"><span className={`tag ${p.running ? "tag-ok" : ""}`}>{p.running ? "running" : `exit ${p.exit_code}`}</span><b>{p.title}</b>
                  {p.running && <button className="btn btn-sm btn-ghost ml-auto" onClick={() => postJson("/api/procs/stop", { pid: p.pid }).then(load)}>stop</button>}</div>
                <pre className="pre max-h-32">{p.tail.join("\n")}</pre>
                <div className="muted mono">{p.log}</div>
              </div>
            ))}
          </Widget>
        )}
      </div>
    </div>
  );
}

function usePromptSource(floorKey: string) {
  const [src, setSrc] = useState<PromptSource>({ kind: "default" });
  const [files, setFiles] = useState<{ name: string; chars: number }[]>([]);
  useEffect(() => { getJson<{ files: { name: string; chars: number }[] }>("/api/seed-prompts").then((r) => setFiles(r.files)).catch(() => {}); }, []);
  const resolve = useCallback(async (): Promise<{ prompt: string; name: string }> => {
    if (src.kind === "text") return { prompt: src.text, name: "dashboard-editor" };
    if (src.kind === "file") {
      const f = await getJson<{ text: string }>(`/api/seed-prompts/${encodeURIComponent(src.name)}`);
      return { prompt: f.text, name: src.name };
    }
    const s = await getJson<{ prompt: string }>(`/api/seed-prompt?floor=${encodeURIComponent(floorKey)}`);
    return { prompt: s.prompt, name: "engine-default-seed" };
  }, [src, floorKey]);
  return { src, setSrc, files, resolve };
}

function PromptSourcePicker({ src, setSrc, files }: { src: PromptSource; setSrc: (s: PromptSource) => void; files: { name: string; chars: number }[] }) {
  return (
    <div className="flex flex-wrap gap-2 items-center text-xs">
      <span className="muted">System prompt</span>
      <select className="input" data-testid="prompt-source" value={src.kind === "file" ? `file:${src.name}` : src.kind}
              onChange={(e) => { const v = e.target.value; setSrc(v === "default" ? { kind: "default" } : v === "text" ? { kind: "text", text: src.kind === "text" ? src.text : "" } : { kind: "file", name: v.slice(5) }); }}>
        <option value="default">default (floor_basic.txt / tower_basic.txt)</option>
        <optgroup label="seed_prompts/">{files.map((f) => <option key={f.name} value={`file:${f.name}`}>{f.name} ({(f.chars / 1000).toFixed(1)}K)</option>)}</optgroup>
        <option value="text">custom text…</option>
      </select>
      {src.kind === "text" && <textarea className="input w-full mono text-[11px]" rows={6} value={src.text} onChange={(e) => setSrc({ kind: "text", text: e.target.value })} />}
    </div>
  );
}

function ReliabilityBuilder() {
  const [cond, setCond] = useState<Condition>({ ...DEFAULT_CONDITION, repeats: 5 });
  const [heuristic, setHeuristic] = useState(false);
  const floorKey = cond.scenario.kind === "floor" ? cond.scenario.floor : "MT0-MT23w";
  const { src, setSrc, files, resolve } = usePromptSource(floorKey);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const launch = async (force = false) => {
    setError(null); setEvents([]); setRunning(true);
    try {
      const p = heuristic ? { prompt: null, name: "none" } : await resolve();
      const body = conditionBody(cond, p.prompt, { prompt_name: p.name, force });
      if (cond.scenario.kind === "floor") body.floor = harnessFloor(cond.scenario.floor);
      await readSse("/api/reliability/stream", body, (ev) => setEvents((e) => [...e, ev]));
    } catch (e) { setError(String((e as Error).message)); } finally { setRunning(false); }
  };
  const stop = () => postJson("/api/reliability/stop", {});
  const runs = events.filter((e) => e.type === "run") as { record: Record<string, unknown>; aggregate: Record<string, unknown> }[];
  const last = runs[runs.length - 1];
  const startEv = events.find((e) => e.type === "start") as { job_id?: string; label?: string } | undefined;

  return (
    <Widget title="Custom run ×N" testId="reliability-builder" bodyClass="space-y-3"
            footer={<>Same harness and result format as run_reliability.py: results/reliability/&lt;label&gt;.json with the success rate and its Wilson interval.
              The API key from the top bar is used.</>}>
      <ConditionForm value={cond} onChange={setCond} />
      <div className="flex flex-wrap gap-3 items-center text-xs">
        <label className="flex items-center gap-1"><input type="checkbox" checked={heuristic} onChange={(e) => setHeuristic(e.target.checked)} /> heuristic baseline (no LLM, N=1)</label>
        {!heuristic && <PromptSourcePicker src={src} setSrc={setSrc} files={files} />}
      </div>
      <div className="flex gap-2 items-center text-xs">
        <button className="btn btn-primary" onClick={() => launch(false)} disabled={running} data-testid="btn-run-reliability">Run ×{heuristic ? 1 : cond.repeats}</button>
        {running && <button className="btn text-orange-300" onClick={stop}>Stop after current episode</button>}
        {error?.includes("api_busy") && <button className="btn text-amber-300" onClick={() => launch(true)}>run anyway</button>}
        {error && <span className="text-red-300">{error}</span>}
        {startEv && <span className="muted">job <a className="underline" href="/live/">{startEv.job_id}</a> · label <span className="mono">{startEv.label}</span></span>}
      </div>
      {runs.length > 0 && (
        <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>#</th><th>success</th><th>HP</th><th>HP/opt</th><th>goal</th><th>calls</th><th>committed</th><th>parse err</th><th>s</th><th>floor</th><th>log</th></tr></thead>
          <tbody>{runs.map((r, i) => {
            const rec = r.record as Record<string, number | string | boolean | null>;
            return (<tr key={i}>
              <td>{String(rec.run_idx ?? i + 1)}</td><td className={rec.success ? "text-emerald-300" : "text-red-300"}>{rec.success ? "✓" : "✗"}</td>
              <td>{String(rec.final_hp ?? "")}</td><td>{pct(rec.hp_ratio as number | null)}</td><td>{num(rec.goal_score as number | null, 3)}</td>
              <td>{String(rec.llm_calls ?? "")}</td><td>{String(rec.planned_turns ?? "")}</td><td>{String(rec.parse_errors ?? "")}</td><td>{String(rec.elapsed_s ?? "")}</td><td>{String(rec.max_floor_id ?? "")}</td>
              <td>{rec.run_log ? <a className="link" href={`/play/?log=${encodeURIComponent(String(rec.run_log))}`}>replay</a> : ""}</td>
            </tr>);
          })}</tbody></table></div>
      )}
      {last && <div className="text-xs">aggregate: <b>{String(last.aggregate.successes)}/{String(last.aggregate.n)}</b> success {ci(last.aggregate.success_ci95 as [number, number])} · HP/opt {num(last.aggregate.hp_ratio_mean as number | null)}</div>}
      {events.some((e) => e.type === "done") && <div className="text-emerald-300 text-xs" data-testid="reliability-done">done → {String((events.find((e) => e.type === "done") as { file?: string })?.file)}</div>}
    </Widget>
  );
}

function ResultsTable() {
  const [rows, setRows] = useState<ReliabilityResult[]>([]);
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<"updated" | "label" | "success">("updated");
  const [scope, setScope] = useState<"thesis" | "other" | "all">("thesis");
  const load = useCallback(() => getJson<ReliabilityResult[]>("/api/reliability/results").then(setRows).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
  const shown = rows.filter((r) => scope === "all" || (scope === "thesis") === !!r.thesis)
    .filter((r) => !filter || r.label.includes(filter) || (r.config.model ?? "").includes(filter))
    .sort((a, b) => sort === "label" ? a.label.localeCompare(b.label) : sort === "success" ? (b.aggregate.success_rate ?? -1) - (a.aggregate.success_rate ?? -1) : (b.updated ?? "").localeCompare(a.updated ?? ""));
  return (
    <Widget title="Stored results" testId="results-table" className="min-h-0"
            badge={<span className="tag">{shown.length}/{rows.length}</span>}
            actions={<>
              <select className="input" value={scope} onChange={(e) => setScope(e.target.value as typeof scope)} aria-label="scope" data-testid="results-scope"
                      title="thesis = result files reported in the thesis (analysis/thesis_index.py)">
                <option value="thesis">in the thesis</option><option value="other">not in the thesis</option><option value="all">all results</option>
              </select>
              <input className="input w-56" placeholder="filter label / model" value={filter} onChange={(e) => setFilter(e.target.value)} />
              <select className="input" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} aria-label="sort"><option value="updated">newest</option><option value="label">label</option><option value="success">success rate</option></select>
              <a className="btn btn-sm btn-ghost" href={`${API_BASE}/api/reliability/results?runs=1`} target="_blank" rel="noreferrer">json</a>
            </>}
            footer={<>results/reliability/*.json — success rate with Wilson 95% interval first, HP/optimum among successes second. Plan = actions committed per call
              (1 = reactive). Labels starting with rerun_ are re-runs started from the catalog.</>}
            bodyClass="text-xs max-h-[calc(100vh-11rem)] overflow-auto" flush>
      <div className="scroll-x"><table className="tbl min-w-max"><thead><tr><th>label</th><th>floor</th><th>model</th><th>plan</th><th>LA</th><th>ovr</th><th>N</th><th>success [Wilson 95%]</th><th>HP/opt</th><th>died</th><th>goal</th><th>HP</th><th>s/call</th><th>parse</th><th>floors</th><th>updated</th></tr></thead>
        <tbody>
          {shown.map((r) => {
            const a = r.aggregate, c = r.config;
            const env = (c as { env?: Record<string, string> }).env ?? {};
            const plan = env.MOTA_PLAN_NO_REPLAN === "1" ? "max, once" : env.MOTA_PLAN_STEPS ? (Number(env.MOTA_PLAN_STEPS) >= 60 ? "max" : env.MOTA_PLAN_STEPS) : c.mode === "reactive" ? "1" : c.mode;
            return (
              <tr key={r.label} className="clickable" data-testid="result-row">
                <td className="mono">{r.label}</td>
                <td>{c.floor ?? `${c.start}→${c.end}`}{c.checkpoint != null ? ` cp${c.checkpoint}` : ""}</td>
                <td title={c.model}>{(c.model ?? "").replace(/-a\d+b$/i, "")}</td><td>{plan}</td><td>{c.lookahead ?? 3}</td><td>{c.overrides_disabled ? "off" : "on"}</td>
                <td>{a.n}</td>
                <td><b className={a.success_rate ? "text-emerald-300" : "muted"}>{a.successes}/{a.n}</b> {a.success_rate != null ? `= ${a.success_rate.toFixed(2)}` : ""} <span className="muted">{ci(a.success_ci95)}</span></td>
                <td>{num(a.hp_ratio_mean)}</td><td>{a.died ?? ""}</td><td>{num(a.goal_score_mean, 3)}</td>
                <td>{num(a.final_hp_mean, 0)}</td><td>{num(a.seconds_per_call, 1)}</td><td>{num(a.parse_error_rate, 3)}</td>
                <td>{a.floors_reached_mean != null ? `${a.floors_reached_mean} (max ${a.floors_reached_max})` : ""}</td>
                <td className="muted">{r.updated}</td>
              </tr>
            );
          })}
        </tbody>
      </table></div>
    </Widget>
  );
}
