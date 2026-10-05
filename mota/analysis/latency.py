"""Latency census over stored run logs (shared by scripts/latency_census.py and /api/latency)."""
from __future__ import annotations

import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path

GEPA_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIRS = ["logs/runs", "_archive/**/logs/runs"]
_CENSUS_CACHE: dict[str, tuple] = {}  # path -> ((path, mtime, size), (lat, chars, model, mode))


def iter_logs(patterns: list[str], root: Path = GEPA_ROOT):
    for pat in patterns:
        for p in glob.glob(str(root / pat / "*.json"), recursive=True):
            yield Path(p)


def episode_latencies(log: dict) -> tuple[list[float], list[int]]:
    """Per-call seconds and reasoning chars: `thinking` -> next non-forced `turn`/`parse_error` on the same turn."""
    turns = log.get("turns") or []
    pending: dict[int, float] = {}
    lat: list[float] = []
    chars: list[int] = []
    for ev in turns:
        t = ev.get("type")
        ts = ev.get("_ts")
        if ts is None:
            continue
        turn = ev.get("turn")
        if t == "thinking":
            pending[turn] = ts
        elif t == "thinking_result":
            chars.append(len(ev.get("thinking") or ""))
        elif t in ("turn", "parse_error") and not ev.get("forced"):
            start = pending.pop(turn, None)
            if start is not None:
                lat.append(ts - start)
    return lat, chars


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(q * (len(xs) - 1))))
    return xs[k]


def census(dirs: list[str] | None = None, root: Path = GEPA_ROOT) -> dict:
    """{"n_logs": int, "rows": [{model, mode, episodes, calls, median, mean, p90, chars_mean, calls_per_episode, min_per_episode}]}

    Per-file results are cached by (mtime, size) so the dashboard call is cheap; a run log that is
    still being flushed every turn (hundreds of MB) is skipped until it has settled for 5 minutes.
    """
    import os
    import time
    per_model: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"lat": [], "chars": [], "episodes": 0, "ep_calls": [], "ep_minutes": []})
    n_logs = 0
    now = time.time()
    for path in iter_logs(dirs or DEFAULT_DIRS, root):
        try:
            st = path.stat()
        except OSError:
            continue
        if now - st.st_mtime < 300 and st.st_size > 20_000_000:
            continue  # in-flight tower log; parsing it every request is what froze /benchmarks
        key = (str(path), st.st_mtime, st.st_size)
        ent = _CENSUS_CACHE.get(str(path))
        if ent and ent[0] == key:
            lat, chars, model, mode = ent[1]
        else:
            try:
                log = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if log.get("mode") != "llm":
                _CENSUS_CACHE[str(path)] = (key, ([], [], "", ""))
                continue
            lat, chars = episode_latencies(log)
            model, mode = log.get("task_model") or "unknown", log.get("task_mode") or "?"
            _CENSUS_CACHE[str(path)] = (key, (lat, chars, model, mode))
        if not lat:
            continue
        n_logs += 1
        b = per_model[(model, mode)]
        b["lat"].extend(lat)
        b["chars"].extend(chars)
        b["episodes"] += 1
        b["ep_calls"].append(len(lat))
        b["ep_minutes"].append(sum(lat) / 60.0)
    rows = []
    for (model, mode), b in sorted(per_model.items(), key=lambda kv: statistics.median(kv[1]["lat"])):
        lat = b["lat"]
        rows.append({
            "model": model, "mode": mode, "episodes": b["episodes"], "calls": len(lat),
            "median": round(statistics.median(lat), 1), "mean": round(statistics.mean(lat), 1),
            "p90": round(pct(lat, 0.9), 1),
            "chars_mean": round(statistics.mean(b["chars"])) if b["chars"] else 0,
            "calls_per_episode": round(statistics.mean(b["ep_calls"]), 1),
            "min_per_episode": round(statistics.mean(b["ep_minutes"]), 1),
        })
    return {"n_logs": n_logs, "rows": rows}


def render_markdown(c: dict) -> str:
    lines = [
        "# Latency census (retrospective, all stored run logs)",
        "",
        f"Source: {c['n_logs']} LLM run logs. One call = `thinking` -> non-forced `turn`/`parse_error` on the same turn; "
        "forced turns (single legal action) are excluded. Reasoning chars = length of the returned thinking text. "
        "Wall-clock includes network + queueing on the SAIA endpoint, so this is user-facing latency, not pure decode time.",
        "",
        "| model | mode | episodes | calls | s/call median | s/call mean | s/call p90 | reasoning chars mean | calls/episode | min/episode mean |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in c["rows"]:
        lines.append(f"| {r['model']} | {r['mode']} | {r['episodes']} | {r['calls']} | {r['median']:.1f} | {r['mean']:.1f} | "
                     f"{r['p90']:.1f} | {r['chars_mean']:.0f} | {r['calls_per_episode']:.1f} | {r['min_per_episode']:.1f} |")
    return "\n".join(lines) + "\n"
