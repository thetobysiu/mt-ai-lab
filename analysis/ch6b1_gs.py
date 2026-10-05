import json, glob, os, math
from collections import defaultdict
root = os.path.join(os.path.dirname(__file__), "..", "results", "gepa_study")

def load(n):
    return json.load(open(os.path.join(root, n), encoding="utf-8"))

def binom_two(b, c):
    n = b + c
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail), sum(math.comb(n, i) for i in range(max(b, c), n + 1)) / 2 ** n

def means(d):
    agg = defaultdict(list)
    for e in d.get("episodes", []):
        agg[(e.get("prompt"), e.get("split"))].append(e)
    out = {}
    for k, v in agg.items():
        out[k] = (len(v), sum(1 for e in v if e.get("success")), sum(1 for e in v if e.get("died")),
                  round(sum(e["goal_score"] for e in v) / len(v), 4))
    return out

for f in sorted(glob.glob(os.path.join(root, "gs*.json"))):
    n = os.path.basename(f)
    d = json.load(open(f, encoding="utf-8"))
    print("=" * 20, n, d.get("preset"), d.get("task_mode"), d.get("obs"), "train", d.get("train"), "repeat", d.get("repeat"))
    print("  test", d.get("test"))
    g = d.get("gepa") or {}
    if g:
        print("  gepa: best", g.get("best_score"), "traj", g.get("trajectory"), "acc", g.get("accepted"), "best_is_seed", g.get("best_is_seed"), "refl", g.get("reflection_model"))
    for k, v in sorted(means(d).items(), key=lambda x: str(x[0])):
        print("  ", k, "n/succ/died/goal", v)
    other = [k for k in d.keys() if k not in ("episodes", "env", "train", "test", "gepa", "summary")]
    print("  keys", other)
