"use client";
// CSS-grid floor map: auto-fits its container (cell size from a ResizeObserver), hover tooltip,
// hero/removed/target/path overlays, and optional click-to-act highlighting (manual play).
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { Hero, MapCell, MapData } from "@/lib/types";
import { calcEnemyDmg, SPECIAL_NAMES } from "@/lib/format";
import SPRITES from "@/lib/sprites.json";

export type MapSkin = "classic" | "game";
type Sprite = [string, number];
const SKIN_KEY = "mota-map-skin";

/** Map skin shared by every map on the page and remembered across visits. */
export function useMapSkin(): [MapSkin, (s: MapSkin) => void] {
  const [skin, setSkinState] = useState<MapSkin>("classic");
  useEffect(() => {
    const read = () => setSkinState(localStorage.getItem(SKIN_KEY) === "game" ? "game" : "classic");
    read();
    window.addEventListener(SKIN_KEY, read);
    window.addEventListener("storage", read);
    return () => { window.removeEventListener(SKIN_KEY, read); window.removeEventListener("storage", read); };
  }, []);
  const setSkin = (s: MapSkin) => { localStorage.setItem(SKIN_KEY, s); window.dispatchEvent(new Event(SKIN_KEY)); };
  return [skin, setSkin];
}

export function MapSkinSelect({ skin, setSkin }: { skin: MapSkin; setSkin: (s: MapSkin) => void }) {
  return (
    <select className="input" value={skin} onChange={(e) => setSkin(e.target.value as MapSkin)} aria-label="map view"
            title="Classic: coloured cells with numbers. Game: the original game's tiles (24/project/materials)." data-testid="map-skin">
      <option value="classic">view: classic</option>
      <option value="game">view: game textures</option>
    </select>
  );
}

const S = SPRITES as unknown as {
  sheets: Record<string, { url: string; frames: number; w: number; h: number }>;
  tiles: Record<string, Sprite>; names: Record<string, Sprite>;
  hero: { sheet: string; rows: number; cols: number; down: number; stop: number };
  doors: Record<string, Sprite>; stairs: Record<string, Sprite>; wall: Sprite;
};
const GROUND = S.tiles["0"];

function spriteFor(c: MapCell): Sprite | null {
  if (c.id != null && S.tiles[String(c.id)]) return S.tiles[String(c.id)];
  switch (c.t) {  // logs recorded before cells carried their tile number
    case "#": return S.wall;
    case "Y": case "B": case "R": return S.doors[c.t];
    case "S": return S.stairs[c.dir === "downFloor" ? "down" : "up"];
    case "E": case "I": case "N": {
      const n = c.name ?? "";
      return S.names[n] ?? S.names[n.split(" (")[0]] ?? null;
    }
    default: return null;
  }
}

/** Background layers for one cell: sprite (frame 0) over the ground tile, scaled to `size`. */
function spriteStyle(sp: Sprite | null, size: number, ground: boolean): CSSProperties {
  const layers: string[] = [], pos: string[] = [], sizes: string[] = [];
  const add = ([sheet, idx]: Sprite) => {
    const m = S.sheets[sheet];
    layers.push(`url(${m.url})`);
    pos.push(`0px ${-idx * size}px`);
    sizes.push(`${m.frames * size}px ${(m.h / 32) * size}px`);
  };
  if (sp) add(sp);
  if (ground && (!sp || sp[0] !== "terrains" || sp[1] !== GROUND[1])) add(GROUND);
  return { backgroundImage: layers.join(", "), backgroundPosition: pos.join(", "), backgroundSize: sizes.join(", "),
           backgroundRepeat: "no-repeat", imageRendering: "pixelated" };
}

function heroStyle(size: number): CSSProperties {
  const h = S.hero, m = S.sheets[h.sheet];
  const fw = size, fh = (m.h / h.rows / (m.w / h.cols)) * size;
  const g = spriteStyle(null, size, true);
  return { ...g, backgroundImage: `url(${m.url}), ${g.backgroundImage}`,
           backgroundPosition: `${-h.stop * fw}px ${-h.down * fh}px, ${g.backgroundPosition}`,
           backgroundSize: `${h.cols * fw}px ${h.rows * fh}px, ${g.backgroundSize}` };
}

const CLS: Record<string, string> = {
  "#": "bg-[#374151] text-slate-500", ".": "bg-[#111827]", E: "bg-[#7f1d1d]", I: "bg-[#1e3a5f]",
  Y: "bg-[#78350f]", B: "bg-[#1e3a8a]", R: "bg-[#7f1d1d] border border-red-400", S: "bg-[#064e3b]", N: "bg-[#4c1d95]", T: "bg-[#1f2937]", "?": "bg-[#111827]",
};
const SYM: Record<string, string> = { "#": "#", ".": "", E: "E", I: "*", Y: "Y", B: "B", R: "R", S: "S", N: "N", T: "", "?": "?" };

