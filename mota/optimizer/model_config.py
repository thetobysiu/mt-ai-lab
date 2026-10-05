"""Shared task-model preset helpers for CLI and dashboard workflows."""
from __future__ import annotations

import os


DEFAULT_TASK_MODEL = "qwen3.5-397b"
DEFAULT_TASK_MODE = "thinking"

# Presets marked deprecated were removed from the SAIA catalogue (checked 2026-09-20);
# they are kept so historical result labels still resolve.
TASK_MODEL_PRESETS = {
    "qwen3.5-397b": {
        "label": "Qwen3.5 397B A17B",
        "model": "qwen3.5-397b-a17b",
        "mode": "thinking",
    },
    "qwen3.8-27b": {
        "label": "Qwen3.8 27B (dense)",
        "model": "qwen3.8-27b",
        "mode": "thinking",
    },
    "qwen3.8-27b-or": {
        "label": "Qwen3.8 27B (dense, OpenRouter)",
        "model": "qwen/qwen3.8-27b:free",
        "mode": "thinking",  # needs SAIA_BASE_URL=https://openrouter.ai/api/v1 + OPENROUTER_API_KEY in .env
    },
    "qwen3.8-27b-groq": {
        "label": "Qwen3.8 27B (dense, Groq)",
        "model": "qwen/qwen3.8-27b",
        "mode": "thinking",  # needs SAIA_BASE_URL=https://api.groq.com/openai/v1 + GROQ_API_KEY; max 16384 output tokens
    },
    "gpt-oss-120b": {
        "label": "OpenAI GPT-OSS 120B",
        "model": "openai-gpt-oss-120b",
        "mode": "instruct",
    },
    "deepseek-v4-flash": {
        "label": "DeepSeek V4 Flash 0731",
        "model": "deepseek-v4-flash-0731",
        "mode": "instruct",
    },
    "deepseek-v4-flash-think": {
        "label": "DeepSeek V4 Flash 0731 (thinking)",
        "model": "deepseek-v4-flash-0731",
        "mode": "thinking",  # returns reasoning (~5 s/decision); instruct mode caps at 2000 tokens
    },
    "glm-5.3-flash": {
        "label": "GLM 5.3 Flash",
        "model": "glm-5.3-flash",
        "mode": "thinking",  # returns reasoning_content; instruct mode's 2000-token cap truncates it
    },
    "mistral-medium-3.5": {
        "label": "Mistral Medium 3.5 128B",
        "model": "mistral-medium-3.5-128b",
        "mode": "instruct",
    },
    "qwen3.5-27b": {
        "label": "Qwen3.5 27B (deprecated on SAIA)",
        "model": "qwen3.5-27b",
        "mode": "thinking",
        "deprecated": True,
    },
    "qwen3-instruct": {
        "label": "Qwen3 30B Instruct",
        "model": "qwen3-30b-a3b-instruct-2507",
        "mode": "instruct",
    },
    "qwen3-omni": {
        "label": "Qwen3 Omni 30B",
        "model": "qwen3-omni-30b-a3b-instruct",
        "mode": "instruct",
        "vision": True,
    },
    "llama-3.1-8b": {
        "label": "Llama 3.1 8B Instruct",
        "model": "meta-llama-3.1-8b-instruct",
        "mode": "instruct",
    },
    "qwen3.6-35b": {
        "label": "Qwen3.6 35B A3B",
        "model": "qwen3.6-35b-a3b",
        "mode": "thinking",
    },
    "qwen3.5-35b": {
        "label": "Qwen3.5 35B A3B (deprecated on SAIA)",
        "model": "qwen3.5-35b-a3b",
        "mode": "thinking",
        "deprecated": True,
    },
    "qwen3.5-122b": {
        "label": "Qwen3.5 122B A10B (deprecated on SAIA)",
        "model": "qwen3.5-122b-a10b",
        "mode": "thinking",
        "deprecated": True,
    },
    "gemma-4-31b": {
        "label": "Gemma 4 31B IT",
        "model": "gemma-4-31b-it",
        "mode": "instruct",
    },
}

