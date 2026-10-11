# Magic Tower AI Lab

A research platform for long-horizon decision making with large language models, built on the
grid puzzle game **Magic Tower** (Chinese *Mota*). A deterministic engine computes what the model
cannot do reliably, which actions are legal and what each one costs and unlocks, and a language model
chooses among the numbered actions. An exact solver gives the optimum of every single floor, so
every result can be measured against the best possible play.

This repository contains the framework, the web platform, the experiment results and the analysis
scripts of the master's thesis

> King Wai Siu (2026). *From Reactive Control to Holistic Planning: Evolutionary Prompt Optimization
> for Hybrid Deterministic-Neural Agents in Long-Horizon Environments.* Master's thesis,
> Leuphana University Lüneburg.

**Start here:** [guided walkthrough of the platform](docs/walkthrough.md) ·
[watch the 6-minute tour](docs/videos/walkthrough.mp4) (captioned, with a
[voice-over script](docs/videos/walkthrough_voiceover.txt); also attached to the release)

![Live page of the platform](docs/images/fig_dash_10_live_jobs.png)

## What you can do with it

- **Play and watch.** Run the rule-based heuristic or any language model on a single floor or on the
  24-floor tower and follow every decision live on the map, with the exact text the model received
  and its reasoning. Play a floor yourself through the same numbered actions the model sees.
- **Replay the thesis.** Every table of Chapter 6 is listed with its result files; each episode can be
  replayed turn by turn (Experiments → Thesis results, or [docs/results.md](docs/results.md)).

  ![Thesis results](docs/images/fig_thesis_results.png)
- **Re-run any experiment** with your own API key for an OpenAI-compatible endpoint; results are
  written under a new label and never overwrite the thesis results.
- **Run your own conditions**: model, prompt, lookahead depth, observation, planning mode
  (reactive or committed plans of *k* actions), engine settings, number of episodes.
- **Solve floors exactly** with the corrected breadth-first solver, design new floors and check that
  they have a unique winning set.
- **Optimise prompts** with the reflective (1+1) loop or the Pareto loop and inspect every iteration.

## Requirements

| Component | Version | Needed for |
|---|---|---|
| Python | 3.12 | everything |
| Node.js | 20.9 or later | building the web front end |
| JDK (`javac`, `java`) | 17 or later | the exact solver and the solver replay in the platform |
| An API key for an OpenAI-compatible endpoint | | model runs only (heuristic runs, the solver and the tests need none) |

## Quick start (no API key)

```bash
git clone https://github.com/thetobysiu/mt-ai-lab.git
cd mt-ai-lab
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,analysis]"

python -m mota.tests.test_engine                      # engine rules (225 checks)
python run_reliability.py --floor simple --heuristic  # rule-based heuristic on the simple floor

cd mota/dashboard/web && npm ci && npm run build && cd ../../..
python -m mota.dashboard                              # open http://localhost:8080
```

On Windows, `.\scripts\build_web.ps1` builds the front end in one step.

To replay the thesis episodes, download the run logs (about 150 MB, 1,996 episodes):

```bash
python scripts/fetch_run_logs.py
```

## Running a language model

Copy `.env.example` to `.env` and set `SAIA_API_KEY` (and `SAIA_BASE_URL` if you do not use the
GWDG SAIA service). Then, for example:

```bash
# the final configuration of the thesis on the simple floor, 5 episodes
export CONVERSATION_HISTORY_TURNS=0 MOTA_ORDER_TWO_SIDED=1 MOTA_FIGHT_KEY_FLOOD=1   # PowerShell: $env:NAME="1"
python run_reliability.py --floor simple --preset qwen3.5-397b --repeats 5 --label my_simple

# re-run a catalogued thesis experiment under a new label
python scripts/run_catalog.py --list
python scripts/run_catalog.py --ids main-results --repeats 1
```

Results go to `results/reliability/<label>.json` (success rate with its Wilson interval, HP relative to
the optimum, every episode with its run log) and appear in the platform while they run.

## Repository layout

```
mota/                 Python package
  game/               engine: rules, damage, reachability, observation text, tower
  solver/             Python port of the solver, floor generator
  optimizer/          evaluation loops, model presets, prompt optimisation
  harness/            repeated-run harness and the thesis experiment catalogue
  dashboard/          FastAPI server and the Next.js front end (web/)
  tests/              test suites (no API key needed)
analysis/             scripts that produce the tables and figures cited in the thesis
scripts/              command-line tools (catalogue re-runs, floor design, figures, run-log download)
tools/java_bfs/       exact breadth-first solver (Java)
data/floors/          single floors: simple, complex, hand01-04, gen01-15
data/games/24/        the 24-floor tower (game data of ckcz123/mota-js)
seed_prompts/         system prompts (single-floor, tower, solver-route, rules-only, earlier versions)
results/              all experiment results, thesis_index.json
training/             fine-tuning pilot (scripts and datasets; no model weights)
docs/                 documentation
run_reliability.py    repeated-run harness (command line)
```

## Documentation

| Document | Contents |
|---|---|
| [Walkthrough](docs/walkthrough.md) | guided tour of the platform in eight steps, with the video and recipes |
| [Getting started](docs/getting-started.md) | installation, first runs, API keys, run logs |
| [Architecture](docs/architecture.md) | how engine, model, harness and platform fit together |
| [Engine and observation](docs/engine-and-observation.md) | game rules, action enumeration, every annotation |
| [Prompts](docs/prompts.md) | the system prompts and how a prompt is chosen |
| [Running experiments](docs/running-experiments.md) | harness, planning modes, tower runs, catalogue, reproducing a thesis table |
| [Results](docs/results.md) | every thesis table with its result files (generated) |
| [Platform guide](docs/dashboard.md) | the pages of the web platform |
| [Configuration](docs/configuration.md) | environment variables and model presets |
| [Solver and floors](docs/solver-and-floors.md) | exact solver, floor format, designing floors |
| [Prompt optimisation](docs/prompt-optimisation.md) | the (1+1) loop, the Pareto loop, the study runner |
| [Development](docs/development.md) | tests, front-end build, adding features |
| [Development history](docs/development-history.md) | material removed from the final thesis: earlier experiments, tower designs, excluded runs, pilots |
| [Glossary](GLOSSARY.md) | the terms used in the thesis and the docs |

## Citation

Please cite the thesis when you use the software or its results; `CITATION.cff` holds the reference.

## Licence

Code: MIT ([LICENSE](LICENSE)). Results, run logs and documentation: CC BY 4.0
([LICENSE-DATA](LICENSE-DATA)). The 24-floor game data and the original solver are third-party
material with their own terms ([THIRD_PARTY.md](THIRD_PARTY.md)).
