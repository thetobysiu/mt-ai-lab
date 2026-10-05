"""
Evaluate fine-tuned student model against BFS oracle.

Loads the LoRA-adapted model and replays the BFS-optimal route, measuring
per-decision alignment (same as align_prompt_to_bfs but with local model).

Usage:
    cd mota-gepa
    python -m training.eval_finetuned --lora training/output/stage_a/lora --floor simple
"""
from __future__ import annotations

# Python 3.14 pickle patch (must be before any imports that trigger dill)
import sys
if sys.version_info >= (3, 14):
    try:
        import dill._dill as _dill_mod
        _orig_smd = _dill_mod.save_module_dict
        def _patched_smd(pickler, obj):
            try:
                return _orig_smd(pickler, obj)
            except TypeError as e:
                if '_batch_setitems' in str(e):
                    pickler.save_reduce(dict, (list(obj.items()),), obj=obj)
                else:
                    raise
        _dill_mod.save_module_dict = _patched_smd
        _dill_mod.Pickler.dispatch[dict] = _patched_smd
    except Exception:
        pass

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

log = logging.getLogger(__name__)

# Must match the system prompt used during training
SYSTEM_PROMPT = """\
You are a strategic planner for Magic Tower (MOTA). Goal: defeat the boss with maximum remaining HP.

RULES:
- Damage = max(0, monATK - heroDEF) * ceil(monHP / max(1, heroATK - monDEF))
- DEF reduces ALL future fight damage (compounding). ATK reduces turns per fight.
- Free items cost 0 HP — always collect first.

DECISION TREE ANALYSIS:
For each available action, evaluate:
1. What does this action unlock? (items, doors, paths to boss)
2. What is the projected final HP if I choose this path? (boss reachable?)
3. Is this a dead end? (boss unreachable = never choose)
4. Among boss-reachable paths, which gives highest final HP?

PRIORITY ORDER:
1. Free items (gems, potions, keys) — zero cost
2. Fights that unlock stat gems or open the path to boss
3. Doors that lead to items/boss — avoid dead-end doors
4. Expensive fights only if required for boss path

Reply: ACTION: <number>"""


# ── Backend: Unsloth (LoRA) ────────────────────────────────────

def load_model(lora_path: str, max_seq_length: int = 2048):
    """Load base model + LoRA adapter for inference."""
    import warnings
    warnings.filterwarnings("ignore")

    from unsloth import FastModel
    import torch

    # Verify CUDA is available
    if not torch.cuda.is_available():
        print("[CRITICAL] CUDA not available! Model will run on CPU (extremely slow).")
        print(f"  torch version: {torch.__version__}")
        print(f"  torch.cuda.is_available(): {torch.cuda.is_available()}")
        print("  Fix: pip install torch --index-url https://download.pytorch.org/whl/cu126")
    else:
        gpu = torch.cuda.get_device_properties(0)
        print(f"[GPU] {gpu.name}, VRAM: {gpu.total_memory / 1024**3:.1f} GB, CUDA: {torch.version.cuda}")

    base_model = "LiquidAI/LFM2.5-1.2B-Thinking"
    log.info("Loading base model: %s", base_model)

    # RTX 2080 (Turing, compute 7.5) needs explicit float16 — dtype=None can mismatch
    model, tokenizer = FastModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
        full_finetuning=False,
        dtype=torch.float16,
    )

    # Load LoRA adapters
    log.info("Loading LoRA adapters from: %s", lora_path)
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, lora_path)
    model.eval()

    # Enable faster inference
    FastModel.for_inference(model)

    # Verify model is actually on GPU
    device = next(model.parameters()).device
    print(f"[Model] Loaded on device: {device}")
    if device.type == 'cpu':
        print("[WARNING] Model is on CPU! Inference will be extremely slow.")
        print("  Try: pip install torch --index-url https://download.pytorch.org/whl/cu126")
    else:
        allocated = torch.cuda.memory_allocated() / 1024**2
        print(f"[Model] GPU memory used: {allocated:.0f} MB")

    return model, tokenizer


# ── Backend: GGUF (llama-cpp-python) ───────────────────────────

