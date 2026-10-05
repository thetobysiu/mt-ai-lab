"""
Census of every stored run log on the boss floors -> empirical success counts.

Scans logs/runs/ and the archived logs, classifies each LLM episode as boss
killed / not killed / died, and writes results/reliability/log_census.md plus
a JSON ledger. This is the retrospective complement to run_reliability.py.

    python scripts/census_run_logs.py
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from run_reliability import wilson_ci  # noqa: E402

BOSS_FLOORS = {"simple": ("simple", "最简单"), "complex": ("complex", "复杂")}
SCORER_FIX_DATE = "20260422"  # results before this used the broken scorer


def _floor_key(floor: str) -> str | None:
    f = str(floor).lower()
    for key, needles in BOSS_FLOORS.items():
        if any(n in f for n in needles):
            return key
    return None


def main():
    files = sorted(set(
        glob.glob(str(ROOT / "logs" / "runs" / "*.json"))
        + glob.glob(str(ROOT / "_archive" / "**" / "logs" / "runs" / "*.json"), recursive=True)
    ))
    rows = []
    for p in files:
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        meta = d.get("meta", d)
        if (meta.get("mode") or d.get("mode")) != "llm":
            continue
        floor = _floor_key(meta.get("floor_id") or d.get("floor_id") or "")
        if not floor:
            continue
        res = d.get("result") or {}
        if not res or res.get("total") is None:
            continue  # aborted / unfinished episode
        viol = [str(v) for v in res.get("violations", [])]
        hp = (res.get("details") or {}).get("final_hp")
        died = any("suicide" in v for v in viol) or (hp is not None and hp <= 0)
        killed = ("boss_not_killed" not in viol) and not died
        name = Path(p).name
        rows.append({
            "file": name,
            "date": name[:8],
            "floor": floor,
            "model": meta.get("task_model") or d.get("task_model") or "?",
            "task_mode": meta.get("task_mode") or "",
            "score": round(float(res["total"]), 4),
            "final_hp": hp,
            "steps": (res.get("details") or {}).get("steps"),
            "boss_killed": killed,
            "died": died,
            "violations": viol,
            "pre_scorer_fix": name[:8] < SCORER_FIX_DATE,
            "prompt_chars": len(meta.get("prompt") or d.get("prompt") or ""),
        })

    out_dir = ROOT / "results" / "reliability"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "log_census.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r["floor"], r["model"])].append(r)

    md = ["# Boss-floor run-log census (retrospective)", "",
          "Every completed LLM episode found in `logs/runs/` and the archive, by floor and task model. "
          "Prompts and evaluator versions vary across dates, so these are *existence* counts, not a controlled sample. "
          f"Episodes before {SCORER_FIX_DATE} used the pre-fix scorer (scores not comparable, kill/no-kill still valid).", "",
          "| floor | model | episodes | boss killed | died | kill rate [Wilson 95%] | kill scores (HP) | date range |",
          "|---|---|---|---|---|---|---|---|"]
    for (floor, model), rs in sorted(groups.items()):
        n = len(rs); k = sum(r["boss_killed"] for r in rs); dd = sum(r["died"] for r in rs)
        lo, hi = wilson_ci(k, n)
        kills = ", ".join(f"{r['score']} ({r['final_hp']})" for r in rs if r["boss_killed"]) or "—"
        dates = f"{min(r['date'] for r in rs)}–{max(r['date'] for r in rs)}"
        md.append(f"| {floor} | {model} | {n} | {k} | {dd} | {k}/{n} = {k/n:.2f} [{lo:.2f}, {hi:.2f}] | {kills} | {dates} |")
    md += ["", "## Boss-kill episodes", "", "| date | floor | model | score | final HP | steps | file |", "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["floor"], r["date"])):
        if r["boss_killed"]:
            md.append(f"| {r['date']} | {r['floor']} | {r['model']} | {r['score']} | {r['final_hp']} | {r['steps']} | `{r['file']}` |")
    (out_dir / "log_census.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\n{len(rows)} episodes -> {out_dir / 'log_census.md'}")


if __name__ == "__main__":
    main()
