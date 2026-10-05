"""
Dashboard API regression tests — heuristic only, no network.

Pins the route contract of the split routers (mota/dashboard/api/*) and the heuristic
baselines that every rework must preserve (simple 0.3712, complex 0.3269, MT3 1.0,
MT4 0.5283, tower MT0->MT23w reaches MT8). Logs and results go to a temp dir.

Run: python -m mota.tests.test_dashboard_api
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

_TMP = Path(tempfile.mkdtemp(prefix="mota_dash_test_"))
os.environ["MOTA_LOGS_DIR"] = str(_TMP / "logs")
os.environ["MOTA_RESULTS_DIR"] = str(_TMP / "results")
for _k in ("MOTA_DISABLE_OVERRIDES", "MOTA_DISABLE_STRUCTURED_OUTPUT", "LOOKAHEAD_DEPTH"):
    os.environ.pop(_k, None)

from fastapi.testclient import TestClient  # noqa: E402
from mota.dashboard.server import app  # noqa: E402

# Heuristic baselines (2026-09-23, engine with shop first-contact fix).
BASELINES = {
    "simple": {"total": 0.3712, "final_hp": 443, "steps": 36, "success": False},
    "complex": {"total": 0.3236, "final_hp": 190, "steps": 31, "success": False},  # 0.3269 with the pre-2026-09-29 HP-22 reference
    "mota-floor:MT3": {"total": 1.0, "final_hp": 448, "steps": 33, "success": True},
    "special-floor:MT4": {"total": 0.5283, "final_hp": 230, "steps": 12, "success": False},
}
TOWER_MAX_FLOOR = "MT8"

PASSED = FAILED = 0
client = TestClient(app)


def check(label, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK  {label}")
    else:
        FAILED += 1
        print(f"  FAIL {label} {extra}")


def sse_events(resp) -> list[dict]:
    out = []
    for frame in resp.text.split("\n\n"):
        frame = frame.strip()
        if frame.startswith("data: "):
            out.append(json.loads(frame[6:]))
    return out


print("\n--- read-only routes ---")
r = client.get("/api/floors")
check("/api/floors 200 + simple/complex present", r.status_code == 200 and {f["id"] for f in r.json()} >= {"simple", "complex"})
r = client.get("/api/models")
check("/api/models has task_presets", r.status_code == 200 and "task_presets" in r.json())
r = client.get("/api/checkpoints")
check("/api/checkpoints 8 segments", r.status_code == 200 and len(r.json()) == 8 and r.json()[1]["floor"] == "MT5")
r = client.get("/api/floor-sequence")
check("/api/floor-sequence starts MT0 and has MT23w", r.json()["floor_ids"][0] == "MT0" and "MT23w" in r.json()["floor_ids"])
r = client.get("/api/map?floor=simple")
m = r.json()
check("/api/map simple 11x11 grid + hero", m["width"] == 11 and len(m["grid"]) == 11 and "hero" in m)
r = client.get("/api/seed-prompt?floor=simple")
check("/api/seed-prompt returns prompt", r.status_code == 200 and len(r.json().get("prompt", "")) > 100)
r = client.get("/api/prompt/versions")
check("/api/prompt/versions 200", r.status_code == 200 and "versions" in r.json())
r = client.get("/api/gepa/runs")
check("/api/gepa/runs lists runs", r.status_code == 200 and isinstance(r.json()["runs"], list))
r = client.get("/api/gepa/study")
check("/api/gepa/study 200", r.status_code == 200 and "studies" in r.json())
r = client.get("/api/gepa/run?label=../../x")
check("/api/gepa/run rejects path labels", r.status_code == 404)
r = client.get("/api/reliability/results")
check("/api/reliability/results list (empty tmp)", r.status_code == 200 and isinstance(r.json(), list))
r = client.get("/api/logs?mode=all")
check("/api/logs empty tmp", r.status_code == 200 and r.json()["runs"] == [])
r = client.get("/api/single-floors")
g = {x["group"]: x["floors"] for x in r.json()["groups"]}
check("/api/single-floors: reference + hand + gen", {"simple", "complex"} <= {f["id"] for f in g["reference"]}
      and len(g.get("hand", [])) == 4 and len(g.get("gen", [])) >= 5)
r = client.get("/api/map?floor=hand01")
check("/api/map resolves hand01 by name", r.status_code == 200 and r.json()["width"] > 0)
r = client.get("/api/catalog")
cat = r.json()["entries"]
check("/api/catalog lists thesis experiments with cells", len(cat) >= 10 and all("id" in e for e in cat)
      and any(c["code"] == "G1" for e in cat for c in e["cells"]))
r = client.post("/api/catalog/run", json={"ids": ["../evil"]})
check("/api/catalog/run rejects unknown ids", r.status_code == 400)
r = client.get("/api/thesis-results")
rows = r.json().get("rows", [])
t62 = next((x for x in rows if x["result"].startswith("Table 6.2, single-floor")), None)
check("/api/thesis-results follows Table F.4 (Table 6.2 has 28 result files)", len(rows) >= 30 and t62 and len(t62["items"]) == 28)
r = client.get("/api/thesis-results/file", params={"path": "results/reliability/simple_qwen3.5-397b_canon.json"})
check("/api/thesis-results/file lists episodes with their run logs", r.status_code == 200 and len(r.json()["episodes"]) == 5
      and all(e["run_log"] for e in r.json()["episodes"]))
r = client.get("/api/thesis-results/file", params={"path": "results/../mota/paths.py"})
check("/api/thesis-results/file rejects paths outside results/", r.status_code == 404)
r = client.get("/api/settings")
s = r.json()["api_key"]
check("/api/settings never returns the key", set(s) == {"configured", "source", "hint"} and len(s["hint"]) <= 5)
r = client.post("/api/settings/api-key", json={"key": "has space"})
check("/api/settings/api-key rejects malformed key", r.status_code == 400)
r = client.post("/api/settings/api-key", json={"key": "k" * 20, "base_url": "http://evil.example"})
check("/api/settings/api-key rejects non-https base_url", r.status_code == 400)
for gone in ("/api/benchmarks", "/api/gepa/status"):
    check(f"{gone} removed", client.get(gone).status_code in (404, 405) or client.get(gone).headers.get("content-type", "").startswith("text/html"))

print("\n--- static serving ---")
r = client.get("/%2e%2e/server.py")
check("static traversal blocked", b"create_app" not in r.content)
r = client.get("/")
check("/ serves web build or 503 hint", r.status_code in (200, 503))
if r.status_code == 200:
    r2 = client.get("/play/")
    check("/play/ SPA route", r2.status_code == 200 and b"<html" in r2.content[:200].lower())

print("\n--- heuristic evaluation stream (baselines) ---")
for floor, exp in BASELINES.items():
    r = client.post("/api/evaluate/stream", json={"floor": floor, "mode": "heuristic", "prompt": None, "enable_logging": True})
    evs = sse_events(r)
    types = [e["type"] for e in evs]
    res = next((e for e in evs if e["type"] == "result"), None)
    check(f"{floor}: stream ends with log_saved + done", types[-2:] == ["log_saved", "done"], str(types[-3:]))
    check(f"{floor}: has start + turn events", "start" in types and types.count("turn") >= 5)
    if res is None:
        check(f"{floor}: result event", False, "missing")
        continue
    d = res.get("details", {})
    check(f"{floor}: total {exp['total']}", round(res["total"], 4) == exp["total"], f"got {res['total']}")
    check(f"{floor}: final_hp {exp['final_hp']}", d.get("final_hp") == exp["final_hp"], f"got {d.get('final_hp')}")
    check(f"{floor}: steps {exp['steps']}", d.get("steps") == exp["steps"], f"got {d.get('steps')}")
    check(f"{floor}: two-tier success={exp['success']}", res.get("success") is exp["success"])
    check(f"{floor}: two-tier keys present", {"hp_ratio", "goal_score"} <= set(res))
    logs = list((_TMP / "logs" / "runs").glob("*.json"))
    check(f"{floor}: run log written to MOTA_LOGS_DIR", any(p.name.endswith("_heuristic.json") for p in logs))

print("\n--- logs routes on the produced logs ---")
r = client.get("/api/logs?mode=heuristic")
runs = r.json()["runs"]
check("/api/logs lists heuristic runs", len(runs) >= 4)
first = runs[0]["filename"]
r = client.get(f"/api/log/detail?kind=run&id={first}")
check("/api/log/detail returns payload with turns + result",
      r.status_code == 200 and {"turns", "result"} <= set(r.json().get("payload", {})))
r = client.get(f"/api/log/download?id={first}")
check("/api/log/download json", r.status_code == 200 and r.headers["content-type"].startswith("application/json"))
r = client.get("/api/log/download?id=../server.py")
check("/api/log/download traversal rejected", r.status_code in (400, 404))
r = client.get(f"/api/logs/compare?a={runs[0]['filename']}&b={runs[1]['filename']}")
check("/api/logs/compare 200", r.status_code == 200)

print("\n--- tower heuristic stream (MT0->MT2) ---")
r = client.post("/api/evaluate/multi-floor", json={"start_floor": "MT0", "end_floor": "MT2", "mode": "heuristic",
                                                    "prompt": None, "enable_logging": False, "max_turns": 200})
evs = sse_events(r)
types = [e["type"] for e in evs]
res = next((e for e in evs if e["type"] == "result"), None)
check("tower: floor_change events emitted", types.count("floor_change") >= 1)
check("tower: result + done", res is not None and types[-1] == "done")
if res:
    check("tower: reached MT2", res.get("goal_reached") is True or res.get("max_floor_id") == "MT2", str({k: res.get(k) for k in ('goal_reached', 'max_floor_id')}))

print("\n--- reliability harness (heuristic N=1, tmp results) ---")
r = client.post("/api/reliability/stream", json={"floor": "simple", "prompt": None, "repeats": 1, "label": "_test_simple_h"})
evs = sse_events(r)
types = [e["type"] for e in evs]
done = next((e for e in evs if e["type"] == "done"), None)
check("reliability: start/run/done", types[:2] == ["start", "run"] and done is not None, str(types))
out_json = _TMP / "results" / "reliability" / "_test_simple_h.json"
check("reliability: result JSON written under MOTA_RESULTS_DIR", out_json.exists())
if out_json.exists():
    d = json.loads(out_json.read_text(encoding="utf-8"))
    check("reliability: record score = baseline", round(d["runs"][0]["score"], 4) == BASELINES["simple"]["total"])
    check("reliability: config.source=dashboard", d["config"].get("source") == "dashboard")
check("reliability: SUMMARY.md regenerated", (_TMP / "results" / "reliability" / "SUMMARY.md").exists())
r = client.get("/api/reliability/results")
check("/api/reliability/results ignores _-prefixed labels", all(not x["label"].startswith("_") for x in r.json()))

print("\n--- manual play ---")
r = client.post("/api/manual/start", json={"floor": "simple", "enable_logging": False})
p = r.json()
check("manual/start returns actions", r.status_code == 200 and len(p.get("actions", [])) > 0)
aid = p["actions"][0]["action_id"] if p.get("actions") else None
if aid is not None:
    r = client.post("/api/manual/action", json={"action_id": aid})
    check("manual/action applies", r.status_code == 200 and "actions" in r.json())
r = client.post("/api/manual/stop", json={})
check("manual/stop", r.status_code == 200 and r.json()["status"] == "stopped")

print("\n--- plan-mode switches reach the env and the label; latency, projects ---")
from mota.dashboard.api.reliability import condition_from_body as _cfb  # noqa: E402
from mota.dashboard.api.common import _apply_experiment_env as _aee  # noqa: E402
c = _cfb({"floor": "hand02", "prompt": "x", "plan_steps": 3, "final_stack": True})
check("condition_from_body carries plan_steps/final_stack", c.plan_steps == 3 and c.final_stack and not c.one_shot)
_aee({"one_shot": True, "final_stack": True})
check("one_shot -> MOTA_PLAN_STEPS=60 + NO_REPLAN; final stack env", os.environ.get("MOTA_PLAN_STEPS") == "60"
      and os.environ.get("MOTA_PLAN_NO_REPLAN") == "1" and os.environ.get("CONVERSATION_HISTORY_TURNS") == "0")
_aee({})
check("a plain run clears the previous run's plan/stack env", "MOTA_PLAN_STEPS" not in os.environ
      and "CONVERSATION_HISTORY_TURNS" not in os.environ)
from mota.optimizer.evaluator import _build_user_msg as _bum  # noqa: E402
os.environ["MOTA_PLAN_STEPS"] = "60"
check("long plans ask for as many actions as the model can", "as many of the fight" in _bum("s", "a"))
os.environ["MOTA_PLAN_WORDING"] = "floor"
check("MOTA_PLAN_WORDING=floor restores the round-7 whole-floor wording", "rest of this floor" in _bum("s", "a"))
for _k in ("MOTA_PLAN_STEPS", "MOTA_PLAN_WORDING"):
    os.environ.pop(_k)
r = client.get("/api/latency")
check("/api/latency returns rows", r.status_code == 200 and "rows" in r.json() and "n_logs" in r.json())
r = client.get("/api/projects")
pr = {x["id"]: x for x in r.json()}
check("/api/projects lists 24 (27 floors)", pr["24"]["floors"] == 27 and pr["24"]["engine_default"])
if "51" in pr:  # optional: data/games/51/project is not distributed
    check("/api/projects lists 51 (51 floors)", pr["51"]["floors"] == 51)
    r = client.get("/api/projects/51/floors")
    check("/api/projects/51/floors inventories scripted events", r.status_code == 200 and len(r.json()["floors"]) == 51
          and "scripted_events" in r.json()["floors"][0])
r = client.get("/api/jobs")
check("/api/jobs shows ui-eval + reliability jobs", r.status_code == 200
      and {j["kind"] for j in r.json()["jobs"]} >= {"ui-eval", "reliability"})

if "--tower-full" in sys.argv:
    print("\n--- full tower heuristic MT0->MT23w (slow) ---")
    r = client.post("/api/evaluate/multi-floor", json={"start_floor": "MT0", "end_floor": "MT23w", "mode": "heuristic",
                                                        "prompt": None, "enable_logging": False, "max_turns": 1500})
    res = next((e for e in sse_events(r) if e["type"] == "result"), None)
    check(f"tower full: max floor {TOWER_MAX_FLOOR}", res is not None and res.get("max_floor_id") == TOWER_MAX_FLOOR,
          str(res and res.get("max_floor_id")))

print(f"\nResults: {PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
