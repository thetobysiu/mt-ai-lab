# Development

## Tests

No test needs an API key; all of them run the heuristic, the solver or recorded data.

```bash
python -m mota.tests.test_engine            # rules, damage, reachability, observation lines, tower engine
python -m mota.tests.test_prompt_golden     # observation text pinned byte for byte at a reference decision
python -m mota.tests.test_boss_scoring      # success, HP/opt, goal score
python -m mota.tests.test_structured_output # answer parsing and the repair call
python -m mota.tests.test_project_adapter   # loading HTML5 Magic Tower projects
python -m mota.tests.test_jobs              # job manifests, pause/resume, harness
python -m mota.tests.test_dashboard_api     # every API router (needs the dev extra)
python scripts/smoke_dashboard.py           # browser smoke test of every page (needs a running server and Playwright)
```

`test_prompt_golden` fails on any change to the observation text. If the change is deliberate,
re-baseline with `python scripts/rebaseline_golden.py` and re-measure: in the thesis, replacing the
effective-cost placeholder with a number changed the success rate from 5 of 10 to 0 of 20 episodes.

## Front end

```bash
cd mota/dashboard/web
npm ci
npm run dev        # development server on :3000, talks to the API on :8080 (see .env.development)
npm run build      # static export into out/, served by the FastAPI server at /
npm run typecheck
```

Design tokens and component classes are in `web/app/globals.css` and `web/design-system/`. Pages live in
`web/app/<page>/page.tsx`; shared components in `web/components/`.

## Solver

```bash
python scripts/build_solver.py     # javac -d tools/java_bfs/out tools/java_bfs/*.java
```

## Adding things

- **A floor:** put a `.txt` file in `data/floors/` (format in [solver-and-floors.md](solver-and-floors.md)),
  record its exact optimum in a `manifest.json` so the scorer can compute HP/opt, and run
  `python run_reliability.py --floor data/floors/<file>.txt --heuristic`.
- **A model:** add a preset to `TASK_MODEL_PRESETS` in `mota/optimizer/model_config.py`
  (`model`, `mode`, optional token caps), or pass `--task-model <id> --task-mode thinking|instruct`.
- **An annotation:** extend `GameState.format_actions` in `mota/game/state.py` behind an environment
  switch, add a test in `test_engine.py`, and re-baseline the golden prompt only when the switch is on
  by default.
- **A catalogue entry:** add a registry code to `scripts/run_followups.py` and an entry to
  `mota/harness/catalog.py`.
- **The thesis index:** after changing results that the thesis reports, regenerate
  `results/thesis_index.json` and `docs/results.md` with
`python analysis/thesis_index.py --appendix <path to Appendix D of the thesis>`.

## Run-log archive

`analysis/build_run_logs_zip.py --logs logs/runs --out <dir>/run_logs.zip` packs every run log named by
a result file; the archive is published as a release asset, and `scripts/fetch_run_logs.py` restores it.
