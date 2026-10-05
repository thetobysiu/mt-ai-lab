import type { RunEvent } from "@/lib/types";
import { num, pct } from "@/lib/format";

/** Two-tier outcome first (success · HP/BFS-opt · goal_score); the legacy composite is demoted. */
export function ScoreFooter({ result }: { result: RunEvent | null }) {
  if (!result) return <div className="muted text-xs" data-testid="score-footer">no result yet</div>;
  const r = result;
  const outcome = r.success == null ? (r.goal_reached ? "GOAL" : "–") : r.success ? "SUCCESS" : (r.alive === false || (r.details as { final_hp?: number } | undefined)?.final_hp === 0 ? "DIED" : "FAILED");
  const col = outcome === "SUCCESS" || outcome === "GOAL" ? "var(--ok)" : outcome === "DIED" ? "var(--bad)" : "var(--warn)";
  const d = (r.details ?? {}) as Record<string, number | undefined>;
  const viol = (r.violations ?? []) as string[];
  return (
    <div className="text-xs space-y-1" data-testid="score-footer">
      <div className="flex flex-wrap gap-4 items-baseline">
        <span>Outcome <b style={{ color: col }} data-testid="score-outcome">{outcome}</b></span>
        {r.hp_ratio != null && <span>HP / BFS-opt <b data-testid="score-hp-ratio">{pct(r.hp_ratio)}</b></span>}
        {r.goal_score != null && <span>goal_score <b data-testid="score-goal">{num(r.goal_score, 3)}</b></span>}
        {d.final_hp != null && <span>HP <b>{d.final_hp}</b>{d.target_hp ? <span className="muted"> / opt {d.target_hp}</span> : null}</span>}
        {d.hero_atk != null && <span className="muted">ATK {d.hero_atk} DEF {d.hero_def}</span>}
        {d.steps != null && <span className="muted">{d.steps} steps</span>}
        {d.enemies_killed != null && <span className="muted">{d.enemies_killed}/{d.enemies_total} enemies</span>}
        {r.max_floor_id && <span>max floor <b>{r.max_floor_id}</b>{r.floors_reached != null ? <span className="muted"> ({r.floors_reached}/{r.total_floors})</span> : null}</span>}
        {r.failure_reason && <span className="text-orange-300">{r.failure_reason}</span>}
      </div>
      {r.hp_ratio != null && (
        <div className="h-1.5 rounded bg-[#1f2937] overflow-hidden w-64"><div className="h-full bg-emerald-500" style={{ width: `${Math.min(100, r.hp_ratio * 100)}%` }} /></div>
      )}
      <details>
        <summary className="cursor-pointer muted" title="0.35 completion + 0.25 hp + 0.15 efficiency + 0.15 shop + 0.10 violations, ×0.5 if boss not killed. Inverts outcome order: a lethal boss attempt scores ~0.70, a safe non-kill ~0.37.">
          legacy composite <b data-testid="score-total">{num(r.total, 4)}</b>
        </summary>
        <div className="flex gap-3 muted mt-1">
          <span>completion {num(r.completion)}</span><span>hp {num(r.hp_score)}</span><span>efficiency {num(r.efficiency)}</span>
          <span>shop {num(r.shop_score)}</span><span>violations {viol.length}{viol.length ? `: ${viol.join(", ")}` : ""}</span>
        </div>
      </details>
    </div>
  );
}
