"use client";
// Maps: every floor in the agent's renderer, in two tabs.
//   Single floors — the boss floors the single-floor experiments use (reference, hand-designed, generated),
//                   each with its exact optimum and difficulty measures.
//   Tower        — the 24-layer game's floors MT0–MT23, with the scripted events the engine models or not.
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getJson } from "@/lib/api";
import type { MapCell, MapData } from "@/lib/types";
import { FloorMap, MapLegend, MapSkinSelect, useMapSkin } from "@/components/FloorMap";
import { Widget, Stat } from "@/components/Widget";
import { IconMap, IconPlay } from "@/components/Icons";
import type { SingleFloor, SingleFloorGroup } from "@/components/ConditionForm";

type TowerRow = { floor_id: string; title: string; width: number | null; height: number | null; scripted_events: string[] };
const MODELLED = new Set(["openShop", "changePos", "setValue", "hide", "setBlock", "show", "changeFloor", "showStatusBar"]);

function playHref(f: string) {
  return `/play/?floor=${encodeURIComponent(f === "MT3" ? "mota-floor:MT3" : f === "MT4" ? "special-floor:MT4" : f)}`;
}

function MapsInner() {
  const params = useSearchParams();
  const initial = params.get("floor") || "simple";
  const [tab, setTab] = useState<"single" | "tower">(/^MT/.test(initial) ? "tower" : "single");
  const [groups, setGroups] = useState<SingleFloorGroup[]>([]);
  const [towerFloors, setTowerFloors] = useState<string[]>([]);
  const [towerRows, setTowerRows] = useState<Record<string, TowerRow>>({});
  const [sel, setSel] = useState<string>(initial);
  const [map, setMap] = useState<MapData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [metric, setMetric] = useState<"dmg" | "hp">("hp");
  const [skin, setSkin] = useMapSkin();

  useEffect(() => {
    getJson<{ groups: SingleFloorGroup[] }>("/api/single-floors").then((r) => setGroups(r.groups)).catch(() => {});
    getJson<{ floor_ids: string[] }>("/api/floor-sequence").then((r) => setTowerFloors(r.floor_ids)).catch(() => {});
    getJson<{ floors: TowerRow[] }>("/api/projects/24/floors").then((r) => setTowerRows(Object.fromEntries(r.floors.map((f) => [f.floor_id, f])))).catch(() => {});
  }, []);
  useEffect(() => {
    setErr(null); setMap(null);
    getJson<MapData>(`/api/map?floor=${encodeURIComponent(sel)}`).then(setMap).catch((e) => setErr(String((e as Error).message)));
  }, [sel]);

  const counts = useMemo(() => {
    const c = { enemies: 0, items: 0, doors: 0, stairs: 0, npcs: 0, unwinnable: 0 };
    if (!map) return c;
    for (const row of map.grid) for (const cell of row) {
      const t = typeof cell === "string" ? cell : (cell as MapCell).t;
      if (t === "E") { c.enemies++; if (typeof cell !== "string" && (cell as { canWin?: boolean }).canWin === false) c.unwinnable++; }
      else if (t === "I") c.items++;
      else if (t === "Y" || t === "B" || t === "R") c.doors++;
      else if (t === "S") c.stairs++;
      else if (t === "N") c.npcs++;
    }
    return c;
  }, [map]);
  const single: SingleFloor | undefined = groups.flatMap((g) => g.floors).find((f) => f.id === sel);
  const tower = towerRows[sel];
  const events = (tower?.scripted_events ?? []).filter((e) => !e.endsWith(":unparsed"));
  const pick = (f: string) => setSel(f);

  return (
    <div className="grid gap-[var(--gap)] grid-cols-[minmax(210px,240px)_minmax(0,1fr)_minmax(240px,300px)] page-fill" data-testid="page-maps">
      <Widget title="Floors" className="min-h-0" bodyClass="min-h-0 flex flex-col gap-2 text-xs"
              actions={<div className="flex gap-1">
                <button className={`btn btn-sm ${tab === "single" ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab("single")} data-testid="maps-tab-single">single floors</button>
                <button className={`btn btn-sm ${tab === "tower" ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab("tower")} data-testid="maps-tab-tower">tower</button>
              </div>}>
        <div className="flex-1 min-h-0 overflow-auto flex flex-col gap-2" data-testid="floor-list">
          {tab === "single" ? groups.map((g) => (
            <div key={g.group}>
              <div className="muted text-[11px] mb-0.5">{g.title}</div>
              <div className="flex flex-col gap-0.5">
                {g.floors.map((f) => (
                  <button key={f.id} className={`nav-link justify-start ${sel === f.id ? "active" : ""}`} onClick={() => pick(f.id)}
                          data-testid="floor-item" data-floor={f.id} title={f.note ?? ""}>
                    <span className="mono">{f.id}</span>
                    <span className="tag ml-auto" title="exact optimum: HP left after the boss">opt {f.optimum_hp ?? "?"}</span>
                  </button>
                ))}
              </div>
            </div>
          )) : (
            <div className="flex flex-col gap-0.5">
              <div className="muted text-[11px] mb-0.5">24-layer game, played as a tower from MT0</div>
              {towerFloors.map((f) => (
                <button key={f} className={`nav-link justify-start ${sel === f ? "active" : ""}`} onClick={() => pick(f)} data-testid="floor-item" data-floor={f}>
                  <span className="mono">{f}</span>
                  {(towerRows[f]?.scripted_events ?? []).some((e) => !MODELLED.has(e.split(":")[0]) && !e.endsWith(":unparsed")) &&
                    <span className="tag tag-bad ml-auto" title="has scripted events the engine does not model">events</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      </Widget>

      <Widget title={`Map · ${sel}`} className="min-h-0 flex-1"
              badge={<>{map ? <span className="tag">{map.width}×{map.height}</span> : null}<span className={`tag ${/^MT/.test(sel) ? "tag-info" : ""}`}>{/^MT/.test(sel) ? "tower floor" : "single floor"}</span></>}
              actions={<>
                <select className="input" value={metric} onChange={(e) => setMetric(e.target.value as "dmg" | "hp")} aria-label="number shown on enemies">
                  <option value="hp">enemies: their HP</option>
                  <option value="dmg">enemies: HP it costs the entry hero</option>
                </select>
                <MapSkinSelect skin={skin} setSkin={setSkin} />
                <a className="btn btn-sm btn-primary" href={playHref(sel)} data-testid="maps-play"><IconPlay />Play this floor</a>
                {/^MT/.test(sel) && <a className="btn btn-sm" href={`/play/?floor=mota24`} title="Start a tower run (MT0→…)"><IconMap />tower run</a>}
              </>}
              bodyClass="flex-1 min-h-0 flex flex-col gap-2">
        <div className="flex-1 min-h-0">
          {err ? <div className="text-red-300 text-xs p-3">{err}</div> :
            <FloorMap map={map} hero={map?.hero ?? null} fit minCell={14} maxCell={72} enemyMetric={metric} skin={skin} />}
        </div>
        <div className="flex items-center gap-2 flex-wrap"><MapLegend enemyMetric={metric} skin={skin} /><span className="muted text-[11px] ml-auto">hover a tile for its stats</span></div>
      </Widget>

      <div className="flex flex-col gap-[var(--gap)] min-h-0 overflow-auto">
        <div className="grid grid-cols-2 gap-[var(--gap)]">
          <Stat label="Enemies" value={counts.enemies} sub={counts.unwinnable ? `${counts.unwinnable} unwinnable at start` : "all winnable at start"} tone={counts.unwinnable ? "warn" : undefined} />
          <Stat label="Items" value={counts.items} />
          <Stat label="Doors" value={counts.doors} />
          <Stat label="NPCs / stairs" value={`${counts.npcs} / ${counts.stairs}`} />
        </div>
        <Widget title="Hero at entry" className="shrink-0">
          {map?.hero ? (
            <div className="text-xs mono">HP {map.hero.hp} · ATK {map.hero.atk} · DEF {map.hero.def} · keys {map.hero.keys?.yellow}/{map.hero.keys?.blue}/{map.hero.keys?.red}</div>
          ) : <span className="muted text-xs">–</span>}
        </Widget>
        {single && (
          <Widget title="Exact solver" className="shrink-0" testId="floor-facts"
                  footer={<>Optimum = HP left after the boss on the best route. Critical = decisions on that route where an alternative makes
                    the boss unwinnable; forced = decisions where only the optimal action keeps it winnable.</>}>
            <div className="text-xs grid grid-cols-2 gap-x-3 gap-y-1">
              <span className="muted">optimum HP</span><b>{single.optimum_hp ?? "–"}</b>
              {single.winning_sets != null && <><span className="muted">winning sets</span><span>{single.winning_sets}</span></>}
              {single.critical != null && <><span className="muted">critical / forced</span><span>{single.critical} / {single.forced}</span></>}
              {single.random_win != null && <><span className="muted">random play wins</span><span>{(single.random_win * 100).toFixed(0)} %</span></>}
              {single.solver_states != null && <><span className="muted">solver states</span><span>{single.solver_states}</span></>}
              <span className="muted">heuristic</span><span className={single.heuristic === "kills" ? "text-emerald-300" : "text-red-300"}>{single.heuristic}</span>
              {single.note && <span className="col-span-2 muted">{single.note}</span>}
            </div>
          </Widget>
        )}
        {/^MT/.test(sel) && (
          <Widget title="Scripted events" className="shrink-0"
                  footer={<>green = modelled by the engine (shops, gift NPCs, flags); red = not modelled (conditional dialogs, after-battle scripts).</>}>
            {tower ? (events.length === 0 ? <span className="muted text-xs">none</span> :
              <div className="flex flex-wrap gap-1">
                {events.map((e, i) => <span key={i} className={`tag ${MODELLED.has(e.split(":")[0]) ? "tag-ok" : "tag-bad"}`}>{e}</span>)}
              </div>) : <span className="muted text-xs">–</span>}
          </Widget>
        )}
      </div>
    </div>
  );
}

export default function MapsPage() {
  return <Suspense fallback={<p className="muted">Loading…</p>}><MapsInner /></Suspense>;
}
