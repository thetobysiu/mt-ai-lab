"""
Golden-prompt regression: the engine must render the simple-floor decision prompt
byte-identically to the text seen by the 2026-06-01 boss-kill episode.

Why: on 2026-09-20 a well-intentioned change to the effCost annotation
(None -> numeric) silently changed the prompt semantics and dropped the
simple-floor kill rate from 6/14 to 0/20 across three models. Any prompt-text
change must therefore be deliberate and re-baselined here.

Run: python -m mota.tests.test_prompt_golden
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from mota.optimizer import evaluator as ev
from mota.optimizer.seed_prompt import SEED_PROMPT_NOSHOP, get_seed_for_floor

GOLDEN_LOG = _root / "logs" / "runs" / "20260601_033724_008241_simple_llm.json"
GOLDEN_SNAPSHOT = _root / "mota" / "tests" / "golden_simple_prompt.json"

PASSED = FAILED = 0


def check(label, cond, detail=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK  {label}")
    else:
        FAILED += 1
        print(f"  FAIL {label}" + (f"\n       {detail}" if detail else ""))


def load_golden() -> dict:
    """Prefer the committed snapshot; (re)build it from the run log if absent."""
    if GOLDEN_SNAPSHOT.exists():
        return json.loads(GOLDEN_SNAPSHOT.read_text(encoding="utf-8"))
    d = json.loads(GOLDEN_LOG.read_text(encoding="utf-8"))
    turns = [e for e in d["turns"] if e.get("type") == "turn"]
    snap = {
        "source_log": GOLDEN_LOG.name,
        "prompt": d["prompt"],
        "turn2_state_text": turns[1]["state_text"],
        "turn2_actions_text": turns[1]["actions_text"],
    }
    GOLDEN_SNAPSHOT.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  (wrote golden snapshot {GOLDEN_SNAPSHOT.name})")
    return snap


def first_diff(a: str, b: str) -> str:
    for i, (la, lb) in enumerate(zip(a.splitlines(), b.splitlines())):
        if la != lb:
            return f"line {i + 1}:\n       golden: {la[:150]}\n       now:    {lb[:150]}"
    return f"length differs: golden {len(a.splitlines())} lines, now {len(b.splitlines())}"


print("\n--- golden prompt (simple floor, 2026-06-01 boss kill) ---")
g = load_golden()

ev.configure_scenario(str(_root / "data" / "floors" / "simple.txt"))
state = ev._create_state()
state.apply_action(state.get_actions()[0])  # forced key pickup -> turn 1 decision
actions = state.get_actions()
check("reached the 4-way decision", len(actions) == 4)

now_actions = state.format_actions(actions)
now_state = state.format_state()
check("actions_text identical to golden", now_actions == g["turn2_actions_text"],
      first_diff(g["turn2_actions_text"], now_actions))
check("state_text identical to golden", now_state == g["turn2_state_text"],
      first_diff(g["turn2_state_text"], now_state))
check("effCost=None preserved for gateway fights", "effCost=None" in now_actions)
# The engine-generated layers (state + actions) are pinned above. The system prompt changed on
# 2026-09-23 (basic prompts); the historical kill's prompt is the LEGACY no-shop seed.
from mota.optimizer.seed_prompt import LEGACY_SEED_PROMPT_NOSHOP, FLOOR_BASIC_PROMPT, TOWER_BASIC_PROMPT
check("2026-06-01 kill used the LEGACY no-shop seed", LEGACY_SEED_PROMPT_NOSHOP.strip() == g["prompt"].strip())
check("get_seed_for_floor('simple') returns the basic floor prompt",
      get_seed_for_floor("simple").strip() == FLOOR_BASIC_PROMPT.strip())
check("get_seed_for_floor('MT0-MT23w') returns the basic tower prompt",
      get_seed_for_floor("MT0-MT23w").strip() == TOWER_BASIC_PROMPT.strip())
_bad = ["MT8", "Red Bat", "(11,2)", "walkthrough", "ALLOW", "FORBIDDEN", "STEP 1"]
check("basic prompts contain no hard-coded choices", not any(w in FLOOR_BASIC_PROMPT + TOWER_BASIC_PROMPT for w in _bad))
check("tower prompt forbids buying HP", "NEVER buy HP" in TOWER_BASIC_PROMPT)

print(f"\nResults: {PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
