"""Start-HP sweep beyond the design value: optimum and number of distinct winning sets (exact Java solver).

    python scratch/tune_sweep.py hand02 50 400 25
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import floor_lab as F  # noqa: E402

name, lo, hi, step = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
p = F.HAND / f"{name}.txt"
lines = p.read_text(encoding="utf-8").rstrip().splitlines()
hero = lines[-1].split()
hps = list(range(lo, hi + 1, step))
res = F.java_solve_many(["\n".join(lines[:-1] + [" ".join([str(h)] + hero[1:])]) + "\n" for h in hps])
print(f"{name} (design start HP {hero[0]}):")
print("  " + ", ".join(f"{h}: {r['hp'] if r['solvable'] else '-'}/{r['wins'] if r['solvable'] else 0}" for h, r in zip(hps, res)))
