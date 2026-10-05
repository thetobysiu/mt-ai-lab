"""Model presets and the LLM latency benchmark."""
from __future__ import annotations

import asyncio
import json
import os
import time
import threading
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, Response

from ..run_logger import RunLogger, GEPASessionLogger
from .paths import HERE as _HERE, GEPA_ROOT as _GEPA_ROOT, PROJECT_ROOT as _PROJECT_ROOT, FLOORS_DIR as _FLOORS_DIR
from . import state as S
from .state import _gepa_state, _eval_state, _matrix_state, _manual_state, _step_gepa_state, _reliability_state
from .common import *  # noqa: F401,F403


router = APIRouter()


async def api_models(request: Request):
    """Return model presets and the current resolved task-model config."""
    from ...optimizer.model_config import list_task_model_presets, resolve_task_config

    config = resolve_task_config()
    return JSONResponse({
        "task_presets": list_task_model_presets(),
        **config,
    })


async def api_llm_latency(request: Request):
    """Benchmark LLM call latency across selected models."""
    import time as _time
    from openai import OpenAI
    from ...optimizer.model_config import TASK_MODEL_PRESETS

    data = await request.json()
    preset_ids = data.get("models")  # list of preset IDs, or None for all
    if not preset_ids:
        preset_ids = list(TASK_MODEL_PRESETS.keys())

    api_key = os.environ.get("SAIA_API_KEY", "")
    base_url = os.environ.get("SAIA_BASE_URL", "https://chat-ai.academiccloud.de/v1")
    if not api_key:
        return JSONResponse({"error": "SAIA_API_KEY not set"}, status_code=500)

    client = OpenAI(api_key=api_key, base_url=base_url)
    test_messages = [
        {"role": "system", "content": "Reply with exactly one word."},
        {"role": "user", "content": "What is 2+2?"},
    ]

    loop = asyncio.get_event_loop()
    results = []

    for pid in preset_ids:
        preset = TASK_MODEL_PRESETS.get(pid)
        if not preset:
            results.append({"preset_id": pid, "error": "Unknown preset"})
            continue

        model_name = preset["model"]

        def _call(model=model_name):
            start = _time.perf_counter()
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=test_messages,
                    max_tokens=10,
                    temperature=0.0,
                )
                elapsed = (_time.perf_counter() - start) * 1000
                content = resp.choices[0].message.content if resp.choices else ""
                return {"latency_ms": round(elapsed), "response": content, "error": None}
            except Exception as e:
                elapsed = (_time.perf_counter() - start) * 1000
                return {"latency_ms": round(elapsed), "response": None, "error": str(e)}

        r = await loop.run_in_executor(None, _call)
        results.append({
            "preset_id": pid,
            "label": preset["label"],
            "model": model_name,
            "mode": preset.get("mode", "instruct"),
            **r,
        })

    return JSONResponse({"results": results})


router.add_api_route("/api/models", api_models, methods=["GET"])
router.add_api_route("/api/models/ping", api_llm_latency, methods=["POST"])
