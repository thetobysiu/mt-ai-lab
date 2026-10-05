"use client";
// Map-centric run view: the floor map is the hero element and fills the viewport height;
// hero KPIs + transport on the left, timeline in a collapsible right rail.
// Works for live runs, replays and previews. Keyboard: ←/→ step, Home/End, Space play/pause.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RunState } from "@/lib/run";
import { FloorMap, MapLegend, MapSkinSelect, useMapSkin } from "./FloorMap";
import { Timeline } from "./Timeline";
import { ScoreFooter } from "./ScoreFooter";
import { Widget, Stat } from "./Widget";
import { IconCollapse, IconExpand, IconNext, IconPause, IconPlay, IconPrev, IconSkipEnd, IconSkipStart } from "./Icons";
import type { MapCell } from "@/lib/types";

export function RunView({ run, live, header, extra, compact, mapExtra, onCellClick, highlight, labels }: {
  run: RunState; live?: boolean; header?: React.ReactNode; extra?: React.ReactNode; compact?: boolean;
  mapExtra?: React.ReactNode;                     // toolbar row under the map (e.g. manual actions)
  onCellClick?: (x: number, y: number, cell: MapCell | string) => void;
  highlight?: Set<string>;
  labels?: Record<string, string>;
}) {
  const [pos, setPos] = useState<number | null>(null); // null = follow latest
  const [showCot, setShowCot] = useState(false);
  const [railOpen, setRailOpen] = useState(true);
  const [enemyMetric, setEnemyMetric] = useState<"dmg" | "hp">("dmg");
  const [skin, setSkin] = useMapSkin();
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4); // snapshots per second
  const last = run.snapshots.length - 1;
  const idx = pos == null ? last : Math.min(pos, last);
  const snap = idx >= 0 ? run.snapshots[idx] : null;
  const heroFloor = snap?.floorId ?? run.currentFloor ?? null;
  // Floor being viewed: follows the hero unless the user pins another visited floor.
  const [pinnedFloor, setPinnedFloor] = useState<string | null>(null);
  const viewFloor = pinnedFloor && run.maps[pinnedFloor] ? pinnedFloor : heroFloor;
  const map = viewFloor ? run.maps[viewFloor] : null;
  const onHeroFloor = viewFloor === heroFloor;
  // Another floor's state at this moment = the last snapshot taken on it up to `idx`.
  const floorView = useMemo(() => {
    if (onHeroFloor || !viewFloor) return { removed: snap?.removed, target: snap?.target ?? null, path: snap?.path ?? null };
    for (let i = idx; i >= 0; i--) {
      const s = run.snapshots[i];
      if (s.floorId === viewFloor) return { removed: s.removed, target: null, path: null };
    }
    return { removed: new Set<string>(), target: null, path: null };
  }, [onHeroFloor, viewFloor, idx, run.snapshots, snap]);
  const heroPos = useMemo(() => snap?.hero ?? run.hero, [snap, run.hero]);
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (pinnedFloor && !run.maps[pinnedFloor]) setPinnedFloor(null); }, [pinnedFloor, run.maps]);
  // "single" = one big map (hero's or pinned floor); "all" = every visited floor side by side,
  // each drawn as it was at this step (tower runs go up and back down, so the state of every
  // floor at a given turn matters).
  const [viewMode, setViewMode] = useState<"single" | "all">("single");
  const multiFloor = run.floorsVisited.length > 1;
  // Per-floor state at `idx`: cleared tiles (cumulative) and whether the floor was entered yet.
  const floorStates = useMemo(() => {
    const out: Record<string, { removed: Set<string>; visited: boolean; enemiesLeft: number | null; lastTurn: number | null }> = {};
    for (const f of run.floorsVisited) out[f] = { removed: new Set<string>(), visited: false, enemiesLeft: null, lastTurn: null };
    for (let i = 0; i <= idx; i++) {
      const s = run.snapshots[i];
      if (!s?.floorId || !out[s.floorId]) continue;
      out[s.floorId] = { removed: s.removed ?? new Set<string>(), visited: true, enemiesLeft: null, lastTurn: s.turn ?? i };
    }
    for (const f of run.floorsVisited) {
      const m = run.maps[f];
      if (!m) continue;
      let n = 0;
      m.grid.forEach((row, y) => row.forEach((c, x) => {
        const t = typeof c === "string" ? c : c.t;
        if (t === "E" && !out[f].removed.has(`${x},${y}`)) n++;
      }));
      out[f].enemiesLeft = n;
    }
    return out;
  }, [run.floorsVisited, run.snapshots, run.maps, idx]);

  useEffect(() => { if (live) { setPos(null); setPlaying(false); } }, [live, run.snapshots.length]);
  useEffect(() => {
    if (!playing || last < 0) return;
    const t = setInterval(() => {
      setPos((p) => {
        const n = (p == null ? 0 : p) + 1;
        if (n >= last) { setPlaying(false); return null; }
        return n;
      });
    }, 1000 / speed);
    return () => clearInterval(t);
  }, [playing, speed, last]);

  const step = useCallback((d: number) => {
    setPlaying(false);
    setPinnedFloor(null);
    setPos((p) => Math.max(0, Math.min(last, (p == null ? last : p) + d)));
  }, [last]);
  const seek = useCallback((p: number | null) => { setPlaying(false); setPinnedFloor(null); setPos(p); }, []);

  const onKey = useCallback((e: React.KeyboardEvent) => {
    if ((e.target as HTMLElement).tagName.match(/INPUT|TEXTAREA|SELECT/)) return;
    if (e.key === "ArrowLeft") { step(-1); e.preventDefault(); }
    else if (e.key === "ArrowRight") { step(1); e.preventDefault(); }
    else if (e.key === "Home") { seek(0); e.preventDefault(); }
    else if (e.key === "End") { seek(null); e.preventDefault(); }
    else if (e.key === " ") { setPinnedFloor(null); setPlaying((v) => !v); e.preventDefault(); }
  }, [step, seek]);

  const hp = heroPos?.hp ?? 0;
  const hpPct = Math.max(0, Math.min(100, (hp / (run.initialHp || hp || 1)) * 100));
  const hpTone = hpPct > 50 ? "ok" : hpPct > 20 ? "warn" : "bad";
  const res = run.result;

  const transport = (
    <div className="shrink-0 flex flex-col gap-1" data-testid="transport">
      <div className="flex items-center gap-1">
        <button className="btn btn-sm" onClick={() => seek(0)} disabled={last < 0} title="First turn"><IconSkipStart /></button>
        <button className="btn btn-sm" onClick={() => step(-1)} disabled={last < 0} title="Previous turn"><IconPrev /></button>
        <button className="btn btn-sm btn-primary" onClick={() => { setPinnedFloor(null); setPlaying((v) => !v); }} disabled={last < 1} data-testid="btn-replay"
                title={playing ? "Pause replay" : "Replay the run"}>{playing ? <IconPause /> : <IconPlay />}</button>
        <button className="btn btn-sm" onClick={() => step(1)} disabled={last < 0} title="Next turn"><IconNext /></button>
        <button className="btn btn-sm" onClick={() => seek(null)} disabled={pos == null} data-testid="btn-latest" title="Follow latest"><IconSkipEnd /></button>
        <input type="range" min={0} max={Math.max(0, last)} value={idx < 0 ? 0 : idx} className="flex-1 mx-2"
               onChange={(e) => seek(Number(e.target.value))} data-testid="scrubber" aria-label="Turn scrubber" />
        <span className="mono muted text-[11px] w-16 text-right">{idx < 0 ? "–" : `${idx}/${Math.max(0, last)}`}</span>
        <select className="input" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} title="Replay speed" aria-label="Replay speed">
          {[1, 2, 4, 8, 16].map((s) => <option key={s} value={s}>{s}×</option>)}
        </select>
      </div>
      <div className="text-[11px] muted truncate" data-testid="status-text">
        {snap?.action ? `#${snap.turn} ${snap.action} · ` : ""}{run.status}
      </div>
    </div>
  );

  const mapPanel = (
    <Widget
      title={map ? (multiFloor ? "Map" : `Map · ${viewFloor ?? ""}`) : "Map"}
      badge={<>
        {multiFloor && (
          <span className="inline-flex items-center gap-1" data-testid="floor-switcher">
            <span className="seg" role="group" aria-label="map view" data-testid="view-mode">
              <button className={`btn btn-sm ${viewMode === "single" ? "btn-primary" : ""}`} onClick={() => setViewMode("single")} title="One floor, full size">one floor</button>
              <button className={`btn btn-sm ${viewMode === "all" ? "btn-primary" : ""}`} onClick={() => setViewMode("all")} title="Every visited floor as it was at this turn" data-testid="btn-all-floors">all floors</button>
            </span>
            {viewMode === "single" && <>
              <select className="input" value={viewFloor ?? ""} aria-label="floor to show" title="Show another visited floor as it was at this turn"
                      onChange={(e) => setPinnedFloor(e.target.value === heroFloor ? null : e.target.value)}>
                {run.floorsVisited.map((f) => <option key={f} value={f}>{f}{f === heroFloor ? " (hero)" : ""}</option>)}
              </select>
              {!onHeroFloor && <button className="btn btn-sm btn-ghost" onClick={() => setPinnedFloor(null)} title="Follow the hero's floor again">follow hero</button>}
            </>}
          </span>
        )}
        <span className={`tag ${run.isTower ? "tag-info" : ""}`} data-testid="scenario-badge"
              title={run.isTower
                ? "Tower: several floors, stairs, shops (gold + EXP buy ATK/DEF/keys), tower system prompt"
                : "Single floor: one map, no shop economy, goal = kill the boss (enemy #299)"}>
          {run.isTower
            ? `tower ${run.floorRange.length ? `${run.floorRange[0]}→${run.floorRange[run.floorRange.length - 1]}` : ""}`
            : "single floor"}
        </span>
        {run.isTower && <span className="tag" data-testid="floor-progress">
          floor {run.floorsVisited.length}{run.floorRange.length ? `/${run.floorRange.length}` : ""}
        </span>}
        {map ? <span className="tag">{map.width}×{map.height}</span> : null}
      </>}
      actions={<>
        {live && <span className="tag tag-ok"><span className="dot dot-running" />live</span>}
        <select className="input" value={enemyMetric} onChange={(e) => setEnemyMetric(e.target.value as "dmg" | "hp")}
                aria-label="enemy number" title="Number drawn on enemy tiles" data-testid="enemy-metric">
          <option value="dmg">enemies: HP cost</option>
          <option value="hp">enemies: their HP</option>
        </select>
        <MapSkinSelect skin={skin} setSkin={setSkin} />
        <button className="btn btn-sm btn-ghost" onClick={() => setRailOpen((v) => !v)} data-testid="toggle-rail"
                title={railOpen ? "Hide reasoning rail (wider map)" : "Show reasoning rail"}>
          {railOpen ? <IconExpand /> : <IconCollapse />}{railOpen ? "focus map" : "show rail"}
        </button>
      </>}
      className="min-h-0 flex-1"
      bodyClass="flex-1 min-h-0 flex flex-col gap-2"
    >
      <div className="flex-1 min-h-0">
        {multiFloor && viewMode === "all" ? (
          <div className="rv-floors h-full" data-testid="all-floors"
               style={{ gridTemplateColumns: `repeat(${Math.max(1, Math.ceil(Math.sqrt(run.floorsVisited.length * 1.4)))}, minmax(0, 1fr))` }}>
            {run.floorsVisited.map((f) => {
              const st = floorStates[f];
              const isHero = f === heroFloor;
              return (
                <div key={f} className={`rv-floor-card ${isHero ? "is-hero" : ""} ${st?.visited ? "" : "is-unvisited"}`} data-testid="floor-card"
                     title={`${f}: ${st?.visited ? `state after turn ${st.lastTurn}` : "not entered yet at this turn"} — click to open full size`}
                     onClick={() => { setPinnedFloor(f === heroFloor ? null : f); setViewMode("single"); }}>
                  <div className="rv-floor-head">
                    <span className="mono">{f}</span>
                    {isHero && <span className="tag tag-ok">hero</span>}
                    {!st?.visited && <span className="tag">not yet</span>}
                    {st?.enemiesLeft != null && <span className="muted text-[11px] ml-auto">{st.enemiesLeft} enemies</span>}
                  </div>
                  <div className="rv-floor-map">
                    <FloorMap map={run.maps[f]} hero={isHero ? heroPos : null} stats={heroPos} removed={st?.removed}
                              target={isHero ? snap?.target ?? null : null} path={isHero ? snap?.path ?? null : null}
                              fit minCell={5} maxCell={22} enemyMetric={enemyMetric} skin={skin} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <FloorMap map={map} hero={onHeroFloor ? heroPos : null} stats={heroPos} removed={floorView.removed} target={floorView.target} path={floorView.path}
                    fit minCell={compact ? 12 : 14} maxCell={compact ? 44 : 72}
                    onCellClick={onHeroFloor ? onCellClick : undefined} highlight={onHeroFloor ? highlight : undefined} labels={onHeroFloor ? labels : undefined} enemyMetric={enemyMetric} skin={skin} />
        )}
      </div>
      {mapExtra}
      {transport}
      <div className="flex items-center gap-2 flex-wrap">
        <MapLegend enemyMetric={enemyMetric} skin={skin} />
        <span className="muted text-[11px] ml-auto">← → step · Space play · Home/End</span>
      </div>
    </Widget>
  );

  const stats = (
    <div className="grid grid-cols-2 gap-[var(--gap)] shrink-0">
      <Stat label="HP" value={hp} sub={`${hpPct.toFixed(0)}% of ${run.initialHp} · LV ${heroPos?.lv ?? 1}`} tone={hpTone as "ok" | "warn" | "bad"} />
      <Stat label="ATK / DEF" value={`${heroPos?.atk ?? "–"}/${heroPos?.def ?? "–"}`} sub={heroPos?.mdef ? `MDEF ${heroPos.mdef}` : `@(${heroPos?.x ?? "–"},${heroPos?.y ?? "–"})`} />
      <Stat label="Keys" value={heroPos?.keys ? `${heroPos.keys.yellow}/${heroPos.keys.blue}/${heroPos.keys.red}` : "–"} sub="yellow / blue / red" />
      <Stat label="Turn" value={snap?.turn ?? run.turnCount} sub={`${run.llmTurns} LLM · ${run.forcedTurns} forced${run.overrides ? ` · ${run.overrides} overridden` : ""}${run.parseErrors ? ` · ${run.parseErrors} parse err` : ""}`}
            title={run.overrides ? `${run.overrides} turn(s) where the engine executed a different action than the LLM chose (mechanical override: dead end / unwinnable / lethal)` : undefined} />
      {run.isTower && <>
        <Stat label="Gold / EXP" value={`${heroPos?.money ?? 0}/${heroPos?.exp ?? 0}`} sub="shop currency" title="Shops buy ATK/DEF/keys with gold (3F, 11F) or EXP (5F, 13F)" />
        <Stat label="Floor" value={snap?.floorId ?? run.currentFloor ?? "–"} sub={`${run.floorsVisited.length} visited${run.floorRange.length ? ` of ${run.floorRange.length}` : ""}`} />
      </>}
    </div>
  );

  const timeline = (
    <Widget title="Turns & reasoning" className="min-h-0 flex-1"
            badge={run.logSaved ? <span className="tag tag-ok" data-testid="log-saved">saved</span> : null}
            actions={<label className="flex items-center gap-1 text-[11px]"><input type="checkbox" checked={showCot} onChange={(e) => setShowCot(e.target.checked)} /> expand CoT</label>}
            bodyClass="flex-1 min-h-0 overflow-auto" flush>
      <div className="p-2" data-scroll>
        <Timeline cards={run.cards} activeSnap={idx} onSelectSnap={(i) => seek(i)} follow={pos == null} showCot={showCot} />
      </div>
    </Widget>
  );

  // The map is the biggest element on screen: fill whatever height the page hands us.
  const h = compact ? "min(72vh, 780px)" : "100%";

  return (
    <div ref={rootRef} tabIndex={0} onKeyDown={onKey} data-testid="run-view"
         className={`runview outline-none flex-1 ${railOpen ? "" : "no-rail"}`} style={{ height: h }}>
      <div className="rv-side flex flex-col gap-[var(--gap)] min-h-0 overflow-auto">
        {header}
        {stats}
        <Widget title="Result" className="shrink-0"><ScoreFooter result={res} /></Widget>
        {extra}
      </div>
      <div className="rv-map min-h-0 flex">{mapPanel}</div>
      {railOpen && <div className="rv-rail min-h-0 flex">{timeline}</div>}
    </div>
  );
}
