"""Python BFS solve-stream and Java BFS replay."""
from __future__ import annotations

import asyncio
import json
import os
import time
import threading
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, Response

from ..run_logger import RunLogger, GEPASessionLogger
from .paths import HERE as _HERE, GEPA_ROOT as _GEPA_ROOT, PROJECT_ROOT as _PROJECT_ROOT, FLOORS_DIR as _FLOORS_DIR
from . import state as S
from .state import _gepa_state, _eval_state, _matrix_state, _manual_state, _step_gepa_state, _reliability_state
from .common import *  # noqa: F401,F403


router = APIRouter()


async def api_bfs_solve_stream(request: Request):
    """SSE: run BFS solver on a floor, then stream the optimal route step by step."""
    data = await request.json()
    floor_id = data.get("floor", "mt3")
    max_states = int(data.get("max_states", 1000000))
    step_delay = float(data.get("step_delay_ms", 300)) / 1000.0

    run_log = RunLogger(
        floor_id=floor_id,
        mode="bfs",
        prompt="",
        task_model="python-bfs",
        task_mode="bfs",
        task_preset="bfs",
    )

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_event(event):
        if event is not None and run_log is not None:
            run_log.add_event(event)
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def run_bfs():
        try:
            from ...solver.bfs_solver import BFSSolver
            from ...game.state import GameState
            from ...optimizer.evaluator import _create_state, _serialize_rich_map, _hero_dict
            from ...game.types import ActionType

            _configure_floor(floor_id)
            state = _create_state()
            floor = state.floor
            hero_init = state.hero.copy()
            game_data = state.gd
            goal = state.goal



            on_event({
                "type": "start",
                "floor_id": floor.floor_id,
                "hero": _hero_dict(state),
                "initial_enemies": state.initial_enemies,
                "map": _serialize_rich_map(state),
                "state_text": state.format_state(),
                "actions_text": state.format_actions(state.get_actions()),
                "mode": "python_bfs",
                "task_model": "python-bfs",
                "task_mode": "solve",
            })
            time.sleep(0.1)

            solver = BFSSolver(
                floor, hero_init,
                game_data=game_data,
                goal=goal,
                max_states=max_states,
            )
            result = solver.solve()

            if result is None:
                on_event({
                    "type": "error",
                    "message": (
                        f"BFS found no solution "
                        f"(explored {solver.states_explored} states, "
                        f"pruned {solver.states_pruned})"
                    ),
                })
                return

            display_turn = 0
            
            def emit_step(trace, label, is_decision=False, action_obj=None, prev_rem=None):
                nonlocal display_turn
                display_turn += 1
                payload = {
                    "type": "turn",
                    "turn": display_turn,
                    "action": label,
                    "hero": _hero_dict(state),
                    # cumulative, like the evaluator's turn events — consumers replace their set with this one
                    "removed": [[int(rx), int(ry)] for (rx, ry) in state.removed],
                    "sub_steps": trace.sub_steps,
                    "floor_id": floor.floor_id,
                    "map": _serialize_rich_map(state),
                    "state_text": state.format_state(),
                    "actions_text": state.format_actions(state.get_actions()),
                }
                if is_decision and action_obj:
                    payload["action_detail"] = {"x": action_obj.x, "y": action_obj.y, "type": action_obj.type.value}
                    if hasattr(action_obj, "path"):
                        payload["action_path"] = action_obj.path
                on_event(payload)

            def play_greedy():
                while True:
                    actions = state.get_actions()
                    # Find free monsters or items
                    auto = next((a for a in actions if a.type == ActionType.COLLECT or (a.type == ActionType.FIGHT and a.total_damage == 0)), None)
                    if not auto: break
                    p_rem = set(state.removed)
                    tr = state.apply_action(auto)
                    emit_step(tr, auto.label(), prev_rem=p_rem)

            # 1. Initial greedy
            play_greedy()

            # 2. Replay BFS route
            for action in result.route:
                p_rem = set(state.removed)
                tr = state.apply_action(action)
                emit_step(tr, action.label(), is_decision=True, action_obj=action, prev_rem=p_rem)
                
                # Post-decision greedy
                play_greedy()
                
                if step_delay > 0:
                    time.sleep(step_delay)

            from ...benchmark.scorer import score_run
            scoring = score_run(state, fixture_id=floor_id)
            on_event({
                "type": "bfs_result",
                "final_hp": state.hero.hp,
                "decisions": len(result.route),
                "states_explored": solver.states_explored,
                "states_pruned": solver.states_pruned,
                "total": scoring["total"],
                "details": scoring["details"],
            })

        except Exception as exc:
            on_event({"type": "error", "message": str(exc)})
        finally:
            on_event(None)  # sentinel

    async def event_gen():
        thread = threading.Thread(target=run_bfs, daemon=True)
        thread.start()

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        if run_log is not None:
            try:
                log_path = run_log.save()
                yield f'data: {{"type": "log_saved", "path": "{log_path.name}"}}\n\n'
            except Exception:
                pass

        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


