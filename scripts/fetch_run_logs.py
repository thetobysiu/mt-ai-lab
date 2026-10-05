"""Download the run logs of the thesis experiments and unpack them into logs/runs/ for replay in the platform.

    python scripts/fetch_run_logs.py                  # download run_logs.zip from the latest GitHub release
    python scripts/fetch_run_logs.py --zip run_logs.zip   # use a zip downloaded by hand
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mota.paths import RUN_LOGS  # noqa: E402

URL = "https://github.com/thetobysiu/mt-ai-lab/releases/latest/download/run_logs.zip"


def download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as resp, dest.open("wb") as out:  # noqa: S310 (fixed https URL)
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 2**20:6.0f} / {total / 2**20:.0f} MB", end="", flush=True)
    print()


def unpack(zip_path: Path) -> None:
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    added = skipped = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = Path(info.filename).name
            # flat archive of run logs: refuse directories and anything that is not a plain .json name
            if info.is_dir() or name != info.filename or not name.endswith(".json"):
                continue
            target = RUN_LOGS / name
            if target.exists():
                skipped += 1
                continue
            with z.open(info) as src, target.open("wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            added += 1
    print(f"{added} run logs added, {skipped} already present -> {RUN_LOGS}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--zip", type=Path, help="local run_logs.zip instead of downloading")
    ap.add_argument("--url", default=URL)
    a = ap.parse_args()
    if a.zip:
        unpack(a.zip)
        return
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "run_logs.zip"
        print(f"downloading {a.url}")
        download(a.url, dest)
        unpack(dest)


if __name__ == "__main__":
    main()
