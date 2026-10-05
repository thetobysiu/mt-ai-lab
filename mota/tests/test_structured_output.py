"""
Tests for constrained-decoding repair (_structured_action_choice) — no network.

Run: python -m mota.tests.test_structured_output
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from mota.optimizer import evaluator as ev

PASSED = FAILED = 0


def check(label, cond):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK  {label}")
    else:
        FAILED += 1
        print(f"  FAIL {label}")


class FakeClient:
    """Records the kwargs of each call and replies per a scripted list."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        behaviour = self.script.pop(0) if self.script else ""
        if isinstance(behaviour, Exception):
            raise behaviour
        msg = SimpleNamespace(content=behaviour, reasoning=None, model_extra={})
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def run_with(script, valid_ids={1, 2, 3}, env=None):
    import os
    fake = FakeClient(script)
    orig_get, orig_model = ev._get_client, ev._get_task_model
    saved = {k: os.environ.get(k) for k in (env or {})}
    try:
        ev._get_client = lambda: fake
        ev._get_task_model = lambda m=None: "test-model"
        for k, v in (env or {}).items():
            os.environ[k] = v
        result = ev._structured_action_choice("sys", "state", "actions", valid_ids)
    finally:
        ev._get_client, ev._get_task_model = orig_get, orig_model
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return result, fake


print("\n--- structured action choice ---")

r, f = run_with(['{"action_id": 2}'])
check("json_schema reply parsed", r == 2)
check("json_schema requested first", f.calls[0].get("response_format", {}).get("type") == "json_schema")
check("enum restricted to legal ids",
      f.calls[0]["response_format"]["json_schema"]["schema"]["properties"]["action_id"]["enum"] == [1, 2, 3])
check("thinking suppressed", "/no_think" in f.calls[0]["messages"][-1]["content"])
check("small token budget", f.calls[0]["max_tokens"] <= 256)

r, _ = run_with(['{"action_id": 9}'])
check("illegal id in schema reply rejected", r is None)

r, f = run_with([TypeError("unsupported response_format"), "3"])
check("falls back to guided_choice", r == 3)
check("guided_choice carries legal ids",
      f.calls[1]["extra_body"]["guided_choice"] == ["1", "2", "3"])

r, f = run_with([TypeError("no response_format"), TypeError("no guided_choice"), "ACTION: 1"])
check("falls back to plain prompt", r == 1)
check("three routes attempted", len(f.calls) == 3)

r, _ = run_with([TypeError("a"), TypeError("b"), TypeError("c")])
check("all routes failing returns None", r is None)

r, _ = run_with(["nothing useful here"])
check("unparseable reply returns None", r is None)

r, _ = run_with(['{"action_id": 2}'], env={"MOTA_DISABLE_STRUCTURED_OUTPUT": "1"})
check("kill switch honoured", r is None)

r, _ = run_with(['{"action_id": 2}'], valid_ids=set())
check("no legal actions returns None", r is None)

r, _ = run_with(["The best option is 2 because..."])
check("numeric scan of prose reply", r == 2)

print(f"\nResults: {PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
