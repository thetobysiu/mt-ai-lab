"""Which strategy rules did GEPA write into its candidates (from the rules-only seed, no strategy examples)?"""
import json, re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
THEMES = {
    "stat gems before fights": r"(gem|stat)s?[^.\n]{0,60}(before|first)|collect[^.\n]{0,40}(ATK|DEF|stat)",
    "fight order by HP cost / cheapest first": r"(lowest|smallest|minimi[sz]e|least)[^.\n]{0,40}(HP|damage|cost)|order[^.\n]{0,30}(fight|cost)",
    "skip fights that unlock nothing": r"(necessary|only if|block)[^.\n]{0,60}(path|item|boss)|unlocks nothing|optional",
    "doors only with purpose / dead ends": r"door[^.\n]{0,80}(only|dead end|prove|purpose|worth)",
    "boss timing (fight when winnable / after stats)": r"boss[^.\n]{0,80}(winnable|survive|all (accessible )?stats|as soon)",
    "HP reserve / 40% rule": r"(\d+ ?%|percent)[^.\n]{0,40}HP|reserve",
    "keys scarce": r"key[^.\n]{0,40}(scarce|conserve|precious|limited)",
    "trust engine annotations (effCost/ORDER)": r"effCost|ORDER|lookahead|min-cost",
    "action/reasoning consistency": r"(consisten|match)[^.\n]{0,40}(reason|choice|action)",
}
seed = Path("seed_prompts/core_rules.txt").read_text(encoding="utf-8")
groups: dict[str, list] = {"first study (gs1-gs4)": [], "(1+1), thinking (gs5)": [], "Pareto, thinking (gs5)": []}
for f in sorted(Path("results/gepa").glob("gepa_result_gs*_*.json")):
    g = json.loads(f.read_text(encoding="utf-8"))
    if g.get("seed_file") != "core_rules.txt":
        continue
    lab = f.stem.replace("gepa_result_", "")
    if g.get("method") == "pareto-loop":
        cands, key = [c["prompt"] for c in g["population"][1:]], "Pareto, thinking (gs5)"
    else:
        cands = [it["prompt"] for it in g["iterations"][1:]]
        key = "(1+1), thinking (gs5)" if lab.startswith("gs5") else "first study (gs1-gs4)"
    # unchanged repeats of the parent are not new candidates
    groups[key] += [(lab, i, p) for i, p in enumerate(cands, 1) if p.strip() != seed.strip()]
for key, rows in groups.items():
    print(f"\n{key}: {len(rows)} evolved candidates")
    for th, rx in THEMES.items():
        in_seed = bool(re.search(rx, seed, re.I))
        hits = [f"{lab}#{i}" for lab, i, p in rows if re.search(rx, p, re.I)]
        print(f"- {th}: {len(hits)}/{len(rows)}{' (already in seed)' if in_seed else ''}")
