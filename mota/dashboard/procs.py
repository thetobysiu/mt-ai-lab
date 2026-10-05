"""Background CLI processes started from the dashboard (catalog re-runs, constrained GEPA).

The processes are ordinary CLI runs: run_reliability.py registers its own job manifest, so every episode
also appears on the Live page. This module only remembers what the dashboard started, where its output
goes, and how to stop it. Children inherit the server's environment, including an API key set on the
Settings panel (never written to disk or logs).
"""
from __future__ import annotations

import datetime
import subprocess
import sys
import threading
from pathlib import Path

from .api.paths import GEPA_ROOT

LOG_DIR = GEPA_ROOT / "logs" / "ui_procs"
_lock = threading.Lock()
_procs: dict[int, dict] = {}


def start(kind: str, title: str, argv: list[str], env_extra: dict | None = None) -> dict:
    """Start `python <argv...>` in the repository root, output to logs/ui_procs/<stamp>_<kind>.log."""
    import os
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"{stamp}_{kind}.log"
    env = {**os.environ, **(env_extra or {}), "PYTHONIOENCODING": "utf-8"}
    fh = open(log_path, "w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen([sys.executable, "-u", *argv], cwd=GEPA_ROOT, stdout=fh, stderr=subprocess.STDOUT,
                         env=env, creationflags=flags)
    rec = {"pid": p.pid, "kind": kind, "title": title, "argv": argv, "log": str(log_path.relative_to(GEPA_ROOT)),
           "started": datetime.datetime.now().isoformat(timespec="seconds"), "_p": p, "_fh": fh}
    with _lock:
        _procs[p.pid] = rec
    return public(rec)


def public(rec: dict) -> dict:
    p: subprocess.Popen = rec["_p"]
    rc = p.poll()
    if rc is not None and not rec["_fh"].closed:
        rec["_fh"].close()
    return {k: v for k, v in rec.items() if not k.startswith("_")} | {
        "running": rc is None, "exit_code": rc, "tail": tail(GEPA_ROOT / rec["log"])}


def tail(path: Path, lines: int = 12) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        return []


def listing(kind: str | None = None) -> list[dict]:
    with _lock:
        recs = [r for r in _procs.values() if kind is None or r["kind"] == kind]
    return sorted((public(r) for r in recs), key=lambda r: r["started"], reverse=True)


def stop(pid: int) -> bool:
    """Stop a process started here, with its children (the run_reliability.py episodes)."""
    with _lock:
        rec = _procs.get(pid)
    if rec is None:
        return False
    try:
        import psutil
        parent = psutil.Process(pid)
        for c in parent.children(recursive=True):
            c.kill()
        parent.kill()
    except Exception:
        rec["_p"].kill()
    return True
