"""Print a compact turn-by-turn trace of one or more run logs: chosen action, HP, whether the turn was an
LLM call or an override, and the LLM's stated reason.  Usage: python scripts/trace_run.py <log.json> [...]"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def trace(path: Path) -> None:
    j = json.loads(path.read_text(encoding="utf-8"))
    print(f"\n=== {path.name}  model={j.get('task_model')} mode={j.get('mode')}")
    res = j.get("result") or {}
    print(f"result: hp={res.get('final_hp')} score={res.get('score')} boss_killed={res.get('boss_killed')} "
          f"violations={res.get('violations')}")
    pending_think = ""
    n_llm = n_forced = 0
    think_chars = 0
    for t in j.get("turns", []):
        typ = t.get("type")
        if typ == "thinking_result":
            pending_think = " ".join(str(t.get("content") or t.get("text") or t.get("response") or "").split())
            think_chars += len(pending_think)
            continue
        if typ == "stuck":
            print(f"     STUCK: {str(t.get('reason') or t.get('message') or '')[:200]}")
            continue
        if typ != "turn":
            continue
        hero = t.get("hero") or {}
        forced = bool(t.get("forced"))
        n_forced += forced
        n_llm += not forced
        src = "override" if forced else "LLM"
        tail = "" if forced else f"  | {pending_think[-220:]}"
        pending_think = ""
        print(f"[{t.get('turn', '?'):>2}] hp={hero.get('hp')!s:>4} {src:<8} #{t.get('action_id')} {t.get('action')}{tail}")
    print(f"llm_turns={n_llm} forced_turns={n_forced} thinking_chars={think_chars}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        trace(Path(p))
