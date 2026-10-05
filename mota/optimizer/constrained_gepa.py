"""Constrained GEPA (2026-09-28): linear reflective prompt evolution on the FINAL engine stack.

Differences to ``linear_gepa`` / ``run_gepa`` (April–May runs):
- evaluation = the reliability harness loop (``evaluate_with_callback`` / multi-floor callback loop):
  the same engine, assists, mechanical override and lethal-only stop as every reported result;
- score = two-tier goal score (single floor) or floors reached (tower), mean over rollouts;
- the teacher (reflection) prompt states the two-prompt rule: the evolved prompt may contain combat
  maths, how to read the annotations and general strategy, but no coordinates, floor ids, monster
  names, route lists, allowlists or floor-specific numbers; single floors have no shops/stairs;
- every candidate is validated against that rule; a violating candidate is sent back once with the
  violations, then discarded (the current prompt is kept).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_TEACHER = """\
You are improving the SYSTEM PROMPT of an LLM agent that plays Magic Tower (MOTA), a deterministic
turn-based dungeon game. {scope}

Each turn the engine gives the agent the exact state and a numbered list of every legal action with
{annotations}. The agent answers with one action number: FINAL_CHOICE: <number>.

{rules}
{shop_rule}- Keep the output contract: short reasoning, then "FINAL_CHOICE: <number>".
- Keep what worked; change or add general rules only for failures you can see in the trace.
- Length: at most ~3000 characters.
{worse_attempts}
CURRENT PROMPT:
```
<curr_param>
```

