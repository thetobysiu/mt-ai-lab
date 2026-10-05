"""Re-baseline the golden simple-floor prompt snapshot after a DELIBERATE formatter change.

Keeps the historical system prompt and state text, replaces turn2_actions_text with the current
engine rendering, and records what changed and why in `rebaselines`.
Usage: python scripts/rebaseline_golden.py "reason"
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from mota.optimizer import evaluator as ev  # noqa: E402

if len(sys.argv) < 2 or sys.argv[1].startswith("-") or len(sys.argv[1]) < 15:
    raise SystemExit(__doc__ + "\nREFUSING: give a real reason (>= 15 chars) as the first argument.")

snap_path = ROOT / "mota" / "tests" / "golden_simple_prompt.json"
snap = json.loads(snap_path.read_text(encoding="utf-8"))
ev.configure_scenario(str(ROOT / "data" / "floors" / "simple.txt"))
state = ev._create_state()
state.apply_action(state.get_actions()[0])
actions = state.get_actions()
new_actions = state.format_actions(actions)
new_state = state.format_state()
old_lines, new_lines = snap["turn2_actions_text"].splitlines(), new_actions.splitlines()
added = [l for l in new_lines if l not in old_lines]
removed = [l for l in old_lines if l not in new_lines]
if "effCost=None" not in new_actions:
    raise SystemExit("REFUSING: effCost=None marker missing (0/20 kills without it, 2026-09-20)")
snap.setdefault("rebaselines", []).append({
    "date": time.strftime("%Y-%m-%d %H:%M"), "reason": sys.argv[1] if len(sys.argv) > 1 else "",
    "added_lines": added, "removed_lines": removed,
})
snap["turn2_actions_text"] = new_actions
snap["turn2_state_text"] = new_state
snap_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"re-baselined: +{len(added)} lines, -{len(removed)} lines")
for l in added:
    print("  +", l[:140])
for l in removed:
    print("  -", l[:140])