def load_model_gguf(gguf_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1):
    """Load a GGUF model for inference via llama-cpp-python.

    Returns a (llm, None) tuple — tokenizer is handled internally by llama.cpp.
    """
    try:
        from llama_cpp import Llama
    except ImportError:
        print("ERROR: llama-cpp-python not installed. Install with:")
        print("  pip install llama-cpp-python")
        print("  For CUDA: CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python")
        sys.exit(1)

    print(f"[GGUF] Loading model: {gguf_path}")
    print(f"[GGUF] n_ctx={n_ctx}, n_gpu_layers={n_gpu_layers}")

    llm = Llama(
        model_path=gguf_path,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        verbose=False,
    )
    print(f"[GGUF] Model loaded successfully")
    return llm, None


def generate_action_gguf(llm, system_prompt: str, user_msg: str,
                         valid_ids: set[int], max_new_tokens: int = 30
                         ) -> tuple[int | None, str]:
    """Generate a response from GGUF model and parse ACTION: N."""
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=max_new_tokens,
        temperature=0.0,
    )
    text = response["choices"][0]["message"]["content"]
    action_id = _parse_action_id(text, valid_ids)
    return action_id, text


# ── Backend: Ollama ────────────────────────────────────────────

OLLAMA_URL = "http://localhost:11434/api/chat"

