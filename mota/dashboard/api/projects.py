"""Game-data projects: which HTML5-mota project roots are available and what floors they contain.

The 24-layer project is the canonical, hard-coded engine data (all recorded baselines). Other
projects (51/project, or any root registered in data/projects.json) are loaded through
mota.game.project.MotaProject when it exists; until then this router only inventories them.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .paths import GEPA_ROOT, PROJECT_ROOT

router = APIRouter()

BUILTIN = {"24": PROJECT_ROOT / "24" / "project", "51": PROJECT_ROOT / "51" / "project"}
REGISTRY = GEPA_ROOT / "data" / "projects.json"
_EVENT_KEYS = ("events", "afterBattle", "afterGetItem", "afterOpenDoor", "firstArrive", "eachArrive")
_NOISE = {"playSound", "sleep", "setText", "vibrate", "animate"}


def registered_projects() -> dict[str, dict]:
    out = {k: {"id": k, "root": str(v), "builtin": True, "engine_default": k == "24"} for k, v in BUILTIN.items() if v.is_dir()}
    if REGISTRY.is_file():
        try:
            for k, root in json.loads(REGISTRY.read_text(encoding="utf-8")).items():
                out[k] = {"id": k, "root": root, "builtin": False, "engine_default": False}
        except Exception:
            pass
    return out


def _floor_ids(root) -> list[str]:
    from ...game.hero_loader import load_floor_sequence
    try:
        return load_floor_sequence(root / "data.js")
    except Exception:
        return sorted(p.stem for p in (root / "floors").glob("*.js"))


def _scripted_events(text: str) -> list[str]:
    """Event types in a floor file that the engine does not model (same walk as scripts/inventory_floor_events.py)."""
    acc: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            t = o.get("type")
            if t and t not in _NOISE:
                acc.append(t)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for key in _EVENT_KEYS:
        pat = r'"%s": (\[.*?\n    \]),\n' if key in ("firstArrive", "eachArrive") else r'"%s": (\{.*?\n    \}),\n'
        m = re.search(pat % key, text, re.S)
        if not m:
            continue
        try:
            walk(json.loads(m.group(1)))
        except json.JSONDecodeError:
            acc.append(f"{key}:unparsed")
    return sorted(set(acc))


async def api_projects(request: Request):
    from pathlib import Path
    out = []
    for pid, meta in registered_projects().items():
        root = Path(meta["root"])
        ids = _floor_ids(root)
        name = None
        try:
            m = re.search(r'"title":\s*"([^"]+)"', (root / "data.js").read_text(encoding="utf-8"))
            name = m.group(1) if m else None
        except Exception:
            pass
        out.append({**meta, "name": name, "floors": len(ids), "floor_ids": ids,
                    "has": {f: (root / f).exists() for f in ("data.js", "enemys.js", "items.js", "maps.js", "floors")}})
    return JSONResponse(out)


async def api_project_floors(request: Request):
    """Per-floor inventory: size, unmodelled scripted events."""
    from pathlib import Path
    pid = request.path_params["project_id"]
    meta = registered_projects().get(pid)
    if not meta:
        return JSONResponse({"error": "unknown project"}, status_code=404)
    root = Path(meta["root"])
    rows = []
    for fid in _floor_ids(root):
        p = root / "floors" / f"{fid}.js"
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        w = re.search(r'"width":\s*(\d+)', text)
        h = re.search(r'"height":\s*(\d+)', text)
        title = re.search(r'"title":\s*"([^"]+)"', text)
        rows.append({"floor_id": fid, "title": title.group(1) if title else fid,
                     "width": int(w.group(1)) if w else None, "height": int(h.group(1)) if h else None,
                     "scripted_events": _scripted_events(text)})
    return JSONResponse({"project": meta, "floors": rows})


router.add_api_route("/api/projects", api_projects, methods=["GET"])
router.add_api_route("/api/projects/{project_id}/floors", api_project_floors, methods=["GET"])
