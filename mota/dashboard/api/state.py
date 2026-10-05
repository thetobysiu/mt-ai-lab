"""Mutable in-process state shared across routers.

Every dict here is mutated in place (never rebound) so all routers observe the same object.
"""
from __future__ import annotations

import threading

lock = threading.Lock()

_gepa_state: dict = {
    "running": False,
    "iterations": [],
    "done": False,
    "error": None,
    "best_prompt": "",
    "best_score": 0,
    "stop_requested": False,
}

_eval_state: dict = {"running": False, "stop_requested": False}
_matrix_state: dict = {"running": False, "stop_requested": False}
_step_gepa_state: dict = {"running": False, "stop_requested": False}
_reliability_state: dict = {"running": False, "stop_requested": False}

_MANUAL_DEFAULTS: dict = {
    "state": None,
    "game": None,
    "multi_floor": False,
    "floor_id": "mt3",
    "run_log": None,
    "log_saved": None,
    "action_ids": [],
    "result": None,
    "walkthrough_guide": None,
    "diverged_at_turn": None,
}
_manual_state: dict = dict(_MANUAL_DEFAULTS)


def reset(d: dict, **values) -> None:
    """Replace a shared state dict's contents in place."""
    d.clear()
    d.update(values)


def reset_manual() -> None:
    reset(_manual_state, **{k: (list(v) if isinstance(v, list) else v) for k, v in _MANUAL_DEFAULTS.items()})
