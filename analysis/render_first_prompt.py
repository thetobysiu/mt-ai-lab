"""Render the exact user message of the first LLM decision on a floor under the final configuration.

    python analysis/render_first_prompt.py                                 # simple floor (Listings 5.1, A.7)
    python analysis/render_first_prompt.py data/floors/hand/hand01.txt     # hand01 (Listing G.4)

Items and 0-HP fights the engine collects before the first decision (the key at (5,1) on the simple floor)
are applied first, as in an episode.
"""
import os
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
os.environ.update({"CONVERSATION_HISTORY_TURNS": "0", "MOTA_ORDER_TWO_SIDED": "1", "MOTA_FIGHT_KEY_FLOOD": "1", "LOOKAHEAD_DEPTH": "3"})
from mota.optimizer import evaluator as ev  # noqa: E402

ev.configure_scenario(sys.argv[1] if len(sys.argv) > 1 else "data/floors/simple.txt")
st = ev._create_state(lookahead_depth=3)
print("collected by the engine before the first decision:", ev._auto_collect_free(st))
out = "=== SYSTEM SUFFIX (floor map) ===\n" + st.format_floor_map() + "\n=== USER MESSAGE ===\n" + ev._build_user_msg(
    st.format_state(), st.format_actions(st.get_actions()))
os.makedirs("scratch", exist_ok=True)
open("scratch/_first_prompt.txt", "w", encoding="utf-8").write(out)
print(len(out.splitlines()), "lines -> scratch/_first_prompt.txt")
