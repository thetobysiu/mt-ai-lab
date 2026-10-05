"""Replay the first N turns of a tower run log into a fresh MultiFloorGame and print the state there.

    python scratch/replay_tower.py <runlog.json> <turns> [--map] [--actions]
Needs the env of the run (MOTA_REMOTE_ACTIONS=1, MOTA_SHOP_ROUTE=1 for final3/final4).
"""
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("MOTA_REMOTE_ACTIONS", "1")
os.environ.setdefault("MOTA_SHOP_ROUTE", "1")
from mota.optimizer import evaluator as ev  # noqa: E402


def replay(log: str, n: int, lookahead: int = 2):
    turns = [t for t in json.loads(Path(log).read_text(encoding="utf-8"))["turns"] if t["type"] == "turn"]
    ev.configure_multi_floor_scenario("MT0", "MT23w")
    game = ev._create_multi_floor_game(lookahead_depth=lookahead)
    for t in turns[:n]:
        acts = game.get_actions()
        want = t["action"]
        local = next((a for a in acts if a.label() == want and a.remote is None), None)
        remote = next((a for a in acts if a.remote is not None and a.remote.label() == want
                       and a.target_floor_id == t.get("floor_id")), None)
        # the log labels remote actions without their floor; the same label can exist on the current floor
        a = (remote or local) if t.get("floor_id") != game.current_floor.floor_id else (local or remote)
        a = a or next((a for a in acts if a.label() == want), None) or next(
            (a for a in acts if a.remote is not None and a.remote.label() == want), None)
        if a is None:
            raise SystemExit(f"turn {t['turn']}: '{want}' not offered; offered: {[x.label() for x in acts][:12]}")
        game.apply_action(a)
    return game


if __name__ == "__main__":
    g = replay(sys.argv[1], int(sys.argv[2]))
    print(g.format_state())
    if "--map" in sys.argv:
        print(g.format_floor_map())
    if "--actions" in sys.argv:
        print(g.format_actions(g.get_actions()))
