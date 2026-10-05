"""Retrospective latency census over every stored run log.

Each RunLogger event carries `_ts`; an LLM decision is the span from a
`thinking` event to the next non-forced `turn` (or `parse_error`) event on the
same turn number. Forced turns cost no API call and are excluded.

Usage (from the repository root):
    python scripts/latency_census.py [--dirs logs/runs _archive/**/logs/runs] [--out results/reliability/latency_census.md]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mota.analysis.latency import census, render_markdown, episode_latencies as _episode_latencies  # noqa: E402,F401


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="*", default=["logs/runs", "_archive/**/logs/runs"])
    ap.add_argument("--out", default="results/reliability/latency_census.md")
    args = ap.parse_args()

    text = render_markdown(census(args.dirs, ROOT))
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
