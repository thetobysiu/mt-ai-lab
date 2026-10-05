"""
Job registry + event bus + WebSocket tests — heuristic only, no network.

Covers: manifest lifecycle, dead-pid reaping, the one-API-job guard (409 api_busy), the
JobWatcher tailing a CLI-style run log into `run:<job_id>`, live mirroring of a dashboard-
launched heuristic run, and the run_reliability.py CLI writing a manifest end-to-end.

Run: python -m mota.tests.test_jobs
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

_TMP = Path(tempfile.mkdtemp(prefix="mota_jobs_test_"))
os.environ["MOTA_LOGS_DIR"] = str(_TMP / "logs")
os.environ["MOTA_RESULTS_DIR"] = str(_TMP / "results")
os.environ["MOTA_EXCLUSIVE_API"] = "1"  # the 409 guard is opt-in since 2026-09-23; test it explicitly

from fastapi.testclient import TestClient  # noqa: E402
from mota.dashboard import jobs as J  # noqa: E402
from mota.dashboard.server import app  # noqa: E402
from mota.dashboard.watcher import watcher  # noqa: E402

watcher.interval = 0.2  # fast ticks for the test
PASSED = FAILED = 0


def check(label, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK  {label}")
    else:
        FAILED += 1
        print(f"  FAIL {label} {extra}")


def recv_until(ws, pred, timeout=8.0) -> list[dict]:
    """Collect ws messages until pred(msg) is True or timeout; returns everything seen."""
    seen = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msg = ws.receive_json()
        except Exception:
            break
        seen.append(msg)
        if pred(msg):
            break
    return seen


print("\n--- manifest lifecycle ---")
job = J.Job.start("reliability", "unit_label", uses_api=False, source="cli", floor="simple", condition={"a": 1})
check("manifest file written", job.path.is_file() and job.path.parent == J.JOBS_DIR)
job.progress(turn=3, hp=100)
job.set_run_log("20260101_000000_000000_simple_llm.json")
m = J.Job.load(job.job_id).m
check("progress + run log persisted", m["progress"]["turn"] == 3 and m["current_run_log"].endswith("_llm.json")
      and m["run_logs"] == [m["current_run_log"]])
check("own pid alive", J.pid_alive(m["pid"], m["pid_create_time"]))
check("heuristic job never counts as api_busy", not J.api_busy())
api_job = J.Job.start("ui-eval", "llm job", uses_api=True, source="dashboard")
check("running uses_api job blocks", [x["job_id"] for x in J.api_busy()] == [api_job.job_id])
check("exclude_job_id works", J.api_busy(exclude_job_id=api_job.job_id) == [])
job.finish("done", result={"x": 1})
api_job.finish("done")
check("finish sets status/finished_at", J.Job.load(job.job_id).m["status"] == "done" and J.Job.load(job.job_id).m["finished_at"])
check("list_jobs newest first", [x["job_id"] for x in J.list_jobs()][0] == api_job.job_id)

print("\n--- dead pid reaping ---")
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
time.sleep(0.3)
dead = J.Job.start("reliability", "will_die", uses_api=True, source="cli")
dead.adopt_pid(child.pid)
check("adopted pid is alive", J.pid_alive(child.pid, dead.m["pid_create_time"]))
check("adopted running job blocks api", any(x["job_id"] == dead.job_id for x in J.api_busy()))
child.kill()
child.wait()
changed = J.mark_dead_jobs()
check("dead job reaped as failed(process_exited)",
      any(x["job_id"] == dead.job_id for x in changed) and J.Job.load(dead.job_id).m["status"] == "failed"
      and J.Job.load(dead.job_id).m["error"] == "process_exited")
check("api free again", not J.api_busy())

print("\n--- pause / resume ---")
pj = J.Job.start("ui-eval", "pausable", uses_api=True, source="dashboard")
check("no pause requested by default", not pj.pause_requested())
t0 = time.time()
J.pause_gate(pj)
check("pause_gate is a no-op when not requested", time.time() - t0 < 0.2 and pj.m["status"] == "running")
check("request_pause on active job", J.request_pause(pj.job_id, True) is not None and J.Job.load(pj.job_id).m["pause_requested"] is True)
pj.progress(turn=7)  # owner rewrite must not clobber the controller's flag
check("owner flush preserves pause_requested", J.Job.load(pj.job_id).m["pause_requested"] is True
      and J.Job.load(pj.job_id).m["progress"]["turn"] == 7)
check("paused-pending job still holds the API", any(x["job_id"] == pj.job_id for x in J.api_busy()))
states: list[str] = []
def _resume_later():
    time.sleep(0.6)
    J.request_pause(pj.job_id, False)
threading.Thread(target=_resume_later, daemon=True).start()
t0 = time.time()
J.pause_gate(pj, poll=0.1, on_state=states.append)
waited = time.time() - t0
check("pause_gate blocked until resume", 0.5 <= waited < 3.0, f"{waited:.2f}s")
check("status paused → running, on_state called", states == ["paused", "running"] and J.Job.load(pj.job_id).m["status"] == "running", str(states))
check("paused_at cleared", J.Job.load(pj.job_id).m.get("paused_at") is None)
J.request_pause(pj.job_id, True)
threading.Thread(target=lambda: (time.sleep(0.4), J.kill_job(pj.job_id)), daemon=True).start()
t0 = time.time()
J.pause_gate(pj, poll=0.1)
check("kill ends a pause wait", time.time() - t0 < 3.0 and J.Job.load(pj.job_id).m["status"] == "killed")
check("request_pause on finished job → None", J.request_pause(pj.job_id, True) is None)

with TestClient(app) as client:
    print("\n--- one-API-job guard ---")
    holder = J.Job.start("reliability", "holder", uses_api=True, source="cli")
    r = client.post("/api/evaluate/stream", json={"floor": "simple", "mode": "llm", "prompt": "x"})
    check("LLM eval → 409 api_busy", r.status_code == 409 and r.json().get("error") == "api_busy"
          and r.json()["jobs"][0]["job_id"] == holder.job_id, str(r.status_code))
    r = client.post("/api/reliability/stream", json={"floor": "simple", "prompt": "x", "repeats": 1})
    check("LLM reliability → 409 api_busy", r.status_code == 409 and r.json().get("error") == "api_busy")
    r = client.post("/api/gepa/start", json={"floor": "simple", "label": "../bad"})
    check("GEPA start rejects a bad label (no process started)", r.status_code == 400)
    r = client.post("/api/evaluate/stream", json={"floor": "simple", "mode": "heuristic", "prompt": None, "enable_logging": False})
    check("heuristic eval not blocked", r.status_code == 200 and '"type": "done"' in r.text)
    holder.finish("done")
    r = client.get("/api/jobs")
    check("/api/jobs lists jobs incl. ui-eval", r.status_code == 200 and any(j["kind"] == "ui-eval" for j in r.json()["jobs"]))
    ui = next(j for j in r.json()["jobs"] if j["kind"] == "ui-eval" and j["floor"] == "simple")
    check("ui-eval job finished with result", ui["status"] == "done" and ui["result"].get("total") is not None, str(ui.get("result")))
    r = client.get(f"/api/jobs/{ui['job_id']}")
    check("/api/jobs/{id}", r.status_code == 200 and r.json()["job_id"] == ui["job_id"])
    r = client.get("/api/jobs/nope")
    check("/api/jobs/unknown → 404", r.status_code == 404)
    ep = J.Job.start("reliability", "ep_pause", uses_api=False, source="cli")
    r = client.post(f"/api/jobs/{ep.job_id}/pause", json={})
    check("POST /pause sets flag", r.status_code == 200 and r.json()["job"]["pause_requested"] is True)
    r = client.post(f"/api/jobs/{ep.job_id}/resume", json={})
    check("POST /resume clears flag", r.status_code == 200 and r.json()["job"]["pause_requested"] is False)
    ep.finish("done")
    r = client.post(f"/api/jobs/{ep.job_id}/pause", json={})
    check("POST /pause on finished job → 404", r.status_code == 404)

    print("\n--- websocket: jobs snapshot + dashboard run mirrored ---")
    with client.websocket_connect("/ws/events?topics=jobs") as ws:
        first = ws.receive_json()
        check("jobs_snapshot first", first["topic"] == "jobs" and first["event"]["type"] == "jobs_snapshot"
              and isinstance(first["event"]["jobs"], list))
        result_holder = {}

        def run_eval():
            rr = client.post("/api/evaluate/stream", json={"floor": "mota-floor:MT3", "mode": "heuristic", "prompt": None,
                                                           "enable_logging": True})
            result_holder["status"] = rr.status_code

        t = threading.Thread(target=run_eval)
        t.start()
        seen = recv_until(ws, lambda m: m["event"].get("type") == "job_update" and m["event"]["job"].get("status") == "done"
                          and m["event"]["job"].get("floor") == "mota-floor:MT3", timeout=20)
        t.join()
        ups = [m for m in seen if m["event"].get("type") == "job_update" and m["event"]["job"].get("floor") == "mota-floor:MT3"]
        check("job_update events for the MT3 run", len(ups) >= 2, f"{len(ups)} updates")
        check("final update status done with run log", ups and ups[-1]["event"]["job"]["status"] == "done"
              and ups[-1]["event"]["job"]["current_run_log"])
        mt3_id = ups[-1]["event"]["job"]["job_id"] if ups else None

    if mt3_id:
        r = client.get(f"/api/jobs/{mt3_id}/snapshot")
        snap = r.json().get("snapshot") or {}
        check("/snapshot returns run-log turns + result", r.status_code == 200 and len(snap.get("turns", [])) > 10
              and snap.get("result", {}).get("total") == 1.0, str(len(snap.get("turns", []))))
        with client.websocket_connect(f"/ws/events?topics=run:{mt3_id}") as ws:
            first = ws.receive_json()
            check("run_snapshot for finished run", first["event"]["type"] == "run_snapshot"
                  and len(first["event"]["snapshot"]["turns"]) > 10)

    print("\n--- websocket: live mirror of a dashboard run (run:<id>) ---")
    with client.websocket_connect("/ws/events?topics=jobs") as ws:
        ws.receive_json()
        started = {}

        def run_eval2():
            client.post("/api/evaluate/stream", json={"floor": "simple", "mode": "heuristic", "prompt": None,
                                                      "enable_logging": False})

        t = threading.Thread(target=run_eval2)
        t.start()
        seen = recv_until(ws, lambda m: m["event"].get("type") == "job_update" and m["event"]["job"].get("floor") == "simple"
                          and m["event"]["job"]["status"] == "running", timeout=10)
        run_id = next((m["event"]["job"]["job_id"] for m in reversed(seen) if m["event"].get("type") == "job_update"
                       and m["event"]["job"].get("floor") == "simple"), None)
        if run_id:
            ws.send_json({"subscribe": [f"run:{run_id}"]})
            seen2 = recv_until(ws, lambda m: m.get("topic") == f"run:{run_id}" and m["event"].get("type") == "done", timeout=20)
            turns = [m for m in seen2 if m.get("topic") == f"run:{run_id}" and m["event"].get("type") == "turn"]
            res = [m for m in seen2 if m.get("topic") == f"run:{run_id}" and m["event"].get("type") == "result"]
            check("live turn events mirrored on run topic", len(turns) >= 1, f"{len(turns)} turns")
            check("result mirrored on run topic", len(res) == 1 and round(res[0]["event"]["total"], 4) == 0.3712)
        else:
            check("caught running job_update for live subscribe", False)
        t.join()

    print("\n--- watcher tails a CLI-style run log ---")
    cli = J.Job.start("tower", "fake_cli", uses_api=False, source="cli")
    runs_dir = _TMP / "logs" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    name = "20260923_000000_000001_MT0-MT2_llm.json"
    log_path = runs_dir / name

    def write_log(n_turns: int, result=None):
        payload = {"floor_id": "MT0-MT2", "mode": "llm", "task_model": "fake", "job_id": cli.job_id,
                   "turns": [{"type": "start", "floor_id": "MT0"}] + [{"type": "turn", "turn": i, "action": f"a{i}",
                                                                          "hero": {"hp": 100 - i}} for i in range(1, n_turns + 1)],
                   "result": result}
        tmp = log_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, log_path)

    with client.websocket_connect(f"/ws/events?topics=run:{cli.job_id}") as ws:
        ws.receive_json()  # run_snapshot (empty)
        write_log(3)
        cli.set_run_log(name)
        seen = recv_until(ws, lambda m: m["event"].get("type") == "turn" and m["event"].get("turn") == 3, timeout=8)
        turns = [m["event"]["turn"] for m in seen if m["event"].get("type") == "turn"]
        check("watcher published the first 3 turns", turns == [1, 2, 3], str(turns))
        check("run_log_opened announced", any(m["event"].get("type") == "run_log_opened" for m in seen))
        time.sleep(0.5)
        write_log(5, result={"type": "result", "total": 0.5})
        seen = recv_until(ws, lambda m: m["event"].get("type") == "result", timeout=8)
        turns = [m["event"]["turn"] for m in seen if m["event"].get("type") == "turn"]
        check("watcher published only the 2 new turns", turns == [4, 5], str(turns))
        check("watcher published the result once", sum(1 for m in seen if m["event"].get("type") == "result") == 1)
    cli.finish("done")

print("\n--- CLI end-to-end (heuristic) writes a manifest ---")
env = {**os.environ, "MOTA_LOGS_DIR": str(_TMP / "logs"), "MOTA_RESULTS_DIR": str(_TMP / "results")}
proc = subprocess.run([sys.executable, "run_reliability.py", "--floor", "simple", "--heuristic", "--label", "_cli_test"],
                      cwd=_root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
check("CLI exit 0", proc.returncode == 0, proc.stderr[-400:])
cli_jobs = [m for m in J.list_jobs() if m.get("label") == "_cli_test"]
check("CLI wrote one manifest, status done", len(cli_jobs) == 1 and cli_jobs[0]["status"] == "done", str([j.get("status") for j in cli_jobs]))
check("CLI manifest carries repeats + aggregate", cli_jobs and cli_jobs[0]["progress"].get("repeats_done") == 1
      and cli_jobs[0]["result"].get("n") == 1)
res_file = _TMP / "results" / "reliability" / "_cli_test.json"
check("CLI results file has baseline score", res_file.exists() and round(json.loads(res_file.read_text(encoding="utf-8"))["runs"][0]["score"], 4) == 0.3712)

print(f"\nResults: {PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
