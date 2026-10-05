"""Settings: the API key and endpoint used for LLM runs started from the dashboard.

The key is held in this server process's environment only. It is never written to disk, never logged
and never returned; GET reports only whether a key is configured, where it came from, and its last four
characters. The server binds localhost only (server.main).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

_KEYS = ("SAIA_API_KEY", "SAIA_API_KEYS", "SAIA_BASE_URL")
_state: dict = {"dashboard": False, "original": None}  # original = env before the first dashboard key (lazy: .env loads late)
DEFAULT_BASE_URL = "https://chat-ai.academiccloud.de/v1"


def _reset_clients() -> None:
    """The evaluator caches OpenAI clients per key; drop them so the next call uses the new key."""
    from ...optimizer import evaluator as ev
    ev._clients.clear()
    ev._client_idx = 0


def _summary() -> dict:
    key = os.environ.get("SAIA_API_KEY") or (os.environ.get("SAIA_API_KEYS") or "").split(",")[0].strip()
    return {"api_key": {"configured": bool(key), "source": ("dashboard" if _state["dashboard"] else "server env") if key else "none",
                        "hint": f"…{key[-4:]}" if len(key) >= 8 else ("set" if key else "")},
            "base_url": os.environ.get("SAIA_BASE_URL") or DEFAULT_BASE_URL}


async def api_settings(request: Request):
    return JSONResponse(_summary())


async def api_set_key(request: Request):
    data = await request.json()
    key = str(data.get("key") or "").strip()
    base_url = str(data.get("base_url") or "").strip()
    if not key or len(key) > 512 or any(ch.isspace() for ch in key):
        return JSONResponse({"error": "invalid key"}, status_code=400)
    if base_url and not base_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        return JSONResponse({"error": "base_url must be https:// (or a local http endpoint)"}, status_code=400)
    if _state["original"] is None:
        _state["original"] = {k: os.environ.get(k) for k in _KEYS}
    os.environ["SAIA_API_KEY"] = key
    os.environ["SAIA_API_KEYS"] = key
    if base_url:
        os.environ["SAIA_BASE_URL"] = base_url
    _state["dashboard"] = True
    _reset_clients()
    return JSONResponse(_summary())


async def api_clear_key(request: Request):
    """Forget the dashboard key and fall back to the environment the server was started with."""
    for k, v in (_state["original"] or {}).items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _state["dashboard"] = False
    _reset_clients()
    return JSONResponse(_summary())


router.add_api_route("/api/settings", api_settings, methods=["GET"])
router.add_api_route("/api/settings/api-key", api_set_key, methods=["POST"])
router.add_api_route("/api/settings/api-key", api_clear_key, methods=["DELETE"])