VALID_TASK_MODES = {"auto", "instruct", "thinking"}


def get_task_model() -> str:
    return os.environ.get("MOTA_TASK_MODEL", DEFAULT_TASK_MODEL)


def _normalize_task_mode(task_mode: str | None) -> str:
    mode = (task_mode or DEFAULT_TASK_MODE).strip().lower()
    return mode if mode in VALID_TASK_MODES else DEFAULT_TASK_MODE


def _effective_task_mode(task_model: str, task_mode: str | None) -> str:
    normalized = _normalize_task_mode(task_mode)
    if normalized == "thinking":
        return "thinking"
    if normalized == "instruct":
        return "instruct"
    return "thinking" if "thinking" in task_model.lower() else "instruct"


def should_use_no_think(task_model: str, task_mode: str | None) -> bool:
    return _effective_task_mode(task_model, task_mode) != "thinking"


def resolve_task_config(
    task_model: str | None = None,
    task_mode: str | None = None,
    task_preset: str | None = None,
) -> dict:
    config = {}
    if task_preset:
        preset = TASK_MODEL_PRESETS.get(task_preset)
        if preset is None:
            # Fallback for unknown preset (e.g. from old browser localStorage)
            preset = {
                "label": task_preset,
                "model": get_task_model(),
                "mode": _effective_task_mode(get_task_model(), None)
            }
        config.update(preset)
        config["task_preset"] = task_preset
    else:
        config["model"] = get_task_model()
        config["mode"] = os.environ.get("MOTA_TASK_MODE", DEFAULT_TASK_MODE)
        config["label"] = config["model"]
        config["task_preset"] = None

    if task_model:
        config["model"] = task_model
    resolved_mode = _effective_task_mode(config["model"], task_mode if task_mode is not None else config.get("mode"))

    matched_preset = None
    for preset_id, preset in TASK_MODEL_PRESETS.items():
        if preset["model"] == config["model"] and preset["mode"] == resolved_mode:
            matched_preset = preset_id
            config["label"] = preset["label"]
            break

    return {
        "task_model": config["model"],
        "task_mode": resolved_mode,
        "task_preset": matched_preset,
        "label": config.get("label", config["model"]),
    }


def list_task_model_presets() -> list[dict]:
    return [
        {
            "id": preset_id,
            "label": preset["label"],
            "model": preset["model"],
            "mode": preset["mode"],
            "deprecated": bool(preset.get("deprecated", False)),
        }
        for preset_id, preset in TASK_MODEL_PRESETS.items()
    ]


def list_available_models(base_url: str | None = None, api_key: str | None = None) -> list[str]:
    """Return chat model IDs currently served by the SAIA /v1/models endpoint.

    Tries every key in the evaluator's pool (SAIA_API_KEYS, SAIA_API_KEY) until one authenticates.
    """
    import json
    import urllib.error
    import urllib.request

    base_url = (base_url or os.environ.get("SAIA_BASE_URL")
                or os.environ.get("OPENAI_API_BASE", "https://chat-ai.academiccloud.de/v1")).rstrip("/")
    if api_key:
        keys = [api_key]
    else:
        from .evaluator import _collect_api_keys
        keys = _collect_api_keys()
    last_err: Exception | None = None
    for key in keys:
        req = urllib.request.Request(f"{base_url}/models", headers={"Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return sorted(m.get("id", "") for m in payload.get("data", []))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in (401, 403):
                raise
    raise RuntimeError(f"No API key in pool authenticated against {base_url}/models") from last_err


def check_preset_availability(base_url: str | None = None, api_key: str | None = None) -> dict[str, bool]:
    """Map each preset ID to whether its model is currently listed by the API."""
    available = set(list_available_models(base_url=base_url, api_key=api_key))
    return {pid: preset["model"] in available for pid, preset in TASK_MODEL_PRESETS.items()}