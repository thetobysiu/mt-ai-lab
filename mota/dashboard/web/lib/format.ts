export function pct(x: number | null | undefined, digits = 0): string {
  return x == null || Number.isNaN(x) ? "–" : `${(x * 100).toFixed(digits)}%`;
}

export function num(x: number | null | undefined, digits = 2): string {
  return x == null || Number.isNaN(x) ? "–" : x.toFixed(digits);
}

export function ci(a: [number, number] | undefined): string {
  return a ? `[${a[0].toFixed(2)}, ${a[1].toFixed(2)}]` : "";
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "–";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
  return `${(s / 86400).toFixed(1)}d`;
}

export function dur(startIso: string | null | undefined, endIso?: string | null): string {
  if (!startIso) return "–";
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const s = Math.max(0, (end - new Date(startIso).getTime()) / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  return h ? `${h}h${String(m).padStart(2, "0")}m` : m ? `${m}m${String(sec).padStart(2, "0")}s` : `${sec}s`;
}

export function shortModel(m: string | null | undefined): string {
  if (!m) return "heuristic";
  return m.replace(/-a\d+b$/i, "").replace(/-instruct.*$/i, "");
}

const BREAK_ARMOR_RATIO = 0.9, COUNTER_ATTACK_RATIO = 0.1, PURIFY_MULTIPLIER = 3;  // mota/game/data.py

/** Mirror of mota/game/damage.py calculate() for the map overlay (must stay in sync; constants from damage.py). */
export function calcEnemyDmg(
  hero: { atk: number; def: number; hp?: number; mdef?: number },
  mon: { hp: number; atk: number; def: number; specials?: number[]; fixed?: number; vampire?: number; n?: number },
): number | null {
  const sp = mon.specials || [];
  let mAtk = mon.atk, mDef = mon.def;
  if (sp.includes(10)) { mAtk = hero.atk; mDef = hero.def; }
  if (sp.includes(3) && mDef < hero.atk - 1) mDef = hero.atk - 1;
  const per = Math.max(0, hero.atk - mDef);
  if (per <= 0) return null;
  const turns = Math.ceil(mon.hp / per);
  let perDamage = sp.includes(2) ? mAtk : Math.max(0, mAtk - hero.def);
  if (sp.includes(4)) perDamage *= 2; else if (sp.includes(5)) perDamage *= 3; else if (sp.includes(6)) perDamage *= mon.n && mon.n > 0 ? mon.n : 4;
  const mdef = hero.mdef ?? 0;
  let init = sp.includes(1) ? perDamage : 0;
  if (sp.includes(11)) init += Math.floor((hero.hp ?? 0) * (mon.vampire ?? 0));
  if (sp.includes(7)) init += Math.floor(BREAK_ARMOR_RATIO * hero.def);
  if (sp.includes(9)) init += PURIFY_MULTIPLIER * mdef;
  const counter = sp.includes(8) ? Math.floor(COUNTER_ATTACK_RATIO * hero.atk) : 0;
  let total = init + (perDamage + counter) * Math.max(0, turns - 1);
  if (sp.includes(22)) total += mon.fixed ?? 0;
  return Math.max(0, total - mdef);
}

export const SPECIAL_NAMES: Record<number, string> = {
  1: "First Strike", 2: "Magic ATK", 3: "Solid", 4: "Double Hit", 5: "Triple Hit", 6: "N-Hit", 7: "Break Armor",
  8: "Counter", 9: "Purify", 10: "Mimic", 11: "Vampire", 22: "Fixed Dmg",
};
