"use client";
// Every experiment knob of run_reliability.py / RunCondition, as one form. Emits a request body.
import { useEffect, useState } from "react";
import { getJson } from "@/lib/api";
import type { Checkpoint, ModelPreset } from "@/lib/types";

export type Scenario =
  | { kind: "floor"; floor: string }
  | { kind: "tower"; start: string; end: string; checkpoint: number | null };

/** Planning granularity (thesis §7.3.6): how many actions one model call commits to. */
export type Planning = "reactive" | "plan2" | "plan3" | "plan5" | "floor" | "oneshot";
export const PLANNING_OPTIONS: { id: Planning; label: string; help: string }[] = [
  { id: "reactive", label: "reactive — one call per action", help: "The model chooses one action; the engine re-annotates the new state; repeat." },
  { id: "plan2", label: "commit 2 — choose + 1 committed step", help: "Each call chooses an action and commits to the next one (NEXT: …), executed without a new call while still legal." },
  { id: "plan3", label: "commit 3 — choose + 2 committed steps", help: "As commit 2, with two committed steps." },
  { id: "plan5", label: "commit 5 — choose + 4 committed steps", help: "As commit 2, with four committed steps." },
  { id: "floor", label: "as many steps as possible — re-planned when it breaks", help: "Each call chooses an action and commits to as many further actions as the model can (at most 59); a new call only when a step is no longer legal." },
  { id: "oneshot", label: "as many steps as possible — single call", help: "One call at the start (per floor in the tower), never re-planned; turns the plan does not cover are played by the heuristic and counted." },
];
export function planningBody(p: Planning): { plan_steps: number; one_shot: boolean } {
  const steps = { reactive: 1, plan2: 2, plan3: 3, plan5: 5, floor: 60, oneshot: 60 }[p];
  return { plan_steps: steps, one_shot: p === "oneshot" };
}

export type Condition = {
  scenario: Scenario;
  preset: string;
  planning: Planning;
  finalStack: boolean;
  lookahead: number;
  temperature: number;
  disableOverrides: boolean;
  thinkingMaxTokens: number;
  structuredOutput: boolean;
  maxTurns: number;
  repeats: number;
  label: string;
  append: boolean;
  enableLogging: boolean;
};

export const DEFAULT_CONDITION: Condition = {
  scenario: { kind: "floor", floor: "simple" }, preset: "qwen3.5-397b", planning: "reactive", finalStack: true, lookahead: 3, temperature: 0,
  disableOverrides: false, thinkingMaxTokens: 16384, structuredOutput: true, maxTurns: 1500, repeats: 3, label: "", append: true, enableLogging: true,
};

export type SingleFloor = { id: string; optimum_hp?: number | null; heuristic?: string; note?: string; critical?: number | null;
  forced?: number | null; solver_states?: number | null; random_win?: number | null; winning_sets?: number | null };
export type SingleFloorGroup = { group: string; title: string; floors: SingleFloor[] };

/** Tower floors that can also be played as single floors (fixed start heroes). */
const TOWER_SINGLE = [
  { id: "mota-floor:MT3", label: "MT3 (tower floor 3, with shop)" },
  { id: "special-floor:MT4", label: "MT4 (tower floor 4)" },
];

/** Dashboard scenario id → harness floor id (simple|complex|MT3|MT4) for reliability/matrix bodies. */
export function harnessFloor(id: string): string {
  if (id === "mota-floor:MT3") return "MT3";
  if (id === "special-floor:MT4") return "MT4";
  return id;
}

export function scenarioFromFloorParam(p: string | null): Scenario | null {
  if (!p) return null;
  if (p === "mota24") return { kind: "tower", start: "MT0", end: "MT4", checkpoint: null };
  if (/^MT\d+/.test(p)) return { kind: "floor", floor: p === "MT3" ? "mota-floor:MT3" : p === "MT4" ? "special-floor:MT4" : p };
  return { kind: "floor", floor: p };
}

export function useCatalog() {
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [floorIds, setFloorIds] = useState<string[]>([]);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [singleFloors, setSingleFloors] = useState<SingleFloorGroup[]>([]);
  useEffect(() => {
    getJson<{ task_presets: ModelPreset[] }>("/api/models").then((m) => setPresets(m.task_presets.filter((p) => !p.deprecated))).catch(() => {});
    getJson<{ floor_ids: string[] }>("/api/floor-sequence").then((f) => setFloorIds(f.floor_ids)).catch(() => {});
    getJson<Checkpoint[]>("/api/checkpoints").then(setCheckpoints).catch(() => {});
    getJson<{ groups: SingleFloorGroup[] }>("/api/single-floors").then((r) => setSingleFloors(r.groups)).catch(() => {});
  }, []);
  return { presets, floorIds, checkpoints, singleFloors };
}

