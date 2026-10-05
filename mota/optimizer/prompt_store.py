# -*- coding: utf-8 -*-
"""
Versioned prompt store with git-like history.

All prompt versions are stored in logs/prompts/versions.json.
Each version has a parent, label, source, and optional score metadata.
"""
from __future__ import annotations

import difflib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "logs" / "prompts"
_VERSIONS_FILE = _PROMPTS_DIR / "versions.json"
_lock = threading.Lock()


def _ensure_dir():
    _PROMPTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_db() -> dict:
    """Load the versions database, or create a fresh one."""
    if _VERSIONS_FILE.exists():
        return json.loads(_VERSIONS_FILE.read_text(encoding="utf-8"))
    return {"next_id": 1, "current_id": None, "versions": []}


def _save_db(db: dict):
    _ensure_dir()
    _VERSIONS_FILE.write_text(
        json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _find_version(db: dict, version_id: int) -> dict | None:
    for v in db["versions"]:
        if v["id"] == version_id:
            return v
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_from_seed():
    """Ensure at least v1 (seed prompt) exists. Safe to call repeatedly."""
    with _lock:
        db = _load_db()
        if db["versions"]:
            return  # Already initialized
        from .seed_prompt import SEED_PROMPT

        db["versions"].append({
            "id": 1,
            "parent_id": None,
            "text": SEED_PROMPT,
            "label": "Initial seed prompt",
            "source": "seed",
            "floor_id": None,
            "scores": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        db["next_id"] = 2
        db["current_id"] = 1
        _save_db(db)


def save_version(
    text: str,
    label: str = "",
    source: str = "manual",
    parent_id: int | None = None,
    floor_id: str | None = None,
    score: float | None = None,
) -> int:
    """Save a new prompt version. Returns the new version ID."""
    with _lock:
        db = _load_db()
        vid = db["next_id"]
        # If no explicit parent, inherit from current
        if parent_id is None:
            parent_id = db["current_id"]
        scores = {}
        if score is not None and floor_id:
            scores[floor_id] = score
        db["versions"].append({
            "id": vid,
            "parent_id": parent_id,
            "text": text,
            "label": label or f"v{vid}",
            "source": source,
            "floor_id": floor_id,
            "scores": scores,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        db["next_id"] = vid + 1
        db["current_id"] = vid
        _save_db(db)
        return vid


def update_score(version_id: int, floor_id: str, score: float):
    """Attach or update a score for a version on a specific floor."""
    with _lock:
        db = _load_db()
        v = _find_version(db, version_id)
        if v is None:
            raise ValueError(f"Version {version_id} not found")
        v["scores"][floor_id] = score
        _save_db(db)


def list_versions() -> list[dict]:
    """Return all versions (metadata only, text truncated)."""
    db = _load_db()
    result = []
    for v in db["versions"]:
        scores = v.get("scores", {})
        result.append({
            "id": v["id"],
            "parent_id": v["parent_id"],
            "label": v["label"],
            "source": v["source"],
            "floor_id": v.get("floor_id"),
            "scores": scores,
            "best_score": max(scores.values()) if scores else None,
            "is_current": v["id"] == db.get("current_id"),
            "text_length": len(v["text"]),
            "created_at": v["created_at"],
        })
    return result


def load_version(version_id: int) -> dict:
    """Return full version data including text."""
    db = _load_db()
    v = _find_version(db, version_id)
    if v is None:
        raise ValueError(f"Version {version_id} not found")
    return dict(v)


def get_current() -> dict:
    """Return the current (active) prompt version with full text."""
    db = _load_db()
    if db["current_id"] is None:
        init_from_seed()
        db = _load_db()
    v = _find_version(db, db["current_id"])
    if v is None:
        raise ValueError("Current version missing from store")
    return dict(v)


def get_current_text() -> str:
    """Return just the text of the current prompt version."""
    return get_current()["text"]


def set_current(version_id: int):
    """Pin a version as the active prompt."""
    with _lock:
        db = _load_db()
        if _find_version(db, version_id) is None:
            raise ValueError(f"Version {version_id} not found")
        db["current_id"] = version_id
        _save_db(db)


def diff_versions(id_a: int, id_b: int) -> dict:
    """Compute a line-level unified diff between two versions."""
    db = _load_db()
    va = _find_version(db, id_a)
    vb = _find_version(db, id_b)
    if va is None or vb is None:
        raise ValueError(f"Version(s) not found: {id_a}, {id_b}")
    lines_a = va["text"].splitlines(keepends=True)
    lines_b = vb["text"].splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        lines_a, lines_b,
        fromfile=f"v{id_a} ({va['label']})",
        tofile=f"v{id_b} ({vb['label']})",
        lineterm="",
    ))
    return {
        "from_id": id_a,
        "to_id": id_b,
        "from_label": va["label"],
        "to_label": vb["label"],
        "diff_lines": diff,
        "diff_text": "\n".join(diff),
    }


def delete_version(version_id: int):
    """Delete a version. Cannot delete the current version."""
    with _lock:
        db = _load_db()
        if db["current_id"] == version_id:
            raise ValueError("Cannot delete the current active version")
        db["versions"] = [v for v in db["versions"] if v["id"] != version_id]
        _save_db(db)
