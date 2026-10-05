"""Thesis experiment catalog: what was run, what it gave, and a button to re-run it with your own API key."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import procs
from ...harness import catalog as C
from ...harness import reliability as H

router = APIRouter()
_ID = re.compile(r"^[a-z0-9-]{1,40}$")


def _result(label: str) -> dict | None:
    p = H.OUT_DIR / f"{label}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    a = d.get("aggregate") or {}
    return {"label": label, "n": a.get("n"), "successes": a.get("successes"), "ci": a.get("success_ci95"),
            "hp_ratio": a.get("hp_ratio_mean"), "died": a.get("died"), "floors_max": a.get("floors_reached_max"),
            "updated": d.get("updated")}


def _reruns(label: str) -> list[dict]:
    out = []
    for p in sorted(H.OUT_DIR.glob(f"rerun_*_{label}.json")):
        r = _result(p.stem)
        if r:
            out.append(r)
    return out


async def api_catalog(request: Request):
    experiments, env = C.registry()
    entries = []
    for e in C.CATALOG:
        cells = []
        for code in e.get("codes", []):
            d = C.describe(code, experiments, env)
            d.pop("args", None)
            d["env"] = {k: v for k, v in d["env"].items() if "KEY" not in k}
            d["thesis"] = _result(d["label"])
            d["reruns"] = _reruns(d["label"])
            cells.append(d)
        entries.append({k: e[k] for k in ("group", "section", "id", "title", "what")} |
                       {"cells": cells, "script": e.get("script")})
    return JSONResponse({"entries": entries})


async def api_catalog_run(request: Request):
    data = await request.json()
    ids = [i for i in (data.get("ids") or []) if isinstance(i, str) and _ID.match(i)]
    known = {e["id"] for e in C.CATALOG}
    ids = [i for i in ids if i in known]
    if not ids:
        return JSONResponse({"error": "no catalog entries selected"}, status_code=400)
    from .settings import _summary
    if not _summary()["api_key"]["configured"]:
        return JSONResponse({"error": "no API key configured (Settings)"}, status_code=400)
    argv = ["scripts/run_catalog.py", "--ids", *ids]
    if data.get("repeats"):
        argv += ["--repeats", str(max(1, min(20, int(data["repeats"]))))]
    rec = procs.start("catalog", f"re-run: {', '.join(ids)}", argv)
    return JSONResponse(rec)


async def api_procs(request: Request):
    return JSONResponse(procs.listing(request.query_params.get("kind")))


async def api_proc_stop(request: Request):
    data = await request.json()
    ok = procs.stop(int(data.get("pid", 0)))
    return JSONResponse({"stopped": ok}, status_code=200 if ok else 404)


router.add_api_route("/api/catalog", api_catalog, methods=["GET"])
router.add_api_route("/api/catalog/run", api_catalog_run, methods=["POST"])
router.add_api_route("/api/procs", api_procs, methods=["GET"])
router.add_api_route("/api/procs/stop", api_proc_stop, methods=["POST"])
