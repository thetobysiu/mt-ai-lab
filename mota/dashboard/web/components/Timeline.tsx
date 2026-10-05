"use client";
// Turn cards with expandable CoT / prompt text; live thinking cards stream chunks.
import { useEffect, useRef, useState } from "react";
import type { TurnCard } from "@/lib/run";

function Pre({ text, max = 4000 }: { text: string; max?: number }) {
  const [all, setAll] = useState(false);
  const shown = all || text.length <= max ? text : text.slice(-max);
  return (
    <div>
      {text.length > max && !all && (
        <button className="btn btn-sm mb-1" onClick={() => setAll(true)}>show all ({(text.length / 1000).toFixed(1)}K chars)</button>
      )}
      <pre className="pre max-h-[50vh]">{shown}</pre>
    </div>
  );
}

function Detail({ label, children, defaultOpen = false }: { label: string; children: React.ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className="mt-1">
      <summary className="text-[11px] muted hover:text-[var(--text)] transition-colors">{label}</summary>
      <div className="mt-1">{children}</div>
    </details>
  );
}

export function TurnCardView({ card, active, onSelect, showCot }: { card: TurnCard; active?: boolean; onSelect?: () => void; showCot?: boolean }) {
  const ev = card.event;
  const hero = ev.hero;
  const border =
    card.kind === "turn" ? (ev.forced ? "border-l-slate-500" : ev.fallback ? "border-l-amber-500" : "border-l-[var(--accent)]")
    : card.kind === "thinking" ? "border-l-violet-400" : card.kind === "floor_change" ? "border-l-sky-400"
    : card.kind === "parse_error" || card.kind === "error" ? "border-l-red-500" : card.kind === "stuck" || card.kind === "stopped" ? "border-l-orange-500"
    : card.kind === "plan" ? "border-l-emerald-500" : card.kind === "info" && (ev.type === "paused" || ev.type === "resumed") ? "border-l-amber-400" : "border-l-slate-600";
  const d = ev.action_detail;
  return (
    <div className={`card ${border} px-2 py-1.5 text-xs ${active ? "active" : ""}`}
         data-testid={`card-${card.kind}`} data-turn={card.turn} data-snap={card.snapIdx ?? undefined}>
      <div className={`flex items-baseline gap-2 ${onSelect ? "cursor-pointer" : ""}`} onClick={onSelect}>
        <span className="mono muted w-8 shrink-0">{card.kind === "start" ? "▶" : card.kind === "floor_change" ? "↑" : card.turn ?? ""}</span>
        <span className="flex-1 truncate">
          {card.kind === "start" && <>Start {ev.floor_id} — {ev.initial_enemies} enemies{ev.task_model ? <span className="muted"> · {ev.task_model}</span> : null}</>}
          {card.kind === "turn" && <>
            {ev.action}
            {ev.forced && (ev.forced_reason?.startsWith("resumed from")
              ? <span className="tag ml-1" title={`${ev.forced_reason}: the original run's own decision, replayed`}>replayed</span>
              : <span className="tag ml-1" title={ev.forced_reason}>forced</span>)}
            {ev.repeat && <span className="tag ml-1" title="repeated purchase (QUANTITY of the previous decision)">repeat</span>}
            {ev.fallback && <span className="tag tag-warn ml-1">fallback</span>}
            {ev.corrected_from != null && <span className="tag tag-warn ml-1" data-testid="override-tag"
                  title={`LLM chose #${ev.corrected_from} "${ev.corrected_from_label ?? ""}" — engine executed this instead (${ev.corrected_reason ?? "override"})`}>
              override: {ev.corrected_reason ?? "?"}</span>}
            {d?.is_dead_end && <span className="tag tag-bad ml-1">dead end</span>}
            {d?.damage != null && <span className="muted ml-1">−{d.damage} HP{d.hp_after != null ? ` → ${d.hp_after}` : ""}</span>}
          </>}
          {card.kind === "thinking" && <span className="text-purple-300">{card.streaming ? "thinking…" : "LLM responded"}</span>}
          {card.kind === "floor_change" && <span className="text-sky-300 font-semibold">Floor → {ev.floor_id}{ev.floor_idx != null ? ` [${ev.floor_idx + 1}]` : ""}</span>}
          {card.kind === "parse_error" && <span className="text-red-300">parse error: {ev.reason}{ev.repaired_id != null ? ` → repaired #${ev.repaired_id}` : ""}</span>}
          {card.kind === "stuck" && <span className="text-orange-300">stuck: {ev.reason}</span>}
          {card.kind === "stopped" && <span className="text-orange-300">{ev.reason ?? "stopped"}</span>}
          {card.kind === "loop_guard" && <span className="text-orange-300">loop guard: {ev.reason}</span>}
          {card.kind === "plan" && <span className="text-emerald-300">plan: {(ev.coords ?? []).length} coordinates</span>}
          {card.kind === "error" && <span className="text-red-300">error: {ev.message}</span>}
          {card.kind === "info" && <span className={ev.type === "paused" || ev.type === "resumed" ? "text-amber-300" : "muted"}>{ev.reason ?? ev.type}</span>}
        </span>
        {hero && <span className="mono muted shrink-0">HP {hero.hp} · {hero.atk}/{hero.def}</span>}
        {ev.elapsed_ms != null && <span className="muted shrink-0">{(ev.elapsed_ms / 1000).toFixed(1)}s</span>}
      </div>
      {card.planNote && <div className="text-[11px] text-emerald-300 mt-0.5" data-testid="plan-note" title="Plan memory: the to-do line the model wrote here; it is shown to the model at its next decision">plan: {card.planNote}</div>}
      {(card.kind === "turn" || card.kind === "thinking" || card.kind === "plan" || card.kind === "parse_error") && (
        <div>
          {card.thinking && <Detail label={`reasoning (${(card.thinking.length / 1000).toFixed(1)}K chars)`} defaultOpen={!!showCot || card.streaming}><Pre text={card.thinking} /></Detail>}
          {card.response && <Detail label="LLM answer" defaultOpen={card.kind === "plan"}><Pre text={card.response} max={2000} /></Detail>}
          {typeof ev.response === "string" && card.kind === "parse_error" && <Detail label="raw response"><Pre text={ev.response} max={2000} /></Detail>}
          {ev.state_text && <Detail label="state text" defaultOpen={card.kind === "thinking" && card.streaming}><Pre text={ev.state_text} /></Detail>}
          {ev.actions_text && <Detail label={card.kind === "thinking" && card.streaming ? "available actions (waiting for the LLM)" : "actions text (prompt)"}
                                      defaultOpen={card.kind === "thinking" && card.streaming}><Pre text={ev.actions_text} /></Detail>}
          {typeof ev.user_message === "string" && card.kind === "thinking" && <Detail label="full user message"><Pre text={ev.user_message} /></Detail>}
        </div>
      )}
      {card.kind === "start" && ev.runtime_system_prompt && <Detail label="system prompt (runtime)"><Pre text={ev.runtime_system_prompt} /></Detail>}
    </div>
  );
}

