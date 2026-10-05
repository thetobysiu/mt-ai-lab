"""SSE evaluation streams: one single-floor episode (heuristic or LLM) and one tower segment.

Every stream registers a job manifest (kind ui-eval), mirrors its events on the WebSocket topic
run:<job_id>, and refuses to start an LLM run while another job holds the API (409 api_busy,
override with force:true). Planning granularity (plan_steps / one_shot) and the final engine stack
(final_stack) are the same env switches the CLI uses (§7.3.6).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import jobs as J
from ..run_logger import RunLogger
from .common import _apply_experiment_env, _configure_floor
from .state import _eval_state
from .streaming import threaded_sse, busy_response

router = APIRouter()


def _release():
    _eval_state["running"] = False
    _eval_state["stop_requested"] = False


def _stop_requested() -> bool:
    return bool(_eval_state["stop_requested"])


def _condition(data: dict, **extra) -> dict:
    keys = ("lookahead_depth", "temperature", "disable_overrides", "thinking_max_tokens", "structured_output",
            "plan_steps", "one_shot", "final_stack", "max_turns", "checkpoint", "mode")
    c = {k: data.get(k) for k in keys if data.get(k) is not None}
    c.update(extra)
    return c


async def api_evaluate_stream(request: Request):
    """SSE: per-turn events for one single-floor episode.

    Body: floor, prompt (null = heuristic), mode (llm | heuristic), plan_steps (1 = reactive), one_shot,
    final_stack, enable_logging, lookahead_depth, temperature, task_model/task_mode/task_preset,
    disable_overrides, thinking_max_tokens, structured_output, force.
    """
    if _eval_state["running"]:
        return JSONResponse({"error": "An evaluation is already running"}, status_code=409)
    data = await request.json()
    floor_id = data.get("floor", "mt3")
    prompt = data.get("prompt")  # None = heuristic mode
    mode = data.get("mode", "llm")  # llm | heuristic
    use_llm = mode == "llm" and prompt is not None
    if use_llm:
        busy = busy_response(bool(data.get("force")))
        if busy is not None:
            return busy
    _eval_state["running"] = True
    _eval_state["stop_requested"] = False

    enable_logging = data.get("enable_logging", True)
    lookahead_depth = int(data["lookahead_depth"]) if data.get("lookahead_depth") is not None else None
    _apply_experiment_env(data)
    from ...optimizer.model_config import resolve_task_config
    task_config = resolve_task_config(
        task_model=data.get("task_model"), task_mode=data.get("task_mode"), task_preset=data.get("task_preset"),
    )
    temperature = float(data.get("temperature", 0.0))

    from ...optimizer.evaluator import evaluate_with_callback

    try:
        _configure_floor(floor_id, data.get("project") or None)
    except Exception as e:
        _release()
        return JSONResponse({"error": str(e)}, status_code=400)

    steps = int(data.get("plan_steps") or 1)
    if not use_llm:
        log_mode = "heuristic"
    elif data.get("one_shot"):
        log_mode = "llm-plan-maxsteps-once"
    elif steps > 1:
        log_mode = f"llm-plan{steps}"
    else:
        log_mode = "llm"
    job = J.Job.start(
        "ui-eval", f"{floor_id} {log_mode}", uses_api=use_llm, source="dashboard",
        floor=floor_id, model=task_config["task_model"] if use_llm else None,
        preset=task_config.get("task_preset") if use_llm else "heuristic", mode=log_mode,
        condition=_condition(data, log_mode=log_mode, project=data.get("project") or "24"),
    )
    run_log = None
    if enable_logging:
        run_log = RunLogger(floor_id=floor_id or "mt3", mode=log_mode, prompt=prompt,
                            task_model=task_config["task_model"], task_mode=task_config["task_mode"],
                            task_preset=task_config["task_preset"], job_id=job.job_id)

    def worker(on_event):
        common = dict(on_event=on_event, task_model=task_config["task_model"], task_mode=task_config["task_mode"],
                      should_stop=_stop_requested)
        evaluate_with_callback(prompt if use_llm else None, lookahead_depth=lookahead_depth, temperature=temperature,
                               **common)

    return threaded_sse(worker, run_log=run_log, job=job, on_finish=_release)


async def api_evaluate_stop(request: Request):
    """Request cooperative stop for the currently running evaluation."""
    if not _eval_state["running"]:
        return JSONResponse({"status": "idle"})
    _eval_state["stop_requested"] = True
    return JSONResponse({"status": "stopping"})


async def api_evaluate_multi_floor_stream(request: Request):
    """SSE: tower segment (start_floor..end_floor, or a walkthrough checkpoint) with floor_change events."""
    if _eval_state["running"]:
        return JSONResponse({"error": "An evaluation is already running"}, status_code=409)
    data = await request.json()
    prompt = data.get("prompt")
    mode = data.get("mode", "llm")
    use_llm = mode == "llm" and prompt is not None
    if use_llm:
        busy = busy_response(bool(data.get("force")))
        if busy is not None:
            return busy
    _eval_state["running"] = True
    _eval_state["stop_requested"] = False

    start_floor = data.get("start_floor", "MT3")
    end_floor = data.get("end_floor", "MT4")
    enable_logging = data.get("enable_logging", True)
    lookahead_depth = int(data["lookahead_depth"]) if data.get("lookahead_depth") is not None else None
    temperature = float(data.get("temperature", 0.0))
    _apply_experiment_env(data)
    if data.get("max_turns"):
        os.environ["MOTA_MULTI_FLOOR_MAX_TURNS"] = str(int(data["max_turns"]))
    # Walkthrough checkpoint: start floor + exact hero stats; target floor unless overridden.
    hero_override = None
    checkpoint = data.get("checkpoint")
    if checkpoint is not None and checkpoint != "":
        from ...game.data import WALKTHROUGH_CHECKPOINTS
        cp = WALKTHROUGH_CHECKPOINTS[int(checkpoint)]
        start_floor = cp["floor"]
        end_floor = data.get("end_floor") or cp["target"]
        hero_override = dict(cp["hero"])
    from ...optimizer.model_config import resolve_task_config
    task_config = resolve_task_config(
        task_model=data.get("task_model"), task_mode=data.get("task_mode"), task_preset=data.get("task_preset"),
    )
    from ...optimizer.evaluator import configure_multi_floor_scenario, evaluate_multi_floor_with_callback

    try:
        project_root = None
        if data.get("project") and data["project"] != "24":
            from .projects import registered_projects
            meta = registered_projects().get(data["project"])
            if not meta:
                raise ValueError(f"unknown project '{data['project']}'")
            project_root = meta["root"]
        configure_multi_floor_scenario(start_floor, end_floor, hero_override=hero_override, project_root=project_root)
    except Exception as e:
        _release()
        return JSONResponse({"error": str(e)}, status_code=400)

    log_mode = "llm" if use_llm else "heuristic"
    job = J.Job.start(
        "ui-eval", f"{start_floor}->{end_floor} {log_mode}", uses_api=use_llm, source="dashboard",
        start=start_floor, end=end_floor, checkpoint=int(checkpoint) if checkpoint not in (None, "") else None,
        model=task_config["task_model"] if use_llm else None,
        preset=task_config.get("task_preset") if use_llm else "heuristic", mode=log_mode,
        condition=_condition(data, tower=True),
    )
    run_log = None
    if enable_logging:
        run_log = RunLogger(floor_id=f"{start_floor}-{end_floor}", mode=log_mode, prompt=prompt,
                            task_model=task_config["task_model"], task_mode=task_config["task_mode"],
                            task_preset=task_config["task_preset"], job_id=job.job_id)

    def worker(on_event):
        evaluate_multi_floor_with_callback(
            prompt if use_llm else None, on_event=on_event,
            task_model=task_config["task_model"], task_mode=task_config["task_mode"],
            should_stop=_stop_requested, lookahead_depth=lookahead_depth, temperature=temperature,
        )

    return threaded_sse(worker, run_log=run_log, job=job, on_finish=_release)


router.add_api_route("/api/evaluate/stream", api_evaluate_stream, methods=["POST"])
router.add_api_route("/api/evaluate/stop", api_evaluate_stop, methods=["POST"])
router.add_api_route("/api/evaluate/multi-floor", api_evaluate_multi_floor_stream, methods=["POST"])
