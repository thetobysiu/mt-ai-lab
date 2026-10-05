# Getting started

After these steps, the [walkthrough](walkthrough.md) tours the platform page by page.

## 1. Install

```bash
git clone https://github.com/thetobysiu/mt-ai-lab.git
cd mt-ai-lab
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # macOS / Linux
pip install -e ".[dev,analysis]"
```

Extras: `analysis` (matplotlib, Pillow) is needed for the figure scripts, `reflection` (litellm) for
the original GEPA library runs, `dev` (httpx, Playwright) for the API and browser tests.

Run every command from the repository root.

## 2. Check the installation (no API key)

```bash
python -m mota.tests.test_engine          # game rules, damage, reachability, tower engine
python -m mota.tests.test_prompt_golden   # the observation text is unchanged
python run_reliability.py --floor simple --heuristic
python run_reliability.py --floor hand01 --heuristic
python run_reliability.py --tower --start MT0 --end MT23w --heuristic --max-turns 1500
```

The heuristic acts on the same engine output as a model, without a language model. It ends the
simple floor alive with the boss untouched and reaches MT8 of the tower.

## 3. Build and start the platform

```bash
cd mota/dashboard/web
npm ci
npm run build          # static export into mota/dashboard/web/out
cd ../../..
python -m mota.dashboard
```

Open the printed address (http://localhost:8080 unless the port is taken). On Windows,
`.\scripts\build_web.ps1` runs the two npm steps. See the [platform guide](dashboard.md).

## 4. Download the thesis run logs

Each result file names the run log of every episode. The logs are published as the release asset
`run_logs.zip` (about 150 MB, 1,996 logs, 1.9 GB unpacked):

```bash
python scripts/fetch_run_logs.py                 # download and unpack into logs/runs/
python scripts/fetch_run_logs.py --zip run_logs.zip   # or use a file you downloaded yourself
```

After that, Experiments → Thesis results links every episode to its replay, and the Logs page lists
all thesis episodes.

## 5. Use a language model

The models are reached through an OpenAI-compatible endpoint. Copy `.env.example` to `.env` and set

```
SAIA_API_KEY=<your key>
SAIA_BASE_URL=https://chat-ai.academiccloud.de/v1   # or https://openrouter.ai/api/v1, https://api.groq.com/openai/v1, ...
```

`--preset` selects a model (see [configuration](configuration.md#model-presets)); `--task-model` passes
any model id your endpoint serves. In the platform, the API key can also be entered in the top bar;
it is kept in memory only and never written to disk.

A first model run:

```bash
python run_reliability.py --floor hand01 --preset deepseek-v4-flash-think --repeats 1 --label try_hand01
```

To use the final configuration of the thesis, set three engine settings first:

```bash
# PowerShell
$env:CONVERSATION_HISTORY_TURNS="0"; $env:MOTA_ORDER_TWO_SIDED="1"; $env:MOTA_FIGHT_KEY_FLOOD="1"
# bash
export CONVERSATION_HISTORY_TURNS=0 MOTA_ORDER_TWO_SIDED=1 MOTA_FIGHT_KEY_FLOOD=1
```

Next: [running experiments](running-experiments.md).
