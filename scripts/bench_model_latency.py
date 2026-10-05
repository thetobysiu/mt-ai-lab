"""Per-model latency + decision quality on one real MOTA turn (no game run)."""
from __future__ import annotations
import os, statistics, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from mota.optimizer import evaluator as ev
from mota.optimizer.model_config import TASK_MODEL_PRESETS, resolve_task_config

PRESETS = sys.argv[1:] or ["qwen3.5-397b", "qwen3.6-35b", "qwen3.8-27b"]
REPEATS = int(os.environ.get("LAT_REPEATS", "3"))

ev.configure_scenario(str(ROOT / "data" / "floors" / "simple.txt"))
state = ev._create_state()
while True:
    actions = state.get_actions()
    if len(actions) >= 3:
        break
    state.apply_action(actions[0])

system_prompt = (ROOT / "seed_prompts" / "target_boss_seed.txt").read_text(encoding="utf-8") \
    + "\n\n" + state.format_floor_map()
state_text, actions_text = state.format_state(), state.format_actions(actions)
user_msg = ev._build_user_msg(state_text, actions_text)
valid = {a.action_id for a in actions}
print(f"Turn {state.turn}, {len(actions)} legal actions {sorted(valid)}; "
      f"prompt {len(system_prompt) + len(user_msg)} chars\n")

print(f"{'preset':14s} {'model':22s} {'mode':9s} {'median s':>9} {'range':>13} {'reasoning':>10} {'choices':>10}")
for preset in PRESETS:
    cfg = resolve_task_config(task_preset=preset)
    times, choices, rlens = [], [], []
    for _ in range(REPEATS):
        t0 = time.time()
        try:
            resp = ev._call_llm(system_prompt, user_msg,
                                task_model=cfg["task_model"], task_mode=cfg["task_mode"],
                                temperature=0.0)
            times.append(time.time() - t0)
            choices.append(ev._parse_action_id(resp, valid_ids=valid))
            rlens.append(len(ev._last_llm_reasoning))
        except Exception as e:
            print(f"{preset:14s} FAIL {type(e).__name__}: {str(e)[:70]}")
            break
    if times:
        print(f"{preset:14s} {cfg['task_model']:22s} {cfg['task_mode']:9s} "
              f"{statistics.median(times):9.1f} {min(times):5.1f}-{max(times):5.1f}s "
              f"{int(statistics.mean(rlens)):9d}c {str(choices):>10}")
