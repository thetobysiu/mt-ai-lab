"""Table 6.11 cells and hand01 first model-chosen door from the canonical hand-floor runs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
OPT = {"hand01": 14, "hand02": 13, "hand03": 9, "hand04": 3}
MODELS = ["qwen3.5-397b", "deepseek-v4-flash", "qwen3.6-35b", "mistral-medium-3.5"]


def find_log(name):
    for base in [ROOT / "logs" / "runs", *ROOT.glob("_archive/**/logs/runs")]:
        p = base / name
        if p.exists():
            return p
    return None


first = True
for floor, opt in OPT.items():
    for m in MODELS:
        p = ROOT / "results" / "reliability" / f"{floor}_{m}_canon.json"
        if not p.exists():
            print(floor, m, "MISSING")
            continue
        d = json.load(open(p, encoding="utf-8"))
        runs = d["runs"]
        if first:
            print("top keys:", list(d.keys()))
            print("run keys:", list(runs[0].keys()))
            first = False
        wins = [r for r in runs if r.get("success")]
        hp = sum(r["final_hp"] for r in wins) / len(wins) / opt if wins else None
        ov = [r.get("overrides") for r in runs]
        print(f"{floor} {m}: {len(wins)}/{len(runs)} hpopt={hp if hp is None else round(hp, 2)} "
              f"final_hp={[r.get('final_hp') for r in runs]} success={[bool(r.get('success')) for r in runs]} "
              f"died={[bool(r.get('died')) for r in runs]} overrides={ov}")
        if floor in ("hand01", "hand02"):
            for r in runs:
                log = find_log(r.get("run_log", ""))
                if not log:
                    print("   log missing", r.get("run_log"))
                    continue
                turns = json.loads(log.read_text(encoding="utf-8"))["turns"]
                tt = [t for t in turns if t.get("type") == "turn"]
                nf = [t for t in tt if not t.get("forced")]
                f0 = nf[0] if nf else None
                forced_before = [t.get("action") for t in tt[: tt.index(f0)]] if f0 else []
                print(f"   {r.get('run_log')} success={bool(r.get('success'))} hp={r.get('final_hp')} "
                      f"forced_before={forced_before} first_choice=T{f0.get('turn') if f0 else None} "
                      f"{f0.get('action') if f0 else None} corrected_from={f0.get('corrected_from') if f0 else None}")
