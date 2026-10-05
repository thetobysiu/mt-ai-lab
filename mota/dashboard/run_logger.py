"""
Per-run structured logging for academic reproducibility.

Each evaluation run is saved as a timestamped JSON file in logs/.
GEPA optimization sessions group all iterations under one directory.
"""
from __future__ import annotations
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

# MOTA_LOGS_DIR lets tests and alternate deployments redirect logs/ without touching code.
_LOGS_DIR = Path(os.environ.get("MOTA_LOGS_DIR") or Path(__file__).resolve().parents[2] / "logs")


def _ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)


def _timestamp_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _normalize_floor_id(floor_id: str) -> str:
    """Collapse path-based floor IDs to a short stable label for saved logs."""
    normalized = str(floor_id or "").replace("\\", "/")
    if "/" in normalized:
        return normalized.split("/")[-1]
    return normalized


class RunLogger:
    """Accumulates events for a single evaluation run and saves to disk."""

    def __init__(self, floor_id: str, mode: str, prompt: str | None = None,
                 session_dir: Path | None = None, task_model: str | None = None,
                 task_mode: str | None = None, task_preset: str | None = None,
                 job_id: str | None = None):
        self.floor_id = _normalize_floor_id(floor_id)
        self.mode = mode  # "heuristic", "llm", "gepa"
        self.prompt = prompt
        self.task_model = task_model
        self.task_mode = task_mode
        self.task_preset = task_preset
        self.job_id = job_id or os.environ.get("MOTA_JOB_ID") or None
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.turns: list[dict] = []
        self.result: dict | None = None
        self.runtime_prompt: str | None = None
        self._session_dir = session_dir
        self._path: Path | None = None  # fixed once the first save() happens

    def add_event(self, event: dict):
        """Record a streaming event."""
        if event is None:
            return
        # Streaming reasoning deltas are transient UI events; the full text arrives in
        # thinking_result / the turn event. Persisting them made tower logs > 200 MB
        # (670K events) and the per-turn flush rewrite proportionally slow.
        if event["type"] == "thinking_chunk":
            return
        event_copy = {**event, "_ts": time.time()}
        if event["type"] in ("result", "bfs_result", "manual_result", "stopped"):
            self.result = event_copy
        elif event["type"] == "start":
            # Capture the runtime system prompt (includes floor map)
            if event.get("runtime_system_prompt"):
                self.runtime_prompt = event["runtime_system_prompt"]
            self.turns.append(event_copy)
        else:
            self.turns.append(event_copy)

    def save(self) -> Path:
        """Write the run log to disk and return the file path.

        Repeated calls overwrite the same file, so long episodes can flush
        progress after every turn without producing duplicate logs."""
        if self._path is not None:
            path = self._path
            out_dir = path.parent
        else:
            ts = _timestamp_token()
            if self._session_dir:
                out_dir = self._session_dir
            else:
                out_dir = _LOGS_DIR / "runs"
            _ensure_dir(out_dir)

            # Sanitize floor_id for filename (handle paths and special chars)
            safe_floor_id = self.floor_id.replace("\\", "/").split("/")[-1]
            for char in '<>:"/\\|?*':
                safe_floor_id = safe_floor_id.replace(char, "_")

            filename = f"{ts}_{safe_floor_id}_{self.mode}.json"
            path = out_dir / filename
            # Two lanes started together got the same token (Windows clock tick) and wrote one
            # file (2026-09-28). Claim the name exclusively; on a clash bump the microseconds.
            for _ in range(1000):
                try:
                    with open(path, "x", encoding="utf-8"):
                        pass
                    break
                except FileExistsError:
                    d, t, us = ts.split("_")
                    ts = f"{d}_{t}_{(int(us) + 1) % 1000000:06d}"
                    path = out_dir / f"{ts}_{safe_floor_id}_{self.mode}.json"
            self._path = path

        payload = {
            "floor_id": self.floor_id,
            "mode": self.mode,
            "prompt": self.prompt,
            "runtime_prompt": self.runtime_prompt,
            "task_model": self.task_model,
            "task_mode": self.task_mode,
            "task_preset": self.task_preset,
            "job_id": self.job_id,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "turns": self.turns,
            "result": self.result,
        }
        try:
            # tmp + replace: a concurrent reader (JobWatcher) sees either the old or the new file, never a torn one
            tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            for attempt in range(8):  # Windows: replace fails while a reader holds the target open
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if attempt == 7:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        except Exception as e:
            print(f"ERROR: Failed to save run log to {path}: {e}")
            raise
        return path

    @property
    def path(self) -> Path | None:
        return self._path


class GEPASessionLogger:
    """Groups all GEPA iterations under a single session directory."""

    def __init__(
        self,
        floor_id: str,
        seed_prompt: str,
        max_calls: int,
        task_model: str | None = None,
        task_mode: str | None = None,
        task_preset: str | None = None,
        reflection_model: str | None = None,
    ):
        ts = _timestamp_token()
        # floor_id may be a full filesystem path (AI test floors); reduce it to a
        # filesystem-safe token for the session directory name.
        safe_floor = Path(str(floor_id)).name or "floor"
        safe_floor = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", safe_floor)
        self.session_dir = _LOGS_DIR / "gepa" / f"{ts}_{safe_floor}"
        _ensure_dir(self.session_dir)

        self.floor_id = floor_id
        self.seed_prompt = seed_prompt
        self.max_calls = max_calls
        self.task_model = task_model
        self.task_mode = task_mode
        self.task_preset = task_preset
        self.reflection_model = reflection_model
        self.iterations: list[dict] = []

        # Save session metadata
        meta = {
            "floor_id": floor_id,
            "seed_prompt": seed_prompt,
            "max_calls": max_calls,
            "task_model": task_model,
            "task_mode": task_mode,
            "task_preset": task_preset,
            "reflection_model": reflection_model,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.session_dir / "session.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def log_iteration(self, iteration: int, prompt: str, score: float, details: dict):
        """Log one GEPA iteration (mutation + evaluation)."""
        entry = {
            "iteration": iteration,
            "prompt": prompt,
            "score": score,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.iterations.append(entry)

        # Save individual iteration file
        path = self.session_dir / f"iter_{iteration:03d}.json"
        path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

    def finalize(self, best_prompt: str, best_score: float):
        """Write the final summary."""
        summary = {
            "floor_id": self.floor_id,
            "seed_prompt": self.seed_prompt,
            "best_prompt": best_prompt,
            "best_score": best_score,
            "task_model": self.task_model,
            "task_mode": self.task_mode,
            "task_preset": self.task_preset,
            "reflection_model": self.reflection_model,
            "total_iterations": len(self.iterations),
            "all_scores": [it["score"] for it in self.iterations],
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.session_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
