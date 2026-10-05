"""Start-HP sweep for hand03 (Table 4.5 lacks it): optimum and number of winning sets per start HP (exact Java solver)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import floor_lab as F  # noqa: E402

p = F.HAND / "hand03.txt"
lines = p.read_text(encoding="utf-8").rstrip().splitlines()
hero = lines[-1].split()
hps = [int(h) for h in sys.argv[1:]] or [641, 645, 649, 655, 670, 700, 800]
for h in hps:
    r = F.java_solve_many(["\n".join(lines[:-1] + [" ".join([str(h)] + hero[1:])]) + "\n"])[0]
    print(f"hand03 start {h}: " + (f"opt {r['hp']}, winning sets {r['wins']}" if r["solvable"] else "not winnable"), flush=True)
