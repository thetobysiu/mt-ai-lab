# Configuration

Settings are environment variables (or entries in `.env`). Unset means the default. Every result file
stores the settings it ran with under `config.env`.

## Endpoint and model

| Variable | Default | Meaning |
|---|---|---|
| `SAIA_API_KEY` | – | API key of the OpenAI-compatible endpoint |
| `SAIA_API_KEYS` | – | optional comma-separated key pool (rotated on rate limits) |
| `SAIA_BASE_URL` | `https://chat-ai.academiccloud.de/v1` | endpoint (GWDG SAIA); any OpenAI-compatible URL works |
| `MOTA_TASK_MODEL`, `MOTA_TASK_MODE` | from the preset | model id and `thinking` / `instruct` (`--preset`, `--task-model` override) |
| `THINKING_MAX_TOKENS` | 32768 | output cap per call including reasoning (tower runs used 8192) |
| `LLM_MAX_TOKENS` | 4096 | output cap for models without reasoning |
| `LLM_TIMEOUT` | 600 | seconds per call |
| `MOTA_EVAL_TEMPERATURE` | 0 | sampling temperature (`--temperature`) |
| `MOTA_DISABLE_STRUCTURED_OUTPUT` | unset | 1 = no constrained-decoding repair call |
| `MOTA_STREAM_REASONING` | unset | 1 = stream reasoning tokens into the run log |
| `MOTA_EXCLUSIVE_API` | unset | 1 = refuse to start a second model job while one is running |

### Model presets

Defined in `mota/optimizer/model_config.py`. The thesis used:

| Name in the thesis | Preset | Endpoint model | Mode |
|---|---|---|---|
| Qwen3.5-397B | `qwen3.5-397b` | qwen3.5-397b-a17b | thinking |
| Qwen3.6-35B | `qwen3.6-35b` | qwen3.6-35b-a3b | thinking |
| Qwen3.8-27B | `qwen3.8-27b` | qwen3.8-27b | thinking |
| DeepSeek-V4-Flash | `deepseek-v4-flash-think` | deepseek-v4-flash-0731 | thinking |
| DeepSeek-V4-Flash (no thinking) | `deepseek-v4-flash` | deepseek-v4-flash-0731 | instruct |
| Mistral Medium 3.5 | `mistral-medium-3.5` | mistral-medium-3.5-128b | instruct (no reasoning channel) |
| Llama-3.1-8B | `llama-3.1-8b` | meta-llama-3.1-8b-instruct | instruct |

Further presets (`gpt-oss-120b`, `gemma-4-31b`, `qwen3-instruct`, `qwen3-omni`, the OpenRouter and Groq
variants of Qwen3.8-27B) and deprecated ones kept for old labels are listed there too. Which presets
your endpoint serves: `python -c "from mota.optimizer.model_config import check_preset_availability as c; print(c())"`.

## Engine settings of the thesis configurations

| Variable | Final configuration | Meaning |
|---|---|---|
| `LOOKAHEAD_DEPTH` | 3 (tower 2) | gateways searched behind an action (`--lookahead`) |
| `CONVERSATION_HISTORY_TURNS` | 0 | earlier observations and answers included in each call (default 6) |
| `MOTA_ORDER_TWO_SIDED` | 1 | fight-order line in both directions, with the guard at the HP-rule threshold |
| `MOTA_FIGHT_KEY_FLOOD` | 1 | key line on fights, computed over the whole reachable region |
| `MOTA_PLAN_STEPS` | 1 | actions committed per call; 60 = long plan |
| `MOTA_PLAN_NO_REPLAN` | unset | with 60: a single call for the whole episode |
| `MOTA_PLAN_WORDING` | unset | `floor` = whole-floor wording of the long plan |
| `MOTA_BARE_OBS` | unset | 1 = bare observation |
| `MOTA_DISABLE_OVERRIDES` | unset | 1 = all assists and overrides off |
| `MOTA_SUPPRESS_HINTS` | unset | 0 / 1 = show / hide the annotations independently of the previous variable |
| `MOTA_STRATEGIC_OVERRIDES` | unset | 1 = restore the strategic overrides of the development phase |
| `MOTA_HP_RULE_PCT` | unset | threshold quoted by the engine lines that refer to the HP rule (default 40 single floors, 60 tower) |
| `MOTA_LEGACY_SEEDS` | unset | 1 = the earlier default prompts |
| `MOTA_COMPACT_PROMPT` | unset | 1 = legend in the system map, no per-turn item list |
| `MOTA_POTIONS_ON_DEMAND` | unset | 1 = potions are not collected automatically |
| `MOTA_EXECUTE_LETHAL_ONLY` | unset | 1 = execute the fatal fight when only lethal fights remain (default: end as stuck) |
| `MOTA_MONSTER_NAMES` | `en` | `en`, `zh` or `both` |