def load_model_ollama(model_name: str = "mota-finetuned"):
    """Verify Ollama model is available. Returns (model_name, None)."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        # Match with or without :latest tag
        found = any(model_name in m for m in models)
        if not found:
            print(f"[Ollama] WARNING: Model '{model_name}' not found. Available: {models}")
            print(f"[Ollama] Create it with: ollama create {model_name} -f Modelfile")
            sys.exit(1)
        print(f"[Ollama] Model '{model_name}' ready (GPU-accelerated)")
    except Exception as e:
        print(f"[Ollama] ERROR: Cannot connect to Ollama at localhost:11434: {e}")
        print("[Ollama] Start Ollama first or install from https://ollama.com")
        sys.exit(1)
    return model_name, None


def generate_action_ollama(model_name: str, system_prompt: str, user_msg: str,
                           valid_ids: set[int], max_new_tokens: int = 512
                           ) -> tuple[int | None, str]:
    """Generate a response via Ollama API and parse ACTION: N."""
    import urllib.request

    body = json.dumps({
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "options": {"temperature": 0, "num_predict": max_new_tokens},
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())

    text = result["message"]["content"]
    action_id = _parse_action_id(text, valid_ids)
    return action_id, text


def generate_action(model, tokenizer, system_prompt: str, user_msg: str,
                    valid_ids: set[int], max_new_tokens: int = 20) -> tuple[int | None, str]:
    """Generate a response from the local model and parse ACTION: N.
    
    Uses greedy decoding (no sampling) for speed on RTX 2080.
    max_new_tokens=20 is enough to capture 'ACTION: N' responses.
    """
    import torch

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    input_ids = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        tokenize=True,
        return_dict=True,
    ).to(model.device)

    # Suppress max_new_tokens/max_length conflict warning
    import transformers.utils.logging as hf_logging
    hf_logging.set_verbosity_error()

    with torch.no_grad():
        output = model.generate(
            **input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=False,  # Greedy decoding (fastest)
            num_beams=1,       # No beam search (avoid OOM on RTX 2080)
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            use_cache=False,   # Disable KV cache to avoid compiled module crashes
        )

    generated = output[0][input_ids["input_ids"].shape[1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True)

    # Parse ACTION: N
    action_id = _parse_action_id(text, valid_ids)
    return action_id, text


def _parse_action_id(text: str, valid_ids: set[int]) -> int | None:
    """Extract ACTION: <number> from response."""
    matches = re.findall(r'ACTION:\s*(\d+)', text)
    for m in reversed(matches):  # Last match takes priority
        aid = int(m)
        if aid in valid_ids:
            return aid
    # Fallback: any number on the last line
    for line in reversed(text.strip().split('\n')):
        nums = re.findall(r'\b(\d+)\b', line)
        for n in reversed(nums):
            if int(n) in valid_ids:
                return int(n)
    return None


def _parse_plan(text: str, valid_ids: set[int]) -> list[int]:
    """Parse PLAN: id1, id2, ... or fallback to extracting integers."""
    # Try PLAN: format first
    m = re.search(r'PLAN:\s*([\d,\s]+)', text)
    if m:
        ids = [int(x.strip()) for x in m.group(1).split(',') if x.strip().isdigit()]
        return [x for x in ids if x in valid_ids]
    # Fallback: all ACTION: N occurrences
    action_ids = [int(m) for m in re.findall(r'ACTION:\s*(\d+)', text)]
    valid = [x for x in action_ids if x in valid_ids]
    if valid:
        return valid
    # Last fallback: all integers
    all_ints = [int(m) for m in re.findall(r'\b(\d+)\b', text)]
    return [x for x in all_ints if x in valid_ids]


def evaluate(lora_path: str = None, gguf_path: str = None,
             ollama_model: str = None,
             floor_name: str = "simple",
             eval_mode: str = "reactive", verbose: bool = False,
             n_gpu_layers: int = -1):
    """Evaluate fine-tuned model against BFS oracle.

    Provide one of: lora_path (Unsloth), gguf_path (llama.cpp), or ollama_model (Ollama).

    eval_mode:
      reactive    — one LLM call per decision (default)
      multistep-N — plan N actions per call, re-plan when queue empty/invalid
      oneshot     — single LLM call for entire floor plan
    """
    from mota.game.types import ActionType
    from training.align_prompt_to_bfs import (
        _load_floor_scenario, _bfs_optimal_action, _bfs_optimal_actions,
    )

    # Select backend
    use_gguf = gguf_path is not None
    use_ollama = ollama_model is not None
    if use_ollama:
        model, tokenizer = load_model_ollama(ollama_model)
        backend_label = f"Ollama: {ollama_model}"
    elif use_gguf:
        model, tokenizer = load_model_gguf(gguf_path, n_gpu_layers=n_gpu_layers)
        backend_label = f"GGUF: {gguf_path}"
    else:
        model, tokenizer = load_model(lora_path)
        backend_label = f"LoRA: {lora_path}"

    state, gd, scenario, bfs_hp = _load_floor_scenario(floor_name)

    # Build runtime prompt with floor map
    floor_map_text = state.format_floor_map()
    runtime_prompt = SYSTEM_PROMPT + "\n\n" + floor_map_text

    matches = 0
    equiv_matches = 0
    total = 0
    decision_idx = 0
    llm_calls = 0

    # Multistep plan buffer
    ms_plan = []
    chunk_size = 5
    if eval_mode.startswith("multistep"):
        parts = eval_mode.split("-")
        if len(parts) > 1:
            chunk_size = int(parts[1])

    print(f"\nEvaluating fine-tuned model on {floor_name} (BFS HP={bfs_hp})")
    print(f"Backend: {backend_label}")
    print(f"Mode: {eval_mode}\n")

    while (not state.goal_reached and not state.failed
           and state.turn < state.max_turns):

        actions = state.get_actions()
        if not actions:
            break

        if len(actions) == 1:
            only = actions[0]
            if only.type == ActionType.FIGHT and not only.can_win:
                break
            state.apply_action(only)
            continue

        # Find all equally-optimal BFS actions
        optimal_set = _bfs_optimal_actions(
            state.floor, state.hero, state.removed, actions,
            gd, scenario.goal,
        )
        if not optimal_set:
            log.warning("No BFS solution from decision %d", decision_idx)
            break

        bfs_action_id = max(optimal_set.keys())
        bfs_action = next(a for a in actions if a.action_id == bfs_action_id)

        # Format state for model
        state_text = state.format_state()
        actions_text = state.format_actions(actions)
        valid_ids = {a.action_id for a in actions}

        llm_action_id = None
        elapsed = 0.0

        # Select generation function based on backend
        def _generate(sys_prompt, usr_msg, vids, max_tok=512):
            if use_ollama:
                return generate_action_ollama(model, sys_prompt, usr_msg, vids, max_tok)
            elif use_gguf:
                return generate_action_gguf(model, sys_prompt, usr_msg, vids, max_tok)
            else:
                return generate_action(model, tokenizer, sys_prompt, usr_msg, vids, max_tok)

        if eval_mode == "reactive":
            user_msg = (
                f"{state_text}\n\n{actions_text}\n\n"
                "Choose the best action. Reply: ACTION: <number>"
            )
            t0 = time.time()
            llm_action_id, response_text = _generate(
                runtime_prompt, user_msg, valid_ids, max_tok=500,
            )
            elapsed = time.time() - t0
            llm_calls += 1

        elif eval_mode.startswith("multistep"):
            # Try to use buffered plan first
            while ms_plan and ms_plan[0] not in valid_ids:
                ms_plan.pop(0)  # Discard stale actions

            if ms_plan:
                llm_action_id = ms_plan.pop(0)
            else:
                # Re-plan
                user_msg = (
                    f"{state_text}\n\n{actions_text}\n\n"
                    f"Plan the next {chunk_size} actions. "
                    f"Reply: PLAN: id1, id2, ..., id{chunk_size}"
                )
                t0 = time.time()
                _, response_text = _generate(
                    runtime_prompt, user_msg, valid_ids, max_tok=100,
                )
                elapsed = time.time() - t0
                llm_calls += 1
                plan_ids = _parse_plan(response_text, valid_ids)
                if plan_ids:
                    llm_action_id = plan_ids[0]
                    ms_plan = plan_ids[1:]
                else:
                    llm_action_id = None

        is_exact = llm_action_id == bfs_action_id
        is_equiv = llm_action_id in optimal_set
        is_match = is_exact or is_equiv
        total += 1
        if is_match:
            matches += 1
        if is_equiv and not is_exact:
            equiv_matches += 1

        llm_action = next((a for a in actions if a.action_id == llm_action_id), None) if llm_action_id else None
        equiv_tag = "~" if is_equiv and not is_exact else ""
        status = f"Y{equiv_tag}" if is_match else "N"
        n_equiv = len(optimal_set)
        bfs_label = bfs_action.label() if hasattr(bfs_action, 'label') else str(bfs_action_id)
        llm_label = llm_action.label() if llm_action and hasattr(llm_action, 'label') else f'id={llm_action_id}'
        equiv_info = f" [{n_equiv} equiv]" if n_equiv > 1 else ""
        time_info = f" ({elapsed:.1f}s)" if elapsed > 0 else ""

        print(f"  {status:3s} Decision {decision_idx:2d}: "
              f"BFS={bfs_label:<35s} LLM={llm_label}{equiv_info}{time_info}")

        if verbose and not is_match:
            if 'response_text' in dir():
                short = response_text[:200].replace('\n', ' ')
                print(f"      Reasoning: {short}...")

        # Always execute BFS action to stay on optimal path
        state.apply_action(bfs_action)
        decision_idx += 1

    accuracy = matches / max(1, total)
    print(f"\n{'=' * 60}")
    print(f"Fine-Tuned Model Evaluation -- {floor_name} ({eval_mode})")
    print(f"BFS alignment: {matches}/{total} = {accuracy:.1%}")
    if equiv_matches:
        print(f"  (exact: {matches - equiv_matches}, equiv-optimal: {equiv_matches})")
    print(f"Final HP: {state.hero.hp}")
    print(f"Goal reached: {state.goal_reached}")
    print(f"LLM calls: {llm_calls}")
    print(f"{'=' * 60}")

    return {
        "accuracy": accuracy,
        "matches": matches,
        "equiv_matches": equiv_matches,
        "total": total,
        "final_hp": state.hero.hp,
        "goal_reached": state.goal_reached,
        "eval_mode": eval_mode,
        "llm_calls": llm_calls,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate fine-tuned model vs BFS")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lora", help="Path to LoRA adapter directory (Unsloth backend)")
    group.add_argument("--gguf", help="Path to GGUF model file (llama.cpp backend)")
    group.add_argument("--ollama", help="Ollama model name (e.g. mota-finetuned)")
    parser.add_argument("--floor", default="simple", help="Floor to evaluate")
    parser.add_argument("--mode", default="reactive",
                        help="Eval mode: reactive, multistep-5, multistep-10, oneshot")
    parser.add_argument("--n-gpu-layers", type=int, default=-1,
                        help="GPU layers for GGUF (-1=all, 0=CPU only)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load env
    from dotenv import load_dotenv
    for env_dir in [_root]:
        if (env_dir / ".env").exists():
            load_dotenv(env_dir / ".env")
            break

    evaluate(
        lora_path=args.lora,
        gguf_path=args.gguf,
        ollama_model=args.ollama,
        floor_name=args.floor,
        eval_mode=args.mode,
        verbose=args.verbose,
        n_gpu_layers=args.n_gpu_layers,
    )


if __name__ == "__main__":
    main()