def _run_java_bfs_solver(txt_path: Path, timeout: int = 180) -> str:
    """Run the Java BFS solver as a subprocess on a .txt floor file."""
    import subprocess

    from ...paths import JAVA_BFS
    java_src = JAVA_BFS
    out_dir = JAVA_BFS / "out"
    java_files = list(java_src.glob("*.java"))
    main_class = out_dir / "Main.class"
    needs_compile = not main_class.exists()
    if not needs_compile:
        class_mtime = main_class.stat().st_mtime
        needs_compile = any(f.stat().st_mtime > class_mtime for f in java_files)
    if needs_compile:
        compile_result = subprocess.run(
            ["javac", "-d", str(out_dir)] + [str(f) for f in java_files],
            cwd=str(java_src),
            capture_output=True,
            timeout=30,
        )
        if compile_result.returncode != 0:
            raise RuntimeError(
                f"Java compile failed: {compile_result.stderr.decode('utf-8', errors='replace')[:500]}"
            )

    result = subprocess.run(
        ["java", "-cp", str(out_dir), "Main"],
        input=txt_path.read_bytes(),
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0 and not result.stdout:
        raise RuntimeError(
            f"Java BFS solver error: {result.stderr.decode('utf-8', errors='replace')[:500]}"
        )
    return result.stdout.decode("utf-8", errors="replace")


def _parse_java_bfs_output(stdout: str) -> dict:
    """Parse Java BFS solver stdout into structured data.

    Returns dict with keys: nodes, route, trace, best_hp, explored, solutions, time_used.
    """
    import re

    nodes: dict[tuple, dict] = {}
    route: list[dict] = []
    trace: list[dict] = []
    best_hp = 0
    explored = 0
    solutions = 0
    time_used = 0.0

    in_nodes = True
    in_best = False
    in_trace = False

    for line in stdout.split("\n"):
        line = line.strip()
        if not line:
            continue
        if "BFS FINISHED" in line:
            in_nodes = False
            continue
        if "BEST SOLUTION" in line:
            hp_m = re.search(r"HP=(-?\d+)", line)
            if hp_m:
                best_hp = int(hp_m.group(1))
            in_best = True
            in_trace = False
            continue
        if "BEST TRACE" in line:
            in_best = False
            in_trace = True
            continue
        if in_best and ("ALL OPTIMAL" in line or "ALL WINNING" in line or line.startswith("===")):
            in_best = False
            continue
        if in_trace and ("ALL OPTIMAL" in line or "ALL WINNING" in line or line.startswith("===")):
            in_trace = False
            continue
        if line.startswith("cnt:"):
            m = re.search(r"cnt:\s*(\d+).*solutions:\s*(\d+)", line)
            if m:
                explored = int(m.group(1))
                solutions = int(m.group(2))
            continue
        if "Time used:" in line:
            tm = re.search(r"([\d.]+)s", line)
            if tm:
                time_used = float(tm.group(1))
            continue

        # Node listing
        if in_nodes and (line.startswith("(") or "Id=" in line):
            node = _parse_java_node_line(line)
            if node:
                nodes[(node["floor"], node["row"], node["col"])] = node
            continue

        # Route lines within BEST SOLUTION
        if in_best and line.startswith("("):
            step = _parse_java_route_line(line)
            if step:
                route.append(step)

        if in_trace and line.startswith("TRACE "):
            step = _parse_java_trace_line(line)
            if step:
                trace.append(step)

    return {
        "nodes": nodes,
        "route": route,
        "trace": trace,
        "best_hp": best_hp,
        "explored": explored,
        "solutions": solutions,
        "time_used": time_used,
    }


def _parse_java_node_line(line: str) -> dict | None:
    """Parse one node-listing line, e.g.
    Id=8: (0,4,6) -- Monsters: [(203,45,5,5,0,2)] -- 6 Linked
    """
    import re

    m = re.match(r"(?:Id=(\d+):\s*)?\((\d+),(\d+),(\d+)\)", line)
    if not m:
        return None

    node: dict = {
        "id": int(m.group(1)) if m.group(1) else 0,
        "floor": int(m.group(2)),
        "row": int(m.group(3)),  # Java x = row
        "col": int(m.group(4)),  # Java y = col
        "x": int(m.group(4)),    # Python x = col
        "y": int(m.group(3)),    # Python y = row
    }

    desc_parts: list[str] = []

    if "Items:" in line:
        im = re.search(r"Items:\s*(.*?)(?:\s*--|\s*$)", line)
        if im:
            desc_parts.append(f"Items: {im.group(1).strip().rstrip(';')}")

    if "Doors:" in line:
        dm = re.search(r"Doors:\s*\[([^\]]*)\]", line)
        if dm:
            door_names = {"1": "Yellow", "2": "Blue", "3": "Red", "4": "Green"}
            vals = [v.strip() for v in dm.group(1).split(",") if v.strip()]
            desc = ", ".join(f"{door_names.get(v, '?')} Door" for v in vals)
            if desc:
                desc_parts.append(desc)

    if "Monsters:" in line:
        mm = re.findall(r"\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\)", line)
        if mm:
            special_names = {
                "0": "", "1": "first-strike", "2": "magic", "3": "solid",
                "4": "2x-hit", "5": "3x-hit", "6": "4x-hit",
                "7": "armor-break", "8": "counter", "9": "purify", "10": "mimic",
            }
            groups: dict[tuple, int] = {}
            monster_tile_ids: list[int] = []
            for mid, _mhp, _matk, _mdef, _, mspec in mm:
                sn = special_names.get(mspec, f"special={mspec}")
                key = (mid, sn)
                groups[key] = groups.get(key, 0) + 1
                monster_tile_ids.append(int(mid))
            node["monsters"] = monster_tile_ids  # List of tile IDs (ints) for companion matching
            m_descs = []
            for (mid, sn), count in groups.items():
                label = f"Monster #{mid}"
                if sn:
                    label += f" [{sn}]"
                if count > 1:
                    label = f"{count}× {label}"
                m_descs.append(label)
            desc_parts.append(", ".join(m_descs))

    if "Hero:" in line and not desc_parts:
        desc_parts.append("Start")

    node["description"] = " + ".join(desc_parts) if desc_parts else "Unknown"
    lm = re.search(r"(\d+)\s+Linked", line)
    node["linked"] = int(lm.group(1)) if lm else 0
    return node


def _parse_java_route_line(line: str) -> dict | None:
    """Parse one route line: (0,4,6) -- Hero: (415,9,4,0,0,1,0,0,0) -- 6 Linked"""
    import re

    m = re.match(
        r"\((\d+),(\d+),(\d+)\)\s*--\s*Hero:\s*\(([^)]+)\)\s*--\s*(\d+)\s+Linked", line
    )
    if not m:
        return None
    stats = [int(v) for v in m.group(4).split(",")]
    return {
        "floor": int(m.group(1)),
        "row": int(m.group(2)),
        "col": int(m.group(3)),
        "x": int(m.group(3)),  # Python x = col
        "y": int(m.group(2)),  # Python y = row
        "hp": stats[0],
        "atk": stats[1],
        "def": stats[2] if len(stats) > 2 else 0,
        "mdef": stats[3] if len(stats) > 3 else 0,
        "money": stats[4] if len(stats) > 4 else 0,
        "yellow": stats[5] if len(stats) > 5 else 0,
        "blue": stats[6] if len(stats) > 6 else 0,
        "red": stats[7] if len(stats) > 7 else 0,
        "green": stats[8] if len(stats) > 8 else 0,
        "linked": int(m.group(5)),
    }


def _parse_java_trace_line(line: str) -> dict | None:
    """Parse one Java atomic trace line emitted by State.atomicRoute."""
    import re

    m = re.match(r"TRACE\s+(\w+):\s*\((\d+),(\d+),(\d+)\)\s*--\s*Hero:\s*\(([^)]+)\)(.*)$", line)
    if not m:
        return None

    stats = [int(v) for v in m.group(5).split(",")]
    tail = m.group(6) or ""
    step = {
        "kind": m.group(1).lower(),
        "floor": int(m.group(2)),
        "row": int(m.group(3)),
        "col": int(m.group(4)),
        "x": int(m.group(4)),
        "y": int(m.group(3)),
        "hp": stats[0],
        "atk": stats[1],
        "def": stats[2] if len(stats) > 2 else 0,
        "mdef": stats[3] if len(stats) > 3 else 0,
        "money": stats[4] if len(stats) > 4 else 0,
        "yellow": stats[5] if len(stats) > 5 else 0,
        "blue": stats[6] if len(stats) > 6 else 0,
        "red": stats[7] if len(stats) > 7 else 0,
        "green": stats[8] if len(stats) > 8 else 0,
        "monster_ids": [],
        "doors": [],
        "items": "",
    }

    desc_parts: list[str] = []

    if "Items:" in tail:
        im = re.search(r"Items:\s*(.*?)(?:\s*--|\s*$)", tail)
        if im:
            step["items"] = im.group(1).strip().rstrip(";")
            if step["items"]:
                desc_parts.append(f"Items: {step['items']}")

    if "Doors:" in tail:
        dm = re.search(r"Doors:\s*\[([^\]]*)\]", tail)
        if dm:
            door_names = {"1": "Yellow Door", "2": "Blue Door", "3": "Red Door", "4": "Green Door"}
            vals = [v.strip() for v in dm.group(1).split(",") if v.strip()]
            step["doors"] = vals
            door_desc = ", ".join(door_names.get(v, f"Door {v}") for v in vals)
            if door_desc:
                desc_parts.append(door_desc)

    if "Monsters:" in tail:
        mm = re.findall(r"\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\)", tail)
        if mm:
            special_names = {
                "0": "", "1": "first-strike", "2": "magic", "3": "solid",
                "4": "2x-hit", "5": "3x-hit", "6": "4x-hit",
                "7": "armor-break", "8": "counter", "9": "purify", "10": "mimic",
            }
            grouped: dict[tuple[str, str], int] = {}
            for mid, _mhp, _matk, _mdef, _money, mspec in mm:
                step["monster_ids"].append(int(mid))
                spec = special_names.get(mspec, f"special={mspec}")
                key = (mid, spec)
                grouped[key] = grouped.get(key, 0) + 1

            monster_descs = []
            for (mid, spec), count in grouped.items():
                label = f"Monster #{mid}"
                if spec:
                    label += f" [{spec}]"
                if count > 1:
                    label = f"{count}× {label}"
                monster_descs.append(label)
            if monster_descs:
                desc_parts.append(", ".join(monster_descs))

    step["description"] = " + ".join(desc_parts) if desc_parts else step["kind"].title()
    return step


def _resolve_java_bfs_txt_path(floor_id: str | None) -> Path | None:
    """Resolve simple/complex dashboard IDs to the backing AI test floor .txt file."""
    if not floor_id:
        return None
    raw = Path(str(floor_id))
    if raw.exists():
        return raw

    search_roots = [
        _GEPA_ROOT / "data" / "floors",
        _GEPA_ROOT / "data" / "floors" / "hand",
        _GEPA_ROOT / "data" / "floors" / "gen",
    ]
    for base in search_roots:
        candidates = [base / raw.name]
        if not raw.suffix:
            candidates.append(base / f"{raw.name}.txt")
        for candidate in candidates:
            if candidate.exists():
                return candidate
    return None


def _hero_from_java_trace(step: dict) -> dict:
    return {
        "hp": step.get("hp", 0),
        "atk": step.get("atk", 0),
        "def": step.get("def", 0),
        "mdef": step.get("mdef", 0),
        "money": step.get("money", 0),
        "exp": 0,
        "keys": {
            "yellow": step.get("yellow", 0),
            "blue": step.get("blue", 0),
            "red": step.get("red", 0),
        },
        "x": step.get("x", 0),
        "y": step.get("y", 0),
    }


def _java_trace_action_type(step: dict) -> str:
    if step.get("kind") == "shop":
        return "shop_buy"
    if step.get("monster_ids"):
        return "fight"
    if step.get("doors"):
        return "open_door"
    if step.get("items"):
        return "collect"
    return "move"


def _java_trace_action_label(step: dict) -> str:
    description = step.get("description") or f"({step.get('x')},{step.get('y')})"
    if step.get("kind") == "shop":
        return "Shop"
    if step.get("monster_ids"):
        return f"Fight {description}"
    if step.get("doors"):
        return f"Open {description}"
    if step.get("items"):
        return f"Collect {description}"
    return description


def _score_java_bfs_trace(trace: list[dict], fixture_id: str, best_hp: int) -> dict:
    """Score a Java-native BFS trace against the same BFS reference targets."""
    from ...benchmark.scorer import BFS_REFERENCE

    ref = BFS_REFERENCE.get(fixture_id) or BFS_REFERENCE.get(f"{fixture_id}.txt")
    final_step = trace[-1] if trace else {}
    final_hp = best_hp or final_step.get("hp", 0)
    final_atk = final_step.get("atk", 0)
    final_def = final_step.get("def", 0)
    steps = max(0, len(trace) - 1)
    enemies_killed = sum(1 for step in trace[1:] if step.get("monster_ids"))
    boss_killed = any(299 in step.get("monster_ids", []) for step in trace[1:])
    violations = []

    if ref is None:
        total = 1.0 if boss_killed and final_hp > 0 else 0.0
        if not boss_killed:
            violations.append("boss_not_killed")
        return {
            "total": round(total, 4),
            "violations": violations,
            "details": {
                "enemies_killed": enemies_killed,
                "enemies_total": enemies_killed,
                "final_hp": final_hp,
                "steps": steps,
                "hero_atk": final_atk,
                "hero_def": final_def,
                "benchmark_id": fixture_id,
                "benchmark_source": "java-bfs-trace",
            },
        }

    completion = min(1.0, enemies_killed / max(1, ref["enemies_killed"]))
    if not boss_killed:
        violations.append("boss_not_killed")

    if final_hp <= 0:
        hp_score = 0.0
    elif final_hp >= ref["target_hp"]:
        hp_score = ref["target_hp"] / final_hp
    else:
        hp_score = final_hp / ref["target_hp"]

    if steps <= ref["ref_steps"]:
        efficiency = 1.0
    else:
        efficiency = max(0.0, 1.0 - (steps - ref["ref_steps"]) / ref["ref_steps"])

    atk_score = min(1.0, final_atk / max(1, ref.get("target_atk", final_atk or 1)))
    def_score = min(1.0, final_def / max(1, ref.get("target_def", final_def or 1)))
    shop_score = (atk_score + def_score) / 2.0
    violation_score = 1.0 - min(1.0, len(violations) * 0.15)

    total = (
        0.35 * completion +
        0.25 * hp_score +
        0.15 * efficiency +
        0.15 * shop_score +
        0.10 * violation_score
    )

    return {
        "total": round(total, 4),
        "violations": violations,
        "details": {
            "enemies_killed": enemies_killed,
            "enemies_total": ref["enemies_total"],
            "final_hp": final_hp,
            "target_hp": ref["target_hp"],
            "steps": steps,
            "ref_steps": ref["ref_steps"],
            "hero_atk": final_atk,
            "hero_def": final_def,
            "target_atk": ref["target_atk"],
            "target_def": ref["target_def"],
            "benchmark_id": fixture_id,
            "benchmark_source": "java-bfs-trace",
        },
    }


def _stream_java_bfs_trace(on_event, floor_id: str | None):
    """Run Java BFS and stream its atomic trace without replaying through Python actions."""
    from ...optimizer.evaluator import _create_state, _serialize_rich_map

    _configure_floor(floor_id)
    state = _create_state()
    txt_path = _resolve_java_bfs_txt_path(floor_id)
    if txt_path is None:
        on_event({
            "type": "error",
            "message": (
                f"No .txt floor file found for '{floor_id}'. "
                "Java BFS solver requires AI test floor .txt files."
            ),
        })
        return

    on_event({
        "type": "status",
        "message": f"Running Java BFS solver on {txt_path.name}...",
    })
    stdout = _run_java_bfs_solver(txt_path)
    bfs = _parse_java_bfs_output(stdout)
    trace = bfs.get("trace") or []

    if not trace:
        on_event({"type": "error", "message": "Java BFS trace missing from solver output."})
        return

    on_event({
        "type": "start",
        "floor_id": txt_path.stem,
        "hero": _hero_from_java_trace(trace[0]),
        "initial_enemies": state.initial_enemies,
        "map": _serialize_rich_map(state),
        "state_text": state.format_state(),
        "actions_text": "",
        "mode": "replay_bfs",
        "task_model": "java-bfs",
        "task_mode": "solver",
    })
    time.sleep(0.1)

    on_event({
        "type": "status",
        "message": (
            f"Java BFS solved: HP={bfs['best_hp']}, "
            f"{len(trace)-1} actions, "
            f"{bfs['explored']} states in {bfs['time_used']:.1f}s"
        ),
    })

    removed_so_far: list[list[int]] = []
    for replay_turn, step in enumerate(trace[1:], start=1):
        action_type = _java_trace_action_type(step)
        if action_type not in {"shop_buy", "move"}:
            cell = [int(step["x"]), int(step["y"])]
            if cell not in removed_so_far:
                removed_so_far.append(cell)
        on_event({
            "type": "turn",
            "turn": replay_turn,
            "action": f"[JAVA {step.get('kind', 'step').upper()}] {_java_trace_action_label(step)}",
            "hero": _hero_from_java_trace(step),
            # cumulative: a consumer replaces its removed set with this one (fought monsters stay gone)
            "removed": list(removed_so_far),
            "sub_steps": [],
            "action_detail": {
                "x": int(step["x"]),
                "y": int(step["y"]),
                "type": action_type,
            },
            "floor_id": txt_path.stem,
            "state_text": f"Java BFS {step.get('kind', 'step')} step {replay_turn}: {step.get('description', '')}",
            "actions_text": "",
        })
        time.sleep(0.04 if action_type == "collect" else 0.08)

    scoring = _score_java_bfs_trace(trace, txt_path.stem, bfs["best_hp"])
    on_event({
        "type": "bfs_result",
        "final_hp": scoring["details"].get("final_hp", bfs["best_hp"]),
        "decisions": len(trace) - 1,
        "states_explored": bfs["explored"],
        "solutions": bfs["solutions"],
        "time_used": bfs["time_used"],
        "total": scoring["total"],
        "details": scoring["details"],
        "violations": scoring.get("violations", []),
    })


async def api_replay_bfs(request: Request):
    """SSE: run Java BFS solver as subprocess and stream step-by-step replay."""
    import re

    data = await request.json()
    floor_id = data.get("floor", "mt3")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    run_log = RunLogger(
        floor_id=floor_id,
        mode="java_bfs",
        prompt="",
        task_model="java-bfs",
        task_mode="solver",
        task_preset="bfs",
    )

    def on_event(event):
        if event is not None and run_log is not None:
            run_log.add_event(event)
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def run_replay():
        try:
            _stream_java_bfs_trace(on_event, floor_id)

        except Exception as exc:
            import traceback
            on_event({"type": "error", "message": f"{exc}\n{traceback.format_exc()}"})
        finally:
            if run_log:
                try:
                    log_path = run_log.save()
                    on_event({"type": "log_saved", "path": log_path.name})
                except Exception:
                    pass
            on_event(None)

    import threading

    async def event_gen():
        thread = threading.Thread(target=run_replay, daemon=True)
        thread.start()

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


router.add_api_route("/api/bfs/solve-stream", api_bfs_solve_stream, methods=["POST"])
router.add_api_route("/api/replay_bfs", api_replay_bfs, methods=["POST"])
