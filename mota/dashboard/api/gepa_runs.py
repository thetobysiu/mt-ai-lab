"""GEPA: the runs behind thesis Chapter 5 / §8.20.12, shown as what happened in each iteration.

Two kinds of result file live in results/gepa/gepa_result_<label>.json:
  * constrained (method "constrained-linear-gepa", Sept 2026, the thesis study): per iteration the prompt
    that was evaluated, its episodes, whether it became the best so far, and the teacher's reply that
    proposed the next prompt (validator verdict, diagnosis);
  * historical (April-May 2026, the `gepa` library): seed, best prompt and candidate scores only.
The pre-registered study's paired evaluation lives in results/gepa_study/<label>.json.
New runs start scripts/run_constrained_gepa.py (the thesis method) as a background process.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import procs
from .paths import GEPA_ROOT

router = APIRouter()
GEPA_DIR = GEPA_ROOT / "results" / "gepa"
STUDY_DIR = GEPA_ROOT / "results" / "gepa_study"
_LABEL = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


def _floor_name(f) -> str:
    return Path(str(f)).stem if f else ""


def _load(label: str) -> dict | None:
    if not _LABEL.match(label):
        return None
    p = GEPA_DIR / f"gepa_result_{label}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _kind(d: dict) -> str:
    return "constrained" if d.get("method") == "constrained-linear-gepa" else "historical"


def _diagnosis(resp: str) -> str:
    """The teacher's reasoning before the fenced prompt (its diagnosis of the episodes)."""
    head = (resp or "").split("```")[0].strip()
    return head[:4000]


async def api_gepa_runs(request: Request):
    rows = []
    for p in sorted(GEPA_DIR.glob("gepa_result_*.json")):
        label = p.stem[len("gepa_result_"):]
        if label.startswith("_"):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        kind = _kind(d)
        if kind == "constrained":
            its = d.get("iterations") or []
            floors = [_floor_name(f) for f in (d.get("floors") or [d.get("floor")]) if f] or (
                [f"{d['tower'][0]}→{d['tower'][1]}"] if d.get("tower") else [])
            rows.append({"label": label, "kind": kind, "model": d.get("preset"), "teacher": d.get("reflection_model"),
                         "floors": floors, "seed": d.get("seed_file"), "obs": "bare" if d.get("bare_obs") else "full",
                         "iterations": len(its), "seed_score": its[0]["score"] if its else None,
                         "best_score": d.get("best_score"), "kept_seed": bool(its) and d.get("best_prompt") == its[0].get("prompt"),
                         "started": d.get("started"), "finished": bool(d.get("finished")),
                         "study": (STUDY_DIR / f"{label}.json").exists()})
        else:
            cfg = d.get("config") or {}
            rows.append({"label": label, "kind": kind, "model": cfg.get("task_model"), "teacher": cfg.get("reflection_model"),
                         "floors": [], "seed": "custom" if d.get("seed_was_custom") else "default",
                         "iterations": d.get("num_candidates"), "seed_score": (d.get("all_scores") or [None])[0],
                         "best_score": d.get("best_score"), "started": d.get("timestamp"), "finished": True, "study": False})
    rows.sort(key=lambda r: (r["kind"] != "constrained", str(r.get("started") or "")), reverse=False)
    return JSONResponse({"runs": rows, "active": procs.listing("gepa")})