## Tower designs

Each tower design adds settings to the one before it (thesis Table 5.2 and Table F.5). Design 7, the
final design, uses all of these:

| Variable | Since design | Meaning |
|---|---|---|
| `MOTA_REMOTE_ACTIONS` | 2 | every reachable object on every visited floor is an action; travel inside the action |
| `MOTA_SHOP_ROUTE` | 2 | price the monsters on the way to a shop not yet reached |
| `MOTA_WAY_UP` | 4 | way-up line to the next floor, actions on the route tagged |
| `MOTA_TOWER_FIDELITY` | 5 | corrected engine (MT4 thief, Cross, item values of the game data, feathers, seals, ice gates) |
| `MOTA_TOWER_HP_FLOOR` | 0 from 5 | 1 = the engine enforces the 40 % rule (designs 1–4) |
| `MOTA_OFFER_LEVELUPS` | 5 | offer level-ups in the experience shops (the prompt forbids them) |
| `MOTA_PLAN_MEMORY` | 5 | the answer ends with a one-line plan shown at the next decision |
| `MOTA_NO_KEY_PURCHASE` | 5 | yellow and blue keys are not for sale; red keys are |
| `MOTA_WAYUP_COMBINED` | 5 | way-up line with purchases combined across shops |
| `MOTA_FREE_AFFORD` | 5 | what the affordable purchases do to each costly fight; prices and treasures |
| `MOTA_NPC_TRADES` | 6 | the MT15 trades are actions once affordable |
| `MOTA_KEY_RESERVE` | 6 | a door off the way up that leaves too few keys says so |
| `MOTA_AFTER_BATTLE` | 6 | after-battle scripts change monsters for the rest of the run |
| `MOTA_BUY_QUANTITY` | 7 | a purchase may carry `QUANTITY: n` |
| `MOTA_VAMPIRE_TAG` | 7 | monsters that take a share of current HP carry a vampire tag |
| `MOTA_EVENT_WAY` | 7 | event and seal lines state the way to the item or guard and the missing keys |
| `MOTA_BLUE_KEY_PURCHASE` | 7b | blue keys are for sale |
| `MOTA_RESUME_LOG`, `MOTA_RESUME_BEFORE_TURN` | – | continue a stored tower run from a turn |
| `MOTA_MULTI_FLOOR_MAX_TURNS` | – | turn limit of a tower run (`--max-turns`) |

## Prompt optimisation

| Variable | Default | Meaning |
|---|---|---|
| `MOTA_REFLECTION_MODEL` | qwen3.5-397b-a17b | teacher model |
| `MOTA_REFLECTION_MAX_TOKENS` | 8000 | teacher output cap |
| `MOTA_REFLECTION_TIMEOUT` | 900 | teacher timeout (seconds) |
| `GEPA_MAX_CALLS` | 50 | budget of the GEPA library runs |
| `GEPA_ROLLOUTS_PER_CANDIDATE` | 1 | episodes averaged per candidate |

## Paths and server

| Variable | Default | Meaning |
|---|---|---|
| `MOTA_GAME_ROOT` | `data/games` | folder that contains `24/project` (and optionally other projects) |
| `MOTA_LOGS_DIR` | `logs` | run logs, job manifests, prompt versions |
| `MOTA_RESULTS_DIR` | `results` | result files read by the platform |
| `DASHBOARD_PORT` | 8080 | first port tried by `python -m mota.dashboard` |
