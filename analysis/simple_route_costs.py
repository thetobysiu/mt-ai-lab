"""Replay the simple floor's exact optimal route on the engine: cost of every action, stats before, HP after (Table 4.4).

    python analysis/simple_route_costs.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from mota.optimizer import evaluator as ev  # noqa: E402
from mota.game.types import ActionType  # noqa: E402

ROUTE = [(6, 4), (5, 6), (4, 7), (3, 7), (7, 0), (8, 0), (9, 0), (3, 5), (7, 5), (9, 5),
         (1, 9), (10, 7), (9, 9), (4, 2), (2, 1), (5, 9), (5, 10)]
ev.configure_scenario(str(ROOT / "data" / "floors" / "simple.txt"))
st = ev._create_state(lookahead_depth=0)


def collect_all():
    while True:
        c = [a for a in st.get_actions(annotate=False) if a.type == ActionType.COLLECT]
        if not c:
            return
        st.apply_action(c[0])


for k, pos in enumerate(ROUTE, 1):
    collect_all()
    h = st.hero
    a = next(a for a in st.get_actions(annotate=False) if (a.x, a.y) == pos and a.type != ActionType.COLLECT)
    hp, atk, df, keys = h.hp, h.atk, h.def_, h.keys.yellow
    st.apply_action(a)
    print(f"{k:2d} {a.label():45s} cost={hp - st.hero.hp:4d} before HP={hp} ATK={atk} DEF={df} Y={keys} -> HP={st.hero.hp}")
collect_all()
print("end", st.hero.hp, st.hero.atk, st.hero.def_)
