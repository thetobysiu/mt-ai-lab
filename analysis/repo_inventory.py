"""Read-only inventory for the public repository: run-log references and sizes."""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
runs = {os.path.basename(p): os.path.getsize(p) for p in glob.glob(os.path.join(R, "logs", "runs", "*.json"))}
arch = {os.path.basename(p): os.path.getsize(p) for p in glob.glob(os.path.join(R, "_archive", "**", "logs", "runs", "*.json"), recursive=True)}
refs = set()


def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "run_log" and isinstance(v, str):
                refs.add(os.path.basename(v))
            else:
                walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


for f in glob.glob(os.path.join(R, "results", "**", "*.json"), recursive=True):
    try:
        walk(json.load(open(f, encoding="utf-8")))
    except Exception:
        pass
present = refs & runs.keys()
in_arch = (refs - runs.keys()) & arch.keys()
print(f"logs/runs: {len(runs)} files, {sum(runs.values()) / 2**30:.2f} GB")
print(f"referenced: {len(refs)}; in logs/runs {len(present)} ({sum(runs[r] for r in present) / 2**30:.2f} GB); "
      f"only in _archive {len(in_arch)} ({sum(arch[r] for r in in_arch) / 2**20:.0f} MB); missing {len(refs - runs.keys() - arch.keys())}")
big = sorted(((runs[r], r) for r in present), reverse=True)[:5]
print("largest referenced:", [(f"{s / 2**20:.0f} MB", n) for s, n in big])
res = sum(os.path.getsize(p) for p in glob.glob(os.path.join(R, "results", "**", "*"), recursive=True) if os.path.isfile(p))
print(f"results/: {res / 2**20:.1f} MB")