async def api_gepa_run(request: Request):
    label = request.query_params.get("label", "")
    d = _load(label)
    if d is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    if _kind(d) == "historical":
        return JSONResponse({"label": label, "kind": "historical", "config": d.get("config"), "objective": d.get("objective"),
                             "seed_prompt": d.get("seed_prompt"), "best_prompt": d.get("best_prompt"),
                             "best_score": d.get("best_score"), "scores": d.get("all_scores"),
                             "early_stopped": d.get("early_stopped")})
    its = d.get("iterations") or []
    best = -1.0
    out = []
    for i, it in enumerate(its):
        score = it.get("score")
        new_best = score is not None and score > best
        best = max(best, score if score is not None else best)
        refl = it.get("reflection") or {}
        retry = refl.get("retry") or {}
        out.append({
            "iteration": it.get("iteration", i), "score": score, "new_best": new_best, "best_so_far": best,
            "dropped": bool(it.get("dropped")), "eval_s": it.get("eval_s"),
            "prompt": it.get("prompt", ""), "prev_prompt": its[i - 1].get("prompt", "") if i else "",
            "episodes": [{"floor": _floor_name(r.get("floor")) or r.get("max_floor_id"), "success": r.get("success"),
                          "final_hp": r.get("final_hp"), "objective": r.get("objective"), "run_log": r.get("run_log"),
                          "failure": r.get("failure_reason")} for r in it.get("rollouts") or []],
            "teacher": None if not refl else {
                "seconds": refl.get("s"), "diagnosis": _diagnosis(refl.get("response", "")),
                "violations": refl.get("violations") or [], "retry_violations": retry.get("violations"),
                "accepted": it.get("accepted")},
        })
    study = None
    sp = STUDY_DIR / f"{label}.json"
    if sp.exists():
        study = _study_summary(json.loads(sp.read_text(encoding="utf-8")))
    return JSONResponse({"label": label, "kind": "constrained", "model": d.get("preset"), "teacher": d.get("reflection_model"),
                         "floors": [_floor_name(f) for f in (d.get("floors") or [d.get("floor")]) if f],
                         "tower": d.get("tower"), "seed": d.get("seed_file"), "obs": "bare" if d.get("bare_obs") else "full",
                         "rollouts": d.get("rollouts"), "select": d.get("select"), "rich_trace": d.get("rich_trace"),
                         "env": d.get("env"), "best_score": d.get("best_score"), "best_prompt": d.get("best_prompt"),
                         "iterations": out, "study": study})


def _study_summary(s: dict) -> dict:
    """Kills / episodes and mean goal score per prompt arm, split train/test, plus the per-floor grid."""
    arms: dict = {}
    grid: dict = {}
    for e in s.get("episodes") or []:
        key = (e.get("prompt"), e.get("split"))
        a = arms.setdefault(key, {"prompt": e.get("prompt"), "split": e.get("split"), "n": 0, "kills": 0, "goal": 0.0})
        a["n"] += 1
        a["kills"] += 1 if e.get("success") else 0
        a["goal"] += e.get("goal_score") or 0.0
        cell = grid.setdefault(_floor_name(e.get("floor")), {}).setdefault(e.get("prompt"), [])
        cell.append({"success": e.get("success"), "hp": e.get("final_hp")})
    for a in arms.values():
        a["goal"] = round(a["goal"] / a["n"], 3) if a["n"] else None
    return {"label": s.get("label"), "preset": s.get("preset"), "obs": s.get("obs"), "train": s.get("train"),
            "test": s.get("test"), "repeat": s.get("repeat"), "arms": list(arms.values()), "grid": grid}


async def api_gepa_study(request: Request):
    rows = []
    for p in sorted(STUDY_DIR.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        try:
            rows.append(_study_summary(json.loads(p.read_text(encoding="utf-8"))) | {"file": p.stem})
        except Exception:
            continue
    return JSONResponse({"studies": rows})


async def api_gepa_start(request: Request):
    """Start constrained GEPA (scripts/run_constrained_gepa.py) in the background."""
    data = await request.json()
    label = str(data.get("label") or "").strip()
    if not _LABEL.match(label) or (GEPA_DIR / f"gepa_result_{label}.json").exists():
        return JSONResponse({"error": "choose a new label (letters, digits, _ . -)"}, status_code=400)
    from .settings import _summary
    if not _summary()["api_key"]["configured"]:
        return JSONResponse({"error": "no API key configured (Settings)"}, status_code=400)
    argv = ["scripts/run_constrained_gepa.py", "--label", label, "--preset", str(data.get("preset") or "qwen3.6-35b"),
            "--iterations", str(max(2, min(12, int(data.get("iterations") or 4)))),
            "--rollouts", str(max(1, min(5, int(data.get("rollouts") or 2))))]
    if data.get("tower"):
        argv += ["--tower", str(data.get("start") or "MT0"), str(data.get("end") or "MT23w")]
    else:
        argv += ["--floor", str(data.get("floor") or "simple")]
    if data.get("teacher"):
        argv += ["--reflection-model", str(data["teacher"])]
    env = {"CONVERSATION_HISTORY_TURNS": "0", "MOTA_ORDER_TWO_SIDED": "1", "MOTA_FIGHT_KEY_FLOOD": "1"}
    return JSONResponse(procs.start("gepa", f"GEPA {label}", argv, env))


router.add_api_route("/api/gepa/runs", api_gepa_runs, methods=["GET"])
router.add_api_route("/api/gepa/run", api_gepa_run, methods=["GET"])
router.add_api_route("/api/gepa/study", api_gepa_study, methods=["GET"])
router.add_api_route("/api/gepa/start", api_gepa_start, methods=["POST"])