export function Timeline({ cards, activeSnap, onSelectSnap, follow = true, showCot }: {
  cards: TurnCard[]; activeSnap?: number | null; onSelectSnap?: (idx: number) => void; follow?: boolean; showCot?: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!follow || !endRef.current) return;
    // Scroll only the nearest scroll container (data-scroll) — never the page itself.
    const sc = endRef.current.closest<HTMLElement>("[data-scroll]") ?? endRef.current.parentElement;
    if (sc) sc.scrollTop = sc.scrollHeight;
  }, [cards.length, follow]);
  useEffect(() => {
    // Replay / scrubbing: keep the highlighted step in view (inside the list's own scroll container).
    if (follow || activeSnap == null || !listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(`[data-snap="${activeSnap}"]`);
    const sc = listRef.current.closest<HTMLElement>("[data-scroll]") ?? listRef.current;
    if (el && sc) sc.scrollTop = el.offsetTop - sc.offsetTop - sc.clientHeight / 3;
  }, [activeSnap, follow]);
  return (
    <div ref={listRef} className="space-y-1 overflow-auto" data-testid="timeline">
      {cards.map((c) => (
        <TurnCardView key={c.key} card={c} active={c.snapIdx != null && c.snapIdx === activeSnap}
                      onSelect={c.snapIdx != null && onSelectSnap ? () => onSelectSnap(c.snapIdx!) : undefined} showCot={showCot} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
