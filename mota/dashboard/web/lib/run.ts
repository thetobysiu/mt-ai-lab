// Fold a stream of evaluator events into a replayable run state (maps per floor, per-turn snapshots, CoT, result).
import type { Hero, MapData, RunEvent } from "./types";

export type Snapshot = {
  idx: number; turn: number; floorId: string | null; hero: Hero | null; removed: Set<string>;
  action: string; target: { x: number; y: number } | null; path: number[][] | null;
};

export type TurnCard = {
  key: string; kind: "start" | "turn" | "thinking" | "parse_error" | "stuck" | "stopped" | "floor_change" | "plan" | "error" | "loop_guard" | "info";
  turn?: number; snapIdx?: number; event: RunEvent; thinking?: string; response?: string; streaming?: boolean;
  planNote?: string;  // the to-do line the model wrote at this decision (plan memory), shown at its next decision
};

export type RunState = {
  maps: Record<string, MapData>;         // floor_id -> rich map (from start/floor_change)
  currentFloor: string | null;
  snapshots: Snapshot[];
  cards: TurnCard[];
  hero: Hero | null;
  initialHp: number;
  result: RunEvent | null;
  status: string;
  turnCount: number;
  llmTurns: number;
  forcedTurns: number;
  overrides: number;         // turns where the engine executed a different action than the LLM chose
  parseErrors: number;
  logSaved: string | null;
  done: boolean;
  error: string | null;
  meta: { mode?: string; taskModel?: string; taskMode?: string; floorId?: string; initialEnemies?: number; systemPrompt?: string | null };
  floorsVisited: string[];
  isTower: boolean;          // multi-floor scenario (shops, gold/EXP economy, stairs)
  floorRange: string[];      // planned floors for a tower run
};

export function emptyRun(): RunState {
  return {
    maps: {}, currentFloor: null, snapshots: [], cards: [], hero: null, initialHp: 1000, result: null, status: "idle",
    turnCount: 0, llmTurns: 0, forcedTurns: 0, overrides: 0, parseErrors: 0, logSaved: null, done: false, error: null, meta: {}, floorsVisited: [],
    isTower: false, floorRange: [],
  };
}

function removedSet(ev: RunEvent, prev: Set<string>): Set<string> {
  // Producers differ: the evaluator sends the cumulative set, the BFS replays send only this turn's
  // tile. Union keeps both correct (tiles are never restored within a floor).
  if (!Array.isArray(ev.removed)) return prev;
  const next = new Set(prev);
  for (const r of ev.removed) next.add(`${r[0]},${r[1]}`);
  return next;
}

