"""
GEPA evaluator — runs an LLM through the MOTA game simulator and scores the result.
This is the core evaluation function that GEPA calls for each candidate prompt.
"""
from __future__ import annotations
import copy
import json
import os
import re
import sys
import time
from pathlib import Path
from openai import OpenAI
from pydantic import BaseModel, ValidationError


def _safe_print(msg: str) -> None:
    """Print with UTF-8 encoding to avoid UnicodeEncodeError on Windows cp1252."""
    try:
        sys.stdout.buffer.write((str(msg) + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        print(str(msg).encode("ascii", errors="replace").decode("ascii"))

from ..game.types import Hero, Keys
from ..game.floor_loader import load_floor
from ..game.state import GameState
from ..game.data import GameData
from ..game.ai_floor_loader import (
    ScenarioConfig, load_ai_floor, build_item_effects,
    build_monsters_lookup, build_shop_def,
)
from ..benchmark.scorer import score_run
from .model_config import get_task_model, should_use_no_think

# Lazy-initialized globals
_clients: list[OpenAI] = []
_client_idx: int = 0

_floor_data = None
_floor_hero: Hero | None = None  # Custom hero for single MOTA floor eval
_floor_removed: set[tuple[int, int]] | None = None  # Pre-removed entities (e.g. MT0 fairy)
_floor_goal: str = "clear_all_enemies"  # Goal for single MOTA floor eval
_scenario: ScenarioConfig | None = None
_game_data: GameData | None = None
_last_eval_result: dict | None = None  # Stores last evaluation result for GEPA wrapper
_last_llm_reasoning: str = ""  # Provider-supplied hidden reasoning from the most recent LLM call
_last_llm_truncated: bool = False  # finish_reason == "length" on the most recent LLM call


def get_last_eval_result() -> dict | None:
    """Return the detailed result dict from the last evaluate() or evaluate_oneshot() call."""
    return _last_eval_result


from ..paths import DATA_JS_24 as _DATA_JS, FLOORS_24 as _FLOORS_DIR, SINGLE_FLOORS as _AI_TEST_DIR


def _resolve_ai_test_floor_path(floor_ref: str | Path) -> Path:
    """Resolve AI test floor IDs like simple/complex to data/floors/*.txt."""
    path = Path(floor_ref)
    if path.exists():
        return path

    candidates = [_AI_TEST_DIR / path.name]
    if not path.suffix:
        candidates.append(_AI_TEST_DIR / f"{path.name}.txt")
        candidates += sorted(_AI_TEST_DIR.glob(f"*/{path.name}.txt"))  # hand01, gen05, ...

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return path


def _collect_api_keys() -> list[str]:
    """
    Collect API keys in priority order.

    Supports:
    - SAIA_API_KEYS="key1,key2,..." (rotation pool)
    - SAIA_API_KEY
    - OPENAI_API_KEY
    """
    keys: list[str] = []

    raw_pool = os.environ.get("SAIA_API_KEYS", "")
    if raw_pool:
        for token in raw_pool.replace(";", ",").split(","):
            key = token.strip()
            if key:
                keys.append(key)

    for env_name in ("SAIA_API_KEY", "OPENAI_API_KEY"):
        key = os.environ.get(env_name, "").strip()
        if key:
            keys.append(key)

    # Keep order but deduplicate.
    deduped: list[str] = []
    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def make_rotating_litellm_lm(
    model_name: str,
    *,
    api_keys: list[str] | None = None,
    base_url: str | None = None,
    max_attempts: int = 4,
    timeout_s: float = 300.0,
    max_tokens: int | None = None,
):
    """Build a LiteLLM callable that rotates across configured API keys.

    This mirrors the task-side OpenAI client pool used by ``_call_llm`` so GEPA
    reflection calls don't pin themselves to a single credential.
    """
    import litellm

    keys = api_keys if api_keys is not None else _collect_api_keys()
    resolved_keys = [key for key in keys if key]
    resolved_base_url = (
        base_url
        or os.environ.get("SAIA_BASE_URL")
        or os.environ.get("OPENAI_API_BASE", "https://chat-ai.academiccloud.de/v1")
    )
    key_idx = 0

    def _next_key() -> str | None:
        nonlocal key_idx
        if not resolved_keys:
            return None
        key = resolved_keys[key_idx % len(resolved_keys)]
        key_idx += 1
        return key

    def _lm(prompt: str | list[dict]) -> str:
        if isinstance(prompt, str):
            messages: list[dict] = [{"role": "user", "content": prompt}]
        else:
            messages = prompt

        last_error = None
        attempts = max(1, max_attempts)
        for attempt in range(attempts):
            key = _next_key()
            try:
                kwargs = {
                    "model": model_name,
                    "messages": messages,
                    "timeout": timeout_s,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if key:
                    kwargs["api_key"] = key
                if resolved_base_url and model_name.startswith("openai/"):
                    kwargs["base_url"] = resolved_base_url

                completion = litellm.completion(**kwargs)
                return completion.choices[0].message.content or ""
            except Exception as exc:
                last_error = exc
                error_str = str(exc)
                is_retryable = (
                    "429" in error_str
                    or "rate" in error_str.lower()
                    or "timeout" in error_str.lower()
                )
                if attempt < attempts - 1 and is_retryable:
                    print(
                        f"  [reflection-retry] attempt {attempt + 1}/{attempts} failed; rotating key and retrying"
                    )
                    time.sleep(min(15, 3 * (attempt + 1)))
                    continue
                raise

        if last_error is not None:
            raise last_error
        return ""

    return _lm


def _is_openrouter() -> bool:
    return "openrouter.ai" in (os.environ.get("SAIA_BASE_URL") or os.environ.get("OPENAI_API_BASE") or "")


def _is_groq() -> bool:
    return "api.groq.com" in (os.environ.get("SAIA_BASE_URL") or os.environ.get("OPENAI_API_BASE") or "")


def _get_client() -> OpenAI:
    global _clients, _client_idx
    if not _clients:
        keys = _collect_api_keys()
        base_url = os.environ.get("SAIA_BASE_URL") or os.environ.get("OPENAI_API_BASE",
                                  "https://chat-ai.academiccloud.de/v1")
        if _is_openrouter():  # the key comes from .env so it never lands in job manifests
            keys = [os.environ["OPENROUTER_API_KEY"]]
        elif _is_groq():
            keys = [os.environ["GROQ_API_KEY"]]
        if not keys:
            keys = [""]
        timeout_s = float(os.environ.get("LLM_TIMEOUT", "600.0"))
        _clients = [OpenAI(api_key=key, base_url=base_url, timeout=timeout_s) for key in keys]
        _client_idx = 0
    return _clients[_client_idx % len(_clients)]





def _rotate_client() -> None:
    global _client_idx
    if _clients:
        _client_idx = (_client_idx + 1) % len(_clients)


def _get_floor():
    global _floor_data
    if _floor_data is None:
        _floor_data = load_floor(_FLOORS_DIR / "MT3.js")
    return _floor_data


def _get_task_model(task_model: str | None = None) -> str:
    return task_model or get_task_model()


def configure_scenario(floor_path: str | Path | None = None, project_root: str | Path | None = None) -> str:
    """
    Configure which floor/scenario to evaluate.
    
    Args:
        floor_path: Path to a floor file. Supports:
            - None: Default MT3 walkthrough scenario
            - .js: MOTA project floor file (e.g., project/floors/MT3.js)
            - AI test floor ID or .txt file (e.g., simple, complex, data/floors/simple.txt)
        project_root: For .js floors of a *foreign* HTML5-mota project (e.g. 51/project): the
            project folder holding data.js/enemys.js/items.js/maps.js. Its tables are loaded through
            mota.game.project into a GameData; the built-in 24-layer tables stay the default.
    
    Returns:
        Description of the configured scenario.
    """
    global _scenario, _game_data, _floor_data, _floor_hero, _floor_removed, _floor_goal

    from ..game.state import set_hp_rule_pct
    set_hp_rule_pct(40)
    if floor_path is None:
        _scenario = None
        _game_data = None
        _floor_data = None
        _floor_hero = None
        _floor_removed = None
        _floor_goal = "clear_all_enemies"
        return "MT3 walkthrough (default)"

    path = _resolve_ai_test_floor_path(floor_path)
    if not path.exists():
        raise FileNotFoundError(f"Floor file not found: {floor_path}")

    if path.suffix == ".txt":
        _scenario = load_ai_floor(path)
        _floor_hero = None
        _floor_removed = None
        _floor_goal = _scenario.goal  # auto-detected: "boss" if tile 299 present, else "clear_all_enemies"
        # Build custom GameData
        monsters_lookup = build_monsters_lookup(_scenario.monsters)
        item_effects = build_item_effects(_scenario.item_bonuses)
        shops = build_shop_def(_scenario.shop, _scenario.name)
        # Build extra_enemy_tiles for tile IDs not in standard TILE_ENEMIES
        from ..game.data import TILE_ENEMIES
        extra_tiles = {}
        for tile_id, monster in _scenario.monsters.items():
            if tile_id not in TILE_ENEMIES:
                extra_tiles[tile_id] = monster.id
        _game_data = GameData(
            custom_monsters=monsters_lookup,
            custom_items=item_effects,
            custom_shops=shops,
            extra_enemy_tiles=extra_tiles,
        )
        _floor_data = None  # Use scenario's floor
        desc = (f"{_scenario.name}: {_scenario.floors[0].width}x{_scenario.floors[0].height}, "
                f"{len(_scenario.monsters)} enemies, hero HP={_scenario.hero.hp}")
        return desc

    elif path.suffix == ".js":
        _scenario = None
        _game_data = None
        _floor_data = load_floor(path)
        # Build a hero for this floor: use initial hero from data.js,
        # positioned at the floor's down_floor arrival point.
        from ..game.hero_loader import load_initial_hero
        if project_root is not None:
            from ..game.project import MotaProject
            proj = MotaProject.load(project_root)
            _game_data = proj.game_data()
            hero = proj.initial_hero()
        else:
            hero = load_initial_hero(_DATA_JS)
        # MT0 fairy NPC grants 1Y+1B+1R keys via dialogue (engine can't
        # simulate NPC scripts), so pre-grant them.
        if _floor_data.floor_id == "MT0" and project_root is None:
            hero.keys = Keys(yellow=1, blue=1, red=1)
            # Fairy NPC at (6,9) and (5,9) disappears after dialogue;
            # engine can't simulate NPC scripts, so pre-remove them.
            _floor_removed = {(6, 9), (5, 9)}
            _floor_goal = "stairs"  # No enemies on tutorial floor
        else:
            if _floor_data.floor_id != "MT0":
                hero.x, hero.y = _floor_data.down_floor
            _floor_removed = None
            _floor_goal = "clear_all_enemies"
        _floor_hero = hero
        src = f" [{Path(project_root).parent.name}/project]" if project_root is not None else ""
        return f"MOTA floor: {_floor_data.floor_id}{src}"

    else:
        raise ValueError(f"Unsupported floor file type: {path.suffix}")


def configure_mt3_scenario() -> str:
    """Configure MT3 with correct post-MT2 walkthrough hero stats."""
    global _scenario, _game_data, _floor_data, _floor_hero, _floor_removed, _floor_goal
    from ..game.state import set_hp_rule_pct
    set_hp_rule_pct(40)
    _scenario = None
    _game_data = None
    _floor_data = load_floor(_FLOORS_DIR / "MT3.js")
    _floor_hero = Hero(
        hp=860, atk=10, def_=10, mdef=0,
        money=4, exp=4,
        keys=Keys(yellow=1, blue=1, red=1),
        x=1, y=11,
    )
    _floor_removed = None
    _floor_goal = "clear_all_enemies"
    return "MT3 walkthrough (HP=860, ATK=10, DEF=10)"


def configure_mt4_scenario() -> str:
    """Configure MT4 with ideal MT3-finish hero stats — goal: reach stairs."""
    global _scenario, _game_data, _floor_data, _floor_hero, _floor_removed, _floor_goal
    from ..game.state import set_hp_rule_pct
    set_hp_rule_pct(40)
    _scenario = None
    _game_data = None
    _floor_data = load_floor(_FLOORS_DIR / "MT4.js")
    # Hero arrives on MT4 via the downstairs tile (the staircase back to MT3).
    # down_floor is the landing position adjacent to that staircase.
    down_x, down_y = _floor_data.down_floor
    _floor_hero = Hero(
        hp=448, atk=23, def_=17, mdef=0,
        money=23, exp=46,
        keys=Keys(yellow=6, blue=1, red=1),
        x=down_x, y=down_y,
    )
    _floor_removed = None
    _floor_goal = "stairs"
    return "MT4 test (HP=448, ATK=23, DEF=17, goal=stairs)"


def list_ai_test_floors() -> list[dict]:
    """List available AI test floors from data/floors/."""
    floors = []
    if _AI_TEST_DIR.exists():
        for f in sorted(_AI_TEST_DIR.glob("*.txt")):
            if f.stem.lower() == "readme":
                continue
            try:
                sc = load_ai_floor(f)
                floors.append({
                    "id": f.stem.lower(),
                    "path": str(f),
                    "name": f.name,
                    "size": f"{sc.floors[0].width}x{sc.floors[0].height}",
                    "enemies": len(sc.monsters),
                    "hero_hp": sc.hero.hp,
                    "has_shop": sc.shop is not None,
                    "goal": sc.goal,
                })
            except Exception as e:
                floors.append({"id": f.stem.lower(), "path": str(f), "name": f.name, "error": str(e)})
    return floors


def _create_state(lookahead_depth: int | None = None) -> GameState:
    """Create the game state for the configured scenario."""
    if _scenario is not None:
        return GameState(
            floor=_scenario.floors[0],
            hero=_scenario.hero.copy(),
            goal=_scenario.goal,
            max_turns=300,
            game_data=_game_data,
            lookahead_depth=lookahead_depth,
        )
    floor = _get_floor()
    if _floor_hero is not None:
        hero = _floor_hero.copy()
    else:
        # Default: MT3 walkthrough (hero state after clearing MT0–MT2)
        hero = Hero(
            hp=860, atk=10, def_=10, mdef=0,
            money=4, exp=4,
            keys=Keys(yellow=1, blue=1, red=1),
            x=1, y=11,
        )
    return GameState(floor=floor, hero=hero, goal=_floor_goal, max_turns=300,
                     lookahead_depth=lookahead_depth, _removed=_floor_removed,
                     game_data=_game_data)


def _create_mt3_state() -> GameState:
    """Create the MT3 game state from the walkthrough starting point (post MT0–MT2)."""
    floor = _get_floor()
    hero = Hero(
        hp=860, atk=10, def_=10, mdef=0,
        money=4, exp=4,
        keys=Keys(yellow=1, blue=1, red=1),
        x=1, y=11,
    )
    return GameState(floor=floor, hero=hero, goal="clear_all_enemies", max_turns=300)


def _call_llm(
    system_prompt: str,
    user_message: str,
    task_model: str | None = None,
    task_mode: str | None = None,
    prior_messages: list | None = None,
    temperature: float = 0.0,
    on_reasoning_chunk: "callable | None" = None,
) -> str:
    """Call the LLM with the given prompts. Returns the response text.

    Args:
        prior_messages: Optional list of prior {"role", "content"} dicts (conversation
            history) to include between the system message and the new user turn.
        on_reasoning_chunk: Optional callback fn(str) called with each reasoning token
            chunk as it streams in. If provided, uses streaming mode.
    """
    global _last_llm_reasoning, _last_llm_truncated
    _last_llm_truncated = False

    model = _get_task_model(task_model)
    delay = float(os.environ.get("LLM_CALL_DELAY", "0"))
    if delay > 0:
        time.sleep(delay)  # Rate limit protection (disabled by default)
    _last_llm_reasoning = ""

    no_think = should_use_no_think(model, task_mode)
    required_prefix = _required_output_prefix(user_message)
    final_user_content = user_message if not no_think else user_message + "\n/no_think"

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if prior_messages:
        messages.extend(prior_messages)
    messages.append({"role": "user", "content": final_user_content})

    for attempt in range(8 if _is_groq() else 4):
        client = _get_client()
        try:
            # Don't set max_tokens by default — let the LLM provider use its own limits
            # Only use LLM_MAX_TOKENS env var if explicitly set (for testing/fine control)
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if task_mode == "thinking":
                # SAIA/vLLM includes reasoning tokens in the max_tokens budget.
                # The model needs enough room for BOTH deep reasoning AND the visible
                # answer (ACTION: N).  E26 proved 32768 enables boss kills.
                # THINKING_MAX_TOKENS always takes priority for thinking models,
                # regardless of LLM_MAX_TOKENS (which is for non-thinking only).
                kwargs["max_tokens"] = int(os.environ.get("THINKING_MAX_TOKENS", "32768"))
                # Repetition penalty breaks the repetitive cycling pathology where
                # thinking models repeat the same paragraph 20+ times.
                rep_penalty = float(os.environ.get("THINKING_REPETITION_PENALTY", "1.05"))
                if rep_penalty > 1.0:
                    kwargs["extra_body"] = {"repetition_penalty": rep_penalty}
                if _is_openrouter():
                    kwargs.setdefault("extra_body", {})["reasoning"] = {"enabled": True}
                if _is_groq():  # Groq rejects unknown sampling fields; its "default" effort returned no reasoning
                    kwargs["extra_body"] = {"reasoning_format": "parsed", "reasoning_effort": "high"}
            else:
                max_tok_env = os.environ.get("LLM_MAX_TOKENS", "")
                if max_tok_env:
                    kwargs["max_tokens"] = int(max_tok_env)
                else:
                    kwargs["max_tokens"] = 4096  # Non-thinking: brief response is enough

            # --- Streaming mode (for live reasoning display) ---
            if on_reasoning_chunk:
                kwargs["stream"] = True
                stream = client.chat.completions.create(**kwargs)
                reasoning_parts = []
                content_parts = []
                finish_reason = ""
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    fr = getattr(chunk.choices[0], "finish_reason", None)
                    if fr:
                        finish_reason = fr
                    # Reasoning tokens (OpenAI standard: reasoning_content on delta)
                    rc = getattr(delta, "reasoning_content", None)
                    if not rc:
                        extra_d = getattr(delta, "model_extra", None) or {}
                        rc = extra_d.get("reasoning_content", "") or extra_d.get("reasoning", "")
                    if rc:
                        reasoning_parts.append(rc)
                        try:
                            on_reasoning_chunk(rc)
                        except Exception:
                            pass
                    # Content tokens
                    if delta.content:
                        content_parts.append(delta.content)
                content = "".join(content_parts)
                reasoning = "".join(reasoning_parts)
            else:
                # --- Non-streaming mode ---
                resp = client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content or ""
                finish_reason = getattr(resp.choices[0], "finish_reason", None) or ""
                # Capture reasoning from the API response (SAIA/vLLM returns it
                # as a separate field instead of <think> tags in the content).
                reasoning = getattr(resp.choices[0].message, "reasoning", None) or ""
                if not reasoning:
                    # Also check model_extra (pydantic extra fields)
                    extra = getattr(resp.choices[0].message, "model_extra", None) or {}
                    reasoning = extra.get("reasoning", "")

            # --- Common post-processing ---
            if finish_reason == "length":
                _last_llm_truncated = True
                print(f"  ⚠️ Response TRUNCATED (finish_reason=length, max_tokens={kwargs.get('max_tokens')})")
            # Some thinking models (e.g. LFM2.5 on OpenRouter) put all output in
            # `reasoning` when max_tokens is exhausted before the final answer.
            # Fall back to reasoning content so the parser can at least attempt to
            # extract an action ID from the chain-of-thought.
            if not content:
                content = reasoning
            _last_llm_reasoning = (reasoning or "").strip()
            # If reasoning was in content (not separate field), extract it for thesis
            if not _last_llm_reasoning and content:
                # Content may contain inline reasoning before FINAL_CHOICE
                fc_match = re.search(r'(?:FINAL_CHOICE|ACTION)\s*:\s*\d+', content, re.IGNORECASE)
                if fc_match and fc_match.start() > 100:
                    # Everything before FINAL_CHOICE is reasoning
                    _last_llm_reasoning = content[:fc_match.start()].strip()
            if required_prefix:
                visible_content = _visible_response_text(content)
                if visible_content and visible_content.lstrip().upper().startswith(required_prefix.upper()):
                    return visible_content
                # Content doesn't start with prefix — search for FINAL_CHOICE anywhere
                # in content (reasoning may precede it); keep the lines after it (NEXT: plan).
                fc_in_content = re.search(r'((?:FINAL_CHOICE|ACTION)\s*:\s*\d+.*)', content, re.IGNORECASE)
                if fc_in_content:
                    nxt = re.findall(r'NEXT\s*:[^\n]*', content[fc_in_content.end():], re.IGNORECASE)
                    return fc_in_content.group(1).strip() + (f"\n{nxt[0].strip()}" if nxt else "")
                # Try the separate reasoning field
                if reasoning:
                    m = re.search(r'(?:FINAL_CHOICE|ACTION)\s*:\s*(\d+)', reasoning, re.IGNORECASE)
                    if m:
                        nxt = re.findall(r'NEXT\s*:[^\n]*', reasoning[m.end():], re.IGNORECASE)
                        return f"FINAL_CHOICE: {m.group(1)}" + (f"\n{nxt[0]}" if nxt else "")
                # Last resort: return full content (parser will scan for any number)
            # Synthesize <think> tags so downstream extraction works uniformly
            if reasoning and "<think>" not in content and not required_prefix:
                content = f"<think>\n{reasoning}\n</think>\n{content}"
            return content
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate" in error_str.lower():
                if len(_clients) > 1:
                    _rotate_client()
                wait = (attempt + 1) * 15  # Longer waits for rate limits
                retry_after = (getattr(getattr(e, "response", None), "headers", None) or {}).get("retry-after")
                if retry_after:
                    try:
                        wait = max(wait, float(retry_after) + 1)
                    except ValueError:
                        pass
                print(f"  [rate-limit] Waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            if attempt < 3:
                time.sleep(3)
                continue
            raise
    return ""


def _is_truncated_response(response: str) -> bool:
    """Detect token-limit truncation: provider finish_reason=length on the last call, or
    <think> opened but never closed / nothing after it.

    The provider flag matters for SAIA/vLLM thinking models: when the budget is exhausted
    the visible content is EMPTY and _call_llm substitutes the reasoning text, which has no
    <think> tags at all, so tag-based detection alone misses it (tower run 5, turn 46)."""
    if _last_llm_truncated:
        return True
    has_open = '<think>' in response.lower()
    has_close = '</think>' in response.lower()
    if has_open and not has_close:
        return True  # cut off mid-think
    # Also detect: response ends with FINAL_CHOICE text missing even after </think>
    after_think = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE).strip()
    if not after_think and has_open:
        return True  # entire non-think output is empty
    return False


def _missing_path_response(response: str) -> bool:
    """Detect a complete (non-truncated) response that still has no PATH: or FINAL_CHOICE:."""
    if _is_truncated_response(response):
        return False  # handled separately
    cleaned = _visible_response_text(response)
    if not cleaned:
        return True
    has_path = bool(re.search(r'PATH\s*:', cleaned, re.IGNORECASE))
    has_final = bool(re.search(r'FINAL_CHOICE\s*:|ACTION\s*:', cleaned, re.IGNORECASE))
    has_plan = bool(re.search(r'PLAN\s*:', cleaned, re.IGNORECASE))
    return not (has_path or has_final or has_plan)


def _visible_response_text(response: str) -> str:
    """Return the visible answer text with any <think> block removed."""
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
    return cleaned if cleaned else response.strip()


def _required_output_prefix(user_message: str) -> str | None:
    """Infer the exact leading token contract requested by the caller."""
    if re.search(r'FINAL_CHOICE\s*:\s*<number>', user_message, re.IGNORECASE):
        return 'FINAL_CHOICE:'
    if re.search(r'PATH\s*:', user_message, re.IGNORECASE):
        return 'PATH:'
    if re.search(r'PLAN\s*:', user_message, re.IGNORECASE):
        return 'PLAN:'
    return None


def _violates_required_prefix(response: str, required_prefix: str | None) -> bool:
    """Check whether the visible response breaks a required prefix contract."""
    if not required_prefix:
        return False
    visible = _visible_response_text(response)
    if not visible:
        return True
    return not visible.lstrip().upper().startswith(required_prefix.upper())


def _parse_action_id(
    response: str,
    valid_ids: set[int] | None = None,
) -> int | None:
    """Parse ACTION: <number> from LLM response. Also accepts FINAL_CHOICE: for backwards
    compatibility. Allows full reasoning before the answer."""
    def _pick_valid(candidates: list[int]) -> int | None:
        if not candidates:
            return None
        if valid_ids is None:
            return candidates[-1]
        for cid in reversed(candidates):
            if cid in valid_ids:
                return cid
        return None

    # Search FULL response (including inside <think>) for explicit answer tokens.
    # ACTION: is the primary format; FINAL_CHOICE: is also accepted for compatibility.
    all_action = re.findall(r'(?:ACTION|FINAL_CHOICE):\s*(\d+)', response, re.IGNORECASE)
    picked = _pick_valid([int(m) for m in all_action])
    if picked is not None:
        return picked

    # Strip thinking tags for softer matching.
    cleaned = _visible_response_text(response)

    # "choose <number>" / "select <number>" / "pick <number>"
    matches = re.findall(r'(?:action|choose|select|pick)\s*[:=]?\s*(\d+)', cleaned, re.IGNORECASE)
    picked = _pick_valid([int(m) for m in matches])
    if picked is not None:
        return picked

    # Ultra-conservative: bare numeric final line only.
    tail_lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    if tail_lines and re.fullmatch(r'\d+', tail_lines[-1]):
        picked = _pick_valid([int(tail_lines[-1])])
        if picked is not None:
            return picked

    return None


class ActionChoice(BaseModel):
    """Schema for the constrained repair call: the model may only name a legal action."""
    action_id: int


_MEMORY_LIMIT = 600


def _llm_memory_enabled() -> bool:
    return os.environ.get("MOTA_LLM_MEMORY", "").strip().lower() in ("1", "true", "yes")


def _with_memory(user_msg: str, notes: str, floor_id: str) -> str:
    """LLM-side memory shown every turn: the model's own notes, written at floor changes."""
    shown = notes if notes else "(none yet — written when you leave a floor)"
    return f"YOUR NOTES (written by you when you changed floors; you are now on {floor_id}):\n{shown}\n\n{user_msg}"


_MEMORY_SYSTEM = (
    "You keep the notes of an agent playing Magic Tower across many floors. The agent sees only its notes "
    "and the current floor, so the notes are its whole memory of other floors. Write concise, general facts: "
    "what each visited floor still holds (fights worth coming back for once stats are higher, items, doors "
    "needing keys, shops and what they sell), what the next floors seemed to need, and what to buy or collect "
    "next. No reasoning, only the notes.")


def _update_memory(notes: str, recent: list[str], state_text: str, left: str, entered: str,
                   task_model: str | None) -> str:
    """One no-think call at each floor change (the agent's answers ignored an in-turn NOTES line on 9/9
    turns: the output contract ends at FINAL_CHOICE). Returns the new notes (old ones on failure)."""
    msg = (f"PREVIOUS NOTES:\n{notes or '(none)'}\n\nACTIONS SINCE THE LAST NOTE:\n" + "\n".join(recent[-25:]) +
           f"\n\nThe agent just moved from {left} to {entered}. Current state:\n{state_text[:2500]}\n\n"
           f"Write the updated notes (max {_MEMORY_LIMIT} characters) as: NOTES: <text>")
    try:
        resp = _get_client().chat.completions.create(
            model=_get_task_model(task_model),
            messages=[{"role": "system", "content": _MEMORY_SYSTEM}, {"role": "user", "content": msg + "\n/no_think"}],
            temperature=0.0, max_tokens=500, extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # memory must never break the episode
        _safe_print(f"  [memory] update failed: {e}")
        return notes
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    m = re.search(r"NOTES\s*:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    new = (m.group(1) if m else text).strip()
    return new[:_MEMORY_LIMIT] or notes


def _repair_candidates(actions: list, valid_ids) -> set[int]:
    """R1: the no-think repair call chooses among actions the mechanical override would not replace.

    B11 (2026-09-25): after 8 K truncations the repair picked the unwinnable boss on 12 turns and the
    override substituted the heuristic each time, so the episode was heuristic-driven.
    """
    from ..game.types import ActionType
    keep = {
        a.action_id for a in actions
        if a.action_id in valid_ids
        and not (a.type == ActionType.FIGHT and not a.can_win)
        and not getattr(a, "is_dead_end", False)
    }
    return keep or set(valid_ids)


def _structured_action_choice(
    system_prompt: str,
    state_text: str,
    actions_text: str,
    valid_ids: set[int],
    task_model: str | None = None,
    temperature: float = 0.0,
) -> int | None:
    """Force one legal action ID via provider-side constrained decoding.

    Used to repair a turn whose free-form answer was truncated or unparseable: the
    thinking budget is the usual culprit, so this call runs WITHOUT thinking and with
    a tiny token budget. Tries JSON-schema output, then vLLM `guided_choice`, then an
    unconstrained minimal prompt; returns None if every route fails.
    """
    if not valid_ids or os.environ.get("MOTA_DISABLE_STRUCTURED_OUTPUT"):
        return None

    model = _get_task_model(task_model)
    allowed = sorted(valid_ids)
    user_msg = (
        f"{state_text}\n\n{actions_text}\n\n"
        f"Reply with ONLY the number of the single best action. "
        f"Allowed values: {', '.join(str(i) for i in allowed)}."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        # /no_think is honoured by Qwen thinking models; harmless elsewhere.
        {"role": "user", "content": user_msg + "\n/no_think"},
    ]
    base = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": int(os.environ.get("STRUCTURED_MAX_TOKENS", "256")),
    }
    # vLLM/Qwen3: hard-disable thinking so the tiny budget is spent on the answer, not on
    # reasoning (qwen3.6-35b ignores /no_think and returned empty content 3x in a row).
    no_think = {"chat_template_kwargs": {"enable_thinking": False}}
    if _is_openrouter():
        no_think = {"reasoning": {"enabled": False}}
    elif _is_groq() or model.startswith("mistral"):  # SAIA Mistral: 400 on chat_template_kwargs; effort none|high only
        no_think = {"reasoning_effort": "none"}
    schema = {
        "type": "object",
        "properties": {"action_id": {"type": "integer", "enum": allowed}},
        "required": ["action_id"],
        "additionalProperties": False,
    }
    attempts = [
        ("json_schema", {**base, "extra_body": no_think, "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "action_choice", "schema": schema, "strict": True},
        }}),
        ("guided_choice", {**base, "extra_body": {**no_think, "guided_choice": [str(i) for i in allowed]}}),
        ("plain_nothink", {**base, "extra_body": no_think}),
        ("plain", base),
    ]

    for mode, kwargs in attempts:
        try:
            resp = _get_client().chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            content = (msg.content or "").strip()
            if not content:
                # Thinking consumed the budget: the answer, if any, is in the reasoning field.
                reasoning = getattr(msg, "reasoning", None) or (getattr(msg, "model_extra", None) or {}).get("reasoning", "")
                content = (reasoning or "").strip()
                if not content:
                    _safe_print(f"  [structured:{mode}] empty response")
                    continue
            if mode == "json_schema":
                try:
                    parsed = ActionChoice.model_validate_json(content)
                    if parsed.action_id in valid_ids:
                        _safe_print(f"  [structured:{mode}] -> {parsed.action_id}")
                        return parsed.action_id
                except ValidationError:
                    pass  # fall through to numeric scan of the same content
            for token in re.findall(r'-?\d+', content):
                if int(token) in valid_ids:
                    _safe_print(f"  [structured:{mode}] -> {token}")
                    return int(token)
        except Exception as e:  # unsupported parameter, transport error, rate limit
            _safe_print(f"  [structured:{mode}] unavailable ({type(e).__name__}: {str(e)[:80]})")
            continue
    return None


def _extract_llm_thinking(response: str) -> str:
    """Return hidden reasoning from the response text or the last provider-side reasoning field."""
    m = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return _last_llm_reasoning.strip()


def _extract_think_summary(response: str, max_chars: int = 800) -> str:
    """Extract and truncate thinking content from <think>...</think> tags or provider reasoning field."""
    m = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
    if not m:
        thinking = _last_llm_reasoning.strip()
        if not thinking:
            return ""
        if len(thinking) > max_chars:
            thinking = thinking[:max_chars] + "..."
        return thinking
    thinking = m.group(1).strip()
    if len(thinking) > max_chars:
        thinking = thinking[:max_chars] + "..."
    return thinking


def _preview_visible_response(response: str, max_chars: int = 500) -> str:
    """Return a short preview of the visible answer text without hidden reasoning."""
    return _visible_response_text(response)[:max_chars]


def _visible_history_response(response: str) -> str:
    """Return the assistant history text without hidden reasoning content."""
    return _visible_response_text(response)


def _pick_auto_collect_action(state: GameState, actions: list):
    """Return the highest-priority collect action, or None if none are available.

    With MOTA_POTIONS_ON_DEMAND=1, HP potions are left on the map as ordinary actions (the model
    decides when to drink them — some monsters deal %-HP damage) and only stat/key items are taken
    automatically. The state text already reports "HP + uncollected potions" as the reserve.
    """
    from ..game.types import ActionType, ItemTier

    on_demand = os.environ.get("MOTA_POTIONS_ON_DEMAND", "").lower() in ("1", "true", "yes")
    collect_actions = [
        action
        for action in actions
        if action.type == ActionType.COLLECT and not (on_demand and action.item_tier == ItemTier.HP)
    ]
    if not collect_actions:
        return None
    return max(collect_actions, key=lambda action: action.item_score)


def _compute_fight_save(state: GameState, action) -> int:
    """Return HP savings (current_damage - min_at_max_stats) for a fight action.
    Returns 0 for magic-atk, non-fight, or unwinnable fights.
    Mirrors the same calculation used in GameState.format_actions().
    """
    from ..game.types import ActionType
    from dataclasses import replace as dc_replace
    from ..game import damage as dmg

    if action.type != ActionType.FIGHT or not action.can_win:
        return 0
    mon = state.gd.get_monster(action.monster_id)
    if mon is None:
        return 0
    # Magic-atk ignores DEF — no savings from raising DEF
    if 2 in (mon.specials or []):
        return 0
    rem_def, rem_atk = state._compute_remaining_stat_gems()
    max_hero = dc_replace(state.hero, def_=state.hero.def_ + rem_def, atk=state.hero.atk + rem_atk)
    min_cost = dmg.calculate(max_hero, mon).total_damage
    return max(0, action.total_damage - min_cost)


def _deferred_fight_alternative(state: GameState, chosen_action, actions: list):
    """If chosen_action is an expensive fight with large HP savings, return a cheaper
    alternative action. Returns None if the fight should proceed (no better option exists).

    Active only on boss-goal floors. Defers fights where dmg≥80 AND save≥40 to ensure
    the boss chain (ball→boss) is entered with maximum HP. This is a deterministic
    strategic constraint analogous to auto-collect — not a parse-failure fallback.
    """
    from ..game.types import ActionType

    if state.goal != "boss":
        return None
    if chosen_action.type != ActionType.FIGHT:
        return None
    if not chosen_action.can_win:
        return None
    if chosen_action.total_damage < 80:
        return None
    save = _compute_fight_save(state, chosen_action)
    if save < 40:
        return None

    # Find alternatives that are NOT themselves deferred (cheaper or non-fight)
    alternatives = []
    for a in actions:
        if a.action_id == chosen_action.action_id:
            continue
        if a.type == ActionType.FIGHT:
            if not a.can_win:
                continue
            a_save = _compute_fight_save(state, a)
            if a.total_damage >= 80 and a_save >= 40:
                continue  # also deferred, skip
            # Magic-atk enemies have permanent, unreducible cost — never use as
            # deferral alternatives when expensive (damage >= 150).
            mon = state.gd.get_monster(a.monster_id) if hasattr(a, 'monster_id') else None
            if mon and 2 in (mon.specials or []) and a.total_damage >= 150:
                continue
        alternatives.append(a)

    if not alternatives:
        return None  # No alternative — must fight now (condition b)

    # Prefer: doors/collect/shop first, then lowest-damage fights
    def _alt_priority(a):
        if a.type in (ActionType.OPEN_DOOR, ActionType.COLLECT, ActionType.SHOP_BUY):
            return (0, 0)
        if a.type == ActionType.USE_STAIRS:
            return (1, 0)
        return (2, getattr(a, 'total_damage', 0))

    return min(alternatives, key=_alt_priority)


def _build_user_msg(
    state_text: str,
    actions_text: str,
) -> str:
    """Build the per-turn user message: state + available actions + format instruction."""
    msg = (
        f"{state_text}\n\n{actions_text}\n\n"
        "Choose the best action. After your analysis, end your response with:\n"
        "FINAL_CHOICE: <number>"
    )
    if _plan_memory_enabled() and _plan_steps() <= 1:
        msg = msg[: msg.rindex("Choose the best action.")] + (
            "Choose the best action. After your analysis, end your response with these two lines:\n"
            "PLAN: <your to-do list in one line, most urgent first: what you will do next and why, and what you are "
            "saving gold/EXP or keys for; it is shown to you at your next decision, because you do not see this "
            "reasoning again>\n"
            "FINAL_CHOICE: <number>")
    k = _plan_steps()
    if k > 1:
        if k <= 10:
            scope = f"exactly the next {k - 1} fight / door / staircase action(s) you will take after it"
        elif os.environ.get("MOTA_PLAN_WORDING") == "floor":  # wording of the round-7 whole-floor / one-shot cells
            scope = (f"your plan for the rest of this floor: every fight, door and staircase you will take after it, in "
                     f"order, up to the goal (at most {k - 1})")
        else:
            scope = (f"as many of the fight / door / staircase actions you will take after it as you can, in order "
                     f"(at most {k - 1})")
        msg += (f"\nThen, on the next line, commit to {scope}. Do not repeat the FINAL_CHOICE action itself; the "
                "first NEXT entry is the decision AFTER it:\n"
                "NEXT: <type> (x,y); <type> (x,y); ...\n"
                "(type = fight / open_door / use_stairs, with the target position; do not list items, they are "
                "collected automatically). They are executed without asking you again as long as each is still "
                "available; free items are picked up in between.")
    return msg


def _plan_memory_enabled() -> bool:
    """MOTA_PLAN_MEMORY=1: the model ends each answer with a one-line PLAN that is shown at its next decision
    (history is off since round 4, so without it the intention behind the previous choice is lost)."""
    return os.environ.get("MOTA_PLAN_MEMORY", "").strip().lower() in ("1", "true", "yes")


def _extract_plan_note(response: str | None) -> str | None:
    """Last 'PLAN: ...' line of the visible answer, else of the reasoning (thinking models wrote it there in every
    design-5 run of 2026-10-02 and answered only 'FINAL_CHOICE: n'), at most 400 characters."""
    if not response:
        return None
    visible = re.sub(r"<think>.*?</think>", "", response, flags=re.S)
    for text in (visible, _extract_llm_thinking(response) or "", globals().get("_last_llm_reasoning") or ""):
        found = re.findall(r"^\W*PLAN\W*:\s*(.+)$", text, flags=re.M | re.I)
        if found:
            return found[-1].strip().strip("*_ ").strip()[:400]
    return None


def _buy_quantity_enabled() -> bool:
    """MOTA_BUY_QUANTITY=1 (design 7, user 2026-10-05): a shop purchase may carry QUANTITY: n (at most 10); the same
    purchase is repeated without new calls while it is offered (design-6 397B run 1: 321 of 946 turns were single buys)."""
    return os.environ.get("MOTA_BUY_QUANTITY") == "1"


def _extract_quantity(response: str | None) -> int:
    """Last 'QUANTITY: n' of the visible answer, else of the reasoning; 1 if absent, capped at 10."""
    if not response:
        return 1
    visible = re.sub(r"<think>.*?</think>", "", response, flags=re.S)
    for text in (visible, _extract_llm_thinking(response) or ""):
        found = re.findall(r"^\W*QUANTITY\W*:\s*(\d+)", text, flags=re.M | re.I)
        if found:
            return max(1, min(10, int(found[-1])))
    return 1


def _with_plan_note(user_msg: str, note: str, turn: int, floor_id: str, since: list[str]) -> str:
    done = "; ".join(since[-12:]) if since else "nothing yet"
    return (f"YOUR PLAN FROM YOUR PREVIOUS DECISION (turn {turn}, on {floor_id}): {note}\n"
            f"Done since then (your choice first, then automatic steps): {done}.\n"
            "Follow it if it still holds at the current state; change it if the state below shows a better option.\n\n"
            + user_msg)


def _resume_tower_from_log(game, log_name: str, before_turn: int, emit) -> tuple | None:
    """MOTA_RESUME_LOG / MOTA_RESUME_BEFORE_TURN (user 2026-10-04): replay the turns of a stored tower run that come
    before `before_turn` on the current engine (each emitted as a forced turn), so a run can continue from a stored
    state. Returns the plan note of the last replayed decision, or None. Raises if a stored action is not offered."""
    from ..game.types import ActionType
    path = Path(log_name) if Path(log_name).exists() else Path(__file__).resolve().parents[2] / "logs" / "runs" / log_name
    events = json.loads(path.read_text(encoding="utf-8"))["turns"]
    turns = [t for t in events if t.get("type") == "turn" and int(t["turn"]) < before_turn]
    notes = {int(e["turn"]): e.get("note") for e in events if e.get("type") == "plan_note" and e.get("note")}
    plan = None
    for t in turns:
        acts = game.get_actions()
        want, fid = t["action"], t.get("floor_id")
        local = next((a for a in acts if a.label() == want and a.remote is None), None)
        remote = next((a for a in acts if a.remote is not None and a.remote.label() == want
                       and a.target_floor_id == fid), None)
        a = (remote or local) if fid != game.current_floor.floor_id else (local or remote)
        a = a or next((x for x in acts if x.label() == want), None) or next(
            (x for x in acts if x.remote is not None and x.remote.label() == want), None)
        if a is None:
            raise RuntimeError(f"resume: turn {t['turn']} '{want}' is not offered by the current engine")
        hist_idx = len(game.history)
        hero_before = _hero_dict_from_hero(game.hero)
        floor_before, idx_before = game.current_floor.floor_id, game.current_floor_idx
        game.apply_action(a)
        if int(t["turn"]) in notes:
            plan = (notes[int(t["turn"])], int(t["turn"]), fid, hist_idx)
        # same display fields as live turns, so the dashboard can draw every floor of the resumed part
        floor_changed = game.current_floor.floor_id != floor_before
        disp_idx = idx_before if floor_changed else game.current_floor_idx
        if a.remote is not None:
            disp_idx = game.current_floor_idx - (1 if a.remote.type == ActionType.USE_STAIRS else 0)
            floor_changed = a.remote.type == ActionType.USE_STAIRS
        hero = _hero_dict_from_hero(game.hero)
        if floor_changed:
            hero = dict(hero_before, **({"x": a.x, "y": a.y} if a.type == ActionType.USE_STAIRS else {}))
        detail = {"type": a.type.value, "x": a.x, "y": a.y, "name": a.name,
                  "is_dead_end": bool(getattr(a, "is_dead_end", False))}
        if a.type == ActionType.FIGHT:
            detail.update(damage=a.total_damage, hp_after=a.hp_after)
        emit({"type": "turn", "turn": game.total_turns, "action": want, "forced": True,
              "forced_reason": f"resumed from {path.name}", "hero": hero,
              "floor_id": game.floors[disp_idx].floor_id, "result_floor_id": game.current_floor.floor_id,
              "action_detail": detail,
              "removed": [list(r) for r in game.per_floor_removed.get(disp_idx, set())],
              "action_path": [list(p) for p in getattr(a, "path", [])]})
        if game.current_floor.floor_id != floor_before:
            emit({"type": "floor_change", "turn": game.total_turns, "floor_id": game.current_floor.floor_id,
                  "floor_idx": game.current_floor_idx, "hero": _hero_dict_from_hero(game.hero),
                  "map": _serialize_rich_map(game._make_state())})
    emit({"type": "resume", "log": path.name, "turns": len(turns), "floor_id": game.current_floor.floor_id,
          "hero": _hero_dict_from_hero(game.hero)})
    return plan


def _plan_steps() -> int:
    """MOTA_PLAN_STEPS=k (default 1): each LLM call chooses one action and commits to k-1 more."""
    try:
        return max(1, int(os.environ.get("MOTA_PLAN_STEPS", "1")))
    except ValueError:
        return 1


class _Plan(list):
    """Committed NEXT entries; `budget` = how many more decisions (fights/doors/stairs) may be executed."""
    budget = 0


def _parse_next_plan(response: str, limit: int, thinking: str | None = None) -> list[tuple[str, int, int]]:
    """NEXT: fight (3,5); open_door (7,0) -> [("fight", 3, 5), ("open_door", 7, 0)] from the visible answer.
    Every entry is kept (types are unreliable, matching is by position); `limit` caps the decisions executed."""
    visible = _visible_response_text(response or "")
    hits = re.findall(r"NEXT\s*:\s*(.+)", visible, re.IGNORECASE)
    if not hits:
        # Thinking models often draft the NEXT line in the reasoning and emit only FINAL_CHOICE.
        hits = re.findall(r"NEXT\s*:\s*(.+)", (thinking or "") + "\n" + (response or ""), re.IGNORECASE)
    if not hits:
        return []
    item_re = r"(fight|open_door|door|collect|use_stairs|stairs)\b[^()]*\(\s*(\d+)\s*,\s*(\d+)\s*\)"
    line = next((h for h in reversed(hits) if re.search(item_re, h, re.IGNORECASE)), "")  # skip echoed templates
    out = _Plan()
    for t, x, y in re.findall(item_re, line, re.IGNORECASE):
        t = t.lower()
        out.append(({"door": "open_door", "stairs": "use_stairs"}.get(t, t), int(x), int(y)))
    out.budget = limit
    return out


def _next_planned_action(plan_queue: list, actions: list, removed, floor=None) -> tuple:
    """Match the committed plan to the legal actions by POSITION (models mislabel types, e.g. 'collect' for
    a fight). Items and already-cleared tiles are skipped (auto-collected); a position with no legal
    fight/door/stairs action breaks the plan. Returns (action or None, remaining queue)."""
    from ..game.types import ActionType as _AT
    from ..game import data as _D
    q = _Plan(plan_queue)
    q.budget = getattr(plan_queue, "budget", len(plan_queue))
    while q and q.budget > 0:
        _, px, py = q.pop(0)
        here = [a for a in actions if (a.x, a.y) == (px, py)]
        act = next((a for a in here if a.type != _AT.COLLECT), None)
        if act is not None:
            # A step the safety override would replace ends the plan: the model re-decides, not the heuristic.
            if (act.type == _AT.FIGHT and (not act.can_win or (act.hp_after is not None and act.hp_after <= 0))) \
                    or (act.type == _AT.OPEN_DOOR and getattr(act, "is_dead_end", False)):
                return None, []
            q.budget -= 1
            return act, q
        tile_is_item = floor is not None and 0 <= py < floor.height and 0 <= px < floor.width \
            and _D.is_item(floor.map[py][px])
        if here or (px, py) in removed or tile_is_item:
            continue  # an item, or something already taken: not a decision
        return None, []
    return None, []


def _verify_plan(state: GameState, plan: list, auto_zero_fights: bool = True) -> dict:
    """Simulate a committed plan on a copy of `state` exactly as the single-floor loop executes it (forced
    single actions, auto-collect, auto-fight at 0 HP, position matching). Reports how many decisions are legal
    in order, the first break and why, and the predicted HP after each executed decision.
    Not modelled: the dead-end-door override (needs the annotated action list)."""
    from ..game.types import ActionType as _AT
    from ..game import data as _D
    s = copy.deepcopy(state)
    q = list(plan)
    steps, cleared, items, brk = [], 0, 0, None
    while q and not s.goal_reached and not s.failed:
        acts = s.get_actions(annotate=False)
        if not acts:
            brk = {"reason": "no actions left"}
            break
        auto = acts[0] if len(acts) == 1 and not (acts[0].type == _AT.FIGHT and not acts[0].can_win) else None
        auto = auto or _pick_auto_collect_action(s, acts)
        if auto is None and auto_zero_fights:
            auto = next((a for a in sorted(acts, key=lambda a: a.path_steps)
                         if a.type == _AT.FIGHT and a.can_win and a.total_damage == 0), None)
        if auto is not None:
            s.apply_action(auto)
            continue
        _, px, py = q[0]
        act = next((a for a in acts if (a.x, a.y) == (px, py) and a.type != _AT.COLLECT), None)
        if act is not None:
            if act.type == _AT.FIGHT and (not act.can_win or act.hp_after <= 0):
                brk = {"x": px, "y": py, "reason": "unwinnable" if not act.can_win else "lethal"}
                break
            s.apply_action(act)
            q.pop(0)
            steps.append({"type": act.type.value, "x": px, "y": py, "hp": s.hero.hp})
            continue
        inside = 0 <= py < s.floor.height and 0 <= px < s.floor.width
        tile = s.floor.map[py][px] if inside else None
        if inside and ((px, py) in s.removed or _D.is_item(tile)):
            q.pop(0)
            cleared += (px, py) in s.removed
            items += (px, py) not in s.removed
            continue
        reason = ("off the map" if not inside else
                  "monster not reachable yet" if _D.is_enemy(tile) else
                  "door not reachable or no key" if _D.is_door(tile) else
                  "stairs not reachable yet" if _D.is_stairs(tile) else
                  "wall" if _D.is_wall(tile) else "empty tile")
        brk = {"x": px, "y": py, "reason": reason}
        break
    return {"entries": len(plan), "legal": len(steps), "already_cleared": cleared, "items": items, "break": brk,
            "goal_reached": bool(s.goal_reached), "died": s.hero.hp <= 0, "final_hp": s.hero.hp, "steps": steps}


def evaluate(
    candidate_prompt: str,
    task_model: str | None = None,
    task_mode: str | None = None,
    temperature: float | None = None,
) -> float:
    """
    GEPA evaluator function.
    
    Runs the LLM (using candidate_prompt as system prompt) through the MT3 game 
    simulator and returns a composite score [0.0, 1.0].
    
    Logs detailed traces via gepa.optimize_anything.log() for GEPA reflection.
    """
    # Temperature: explicit param > env var > 0.0
    if temperature is None:
        temperature = float(os.environ.get("MOTA_EVAL_TEMPERATURE", "0.0"))
    try:
        import gepa.optimize_anything as oa
        # Check if we're actually inside a GEPA evaluator context
        # by testing if log works without warning
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            oa.log("__test__")
            _inside_gepa = not any("outside of an evaluator" in str(x.message) for x in w)
    except (ImportError, AttributeError):
        _inside_gepa = False

    def _log(msg):
        if _inside_gepa:
            oa.log(msg)
        else:
            # Force UTF-8 output so em-dashes, arrows etc. don't corrupt on Windows consoles
            try:
                import sys as _sys
                _sys.stdout.buffer.write((str(msg) + "\n").encode("utf-8", errors="replace"))
                _sys.stdout.buffer.flush()
            except Exception:
                print(str(msg))

    state = _create_state(lookahead_depth=None)
    _log(f"Starting evaluation ({state.floor.floor_id}): HP={state.hero.hp} ATK={state.hero.atk} DEF={state.hero.def_}")
    _log(f"Task model: {_get_task_model(task_model)} [{task_mode or ('thinking' if 'thinking' in _get_task_model(task_model) else 'instruct')}]")
    _log("TARGET (expert walkthrough): HP=448 ATK=23 DEF=17 in ~33 steps")

    # Build floor map once and append to system prompt so LLM has full spatial reference
    floor_map_text = state.format_floor_map()
    runtime_system_prompt = candidate_prompt + "\n\n" + floor_map_text

    # Per-run conversation history (sliding window of last N turn pairs)
    max_hist_turns = int(os.environ.get("CONVERSATION_HISTORY_TURNS", "6"))
    conversation_history: list[dict] = []

    consecutive_errors = 0
    max_parse_retries = 20  # safety cap — if LLM refuses to output ACTION: after this many tries, fail the run
    _eval_llm_calls = 0
    _eval_parse_errors = 0
    _eval_forced_turns = 0
    _eval_start_time = time.time()
    _eval_reasoning_log: list[dict] = []  # per-turn reasoning for thesis analysis

    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        actions = state.get_actions()
        if not actions:
            _log("No actions available — stuck!")
            state.failed = True
            state.failure_reason = "No actions available"
            break

        # If only one action, take it automatically — unless it's an unwinnable fight
        if len(actions) == 1:
            from ..game.types import ActionType as AT
            only = actions[0]
            if only.type == AT.FIGHT and not only.can_win:
                _log(f"Turn {state.turn + 1}: Only action is unwinnable fight — stopping")
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fight remains"
                break
            trace = state.apply_action(only)
            _log(f"Turn {trace.turn}: [forced] {trace.action.label()} -> HP={trace.hero_after['hp']}")
            consecutive_errors = 0
            _eval_forced_turns += 1
            continue

        # Auto-collect: take the best collect action immediately without LLM (always beneficial;
        # matches system-prompt rule "STEP 1: Any collect action? Take it immediately.")
        # Disable with MOTA_DISABLE_AUTO_COLLECT=1 for raw-LLM GEPA experiments.
        from ..game.types import ActionType as AT
        if not os.environ.get("MOTA_DISABLE_AUTO_COLLECT"):
            best_collect = _pick_auto_collect_action(state, actions)
            if best_collect is not None:
                trace = state.apply_action(best_collect)
                _log(f"Turn {trace.turn}: [auto-collect] {trace.action.label()} -> HP={trace.hero_after['hp']}")
                consecutive_errors = 0
                _eval_forced_turns += 1
                continue
            # A fight that costs 0 HP needs no judgement either (user rule 2026-09-23).
            free_fight = next((a for a in sorted(actions, key=lambda a: a.path_steps)
                               if a.type == AT.FIGHT and a.can_win and a.total_damage == 0), None)
            if free_fight is not None:
                trace = state.apply_action(free_fight)
                _log(f"Turn {trace.turn}: [auto-fight 0 HP] {trace.action.label()} -> HP={trace.hero_after['hp']}")
                consecutive_errors = 0
                _eval_forced_turns += 1
                continue

        # Build context for LLM
        state_text = state.format_state(actions=actions)
        actions_text = state.format_actions(actions)
        user_msg = _build_user_msg(state_text, actions_text)

        # Log available actions at decision points so GEPA reflection can diagnose wrong choices
        if _inside_gepa and len(actions) > 1:
            brief_actions = []
            for a in actions[:8]:  # cap at 8 to keep trace concise
                label = a.label()
                la = getattr(a, 'lookahead_value', None)
                if la and la > 0:
                    brief_actions.append(f"  #{a.action_id} {label} [lookahead={la:.0f}]")
                else:
                    brief_actions.append(f"  #{a.action_id} {label}")
            _log(f"Turn {state.turn + 1}: AVAILABLE ({len(actions)} options):\n" + "\n".join(brief_actions))

        valid_ids = {a.action_id for a in actions}
        # Call LLM with conversation history
        _eval_llm_calls += 1
        # Live heartbeat: when MOTA_STREAM_REASONING=1, stream reasoning tokens so the
        # operator can SEE the model is alive during long (32K-token) thinking turns
        # instead of staring at a silent gap (which feels "stuck").
        _hb = None
        if os.environ.get("MOTA_STREAM_REASONING") == "1":
            import sys as _sys2
            _hb_state = {"n": 0, "t0": time.time()}

            def _hb(chunk):
                _hb_state["n"] += len(chunk)
                # Print a dot every ~200 reasoning chars, with a token/elapsed counter
                if _hb_state["n"] // 200 != (_hb_state["n"] - len(chunk)) // 200:
                    el = int(time.time() - _hb_state["t0"])
                    _sys2.stdout.write(f"\r  Turn {state.turn + 1}: thinking… {_hb_state['n']} chars / {el}s ")
                    _sys2.stdout.flush()
            print(f"  Turn {state.turn + 1}: calling LLM…", flush=True)
        response = _call_llm(
            runtime_system_prompt, user_msg,
            task_model=task_model, task_mode=task_mode,
            prior_messages=conversation_history if conversation_history else None,
            temperature=temperature,
            on_reasoning_chunk=_hb,
        )
        if _hb is not None:
            print(flush=True)  # newline after the heartbeat line
        # Log LLM reasoning chain so GEPA reflection sees full thinking trace
        think_summary = _extract_think_summary(response)
        if think_summary:
            _log(f"Turn {state.turn + 1}: [thinking] {think_summary}")
        # Store full reasoning for thesis CoT analysis
        _eval_reasoning_log.append({
            "turn": state.turn + 1,
            "reasoning": _last_llm_reasoning,
            "answer": response[:500],  # visible answer (truncated for storage)
        })

        action_id = _parse_action_id(response, valid_ids=valid_ids)

        # If no valid action found, retry without heuristic fallback.
        # The LLM must produce a parseable ACTION: number — no shortcuts.
        if action_id is None or action_id not in valid_ids:
            # Repair first: a truncated/garbled answer usually means the thinking
            # budget was spent, so re-ask with constrained decoding and no thinking
            # instead of burning another full-length call on the same failure.
            repaired = _structured_action_choice(
                runtime_system_prompt, state_text, actions_text, _repair_candidates(actions, valid_ids),
                task_model=task_model, temperature=temperature,
            )
            if repaired is not None:
                _eval_parse_errors += 1
                _log(f"Turn {state.turn + 1}: [parse-error] unparseable answer repaired "
                     f"by constrained decoding -> {repaired}")
                action_id = repaired
        if action_id is None or action_id not in valid_ids:
            consecutive_errors += 1
            _eval_parse_errors += 1
            _log(f"Turn {state.turn + 1}: [parse-error #{consecutive_errors}] No valid ACTION in response "
                 f"(parsed={action_id}, valid={sorted(valid_ids)}) — retrying")
            if consecutive_errors >= max_parse_retries:
                _log(f"  -> LLM refused to produce parseable ACTION after {max_parse_retries} retries — run failed")
                state.failed = True
                state.failure_reason = f"LLM parse failure after {max_parse_retries} retries"
                break
            continue  # Always retry — no heuristic fallback

        chosen = next(a for a in actions if a.action_id == action_id)

        # Fight-deferral enforcement (boss-goal floors):
        # Defer expensive fights (dmg≥80, save≥40) when cheaper alternatives exist.
        # This preserves HP for the boss chain. E26 proved this enables boss kills.
        # Disable with MOTA_DISABLE_OVERRIDES=1 for raw-LLM GEPA experiments.
        if not os.environ.get("MOTA_DISABLE_OVERRIDES"):
            alt = _deferred_fight_alternative(state, chosen, actions)
            if alt is not None:
                _log(f"Turn {state.turn + 1}: [defer] {chosen.name}@({chosen.x},{chosen.y}) "
                     f"(dmg={chosen.total_damage}) -> {alt.name}@({alt.x},{alt.y})")
                chosen = alt

        # HP-floor deferral (boss-goal floors only):
        # If the chosen fight leaves hpAfter < 350 and non-fight alternatives exist,
        # defer it — routing should collect HP potions (via doors) before fighting.
        # Threshold 350 is calibrated so the hero has a safety buffer before big fights.
        # Disable with MOTA_DISABLE_OVERRIDES=1 for raw-LLM GEPA experiments.
        if not os.environ.get("MOTA_DISABLE_OVERRIDES"):
            if state.goal == "boss" and chosen.type.name == "FIGHT" and chosen.can_win:
                from ..game.types import ActionType as AT2
                non_fight_alts = [a for a in actions
                                  if a.action_id != chosen.action_id
                                  and a.type != AT2.FIGHT]
                if chosen.hp_after < 350 and non_fight_alts:
                    best_alt = min(non_fight_alts, key=lambda a: (
                        0 if a.type in (AT2.OPEN_DOOR, AT2.COLLECT, AT2.SHOP_BUY) else 1,
                        getattr(a, 'total_damage', 0),
                    ))
                    _log(f"Turn {state.turn + 1}: [hp-floor] defer {chosen.name}@({chosen.x},{chosen.y}) "
                         f"(hpAfter={chosen.hp_after}<350) -> {best_alt.name}@({best_alt.x},{best_alt.y})")
                    chosen = best_alt

        trace = state.apply_action(chosen)
        _log(f"Turn {trace.turn}: {trace.action.label()} -> HP={trace.hero_after['hp']} "
             f"ATK={trace.hero_after['atk']} DEF={trace.hero_after['def']}")
        consecutive_errors = 0

        # Update conversation history (keep last max_hist_turns turn pairs)
        # SAIA returns reasoning separately — response is already clean (no <think> tags).
        # Strip any leftover <think> blocks just in case (e.g. non-SAIA providers).
        history_response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        conversation_history.append({"role": "user", "content": user_msg})
        conversation_history.append({"role": "assistant", "content": history_response or response[:200]})
        max_msg = max_hist_turns * 2
        if len(conversation_history) > max_msg:
            conversation_history = conversation_history[len(conversation_history) - max_msg:]

    # Score the result
    global _last_eval_result
    fid = _scenario.name if _scenario else "mt3-walkthrough"
    result = score_run(state, fixture_id=fid)
    result["tracking"] = {
        "llm_calls": _eval_llm_calls,
        "parse_errors": _eval_parse_errors,
        "forced_turns": _eval_forced_turns,
        "elapsed_seconds": round(time.time() - _eval_start_time, 1),
        "seconds_per_call": round((time.time() - _eval_start_time) / max(1, _eval_llm_calls), 2),
    }
    result["history"] = [
        {"turn": t.turn, "action": t.action.label(), "hp": t.hero_after["hp"]}
        for t in state.history
    ]
    result["reasoning_log"] = _eval_reasoning_log
    _last_eval_result = result
    _log(f"\n=== RESULT ===")
    _log(f"Score: {result['total']:.3f}")
    _log(f"Completion: {result['completion']:.1%} ({result['details']['enemies_killed']}/{result['details']['enemies_total']})")
    _log(f"Final HP: {result['details']['final_hp']} (target: {result['details']['target_hp']})")
    _log(f"Final ATK={result['details']['hero_atk']} DEF={result['details']['hero_def']}")
    _log(f"Steps: {result['details']['steps']}")
    _log(f"Violations: {result['violations']}")
    if "mt3" in fid.lower():
        _log(
            f"DELTA vs expert: HP {result['details']['final_hp'] - 448:+d} | "
            f"ATK {result['details']['hero_atk'] - 23:+d} | "
            f"DEF {result['details']['hero_def'] - 17:+d} | "
            f"steps {result['details']['steps'] - 33:+d}"
        )

    return result["total"]


def evaluate_oneshot(
    candidate_prompt: str,
    task_model: str | None = None,
    task_mode: str | None = None,
    on_event=None,
    should_stop=None,
) -> float:
    """
    One-shot holistic planning evaluator.

    Sends the complete initial floor state to the LLM once, asks for a full
    coordinate-based priority plan (PLAN: (x1,y1), (x2,y2), ...), then executes
    it greedily turn-by-turn matching by (x,y) coordinates.

    Falls back to the heuristic for newly-unlocked actions not in the original plan.
    This represents Architecture B in the thesis: holistic vs. turn-by-turn reactive.

    on_event (optional) receives the same event stream as evaluate_with_callback
    (start / thinking / thinking_result / plan / turn / stuck / result) for the dashboard.
    """
    def emit(event):
        if on_event:
            on_event(event)

    def turn_event(trace, action, *, forced: bool, fallback: bool = False, extra: dict | None = None):
        if not on_event:
            return
        ev = {
            "type": "turn", "turn": trace.turn, "action": trace.action.label(), "action_id": action.action_id,
            "forced": forced, "fallback": fallback, "hero": _hero_dict(state),
            "enemies_remaining": state.remaining_enemies(), "removed": [list(r) for r in state.removed],
            "sub_steps": trace.sub_steps, "action_path": [list(p) for p in getattr(action, "path", [])],
            "action_detail": {"type": action.type.value, "x": action.x, "y": action.y, "name": action.name},
        }
        if extra:
            ev.update(extra)
        emit(ev)

    state = _create_state(lookahead_depth=None)
    floor_map_text = state.format_floor_map()
    runtime_system_prompt = candidate_prompt + "\n\n" + floor_map_text
    resolved_task_model = _get_task_model(task_model)

    initial_actions = state.get_actions()
    if not initial_actions:
        fid = _scenario.name if _scenario else "mt3-walkthrough"
        result = score_run(state, fixture_id=fid)
        emit({"type": "result", **result})
        return result["total"]

    state_text = state.format_state()
    actions_text = state.format_actions(initial_actions)
    emit({
        "type": "start", "floor_id": state.floor.floor_id, "hero": _hero_dict(state),
        "initial_enemies": state.initial_enemies, "state_text": state_text, "mode": "oneshot",
        "task_model": resolved_task_model,
        "task_mode": task_mode or ("thinking" if "thinking" in resolved_task_model else "instruct"),
        "map": _serialize_rich_map(state), "runtime_system_prompt": runtime_system_prompt,
    })

    # Build explicit (x,y) listing so the LLM can reference stable coordinates
    coord_listing = "\n".join(
        f"  ({a.x},{a.y}) {a.name} [{a.type.value if hasattr(a.type, 'value') else a.type}]"
        + (f" dmg={a.total_damage}" if getattr(a, "total_damage", 0) else "")
        for a in initial_actions
    )

    user_msg = (
        f"{state_text}\n\n"
        f"{actions_text}\n\n"
        f"Entity coordinates for planning:\n{coord_listing}\n\n"
        "ONE-SHOT PLANNING MODE: Using the floor map and all visible entities above, "
        "output your complete strategic plan for this floor as an ordered list of "
        "entity coordinates. List every entity you intend to act on, in optimal order.\n"
        "Reply: PLAN: (x1,y1), (x2,y2), (x3,y3), ..."
    )

    _oneshot_start_time = time.time()
    emit({"type": "thinking", "turn": 0, "state_text": state_text, "actions_text": actions_text, "user_message": user_msg})
    response = _call_llm(
        runtime_system_prompt, user_msg,
        task_model=task_model, task_mode=task_mode,
    )
    plan_coords = _parse_coord_plan(response)
    _oneshot_fallbacks = 0
    if on_event:
        thinking_text = _extract_llm_thinking(response)
        emit({"type": "thinking_result", "turn": 0, "thinking": thinking_text or "",
              "response_preview": (response or "")[-400:]})
        emit({"type": "plan", "turn": 0, "response": response, "coords": [list(c) for c in plan_coords],
              "elapsed_ms": int((time.time() - _oneshot_start_time) * 1000)})

    # Execute greedily using planned coordinates as stable entity keys
    plan_queue = list(plan_coords)
    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        if should_stop and should_stop():
            emit({"type": "stopped", "reason": "Stopped by user"})
            break
        actions = state.get_actions()
        if not actions:
            state.failed = True
            state.failure_reason = "No actions available"
            emit({"type": "stuck", "reason": state.failure_reason})
            break

        # Auto-execute forced single actions
        if len(actions) == 1:
            from ..game.types import ActionType as AT
            only = actions[0]
            if only.type == AT.FIGHT and not only.can_win:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fight remains"
                emit({"type": "stuck", "reason": state.failure_reason})
                break
            trace = state.apply_action(only)
            turn_event(trace, only, forced=True)
            continue

        # Auto-collect: pick up any available item before executing the next plan step.
        # Items unlocked mid-plan (e.g., gem behind a killed enemy) must be collected
        # immediately — they are always free and improve all subsequent fight costs.
        best_collect = _pick_auto_collect_action(state, actions)
        if best_collect is not None:
            trace = state.apply_action(best_collect)
            turn_event(trace, best_collect, forced=True)
            continue

        # Match next planned (x,y) to a currently available action
        coord_map = {(a.x, a.y): a for a in actions}
        chosen = None
        consumed = 0
        for i, coord in enumerate(plan_queue):
            if coord in coord_map:
                chosen = coord_map[coord]
                consumed = i + 1
                break

        fallback = False
        if chosen is not None:
            plan_queue = plan_queue[consumed:]
        else:
            # Heuristic fallback for newly-unlocked entities not in the original plan
            chosen_id = _heuristic_pick(actions, state)
            _oneshot_fallbacks += 1
            fallback = True
            if chosen_id is None:
                state.failed = True
                state.failure_reason = "Stuck — heuristic found no valid action"
                emit({"type": "stuck", "reason": state.failure_reason})
                break
            chosen = next(a for a in actions if a.action_id == chosen_id)

        trace = state.apply_action(chosen)
        turn_event(trace, chosen, forced=False, fallback=fallback,
                   extra={"plan_remaining": len(plan_queue)})

    global _last_eval_result
    fid = _scenario.name if _scenario else "mt3-walkthrough"
    result = score_run(state, fixture_id=fid)
    result["tracking"] = {
        "llm_calls": 1,
        "parse_errors": 0,
        "heuristic_fallbacks": _oneshot_fallbacks,
        "forced_turns": 0,
        "plan_coords_count": len(plan_coords),
        "elapsed_seconds": round(time.time() - _oneshot_start_time, 1),
    }
    _last_eval_result = result
    if on_event:
        result_ev = dict(result)
        result_ev["hero"] = _hero_dict(state)
        emit({"type": "result", **result_ev})

    print(f"\n=== RESULT (oneshot) ===")
    print(f"Score: {result['total']:.3f}")
    print(f"Completion: {result['completion']:.1%} ({result['details']['enemies_killed']}/{result['details']['enemies_total']})")
    print(f"Final HP: {result['details']['final_hp']} (target: {result['details']['target_hp']})")
    print(f"Final ATK={result['details']['hero_atk']} DEF={result['details']['hero_def']}")
    print(f"Steps: {result['details']['steps']}")
    print(f"Violations: {result['violations']}")
    print(f"LLM calls: 1 | Heuristic fallbacks: {_oneshot_fallbacks} | Plan coords: {len(plan_coords)}")

    return result["total"]


# ---------------------------------------------------------------------------
# Multi-step Tree Planning — decision tree builder, formatter, and parser
# ---------------------------------------------------------------------------


def _clone_state(state) -> 'GameState':
    """Create an independent shallow copy of a GameState for tree simulation."""
    return GameState(
        floor=state.floor,
        hero=state.hero.copy(),
        goal=state.goal,
        max_turns=state.max_turns,
        game_data=state.gd,
        lookahead_depth=state.lookahead_depth,
        _removed=set(state.removed),
    )


_SPECIAL_LABELS = {
    1: "first-strike", 2: "magic-atk", 3: "solid",
    4: "2x-combo", 5: "3x-combo", 6: "Nx-combo",
    7: "break-armor", 8: "counter", 9: "purify", 10: "mimic",
}


def _rank_actions_for_tree(actions: list, state) -> list:
    """Rank actions for tree branching — only meaningful decision points.

    Sort by effective cost (damage - lookahead) so BFS-aligned low-cost
    fights with high unlock value are preferred over expensive fights.
    """
    from ..game.types import ActionType

    meaningful = []
    for a in actions:
        # Skip auto-collectible items (handled by _auto_collect_free)
        if a.type == ActionType.COLLECT:
            continue
        if a.type == ActionType.FIGHT and not a.can_win:
            continue
        if a.type == ActionType.OPEN_DOOR and getattr(a, 'is_dead_end', False):
            continue
        meaningful.append(a)
    if not meaningful:
        meaningful = [a for a in actions if a.type != ActionType.FIGHT or a.can_win]

    def _sort_key(a):
        if a.type == ActionType.OPEN_DOOR:
            la = getattr(a, 'lookahead_value', 0)
            # Only prioritize doors with positive net lookahead
            if la > 0:
                return (0, -la)
            else:
                return (2, 0)  # Zero/negative lookahead doors after good fights
        if a.type == ActionType.FIGHT:
            # Sort by effective cost: damage minus lookahead value
            # Lower effective cost = better value per HP spent
            eff = a.total_damage - getattr(a, 'lookahead_value', 0)
            return (1, eff)
        if a.type == ActionType.USE_STAIRS:
            return (3, 0)
        return (4, 0)

    meaningful.sort(key=_sort_key)
    return meaningful


def _auto_collect_free(state) -> list[str]:
    """Apply all free collectibles and zero-cost fights.

    Returns list of descriptions of collected items (e.g. "+1 ATK", "Yellow Key").
    """
    from ..game.types import ActionType
    collected: list[str] = []
    for _ in range(50):
        actions = state.get_actions()
        free = next(
            (
                a
                for a in actions
                if a.type == ActionType.COLLECT
            ),
            None,
        )
        if free is None:
            free = next(
                (
                    a
                    for a in actions
                    if a.type == ActionType.FIGHT and getattr(a, 'total_damage', 0) == 0
                ),
                None,
            )
        if free is None:
            break
        collected.append(free.name)
        state.apply_action(free)
    return collected


def _build_decision_tree(
    state,
    depth: int,
    max_branches_per_level: tuple[int, ...] = (3, 3, 2),
) -> list[dict]:
    """Build a decision tree of possible action sequences.

    Each node stores FULL action detail (same info as format_actions) plus
    the resulting hero state after execution + auto-collect.
    """
    from ..game.types import ActionType

    if depth <= 0:
        return []

    actions = state.get_actions()
    if not actions:
        return []

    ranked = _rank_actions_for_tree(actions, state)
    branch_limit = max_branches_per_level[0] if max_branches_per_level else 3
    ranked = ranked[:branch_limit]

    child_limits = max_branches_per_level[1:] if len(max_branches_per_level) > 1 else (2,)

    tree = []
    for action in ranked:
        child_state = _clone_state(state)
        child_actions = child_state.get_actions()
        match = next(
            (a for a in child_actions
             if a.x == action.x and a.y == action.y and a.type == action.type),
            None,
        )
        if match is None:
            continue

        child_state.apply_action(match)
        auto_desc = _auto_collect_free(child_state)
        children = _build_decision_tree(child_state, depth - 1, child_limits)

        # Risk level
        risk = ""
        if action.type == ActionType.FIGHT:
            dp = getattr(action, 'damage_percent', 0)
            risk = "RISKY" if dp > 30 else ("MODERATE" if dp > 15 else "SAFE")

        # Monster stats and specials
        specials = ""
        mon_atk = 0
        mon_def = 0
        def_threshold = ""
        specials_raw = []
        if action.type == ActionType.FIGHT and hasattr(action, 'monster_id'):
            try:
                mon = state.gd.get_monster(action.monster_id)
                mon_atk = mon.atk
                mon_def = mon.def_
                specials_raw = mon.specials
                sl = [_SPECIAL_LABELS[s] for s in mon.specials if s in _SPECIAL_LABELS]
                specials = ",".join(sl) if sl else ""
                # DEF threshold hint
                if 2 not in specials_raw:  # magic-atk ignores DEF
                    def_gap = mon.atk - state.hero.def_
                    if def_gap > 0:
                        def_threshold = f"FREE if DEF≥{mon.atk}, need +{def_gap} more"
                    else:
                        def_threshold = f"already immune: DEF≥monATK"
                else:
                    def_threshold = "magic-atk: DEF useless"
            except Exception:
                pass

        # Optional (not needed for boss goal)
        is_optional = (
            state.goal == "boss"
            and action.type == ActionType.FIGHT
            and getattr(action, 'monster_id', '') != 'enemy_299'
            and not getattr(action, 'unlocks_tree', [])
        )

        # Lookahead info
        la_value = getattr(action, 'lookahead_value', 0)
        raw_la = getattr(action, 'raw_lookahead', la_value)
        gw_cost = getattr(action, 'gateway_cost', 0)
        eff_cost = (action.total_damage - la_value) if la_value else None

        tree.append({
            'action_id': action.action_id,
            'type': action.type.value,
            'label': action.label(),
            'x': action.x,
            'y': action.y,
            'name': action.name,
            'total_damage': getattr(action, 'total_damage', 0),
            'damage_percent': getattr(action, 'damage_percent', 0.0),
            'hp_after': child_state.hero.hp,
            'atk_after': child_state.hero.atk,
            'def_after': child_state.hero.def_,
            'keys_after': {
                'yellow': child_state.hero.keys.yellow,
                'blue': child_state.hero.keys.blue,
                'red': child_state.hero.keys.red,
            },
            'can_win': getattr(action, 'can_win', True),
            'monster_id': getattr(action, 'monster_id', ''),
            'mon_atk': mon_atk,
            'mon_def': mon_def,
            'specials': specials,
            'specials_raw': specials_raw,
            'def_threshold': def_threshold,
            'risk': risk,
            'is_optional': is_optional,
            'lookahead_value': la_value,
            'raw_lookahead': raw_la,
            'gateway_cost': gw_cost,
            'effective_cost': eff_cost,
            'unlocks_tree': getattr(action, 'unlocks_tree', []),
            'is_dead_end': getattr(action, 'is_dead_end', False),
            'item_tier': getattr(action, 'item_tier', None),
            'item_score': getattr(action, 'item_score', 0),
            'auto_collected': auto_desc,
            'children': children,
        })

    return tree


def _format_tree_prompt(tree: list[dict], depth: int, hero_summary: str,
                        auto_collected_before: list[str] | None = None) -> tuple[str, dict]:
    """Format a decision tree as Available Actions with N-step lookahead.

    Each node is formatted with the SAME rich detail as format_actions:
    damage%, lookahead, effective cost, DEF threshold, specials, unlocks tree.

    Labels: step 1 = A/B/C, step 2 = 1/2/3, step 3 = a/b/c (local per step, no redundancy).
    label_map keys are tuples of the path, e.g. ("A",), ("A","1"), ("A","1","a").
    Returns (prompt_text, label_map) where label_map maps path-tuple → tree node.
    """
    lines = [
        "Available actions:",
        "  (Note: lookahead = net HP-equivalent value unlocked by this action.",
        "   Negative lookahead means the content is also reachable via other paths — prefer alternatives.",
        "   effCost = raw damage minus net lookahead. Negative effCost = net positive value.",
        "   ⚠[SECONDARY PATH]: fighting this enemy has negative net value; its unlocks are better reached via other enemies.",
        "   ⚡[OPTIONAL]: enemy not needed for boss goal, skip unless free (effCost ≤ 0).",
        "   Each STEP shows lookahead from that state's perspective.)",
        "",
        f"  Current: {hero_summary}",
    ]
    if auto_collected_before:
        lines.append(f"  (Auto-collected first: {', '.join(auto_collected_before)})")
    lines.append("")

    # Labels cycle: level 0 = A/B/C, level 1 = 1/2/3, level 2 = a/b/c, level 3 = A/B/C, ...
    def _label_for_level(depth_level: int, index: int) -> str:
        cycle = depth_level % 3
        if cycle == 0:
            return chr(ord('A') + index)
        elif cycle == 1:
            return str(index + 1)
        else:
            return chr(ord('a') + index)

    # label_map: path-tuple → node, e.g. ("A",) → node, ("A","1") → child_node
    label_map: dict[tuple, dict] = {}

    def _format_node_rich(node: dict) -> str:
        """Format a tree node with full format_actions-style detail."""
        ntype = node['type']

        if ntype == 'fight':
            # Risk label
            risk = node.get('risk', '')
            if not node.get('can_win', True):
                risk = 'LETHAL'
            # Monster stats + specials
            spec_str = f" [{node['specials']}]" if node['specials'] else ""
            mon_stats = f"monATK={node['mon_atk']} monDEF={node['mon_def']}"
            # DEF threshold
            thresh = f" [{node['def_threshold']}]" if node.get('def_threshold') else ""
            # Lookahead/effcost — use actual net = raw - gw (can be negative)
            la = node.get('lookahead_value', 0)
            raw_la = node.get('raw_lookahead', la)
            gw = node.get('gateway_cost', 0)
            net_la = (raw_la - gw) if gw else la  # actual net lookahead
            if gw:
                la_str = f" lookahead={net_la}(raw={raw_la}-gw={gw})"
            elif la:
                la_str = f" lookahead={la}"
            elif raw_la > 0:
                la_str = f" lookahead=0(raw={raw_la}-gw={gw})"
            else:
                la_str = ""
            # effCost = damage - net_la; show for all fight actions when lookahead exists
            eff = node.get('effective_cost')
            if raw_la > 0 or gw > 0:
                eff_val = node.get('total_damage', 0) - net_la
                eff_str = f" effCost={eff_val}"
            else:
                eff_str = f" effCost={eff}" if eff is not None else ""
            # Secondary-path tag: when gw > raw_la, content is reachable via other enemies
            is_secondary = (gw > 0 and gw > raw_la)
            # Optional tag
            opt_str = "  \u26a1[OPTIONAL]" if node.get('is_optional') else ""
            if is_secondary and not opt_str:
                opt_str = "  \u26a0[SECONDARY PATH - prefer alternatives]"
            # Result state
            result = f"→ HP={node['hp_after']} ATK={node['atk_after']} DEF={node['def_after']}"
            ky = node['keys_after']
            key_parts = []
            if ky['yellow']: key_parts.append(f"Y={ky['yellow']}")
            if ky['blue']: key_parts.append(f"B={ky['blue']}")
            if ky['red']: key_parts.append(f"R={ky['red']}")
            key_str = f" Keys:{','.join(key_parts)}" if key_parts else ""

            return (
                f"[fight] {node['name']} at ({node['x']},{node['y']}) "
                f"— {mon_stats}{spec_str}{thresh} — "
                f"damage={node['total_damage']} ({node['damage_percent']:.1f}%) "
                f"hpAfter={node['hp_after']} [{risk}]{la_str}{eff_str}{opt_str} "
                f"{result}{key_str}"
            )

        elif ntype == 'open_door':
            dead_end = " [DEAD END - DO NOT OPEN]" if node.get('is_dead_end') else ""
            la = node.get('lookahead_value', 0)
            raw_la = node.get('raw_lookahead', la)
            gw = node.get('gateway_cost', 0)
            if gw:
                la_str = f" — net_lookahead={la}(raw={raw_la}-gw_cost={gw})"
            elif la:
                la_str = f" — lookahead={la}"
            else:
                la_str = ""
            result = f"→ HP={node['hp_after']} ATK={node['atk_after']} DEF={node['def_after']}"
            return (
                f"[open_door] {node['name']} at ({node['x']},{node['y']})"
                f"{dead_end}{la_str} {result}"
            )

        elif ntype == 'use_stairs':
            return f"[use_stairs] {node['name']} at ({node['x']},{node['y']})"

        else:
            return f"[{ntype}] {node['name']} at ({node['x']},{node['y']})"

    def _format_unlocks(node: dict, indent: str) -> list[str]:
        """Render unlocks_tree for a node, matching format_actions style."""
        tree_data = node.get('unlocks_tree', [])
        if not tree_data:
            return []
        enemies = [u for u in tree_data if u["type"] == "enemy"]
        rewards = [u for u in tree_data if u["type"] != "enemy"]
        direct = [u for u in rewards if not u["via"]]
        chained: dict[tuple, list] = {}
        for u in rewards:
            if u["via"]:
                key = tuple(u["via"])
                chained.setdefault(key, []).append(u)

        parts = []
        if enemies:
            enemy_labels = ", ".join(u["label"] for u in enemies)
            parts.append(f"{indent} → next fight: {enemy_labels}")
        if direct:
            labels = ", ".join(u["label"] for u in direct)
            parts.append(f"{indent} → unlocks: {labels}")
        for chain, items in sorted(chained.items(), key=lambda kv: (len(kv[0]), kv[0])):
            via_str = " → ".join(chain)
            labels = ", ".join(u["label"] for u in items)
            chain_indent = "  " * len(chain)
            parts.append(f"{indent}{chain_indent} → via [{via_str}]: {labels}")
        return parts

    def _emit_level(nodes: list[dict], level: int, current_path: tuple, indent: str):
        if not nodes:
            return
        step_label = f"STEP {level + 1}"
        if level == 0:
            lines.append(f"{indent}{step_label} — your immediate choices:")
        else:
            lines.append(f"{indent}{step_label}:")

        for i, node in enumerate(nodes):
            lbl = _label_for_level(level, i)
            node_path = current_path + (lbl,)
            label_map[node_path] = node
            line = f"{indent}  {lbl}. {_format_node_rich(node)}"
            lines.append(line)
            # Show unlocks tree only at level 0 — keeps inner nodes compact
            if level == 0:
                for ul in _format_unlocks(node, indent + "    "):
                    lines.append(ul)

        # Emit children grouped under each parent
        for i, node in enumerate(nodes):
            lbl = _label_for_level(level, i)
            node_path = current_path + (lbl,)
            if node['children']:
                auto_str = ""
                if node['auto_collected']:
                    auto_str = f" (auto-collected: {', '.join(node['auto_collected'])})"
                # Show the full path prefix so the LLM knows which branch we're under
                path_str = ", ".join(node_path)
                lines.append(f"{indent}  If {path_str}{auto_str}:")
                _emit_level(node['children'], level + 1, node_path, indent + "    ")

    _emit_level(tree, 0, (), "")

    lines.append("")
    lines.append(f"Choose a PATH of up to {depth} choices, one per STEP (local label for each step).")
    lines.append(f"YOUR RESPONSE MUST START WITH THIS EXACT LINE (before any explanation):")
    lines.append(f"PATH: <step1>, <step2>, ...")
    lines.append(f"Example: PATH: B, 2, a   (= pick B at step1, then 2nd option in step2, then option a)")
    lines.append(f"Then optionally explain your reasoning.")

    return "\n".join(lines), label_map


def _parse_tree_path(response: str, label_map: dict) -> list[int]:
    """Parse PATH: B, 2, a from LLM response into action_id sequence.

    PATH labels are local per-step: step1=A/B/C, step2=1/2/3, step3=a/b/c.
    label_map keys are tuples: ("A",), ("A","1"), ("A","1","a"), etc.
    Returns list of action_ids for the chosen path.
    """
    if not label_map:
        return []
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    if not cleaned:
        cleaned = response

    path_match = re.search(
        r'PATH\s*:\s*(.*?)(?:\n\n|\Z)', cleaned, re.DOTALL | re.IGNORECASE,
    )
    if not path_match:
        return []

    raw = path_match.group(1).strip()
    labels = [lbl.strip().rstrip(',') for lbl in re.split(r'[,\s]+', raw) if lbl.strip()]

    # Navigate tree sequentially using tuple path keys:
    # labels = ['B', '2', 'a'] → look up ("B",), ("B","2"), ("B","2","a")
    action_ids = []
    path: tuple = ()
    for lbl in labels:
        path = path + (lbl,)
        node = label_map.get(path)
        if node:
            action_ids.append(node['action_id'])
        else:
            # Unknown label for this step — stop navigating
            break

    return action_ids


def _resolve_tree_action(tree_action_id: int, available_actions: list, label_map: dict, tree_nodes: list = None):
    """Resolve a tree action_id to a real action by matching (x, y, type)."""
    target = None
    for node in label_map.values():
        if node.get('action_id') == tree_action_id:
            target = node
            break
    if target is None:
        return next((a for a in available_actions if a.action_id == tree_action_id), None)

    return next(
        (a for a in available_actions
         if a.x == target['x'] and a.y == target['y'] and a.type.value == target['type']),
        None,
    )


def evaluate_multistep(
    candidate_prompt: str,
    task_model: str | None = None,
    task_mode: str | None = None,
    chunk_size: int = 5,
) -> float:
    """
    Multi-step (chunked) planning evaluator.

    Instead of one action per LLM call (reactive) or one plan for the whole
    floor (one-shot), this approach asks the LLM to plan the next *chunk_size*
    actions at once.  When the chunk is exhausted or a planned action becomes
    invalid, the LLM is called again with the updated state.

    This represents **long-horizon planning**: fewer LLM calls than reactive,
    better state-awareness than one-shot (which never sees the updated state).

    Response format:  PLAN: 3, 1, 5, 2, 4   (action IDs in execution order)
    """
    state = _create_state(lookahead_depth=None)
    floor_map_text = state.format_floor_map()
    runtime_system_prompt = candidate_prompt + "\n\n" + floor_map_text

    _ms_start = time.time()
    _ms_llm_calls = 0
    _ms_fallbacks = 0
    _ms_parse_errors = 0
    _ms_plan_actions_total = 0  # How many planned actions were successfully executed

    plan_queue: list[int] = []  # Queued action IDs from current LLM plan
    last_label_map: dict = {}  # Label map from the last tree-plan call
    conversation_history: list[dict] = []
    max_hist_turns = int(os.environ.get("CONVERSATION_HISTORY_TURNS", "6"))
    consecutive_errors = 0
    max_consecutive_errors = 3

    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        actions = state.get_actions()
        if not actions:
            state.failed = True
            state.failure_reason = "No actions available"
            break

        # Auto-execute forced single actions
        if len(actions) == 1:
            from ..game.types import ActionType as AT
            only = actions[0]
            if only.type == AT.FIGHT and not only.can_win:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fight remains"
                break
            state.apply_action(only)
            continue

        # Try to use a queued plan action
        valid_ids = {a.action_id for a in actions}
        chosen = None

        while plan_queue:
            next_id = plan_queue.pop(0)
            # Try direct ID match first
            if next_id in valid_ids:
                chosen = next(a for a in actions if a.action_id == next_id)
                _ms_plan_actions_total += 1
                break
            # Try coordinate-based match (tree action_ids are from cloned state)
            resolved = _resolve_tree_action(next_id, actions, last_label_map)
            if resolved:
                chosen = resolved
                _ms_plan_actions_total += 1
                break
            # Action ID is no longer valid (monster died, door opened, etc.)
            # Skip it and try the next one

        if chosen is not None:
            # Execute the planned action (auto-collect free items first)
            auto = _pick_auto_priority_action(actions, state)
            if auto and auto.action_id != chosen.action_id:
                _safe_print(f"Turn {state.turn}: [auto] {auto.name} at ({auto.x},{auto.y})")
                state.apply_action(auto)
                continue
            _safe_print(f"Turn {state.turn}: [plan] {chosen.name} at ({chosen.x},{chosen.y}) -> HP={state.hero.hp}")
            state.apply_action(chosen)
            consecutive_errors = 0
            continue

        # Plan queue exhausted or empty — call LLM for a new chunk
        _safe_print(f"Turn {state.turn}: [calling LLM for tree-plan depth={chunk_size}...]")
        state_text = state.format_state()

        # Build decision tree on a clone (auto-collect forced actions first)
        tree_state = _clone_state(state)
        pre_auto = _auto_collect_free(tree_state)
        tree_actions = tree_state.get_actions()
        if len(tree_actions) <= 1:
            tree = []
        else:
            # For small chunk sizes, keep tree compact to avoid prompt-length/token issues.
            # chunk_size=2 → (2,2), chunk_size=3 → (2,2,2), larger → (3,3,2) default.
            if chunk_size <= 2:
                branch_limits = (2, 2)
            elif chunk_size == 3:
                branch_limits = (2, 2, 2)
            else:
                branch_limits = (3, 3, 2)  # default
            tree = _build_decision_tree(tree_state, depth=chunk_size, max_branches_per_level=branch_limits)
        if tree:
            h = tree_state.hero
            hero_sum = (
                f"HP={h.hp} ATK={h.atk} DEF={h.def_} "
                f"| Keys: Y={h.keys.yellow} B={h.keys.blue} R={h.keys.red}"
            )
            tree_prompt, label_map = _format_tree_prompt(
                tree, chunk_size, hero_sum, auto_collected_before=pre_auto or None,
            )
            last_label_map = label_map
            # Unified: state + tree (no separate actions_text)
            # For multistep, append explicit format reminder so the model doesn't omit PATH.
            path_example = "/".join(
                chr(ord('A') + i) if i % 3 == 0 else (str(i // 3 + 1) if i % 3 == 1 else chr(ord('a') + i // 9))
                for i in range(chunk_size)
            )
            user_msg = (
                f"{state_text}\n\n{tree_prompt}\n\n"
                f"Choose the best {chunk_size}-action sequence.\n"
                f"After your reasoning, output EXACTLY:\n"
                f"PATH: <label>/<label>/... (e.g. PATH: {path_example[:5]})\n"
                f"Use only the labels shown in the tree (A/B/C at step 1, 1/2/3 at step 2, a/b/c at step 3)."
            )
        else:
            label_map = {}
            last_label_map = {}
            actions_text = state.format_actions(actions)
            user_msg = (
                f"{state_text}\n\n{actions_text}\n\n"
                f"MULTI-STEP PLANNING: Choose the best {chunk_size} actions to execute in order.\n"
                f"Reply: PLAN: <id1>, <id2>, ..."
            )

        _ms_llm_calls += 1
        response = _call_llm(
            runtime_system_prompt, user_msg,
            task_model=task_model, task_mode=task_mode,
            prior_messages=conversation_history if conversation_history else None,
        )

        # Retry on truncated response (thinking models can exhaust tokens before emitting PATH)
        if _is_truncated_response(response):
            _ms_parse_errors += 1
            _safe_print(f"Turn {state.turn}: [multistep truncated] Response cut off — retrying")
            consecutive_errors += 1
            if consecutive_errors < max_consecutive_errors:
                continue

        # Parse tree-path response first, then fall back to flat plan
        plan_ids = _parse_tree_path(response, label_map)
        if not plan_ids:
            plan_ids = _parse_multistep_plan(response, valid_ids=valid_ids)
        # Cap plan to chunk_size to prevent over-execution
        if plan_ids:
            plan_ids = plan_ids[:chunk_size]
            _safe_print(f"  LLM returned plan: {plan_ids[:10]}")
        else:
            # Show what the model actually said (first 200 chars of non-think content)
            cleaned_for_debug = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()[:200]
            _safe_print(f"  [parse fail] LLM response (non-think, first 200): {cleaned_for_debug!r}")

        if not plan_ids:
            # Parsing failed — try single-action fallback
            _ms_parse_errors += 1
            single_id = _parse_action_id(response, valid_ids=valid_ids)
            if single_id is not None:
                plan_ids = [single_id]
            else:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    fallback_id = _heuristic_pick(actions, state)
                    if fallback_id is not None:
                        plan_ids = [fallback_id]
                        _ms_fallbacks += 1
                    consecutive_errors = 0
                if not plan_ids:
                    continue

        # Queue the plan (first action executes this turn, rest queued)
        plan_queue = list(plan_ids[1:])
        first_action = next((a for a in actions if a.action_id == plan_ids[0]), None)
        if first_action is None:
            # Tree IDs differ from current state — try coordinate match
            first_action = _resolve_tree_action(plan_ids[0], actions, last_label_map)
        if first_action is None:
            # Action not available yet (needs auto-collect first) — queue all and retry
            plan_queue = list(plan_ids)
            auto = _pick_auto_priority_action(actions, state)
            if auto:
                state.apply_action(auto)
            continue

        # Auto-collect free items before executing plan
        auto = _pick_auto_priority_action(actions, state)
        if auto and auto.action_id != first_action.action_id:
            plan_queue = [plan_ids[0]] + plan_queue  # Re-queue the first action
            state.apply_action(auto)
        else:
            state.apply_action(first_action)
            _ms_plan_actions_total += 1

        consecutive_errors = 0

        # Update conversation history
        # Strip <think> blocks to prevent context explosion with thinking models.
        history_response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        conversation_history.append({"role": "user", "content": user_msg})
        conversation_history.append({"role": "assistant", "content": history_response or response[:200]})
        max_msg = max_hist_turns * 2
        if len(conversation_history) > max_msg:
            conversation_history = conversation_history[len(conversation_history) - max_msg:]

    # Score
    global _last_eval_result
    fid = _scenario.name if _scenario else "mt3-walkthrough"
    result = score_run(state, fixture_id=fid)
    elapsed = time.time() - _ms_start
    result["tracking"] = {
        "llm_calls": _ms_llm_calls,
        "parse_errors": _ms_parse_errors,
        "heuristic_fallbacks": _ms_fallbacks,
        "forced_turns": 0,
        "plan_actions_executed": _ms_plan_actions_total,
        "chunk_size": chunk_size,
        "elapsed_seconds": round(elapsed, 1),
        "seconds_per_call": round(elapsed / max(1, _ms_llm_calls), 2),
    }
    _last_eval_result = result

    _safe_print(f"\n=== RESULT (multistep, chunk={chunk_size}) ===")
    _safe_print(f"Score: {result['total']:.3f}")
    _safe_print(f"Completion: {result['completion']:.1%} ({result['details']['enemies_killed']}/{result['details']['enemies_total']})")
    _safe_print(f"Final HP: {result['details']['final_hp']} (target: {result['details']['target_hp']})")
    _safe_print(f"Final ATK={result['details']['hero_atk']} DEF={result['details']['hero_def']}")
    _safe_print(f"Steps: {result['details']['steps']}")
    _safe_print(f"Violations: {result['violations']}")
    _safe_print(f"LLM calls: {_ms_llm_calls} | Parse errors: {_ms_parse_errors} | Heuristic fallbacks: {_ms_fallbacks} | Plan actions: {_ms_plan_actions_total}")

    return result["total"]


def _parse_multistep_plan(response: str, valid_ids: set[int] | None = None) -> list[int]:
    """Parse PLAN: id1, id2, id3, ... from LLM response."""
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    if not cleaned:
        cleaned = response

    # Look for PLAN: pattern
    plan_match = re.search(r'PLAN\s*:\s*(.*?)(?:\n\n|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
    if plan_match:
        numbers = [int(n) for n in re.findall(r'\b(\d+)\b', plan_match.group(1))]
    else:
        # Fallback: look for ACTION: followed by comma-separated ids
        action_match = re.search(r'ACTION[S]?\s*:\s*(.*?)(?:\n\n|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
        if action_match:
            numbers = [int(n) for n in re.findall(r'\b(\d+)\b', action_match.group(1))]
        else:
            return []

    if valid_ids is not None:
        numbers = [n for n in numbers if n in valid_ids]

    return numbers


def _parse_coord_plan(response: str) -> list[tuple[int, int]]:
    """Parse PLAN: (x1,y1), (x2,y2), ... from LLM response."""
    # Strip thinking tags first
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    if not cleaned:
        cleaned = response
    # Prefer the portion after PLAN: for precision
    plan_match = re.search(r'PLAN\s*:\s*(.*?)(?:\n\n|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
    search_text = plan_match.group(1) if plan_match else cleaned
    pairs = re.findall(r'\((\d+)\s*,\s*(\d+)\)', search_text)
    return [(int(x), int(y)) for x, y in pairs]


def _door_key_cost(action, state: GameState) -> int:
    from ..game.types import DoorType
    from ..game import data as D

    def _has_spare_key(key_item_id: str) -> bool:
        """True if at least one uncollected key of this type remains on the floor."""
        for y in range(state.floor.height):
            for x in range(state.floor.width):
                tile = state.floor.map[y][x]
                if D.TILE_ITEMS.get(tile) == key_item_id and (x, y) not in state.removed:
                    return True
        return False

    if action.door_type == DoorType.YELLOW:
        surplus = state.hero.keys.yellow > 1 or _has_spare_key("yellowKey")
        return 70 if surplus else 110
    if action.door_type == DoorType.BLUE:
        surplus = state.hero.keys.blue > 1 or _has_spare_key("blueKey")
        return 110 if surplus else 170
    if action.door_type == DoorType.RED:
        surplus = state.hero.keys.red > 1 or _has_spare_key("redKey")
        return 150 if surplus else 220
    if action.door_type == DoorType.ICE:
        return 0
    return 120


def _action_effective_cost(action, state: GameState) -> int:
    from ..game.types import ActionType

    lookahead_value = getattr(action, "lookahead_value", 0) or 0
    if action.type == ActionType.FIGHT:
        return action.total_damage - lookahead_value
    if action.type == ActionType.OPEN_DOOR:
        base_cost = _door_key_cost(action, state) - lookahead_value
        if getattr(action, "is_dead_end", False):
            base_cost += 1000
        return base_cost
    return -lookahead_value


def _pick_auto_priority_action(actions: list, state: GameState | None = None):
    from ..game.types import ActionType, ItemTier

    for tier in [ItemTier.MAJOR_STAT, ItemTier.CORE_STAT, ItemTier.KEY, ItemTier.HP]:
        for action in actions:
            if action.type == ActionType.COLLECT and action.item_tier == tier:
                return action

    for action in actions:
        if action.type == ActionType.COLLECT:
            return action

    # Also auto-execute zero-cost fights (matching tree's _auto_collect_free)
    for action in actions:
        if action.type == ActionType.FIGHT and getattr(action, 'total_damage', 1) == 0:
            return action

    for action in actions:
        if action.type == ActionType.SHOP_BUY and action.shop_choice == "def":
            return action

    return None


def _auto_apply_priority_actions(state: GameState) -> None:
    while not state.goal_reached and not state.failed:
        actions = state.get_actions()
        action = _pick_auto_priority_action(actions, state)
        if action is None:
            return
        state.apply_action(action)


def _projected_progress_cost(action, state: GameState, depth: int = 1) -> float:
    base_cost = float(_action_effective_cost(action, state))
    if depth <= 0:
        return base_cost

    projected_state = copy.deepcopy(state)
    projected_state.apply_action(action)
    _auto_apply_priority_actions(projected_state)

    next_action = _pick_progress_action(projected_state.get_actions(), projected_state, depth=depth - 1)
    if next_action is None:
        return base_cost
    return base_cost + 0.6 * _projected_progress_cost(next_action, projected_state, depth=depth - 1)


def _pick_progress_action(actions: list, state: GameState, depth: int = 1):
    from ..game.types import ActionType

    candidates = [
        a for a in actions
        if (a.type == ActionType.OPEN_DOOR and not getattr(a, "is_dead_end", False))
        or (a.type == ActionType.FIGHT and a.can_win)
    ]
    if not candidates:
        return None

    scored = [
        (a, _projected_progress_cost(a, state, depth=depth))
        for a in candidates
    ]
    best_action, best_score = min(
        scored,
        key=lambda item: (
            item[1],
            0 if item[0].type == ActionType.FIGHT else 1,
            item[0].action_id,
        ),
    )

    if best_action.type == ActionType.FIGHT:
        safety_margin = max(60, int(state.hero.hp * 0.15))
        comparable_fights = [
            action
            for action, score in scored
            if action.type == ActionType.FIGHT and score <= best_score + safety_margin
        ]
        if comparable_fights:
            return min(
                comparable_fights,
                key=lambda action: (action.total_damage, -getattr(action, "lookahead_value", 0), action.action_id),
            )

    return best_action


def _heuristic_pick(actions: list, state: GameState) -> int:
    """Lookahead-aware heuristic: free items first, then best door/fight branch."""
    from ..game.types import ActionType, ItemTier

    # Priority 1: Major stat items (sword, shield) and core stats (gems)
    for tier in [ItemTier.MAJOR_STAT, ItemTier.CORE_STAT]:
        for a in actions:
            if a.type == ActionType.COLLECT and a.item_tier == tier:
                return a.action_id

    # Priority 2: Keys
    for a in actions:
        if a.type == ActionType.COLLECT and a.item_tier == ItemTier.KEY:
            return a.action_id

    # Priority 3: Potions
    for a in actions:
        if a.type == ActionType.COLLECT and a.item_tier == ItemTier.HP:
            return a.action_id

    # Priority 4: Any other free item.
    for a in actions:
        if a.type == ActionType.COLLECT:
            return a.action_id

    # Priority 5: Shop buy — DEF for threshold-hunting, but ATK whenever a reachable
    # fight is unwinnable because ATK does not exceed the monster's DEF (no amount of
    # DEF helps there). Never buy HP, keys or level-ups (key shops would otherwise
    # drain gold; HP is short-term gain).
    shop_actions = [a for a in actions if a.type == ActionType.SHOP_BUY and getattr(a, 'can_afford', True)]
    if shop_actions:
        def_shop = [s for s in shop_actions if s.shop_choice == "def"]
        atk_shop = [s for s in shop_actions if s.shop_choice == "atk"]
        atk_gated = False
        for a in actions:
            if a.type == ActionType.FIGHT and not a.can_win and a.monster_id:
                mon = state.gd.get_monster(a.monster_id) if hasattr(state.gd, "get_monster") else None
                if mon is not None and state.hero.atk <= mon.def_:
                    atk_gated = True
                    break
        if atk_gated and atk_shop:
            chosen = atk_shop[0]
        else:
            chosen = def_shop[0] if def_shop else (atk_shop[0] if atk_shop else None)
        if chosen is not None:
            return chosen.action_id

    # Priority 6: Best lookahead-adjusted door or fight.
    best_progress = _pick_progress_action(actions, state, depth=2)
    if best_progress:
        return best_progress.action_id

    # Last resort: stairs or non-fight action
    non_fight = [
        a for a in actions
        if a.type != ActionType.FIGHT and not (a.type == ActionType.OPEN_DOOR and getattr(a, "is_dead_end", False))
    ]
    if non_fight:
        return non_fight[0].action_id
    # Only unwinnable fights remain — stuck
    return None


def evaluate_heuristic_only() -> dict:
    """Run the pure heuristic (no LLM) for baseline measurement."""
    state = _create_state()

    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        actions = state.get_actions()
        if not actions:
            state.failed = True
            state.failure_reason = "No actions"
            break

        action_id = _heuristic_pick(actions, state)
        if action_id is None:
            state.failed = True
            state.failure_reason = "Stuck — only unwinnable fights remain"
            break
        chosen = next(a for a in actions if a.action_id == action_id)
        state.apply_action(chosen)

    fid = _scenario.name if _scenario else "mt3-walkthrough"
    result = score_run(state, fixture_id=fid)
    result["hero"] = {
        "hp": state.hero.hp, "atk": state.hero.atk, "def": state.hero.def_,
        "money": state.hero.money, "exp": state.hero.exp,
    }
    result["history"] = [
        {"turn": t.turn, "action": t.action.label(), "hp": t.hero_after["hp"]}
        for t in state.history
    ]
    return result


# ---------------------------------------------------------------------------
# Map serialization for dashboard
# ---------------------------------------------------------------------------

def _serialize_map_grid(state: GameState) -> dict:
    """Build a JSON-serializable map grid from current game state."""
    from ..game import data as D
    gd = state.gd
    floor = state.floor
    grid = []
    for y in range(floor.height):
        row = []
        for x in range(floor.width):
            tile = floor.map[y][x]
            removed = (x, y) in state.removed
            if removed:
                row.append(".")
            elif gd.is_enemy(tile):
                row.append("E")
            elif gd.is_item(tile):
                row.append("I")
            elif gd.is_door(tile):
                color = gd.get_door_type(tile).value[0].upper()  # Y/B/R
                row.append(color)
            elif gd.is_stairs(tile):
                row.append("S")
            elif gd.is_npc(tile):
                row.append("N")
            elif gd.is_wall(tile):
                row.append("#")
            elif gd.is_ground(tile):
                row.append(".")
            elif gd.is_terrain(tile):
                row.append("T")
            else:
                row.append("?")
        grid.append(row)
    return {
        "width": floor.width,
        "height": floor.height,
        "grid": grid,
        "hero": {"x": state.hero.x, "y": state.hero.y},
    }


def _hero_dict(state: GameState) -> dict:
    """Serialize hero stats including keys for dashboard events."""
    h = state.hero
    return {
        "hp": h.hp, "atk": h.atk, "def": h.def_, "mdef": h.mdef,
        "money": h.money, "exp": h.exp,
        "keys": {"yellow": h.keys.yellow, "blue": h.keys.blue, "red": h.keys.red},
        "x": h.x, "y": h.y,
    }


def _serialize_rich_map(state: GameState) -> dict:
    """Build a rich map grid with per-cell entity detail for the dashboard."""
    from ..game import data as D
    from ..game import damage as dmg_mod
    gd = state.gd
    floor = state.floor
    grid = []
    for y in range(floor.height):
        row = []
        for x in range(floor.width):
            tile = floor.map[y][x]
            removed = (x, y) in state.removed
            if removed:
                row.append({"t": "."})
            elif gd.is_enemy(tile):
                eid = gd.get_enemy_id(tile)
                m = gd.get_monster(eid)
                battle = dmg_mod.calculate(state.hero, m)
                row.append({
                    "t": "E", "id": tile, "name": m.name,
                    "hp": m.hp, "atk": m.atk, "def": m.def_,
                    "money": m.money,
                    "specials": list(m.specials),
                    "fixed": m.damage, "vampire": m.vampire, "n": m.n,
                    "dmg": battle.total_damage, "canWin": battle.can_win,
                })
            elif gd.is_item(tile):
                item_id = gd.get_item_id(tile)
                eff = gd.get_item_effect(item_id)
                row.append({"t": "I", "id": tile, "name": eff.get("name", item_id)})
            elif gd.is_door(tile):
                color = gd.get_door_type(tile).value[0].upper()
                row.append({"t": color, "id": tile})
            elif gd.is_stairs(tile):
                row.append({"t": "S", "id": tile, "dir": gd.get_stairs(tile)})
            elif gd.is_npc(tile):
                row.append({"t": "N", "id": tile, "name": gd.get_npc_id(tile) or "NPC"})
            elif gd.is_wall(tile):
                row.append({"t": "#", "id": tile})
            elif gd.is_ground(tile) or gd.is_terrain(tile):
                row.append({"t": ".", "id": tile} if tile else {"t": "."})
            else:
                row.append({"t": "?", "id": tile})
        grid.append(row)
    return {
        "floor_id": floor.floor_id,
        "width": floor.width,
        "height": floor.height,
        "grid": grid,
        "hero": _hero_dict(state),
    }


# ---------------------------------------------------------------------------
# Safety corrector — prevents catastrophically wrong LLM choices
# ---------------------------------------------------------------------------

def _safety_correct(chosen, actions: list, state: "GameState"):
    """Backward-compatible wrapper: return only the (possibly corrected) action."""
    return _safety_correct_with_reason(chosen, actions, state)[0]


def _strategic_overrides_enabled() -> bool:
    """Opt-in for the pre-2026-09-24 strategic override rules (effCost gap, stairs preference).

    Default (unset): the override is *mechanical-only* — dead-end door, unwinnable fight,
    lethal fight. The strategic rules silently replaced the LLM's choice with the heuristic's
    pick (94 unlogged overrides in 68 simple episodes; see SIMPLE_FLOOR_PLAN.md §2.3/§4) and are
    kept only to reproduce the historical stack (`MOTA_STRATEGIC_OVERRIDES=1`).
    """
    return os.environ.get("MOTA_STRATEGIC_OVERRIDES", "").strip() in ("1", "true", "yes")


def _safety_correct_with_reason(chosen, actions: list, state: "GameState"):
    """
    Override the LLM's chosen action when it is *mechanically* wrong: a [DEAD END] door, an
    unwinnable fight, or a lethal fight while a non-lethal action exists. Returns
    ``(action, reason)``; ``reason`` is None when the choice is kept.

    With ``MOTA_STRATEGIC_OVERRIDES=1`` the historical strategic rules are added back:
    heuristic prefers a non-fight, effCost gap > 40, and the multi-floor ">20% fight → stairs"
    preference.
    """
    from ..game.types import ActionType

    best_action_id = _heuristic_pick(actions, state)
    if best_action_id is None:
        return chosen, None
    best_action = next((a for a in actions if a.action_id == best_action_id), None)
    if best_action is None:
        return chosen, None
    strategic = _strategic_overrides_enabled()

    if chosen.type == ActionType.OPEN_DOOR:
        if getattr(chosen, "is_dead_end", False):
            return best_action, "dead_end_door"
        if strategic:
            # Multi-floor: don't open doors with expensive gateway fights when stairs available
            stairs_action = next((a for a in actions if a.type == ActionType.USE_STAIRS), None)
            if stairs_action and state.goal == "stairs":
                # Check if via-chain has expensive fights (>20% HP)
                tree = getattr(chosen, "unlocks_tree", None) or []
                for node in tree:
                    via = node.get("via", "")
                    if "dmg=" in via:
                        # Extract damage percentage from via-chain annotation like "dmg=315 (37%)"
                        import re
                        pct_match = re.search(r'\((\d+)%\)', via)
                        if pct_match and int(pct_match.group(1)) > 20:
                            return stairs_action, "stairs_pref_door"
        return chosen, None

    if chosen.type != ActionType.FIGHT:
        return chosen, None

    if not chosen.can_win:
        return best_action, "unwinnable"

    hp_after = getattr(chosen, "hp_after", None)
    if hp_after is not None and hp_after <= 0:
        # Lethal fight while some other legal action exists.
        if best_action.action_id != chosen.action_id:
            return best_action, "lethal"
        return chosen, None

    if not strategic:
        return chosen, None

    # ---- historical strategic rules (opt-in) ----
    # Multi-floor stair preference: never commit to >20% HP fight when stairs available
    stairs_action = next((a for a in actions if a.type == ActionType.USE_STAIRS), None)
    if stairs_action and state.goal == "stairs":
        if chosen.damage_percent > 20:
            return stairs_action, "stairs_pref_fight"

    if best_action.type != ActionType.FIGHT:
        return best_action, "heuristic_non_fight"

    chosen_eff = _action_effective_cost(chosen, state)
    best_eff = _action_effective_cost(best_action, state)

    # On boss-goal floors: never override a required-path fight with a cheaper optional enemy.
    # Required = has unlocks_tree leading to boss chain, or IS the boss itself.
    # Optional = no unlocks_tree and not the boss — fighting it only wastes HP.
    if state.goal == "boss" and chosen_eff - best_eff > 40:
        chosen_required = bool(getattr(chosen, "unlocks_tree", None)) or chosen.monster_id == "enemy_299"
        best_optional = not bool(getattr(best_action, "unlocks_tree", None)) and best_action.monster_id != "enemy_299"
        if chosen_required and best_optional:
            return chosen, None

    if chosen_eff - best_eff > 40:
        return best_action, "effcost_gap"

    return chosen, None


def _lethal_only_stop(chosen, actions: list) -> dict | None:
    """The chosen fight kills the hero and nothing else legal is survivable except dead-end doors.

    Such a position is lost either way; it ends as 'stuck' (as the heuristic loop does) instead of
    executing the suicide. The would-be action is returned so reports can show both labels.
    ``MOTA_EXECUTE_LETHAL_ONLY=1`` restores the pre-2026-09-26 behaviour (recorded as a death).
    """
    from ..game.types import ActionType
    if os.environ.get("MOTA_EXECUTE_LETHAL_ONLY"):
        return None

    def lethal(a):
        return a.type == ActionType.FIGHT and (not a.can_win or (a.hp_after is not None and a.hp_after <= 0))

    if not lethal(chosen):
        return None
    if not all(lethal(a) or (a.type == ActionType.OPEN_DOOR and getattr(a, "is_dead_end", False)) for a in actions):
        return None
    return {"action": chosen.label(), "hp_after": chosen.hp_after, "damage": chosen.total_damage}


def _apply_override(chosen, actions: list, state: "GameState", emit, turn: int):
    """Run the safety override and, if it changed the action, record it (event + return info).

    Returns ``(chosen, override_info | None)`` where ``override_info`` =
    ``{"corrected_from": id, "corrected_from_label": str, "corrected_reason": str}``.
    """
    corrected, reason = _safety_correct_with_reason(chosen, actions, state)
    if reason is None or corrected.action_id == chosen.action_id:
        return chosen, None
    info = {
        "corrected_from": chosen.action_id,
        "corrected_from_label": chosen.label(),
        "corrected_reason": reason,
    }
    emit({
        "type": "override",
        "turn": turn,
        "llm_action_id": chosen.action_id,
        "llm_action": chosen.label(),
        "executed_action_id": corrected.action_id,
        "executed_action": corrected.label(),
        "reason": reason,
    })
    return corrected, info


# ---------------------------------------------------------------------------
# Streaming evaluation for dashboard
# ---------------------------------------------------------------------------

def evaluate_with_callback(
    candidate_prompt: str | None = None,
    on_event=None,
    task_model: str | None = None,
    task_mode: str | None = None,
    should_stop=None,
    lookahead_depth: int | None = None,
    temperature: float = 0.0,
) -> dict:
    """
    Evaluation with per-turn callbacks for dashboard streaming.

    Args:
        candidate_prompt: System prompt for LLM. None = heuristic-only mode.
        on_event: Callback fn(dict) called at each step.
        should_stop: Optional callback that returns True to request early stop.
        lookahead_depth: BFS lookahead depth override (None = use env/default).

    Returns:
        Full result dict from score_run() plus hero/history.
    """
    from ..game.types import ActionType

    def emit(event):
        if on_event:
            on_event(event)

    use_llm = candidate_prompt is not None
    state = _create_state(lookahead_depth=lookahead_depth)
    resolved_task_model = _get_task_model(task_model)
    resolved_task_mode = task_mode or ("thinking" if "thinking" in resolved_task_model else "instruct")

    # Build floor map once and append to system prompt
    floor_map_text = state.format_floor_map()
    runtime_system_prompt = (candidate_prompt + "\n\n" + floor_map_text) if use_llm else ""

    # Per-run conversation history (sliding window)
    max_hist_turns = int(os.environ.get("CONVERSATION_HISTORY_TURNS", "6"))
    conversation_history: list[dict] = []

    # Build initial rich map for visualization
    map_data = _serialize_rich_map(state)

    emit({
        "type": "start",
        "floor_id": state.floor.floor_id,
        "hero": _hero_dict(state),
        "initial_enemies": state.initial_enemies,
        "state_text": state.format_state(),
        "mode": "llm" if use_llm else "heuristic",
        "task_model": resolved_task_model,
        "task_mode": resolved_task_mode,
        "map": map_data,
        "runtime_system_prompt": runtime_system_prompt if use_llm else None,
    })

    consecutive_errors = 0
    max_consecutive_errors = 3
    elapsed_ms = None
    plan_steps = _plan_steps() if use_llm else 1
    plan_queue: list[tuple[str, int, int]] = []
    # One-shot: MOTA_PLAN_NO_REPLAN=1 + MOTA_PLAN_STEPS=60 -> one LLM call; unplanned turns go to the heuristic.
    one_plan = use_llm and os.environ.get("MOTA_PLAN_NO_REPLAN") == "1"
    planned_once = False
    plan_note = None  # MOTA_PLAN_MEMORY=1: (note, turn, history index at that decision)

    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        elapsed_ms = None
        if should_stop and should_stop():
            emit({"type": "stopped", "reason": "Stopped by user"})
            break

        actions = state.get_actions()
        if not actions:
            state.failed = True
            state.failure_reason = "No actions available"
            emit({"type": "stuck", "reason": "No actions available"})
            break

        state_text = state.format_state()
        actions_text = state.format_actions(actions)

        # Forced action (only one choice) — but don't force unwinnable fights
        if len(actions) == 1:
            only = actions[0]
            if only.type == ActionType.FIGHT and not only.can_win:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fight remains"
                emit({"type": "stuck", "reason": state.failure_reason})
                break
            trace = state.apply_action(only)
            emit({
                "type": "turn",
                "turn": trace.turn,
                "action": trace.action.label(),
                "action_id": actions[0].action_id,
                "forced": True,
                "state_text": state_text,
                "actions_text": actions_text,
                "hero": _hero_dict(state),
                "enemies_remaining": state.remaining_enemies(),
                "removed": [list(r) for r in state.removed],
                "sub_steps": trace.sub_steps,
                "action_path": [list(p) for p in getattr(only, "path", [])],
            })
            consecutive_errors = 0
            continue

        # Auto-collect: take ALL reachable collect actions immediately without LLM.
        # Items are always beneficial and order-independent — no LLM query needed.
        # Likewise a fight that costs 0 HP (user rule 2026-09-23).
        best_collect = _pick_auto_collect_action(state, actions)
        forced_reason = "auto-collect"
        if best_collect is None and not os.environ.get("MOTA_DISABLE_OVERRIDES"):
            best_collect = next((a for a in sorted(actions, key=lambda a: a.path_steps)
                                 if a.type == ActionType.FIGHT and a.can_win and a.total_damage == 0), None)
            forced_reason = "auto-fight (0 HP)"
        if best_collect is not None:
            trace = state.apply_action(best_collect)
            emit({
                "type": "turn",
                "turn": trace.turn,
                "action": trace.action.label(),
                "action_id": best_collect.action_id,
                "forced": True,
                "forced_reason": forced_reason,
                "state_text": state_text,
                "actions_text": actions_text,
                "hero": _hero_dict(state),
                "enemies_remaining": state.remaining_enemies(),
                "removed": [list(r) for r in state.removed],
                "sub_steps": trace.sub_steps,
                "action_path": [list(p) for p in getattr(best_collect, "path", [])],
            })
            consecutive_errors = 0
            continue

        planned_step = None
        if use_llm and plan_queue:
            planned_step, plan_queue = _next_planned_action(plan_queue, actions, state.removed, state.floor)

        if planned_step is not None:
            response = None
            action_id = planned_step.action_id
            fallback = False
        elif one_plan and planned_once:
            response = None
            action_id = _heuristic_pick(actions, state)
            fallback = True
            if action_id is None:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fights remain"
                emit({"type": "stuck", "reason": state.failure_reason})
                break
        elif use_llm:
            planned_once = True
            user_msg = _build_user_msg(state_text, actions_text)
            if _plan_memory_enabled() and plan_note is not None:
                note, n_turn, n_idx = plan_note
                user_msg = _with_plan_note(user_msg, note, n_turn, state.floor.floor_id,
                                           [t.action.label() for t in state.history[n_idx:]])
            decision_hist_idx = len(state.history)

            emit({
                "type": "thinking",
                "turn": state.turn + 1,
                "state_text": state_text,
                "actions_text": actions_text,
                "user_message": user_msg,
            })

            valid_ids = {a.action_id for a in actions}
            _current_turn = state.turn + 1

            def _on_chunk(chunk_text):
                emit({"type": "thinking_chunk", "turn": _current_turn, "chunk": chunk_text})

            _start = time.perf_counter()
            response = _call_llm(
                runtime_system_prompt, user_msg,
                task_model=task_model, task_mode=task_mode,
                prior_messages=conversation_history if conversation_history else None,
                temperature=temperature,
                on_reasoning_chunk=_on_chunk if on_event else None,
            )
            elapsed_ms = (time.perf_counter() - _start) * 1000
            if _plan_memory_enabled():
                note = _extract_plan_note(response)
                if note:
                    plan_note = (note, state.turn + 1, decision_hist_idx)
                emit({"type": "plan_note", "turn": state.turn + 1, "note": note})

            # Retry immediately on truncated response (token limit cut off before ACTION:).
            if _is_truncated_response(response):
                consecutive_errors += 1
                emit({
                    "type": "parse_error",
                    "turn": state.turn + 1,
                    "response": response[:300],
                    "parsed_id": None,
                    "valid_ids": sorted(valid_ids),
                    "reason": "truncated",
                })
                if consecutive_errors < max_consecutive_errors:
                    continue
                # Too many truncations — fall through to parse attempt

            # Emit thinking result immediately so dashboard shows reasoning
            thinking_text = _extract_llm_thinking(response)
            if thinking_text:
                emit({
                    "type": "thinking_result",
                    "turn": state.turn + 1,
                    "thinking": thinking_text,
                    "response_preview": _preview_visible_response(response),
                })

            action_id = _parse_action_id(response, valid_ids=valid_ids)
            fallback = False
            if action_id is None or action_id not in valid_ids:
                repaired = _structured_action_choice(
                    runtime_system_prompt, state_text, actions_text, _repair_candidates(actions, valid_ids),
                    task_model=task_model, temperature=temperature,
                )
                if repaired is not None:
                    emit({
                        "type": "parse_error",
                        "turn": state.turn + 1,
                        "response": response[:300],
                        "parsed_id": action_id,
                        "valid_ids": sorted(valid_ids),
                        "reason": "repaired_by_structured_output",
                        "repaired_id": repaired,
                    })
                    action_id = repaired
            if action_id is None or action_id not in valid_ids:
                consecutive_errors += 1
                emit({
                    "type": "parse_error",
                    "turn": state.turn + 1,
                    "response": response[:300],
                    "parsed_id": action_id,
                    "valid_ids": sorted(valid_ids),
                })
                if consecutive_errors >= max_consecutive_errors:
                    action_id = _heuristic_pick(actions, state)
                    if action_id is None:
                        state.failed = True
                        state.failure_reason = "Stuck — only unwinnable fights remain"
                        emit({"type": "stuck", "reason": state.failure_reason})
                        break
                    fallback = True
                    consecutive_errors = 0
                else:
                    continue
        else:
            # Heuristic mode
            response = None
            action_id = _heuristic_pick(actions, state)
            fallback = False
            if action_id is None:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fights remain"
                emit({"type": "stuck", "reason": state.failure_reason})
                break

        chosen = next(a for a in actions if a.action_id == action_id)

        # Safety override (mechanical-only by default: dead-end door / unwinnable / lethal;
        # MOTA_STRATEGIC_OVERRIDES=1 restores the historical effCost rules). Every override is
        # recorded on the turn event and as an `override` event.
        # Disable with MOTA_DISABLE_OVERRIDES=1 for raw-LLM GEPA experiments.
        override_info = None
        if use_llm and not os.environ.get("MOTA_DISABLE_OVERRIDES"):
            chosen, override_info = _apply_override(chosen, actions, state, emit, state.turn + 1)

        lethal_stop = _lethal_only_stop(chosen, actions) if use_llm else None
        if lethal_stop:
            state.failed = True
            state.failure_reason = f"Stuck — only lethal/unwinnable actions remain (LLM chose {lethal_stop['action']})"
            state.lethal_only_stop = lethal_stop
            emit({"type": "stuck", "reason": state.failure_reason, "lethal_only": True, **lethal_stop})
            break

        effective_cost = None
        if chosen.type in (ActionType.FIGHT, ActionType.OPEN_DOOR):
            effective_cost = _action_effective_cost(chosen, state)

        trace = state.apply_action(chosen)
        action_id = chosen.action_id  # may have been corrected

        # Build action detail with lookahead info
        action_detail = {
            "type": chosen.type.value,
            "x": chosen.x, "y": chosen.y,
            "name": chosen.name,
            "is_dead_end": bool(getattr(chosen, "is_dead_end", False)),
        }
        if chosen.type == ActionType.FIGHT:
            action_detail["damage"] = chosen.total_damage
            action_detail["damage_pct"] = chosen.damage_percent
            action_detail["hp_after"] = chosen.hp_after
        if chosen.type in (ActionType.FIGHT, ActionType.OPEN_DOOR):
            action_detail["lookahead_value"] = getattr(chosen, "lookahead_value", 0)
            action_detail["effective_cost"] = effective_cost
        if chosen.unlocks_items:
            action_detail["unlocks"] = chosen.unlocks_items

        event = {
            "type": "turn",
            "turn": trace.turn,
            "action": trace.action.label(),
            "action_id": action_id,
            "forced": False,
            "fallback": fallback,
            "elapsed_ms": elapsed_ms if use_llm else None,
            "state_text": state_text,
            "actions_text": actions_text,
            "hero": _hero_dict(state),
            "enemies_remaining": state.remaining_enemies(),
            "removed": [list(r) for r in state.removed],
            "sub_steps": trace.sub_steps,
            "action_detail": action_detail,
            "action_path": [list(p) for p in getattr(chosen, "path", [])],
        }
        if override_info:
            event.update(override_info)
        if planned_step is not None:
            event["planned"] = True
        if response is not None:
            event["llm_response"] = response
            thinking_text = _extract_llm_thinking(response)
            if thinking_text:
                event["llm_thinking"] = thinking_text
        emit(event)
        consecutive_errors = 0
        if use_llm and response is not None:
            plan_queue = [] if (fallback or override_info or plan_steps <= 1) else _parse_next_plan(
                response, plan_steps - 1, _extract_llm_thinking(response))
            if plan_queue:
                emit({"type": "plan_check", "turn": trace.turn, "plan": [list(p) for p in plan_queue],
                      "budget": plan_queue.budget,
                      **_verify_plan(state, plan_queue, not os.environ.get("MOTA_DISABLE_OVERRIDES"))})
        elif override_info:
            plan_queue = []

        # Update conversation history after a successful LLM turn
        # Strip <think> blocks to prevent context explosion with thinking models.
        if use_llm and response is not None and not fallback:
            history_response = _visible_history_response(response)
            conversation_history.append({"role": "user", "content": user_msg})
            conversation_history.append({"role": "assistant", "content": history_response or response[:200]})
            max_msg = max_hist_turns * 2
            if len(conversation_history) > max_msg:
                conversation_history = conversation_history[len(conversation_history) - max_msg:]

    # Score
    fid = _scenario.name if _scenario else "mt3-walkthrough"
    result = score_run(state, fixture_id=fid)
    result["hero"] = _hero_dict(state)
    result["lethal_only_stop"] = getattr(state, "lethal_only_stop", None)
    result["history"] = [
        {"turn": t.turn, "action": t.action.label(), "hp": t.hero_after["hp"]}
        for t in state.history
    ]
    emit({"type": "result", **result})
    return result


# ---------------------------------------------------------------------------
# Multi-floor scenario configuration and evaluation
# ---------------------------------------------------------------------------

# Multi-floor globals
_multi_floor_config: dict | None = None  # {"floors": [FloorData], "hero": Hero}


def configure_multi_floor_scenario(
    start_floor_id: str,
    end_floor_id: str,
    floors_dir: str | Path | None = None,
    project_data_js: str | Path | None = None,
    hero_override: dict | None = None,
    project_root: str | Path | None = None,
) -> str:
    """
    Configure a multi-floor scenario.

    Args:
        start_floor_id: First floor ID (e.g. "MT0" or "MT3").
        end_floor_id: Last floor ID (inclusive, e.g. "MT4" or "MT23w").
        floors_dir: Override path to floors directory.
        project_data_js: Override path to project/data.js.
        hero_override: Optional stats {hp, atk, def, mdef, money, exp, yellow, blue, red}
            applied to the starting hero (e.g. a walkthrough checkpoint).
        project_root: Foreign HTML5-mota project folder (see configure_scenario); implies
            floors_dir/data.js under it and a GameData built from its tables.

    Returns:
        Human-readable description of the configured range.
    """
    global _multi_floor_config

    from ..game.state import set_hp_rule_pct
    set_hp_rule_pct(60)  # tower prompt rule 4 since 2026-10-02 (MT3 turn-15 replay); single floors keep 40
    from ..game.hero_loader import load_initial_hero, load_floor_sequence
    from ..game.floor_loader import load_floors_range

    game_data = None
    if project_root is not None:
        from ..game.project import MotaProject
        proj = MotaProject.load(project_root)
        game_data = proj.game_data()
        floors_dir = floors_dir or proj.floors_dir
        project_data_js = project_data_js or proj.data_js
    _floors_dir = Path(floors_dir) if floors_dir else _FLOORS_DIR
    _data_js = Path(project_data_js) if project_data_js else _DATA_JS

    all_floor_ids = load_floor_sequence(_data_js)
    try:
        start_idx = all_floor_ids.index(start_floor_id)
        end_idx = all_floor_ids.index(end_floor_id)
    except ValueError as e:
        raise ValueError(f"Unknown floor ID: {e}") from e

    if start_idx > end_idx:
        raise ValueError(f"start_floor_id '{start_floor_id}' comes after end_floor_id '{end_floor_id}'")

    selected_ids = all_floor_ids[start_idx: end_idx + 1]
    floors = load_floors_range(_floors_dir, selected_ids)

    # Build starting hero — use game's initial hero if starting from MT0,
    # otherwise still use game's initial hero (user can override later).
    hero = load_initial_hero(_data_js)
    if start_floor_id == "MT0" and project_root is None:
        # MT0 fairy NPC gives 1Y+1B+1R keys via dialogue event (engine can't
        # simulate NPC scripts), so pre-grant them so the hero can open the
        # door to reach the stairs.
        hero.keys = Keys(yellow=1, blue=1, red=1)
    else:
        # For non-MT0 starts, place hero at arrival-from-below position
        if floors:
            arrive_x, arrive_y = floors[0].down_floor
            if arrive_x or arrive_y:
                hero.x = arrive_x
                hero.y = arrive_y

    if hero_override:
        for k in ("hp", "atk", "mdef", "money", "exp"):
            if k in hero_override:
                setattr(hero, k, int(hero_override[k]))
        if "def" in hero_override:
            hero.def_ = int(hero_override["def"])
        for k in ("yellow", "blue", "red"):
            if k in hero_override:
                setattr(hero.keys, k, int(hero_override[k]))

    _multi_floor_config = {
        "floors": floors,
        "hero": hero,
        "floor_ids": selected_ids,
        "hero_override": hero_override,
        "initial_removed": {},  # floor_idx -> set of (x,y) to pre-remove
        "game_data": game_data,
    }
    if game_data is None and os.environ.get("MOTA_TOWER_FIDELITY") == "1":
        from ..game.data import GameData, TOWER_ITEM_EFFECTS, TOWER_TILE_ITEMS
        _multi_floor_config["game_data"] = GameData(custom_items=TOWER_ITEM_EFFECTS, tile_items=TOWER_TILE_ITEMS,
                                                    source="24/project (items.js values)")

    # MT0 fairy NPC at (6,9) disappears after dialogue; pre-remove so hero
    # can reach the door at (6,8) leading to stairs.  We also pre-remove the
    # NPC duplicate at (5,9) that spawns after the first dialogue script.
    if start_floor_id == "MT0" and project_root is None:
        _multi_floor_config["initial_removed"][0] = {(6, 9), (5, 9)}

    return f"Multi-floor: {start_floor_id} -> {end_floor_id} ({len(floors)} floors)"


def _create_multi_floor_game(lookahead_depth: int | None = None):
    """Create a MultiFloorGame from the configured multi-floor scenario."""
    from ..game.multi_floor import MultiFloorGame

    if _multi_floor_config is None:
        raise RuntimeError("No multi-floor scenario configured. Call configure_multi_floor_scenario() first.")

    max_total = int(os.environ.get("MOTA_MULTI_FLOOR_MAX_TURNS", "3000"))
    return MultiFloorGame(
        floors=_multi_floor_config["floors"],
        hero=_multi_floor_config["hero"].copy(),
        lookahead_depth=lookahead_depth,
        initial_removed=_multi_floor_config.get("initial_removed"),
        max_total_turns=max_total,
        game_data=_multi_floor_config.get("game_data"),
    )


def _score_multi_floor(game) -> dict:
    """Produce a result dict from a finished MultiFloorGame."""
    # Highest floor index ever entered (revisits may leave the hero on a lower floor).
    floor_ids = [f.floor_id for f in game.floors]
    floors_reached = game.current_floor_idx
    for t in game.floor_transitions:
        if t.get("to") in floor_ids:
            floors_reached = max(floors_reached, floor_ids.index(t["to"]))
    total_floors = len(game.floors)
    floor_progress = floors_reached / max(1, total_floors - 1)
    goal_bonus = 1.0 if game.goal_reached else 0.0

    hero = game.hero
    hp_ratio = hero.hp / 1000.0  # relative to start HP

    total = min(1.0, 0.5 * floor_progress + 0.3 * goal_bonus + 0.2 * hp_ratio)

    return {
        "total": round(total, 4),
        "floor_progress": round(floor_progress, 3),
        "goal_reached": game.goal_reached,
        "failed": game.failed,
        "failure_reason": game.failure_reason,
        "floors_reached": floors_reached,
        "max_floor_id": floor_ids[floors_reached],
        "final_floor_id": game.current_floor.floor_id,
        "total_floors": total_floors,
        "hero": {
            "hp": hero.hp, "atk": hero.atk, "def": hero.def_,
            "money": hero.money, "exp": hero.exp,
            "keys": {"yellow": hero.keys.yellow, "blue": hero.keys.blue, "red": hero.keys.red},
            "x": hero.x, "y": hero.y,
        },
        "turn_count": game.total_turns,
        "floor_transitions": game.floor_transitions,
        "violations": [],
        "details": {
            "final_hp": hero.hp,
            "hero_atk": hero.atk,
            "hero_def": hero.def_,
        },
    }


def _hero_dict_from_hero(hero) -> dict:
    return {
        "hp": hero.hp, "atk": hero.atk, "def": hero.def_, "mdef": hero.mdef,
        "money": hero.money, "exp": hero.exp,
        "keys": {"yellow": hero.keys.yellow, "blue": hero.keys.blue, "red": hero.keys.red},
        "x": hero.x, "y": hero.y, "lv": getattr(hero, "lv", 1),
    }


def evaluate_multi_floor_with_callback(
    candidate_prompt: str | None = None,
    on_event=None,
    task_model: str | None = None,
    task_mode: str | None = None,
    should_stop=None,
    lookahead_depth: int | None = None,
    temperature: float = 0.0,
) -> dict:
    """
    Multi-floor evaluation with per-turn callbacks for dashboard streaming.

    Mirrors evaluate_with_callback but operates on a MultiFloorGame.
    Emits an additional 'floor_change' event on floor transitions.

    Args:
        candidate_prompt: System prompt for LLM. None = heuristic-only mode.
        on_event: Callback fn(dict) called at each step.
        should_stop: Optional callable returning True to stop early.
        lookahead_depth: BFS lookahead depth override.
    """
    from ..game.types import ActionType

    def emit(event):
        if on_event:
            on_event(event)

    use_llm = candidate_prompt is not None
    game = _create_multi_floor_game(lookahead_depth=lookahead_depth)
    resolved_task_model = _get_task_model(task_model)
    resolved_task_mode = task_mode or ("thinking" if "thinking" in resolved_task_model else "instruct")

    # Build initial floor map for system prompt
    floor_map_text = game.format_floor_map()
    runtime_system_prompt = (candidate_prompt + "\n\n" + floor_map_text) if use_llm else ""

    max_hist_turns = int(os.environ.get("CONVERSATION_HISTORY_TURNS", "6"))
    conversation_history: list[dict] = []
    llm_memory = ""  # MOTA_LLM_MEMORY=1: notes the model writes for itself at floor changes, shown every turn
    memory_floor, memory_hist_idx = game.current_floor.floor_id, 0
    plan_note = None  # MOTA_PLAN_MEMORY=1: (note, turn, floor, history index at that decision)

    # Build a rich map from the initial state
    initial_state = game._make_state()
    map_data = _serialize_rich_map(initial_state)

    emit({
        "type": "start",
        "floor_id": game.current_floor.floor_id,
        "hero": _hero_dict_from_hero(game.hero),
        "initial_enemies": initial_state.initial_enemies,
        "state_text": game.format_state(),
        "mode": "llm" if use_llm else "heuristic",
        "task_model": resolved_task_model,
        "task_mode": resolved_task_mode,
        "map": map_data,
        "runtime_system_prompt": runtime_system_prompt if use_llm else None,
        "multi_floor": True,
        "floor_range": [f.floor_id for f in game.floors],
    })

    consecutive_errors = 0
    max_consecutive_errors = 3
    if os.environ.get("MOTA_RESUME_LOG"):
        plan_note = _resume_tower_from_log(game, os.environ["MOTA_RESUME_LOG"],
                                           int(os.environ.get("MOTA_RESUME_BEFORE_TURN", "0")), emit) or plan_note
    last_floor_id = game.current_floor.floor_id
    tried_revisits: set[tuple[str, str]] = set()
    plan_steps = _plan_steps() if use_llm else 1
    plan_queue: list[tuple[str, int, int]] = []  # committed steps on the current floor (MOTA_PLAN_STEPS)
    buy_repeat: tuple[str, int] | None = None  # MOTA_BUY_QUANTITY: (shop action label, purchases still to make)
    # Single call (MOTA_PLAN_NO_REPLAN=1): later floors are unseen, so one plan per floor; unplanned turns -> heuristic.
    one_plan = use_llm and os.environ.get("MOTA_PLAN_NO_REPLAN") == "1"
    planned_floors: set[str] = set()
    # Consecutive turns that only moved between floors (stairs / return). Beyond the
    # threshold, return actions are withheld until the agent does something on a floor.
    transition_streak = 0
    max_transition_streak = 6

    def _fallback_pick(actions):
        """Heuristic in-floor choice; if nothing sensible remains on this floor, an untried
        return/revisit action. None only when both are exhausted (genuinely stuck)."""
        in_floor = [a for a in actions if a.type != ActionType.RETURN_TO_FLOOR and a.remote is None]
        aid = _heuristic_pick(in_floor, game._make_state()) if in_floor else None
        if aid is not None:
            return aid
        remote = [a for a in actions if a.remote is not None]  # MOTA_REMOTE_ACTIONS: other floors only once this one is done
        aid = _heuristic_pick(remote, game._make_state()) if remote else None
        if aid is not None:
            return aid
        for a in actions:
            if a.type != ActionType.RETURN_TO_FLOOR:
                continue
            sig = (a.target_floor_id, a.name)
            if sig in tried_revisits:
                continue
            tried_revisits.add(sig)
            return a.action_id
        return None

    def _build_action_detail(action):
        action_detail = {
            "type": action.type.value,
            "x": action.x,
            "y": action.y,
            "name": action.name,
            "is_dead_end": bool(getattr(action, "is_dead_end", False)),
        }
        if action.type == ActionType.FIGHT:
            action_detail["damage"] = action.total_damage
            action_detail["hp_after"] = action.hp_after
        return action_detail

    def _display_hero_after_action(action, hero_before, floor_changed):
        if not floor_changed:
            return _hero_dict_from_hero(game.hero)

        display_hero = dict(hero_before)
        if action.type == ActionType.USE_STAIRS:
            display_hero["x"] = action.x
            display_hero["y"] = action.y
        return display_hero

    while not game.goal_reached and not game.failed:
        if should_stop and should_stop():
            emit({"type": "stopped", "reason": "Stopped by user"})
            break

        actions = game.get_actions()
        if transition_streak >= max_transition_streak:
            trimmed = [a for a in actions if a.type != ActionType.RETURN_TO_FLOOR]
            if trimmed:
                if len(trimmed) < len(actions):
                    emit({"type": "loop_guard", "turn": game.total_turns + 1,
                          "reason": f"{transition_streak} consecutive floor transitions; return actions withheld"})
                actions = trimmed
        if not actions:
            game.failed = True
            game.failure_reason = "No actions available"
            emit({"type": "stuck", "reason": "No actions available"})
            break

        # Detect floor change (could happen if RETURN_TO_FLOOR was applied previously)
        if game.current_floor.floor_id != last_floor_id:
            last_floor_id = game.current_floor.floor_id
            plan_queue = []  # a plan is made for one floor
            new_state = game._make_state()
            new_map = _serialize_rich_map(new_state)
            # Update system prompt with new floor map
            if use_llm:
                new_floor_map = game.format_floor_map()
                runtime_system_prompt = candidate_prompt + "\n\n" + new_floor_map
            emit({
                "type": "floor_change",
                "turn": game.total_turns,
                "floor_id": game.current_floor.floor_id,
                "floor_idx": game.current_floor_idx,
                "hero": _hero_dict_from_hero(game.hero),
                "map": new_map,
                "state_text": game.format_state(),
            })

        state_text = game.format_state()
        actions_text = game.format_actions(actions)

        # Forced action: only one choice, or an engine-side mechanical assist (auto-collect,
        # 0-HP fight, scout an unvisited floor) — user rules 2026-09-23; MOTA_DISABLE_OVERRIDES=1
        # turns the assists off for raw-LLM ablations (the single-choice case is always forced).
        mech = None
        if use_llm and len(actions) > 1 and not os.environ.get("MOTA_DISABLE_OVERRIDES"):
            mech = game.mechanical_action(actions)
        if len(actions) == 1 or mech is not None:
            only = actions[0] if mech is None else mech[0]
            reason = None if mech is None else mech[1]
            if only.type == ActionType.FIGHT and not only.can_win:
                game.failed = True
                game.failure_reason = "Stuck — only unwinnable fight remains"
                emit({"type": "stuck", "reason": game.failure_reason})
                break
            action_floor_id = game.current_floor.floor_id
            action_floor_idx = game.current_floor_idx
            hero_before = _hero_dict_from_hero(game.hero)
            trace = game.apply_action(only)
            transition_streak = transition_streak + 1 if (only.type in (ActionType.USE_STAIRS, ActionType.RETURN_TO_FLOOR)
                                                          and only.remote is None) else 0
            floor_changed = game.current_floor.floor_id != action_floor_id
            display_floor_id = action_floor_id if floor_changed else game.current_floor.floor_id
            display_floor_idx = action_floor_idx if floor_changed else game.current_floor_idx
            if only.remote is not None:  # performed on the target floor (stairs: the floor below the new one)
                display_floor_idx = game.current_floor_idx - (1 if only.remote.type == ActionType.USE_STAIRS else 0)
                display_floor_id = game.floors[display_floor_idx].floor_id
                floor_changed = only.remote.type == ActionType.USE_STAIRS
            cur_removed = game.per_floor_removed.get(display_floor_idx, set())
            emit({
                "type": "turn",
                "turn": trace.turn,
                "action": trace.action.label(),
                "action_id": only.action_id,
                "forced": True,
                "forced_reason": reason or "only choice",
                "state_text": state_text,
                "actions_text": actions_text,
                "hero": _display_hero_after_action(only, hero_before, floor_changed),
                "floor_id": display_floor_id,
                "result_floor_id": game.current_floor.floor_id,
                "action_detail": _build_action_detail(only),
                "removed": [list(r) for r in cur_removed],
                "action_path": [list(p) for p in getattr(only, "path", [])],
            })
            consecutive_errors = 0
            # Check if floor changed after this action
            if game.current_floor.floor_id != last_floor_id:
                last_floor_id = game.current_floor.floor_id
                plan_queue = []
                new_state = game._make_state()
                new_map = _serialize_rich_map(new_state)
                if use_llm:
                    new_floor_map = game.format_floor_map()
                    runtime_system_prompt = candidate_prompt + "\n\n" + new_floor_map
                emit({
                    "type": "floor_change",
                    "turn": game.total_turns,
                    "floor_id": game.current_floor.floor_id,
                    "floor_idx": game.current_floor_idx,
                    "hero": _hero_dict_from_hero(game.hero),
                    "map": new_map,
                    "state_text": game.format_state(),
                })
            continue

        planned_step = None
        repeat_step = None
        if buy_repeat is not None:  # MOTA_BUY_QUANTITY: remaining purchases of the last chosen shop item
            label, left = buy_repeat
            repeat_step = next((a for a in actions if a.type == ActionType.SHOP_BUY and a.label() == label), None)
            buy_repeat = (label, left - 1) if repeat_step is not None and left > 1 else None
        if use_llm and plan_queue and repeat_step is None:
            planned_step, plan_queue = _next_planned_action(
                plan_queue, actions, game.per_floor_removed.get(game.current_floor_idx, set()), game.current_floor)

        if repeat_step is not None:
            response = None
            fallback = False
            action_id = repeat_step.action_id
        elif planned_step is not None:
            response = None
            fallback = False
            action_id = planned_step.action_id
        elif one_plan and game.current_floor.floor_id in planned_floors:
            response = None
            fallback = True
            action_id = _fallback_pick(actions)
            if action_id is None:
                game.failed = True
                game.failure_reason = "Stuck — only unwinnable fights remain"
                emit({"type": "stuck", "reason": game.failure_reason})
                break
        elif use_llm:
            planned_floors.add(game.current_floor.floor_id)
            user_msg = _build_user_msg(state_text, actions_text)
            if _llm_memory_enabled():
                if game.current_floor.floor_id != memory_floor:
                    recent = [t.action.label() for t in game.history[memory_hist_idx:]]
                    llm_memory = _update_memory(llm_memory, recent, state_text, memory_floor,
                                                game.current_floor.floor_id, task_model)
                    emit({"type": "memory", "turn": game.total_turns + 1, "notes": llm_memory,
                          "from_floor": memory_floor, "floor_id": game.current_floor.floor_id})
                    memory_floor, memory_hist_idx = game.current_floor.floor_id, len(game.history)
                user_msg = _with_memory(user_msg, llm_memory, game.current_floor.floor_id)
            if _plan_memory_enabled() and plan_note is not None:
                note, n_turn, n_floor, n_idx = plan_note
                user_msg = _with_plan_note(user_msg, note, n_turn, n_floor,
                                           [t.action.label() for t in game.history[n_idx:]])
            decision_hist_idx = len(game.history)
            emit({
                "type": "thinking",
                "turn": game.total_turns + 1,
                "state_text": state_text,
                "actions_text": actions_text,
                "user_message": user_msg,
            })

            valid_ids = {a.action_id for a in actions}
            _current_turn = game.total_turns + 1

            def _on_chunk_mf(chunk_text):
                emit({"type": "thinking_chunk", "turn": _current_turn, "chunk": chunk_text})

            response = _call_llm(
                runtime_system_prompt, user_msg,
                task_model=task_model, task_mode=task_mode,
                prior_messages=conversation_history if conversation_history else None,
                temperature=temperature,
                on_reasoning_chunk=_on_chunk_mf if on_event else None,
            )

            # Emit thinking result immediately so dashboard shows reasoning
            thinking_text = _extract_llm_thinking(response)
            if thinking_text:
                emit({
                    "type": "thinking_result",
                    "turn": game.total_turns + 1,
                    "thinking": thinking_text,
                    "response_preview": _preview_visible_response(response),
                })
            if _plan_memory_enabled():
                note = _extract_plan_note(response)
                if note:  # no PLAN line: the previous plan stays, shown with its own turn number
                    plan_note = (note, game.total_turns + 1, game.current_floor.floor_id, decision_hist_idx)
                emit({"type": "plan_note", "turn": game.total_turns + 1, "note": note})

            if _is_truncated_response(response):
                # A truncated thinking budget on the tower prompt is a runaway
                # deliberation, not a transient error: repeating the same 32K-token
                # call costs ~20 min each. Repair immediately with a no-think,
                # constrained-decoding choice; fall back to the heuristic if that fails.
                consecutive_errors += 1
                repaired = _structured_action_choice(
                    runtime_system_prompt, state_text, actions_text, _repair_candidates(actions, valid_ids),
                    task_model=task_model, temperature=temperature,
                )
                emit({
                    "type": "parse_error",
                    "turn": game.total_turns + 1,
                    "response": response[:300],
                    "parsed_id": None,
                    "valid_ids": sorted(valid_ids),
                    "reason": "truncated",
                    "repaired_id": repaired,
                })
                if repaired is None:
                    if consecutive_errors < max_consecutive_errors:
                        continue
                    repaired = _fallback_pick(actions)
                    if repaired is None:
                        game.failed = True
                        game.failure_reason = "Stuck — only unwinnable fights remain"
                        emit({"type": "stuck", "reason": game.failure_reason})
                        break
                    response = f"ACTION: {repaired}"
                    fallback_after_truncation = True
                    consecutive_errors = 0
                else:
                    response = f"ACTION: {repaired}"
                    fallback_after_truncation = False
            else:
                fallback_after_truncation = False

            action_id = _parse_action_id(response, valid_ids=valid_ids)
            fallback = fallback_after_truncation
            if action_id is None or action_id not in valid_ids:
                repaired = _structured_action_choice(
                    runtime_system_prompt, state_text, actions_text, _repair_candidates(actions, valid_ids),
                    task_model=task_model, temperature=temperature,
                )
                if repaired is not None:
                    emit({
                        "type": "parse_error",
                        "turn": game.total_turns + 1,
                        "response": response[:300],
                        "parsed_id": action_id,
                        "valid_ids": sorted(valid_ids),
                        "reason": "repaired_by_structured_output",
                        "repaired_id": repaired,
                    })
                    action_id = repaired
            if action_id is None or action_id not in valid_ids:
                consecutive_errors += 1
                emit({
                    "type": "parse_error",
                    "turn": game.total_turns + 1,
                    "response": response[:300],
                    "parsed_id": action_id,
                    "valid_ids": sorted(valid_ids),
                })
                if consecutive_errors >= max_consecutive_errors:
                    action_id = _fallback_pick(actions)
                    if action_id is None:
                        game.failed = True
                        game.failure_reason = "Stuck — only unwinnable fights remain"
                        emit({"type": "stuck", "reason": game.failure_reason})
                        break
                    fallback = True
                    consecutive_errors = 0
                else:
                    continue
        else:
            response = None
            fallback = False
            action_id = _fallback_pick(actions)
            if action_id is None:
                game.failed = True
                game.failure_reason = "Stuck — only unwinnable fights remain"
                emit({"type": "stuck", "reason": game.failure_reason})
                break

        chosen = next(a for a in actions if a.action_id == action_id)
        if response is not None and _buy_quantity_enabled() and chosen.type == ActionType.SHOP_BUY:
            qty = _extract_quantity(response)
            buy_repeat = (chosen.label(), qty - 1) if qty > 1 else None
            if qty > 1:
                emit({"type": "quantity", "turn": game.total_turns + 1, "action": chosen.label(), "quantity": qty})

        # Safety override (mechanical-only by default; MOTA_STRATEGIC_OVERRIDES=1 restores the
        # historical ">20% fight → stairs" / effCost rules). Every override is recorded.
        # Disable with MOTA_DISABLE_OVERRIDES=1 for raw-LLM GEPA experiments.
        override_info = None
        if use_llm and not os.environ.get("MOTA_DISABLE_OVERRIDES"):
            chosen, override_info = _apply_override(chosen, actions, game._make_state(), emit, game.total_turns + 1)
            action_id = chosen.action_id
            # User 2026-10-01: the 40 % rule is a suggestion (the MT8 Red Bats cost ~2k HP even on the optimal route);
            # the override is opt-in since then. Tower designs 1-4 ran with it (MOTA_TOWER_HP_FLOOR=1).
            if os.environ.get("MOTA_TOWER_HP_FLOOR", "0") == "1":
                alt = game.hp_floor_alternative(chosen, actions)
                if alt is not None:
                    first = override_info or {"corrected_from": chosen.action_id, "corrected_from_label": chosen.label()}
                    override_info = {**first, "corrected_reason": "hp_floor_40"}
                    emit({"type": "override", "turn": game.total_turns + 1, "llm_action_id": chosen.action_id,
                          "llm_action": chosen.label(), "executed_action_id": alt.action_id,
                          "executed_action": alt.label(), "reason": "hp_floor_40"})
                    chosen = alt
                    action_id = chosen.action_id

        lethal_stop = _lethal_only_stop(chosen, actions) if use_llm else None
        if lethal_stop:
            game.failed = True
            game.failure_reason = f"Stuck — only lethal/unwinnable actions remain (LLM chose {lethal_stop['action']})"
            game.lethal_only_stop = lethal_stop
            emit({"type": "stuck", "reason": game.failure_reason, "lethal_only": True, **lethal_stop})
            break

        action_floor_id = game.current_floor.floor_id
        action_floor_idx = game.current_floor_idx
        hero_before = _hero_dict_from_hero(game.hero)
        trace = game.apply_action(chosen)
        transition_streak = transition_streak + 1 if (chosen.type in (ActionType.USE_STAIRS, ActionType.RETURN_TO_FLOOR)
                                                      and chosen.remote is None) else 0
        floor_changed = game.current_floor.floor_id != action_floor_id
        display_floor_id = action_floor_id if floor_changed else game.current_floor.floor_id
        display_floor_idx = action_floor_idx if floor_changed else game.current_floor_idx
        if chosen.remote is not None:
            display_floor_idx = game.current_floor_idx - (1 if chosen.remote.type == ActionType.USE_STAIRS else 0)
            display_floor_id = game.floors[display_floor_idx].floor_id
            floor_changed = chosen.remote.type == ActionType.USE_STAIRS
        cur_removed = game.per_floor_removed.get(display_floor_idx, set())
        event = {
            "type": "turn",
            "turn": trace.turn,
            "action": trace.action.label(),
            "action_id": action_id,
            "forced": False,
            "fallback": fallback,
            "state_text": state_text,
            "actions_text": actions_text,
            "hero": _display_hero_after_action(chosen, hero_before, floor_changed),
            "floor_id": display_floor_id,
            "result_floor_id": game.current_floor.floor_id,
            "action_detail": _build_action_detail(chosen),
            "removed": [list(r) for r in cur_removed],
            "action_path": [list(p) for p in getattr(chosen, "path", [])],
        }
        if override_info:
            event.update(override_info)
        if planned_step is not None:
            event["planned"] = True
        if repeat_step is not None:
            event["repeat"] = True
        if response is not None:
            event["llm_response"] = response
            thinking_text = _extract_llm_thinking(response)
            if thinking_text:
                event["llm_thinking"] = thinking_text
        emit(event)
        consecutive_errors = 0
        if use_llm and response is not None:
            plan_queue = [] if (fallback or override_info or plan_steps <= 1) else _parse_next_plan(
                response, plan_steps - 1, _extract_llm_thinking(response))
        elif override_info:
            plan_queue = []

        if use_llm and response is not None and not fallback:
            # Strip <think> blocks to prevent context explosion with thinking models.
            history_response = _visible_history_response(response)
            conversation_history.append({"role": "user", "content": user_msg})
            conversation_history.append({"role": "assistant", "content": history_response or response[:200]})
            max_msg = max_hist_turns * 2
            if len(conversation_history) > max_msg:
                conversation_history = conversation_history[len(conversation_history) - max_msg:]

        # Emit floor change after action if floor changed
        if game.current_floor.floor_id != last_floor_id:
            last_floor_id = game.current_floor.floor_id
            plan_queue = []
            new_state = game._make_state()
            new_map = _serialize_rich_map(new_state)
            if use_llm:
                new_floor_map = game.format_floor_map()
                runtime_system_prompt = candidate_prompt + "\n\n" + new_floor_map
            emit({
                "type": "floor_change",
                "turn": game.total_turns,
                "floor_id": game.current_floor.floor_id,
                "floor_idx": game.current_floor_idx,
                "hero": _hero_dict_from_hero(game.hero),
                "map": new_map,
                "state_text": game.format_state(),
            })

    result = _score_multi_floor(game)
    result["lethal_only_stop"] = getattr(game, "lethal_only_stop", None)
    emit({"type": "result", **result})
    return result


def evaluate_multi_floor(
    candidate_prompt: str,
    task_model: str | None = None,
    task_mode: str | None = None,
) -> float:
    """Run multi-floor evaluation and return the composite score.

    Wraps evaluate_multi_floor_with_callback for use as a GEPA evaluator.
    Requires configure_multi_floor_scenario() to have been called first.
    """
    result = evaluate_multi_floor_with_callback(
        candidate_prompt=candidate_prompt,
        on_event=None,
        task_model=task_model,
        task_mode=task_mode,
    )
    return float(result.get("total", 0.0))


def evaluate_multistep_with_callback(
    candidate_prompt: str | None = None,
    on_event=None,
    task_model: str | None = None,
    task_mode: str | None = None,
    should_stop=None,
    lookahead_depth: int | None = None,
    chunk_size: int = 5,
    temperature: float = 0.0,
) -> dict:
    from ..game.types import ActionType

    def emit(event):
        if on_event:
            on_event(event)

    use_llm = candidate_prompt is not None
    state = _create_state(lookahead_depth=lookahead_depth)
    resolved_task_model = _get_task_model(task_model)
    resolved_task_mode = task_mode or ("thinking" if "thinking" in resolved_task_model else "instruct")

    floor_map_text = state.format_floor_map()
    runtime_system_prompt = (candidate_prompt + "\n\n" + floor_map_text) if use_llm else ""

    conversation_history: list[dict] = []
    max_hist_turns = int(os.environ.get("CONVERSATION_HISTORY_TURNS", "6"))

    map_data = _serialize_rich_map(state)

    emit({
        "type": "start",
        "floor_id": state.floor.floor_id,
        "hero": _hero_dict(state),
        "initial_enemies": state.initial_enemies,
        "state_text": state.format_state(),
        "mode": "llm-multistep" if use_llm else "heuristic",
        "task_model": resolved_task_model,
        "task_mode": resolved_task_mode,
        "map": map_data,
        "runtime_system_prompt": runtime_system_prompt if use_llm else None,
        "chunk_size": chunk_size,
    })

    consecutive_errors = 0
    max_consecutive_errors = 3
    plan_queue: list[int] = []
    last_tree_prompt: str | None = None  # Last tree prompt sent to LLM (for logging)
    last_label_map: dict = {}  # Label map from the last tree-plan call (for coord resolution)
    _force_simple_prompt: dict | None = None  # Simplified retry prompt when PATH: was missing

    elapsed_ms = None

    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        elapsed_ms = None
        if should_stop and should_stop():
            emit({"type": "stopped", "reason": "Stopped by user"})
            break

        actions = state.get_actions()
        if not actions:
            state.failed = True
            state.failure_reason = "No actions available"
            emit({"type": "stuck", "reason": "No actions available"})
            break

        state_text = state.format_state()
        actions_text = state.format_actions(actions)

        # Forced action
        if len(actions) == 1:
            only = actions[0]
            if only.type == ActionType.FIGHT and not only.can_win:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fight remains"
                emit({"type": "stuck", "reason": state.failure_reason})
                break
            trace = state.apply_action(only)
            emit({
                "type": "turn",
                "turn": trace.turn,
                "action": trace.action.label(),
                "action_id": actions[0].action_id,
                "forced": True,
                "state_text": state_text,
                "actions_text": actions_text,
                "hero": _hero_dict(state),
                "enemies_remaining": state.remaining_enemies(),
                "removed": [list(r) for r in state.removed],
                "sub_steps": trace.sub_steps,
                "action_path": [list(p) for p in getattr(only, "path", [])],
            })
            consecutive_errors = 0
            continue

        valid_ids = {a.action_id for a in actions}
        chosen = None

        while plan_queue:
            next_id = plan_queue.pop(0)
            if next_id in valid_ids:
                chosen = next(a for a in actions if a.action_id == next_id)
                break
            # Coordinate-based match using LAST call's label_map (action_ids differ across states)
            resolved = _resolve_tree_action(next_id, actions, last_label_map)
            if resolved:
                chosen = resolved
                break

        fallback = False
        action_id = None
        response = None
        label_map = {}  # For tree-path parsing; populated if LLM is called
        tree_prompt = None  # Tree prompt text; logged in thinking event

        if chosen is not None:
            # We have a valid queued action
            auto = _pick_auto_priority_action(actions, state)
            if auto and auto.action_id != chosen.action_id:
                plan_queue = [chosen.action_id] + plan_queue
                chosen = auto
            action_id = chosen.action_id
            
        else:
            # Call LLM
            if use_llm:
                # Build decision tree for tree-level planning
                tree_state = _clone_state(state)
                pre_auto = _auto_collect_free(tree_state)
                tree_actions = tree_state.get_actions()
                if len(tree_actions) <= 1:
                    tree = []
                else:
                    tree = _build_decision_tree(tree_state, depth=chunk_size)

                if tree:
                    h = tree_state.hero
                    hero_sum = (
                        f"HP={h.hp} ATK={h.atk} DEF={h.def_} "
                        f"| Keys: Y={h.keys.yellow} B={h.keys.blue} R={h.keys.red}"
                    )
                    tree_prompt, label_map = _format_tree_prompt(
                        tree, chunk_size, hero_sum, auto_collected_before=pre_auto or None,
                    )
                    last_tree_prompt = tree_prompt
                    last_label_map = label_map
                    # Unified: state + tree (no separate actions_text)
                    # For thinking models, add a brief reasoning budget hint
                    _is_thinking_model = "thinking" in resolved_task_mode
                    _think_hint = ("\n(Use your thinking budget, then start your visible response with PATH: immediately.)" if _is_thinking_model else "")
                    user_msg = f"{state_text}\n\n{tree_prompt}{_think_hint}"

                    # If previous attempt failed (missing PATH:), use a simplified retry prompt
                    # Temperature=0 → same prompt → same wrong output → must change the prompt
                    if _force_simple_prompt is not None and _force_simple_prompt.get("turn") == state.turn + 1:
                        _force_simple_prompt = None
                        _step1_opts = "\n".join(
                            f"  {chr(ord('A')+i)}: {n['name']} at ({n['x']},{n['y']}) "
                            f"cost={n.get('total_damage', 0)}HP effCost={n.get('effective_cost', '?')}"
                            for i, n in enumerate(tree[:4])
                        )
                        user_msg = (
                            f"[RETRY — your previous response was missing PATH:]\n"
                            f"HP={state.hero.hp} ATK={state.hero.atk} DEF={state.hero.def_}\n\n"
                            f"Step 1 options:\n{_step1_opts}\n\n"
                            f"OUTPUT IMMEDIATELY (first line only):\n"
                            f"PATH: [A or B or C], [1 or 2 or 3]\n"
                            f"(then optionally explain on subsequent lines)"
                        )
                else:
                    _force_simple_prompt = None
                    user_msg = (
                        f"{state_text}\n\n{actions_text}\n\n"
                        f"MULTI-STEP PLANNING: Choose the best {chunk_size} actions to execute in order.\n"
                        f"Reply: PLAN: <id1>, <id2>, ..."
                    )

                emit({
                    "type": "thinking",
                    "turn": state.turn + 1,
                    "state_text": state_text,
                    "actions_text": actions_text,
                    "user_message": user_msg,
                    "tree_prompt": tree_prompt,
                })

                import time
                _current_turn_ms = state.turn + 1

                def _on_chunk_ms(chunk_text):
                    emit({"type": "thinking_chunk", "turn": _current_turn_ms, "chunk": chunk_text})

                _start = time.perf_counter()
                response = _call_llm(
                    runtime_system_prompt, user_msg,
                    task_model=task_model, task_mode=task_mode,
                    prior_messages=conversation_history if conversation_history else None,
                    temperature=temperature,
                    on_reasoning_chunk=_on_chunk_ms if on_event else None,
                )
                elapsed_ms = (time.perf_counter() - _start) * 1000

                thinking_text = _extract_llm_thinking(response)
                if thinking_text:
                    emit({
                        "type": "thinking_result",
                        "turn": state.turn + 1,
                        "thinking": thinking_text,
                        "response_preview": _preview_visible_response(response),
                    })

                if _is_truncated_response(response):
                    consecutive_errors += 1
                    emit({
                        "type": "parse_error",
                        "turn": state.turn + 1,
                        "response": response[:300],
                        "parsed_id": None,
                        "valid_ids": sorted(valid_ids),
                        "reason": "truncated",
                    })
                    if consecutive_errors < max_consecutive_errors:
                        continue

                # Also retry if no PATH/PLAN/FINAL_CHOICE found in a complete response
                if _missing_path_response(response):
                    consecutive_errors += 1
                    emit({
                        "type": "parse_error",
                        "turn": state.turn + 1,
                        "response": response[:300],
                        "parsed_id": None,
                        "valid_ids": sorted(valid_ids),
                        "reason": "missing_path",
                    })
                    if consecutive_errors < max_consecutive_errors:
                        # Save simplified-retry trigger; next iteration will use a different prompt
                        if tree and _is_thinking_model:
                            _force_simple_prompt = {"turn": state.turn + 1}
                        continue

                plan_ids = _parse_tree_path(response, label_map)
                if not plan_ids:
                    plan_ids = _parse_multistep_plan(response, valid_ids=valid_ids)
                if not plan_ids:
                    plan_ids = [_parse_action_id(response, valid_ids=valid_ids)]
                    if plan_ids[0] is None:
                        plan_ids = []
                # Cap plan to chunk_size to prevent over-execution
                if plan_ids:
                    plan_ids = plan_ids[:chunk_size]

                if not plan_ids:
                    consecutive_errors += 1
                    emit({
                        "type": "parse_error",
                        "turn": state.turn + 1,
                        "response": response[:300],
                        "parsed_id": None,
                        "valid_ids": sorted(valid_ids),
                    })
                    if consecutive_errors >= max_consecutive_errors:
                        fb_id = _heuristic_pick(actions, state)
                        if fb_id is None:
                            state.failed = True
                            state.failure_reason = "Stuck — only unwinnable fights remain"
                            emit({"type": "stuck", "reason": state.failure_reason})
                            break
                        plan_ids = [fb_id]
                        fallback = True
                        consecutive_errors = 0
                    else:
                        continue
                
                action_id = plan_ids[0]
                plan_queue = list(plan_ids[1:])
                
                # Resolve tree action_id → current state action
                first_match = next((a for a in actions if a.action_id == action_id), None)
                if first_match is None:
                    first_match = _resolve_tree_action(action_id, actions, label_map)
                if first_match is None:
                    # Action needs auto-collect first — queue everything and retry
                    plan_queue = list(plan_ids)
                    auto = _pick_auto_priority_action(actions, state)
                    if auto:
                        action_id = auto.action_id
                    else:
                        continue
                else:
                    action_id = first_match.action_id
                    # Auto-collect before plan
                    auto = _pick_auto_priority_action(actions, state)
                    if auto and auto.action_id != action_id:
                        plan_queue = [action_id] + plan_queue
                        action_id = auto.action_id

                history_response = _visible_history_response(response)
                conversation_history.append({"role": "user", "content": user_msg})
                conversation_history.append({"role": "assistant", "content": history_response or response[:200]})
                max_msg = max_hist_turns * 2
                if len(conversation_history) > max_msg:
                    conversation_history = conversation_history[len(conversation_history) - max_msg:]

            else:
                action_id = _heuristic_pick(actions, state)
                fallback = False
                if action_id is None:
                    state.failed = True
                    state.failure_reason = "Stuck — only unwinnable fights remain"
                    emit({"type": "stuck", "reason": state.failure_reason})
                    break

            chosen = next(a for a in actions if a.action_id == action_id)

        # Disable with MOTA_DISABLE_OVERRIDES=1 for raw-LLM GEPA experiments.
        override_info = None
        if use_llm and not os.environ.get("MOTA_DISABLE_OVERRIDES"):
            chosen, override_info = _apply_override(chosen, actions, state, emit, state.turn + 1)

        lethal_stop = _lethal_only_stop(chosen, actions) if use_llm else None
        if lethal_stop:
            state.failed = True
            state.failure_reason = f"Stuck — only lethal/unwinnable actions remain (LLM chose {lethal_stop['action']})"
            state.lethal_only_stop = lethal_stop
            emit({"type": "stuck", "reason": state.failure_reason, "lethal_only": True, **lethal_stop})
            break

        effective_cost = None
        if chosen.type in (ActionType.FIGHT, ActionType.OPEN_DOOR):
            effective_cost = _action_effective_cost(chosen, state)

        trace = state.apply_action(chosen)
        action_id = chosen.action_id

        action_detail = {
            "type": chosen.type.value,
            "x": chosen.x, "y": chosen.y,
            "name": chosen.name,
            "is_dead_end": bool(getattr(chosen, "is_dead_end", False)),
        }
        if chosen.type == ActionType.FIGHT:
            action_detail["damage"] = chosen.total_damage
            action_detail["damage_pct"] = chosen.damage_percent
            action_detail["hp_after"] = chosen.hp_after
        if chosen.type in (ActionType.FIGHT, ActionType.OPEN_DOOR):
            action_detail["lookahead_value"] = getattr(chosen, "lookahead_value", 0)
            action_detail["effective_cost"] = effective_cost
        if chosen.unlocks_items:
            action_detail["unlocks"] = chosen.unlocks_items

        event = {
            "type": "turn",
            "turn": trace.turn,
            "action": trace.action.label(),
            "action_id": action_id,
            "forced": False,
            "fallback": fallback,
            "elapsed_ms": elapsed_ms if use_llm else None,
            "state_text": state_text,
            "actions_text": actions_text,
            "hero": _hero_dict(state),
            "enemies_remaining": state.remaining_enemies(),
            "removed": [list(r) for r in state.removed],
            "sub_steps": trace.sub_steps,
            "action_detail": action_detail,
            "action_path": [list(p) for p in getattr(chosen, "path", [])],
        }
        if override_info:
            event.update(override_info)
        if response is not None:
            event["llm_response"] = response
            thinking_text = _extract_llm_thinking(response)
            if thinking_text:
                event["llm_thinking"] = thinking_text
        if last_tree_prompt is not None:
            event["tree_prompt"] = last_tree_prompt
        emit(event)
        consecutive_errors = 0
        _force_simple_prompt = None  # Clear on successful action

    fid = _scenario.name if _scenario else "mt3-walkthrough"
    from ..benchmark.scorer import score_run
    result = score_run(state, fixture_id=fid)
    result["lethal_only_stop"] = getattr(state, "lethal_only_stop", None)
    
    emit({
        "type": "done",
        "result": result
    })

    return result


# ---------------------------------------------------------------------------
# Map-only ablation: no enumerated choices, no lookahead, no annotations.
# The LLM sees the grid and must first list every action it can take, then choose one.
# ---------------------------------------------------------------------------

_MAP_ENUM_CONTRACT = """\
In this episode you do NOT get a list of actions. You see only the floor grid, the entity details and
your stats. Each turn:
1. List EVERY action you can take right now, one per line, in this exact block:
OPTIONS:
fight (x,y)
collect (x,y)
open_door (x,y)
stairs (x,y)
(An action is possible when you can walk to a tile next to the target over empty floor, stairs or
already-cleared tiles; walls, closed doors and monsters block walking. A door needs a key of its
colour. Items on your way are picked up automatically.)
2. Then choose one of them:
FINAL_CHOICE: (x,y)
This replaces the numbered FINAL_CHOICE format of the instructions above."""

_MAP_ENUM_TYPES = {"fight": "fight", "collect": "collect", "open_door": "open_door", "door": "open_door",
                   "stairs": "use_stairs", "use_stairs": "use_stairs"}


def _parse_map_enum(response: str) -> tuple[list[tuple[str | None, tuple[int, int]]], tuple[int, int] | None]:
    """(listed options [(type|None, (x,y))], final choice (x,y) | None) from a map-enum reply.
    Only the visible answer counts: reasoning (closed or truncated <think>) is dropped, otherwise
    every coordinate the model merely considered would be scored as a listed option."""
    text = response or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in text:
        text = text.split("<think>")[0]
    fc = list(re.finditer(r"FINAL_CHOICE\s*[:=]\s*(?:[A-Za-z_ ]+)?\(?\s*(\d+)\s*,\s*(\d+)\s*\)?", text, re.IGNORECASE))
    choice = (int(fc[-1].group(1)), int(fc[-1].group(2))) if fc else None
    m = list(re.finditer(r"OPTIONS\s*:", text, re.IGNORECASE))
    opts: list[tuple[str | None, tuple[int, int]]] = []
    if m:
        block = text[m[-1].end():]
        end = re.search(r"FINAL_CHOICE", block, re.IGNORECASE)
        block = block[:end.start()] if end else block
        for line in block.splitlines():
            c = re.search(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", line)
            if not c:
                continue
            w = re.match(r"\s*[-*\d.)]*\s*([a-z_]+)", line.lower())
            opts.append((_MAP_ENUM_TYPES.get(w.group(1)) if w else None, (int(c.group(1)), int(c.group(2)))))
    return opts, choice


def _map_enum_state_text(state: "GameState", recent: list[str], with_costs: bool) -> str:
    h = state.hero
    boss = next(((x, y) for y in range(state.floor.height) for x in range(state.floor.width)
                 if state.floor.map[y][x] == 299 and (x, y) not in state.removed), None)
    goal = f"Goal: defeat the boss at {boss}." if boss else f"Goal: {state.goal}."
    lines = [
        f"Hero: HP={h.hp} ATK={h.atk} DEF={h.def_} MDEF={h.mdef}  Keys: yellow={h.keys.yellow} "
        f"blue={h.keys.blue} red={h.keys.red}  Position: ({h.x},{h.y})",
        goal,
    ]
    if recent:
        lines.append("Recent actions: " + "; ".join(recent[-6:]))
    lines.append("")
    lines.append(state.format_map_grid_text(with_costs=with_costs))
    lines.append("")
    lines.append(_MAP_ENUM_CONTRACT)
    return "\n".join(lines)


def evaluate_map_enumerate(
    candidate_prompt: str,
    on_event=None,
    task_model: str | None = None,
    task_mode: str | None = None,
    temperature: float = 0.0,
    with_costs: bool = False,
) -> dict:
    """Choice-generation ablation. Engine assists (auto-collect, 0-HP fights, mechanical override,
    lethal-only stop) are the same as in the reactive loop; what is removed is the numbered action
    list, the unlock trees and every annotation. Per LLM turn the listed options are compared with
    the engine's legal set (precision / recall / hallucination kind) and the final choice is checked
    for legality. An illegal choice gets one retry told only that it was illegal; a second failure
    falls back to the heuristic (flagged)."""
    from ..game.types import ActionType

    def emit(event):
        if on_event:
            on_event(event)

    state = _create_state(lookahead_depth=0)
    resolved_task_model = _get_task_model(task_model)
    resolved_task_mode = task_mode or ("thinking" if "thinking" in resolved_task_model else "instruct")
    emit({"type": "start", "floor_id": state.floor.floor_id, "hero": _hero_dict(state),
          "initial_enemies": state.initial_enemies, "state_text": state.format_state(), "mode": "llm",
          "task_model": resolved_task_model, "task_mode": resolved_task_mode, "map": _serialize_rich_map(state),
          "runtime_system_prompt": candidate_prompt, "eval_mode": "map-enum" + ("-costs" if with_costs else "")})

    recent: list[str] = []
    stats = {"llm_turns": 0, "options_listed": 0, "options_legal": 0, "legal_total": 0, "legal_found": 0,
             "halluc_no_entity": 0, "halluc_unreachable": 0, "type_errors": 0, "choice_illegal": 0,
             "choice_parse_fail": 0, "truncated": 0, "retries": 0, "fallbacks": 0, "overrides": 0}

    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        actions = state.get_actions()
        if not actions:
            state.failed = True
            state.failure_reason = "Stuck — no legal action"
            emit({"type": "stuck", "reason": state.failure_reason})
            break
        forced = None
        if len(actions) == 1:
            forced = (actions[0], "only action")
            if actions[0].type == ActionType.FIGHT and not actions[0].can_win:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fights remain"
                emit({"type": "stuck", "reason": state.failure_reason})
                break
        if forced is None:
            ac = _pick_auto_collect_action(state, actions)
            if ac is not None:
                forced = (ac, "auto-collect")
            else:
                zero = next((a for a in sorted(actions, key=lambda a: a.path_steps)
                             if a.type == ActionType.FIGHT and a.can_win and a.total_damage == 0), None)
                if zero is not None:
                    forced = (zero, "auto-fight (0 HP)")
        if forced is not None:
            trace = state.apply_action(forced[0])
            recent.append(trace.action.label())
            emit({"type": "turn", "turn": trace.turn, "action": trace.action.label(), "action_id": forced[0].action_id,
                  "forced": True, "forced_reason": forced[1], "hero": _hero_dict(state),
                  "enemies_remaining": state.remaining_enemies(), "removed": [list(r) for r in state.removed],
                  "sub_steps": trace.sub_steps, "action_path": [list(p) for p in getattr(forced[0], "path", [])]})
            continue

        legal = {(a.x, a.y): a for a in actions}
        user_msg = _map_enum_state_text(state, recent, with_costs)
        stats["llm_turns"] += 1
        t0 = time.perf_counter()
        response = _call_llm(candidate_prompt, user_msg, task_model=task_model, task_mode=task_mode,
                             temperature=temperature)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        truncated = bool(_last_llm_truncated)
        stats["truncated"] += truncated
        opts, choice = _parse_map_enum(response)

        listed = {c for _, c in opts}
        ok = listed & set(legal)
        stats["options_listed"] += len(listed)
        stats["options_legal"] += len(ok)
        stats["legal_total"] += len(legal)
        stats["legal_found"] += len(ok)
        no_entity = unreachable = 0
        for c in listed - set(legal):
            x, y = c
            inside = 0 <= y < state.floor.height and 0 <= x < state.floor.width
            tile = state.floor.map[y][x] if inside else 0
            has_entity = inside and c not in state.removed and (
                state.gd.is_enemy(tile) or state.gd.is_item(tile) or state.gd.is_door(tile) or state.gd.is_stairs(tile))
            if has_entity:
                unreachable += 1
            else:
                no_entity += 1
        type_err = sum(1 for t, c in opts if t and c in legal and t != legal[c].type.value)
        stats["halluc_no_entity"] += no_entity
        stats["halluc_unreachable"] += unreachable
        stats["type_errors"] += type_err
        turn_metrics = {"listed": len(listed), "legal": len(legal), "listed_legal": len(ok),
                        "missed": sorted(list(c) for c in set(legal) - listed),
                        "hallucinated": sorted(list(c) for c in listed - set(legal)),
                        "halluc_no_entity": no_entity, "halluc_unreachable": unreachable, "type_errors": type_err}

        violation = None
        if choice is None:
            violation = "parse_fail"
            stats["choice_parse_fail"] += 1
        elif choice not in legal:
            violation = "illegal"
            stats["choice_illegal"] += 1
        fallback = False
        if violation is not None:
            stats["retries"] += 1
            why = "could not be read" if choice is None else f"{choice} is not an action you can take right now"
            retry_msg = user_msg + f"\n\nYour previous answer {why}. List the options again and choose one."
            response2 = _call_llm(candidate_prompt, retry_msg, task_model=task_model, task_mode=task_mode,
                                  temperature=temperature)
            _, choice2 = _parse_map_enum(response2)
            turn_metrics["retry_choice"] = list(choice2) if choice2 else None
            if choice2 in legal:
                choice = choice2
                response = response + "\n\n[RETRY]\n" + response2
            else:
                stats["fallbacks"] += 1
                fallback = True
                hid = _heuristic_pick(actions, state)
                if hid is None:
                    state.failed = True
                    state.failure_reason = "Stuck — only unwinnable fights remain"
                    emit({"type": "stuck", "reason": state.failure_reason})
                    break
                choice = next((a.x, a.y) for a in actions if a.action_id == hid)

        chosen = legal[choice]
        override_info = None
        if not os.environ.get("MOTA_DISABLE_OVERRIDES"):
            chosen, override_info = _apply_override(chosen, actions, state, emit, state.turn + 1)
            if override_info:
                stats["overrides"] += 1
        lethal_stop = _lethal_only_stop(chosen, actions)
        if lethal_stop:
            state.failed = True
            state.failure_reason = f"Stuck — only lethal/unwinnable actions remain (LLM chose {lethal_stop['action']})"
            state.lethal_only_stop = lethal_stop
            emit({"type": "stuck", "reason": state.failure_reason, "lethal_only": True, **lethal_stop})
            break

        trace = state.apply_action(chosen)
        recent.append(trace.action.label())
        event = {"type": "turn", "turn": trace.turn, "action": trace.action.label(), "action_id": chosen.action_id,
                 "forced": False, "fallback": fallback, "elapsed_ms": elapsed_ms, "state_text": user_msg,
                 "actions_text": "", "hero": _hero_dict(state), "enemies_remaining": state.remaining_enemies(),
                 "removed": [list(r) for r in state.removed], "sub_steps": trace.sub_steps,
                 "action_detail": {"type": chosen.type.value, "x": chosen.x, "y": chosen.y, "name": chosen.name},
                 "action_path": [list(p) for p in getattr(chosen, "path", [])],
                 "llm_response": response, "map_enum": {**turn_metrics, "violation": violation, "truncated": truncated}}
        thinking = _extract_llm_thinking(response)
        if thinking:
            event["llm_thinking"] = thinking
        if override_info:
            event.update(override_info)
        emit(event)

    fid = _scenario.name if _scenario else "mt3-walkthrough"
    result = score_run(state, fixture_id=fid)
    result["hero"] = _hero_dict(state)
    result["lethal_only_stop"] = getattr(state, "lethal_only_stop", None)
    n = stats["llm_turns"] or 1
    stats["precision"] = round(stats["options_legal"] / stats["options_listed"], 4) if stats["options_listed"] else None
    stats["recall"] = round(stats["legal_found"] / stats["legal_total"], 4) if stats["legal_total"] else None
    stats["choice_violation_rate"] = round((stats["choice_illegal"] + stats["choice_parse_fail"]) / n, 4)
    result["map_enum"] = stats
    result.setdefault("tracking", {})["llm_calls"] = stats["llm_turns"] + stats["retries"]
    result["tracking"]["parse_errors"] = stats["choice_parse_fail"]
    emit({"type": "result", **result})
    return result


# ---------------------------------------------------------------------------
# LLM-built graph agent: the LLM converts the map into a graph (what is reachable now, what lies
# behind what), the engine checks the graph, then the LLM chooses from its checked graph.
# ---------------------------------------------------------------------------

_MAP_GRAPH_CONTRACT = """\
In this episode you do NOT get a list of actions. You see only the floor grid, the entity details and
your stats. First turn the map into a graph problem. Write this block and nothing after it:
GRAPH:
now <type> (x,y)            <- an action you can take right now (type = fight / collect / open_door / stairs)
behind (x,y) <type> (a,b)   <- target (a,b) becomes reachable once the action at (x,y) is taken
List every action you can take now, and for each of them what it opens up (one level is enough).
(You can walk over empty floor, stairs and cleared tiles; walls, closed doors and monsters block walking;
a door needs a key of its colour; items on your way are picked up automatically.)
The engine will check your graph and then ask you to choose."""

_MAP_GRAPH_CHOOSE = """\
ENGINE CHECK OF YOUR GRAPH (only your own claims are checked; nothing is added):
{check}
Now choose one of YOUR actions that the engine confirmed as possible now. Give a short reasoning, then end with:
FINAL_CHOICE: (x,y)"""


def _parse_map_graph(response: str):
    """([(type, (x,y))] now-nodes, [((x,y) source, type, (a,b) target)] behind-edges) from the visible answer."""
    text = re.sub(r"<think>.*?</think>", "", response or "", flags=re.DOTALL)
    if "<think>" in text:
        text = text.split("<think>")[0]
    m = list(re.finditer(r"GRAPH\s*:", text, re.IGNORECASE))
    block = text[m[-1].end():] if m else ""
    nodes, edges = [], []
    coord = r"\(\s*(\d+)\s*,\s*(\d+)\s*\)"
    for line in block.splitlines():
        low = line.strip().lower()
        e = re.match(rf"[-*\s]*behind\s*{coord}\s*([a-z_]*)\s*{coord}", low)
        if e:
            edges.append(((int(e.group(1)), int(e.group(2))), _MAP_ENUM_TYPES.get(e.group(3)), (int(e.group(4)), int(e.group(5)))))
            continue
        n = re.match(rf"[-*\s]*now\s*([a-z_]*)\s*{coord}", low)
        if n:
            nodes.append((_MAP_ENUM_TYPES.get(n.group(1)), (int(n.group(2)), int(n.group(3)))))
    return nodes, edges


def evaluate_map_graph(
    candidate_prompt: str,
    on_event=None,
    task_model: str | None = None,
    task_mode: str | None = None,
    temperature: float = 0.0,
) -> dict:
    """Two calls per decision: (1) the LLM writes a graph from the grid; (2) the engine checks every
    claim (now-nodes against the legal set, behind-edges against the action's own unlock set) and
    the LLM chooses from its confirmed nodes. Engine assists as in the reactive loop. An illegal or
    unreadable final choice falls back to the heuristic (flagged)."""
    from ..game.types import ActionType

    def emit(event):
        if on_event:
            on_event(event)

    state = _create_state(lookahead_depth=3)
    resolved_task_model = _get_task_model(task_model)
    resolved_task_mode = task_mode or ("thinking" if "thinking" in resolved_task_model else "instruct")
    emit({"type": "start", "floor_id": state.floor.floor_id, "hero": _hero_dict(state),
          "initial_enemies": state.initial_enemies, "state_text": state.format_state(), "mode": "llm",
          "task_model": resolved_task_model, "task_mode": resolved_task_mode, "map": _serialize_rich_map(state),
          "runtime_system_prompt": candidate_prompt, "eval_mode": "map-graph"})

    recent: list[str] = []
    stats = {"llm_turns": 0, "nodes_listed": 0, "nodes_legal": 0, "legal_total": 0, "edges_listed": 0,
             "edges_correct": 0, "truncated": 0, "graph_empty": 0, "choice_illegal": 0, "choice_parse_fail": 0,
             "choice_unconfirmed": 0, "fallbacks": 0, "overrides": 0}

    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        actions = state.get_actions()
        if not actions:
            state.failed = True
            state.failure_reason = "Stuck — no legal action"
            emit({"type": "stuck", "reason": state.failure_reason})
            break
        forced = None
        if len(actions) == 1:
            if actions[0].type == ActionType.FIGHT and not actions[0].can_win:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fights remain"
                emit({"type": "stuck", "reason": state.failure_reason})
                break
            forced = (actions[0], "only action")
        if forced is None:
            ac = _pick_auto_collect_action(state, actions)
            if ac is not None:
                forced = (ac, "auto-collect")
            else:
                zero = next((a for a in sorted(actions, key=lambda a: a.path_steps)
                             if a.type == ActionType.FIGHT and a.can_win and a.total_damage == 0), None)
                if zero is not None:
                    forced = (zero, "auto-fight (0 HP)")
        if forced is not None:
            trace = state.apply_action(forced[0])
            recent.append(trace.action.label())
            emit({"type": "turn", "turn": trace.turn, "action": trace.action.label(), "action_id": forced[0].action_id,
                  "forced": True, "forced_reason": forced[1], "hero": _hero_dict(state),
                  "enemies_remaining": state.remaining_enemies(), "removed": [list(r) for r in state.removed],
                  "sub_steps": trace.sub_steps, "action_path": [list(p) for p in getattr(forced[0], "path", [])]})
            continue

        legal = {(a.x, a.y): a for a in actions}
        base = _map_enum_state_text(state, recent, with_costs=False).replace(_MAP_ENUM_CONTRACT, _MAP_GRAPH_CONTRACT)
        stats["llm_turns"] += 1
        t0 = time.perf_counter()
        r1 = _call_llm(candidate_prompt, base, task_model=task_model, task_mode=task_mode, temperature=temperature)
        trunc1 = bool(_last_llm_truncated)
        nodes, edges = ([], []) if trunc1 else _parse_map_graph(r1)
        stats["truncated"] += trunc1

        listed = {c for _, c in nodes}
        ok = listed & set(legal)
        stats["nodes_listed"] += len(listed)
        stats["nodes_legal"] += len(ok)
        stats["legal_total"] += len(legal)
        if not nodes:
            stats["graph_empty"] += 1
        edge_ok = []
        for src, _t, dst in edges:
            a = legal.get(src)
            unlocked = {tuple(u["pos"]) for u in (a.unlocks_tree or [])} if a is not None else set()
            good = a is not None and dst in unlocked
            edge_ok.append(good)
        stats["edges_listed"] += len(edges)
        stats["edges_correct"] += sum(edge_ok)
        check_lines = []
        for t, c in nodes:
            check_lines.append(f"  now {t or '?'} {c}: {'POSSIBLE now' if c in legal else 'NOT possible now'}")
        for (src, t, dst), good in zip(edges, edge_ok):
            check_lines.append(f"  behind {src} -> {dst}: {'correct' if good else 'wrong'}")
        if not check_lines:
            check_lines.append("  (no graph could be read from your answer)")
        choose_msg = base + "\n\nYOUR GRAPH:\n" + "\n".join(f"  now {t} {c}" for t, c in nodes) + \
            "\n\n" + _MAP_GRAPH_CHOOSE.format(check="\n".join(check_lines))
        r2 = _call_llm(candidate_prompt, choose_msg, task_model=task_model, task_mode=task_mode, temperature=temperature)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        trunc2 = bool(_last_llm_truncated)
        _, choice = ([], None) if trunc2 else _parse_map_enum(r2)

        violation = None
        if choice is None:
            violation = "parse_fail"
            stats["choice_parse_fail"] += 1
        elif choice not in legal:
            violation = "illegal"
            stats["choice_illegal"] += 1
        elif choice not in ok:
            stats["choice_unconfirmed"] += 1  # legal, but not a node the engine confirmed
        fallback = False
        if violation is not None:
            stats["fallbacks"] += 1
            fallback = True
            hid = _heuristic_pick(actions, state)
            if hid is None:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fights remain"
                emit({"type": "stuck", "reason": state.failure_reason})
                break
            choice = next((a.x, a.y) for a in actions if a.action_id == hid)

        chosen = legal[choice]
        override_info = None
        if not os.environ.get("MOTA_DISABLE_OVERRIDES"):
            chosen, override_info = _apply_override(chosen, actions, state, emit, state.turn + 1)
            if override_info:
                stats["overrides"] += 1
        lethal_stop = _lethal_only_stop(chosen, actions)
        if lethal_stop:
            state.failed = True
            state.failure_reason = f"Stuck — only lethal/unwinnable actions remain (LLM chose {lethal_stop['action']})"
            state.lethal_only_stop = lethal_stop
            emit({"type": "stuck", "reason": state.failure_reason, "lethal_only": True, **lethal_stop})
            break

        trace = state.apply_action(chosen)
        recent.append(trace.action.label())
        event = {"type": "turn", "turn": trace.turn, "action": trace.action.label(), "action_id": chosen.action_id,
                 "forced": False, "fallback": fallback, "elapsed_ms": elapsed_ms, "state_text": choose_msg,
                 "actions_text": "", "hero": _hero_dict(state), "enemies_remaining": state.remaining_enemies(),
                 "removed": [list(r) for r in state.removed], "sub_steps": trace.sub_steps,
                 "action_detail": {"type": chosen.type.value, "x": chosen.x, "y": chosen.y, "name": chosen.name},
                 "action_path": [list(p) for p in getattr(chosen, "path", [])],
                 "llm_response": r1 + "\n\n[CHOOSE]\n" + r2,
                 "map_graph": {"nodes": [[t, list(c)] for t, c in nodes], "edges": [[list(s), t, list(d)] for s, t, d in edges],
                               "legal": len(legal), "nodes_legal": len(ok), "edges_correct": sum(edge_ok),
                               "missed": sorted(list(c) for c in set(legal) - listed), "violation": violation,
                               "truncated": [trunc1, trunc2]}}
        thinking = _extract_llm_thinking(r2)
        if thinking:
            event["llm_thinking"] = thinking
        if override_info:
            event.update(override_info)
        emit(event)

    fid = _scenario.name if _scenario else "mt3-walkthrough"
    result = score_run(state, fixture_id=fid)
    result["hero"] = _hero_dict(state)
    result["lethal_only_stop"] = getattr(state, "lethal_only_stop", None)
    n = stats["llm_turns"] or 1
    stats["node_precision"] = round(stats["nodes_legal"] / stats["nodes_listed"], 4) if stats["nodes_listed"] else None
    stats["node_recall"] = round(stats["nodes_legal"] / stats["legal_total"], 4) if stats["legal_total"] else None
    stats["edge_accuracy"] = round(stats["edges_correct"] / stats["edges_listed"], 4) if stats["edges_listed"] else None
    stats["choice_violation_rate"] = round((stats["choice_illegal"] + stats["choice_parse_fail"]) / n, 4)
    result["map_graph"] = stats
    result.setdefault("tracking", {})["llm_calls"] = 2 * stats["llm_turns"]
    result["tracking"]["parse_errors"] = stats["choice_parse_fail"]
    emit({"type": "result", **result})
    return result