type Props = {
  map: MapData | null | undefined;
  hero?: Hero | null;
  stats?: Hero | null;       // hero attributes for the damage overlay on floors the hero is not on
  removed?: Set<string>;
  target?: { x: number; y: number } | null;
  path?: number[][] | null;
  cell?: number;             // px; ignored when `fit` is set
  fit?: boolean;             // size cells to fill the parent box
  minCell?: number;
  maxCell?: number;
  onCellClick?: (x: number, y: number, cell: MapCell | string) => void;
  highlight?: Set<string>;   // "x,y" of actionable cells (manual mode)
  labels?: Record<string, string>;  // "x,y" -> short overlay label (e.g. action id)
  enemyMetric?: "dmg" | "hp";       // number drawn on enemy tiles
  skin?: MapSkin;
};

/** Cell size that makes a w×h grid fill `box`, clamped to [min,max]. */
function fitCell(box: { w: number; h: number }, w: number, h: number, min: number, max: number): number {
  const gutter = 22, gap = 1;
  const cw = (box.w - gutter - (w + 1) * gap) / w;
  const ch = (box.h - gutter - (h + 1) * gap) / h;
  return Math.max(min, Math.min(max, Math.floor(Math.min(cw, ch))));
}

export function FloorMap({ map, hero, stats, removed, target, path, cell = 28, fit, minCell = 14, maxCell = 64, onCellClick, highlight, labels, enemyMetric = "dmg", skin = "classic" }: Props) {
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ w: number; h: number } | null>(null);
  const pathSet = useMemo(() => new Set((path ?? []).map((p) => `${p[0]},${p[1]}`)), [path]);

  useLayoutEffect(() => {
    if (!fit || !boxRef.current) return;
    const el = boxRef.current;
    const ro = new ResizeObserver(() => setBox({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setBox({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, [fit]);
  useEffect(() => { setTip(null); }, [map?.floor_id]);

  if (!map) return <div ref={boxRef} className="muted p-4 w-full h-full flex items-center justify-center" data-testid="map-empty">No map</div>;
  const { width: w, height: h, grid } = map;
  const size = fit && box ? fitCell(box, w, h, minCell, maxCell) : cell;
  const hx = hero?.x ?? -1, hy = hero?.y ?? -1;
  const font = Math.max(8, Math.min(16, Math.round(size * 0.42)));
  const game = skin === "game";

  const inner = (
    <div className="relative select-none" data-testid="floor-map" data-skin={skin} onMouseLeave={() => setTip(null)}>
      <div className={`grid ${game ? "gap-0" : "gap-px"}`} style={{ gridTemplateColumns: `${Math.min(20, size)}px repeat(${w}, ${size}px)` }}>
        <div />
        {Array.from({ length: w }, (_, x) => <div key={`hx${x}`} className="text-[9px] text-center muted overflow-hidden" style={{ lineHeight: 1.2 }}>{size >= 12 ? x : ""}</div>)}
        {grid.map((row, y) => [
          // label cells must not be taller than a tile: in small maps a 9 px label made every row taller (gaps)
          <div key={`hy${y}`} className="text-[9px] muted flex items-center justify-center overflow-hidden" style={{ height: size, lineHeight: 1 }}>{size >= 12 ? y : ""}</div>,
          ...row.map((c, x) => {
            const cellObj = typeof c === "string" ? ({ t: c } as MapCell) : c;
            const t = cellObj.t;
            const k = `${x},${y}`;
            const isRemoved = removed?.has(k) ?? false;
            const isHero = x === hx && y === hy;
            let cls = CLS[t] ?? CLS["."];
            let sym = SYM[t] ?? "";
            let title = `(${x},${y})`;
            if (!isRemoved && t === "I") {
              const nm = (cellObj as { name?: string }).name?.toLowerCase() ?? "";
              sym = nm.includes("yellow key") ? "Y" : nm.includes("blue key") ? "B" : nm.includes("red key") ? "R" : "*";
              if (nm.includes("key")) cls += " text-yellow-200 font-bold";
              title = `${(cellObj as { name?: string }).name ?? "Item"} (${x},${y})`;
            }
            if (!isRemoved && t === "E") {
              const e = cellObj as Extract<MapCell, { t: "E" }>;
              const who = hero ?? stats;
              const dmg = who ? calcEnemyDmg(who, e) : (e.dmg != null && e.dmg < 999999999 ? e.dmg : null);
              const canWin = dmg != null && (who ? dmg < who.hp : e.canWin ?? true);
              cls += canWin ? " text-green-300" : " text-red-300 font-bold";
              sym = enemyMetric === "hp" ? String(e.hp) : dmg == null ? "!" : String(dmg);
              const sp = (e.specials ?? []).map((s) => SPECIAL_NAMES[s] ?? `#${s}`).join(", ");
              title = `${e.name} (${x},${y})\nHP ${e.hp}  ATK ${e.atk}  DEF ${e.def}  gold ${e.money ?? 0}${sp ? `\n${sp}` : ""}\n${dmg == null ? "CANNOT WIN at the hero's ATK" : `costs ${dmg} HP to kill now`}`;
            }
            if (!isRemoved && (t === "Y" || t === "B" || t === "R")) title = `${{ Y: "Yellow", B: "Blue", R: "Red" }[t]} door (${x},${y})`;
            if (!isRemoved && t === "S") title = `Stairs ${(cellObj as { dir?: string }).dir ?? ""} (${x},${y})`;
            if (!isRemoved && t === "N") title = `${(cellObj as { name?: string }).name ?? "NPC"} (${x},${y})`;
            if (isRemoved) { cls = "bg-[#111827] opacity-40"; sym = ""; }
            if (pathSet.has(k) && !isHero) cls += " ring-1 ring-inset ring-sky-400/60";
            if (target && target.x === x && target.y === y && !isHero) cls += " ring-2 ring-inset ring-amber-400";
            const actionable = highlight?.has(k) ?? false;
            if (actionable) cls += " ring-2 ring-inset ring-[var(--accent)] cell-interactive";
            if (isHero) { cls = "bg-[#fbbf24] text-black font-bold"; sym = "@"; }
            const label = labels?.[k];
            let style: CSSProperties = { width: size, height: size, fontSize: font };
            let enemyTag: string | null = null;
            if (game) {
              const sp = isRemoved ? null : spriteFor(cellObj);
              if (isHero) style = { ...style, ...heroStyle(size) };
              else if (sp || isRemoved || t === ".") style = { ...style, ...spriteStyle(sp, size, t !== "#" || isRemoved) };
              const known = isHero || sp || isRemoved || t === ".";
              if (known) {
                if (!isRemoved && t === "E") { enemyTag = sym; cls = cls.replace(/bg-\[[^\]]+\]/, ""); }
                else cls = cls.replace(/bg-\[[^\]]+\]/, "").replace("opacity-40", "");
                if (!isRemoved && t === "E" && S.sheets[sp?.[0] ?? ""]?.frames === 2) cls += " sprite-anim2";
                sym = "";
              }
              style = { ...style, ["--s" as string]: `${size}px` };
            }
            return (
              <div
                key={k}
                data-x={x} data-y={y} data-t={t} data-actionable={actionable || undefined} data-removed={isRemoved || undefined}
                className={`relative flex items-center justify-center font-mono ${game ? "" : "rounded-[2px]"} ${cls}`}
                style={style}
                onMouseEnter={(e) => setTip({ x: e.clientX, y: e.clientY, text: actionable ? `${title}\n\u2192 click to take this action` : title })}
                onMouseMove={(e) => setTip((tp) => (tp ? { ...tp, x: e.clientX, y: e.clientY } : tp))}
                onClick={onCellClick && (actionable || !highlight) ? () => onCellClick(x, y, c) : undefined}
              >
                {sym}
                {enemyTag && size >= 18 && (
                  <span className="sprite-dmg absolute left-0.5 bottom-0 leading-none font-bold" style={{ fontSize: Math.max(8, Math.round(size * 0.3)) }}>{enemyTag}</span>
                )}
                {label && size >= 20 && (
                  <span className="absolute -top-0.5 -right-0.5 px-0.5 rounded-bl bg-[var(--accent)] text-[var(--accent-fg)] font-bold"
                        style={{ fontSize: Math.max(7, font - 3) }}>{label}</span>
                )}
              </div>
            );
          }),
        ])}
      </div>
      {tip && (
        <div className="fixed z-50 pointer-events-none whitespace-pre text-xs px-2 py-1 rounded panel"
             style={{ left: tip.x + 12, top: tip.y + 12 }}>{tip.text}</div>
      )}
    </div>
  );

  if (!fit) return inner;
  return <div ref={boxRef} className="mapwrap w-full h-full">{inner}</div>;
}

export function MapLegend({ enemyMetric = "dmg", skin = "classic" }: { enemyMetric?: "dmg" | "hp"; skin?: MapSkin }) {
  if (skin === "game") {
    return (
      <span className="text-[11px] muted" data-testid="map-legend-game">
        Original game tiles (24/project/materials). Number on a monster = {enemyMetric === "hp" ? "its HP" : "HP it costs to kill now"} (green: winnable, red: not). Hover any tile for its stats.
      </span>
    );
  }
  const items: [string, string][] = [["#7f1d1d", enemyMetric === "hp" ? "Enemy (HP)" : "Enemy (HP cost to kill)"], ["#1e3a5f", "Item"], ["#78350f", "Door"], ["#064e3b", "Stairs"], ["#4c1d95", "NPC"], ["#fbbf24", "Hero"]];
  return (
    <div className="flex gap-3 text-[11px] muted flex-wrap">
      {items.map(([c, l]) => <span key={l}><span className="inline-block w-3 h-3 rounded-sm mr-1 align-middle" style={{ background: c }} />{l}</span>)}
    </div>
  );
}
