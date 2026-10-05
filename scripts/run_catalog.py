"""Re-run thesis experiments from the catalog (mota/harness/catalog.py) under a new label.

    python scripts/run_catalog.py --list
    python scripts/run_catalog.py --ids final-stack depth-curve [--repeats 2] [--prefix rerun_20260930]
    python scripts/run_catalog.py --codes G1 P3

Each registry code runs run_reliability.py with the thesis cell's exact arguments and env
(scripts/run_followups.py), except: the label becomes <prefix>_<label>, --append is dropped, and
--repeats can be lowered. Script entries (GEPA study) get --label <prefix>_<id>. Uses the API key in the
environment (SAIA_API_KEY / SAIA_API_KEYS).
"""
from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from mota.harness import catalog as C  # noqa: E402


def cell_command(code: str, experiments: dict, prefix: str, repeats: int | None) -> list[str]:
    args = [a for a in experiments[code] if a != "--append"]
    i = args.index("--label")
    args[i + 1] = f"{prefix}_{args[i + 1]}"
    if repeats and "--repeats" in args:
        j = args.index("--repeats")
        args[j + 1] = str(min(int(args[j + 1]), repeats))
    return [str(ROOT / "run_reliability.py"), *args, "--force"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=[], help="catalog entry ids")
    ap.add_argument("--codes", nargs="*", default=[], help="registry codes (scripts/run_followups.py)")
    ap.add_argument("--repeats", type=int, default=None, help="cap episodes per cell (default: the thesis N)")
    ap.add_argument("--prefix", default="rerun_" + datetime.datetime.now().strftime("%Y%m%d_%H%M"))
    ap.add_argument("--list", action="store_true", help="list the catalog entries and their cells, then exit")
    a = ap.parse_args()
    experiments, env = C.registry()
    if a.list:
        for e in C.CATALOG:
            cells = " ".join(e.get("codes", [])) or " ".join(e.get("script", []))
            print(f"{e['id']:<24} {e['section']:<10} {e['title']}\n{'':<24} {cells}")
        return 0
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")  # does not override a key already set in the process env
    except ImportError:
        pass
    if not (os.environ.get("SAIA_API_KEY") or os.environ.get("SAIA_API_KEYS")):
        print("no API key: set SAIA_API_KEY (or put it in .env, or use the dashboard's API key panel)", flush=True)
        return 2
    by_id = {e["id"]: e for e in C.CATALOG}
    jobs: list[tuple[str, list[str], dict]] = []
    for eid in a.ids:
        e = by_id[eid]
        for code in e.get("codes", []):
            jobs.append((code, cell_command(code, experiments, a.prefix, a.repeats), env.get(code, {})))
        if e.get("script"):
            script = [str(ROOT / e["script"][0]), *e["script"][1:], "--label", f"{a.prefix}_{eid}"]
            jobs.append((eid, script, {}))
    for code in a.codes:
        jobs.append((code, cell_command(code, experiments, a.prefix, a.repeats), env.get(code, {})))
    seen: set[str] = set()
    for i, (name, cmd, extra) in enumerate(jobs, 1):
        if name in seen:
            continue
        seen.add(name)
        print(f"\n=== [{i}/{len(jobs)}] {name}: {' '.join(Path(cmd[0]).name if k == 0 else c for k, c in enumerate(cmd))}", flush=True)
        rc = subprocess.run([sys.executable, "-u", *cmd], cwd=ROOT, env={**os.environ, **extra}).returncode
        print(f"=== {name} finished (exit {rc})", flush=True)
    print("\ncatalog run done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