/** Body fields shared by /api/evaluate/*, /api/reliability/stream. */
export function conditionBody(c: Condition, prompt: string | null, extra: Record<string, unknown> = {}): Record<string, unknown> {
  const body: Record<string, unknown> = {
    prompt, task_preset: c.preset, lookahead_depth: c.lookahead, temperature: c.temperature,
    disable_overrides: c.disableOverrides, thinking_max_tokens: c.thinkingMaxTokens, structured_output: c.structuredOutput,
    enable_logging: c.enableLogging, ...planningBody(c.planning), final_stack: c.finalStack,
    mode: prompt == null ? "heuristic" : "reactive",
    repeats: c.repeats, label: c.label || undefined, append: c.append,
  };
  if (c.scenario.kind === "floor") {
    body.floor = c.scenario.floor;
  } else {
    body.tower = true; body.start_floor = c.scenario.start; body.end_floor = c.scenario.end; body.max_turns = c.maxTurns;
    if (c.scenario.checkpoint != null) body.checkpoint = c.scenario.checkpoint;
  }
  return { ...body, ...extra };
}

export function ConditionForm({ value, onChange, showRepeats = true, compact = false }: {
  value: Condition; onChange: (c: Condition) => void; showRepeats?: boolean; compact?: boolean;
}) {
  const { presets, floorIds, checkpoints, singleFloors } = useCatalog();
  const c = value;
  const set = (patch: Partial<Condition>) => onChange({ ...c, ...patch });
  const sc = c.scenario;
  const known = new Set([...singleFloors.flatMap((g) => g.floors.map((f) => f.id)), ...TOWER_SINGLE.map((f) => f.id)]);
  const planHelp = PLANNING_OPTIONS.find((p) => p.id === c.planning)?.help;

  return (
    <div className={`grid gap-2 text-xs ${compact ? "grid-cols-2" : "grid-cols-2 md:grid-cols-4"}`} data-testid="condition-form">
      <label className="col-span-2 flex flex-col gap-0.5">
        <span className="muted">Scenario</span>
        <select className="input" data-testid="scenario-select"
                value={sc.kind === "floor" ? sc.floor : "mota24"}
                onChange={(e) => set({ scenario: e.target.value === "mota24" ? { kind: "tower", start: "MT0", end: "MT4", checkpoint: null } : { kind: "floor", floor: e.target.value } })}>
          {singleFloors.map((g) => (
            <optgroup key={g.group} label={`Single floor · ${g.title}`}>
              {g.floors.map((f) => <option key={f.id} value={f.id}>{f.id}{f.optimum_hp != null ? ` (optimum HP ${f.optimum_hp})` : ""}</option>)}
            </optgroup>
          ))}
          {singleFloors.length === 0 && <option value="simple">simple</option>}
          <optgroup label="Single floor · tower floors">{TOWER_SINGLE.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</optgroup>
          {sc.kind === "floor" && singleFloors.length > 0 && !known.has(sc.floor) && <option value={sc.floor}>{sc.floor} (single tower floor)</option>}
          <optgroup label="Tower (several floors)"><option value="mota24">Tower run (choose floors below)</option></optgroup>
        </select>
      </label>
      {sc.kind === "tower" && (
        <>
          <label className="flex flex-col gap-0.5"><span className="muted">From</span>
            <select className="input" data-testid="start-floor" value={sc.start} disabled={sc.checkpoint != null}
                    onChange={(e) => set({ scenario: { ...sc, start: e.target.value } })}>
              {floorIds.map((f) => <option key={f}>{f}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-0.5"><span className="muted">To</span>
            <select className="input" data-testid="end-floor" value={sc.end} onChange={(e) => set({ scenario: { ...sc, end: e.target.value } })}>
              {floorIds.map((f) => <option key={f}>{f}</option>)}
            </select>
          </label>
          <label className="col-span-2 flex flex-col gap-0.5"><span className="muted">Walkthrough checkpoint (start state)</span>
            <select className="input" data-testid="checkpoint-select" value={sc.checkpoint ?? ""}
                    onChange={(e) => {
                      const v = e.target.value === "" ? null : Number(e.target.value);
                      const cp = checkpoints.find((x) => x.id === v);
                      set({ scenario: { ...sc, checkpoint: v, start: cp ? cp.floor : sc.start, end: cp ? cp.target : sc.end } });
                    }}>
              <option value="">none (fresh hero at From)</option>
              {checkpoints.map((cp) => <option key={cp.id} value={cp.id}>{cp.id}: {cp.section} — {cp.floor}→{cp.target} (HP {cp.hero.hp} ATK {cp.hero.atk} DEF {cp.hero.def})</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-0.5"><span className="muted">Max turns</span>
            <input className="input" type="number" min={10} max={5000} step={10} value={c.maxTurns} data-testid="max-turns" onChange={(e) => set({ maxTurns: Number(e.target.value) })} />
          </label>
        </>
      )}
      <label className="col-span-2 flex flex-col gap-0.5"><span className="muted">Model preset</span>
        <select className="input" data-testid="preset-select" value={c.preset} onChange={(e) => set({ preset: e.target.value })}>
          {presets.length === 0 && <option value={c.preset}>{c.preset}</option>}
          {presets.map((p) => <option key={p.id} value={p.id}>{p.label} — {p.model}</option>)}
        </select>
      </label>
      <label className="col-span-2 flex flex-col gap-0.5" title={planHelp}><span className="muted">Planning (actions per model call)</span>
        <select className="input" data-testid="planning-select" value={c.planning} onChange={(e) => set({ planning: e.target.value as Planning })}>
          {PLANNING_OPTIONS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-0.5" title="Depth of the engine's unlock tree printed under each action (thesis default 3; the tower uses 2)"><span className="muted">Lookahead depth</span>
        <input className="input" type="number" min={0} max={8} value={c.lookahead} data-testid="lookahead" onChange={(e) => set({ lookahead: Number(e.target.value) })} />
      </label>
      <label className="flex flex-col gap-0.5"><span className="muted">Temperature</span>
        <input className="input" type="number" min={0} max={2} step={0.1} value={c.temperature} data-testid="temperature" onChange={(e) => set({ temperature: Number(e.target.value) })} />
      </label>
      <label className="flex flex-col gap-0.5"><span className="muted">Think cap (tokens)</span>
        <input className="input" type="number" min={512} max={65536} step={512} value={c.thinkingMaxTokens} data-testid="think-cap" onChange={(e) => set({ thinkingMaxTokens: Number(e.target.value) })} />
      </label>
      {showRepeats && (
        <label className="flex flex-col gap-0.5"><span className="muted">Repeats ×N</span>
          <input className="input" type="number" min={1} max={50} value={c.repeats} data-testid="repeats" onChange={(e) => set({ repeats: Number(e.target.value) })} />
        </label>
      )}
      <div className="col-span-2 md:col-span-4 flex flex-wrap gap-4 items-center pt-1">
        <label className="flex items-center gap-1" title="The engine configuration of every thesis result from round 5 on: no conversation history, two-sided ORDER lines, key lines on fights (§8.20.11a)">
          <input type="checkbox" checked={c.finalStack} data-testid="final-stack" onChange={(e) => set({ finalStack: e.target.checked })} /> final engine stack (thesis)
        </label>
        <label className="flex items-center gap-1" title="MOTA_DISABLE_OVERRIDES=1: no mechanical safety check, no auto-fight at 0 HP. Used with the compiled complex-floor prompts.">
          <input type="checkbox" checked={c.disableOverrides} data-testid="overrides-off" onChange={(e) => set({ disableOverrides: e.target.checked })} /> overrides off
        </label>
        <label className="flex items-center gap-1" title="constrained-decoding repair on unparseable answers">
          <input type="checkbox" checked={c.structuredOutput} data-testid="structured-output" onChange={(e) => set({ structuredOutput: e.target.checked })} /> structured output
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={c.enableLogging} data-testid="enable-logging" onChange={(e) => set({ enableLogging: e.target.checked })} /> save run log
        </label>
        {showRepeats && (
          <>
            <label className="flex items-center gap-1"><span className="muted">label</span>
              <input className="input w-56" placeholder="(derived from condition)" value={c.label} data-testid="label" onChange={(e) => set({ label: e.target.value })} />
            </label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={c.append} onChange={(e) => set({ append: e.target.checked })} /> append</label>
          </>
        )}
      </div>
    </div>
  );
}
