import json, os
root = os.path.join(os.path.dirname(__file__), "..", "results", "gepa_study")
def load(n):
    return json.load(open(os.path.join(root, n), encoding="utf-8"))
one = load("gs5_oneplusone_dsthink_bare.json")
par = load("gs5_pareto_dsthink_bare.json")
def idx(d, prompt):
    return {(e["floor"], e["rep"]): e["success"] for e in d["episodes"] if e["prompt"] == prompt and e["split"] == "test"}
core = idx(par, "core")
po = idx(one, "gepa")
pp = idx(par, "gepa")
def disc(a, b):
    ka = set(a) & set(b)
    return sum(1 for k in ka if a[k] and not b[k]), sum(1 for k in ka if b[k] and not a[k]), len(ka)
print("core vs 1+1 (core-only : 1+1-only, n)", disc(core, po))
print("core vs pareto", disc(core, pp))
print("1+1 vs pareto", disc(po, pp))
conf = load("gs3_dsbare_confirm.json")
c = {(e["floor"], e["rep"]): e["success"] for e in conf["episodes"] if e["prompt"] == "core"}
g = {(e["floor"], e["rep"]): e["success"] for e in conf["episodes"] if e["prompt"] == "gepa"}
print("confirm core-only : gepa-only", disc(c, g))
trial = {"gen10", "gen12", "gen13", "gen14"}
c9 = {k: v for k, v in c.items() if k[0] not in trial}
g9 = {k: v for k, v in g.items() if k[0] not in trial}
print("confirm 9 floors", disc(c9, g9))
from collections import Counter
print("per floor core", sorted(Counter(k[0] for k, v in c.items() if v).items()))
print("per floor gepa", sorted(Counter(k[0] for k, v in g.items() if v).items()))
# pareto per-candidate per-floor scores if stored
gp = par.get("gepa", {})
print("pareto gepa keys", list(gp.keys()))
for k in ("candidates", "per_floor", "scores", "history"):
    if k in gp:
        print(k, json.dumps(gp[k])[:1500])
