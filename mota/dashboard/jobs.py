"""
Cross-process job registry: one JSON manifest per run under logs/jobs/.

Written by CLI runners (run_reliability.py, run_followups.py, run_model_matrix.py, run_gepa.py)
and by the dashboard API for runs it launches itself. The dashboard's JobWatcher tails these
manifests (and the run logs they point at) so every experiment — including ones started from
a terminal — is visible live in the UI. Manifests are written atomically (tmp + os.replace).

Job kinds: reliability | tower | gepa | matrix | ui-eval | manual | followup-queue
Status:    queued | running | paused | done | failed | killed | stopped

Pause/resume: the dashboard sets ``pause_requested`` in the manifest; the owning process
calls ``pause_gate(job)`` between turns (wired into the on_event hooks of the harness and the
SSE streamer), sees the flag on its next flush/poll, flips status to ``paused`` and blocks until
the flag is cleared. Control fields set by other processes survive the owner's rewrites
(``_flush`` merges them from disk).
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

from .api.paths import JOBS_DIR

_ACTIVE = ("queued", "running", "paused")
_CONTROL_FIELDS = ("pause_requested",)  # written by controllers, owned by nobody: never clobber


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_job_id(kind: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"{stamp}_{kind}_{secrets.token_hex(2)}"


def _proc_create_time(pid: int) -> float | None:
    try:
        return psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def pid_alive(pid: int | None, create_time: float | None = None) -> bool:
    """True if pid exists and (when known) was created at the recorded time (guards pid reuse)."""
    if not pid:
        return False
    ct = _proc_create_time(pid)
    if ct is None:
        return False
    if create_time is not None and abs(ct - create_time) > 2.0:
        return False
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    for attempt in range(8):  # Windows: replace fails while a reader (watcher/UI) holds the target open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    os.replace(tmp, path)


def _read(path: Path) -> dict | None:
    for _ in range(3):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            time.sleep(0.05)
        except OSError:
            return None
    return None


class Job:
    """Handle on one manifest; every mutator rewrites the file."""

    def __init__(self, manifest: dict, path: Path):
        self.m = manifest
        self.path = path
        self._control_owned: set[str] = set()  # control fields this write is deliberately changing

    # -- control -----------------------------------------------------------------------------
    def set_control(self, **fields) -> None:
        """Write a control field (e.g. pause_requested) that must not be merged back from disk."""
        self.m.update(fields)
        self._control_owned = set(fields)
        self._flush()

    def pause_requested(self) -> bool:
        disk = _read(self.path) if self.path.is_file() else None
        return bool((disk or self.m).get("pause_requested"))

    # -- construction -------------------------------------------------------------------------
    @classmethod
    def start(cls, kind: str, label: str, *, uses_api: bool, source: str = "cli",
              argv: list[str] | None = None, condition: dict | None = None,
              floor: str | None = None, start: str | None = None, end: str | None = None,
              checkpoint: int | None = None, model: str | None = None, preset: str | None = None,
              mode: str | None = None, status: str = "running", parent_id: str | None = None,
              job_id: str | None = None) -> "Job":
        pid = os.getpid()
        job_id = job_id or new_job_id(kind)
        m = {
            "job_id": job_id, "kind": kind, "label": label, "status": status, "source": source,
            "uses_api": bool(uses_api), "parent_id": parent_id,
            "pid": pid, "pid_create_time": _proc_create_time(pid),
            "argv": argv if argv is not None else sys.argv, "cwd": os.getcwd(),
            "started_at": _now(), "updated_at": _now(), "finished_at": None,
            "floor": floor, "start": start, "end": end, "checkpoint": checkpoint,
            "model": model, "preset": preset, "mode": mode,
            "condition": condition or {},
            "run_logs": [], "current_run_log": None,
            "progress": {}, "result": None, "error": None,
        }
        job = cls(m, JOBS_DIR / f"{job_id}.json")
        job._flush()
        return job

    @classmethod
    def load(cls, job_id: str) -> "Job | None":
        path = JOBS_DIR / f"{Path(job_id).name}.json"
        m = _read(path) if path.is_file() else None
        return cls(m, path) if m else None

    # -- mutation -----------------------------------------------------------------------------
    def _flush(self) -> None:
        self.m["updated_at"] = _now()
        try:
            disk = _read(self.path) if self.path.is_file() else None
            if disk:
                for k in _CONTROL_FIELDS:
                    if k in disk and k not in self._control_owned:
                        self.m[k] = disk[k]
            self._control_owned = set()
            _write_atomic(self.path, self.m)
        except OSError as e:  # manifests are telemetry — never fail the experiment over them
            print(f"[jobs] manifest write failed for {self.path.name}: {e}", flush=True)

    def update(self, **fields) -> None:
        self.m.update(fields)
        self._flush()

    def progress(self, **fields) -> None:
        self.m.setdefault("progress", {}).update(fields)
        self._flush()

    def set_run_log(self, name: str | None) -> None:
        if name and name not in self.m["run_logs"]:
            self.m["run_logs"].append(name)
        self.m["current_run_log"] = name
        self._flush()

    def adopt_pid(self, pid: int) -> None:
        """Point the manifest at a child process (queue runners hand off to run_reliability.py)."""
        self.m["pid"] = pid
        self.m["pid_create_time"] = _proc_create_time(pid)
        self._flush()

    def finish(self, status: str = "done", result: dict | None = None, error: str | None = None) -> None:
        self.m["status"] = status
        self.m["finished_at"] = _now()
        if result is not None:
            self.m["result"] = result
        if error is not None:
            self.m["error"] = error
        self._flush()

    @property
    def job_id(self) -> str:
        return self.m["job_id"]


# -- queries ----------------------------------------------------------------------------------

def list_jobs(limit: int | None = None, active_only: bool = False) -> list[dict]:
    mark_dead_jobs()
    out: list[dict] = []
    if JOBS_DIR.is_dir():
        for p in JOBS_DIR.glob("*.json"):
            m = _read(p)
            if m:
                out.append(m)
    out.sort(key=lambda m: (m.get("started_at") or "", m.get("job_id") or ""), reverse=True)
    if active_only:
        out = [m for m in out if m.get("status") in _ACTIVE]
    return out[:limit] if limit else out


def mark_dead_jobs() -> list[dict]:
    """Jobs whose process vanished while status was still active → failed(process_exited)."""
    changed: list[dict] = []
    if not JOBS_DIR.is_dir():
        return changed
    for p in JOBS_DIR.glob("*.json"):
        m = _read(p)
        if not m or m.get("status") not in _ACTIVE:
            continue
        if pid_alive(m.get("pid"), m.get("pid_create_time")):
            continue
        m["status"] = "failed"
        m["error"] = m.get("error") or "process_exited"
        m["finished_at"] = _now()
        m["updated_at"] = _now()
        _write_atomic(p, m)
        changed.append(m)
    return changed


def api_busy(exclude_job_id: str | None = None) -> list[dict]:
    """Running (or paused) jobs that talk to the LLM API."""
    return [m for m in list_jobs(active_only=True)
            if m.get("uses_api") and m.get("status") in ("running", "paused") and m.get("job_id") != exclude_job_id]


def exclusive_api() -> bool:
    """Refuse to start a second API job? Off by default (2026-09-23: concurrent jobs are allowed);
    set MOTA_EXCLUSIVE_API=1 to restore the hard guard (e.g. on the basic KISSKI tier)."""
    return os.environ.get("MOTA_EXCLUSIVE_API", "").lower() in ("1", "true", "yes")


def pause_gate(job: "Job | None", should_stop=None, poll: float = 0.5, on_state=None) -> None:
    """Block while the job's manifest asks for a pause. Call between turns from the owning process.

    ``should_stop`` (callable) or a killed/stopped status on disk ends the wait early. ``on_state``
    (callable(str)) is told 'paused' / 'running' so the caller can emit UI events.
    """
    if job is None or not job.pause_requested():
        return
    job.m["status"] = "paused"
    job.m["paused_at"] = _now()
    job._flush()
    if on_state:
        on_state("paused")
    while True:
        disk = _read(job.path) if job.path.is_file() else None
        if not disk or not disk.get("pause_requested") or disk.get("status") in ("killed", "stopped", "failed"):
            break
        if should_stop and should_stop():
            break
        time.sleep(poll)
    if disk and disk.get("status") not in ("running", "paused"):
        job.m["status"] = disk["status"]  # killed/stopped while paused: keep the controller's verdict
    if job.m.get("status") == "paused":
        job.m["status"] = "running"
        job.m["paused_at"] = None
        job._flush()
    if on_state:
        on_state(job.m.get("status", "running"))


def request_pause(job_id: str, paused: bool) -> dict | None:
    """Controller side: set/clear pause_requested on an active job. Returns the manifest or None."""
    job = Job.load(job_id)
    if job is None or job.m.get("status") not in _ACTIVE:
        return None
    job.set_control(pause_requested=bool(paused))
    return job.m


def kill_job(job_id: str) -> bool:
    job = Job.load(job_id)
    if job is None:
        return False
    pid = job.m.get("pid")
    killed = False
    if pid and pid != os.getpid() and pid_alive(pid, job.m.get("pid_create_time")):
        try:
            proc = psutil.Process(pid)
            for child in proc.children(recursive=True):
                child.terminate()
            proc.terminate()
            psutil.wait_procs([proc], timeout=5)
            if proc.is_running():
                proc.kill()
            killed = True
        except psutil.Error:
            pass
    job.finish("killed", error="killed from dashboard")
    return killed or pid == os.getpid()