EPISODE TRACES (per LLM decision: turn, chosen action, hero after, engine overrides, end of the
agent's reasoning; then the outcome):
```
<side_info>
```

First diagnose in 3-6 bullet points which decisions lost HP or the game and which general principle
the agent misapplied (name the annotation it misread, not the position). Then give the full improved
prompt inside ``` fences.
"""

_SCOPE_SINGLE = ("This is SINGLE-FLOOR mode: one floor, the goal is to kill the boss alive with as much HP as "
                 "possible. There are NO shops, NO gold/EXP purchases and NO stairs on these floors.")
_SCOPE_TOWER = ("This is TOWER mode: many floors connected by stairs; the goal is to climb as high as possible "
                "without dying. There are shops (gold / EXP) on some floors, usable from any floor once found.")


_ANNOT_FULL = ("exact annotations (damage, hpAfter, [FREE if DEF>=X], min-cost@maxStats, an unlock tree, lookahead,\n"
               "effCost, stat-gem net value, ORDER lines comparing fight orders, key budget / key lines, [DEAD END],\n"
               "[OPTIONAL], [LETHAL]{tower_annot})")
_ANNOT_BARE = ("only the raw facts a player sees on screen: hero HP/ATK/DEF/keys, the items still on the floor, the\n"
               "boss's stats, and for each fight the monster's ATK/DEF/HP and the exact damage and HP after it.\n"
               "There is NO lookahead, NO unlock tree, NO tags or hints: the agent must work out itself, from the\n"
               "floor's entity list in the system prompt (positions of every monster, item and door), what each\n"
               "action leads to")


_RULES_GENERAL = """\
RULES FOR THE PROMPT YOU WRITE (binding — a prompt that breaks them is rejected):
- It must work on ANY floor of this kind, not only the one in the trace. So it must NOT contain:
  coordinates, floor names/ids, monster or item names, positions, lists of fights/doors to take or
  avoid, step-by-step routes, allowlists/forbidden lists, or numbers taken from this floor
  (HP thresholds, costs, counts). Percentages of current HP and the combat formula are fine.
- Allowed content: the exact combat calculation and special abilities; how to read what the engine
  shows; general strategy rules{strategy_examples}."""

_RULES_FLOOR = """\
RULES FOR THE PROMPT YOU WRITE:
- The prompt is used on THIS ONE FLOOR only, always from the same start. It may contain anything
  you can learn from the traces: positions, which fights or doors to take or avoid, an order,
  conditions on HP/ATK/DEF, as well as the combat calculation and how to read what the engine shows."""


def teacher_template(tower: bool, bare: bool = False, strategy_examples: bool = True,
                     floor_specific: bool = False) -> str:
    ex = (" (stat items before fights they make cheaper; lowest effCost among progress fights; never a fight "
          "above 40 % of current HP unless nothing else can progress; never pay HP for a fight that unlocks "
          "nothing needed; keys are scarce" + ("; scout an unvisited next floor before spending here" if tower else "")
          + ")") if strategy_examples else " that you derive from the traces"
    return _TEACHER.format(
        scope=_SCOPE_TOWER if tower else _SCOPE_SINGLE,
        annotations=_ANNOT_BARE if bare else _ANNOT_FULL.format(
            tower_annot=", [use_stairs] next-floor preview, [return_to_floor] leftovers, shop lines, ATK gate" if tower else ""),
        rules=_RULES_FLOOR if floor_specific else _RULES_GENERAL.format(strategy_examples=ex),
        shop_rule=("- Shops: NEVER buy HP, NEVER buy level-ups; DEF before ATK, but ATK must stay above the highest "
                   "monster DEF among the fights you need.\n") if tower else
                  "- Do NOT mention shops, gold, EXP or stairs: single floors have none.\n",
        worse_attempts="<worse_attempts>",
    )


def _monster_names() -> list[str]:
    from ..game import data as D
    names = set()
    for n in getattr(D, "MONSTER_NAMES_EN", {}).values():
        if isinstance(n, str) and len(n) > 3:
            names.add(n)
    return sorted(names)


def prompt_violations(text: str, tower: bool) -> list[str]:
    """Why a candidate prompt breaks the two-prompt rule (empty = acceptable)."""
    v = []
    if re.search(r"\(\s*\d+\s*,\s*\d+\s*\)", text):
        v.append("contains coordinates like (x,y)")
    if re.search(r"\bMT\d+", text):
        v.append("names a floor (MTn)")
    for w in ("ALLOW", "FORBIDDEN", "STEP 1", "walkthrough", "allowlist"):
        if w.lower() in text.lower():
            v.append(f"contains '{w}'")
    for n in _monster_names():
        if re.search(rf"\b{re.escape(n)}\b", text):
            v.append(f"names a monster ('{n}')")
            break
    for m in re.finditer(r"(?<![\w.%])(\d{3,})(?![\w%])", text):
        v.append(f"floor-specific number {m.group(1)}")
        break
    if not tower and re.search(r"\b(shop|gold|EXP|stairs)\b", text, re.IGNORECASE):
        v.append("mentions shops/gold/EXP/stairs on a single floor")
    if "FINAL_CHOICE" not in text:
        v.append("output contract FINAL_CHOICE missing")
    if len(text) > 4500:
        v.append(f"too long ({len(text)} chars)")
    return v


def format_violations(text: str) -> list[str]:
    """The only check when the validator is off (evolved-route prompt): output contract and length."""
    v = [] if "FINAL_CHOICE" in text else ["output contract FINAL_CHOICE missing"]
    if len(text) > 6000:
        v.append(f"too long ({len(text)} chars)")
    return v


def _extract_prompt(resp: str) -> str | None:
    if not isinstance(resp, str):
        return None
    blocks = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", resp, re.DOTALL)
    return blocks[-1].strip() if blocks else None


def _option_lines(actions_text: str, chosen_id, limit: int = 12, width: int = 170) -> list[str]:
    out = []
    for ln in (actions_text or "").splitlines():
        m = re.match(r"\s+(\d+)\. (\[.*)", ln)
        if m:
            mark = "*" if str(chosen_id) == m.group(1) else " "
            out.append(f"     {mark}{m.group(1)}. {m.group(2)[:width]}")
    return out[:limit]


def trace_text(log_file: str, record: dict, tower: bool, max_chars: int = 9000, rich: bool = False) -> str:
    """Compact episode trace for the teacher: every LLM decision + outcome.
    ``rich`` adds the options offered at each decision (chosen = *) and a longer reasoning tail."""
    d = json.load(open(ROOT / "logs" / "runs" / log_file, encoding="utf-8"))
    lines = []
    h = {}
    for e in d["turns"]:
        if e.get("type") != "turn":
            continue
        h = e.get("hero") or {}
        fl = f"{e.get('floor_id')} " if tower else ""
        if e.get("forced"):
            lines.append(f"T{e['turn']} {fl}[engine: {e.get('forced_reason', 'forced')}] {e['action']} -> HP {h.get('hp')}")
            continue
        ov = f" [engine override: LLM chose {e.get('corrected_from_label')} ({e.get('corrected_reason')})]" if e.get("corrected_from_label") else ""
        cot = re.sub(r"\s+", " ", (e.get("llm_thinking") or e.get("llm_response") or "")[-(700 if rich else 350):])
        opts = ""
        if rich:
            ol = _option_lines(e.get("actions_text", ""), e.get("corrected_from") or e.get("action_id"))
            opts = ("\n   options offered (* = the agent's choice):\n" + "\n".join(ol)) if ol else ""
        lines.append(f"T{e['turn']} {fl}{e['action']} -> HP {h.get('hp')} ATK {h.get('atk')} DEF {h.get('def')}{ov}{opts}\n"
                     f"   reasoning tail: ...{cot}")
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars // 3] + "\n   [...]\n" + out[-2 * max_chars // 3:]
    if tower:
        res = (f"OUTCOME: reached {record.get('max_floor_id')} (floors reached {record.get('floors_reached')}), "
               f"HP {record.get('final_hp')} ATK {record.get('hero_atk')} DEF {record.get('hero_def')}, "
               f"end: {record.get('failure_reason')}")
    else:
        res = (f"OUTCOME: {'BOSS KILLED' if record.get('success') else 'boss NOT killed'}; final HP {record.get('final_hp')}"
               f"{f' = {round(100 * record["hp_ratio"])} % of the solver optimum' if record.get('hp_ratio') else ' (solver optimum ends with more HP)'}"
               f"; ATK {record.get('hero_atk')} DEF {record.get('hero_def')}; goal score {record.get('objective', record.get('goal_score'))}; "
               f"{'died' if record.get('died') else 'alive'}; lethal-only stop: {bool(record.get('lethal_only_stop'))}")
        k = h.get("keys") or {}
        if k:
            res += f"; keys left at the end: yellow {k.get('yellow', 0)}, blue {k.get('blue', 0)}, red {k.get('red', 0)}"
    return out + "\n" + res


def run_constrained_gepa(*, floor: str | None, tower: tuple[str, str] | None, preset: str, seed_file: str,
                         label: str, iterations: int = 4, rollouts: int = 2,
                         reflection_model: str | None = None, floors: list[str] | None = None,
                         bare: bool = False, strategy_examples: bool = True,
                         select: str = "current", rich_trace: bool = False, validate: bool = True) -> dict:
    """``floors`` = train set (objective = mean over floors x rollouts; ``floor`` is its 1-element form).
    ``select='best'`` reflects from the best prompt so far (a worse candidate is dropped and shown to the
    teacher as a failed attempt); ``'current'`` is the round-6 linear walk."""
    from ..harness import reliability as H
    from ..optimizer.model_config import resolve_task_config
    from .evaluator import make_rotating_litellm_lm

    is_tower = tower is not None
    train = list(floors) if floors else ([floor] if floor else [])
    cfg = resolve_task_config(task_preset=preset)
    task_model, task_mode = cfg["task_model"], cfg["task_mode"]
    base_url = os.environ.get("SAIA_BASE_URL", "https://chat-ai.academiccloud.de/v1")
    reflection_model = reflection_model or os.environ.get("MOTA_REFLECTION_MODEL", "qwen3.5-397b-a17b")
    teacher_lm = make_rotating_litellm_lm(f"openai/{reflection_model}", base_url=base_url,
                                          max_tokens=int(os.environ.get("MOTA_REFLECTION_MAX_TOKENS", "16000")),
                                          timeout_s=float(os.environ.get("MOTA_REFLECTION_TIMEOUT", "900")))
    template = teacher_template(is_tower, bare=bare, strategy_examples=strategy_examples, floor_specific=not validate)
    check = (lambda t: prompt_violations(t, is_tower)) if validate else format_violations
    out_path = ROOT / "results" / "gepa" / f"gepa_result_{label}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    per_ep_chars = (14000 if rich_trace else 9000) if len(train) <= 1 else (10000 if rich_trace else 6000)

    def evaluate(prompt: str) -> tuple[float, list[dict]]:
        recs = []
        for fl in (train if not is_tower else [None]):
            for _ in range(rollouts):
                if is_tower:
                    r = H.run_tower_once(tower[0], tower[1], prompt, task_model, task_mode)
                    r["objective"] = (r.get("floors_reached") or 0) + (r.get("final_hp") or 0) / 100000
                else:
                    r = H.run_once(fl, prompt, "reactive", task_model, task_mode)
                    r["objective"] = r.get("goal_score") or 0.0
                    r["floor"] = fl
                recs.append(r)
                print(f"    rollout {r.get('floor') or ''}: objective={r['objective']:.4f} success={r.get('success')} "
                      f"hp={r.get('final_hp')} {r.get('max_floor_id') or ''} log={r.get('run_log')}", flush=True)
        return statistics.fmean(r["objective"] for r in recs), recs

    seed_path = Path(seed_file) if Path(seed_file).is_file() else ROOT / "seed_prompts" / seed_file
    seed = seed_path.read_text(encoding="utf-8")
    current, best, best_score = seed, seed, -1.0
    best_recs: list[dict] = []
    worse: list[tuple[float, str]] = []
    history = []
    result = {"label": label, "method": "constrained-linear-gepa", "floor": floor, "floors": train, "tower": tower,
              "preset": preset, "task_model": task_model, "reflection_model": reflection_model,
              "rollouts": rollouts, "seed_file": seed_file, "bare_obs": bare, "strategy_examples": strategy_examples,
              "select": select, "rich_trace": rich_trace, "validate": validate,
              "started": datetime.datetime.now().isoformat(),
              "env": {k: os.environ[k] for k in ("CONVERSATION_HISTORY_TURNS", "MOTA_ORDER_TWO_SIDED",
                                                   "MOTA_FIGHT_KEY_FLOOD", "THINKING_MAX_TOKENS", "LOOKAHEAD_DEPTH",
                                                   "MOTA_MULTI_FLOOR_MAX_TURNS", "MOTA_BARE_OBS", "MOTA_SUPPRESS_HINTS",
                                                   "MOTA_EVAL_TEMPERATURE") if k in os.environ},
              "iterations": history}

    def save():
        result.update(best_prompt=best, best_score=best_score, updated=datetime.datetime.now().isoformat())
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    for it in range(iterations):
        print(f"\n[{label}] iteration {it} — evaluating ({rollouts} rollouts)", flush=True)
        t0 = time.time()
        score, recs = evaluate(current)
        entry = {"iteration": it, "prompt": current, "score": round(score, 4),
                 "rollouts": [{k: r.get(k) for k in ("floor", "objective", "success", "final_hp", "hero_atk", "hero_def",
                                                      "max_floor_id", "floors_reached", "failure_reason", "run_log")}
                              for r in recs],
                 "eval_s": round(time.time() - t0, 1)}
        history.append(entry)
        if score > best_score or (select == "best" and it > 0 and score == best_score):
            best, best_score, best_recs = current, score, recs  # ties move on (exploration)
        elif select == "best":
            worse.append((score, current))
            entry["dropped"] = True
        print(f"[{label}] iteration {it}: score={score:.4f} best={best_score:.4f}", flush=True)
        save()
        if it == iterations - 1:
            break
        if select == "best":
            current, recs = best, best_recs
        side = "\n\n".join(f"--- episode {i + 1}{' (' + str(r['floor']) + ')' if r.get('floor') else ''} ---\n"
                           + trace_text(r["run_log"], r, is_tower, max_chars=per_ep_chars, rich=rich_trace)
                           for i, r in enumerate(recs) if r.get("run_log"))
        worse_txt = ""
        if worse:
            worse_txt = (f"\nEARLIER REWRITES THAT SCORED WORSE than the current prompt (score {best_score:.3f}) "
                         "- do not repeat their changes:\n" +
                         "\n".join(f"- score {s:.3f}:\n```\n{p[:1800]}\n```" for s, p in worse[-2:]) + "\n")
        ask = (template.replace("<curr_param>", current).replace("<side_info>", side)
               .replace("<worse_attempts>", worse_txt))
        t0 = time.time()
        resp = teacher_lm(ask)
        cand = _extract_prompt(resp)
        viol = check(cand) if cand else ["no fenced prompt in the reply"]
        entry["reflection"] = {"response": (resp or "")[:12000], "violations": viol, "s": round(time.time() - t0, 1)}
        if viol:
            fix = ask + ("\n\nYour previous prompt was REJECTED for breaking the rules: " + "; ".join(viol) +
                         ".\nRewrite it without these problems. Previous prompt:\n```\n" + (cand or "") + "\n```")
            resp2 = teacher_lm(fix)
            cand2 = _extract_prompt(resp2)
            viol2 = check(cand2) if cand2 else ["no fenced prompt in the reply"]
            entry["reflection"]["retry"] = {"response": (resp2 or "")[:12000], "violations": viol2}
            cand, viol = cand2, viol2
        if viol:
            print(f"[{label}] candidate rejected ({'; '.join(viol)}) — keeping current prompt", flush=True)
            entry["accepted"] = False
        else:
            current = cand
            entry["accepted"] = True
            print(f"[{label}] new candidate accepted ({len(cand)} chars)", flush=True)
        save()
    result["finished"] = datetime.datetime.now().isoformat()
    save()
    return result


_MERGE = """\
You are improving the SYSTEM PROMPT of an LLM agent that plays Magic Tower (MOTA). {scope}
Two prompts each did best on a different training floor. Write ONE prompt that keeps the rules that made
each of them succeed where it did, and drops rules that the per-floor results show to be harmful.

{rules}
- Keep the output contract: short reasoning, then "FINAL_CHOICE: <number>".
- Length: at most ~3000 characters.

PROMPT A (goal score per floor: {scores_a}):
```
{prompt_a}
```

PROMPT B (goal score per floor: {scores_b}):
```
{prompt_b}
```

OUTCOMES:
{outcomes}

First say in 3-6 bullet points which rules of A and of B explain their per-floor results. Then give the full
merged prompt inside ``` fences.
"""


def pareto_front(pop: list[dict], floors: list[str]) -> list[int]:
    """Indices of candidates that are best (ties included) on at least one floor."""
    front = set()
    for f in floors:
        top = max(c["scores"][f] for c in pop)
        front |= {i for i, c in enumerate(pop) if c["scores"][f] == top}
    return sorted(front)


def run_pareto_loop(*, floors: list[str], preset: str, seed_file: str, label: str, candidates: int = 8,
                    merge_at: int | None = None, rollouts: int = 1, reflection_model: str | None = None,
                    bare: bool = False, strategy_examples: bool = False, rich_trace: bool = True,
                    rng_seed: int = 0) -> dict:
    """Pareto loop (single floors): population scored per training floor; the parent of each rewrite is
    drawn from the candidates that are best on at least one floor (weighted by how many floors); one merge
    of two front candidates at ``merge_at`` (default: the last candidate). Same teacher, validator, trace
    and harness as the (1+1) loop, so the two differ only in selection."""
    import random

    from ..harness import reliability as H
    from ..optimizer.model_config import resolve_task_config
    from .evaluator import make_rotating_litellm_lm

    rng = random.Random(rng_seed)
    merge_at = candidates - 1 if merge_at is None else merge_at
    cfg = resolve_task_config(task_preset=preset)
    task_model, task_mode = cfg["task_model"], cfg["task_mode"]
    base_url = os.environ.get("SAIA_BASE_URL", "https://chat-ai.academiccloud.de/v1")
    reflection_model = reflection_model or os.environ.get("MOTA_REFLECTION_MODEL", "qwen3.5-397b-a17b")
    teacher_lm = make_rotating_litellm_lm(f"openai/{reflection_model}", base_url=base_url,
                                          max_tokens=int(os.environ.get("MOTA_REFLECTION_MAX_TOKENS", "16000")),
                                          timeout_s=float(os.environ.get("MOTA_REFLECTION_TIMEOUT", "900")))
    template = teacher_template(False, bare=bare, strategy_examples=strategy_examples)
    rules = _RULES_GENERAL.format(strategy_examples=" that you derive from the traces")
    out_path = ROOT / "results" / "gepa" / f"gepa_result_{label}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    per_ep_chars = 10000 if rich_trace else 6000

    def evaluate(prompt: str) -> tuple[dict, list[dict]]:
        recs, scores = [], {}
        for fl in floors:
            got = []
            for _ in range(rollouts):
                r = H.run_once(fl, prompt, "reactive", task_model, task_mode)
                r["objective"] = r.get("goal_score") or 0.0
                r["floor"] = fl
                got.append(r)
                print(f"    rollout {fl}: objective={r['objective']:.4f} success={r.get('success')} "
                      f"hp={r.get('final_hp')} log={r.get('run_log')}", flush=True)
            scores[fl] = round(statistics.fmean(r["objective"] for r in got), 4)
            recs += got
        return scores, recs

    def ask_teacher(ask: str) -> tuple[str | None, dict]:
        t0 = time.time()
        resp = teacher_lm(ask)
        cand = _extract_prompt(resp)
        viol = prompt_violations(cand, False) if cand else ["no fenced prompt in the reply"]
        info = {"response": (resp or "")[:12000], "violations": viol, "s": round(time.time() - t0, 1)}
        if viol:
            fix = ask + ("\n\nYour previous prompt was REJECTED for breaking the rules: " + "; ".join(viol) +
                         ".\nRewrite it without these problems. Previous prompt:\n```\n" + (cand or "") + "\n```")
            resp2 = teacher_lm(fix)
            cand = _extract_prompt(resp2)
            viol = prompt_violations(cand, False) if cand else ["no fenced prompt in the reply"]
            info["retry"] = {"response": (resp2 or "")[:12000], "violations": viol}
        return (None if viol else cand), info

    def keep(r: dict) -> dict:
        return {k: r.get(k) for k in ("floor", "objective", "success", "final_hp", "hero_atk", "hero_def",
                                      "failure_reason", "run_log")}

    seed_path = Path(seed_file) if Path(seed_file).is_file() else ROOT / "seed_prompts" / seed_file
    pop: list[dict] = []
    result = {"label": label, "method": "pareto-loop", "floors": floors, "preset": preset, "task_model": task_model,
              "reflection_model": reflection_model, "rollouts": rollouts, "seed_file": seed_file, "bare_obs": bare,
              "rich_trace": rich_trace, "candidates_budget": candidates, "merge_at": merge_at, "rng_seed": rng_seed,
              "started": datetime.datetime.now().isoformat(),
              "env": {k: os.environ[k] for k in ("CONVERSATION_HISTORY_TURNS", "MOTA_ORDER_TWO_SIDED",
                                                   "MOTA_FIGHT_KEY_FLOOD", "THINKING_MAX_TOKENS", "LOOKAHEAD_DEPTH",
                                                   "MOTA_BARE_OBS", "MOTA_EVAL_TEMPERATURE") if k in os.environ},
              "population": pop}

    def save():
        best = max(pop, key=lambda c: c["score"]) if pop else None
        result.update(best_prompt=best["prompt"] if best else None, best_score=best["score"] if best else None,
                      best_index=pop.index(best) if best else None, front=pareto_front(pop, floors) if pop else [],
                      updated=datetime.datetime.now().isoformat())
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(prompt: str, kind: str, parents: list[int], teacher: dict | None):
        t0 = time.time()
        scores, recs = evaluate(prompt)
        pop.append({"index": len(pop), "kind": kind, "parents": parents, "prompt": prompt, "scores": scores,
                    "score": round(statistics.fmean(scores.values()), 4), "rollouts": [keep(r) for r in recs],
                    "_recs": recs, "teacher": teacher, "eval_s": round(time.time() - t0, 1)})
        print(f"[{label}] candidate {len(pop) - 1} ({kind} of {parents}): {scores} mean={pop[-1]['score']:.4f} "
              f"front={pareto_front(pop, floors)}", flush=True)

    def dump():
        result["population"] = [{k: v for k, v in c.items() if k != "_recs"} for c in pop]
        save()
        result["population"] = pop

    print(f"\n[{label}] Pareto loop on {floors}: {candidates} candidates, merge at {merge_at}", flush=True)
    add(seed_path.read_text(encoding="utf-8"), "seed", [], None)
    dump()
    attempts = []
    for slot in range(1, candidates):
        front = pareto_front(pop, floors)
        if slot == merge_at and len(front) >= 2:
            a, b = sorted(front, key=lambda i: -pop[i]["score"])[:2]
            outcomes = "\n".join(f"{'A' if i == a else 'B'} on {r['floor']}: {trace_text(r['run_log'], r, False, 400).splitlines()[-1]}"
                                 for i in (a, b) for r in pop[i]["_recs"] if r.get("run_log"))
            ask = _MERGE.format(scope=_SCOPE_SINGLE, rules=rules, prompt_a=pop[a]["prompt"], prompt_b=pop[b]["prompt"],
                                scores_a=pop[a]["scores"], scores_b=pop[b]["scores"], outcomes=outcomes)
            cand, info = ask_teacher(ask)
            kind, parents = "merge", [a, b]
        else:
            weights = [sum(pop[i]["scores"][f] == max(c["scores"][f] for c in pop) for f in floors) for i in front]
            p = rng.choices(front, weights=weights)[0]
            worse = [c for c in pop if c["parents"] == [p] and c["score"] < pop[p]["score"]][-2:]
            worse_txt = ("" if not worse else
                         f"\nEARLIER REWRITES OF THIS PROMPT THAT SCORED WORSE (it scored {pop[p]['score']:.3f}) "
                         "- do not repeat their changes:\n" +
                         "\n".join(f"- score {c['score']:.3f}:\n```\n{c['prompt'][:1800]}\n```" for c in worse) + "\n")
            side = "\n\n".join(f"--- episode {i + 1} ({r['floor']}) ---\n"
                               + trace_text(r["run_log"], r, False, max_chars=per_ep_chars, rich=rich_trace)
                               for i, r in enumerate(pop[p]["_recs"]) if r.get("run_log"))
            ask = (template.replace("<curr_param>", pop[p]["prompt"]).replace("<side_info>", side)
                   .replace("<worse_attempts>", worse_txt))
            cand, info = ask_teacher(ask)
            kind, parents = "mutation", [p]
        if cand is None:
            print(f"[{label}] slot {slot}: {kind} of {parents} rejected ({'; '.join(info['violations'])})", flush=True)
            attempts.append({"slot": slot, "kind": kind, "parents": parents, "teacher": info, "accepted": False})
            result["rejected"] = attempts
            dump()
            continue
        add(cand, kind, parents, info)
        dump()
    result["finished"] = datetime.datetime.now().isoformat()
    dump()
    return result
