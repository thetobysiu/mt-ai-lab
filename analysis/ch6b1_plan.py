import json, os, sys, math
R = os.path.join(os.path.dirname(__file__), "..", "results", "reliability")

def wilson(k, n, z=1.959964):
    if n == 0:
        return (0, 0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(max(0, c - h), 3), round(min(1, c + h), 3))

for n in sys.argv[1:]:
    p = os.path.join(R, n if n.endswith(".json") else n + ".json")
    d = json.load(open(p, encoding="utf-8"))
    cfg = d.get("config", {})
    env = cfg.get("env", {})
    runs = d.get("runs") or []
    k = sum(1 for r in runs if r.get("success"))
    calls = [r.get("llm_calls") for r in runs]
    print(f"{n}: {k}/{len(runs)} model={cfg.get('preset')} T={cfg.get('temperature')} cap={env.get('THINKING_MAX_TOKENS')} plan={env.get('MOTA_PLAN_STEPS')} norep={env.get('MOTA_PLAN_NO_REPLAN')} wording={env.get('MOTA_PLAN_WORDING')} calls={calls} hp={[r.get('final_hp') for r in runs]}")

print("wilson 1/70", wilson(1, 70), "14/20", wilson(14, 20), "18/20", wilson(18, 20), "0/30", wilson(0, 30))
print("wilson 10/10", wilson(10, 10), "1/5", wilson(1, 5), "0/5", wilson(0, 5), "8/10", wilson(8, 10), "4/5", wilson(4, 5), "5/5", wilson(5, 5))
print("wilson 3/3", wilson(3, 3), "3/9", wilson(3, 9), "0/3", wilson(0, 3), "2/5", wilson(2, 5), "0/20", wilson(0, 20))
print("wilson 30/39", wilson(30, 39), "24/39", wilson(24, 39), "32/39", wilson(32, 39), "26/39", wilson(26, 39))
print("wilson 6/40", wilson(6, 40), "0/15", wilson(0, 15), "0/10", wilson(0, 10))

def sign(b, c):
    n = b + c
    one = sum(math.comb(n, i) for i in range(max(b, c), n + 1)) / 2 ** n
    two = min(1.0, 2 * sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n)
    return round(one, 4), round(two, 4)
print("sign 7:1", sign(7, 1), "3:1", sign(3, 1), "8:0", sign(8, 0), "4:2", sign(4, 2))
