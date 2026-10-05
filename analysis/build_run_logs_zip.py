"""Build run_logs.zip: every run log named by a result file in results/ (release asset of the repository).

    python analysis/build_run_logs_zip.py --logs <folder with the run logs> --out <path>/run_logs.zip
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]


def referenced() -> set[str]:
    names: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "run_log" and isinstance(v, str):
                    names.add(Path(v).name)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for p in (ROOT / "results").rglob("*.json"):
        try:
            walk(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    names = sorted(referenced())
    missing = [n for n in names if not (a.logs / n).exists()]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for i, n in enumerate(names, 1):
            src = a.logs / n
            if src.exists():
                z.write(src, arcname=n)
            if i % 200 == 0:
                print(f"  {i}/{len(names)}", flush=True)
    print(f"{len(names) - len(missing)} logs written, {len(missing)} missing -> {a.out} ({a.out.stat().st_size / 2**20:.0f} MB)")
    for n in missing[:20]:
        print("  missing:", n)


if __name__ == "__main__":
    main()
