"""
Vision-Language Experiment for MOTA Game Agent.

Compares three input modalities for LLM game playing:
  1. Text-only:  structured text state + action list (baseline)
  2. Image+Text: rendered map image + text state + action list (hybrid)
  3. Image-only: rendered map image + minimal text action list (vision-first)

Models:
  - Text-only:  LFM2.5-1.2B-Thinking (via Unsloth QLoRA or base)
  - Vision:     LFM2.5-VL-1.6B (Transformers, local GPU)

Hardware target: RTX 2080 8GB (4-bit quantized).

Usage:
    python -m training.vl_experiment --mode all
    python -m training.vl_experiment --mode image_text --floor MT3
    python -m training.vl_experiment --render-only  # Just render and save images
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Force UTF-8 stdout on Windows to handle Chinese entity names in output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root on path
_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FLOORS_DIR = Path(__file__).resolve().parents[1] / "data" / "games" / "24" / "project" / "floors"


def _load_env():
    try:
        from dotenv import load_dotenv
        for env_dir in [_root]:
            env_file = env_dir / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                break
    except ImportError:
        pass


# ── VL Model Loading ───────────────────────────────────────────────────────

_vl_model = None
_vl_processor = None
_vl_load_failed = False  # Set after first load failure to avoid retrying


def _load_vl_model():
    """Load LFM2.5-VL-1.6B for local GPU inference using no-mmap streaming reader."""
    global _vl_model, _vl_processor, _vl_load_failed
    if _vl_load_failed:
        raise RuntimeError("VL model previously failed to load; skipping retry")
    if _vl_model is not None:
        return _vl_model, _vl_processor

    print("Loading LFM2.5-VL-1.6B...")
    import json
    import os
    import struct
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText, AutoConfig

    model_id = "LiquidAI/LFM2.5-VL-1.6B"

    def _stream_safetensors(path: str, device: str = "cuda", dtype=torch.float16):
        """Read safetensors without mmap by streaming with read() — avoids Windows paging file error."""
        tensors = {}
        dtype_map = {
            "F32": torch.float32, "F16": torch.float16,
            "BF16": torch.bfloat16, "I32": torch.int32,
            "I64": torch.int64, "BOOL": torch.bool,
        }
        with open(path, "rb") as f:
            header_len = struct.unpack("<Q", f.read(8))[0]
            header_data = json.loads(f.read(header_len).decode("utf-8"))
            data_offset = 8 + header_len
            for key, info in header_data.items():
                if key == "__metadata__":
                    continue
                offsets = info["data_offsets"]
                f.seek(data_offset + offsets[0])
                raw = f.read(offsets[1] - offsets[0])
                torch_dtype = dtype_map.get(info["dtype"], torch.float32)
                t = torch.frombuffer(bytearray(raw), dtype=torch_dtype)
                if info["shape"]:
                    t = t.reshape(info["shape"])
                tensors[key] = t.to(device=device, dtype=dtype, non_blocking=True)
        return tensors

    try:
        # Find local model path in HF cache
        cache_root = os.path.expanduser("~/.cache/huggingface/hub/models--LiquidAI--LFM2.5-VL-1.6B/snapshots")
        snap = sorted(os.listdir(cache_root))[-1]
        model_file = os.path.join(cache_root, snap, "model.safetensors")
        config_dir = os.path.join(cache_root, snap)

        print(f"  Config dir: {config_dir}")
        config = AutoConfig.from_pretrained(config_dir)

        print(f"  Building model on CPU (float16)...")
        with torch.device("cpu"):
            _vl_model = AutoModelForImageTextToText.from_config(config, dtype=torch.float16)

        print(f"  Streaming weights to CUDA (no mmap)...")
        state_dict = _stream_safetensors(model_file, device="cuda", dtype=torch.float16)
        # Load weights: missing keys stay as CPU-initialized float16 buffers
        missing, unexpected = _vl_model.load_state_dict(state_dict, strict=False)
        if missing:
            print(f"  Warning: {len(missing)} missing keys (kept as CPU-init)")
        del state_dict

        # Move entire model to CUDA (CPU buffers + CUDA weights → all CUDA)
        _vl_model = _vl_model.to("cuda")

        _vl_processor = AutoProcessor.from_pretrained(config_dir)
        print(f"  Model loaded. CUDA: {torch.cuda.memory_allocated() / 1e9:.1f} GB")

    except Exception as e:
        _vl_load_failed = True
        raise RuntimeError(f"VL model load failed: {e}") from e

    return _vl_model, _vl_processor


def _call_cloud_vl_model(
    image,
    text_prompt: str,
    system_prompt: str = "",
    model_name: str = "qwen3-omni-30b-a3b-instruct",
    max_tokens: int = 512,
) -> str:
    """Call a cloud vision-language model via SAIA API. Image is base64-encoded PNG."""
    import base64
    import io
    from openai import OpenAI

    api_key = os.environ.get("SAIA_API_KEY", "")
    base_url = os.environ.get("SAIA_BASE_URL", "https://chat-ai.academiccloud.de/v1")
    if not api_key:
        raise RuntimeError("SAIA_API_KEY not set — cannot call cloud VL model")
    client = OpenAI(api_key=api_key, base_url=base_url)

    user_content = []
    if image is not None:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    user_content.append({"type": "text", "text": text_prompt})

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    resp = client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()


def _call_vl_model(image, text_prompt: str, system_prompt: str = "", max_tokens: int = 512) -> str:
    """
    Call LFM2.5-VL-1.6B with an image and text prompt.

    Args:
        image: PIL Image or None (text-only mode).
        text_prompt: The user's text message.
        system_prompt: System message.
        max_tokens: Maximum generation tokens.

    Returns:
        Generated text response.
    """
    model, processor = _load_vl_model()

    # Build conversation in the model's expected format
    user_content = []
    if image is not None:
        user_content.append({"type": "image", "image": image})
    user_content.append({"type": "text", "text": text_prompt})

    messages = []
    if system_prompt:
        # VL processor requires content as a list of typed items, not a plain string
        messages.append({"role": "system", "content": [{"type": "text", "text": system_prompt}]})
    messages.append({"role": "user", "content": user_content})

    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
        tokenize=True,
    )
    # Fallback: apply_chat_template may return a plain string (older processor)
    if isinstance(inputs, str):
        inputs = processor(text=inputs, return_tensors="pt")
    inputs = {k: v.to(model.device) if hasattr(v, "to") else v for k, v in inputs.items()}

    import torch
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=0.1,
            do_sample=True,
            min_p=0.15,
            repetition_penalty=1.05,
        )

    # Decode only the generated tokens (skip input)
    generated = outputs[0, inputs["input_ids"].shape[1]:]
    response = processor.tokenizer.decode(generated, skip_special_tokens=True)
    return response.strip()


# ── Experiment Modes ───────────────────────────────────────────────────────

VL_SYSTEM_PROMPT = """\
You are a strategic planner for Magic Tower (MOTA), a deterministic dungeon-crawling RPG.

