// Event + payload types mirroring the FastAPI/evaluator contracts (see mota/dashboard/api/*).

export type Hero = {
  hp: number; atk: number; def: number; mdef?: number; money?: number; exp?: number;
  keys?: { yellow: number; blue: number; red: number }; x: number; y: number; lv?: number;
};

export type MapCell = (
  | { t: "."; }
  | { t: "#" } | { t: "?" } | { t: "T" }
  | { t: "E"; name: string; hp: number; atk: number; def: number; money?: number; specials?: number[]; dmg?: number; canWin?: boolean;
      fixed?: number; vampire?: number; n?: number }
  | { t: "I"; name: string }
  | { t: "Y" } | { t: "B" } | { t: "R" }
  | { t: "S"; dir?: string }
  | { t: "N"; name?: string }
) & { id?: number };  // id = the game's tile number (absent in logs recorded before 2026-09-29)

export type MapData = { floor_id?: string; width: number; height: number; grid: (MapCell | string)[][]; hero?: Hero };

export type ActionDetail = {
  type: string; x: number; y: number; name: string; is_dead_end?: boolean;
  damage?: number; damage_pct?: number; hp_after?: number; lookahead_value?: number; effective_cost?: number | null; unlocks?: string[];
};

export type RunEvent = {
  type: string; turn?: number; floor_id?: string; floor_idx?: number; hero?: Hero; map?: MapData;
  action?: string; action_id?: number; forced?: boolean; fallback?: boolean; elapsed_ms?: number | null;
  forced_reason?: string; repeat?: boolean; corrected_from?: number | null; corrected_from_label?: string; corrected_reason?: string;
  state_text?: string; actions_text?: string; enemies_remaining?: number; removed?: number[][];
  action_detail?: ActionDetail; action_path?: number[][]; llm_response?: string; llm_thinking?: string;
  chunk?: string; thinking?: string; response_preview?: string; user_message?: string;
  reason?: string; message?: string; response?: string; parsed_id?: number | null; repaired_id?: number | null; valid_ids?: number[];
  // result
  total?: number; success?: boolean | null; alive?: boolean; hp_ratio?: number | null; goal_score?: number | null; goal_reached?: boolean | null;
  completion?: number; hp_score?: number; efficiency?: number; shop_score?: number; violations?: string[]; details?: Record<string, unknown>;
  max_floor_id?: string; floors_reached?: number; total_floors?: number; failure_reason?: string | null; final_floor_id?: string;
  initial_enemies?: number; mode?: string; task_model?: string; task_mode?: string; runtime_system_prompt?: string | null;
  multi_floor?: boolean; floor_range?: string[];
  path?: string; job_id?: string; coords?: number[][]; plan_remaining?: number;
  [k: string]: unknown;
};

export type Job = {
  job_id: string; kind: string; label: string; status: "queued" | "running" | "paused" | "done" | "failed" | "killed" | "stopped";
  pause_requested?: boolean; paused_at?: string | null;
  source: "cli" | "dashboard"; uses_api: boolean; pid: number; argv: string[]; started_at: string; updated_at: string; finished_at: string | null;
  floor?: string | null; start?: string | null; end?: string | null; checkpoint?: number | null; model?: string | null; preset?: string | null; mode?: string | null;
  condition: Record<string, unknown>; run_logs: string[]; current_run_log: string | null;
  progress: { turn?: number; floor_id?: string; hp?: number; atk?: number; def?: number; last_action?: string; repeats_done?: number; repeats_total?: number;
    run_idx?: number; cells_done?: number; cells_total?: number; current?: string; iteration?: number; best_score?: number; [k: string]: unknown };
  result: Record<string, unknown> | null; error: string | null;
};

export type WsEnvelope = { topic: string; job_id?: string | null; event: RunEvent & { jobs?: Job[]; job?: Job; snapshot?: RunSnapshot | null } };
export type RunSnapshot = { run_log: string; floor_id: string; mode: string; task_model?: string; job_id?: string; turns: RunEvent[]; result: RunEvent | null };

export type ModelPreset = { id: string; label: string; model: string; mode?: string; deprecated?: boolean; description?: string };
export type FloorInfo = { id: string; path: string; name?: string; description?: string };
export type Checkpoint = { id: number; section: string; floor: string; target: string; hero: Record<string, number> };

export type ManualAction = {
  action_id: number; type: string; label: string; x: number; y: number; name: string; is_dead_end?: boolean; path_steps?: number; path?: number[][];
  can_win?: boolean; total_damage?: number; damage_percent?: number; hp_after?: number; item_tier?: string; item_score?: number; unlocks_items?: string[];
  [k: string]: unknown;
};
export type ManualPayload = {
  type?: string; floor_id: string; turn: number; hero: Hero; map: MapData; removed: number[][]; state_text: string; actions_text: string;
  actions: ManualAction[]; goal_reached: boolean; failed: boolean; failure_reason?: string | null; done: boolean; floor_progress?: string;
  action?: string; action_id?: number; action_detail?: ActionDetail; action_path?: number[][];
  result?: RunEvent; walkthrough?: unknown; expert_recommendation?: Record<string, unknown>; log_saved?: string;
};

export type ReliabilityResult = {
  label: string; file: string; n: number; updated?: string;
  config: { floor?: string | null; start?: string | null; end?: string | null; model?: string; task_mode?: string; preset?: string; mode?: string;
    lookahead?: number; overrides_disabled?: boolean; prompt_file?: string; checkpoint?: number | null; temperature?: number; source?: string };
  aggregate: { n: number; successes: number; success_rate: number | null; success_ci95: [number, number]; died?: number; hp_ratio_mean?: number | null;
    goal_score_mean?: number | null; score_mean?: number | null; score_sd?: number | null; final_hp_mean?: number | null; seconds_per_call?: number | null;
    parse_error_rate?: number | null; floors_reached_mean?: number | null; floors_reached_max?: number | null };
  runs?: Record<string, unknown>[];
  thesis?: boolean; run_logs?: string[];
};

export type LogSummary = {
  kind: "run" | "gepa"; filename: string; floor_id: string; mode: string; score?: number | null; final_hp?: number | null; timestamp?: string;
  task_model?: string; success?: boolean | null; hp_ratio?: number | null; goal_score?: number | null; turns?: number; multi_floor?: boolean;
  scenario?: "floor" | "tower"; start_floor?: string; end_floor?: string;
  goal?: string | null; goal_reached?: boolean | null; boss_floor?: boolean; boss_killed?: boolean | null; died?: boolean; has_result?: boolean;
  failure_reason?: string | null; max_floor_id?: string | null; floors_reached?: number | null; size_mb?: number; job_id?: string | null;
  turn_count?: number; overrides?: number;
  [k: string]: unknown;
};
