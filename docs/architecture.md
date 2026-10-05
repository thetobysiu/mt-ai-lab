# Architecture

## The hybrid agent

```
            ┌───────────────────────────────┐
  floor ──▶ │ Engine (deterministic)        │ ──▶ annotated action list ──┐
            │ reachability · exact damage · │                             ▼
            │ lookahead tree                │                     ┌──────────────┐
            └──────────────▲────────────────┘    system prompt ──▶│ Language     │
                           │                                       │ model        │
                           └──── action number (1 or k per call) ──┴──────────────┘
```

The engine reads the floor, enumerates every legal action, computes its exact consequences and
writes them as text (the *observation*). The model answers with the number of an action, ending its
answer with `FINAL_CHOICE: <n>`. Because it can only name a listed number, it cannot refer to a target
that does not exist. The engine executes the action, walks the shortest path to it, collects what is
reachable and produces the next observation.

## Packages

| Package | Role | Main modules |
|---|---|---|
| `mota.game` | the game | `state.py` (game state, `format_state` / `format_actions` = the observation), `pathfinder.py` (reachability), `damage.py` (combat formula and special abilities), `floor_loader.py` and `ai_floor_loader.py` (tower and single-floor files), `multi_floor.py` (tower engine), `data.py` (monster, item and shop tables), `project.py` (loader for other HTML5 Magic Tower projects) |
| `mota.solver` | search | `bfs_solver.py` (Python port of the solver), `boss_floor_gen.py` (generated floors), `data_generator.py` and `synthetic_maps.py` (training data of the fine-tuning pilot) |
| `mota.optimizer` | decision loops | `evaluator.py` (reactive loop, committed plans, tower loop, overrides, repair calls), `model_config.py` (presets), `seed_prompt.py` (prompt per floor), `constrained_gepa.py` (the (1+1) and Pareto loops), `run_gepa.py` (GEPA library entry point) |
| `mota.harness` | experiments | `reliability.py` (repeated runs, result files, job manifests), `catalog.py` (thesis experiments that can be re-run) |
| `mota.benchmark` | scoring | `scorer.py` (success, HP relative to the optimum, goal score, legacy composite) |
| `mota.dashboard` | platform | `server.py`, `api/*.py` (REST routers), `run_logger.py` (run logs), `jobs.py` (job manifests, pause/resume), `watcher.py` and `events.py` (live view of command-line runs), `procs.py` (processes started from the browser), `web/` (Next.js front end) |
| `mota.paths` | file locations | repository root, game data (`MOTA_GAME_ROOT`), single floors, solver, results, logs |

## One episode

1. `configure_scenario(...)` loads a single floor (`data/floors/*.txt`) or a tower range
   (`data/games/24/project/floors/MT*.js`) and the system prompt (`seed_prompts/`).
2. At each decision the engine applies the *assists* (collect reachable items, fight 0-HP monsters,
   on the tower take the stairs to an unvisited floor) and records them as forced turns.
3. It sends the system prompt and the observation to the model. The answer is parsed; an answer
   without a valid number goes to one repair call with constrained decoding.
4. A *mechanical override* replaces a dead-end door, an unwinnable fight or a lethal fight while a
   non-lethal action exists; every override is logged with the model's original choice.
5. The episode ends when the boss is defeated (single floors), when no action is left, or at the turn
   limit. The scorer computes success and HP relative to the exact optimum.

In committed planning modes, one call returns *k* actions that are executed without asking the model
again; the plan stops early when a planned action is no longer available.

## Runs, results and logs

```
run_reliability.py / platform / scripts/run_catalog.py
        │  same condition object
        ▼
mota.harness.reliability ──▶ results/reliability/<label>.json   (aggregate + one record per episode)
        │                 ──▶ logs/runs/<timestamp>_<floor>_llm.json   (every observation, answer, override)
        │                 ──▶ logs/jobs/<job>.json                     (job manifest: progress, current log)
        ▼
platform: JobWatcher tails manifests and run logs ──▶ event bus ──▶ WebSocket ──▶ browser
```

Runs started in the browser and runs started from the command line write the same files, so the
platform shows both live. `results/thesis_index.json` maps each table of the thesis to its result files.