RULES:
- Damage = max(0, monATK - heroDEF) * ceil(monHP / max(1, heroATK - monDEF))
- Collect FREE items (gems, keys, potions) before fighting enemies.
- Buy DEF at shops first (DEF permanently reduces all future fight damage).
- Kill ALL enemies on the floor. Minimize HP loss.
- Lookahead value (effCost = damage - lookahead) tells you the net cost including future unlocks.
- Never waste keys on dead-end doors.

RESPONSE: Brief reasoning, then: ACTION: <number>"""


def evaluate_vl(
    mode: str = "image_text",
    floor_id: str = "MT3",
    max_turns: int = 100,
    cloud_model: str | None = None,
) -> dict:
    """
    Run a VL evaluation experiment.

    Args:
        mode: "text_only", "image_text", or "image_only"
        floor_id: Floor to evaluate on
        max_turns: Maximum decision turns

    Returns:
        Result dict with score, tracking, and per-turn trace.
    """
    from mota.optimizer.evaluator import (
        _create_state, _heuristic_pick, _parse_action_id, _pick_auto_priority_action,
        configure_scenario, configure_mt3_scenario,
    )
    from mota.game.map_renderer import render_map_image
    from mota.benchmark.scorer import score_run

    # Configure scenario
    if floor_id == "MT3":
        configure_mt3_scenario()
    else:
        floor_file = _FLOORS_DIR / f"{floor_id}.js"
        configure_scenario(str(floor_file))

    state = _create_state(lookahead_depth=None)

    print(f"\n{'='*60}")
    print(f"  VL Experiment: mode={mode}, floor={floor_id}")
    print(f"  Hero: HP={state.hero.hp} ATK={state.hero.atk} DEF={state.hero.def_}")
    print(f"{'='*60}")

    start_time = time.time()
    llm_calls = 0
    parse_errors = 0
    fallbacks = 0
    trace = []
    consecutive_errors = 0

    while not state.goal_reached and not state.failed and state.turn < state.max_turns:
        actions = state.get_actions()
        if not actions:
            state.failed = True
            state.failure_reason = "No actions available"
            break

        # Auto-execute forced single actions
        if len(actions) == 1:
            from mota.game.types import ActionType as AT
            only = actions[0]
            if only.type == AT.FIGHT and not only.can_win:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fight"
                break
            state.apply_action(only)
            continue

        # Auto-collect free items
        auto = _pick_auto_priority_action(actions)
        if auto:
            state.apply_action(auto)
            continue

        # Build input based on mode
        valid_ids = {a.action_id for a in actions}
        image = None
        text_prompt = ""

        if mode in ("image_text", "image_only"):
            image = render_map_image(state, cell_size=38, show_labels=True)

        if mode in ("text_only", "image_text"):
            state_text = state.format_state()
            actions_text = state.format_actions(actions)
            text_prompt = (
                f"{state_text}\n\n{actions_text}\n\n"
                "Choose the best action. Reply: ACTION: <number>"
            )
        elif mode == "image_only":
            # Minimal text: just the action choices with IDs
            action_lines = []
            for a in actions:
                label = a.label() if hasattr(a, "label") else str(a)
                action_lines.append(f"  {a.action_id}. {label}")
            text_prompt = (
                f"The image shows the current game map. Hero: HP={state.hero.hp} ATK={state.hero.atk} DEF={state.hero.def_}\n"
                f"Keys: Y={state.hero.keys.yellow} B={state.hero.keys.blue} R={state.hero.keys.red}\n\n"
                f"Available actions:\n" + "\n".join(action_lines) + "\n\n"
                "Choose the best action. Reply: ACTION: <number>"
            )

        # Call VL model (cloud or local)
        llm_calls += 1
        try:
            if cloud_model:
                response = _call_cloud_vl_model(
                    image, text_prompt, system_prompt=VL_SYSTEM_PROMPT, model_name=cloud_model
                )
            else:
                response = _call_vl_model(image, text_prompt, system_prompt=VL_SYSTEM_PROMPT)
        except Exception as e:
            import traceback
            print(f"  VL model error: {e}")
            traceback.print_exc()
            parse_errors += 1
            fallbacks += 1
            action_id = _heuristic_pick(actions, state)
            if action_id is None:
                state.failed = True
                state.failure_reason = "Stuck"
                break
            chosen = next(a for a in actions if a.action_id == action_id)
            state.apply_action(chosen)
            continue

        action_id = _parse_action_id(response, valid_ids=valid_ids)
        if action_id is None or action_id not in valid_ids:
            parse_errors += 1
            consecutive_errors += 1
            if consecutive_errors >= 3:
                action_id = _heuristic_pick(actions, state)
                fallbacks += 1
                consecutive_errors = 0
                if action_id is None:
                    state.failed = True
                    state.failure_reason = "Stuck"
                    break
            else:
                continue

        chosen = next(a for a in actions if a.action_id == action_id)
        t = state.apply_action(chosen)
        consecutive_errors = 0

        trace.append({
            "turn": t.turn,
            "action": chosen.label() if hasattr(chosen, "label") else str(chosen),
            "hp": t.hero_after["hp"],
            "response_excerpt": response[:200],
        })
        print(f"  T{t.turn}: {chosen.label() if hasattr(chosen, 'label') else str(chosen)} -> HP={t.hero_after['hp']}")

    # Score
    fid = "mt3-walkthrough" if floor_id == "MT3" else floor_id
    result = score_run(state, fixture_id=fid)
    elapsed = time.time() - start_time

    result["tracking"] = {
        "mode": mode,
        "llm_calls": llm_calls,
        "parse_errors": parse_errors,
        "heuristic_fallbacks": fallbacks,
        "elapsed_seconds": round(elapsed, 1),
        "seconds_per_call": round(elapsed / max(1, llm_calls), 2),
    }
    result["trace"] = trace

    print(f"\n  Score: {result['total']:.4f}")
    print(f"  LLM calls: {llm_calls}, Parse errors: {parse_errors}, Fallbacks: {fallbacks}")
    print(f"  Time: {elapsed:.1f}s ({elapsed / max(1, llm_calls):.1f}s/call)")

    return result


def evaluate_vl_with_callback(
    mode: str = "image_only",
    floor_id: str = "MT3",
    cloud_model: str = "qwen3-omni-30b-a3b-instruct",
    system_prompt_override: str | None = None,
    on_event=None,
    should_stop=None,
    max_turns: int = 100,
) -> dict:
    """
    VL evaluation with per-turn SSE-style callbacks for dashboard streaming.

    Emits event dicts via on_event(): {type: "start"|"turn"|"forced"|"result", ...}
    """
    from mota.optimizer.evaluator import (
        _create_state, _heuristic_pick, _parse_action_id, _pick_auto_priority_action,
        configure_scenario, configure_mt3_scenario, _hero_dict, _serialize_rich_map,
    )
    from mota.game.map_renderer import render_map_image
    from mota.benchmark.scorer import score_run
    from mota.game.types import ActionType as AT

    def emit(event):
        if on_event is not None:
            on_event(event)

    if floor_id == "MT3":
        configure_mt3_scenario()
    else:
        floor_file = _FLOORS_DIR / f"{floor_id}.js"
        configure_scenario(str(floor_file))

    state = _create_state(lookahead_depth=None)
    sys_prompt = system_prompt_override or VL_SYSTEM_PROMPT

    emit({
        "type": "start",
        "floor_id": state.floor.floor_id,
        "hero": _hero_dict(state),
        "vl_mode": mode,
        "vl_model": cloud_model,
        "map": _serialize_rich_map(state),
    })

    llm_calls = 0
    parse_errors = 0
    fallbacks = 0
    consecutive_errors = 0

    while not state.goal_reached and not state.failed and state.turn < max_turns:
        if should_stop and should_stop():
            break

        actions = state.get_actions()
        if not actions:
            state.failed = True
            state.failure_reason = "No actions available"
            break

        if len(actions) == 1:
            only = actions[0]
            if only.type == AT.FIGHT and not only.can_win:
                state.failed = True
                state.failure_reason = "Stuck — only unwinnable fight"
                break
            t = state.apply_action(only)
            emit({
                "type": "forced",
                "turn": t.turn,
                "action": only.label(),
                "hero": _hero_dict(state),
                "action_detail": {"type": only.type.value, "x": only.x, "y": only.y, "name": only.name},
            })
            continue

        auto = _pick_auto_priority_action(actions)
        if auto:
            t = state.apply_action(auto)
            emit({
                "type": "forced",
                "turn": t.turn,
                "action": auto.label(),
                "hero": _hero_dict(state),
                "action_detail": {"type": auto.type.value, "x": auto.x, "y": auto.y, "name": auto.name},
            })
            continue

        valid_ids = {a.action_id for a in actions}
        image = None
        text_prompt = ""

        if mode in ("image_text", "image_only"):
            image = render_map_image(state, cell_size=38, show_labels=True)

        if mode in ("text_only", "image_text"):
            state_text = state.format_state()
            actions_text = state.format_actions(actions)
            text_prompt = f"{state_text}\n\n{actions_text}\n\nChoose the best action. Reply: ACTION: <number>"
        else:
            action_lines = [f"  {a.action_id}. {a.label()}" for a in actions]
            text_prompt = (
                f"The image shows the current game map. Hero: HP={state.hero.hp} ATK={state.hero.atk} DEF={state.hero.def_}\n"
                f"Keys: Y={state.hero.keys.yellow} B={state.hero.keys.blue} R={state.hero.keys.red}\n\n"
                f"Available actions:\n" + "\n".join(action_lines) + "\n\nChoose the best action. Reply: ACTION: <number>"
            )

        llm_calls += 1
        action_id = None
        llm_response = ""
        try:
            llm_response = _call_cloud_vl_model(
                image, text_prompt, system_prompt=sys_prompt, model_name=cloud_model
            )
            action_id = _parse_action_id(llm_response, valid_ids=valid_ids)
        except Exception as e:
            emit({"type": "error", "message": str(e)})
            parse_errors += 1

        if action_id is None or action_id not in valid_ids:
            parse_errors += 1
            consecutive_errors += 1
            if consecutive_errors >= 3:
                action_id = _heuristic_pick(actions, state)
                fallbacks += 1
                consecutive_errors = 0
            if action_id is None:
                state.failed = True
                state.failure_reason = "Stuck"
                break
            # retry without emitting a turn if consecutive errors < 3
            if action_id is None or action_id not in valid_ids:
                continue
        else:
            consecutive_errors = 0

        chosen = next(a for a in actions if a.action_id == action_id)
        t = state.apply_action(chosen)

        emit({
            "type": "turn",
            "turn": t.turn,
            "action": chosen.label(),
            "action_id": chosen.action_id,
            "forced": False,
            "hero": _hero_dict(state),
            "action_detail": {"type": chosen.type.value, "x": chosen.x, "y": chosen.y, "name": chosen.name},
            "llm_response_excerpt": llm_response[:300],
            "map": _serialize_rich_map(state),
        })

    fid = "mt3-walkthrough" if floor_id == "MT3" else floor_id
    result = score_run(state, fixture_id=fid)
    result["tracking"] = {
        "mode": mode,
        "cloud_model": cloud_model,
        "llm_calls": llm_calls,
        "parse_errors": parse_errors,
        "heuristic_fallbacks": fallbacks,
    }
    emit({"type": "result", **result})
    return result


def run_vl_comparison(floor_id: str = "MT3", cloud_model: str | None = None) -> dict:
    """Run the full VL comparison experiment: text_only vs image_text vs image_only."""
    from mota.optimizer.evaluator import evaluate_heuristic_only, configure_mt3_scenario

    print("\n" + "=" * 60)
    print("  VL EXPERIMENT: Modality Comparison")
    if cloud_model:
        print(f"  Cloud model: {cloud_model}")
    print("=" * 60)

    results = {}

    # Heuristic baseline
    configure_mt3_scenario()
    r = evaluate_heuristic_only()
    r["mode"] = "heuristic"
    results["heuristic"] = r
    print(f"  Heuristic: {r['total']:.4f}")

    # Run each mode
    for mode in ["text_only", "image_text", "image_only"]:
        try:
            r = evaluate_vl(mode=mode, floor_id=floor_id, cloud_model=cloud_model)
            results[mode] = r
        except Exception as e:
            print(f"  ERROR in {mode}: {e}")
            results[mode] = {"error": str(e), "total": 0}

    # Summary
    print(f"\n{'='*60}")
    print(f"  VL EXPERIMENT SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Mode':<15s} {'Score':>7s} {'Calls':>6s} {'Errors':>7s} {'Time':>8s}")
    print(f"  {'-'*15} {'-'*7} {'-'*6} {'-'*7} {'-'*8}")
    for label, r in results.items():
        if "error" in r and "total" not in r:
            print(f"  {label:<15s} ERROR")
            continue
        t = r.get("tracking", {})
        print(f"  {label:<15s} {r.get('total', 0):7.4f} {t.get('llm_calls', 0):6d} "
              f"{t.get('parse_errors', 0):7d} {t.get('elapsed_seconds', 0):8.1f}s")

    # Save results
    output_dir = _root / "results" / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"VL_comparison_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Results saved: {out_path}")

    return results


def render_test_images(floor_id: str = "MT3"):
    """Render and save test images for manual inspection."""
    from mota.optimizer.evaluator import _create_state, configure_mt3_scenario, configure_scenario
    from mota.game.map_renderer import render_map_image, render_map_with_legend

    if floor_id == "MT3":
        configure_mt3_scenario()
    else:
        floor_file = _FLOORS_DIR / f"{floor_id}.js"
        configure_scenario(str(floor_file))

    state = _create_state(lookahead_depth=None)

    output_dir = _root / "results" / "vl_images"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Basic map
    img = render_map_image(state, cell_size=38, show_labels=False)
    path = output_dir / f"{floor_id}_map.png"
    img.save(path)
    print(f"  Saved: {path} ({img.width}x{img.height})")

    # Map with labels
    img_labels = render_map_image(state, cell_size=38, show_labels=True)
    path = output_dir / f"{floor_id}_map_labeled.png"
    img_labels.save(path)
    print(f"  Saved: {path}")

    # Map with legend
    img_legend = render_map_with_legend(state, cell_size=38)
    path = output_dir / f"{floor_id}_map_legend.png"
    img_legend.save(path)
    print(f"  Saved: {path} ({img_legend.width}x{img_legend.height})")


def main():
    _load_env()

    parser = argparse.ArgumentParser(description="MOTA Vision-Language Experiment")
    parser.add_argument("--mode", choices=["text_only", "image_text", "image_only", "all", "render-only"],
                       default="all", help="Experiment mode")
    parser.add_argument("--floor", default="MT3", help="Floor ID")
    parser.add_argument("--max-turns", type=int, default=100, help="Max turns")
    parser.add_argument("--cloud-model", default=None,
                        help="Use a cloud VL model via SAIA API instead of local GPU "
                             "(e.g. qwen3-omni-30b-a3b-instruct)")
    args = parser.parse_args()

    if args.mode == "render-only":
        render_test_images(args.floor)
        return

    if args.mode == "all":
        run_vl_comparison(args.floor, cloud_model=args.cloud_model)
    else:
        result = evaluate_vl(
            mode=args.mode, floor_id=args.floor, max_turns=args.max_turns,
            cloud_model=args.cloud_model,
        )
        print(f"\nFinal score: {result['total']:.4f}")


if __name__ == "__main__":
    main()