export function applyEvent(s: RunState, ev: RunEvent): RunState {
  const n: RunState = { ...s, cards: s.cards.slice(), snapshots: s.snapshots.slice() };
  const key = `${ev.type}-${ev.turn ?? "x"}-${n.cards.length}`;
  switch (ev.type) {
    case "run_snapshot":
    case "run_log_opened":
    case "jobs_snapshot":
    case "job_update":
    case "ping":
      return s;
    case "start": {
      const fid = ev.floor_id ?? ev.map?.floor_id ?? "floor";
      if (ev.map) n.maps = { ...n.maps, [fid]: ev.map };
      n.currentFloor = fid;
      const hero = ev.hero ?? ev.map?.hero ?? null;
      n.hero = hero;
      n.initialHp = hero?.hp ?? 1000;
      n.snapshots = [{ idx: 0, turn: 0, floorId: fid, hero, removed: new Set(), action: "Start", target: null, path: null }];
      n.meta = { mode: ev.mode, taskModel: ev.task_model, taskMode: ev.task_mode, floorId: fid, initialEnemies: ev.initial_enemies,
                 systemPrompt: ev.runtime_system_prompt ?? null };
      n.status = `Playing ${fid} (${ev.mode ?? ""})${ev.task_model ? ` — ${ev.task_model}` : ""}`;
      n.floorsVisited = [fid];
      n.floorRange = Array.isArray(ev.floor_range) ? (ev.floor_range as string[]) : [];
      n.isTower = !!ev.multi_floor || n.floorRange.length > 1;
      n.cards.push({ key, kind: "start", event: ev });
      return n;
    }
    case "thinking":
      n.status = `Turn ${ev.turn}: calling LLM…`;
      n.cards.push({ key, kind: "thinking", turn: ev.turn, event: ev, thinking: "", streaming: true });
      return n;
    case "thinking_chunk": {
      const i = findLast(n.cards, (c) => c.kind === "thinking" && c.turn === ev.turn);
      if (i >= 0) n.cards[i] = { ...n.cards[i], thinking: (n.cards[i].thinking ?? "") + (ev.chunk ?? "") };
      return n;
    }
    case "thinking_result": {
      const i = findLast(n.cards, (c) => c.kind === "thinking" && c.turn === ev.turn);
      const patch = { thinking: ev.thinking ?? n.cards[i]?.thinking ?? "", response: ev.response_preview, streaming: false };
      if (i >= 0) n.cards[i] = { ...n.cards[i], ...patch };
      else n.cards.push({ key, kind: "thinking", turn: ev.turn, event: ev, ...patch });
      n.status = `Turn ${ev.turn}: LLM responded — applying…`;
      return n;
    }
    case "plan_note": {
      // Not a step: attach the plan written at this decision to its thinking (later: turn) card.
      const i = findLast(n.cards, (c) => (c.kind === "thinking" || c.kind === "turn") && c.turn === ev.turn);
      if (i >= 0 && typeof ev.note === "string") n.cards[i] = { ...n.cards[i], planNote: ev.note };
      return n;
    }
    case "plan":
      n.cards.push({ key, kind: "plan", turn: 0, event: ev, response: ev.response });
      return n;
    case "turn": {
      const prev = n.snapshots[n.snapshots.length - 1];
      const fid = ev.floor_id ?? n.currentFloor;
      const hero = ev.hero ?? prev?.hero ?? null;
      const d = ev.action_detail;
      const lastHere = findLast(n.snapshots, (x) => x.floorId === fid);  // never union another floor's cleared tiles
      const snap: Snapshot = {
        idx: n.snapshots.length, turn: ev.turn ?? n.snapshots.length, floorId: fid, hero,
        removed: removedSet(ev, lastHere >= 0 ? n.snapshots[lastHere].removed : new Set()), action: ev.action ?? "",
        target: d ? { x: d.x, y: d.y } : null, path: ev.action_path ?? null,
      };
      n.snapshots.push(snap);
      n.hero = hero;
      n.turnCount += 1;
      if (ev.forced) n.forcedTurns += 1; else n.llmTurns += 1;
      if (ev.corrected_from != null) n.overrides += 1;
      n.status = `Turn ${ev.turn}: ${ev.action}`;
      // a turn replaces its thinking card (the CoT is kept on the turn card)
      const ti = findLast(n.cards, (c) => c.kind === "thinking" && c.turn === ev.turn);
      const thinking = ti >= 0 ? n.cards[ti].thinking : (ev.llm_thinking as string | undefined);
      const response = ti >= 0 ? n.cards[ti].response : undefined;
      const planNote = ti >= 0 ? n.cards[ti].planNote : undefined;
      const card: TurnCard = { key, kind: "turn", turn: ev.turn, snapIdx: snap.idx, event: ev, thinking, response: ev.llm_response ?? response, planNote };
      if (ti >= 0) n.cards.splice(ti, 1, card); else n.cards.push(card);
      return n;
    }
    case "floor_change": {
      const fid = ev.floor_id ?? "floor";
      // Keep the first map of a floor: a re-entry map already has the cleared tiles baked in, which would
      // show the latest state at every replay position; the per-snapshot `removed` set carries the history.
      if (ev.map && !n.maps[fid]) n.maps = { ...n.maps, [fid]: ev.map };
      n.currentFloor = fid;
      n.isTower = true;
      if (!n.floorsVisited.includes(fid)) n.floorsVisited = [...n.floorsVisited, fid];
      const prev = n.snapshots[n.snapshots.length - 1];
      const hero = ev.hero ?? prev?.hero ?? null;
      n.hero = hero;
      const lastHere = findLast(n.snapshots, (x) => x.floorId === fid);
      const snap: Snapshot = { idx: n.snapshots.length, turn: ev.turn ?? prev?.turn ?? 0, floorId: fid, hero,
                               removed: lastHere >= 0 ? n.snapshots[lastHere].removed : new Set(),
                               action: `→ ${fid}`, target: null, path: null };
      n.snapshots.push(snap);
      n.cards.push({ key, kind: "floor_change", turn: ev.turn, snapIdx: snap.idx, event: ev });
      return n;
    }
    case "parse_error":
      n.parseErrors += 1;
      n.cards.push({ key, kind: "parse_error", turn: ev.turn, event: ev });
      return n;
    case "loop_guard":
      n.cards.push({ key, kind: "loop_guard", turn: ev.turn, event: ev });
      return n;
    case "override":
      // The following turn event carries corrected_from; the card there shows the tag. Nothing to add.
      return n;
    case "stuck":
      n.status = `Stuck: ${ev.reason}`;
      n.cards.push({ key, kind: "stuck", turn: ev.turn, event: ev });
      return n;
    case "stopped":
      n.status = ev.reason ?? "Stopped";
      n.cards.push({ key, kind: "stopped", event: ev });
      return n;
    case "result":
    case "bfs_result":
    case "manual_result":
      n.result = ev;
      n.status = ev.success != null
        ? `Done — ${ev.success ? "SUCCESS" : "FAIL"}${ev.hp_ratio != null ? ` HP/opt=${(ev.hp_ratio * 100).toFixed(0)}%` : ""} | legacy ${num4(ev.total)}`
        : `Done — legacy ${num4(ev.total)}`;
      return n;
    case "log_saved":
      n.logSaved = ev.path ?? null;
      return n;
    case "error":
      n.error = ev.message ?? "error";
      n.status = `Error: ${ev.message}`;
      n.cards.push({ key, kind: "error", event: ev });
      return n;
    case "done":
      n.done = true;
      return n;
    case "status":
      n.status = ev.message ?? n.status;
      return n;
    case "paused":
      n.status = `Paused after turn ${ev.turn ?? "?"}`;
      n.cards.push({ key, kind: "info", turn: ev.turn, event: ev });
      return n;
    case "resumed":
      n.status = `Resumed at turn ${ev.turn ?? "?"}`;
      n.cards.push({ key, kind: "info", turn: ev.turn, event: ev });
      return n;
    default:
      n.cards.push({ key, kind: "info", turn: ev.turn, event: ev });
      return n;
  }
}

export function applyEvents(s: RunState, evs: RunEvent[]): RunState {
  return evs.reduce(applyEvent, s);
}

function findLast<T>(arr: T[], pred: (x: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i--) if (pred(arr[i])) return i;
  return -1;
}

function num4(x: unknown): string {
  return typeof x === "number" ? x.toFixed(4) : "–";
}
