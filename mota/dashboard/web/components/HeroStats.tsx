import type { Hero } from "@/lib/types";

export function HeroStats({ hero, initialHp, floorId, turn }: { hero: Hero | null | undefined; initialHp?: number; floorId?: string | null; turn?: number }) {
  if (!hero) return <div className="muted text-xs" data-testid="hero-stats">no hero</div>;
  const pct = Math.max(0, Math.min(100, (hero.hp / (initialHp || hero.hp || 1)) * 100));
  const col = pct > 50 ? "var(--ok)" : pct > 20 ? "var(--warn)" : "var(--bad)";
  return (
    <div className="text-xs space-y-1" data-testid="hero-stats">
      <div className="flex gap-3 flex-wrap items-baseline">
        {floorId && <span className="tag">{floorId}</span>}
        {turn != null && <span className="muted">turn {turn}</span>}
        <span>HP <b data-testid="stat-hp">{hero.hp}</b></span>
        <span>ATK <b data-testid="stat-atk">{hero.atk}</b></span>
        <span>DEF <b data-testid="stat-def">{hero.def}</b></span>
        {hero.mdef != null && hero.mdef > 0 && <span>MDEF <b>{hero.mdef}</b></span>}
        <span>Gold <b>{hero.money ?? 0}</b></span>
        {hero.exp != null && <span>EXP <b>{hero.exp}</b></span>}
        {hero.keys && (
          <span className="font-mono">
            <span className="text-yellow-300">Y{hero.keys.yellow}</span> <span className="text-blue-300">B{hero.keys.blue}</span> <span className="text-red-300">R{hero.keys.red}</span>
          </span>
        )}
        <span className="muted">@({hero.x},{hero.y})</span>
      </div>
      <div className="h-1.5 rounded bg-[#1f2937] overflow-hidden"><div className="h-full" style={{ width: `${pct}%`, background: col }} /></div>
    </div>
  );
}
