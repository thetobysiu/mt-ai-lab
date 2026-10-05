"""Character counts of every system prompt file for Appendix I (raw and stripped)."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1] / "seed_prompts"
for f in sorted(ROOT.rglob("*.txt")):
    t = f.read_text(encoding="utf-8")
    print(f"{str(f.relative_to(ROOT)):55s} raw={len(t):6d} strip={len(t.strip()):6d}")
