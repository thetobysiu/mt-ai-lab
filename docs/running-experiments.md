# Running experiments

Every experiment is a *configuration* (floor or tower range, model, prompt, planning mode, lookahead
depth, engine settings) run *N* times. The repeated-run harness writes one result file per label with
the success rate, its Wilson 95 % interval, the final HP relative to the exact optimum among the
successes, and one record per episode that names its run log.

## The harness: `run_reliability.py`

```bash
python run_reliability.py --floor <floor> [--preset <model>] [--repeats N] [--label <name>] [options]
```

| Option | Meaning |
|---|---|
| `--floor` | `simple`, `complex`, `hand01`…`hand04`, `MT3`, `MT4`, or a floor file such as `data/floors/gen/gen07.txt` |
| `--tower --start MT0 --end MT23w` | tower run over a range of floors; `--max-turns` caps the turns |
| `--preset` | model preset ([configuration](configuration.md#model-presets)); `--task-model` passes any model id |
| `--heuristic` | rule-based heuristic, no model (N = 1) |
| `--repeats` | number of episodes |
| `--prompt-file` | a file in `seed_prompts/` or a path; default = the prompt of the floor type |
| `--lookahead` | gateways searched behind an action (default 3; tower runs use 2) |
| `--mode` | `reactive` (default), `map-enum` (map-only condition), `oneshot`, `multistep-N` (earlier harness) |
| `--temperature` | sampling temperature (default 0) |
| `--disable-overrides` | switch off all assists and overrides |
| `--label`, `--append` | result file name; append episodes to an existing label |

Engine settings are environment variables ([configuration](configuration.md)). The **final
configuration** of the thesis is:

```bash
CONVERSATION_HISTORY_TURNS=0  MOTA_ORDER_TWO_SIDED=1  MOTA_FIGHT_KEY_FLOOD=1   # lookahead 3, temperature 0
```

Each result file stores the complete condition (`config`, including every engine setting) so a run
can be repeated exactly.

### Planning modes

| Mode | Settings |
|---|---|
| reactive (one action per call) | default |
| commit-*k* (k actions per call, executed without asking again) | `MOTA_PLAN_STEPS=k` |
| long plan, re-planned (as many actions as the model can, then a new call) | `MOTA_PLAN_STEPS=60` |
| single-call plan (one call for the whole episode) | `MOTA_PLAN_STEPS=60 MOTA_PLAN_NO_REPLAN=1` |
| whole-floor wording of the long plan (earlier runs) | add `MOTA_PLAN_WORDING=floor` |

A committed plan stops early when a planned action is no longer listed; `scripts/verify_plans.py`
checks every stored plan against the engine.

### Tower runs

Tower design 7 (the final design) as stored with its results:

```powershell
$env:THINKING_MAX_TOKENS="8192"; $env:CONVERSATION_HISTORY_TURNS="0"
$env:MOTA_ORDER_TWO_SIDED="1"; $env:MOTA_FIGHT_KEY_FLOOD="1"
$env:MOTA_REMOTE_ACTIONS="1"; $env:MOTA_SHOP_ROUTE="1"; $env:MOTA_WAY_UP="1"; $env:MOTA_TOWER_FIDELITY="1"
$env:MOTA_TOWER_HP_FLOOR="0"; $env:MOTA_OFFER_LEVELUPS="1"; $env:MOTA_PLAN_MEMORY="1"; $env:MOTA_NO_KEY_PURCHASE="1"
$env:MOTA_WAYUP_COMBINED="1"; $env:MOTA_FREE_AFFORD="1"; $env:MOTA_NPC_TRADES="1"; $env:MOTA_KEY_RESERVE="1"
$env:MOTA_AFTER_BATTLE="1"; $env:MOTA_BUY_QUANTITY="1"; $env:MOTA_VAMPIRE_TAG="1"; $env:MOTA_EVENT_WAY="1"
python run_reliability.py --tower --start MT0 --end MT23w --max-turns 1500 --lookahead 2 --preset deepseek-v4-flash-think --repeats 3 --label my_tower
```

The catalogue entry `tower-final` (codes `T11QR`, `T11DR`, `T11Q6`, `T11MM`) sets all of this for you.

A tower run of a strong model takes several hours and several hundred calls. Long reasoning can run
into the token cap; truncated answers are repaired immediately. `MOTA_RESUME_LOG` and
`MOTA_RESUME_BEFORE_TURN` continue a stored run from a given turn.

## The thesis catalogue

`mota/harness/catalog.py` lists the experiments of Chapter 6 with their exact arguments and settings
(the registry `scripts/run_followups.py` holds one code per thesis cell). Re-runs always write a new
label (`rerun_<time>_<label>`), never the thesis result:

```bash
python scripts/run_catalog.py --list                       # entries and their cells
python scripts/run_catalog.py --ids main-results           # Table 6.2 cells of Qwen3.5-397B
python scripts/run_catalog.py --codes VDS5 VD15 --repeats 2  # any registry code, capped at 2 episodes
```

The same catalogue is the "Re-run thesis experiments" tab of the Experiments page, where you can also
enter the API key.

## Reproducing a table of the thesis

1. Find the table in [results.md](results.md) (or Experiments → Thesis results). It lists the result files.
2. Open a result file: `config` holds the floor, model, prompt, mode, lookahead and every engine setting.
3. Re-run it with the same settings, either with `run_catalog.py --codes <code>` (codes in
   `scripts/run_followups.py`, searchable by label) or with `run_reliability.py` and the stored settings.
4. Compare success rates with their intervals, not single episodes: the service is not deterministic
   at temperature 0, and identical configurations have produced both wins and losses.

## Inspecting runs

```bash
python scripts/trace_run.py logs/runs/<file>.json         # compact turn-by-turn trace
python scripts/last_decisions.py logs/runs/<file>.json 5  # last decisions with reasoning tail
python scripts/tower_progress.py logs/runs/<file>.json    # floors, hero trajectory, loops
python scripts/audit_cot.py                               # truncations, repairs, fallbacks
python run_reliability.py --summary                       # regenerate results/reliability/SUMMARY.md
```

All of this is also visible in the platform: Live (running jobs), Logs (stored episodes) and Play
(full-size replay).
