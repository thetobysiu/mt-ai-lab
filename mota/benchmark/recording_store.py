"""Persistent manual benchmark recordings stored under logs/benchmarks/."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


_BENCHMARKS_DIR = Path(__file__).resolve().parents[2] / "logs" / "benchmarks"
_RECORDINGS_FILE = _BENCHMARKS_DIR / "recordings.json"
_lock = threading.Lock()


def _ensure_dir() -> None:
    _BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)


def _load_db() -> dict:
    if _RECORDINGS_FILE.exists():
        return json.loads(_RECORDINGS_FILE.read_text(encoding="utf-8"))
    return {"next_id": 1, "active_by_floor": {}, "recordings": []}


def _save_db(db: dict) -> None:
    _ensure_dir()
    _RECORDINGS_FILE.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _find_recording(db: dict, recording_id: int) -> dict | None:
    for recording in db["recordings"]:
        if recording["id"] == recording_id:
            return recording
    return None


def list_recordings() -> list[dict]:
    db = _load_db()
    active_by_floor = db.get("active_by_floor", {})
    recordings = []
    for recording in db["recordings"]:
        result = recording.get("result") or {}
        expected = recording.get("expected") or {}
        recordings.append({
            "id": recording["id"],
            "label": recording.get("label") or f"benchmark-{recording['id']}",
            "floor_id": recording.get("floor_id", ""),
            "source": recording.get("source", "manual"),
            "created_at": recording.get("created_at", ""),
            "score": result.get("total"),
            "turn_count": expected.get("turns"),
            "is_active": active_by_floor.get(recording.get("floor_id")) == recording["id"],
        })
    return recordings


def load_recording(recording_id: int) -> dict:
    db = _load_db()
    recording = _find_recording(db, recording_id)
    if recording is None:
        raise ValueError(f"Recording {recording_id} not found")
    return recording


def save_recording(recording: dict, set_active: bool = True) -> int:
    with _lock:
        db = _load_db()
        recording_id = db["next_id"]
        payload = dict(recording)
        payload["id"] = recording_id
        payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        payload.setdefault("label", f"Benchmark {recording_id}")
        db["recordings"].append(payload)
        db["next_id"] = recording_id + 1
        if set_active and payload.get("floor_id"):
            db.setdefault("active_by_floor", {})[payload["floor_id"]] = recording_id
        _save_db(db)
        return recording_id


def set_active(recording_id: int) -> None:
    with _lock:
        db = _load_db()
        recording = _find_recording(db, recording_id)
        if recording is None:
            raise ValueError(f"Recording {recording_id} not found")
        floor_id = recording.get("floor_id")
        if not floor_id:
            raise ValueError(f"Recording {recording_id} has no floor_id")
        db.setdefault("active_by_floor", {})[floor_id] = recording_id
        _save_db(db)


def delete_recording(recording_id: int) -> None:
    with _lock:
        db = _load_db()
        recording = _find_recording(db, recording_id)
        if recording is None:
            raise ValueError(f"Recording {recording_id} not found")
        floor_id = recording.get("floor_id")
        db["recordings"] = [r for r in db["recordings"] if r["id"] != recording_id]
        if floor_id and db.get("active_by_floor", {}).get(floor_id) == recording_id:
            del db["active_by_floor"][floor_id]
        _save_db(db)


def get_active_recording(floor_id: str | None) -> dict | None:
    if not floor_id:
        return None
    db = _load_db()
    recording_id = db.get("active_by_floor", {}).get(floor_id)
    if recording_id is None:
        return None
    return _find_recording(db, recording_id)