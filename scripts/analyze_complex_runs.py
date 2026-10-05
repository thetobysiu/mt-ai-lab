"""Detailed post-mortem of the complex-floor LLM episodes.

For every stored complex run log: outcome class (kill / pre-boss death / lethal boss
attempt / alive-no-kill), the hero stats at the moment of the fatal decision, the
first turn where the trajectory diverges from the best stored kill, and the
distribution of decisions at that divergence point.

    python scripts/analyze_complex_runs.py [--out results/reliability/complex_postmortem.md]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BFS_OPT_HP = {"complex": 22, "simple": 13}


def _is_floor(d: dict, key: str) -> bool:
    f = str(d.get("floor_id", "")).lower()
    return key in f or ("复杂" in f if key == "complex" else "最简单" in f)


def _turns(d: dict) -> list[dict]:
    return [t for t in d.get("turns", []) if t.get("type") == "turn"]


def _sig(t: dict) -> str:
    """Action signature independent of numbering: type + target coordinates."""
    det = t.get("action_detail") or {}
    if det.get("type"):
        return f"{det['type']}@({det.get('x')},{det.get('y')})"
    return t.get("action", "")


def classify(d: dict) -> dict:
    res = d.get("result") or {}
    turns = _turns(d)
    hp = (res.get("details") or {}).get("final_hp")
    if hp is None and turns:
        hp = (turns[-1].get("hero") or {}).get("hp")
    goal = res.get("goal_reached")
    viol = [str(v) for v in res.get("violations", [])]
    last = turns[-1] if turns else {}
    last_det = last.get("action_detail") or {}
    last_name = last_det.get("name") or last.get("action", "")
    boss = ("boss" in last_name.lower()) or ("魔王" in last_name) or ("骷髅队长" in last_name and "complex" in str(d.get("floor_id", "")).lower())
    died = hp is not None and hp <= 0
    if goal and not died:
        cls = "kill"
    elif died and last_det.get("type") == "fight" and last_det.get("damage", 0) >= (last.get("hero_before") or {}).get("hp", 10**9):
        cls = "lethal_boss" if boss else "lethal_fight"
    elif died:
        cls = "lethal_boss" if boss else "lethal_fight"
    else:
        cls = "alive_no_kill"
    hero_before = None
    if len(turns) >= 2:
        hero_before = turns[-2].get("hero")
    elif turns:
        hero_before = turns[-1].get("hero")
    return {
        "file": Path(d.get("_path", "")).name,
        "model": d.get("task_model"),
        "prompt_chars": len(d.get("prompt") or ""),
        "class": cls,
        "final_hp": hp,
        "score": res.get("total"),
        "turns": len(turns),
        "llm_turns": sum(1 for t in turns if not t.get("forced")),
        "last_action": last.get("action", ""),
        "last_damage": last_det.get("damage"),
        "hero_final": {k: (hero_before or {}).get(k) for k in ("hp", "atk", "def")},
        "violations": viol[:3],
        "sigs": [_sig(t) for t in turns],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", default="complex")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = Path(args.out) if args.out else ROOT / "results" / "reliability" / f"{args.floor}_postmortem.md"

    files = sorted(set(glob.glob(str(ROOT / "logs" / "runs" / "*.json"))
                       + glob.glob(str(ROOT / "_archive" / "**" / "logs" / "runs" / "*.json"), recursive=True)))
    rows = []
    for p in files:
        if Path(p).name.startswith("_"):
            continue
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("mode") != "llm" or not _is_floor(d, args.floor):
            continue
        if not (d.get("result") or {}).get("total") is not None and not _turns(d):
            continue
        d["_path"] = p
        rows.append(classify(d))

    kills = [r for r in rows if r["class"] == "kill"]
    best = max(kills, key=lambda r: (r["final_hp"] or 0)) if kills else None
    opt = BFS_OPT_HP.get(args.floor)

    lines = [f"# {args.floor} floor — episode post-mortem", "",
             f"{len(rows)} LLM episodes with a stored run log (logs/runs + archives). BFS-optimal final HP = {opt}.", ""]
    cls_count = Counter(r["class"] for r in rows)
    lines += ["## Outcome classes", "", "| class | n | meaning |", "|---|---|---|",
              f"| kill | {cls_count['kill']} | boss killed, hero alive |",
              f"| lethal_boss | {cls_count['lethal_boss']} | hero attacked the boss with HP <= boss damage (suicide) |",
              f"| lethal_fight | {cls_count['lethal_fight']} | hero died to a non-boss enemy |",
              f"| alive_no_kill | {cls_count['alive_no_kill']} | stopped / stuck alive without killing the boss |", ""]

    # Per model
    lines += ["## By model", "", "| model | n | kill | lethal_boss | lethal_fight | alive_no_kill | kill HP (list) |", "|---|---|---|---|---|---|---|"]
    by_model: dict[str, list] = defaultdict(list)
    for r in rows:
        by_model[r["model"] or "?"].append(r)
    for m, rs in sorted(by_model.items(), key=lambda kv: -len(kv[1])):
        c = Counter(r["class"] for r in rs)
        hps = sorted((r["final_hp"] for r in rs if r["class"] == "kill"), reverse=True)
        lines.append(f"| {m} | {len(rs)} | {c['kill']} | {c['lethal_boss']} | {c['lethal_fight']} | {c['alive_no_kill']} | {hps} |")
    lines.append("")

    # Lethal boss attempts: how far below the requirement
    lb = [r for r in rows if r["class"] == "lethal_boss"]
    if lb:
        lines += ["## Lethal boss attempts (suicides)", "",
                  "Hero stats at the moment of the fatal boss fight. `damage` is what the engine showed the model *before* it chose the fight — the HP arithmetic was always available in the prompt.", "",
                  "| file | model | hp before | atk | def | boss damage shown | hp after | turns |", "|---|---|---|---|---|---|---|---|"]
        for r in lb:
            hf = r["hero_final"]
            lines.append(f"| {r['file']} | {r['model']} | {hf['hp']} | {hf['atk']} | {hf['def']} | {r['last_damage']} | {r['final_hp']} | {r['turns']} |")
        lines.append("")

    # Divergence from the best kill
    if best:
        lines += [f"## Divergence from the best stored kill ({best['file']}, HP={best['final_hp']}, {best['turns']} turns)", ""]
        ref = best["sigs"]
        div_turn = Counter()
        div_choice = defaultdict(Counter)
        for r in rows:
            if r is best:
                continue
            k = 0
            while k < min(len(ref), len(r["sigs"])) and ref[k] == r["sigs"][k]:
                k += 1
            if k < len(r["sigs"]):
                div_turn[k + 1] += 1
                div_choice[k + 1][f"{r['sigs'][k]}  (kill did {ref[k] if k < len(ref) else '-'})"] += 1
            else:
                div_turn["identical/prefix"] += 1
        lines += ["| first divergent turn | episodes |", "|---|---|"]
        for k, n in sorted(div_turn.items(), key=lambda kv: (str(type(kv[0])), kv[0])):
            lines.append(f"| {k} | {n} |")
        lines.append("")
        lines += ["### What the failing episodes did at their divergence point", ""]
        for k in sorted(k for k in div_choice if isinstance(k, int))[:12]:
            for choice, n in div_choice[k].most_common(4):
                lines.append(f"- turn {k}: {n}× `{choice}`")
        lines.append("")
        lines += ["### Best kill trajectory (action signatures)", "", "```"]
        for i, s in enumerate(ref, 1):
            lines.append(f"{i:3d}. {s}")
        lines += ["```", ""]

    # Per-episode table
    lines += ["## All episodes", "", "| file | model | class | final HP | score | turns | llm turns | last action |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["class"], -(r["final_hp"] or -10**9))):
        lines.append(f"| {r['file']} | {r['model']} | {r['class']} | {r['final_hp']} | {r['score']} | {r['turns']} | {r['llm_turns']} | {r['last_action'][:50]} |")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:60]))
    print(f"\n... wrote {out}")


if __name__ == "__main__":
    main()
