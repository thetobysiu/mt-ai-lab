"""
Inference with fine-tuned Architecture C model.

Loads the LoRA-adapted LFM2.5 model and generates look-ahead graph + macro-action
sequences from game state inputs.

Usage:
    python training/inference.py --model training/output/stage_c/lora \
                                 --input "Hero: HP=500 ATK=10 DEF=10..."
    python training/inference.py --model training/output/stage_c/gguf/model-unsloth-Q4_K_M.gguf \
                                 --input-file test_input.txt
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

log = logging.getLogger(__name__)


def inference_unsloth(model_path: str, inputs: list[str], args: argparse.Namespace):
    """Run inference using Unsloth (LoRA or merged model)."""
    from unsloth import FastLanguageModel
    import torch

    # Try custom model class if available, fall back to auto-detection
    load_kwargs = dict(
        model_name=model_path,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )
    try:
        from transformers import Lfm2ForCausalLM
        load_kwargs["auto_model"] = Lfm2ForCausalLM
    except ImportError:
        log.warning("Lfm2ForCausalLM not found in transformers; using auto-detection")

    log.info("Loading model from %s", model_path)
    model, tokenizer = FastLanguageModel.from_pretrained(**load_kwargs)
    FastLanguageModel.for_inference(model)

    system_prompt = (
        "You are a MOTA (Magic Tower) game solver. Given the current game state "
        "and a list of available actions as multiple-choice options, choose the "
        "best next action. Output a JSON object with answer, reason, and macro_action."
    )

    for i, user_input in enumerate(inputs):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        input_ids = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            tokenize=True,
            return_dict=True,
        ).to(model.device)

        t0 = time.time()
        output = model.generate(
            **input_ids,
            max_new_tokens=args.max_new_tokens,
            temperature=0.05,
            top_k=50,
            repetition_penalty=1.05,
            do_sample=True,
        )
        elapsed = time.time() - t0

        # Decode only the generated part
        generated = output[0][input_ids["input_ids"].shape[1]:]
        text = tokenizer.decode(generated, skip_special_tokens=True)

        print(f"\n{'='*60}")
        print(f"Input {i+1} ({elapsed:.2f}s, {len(generated)} tokens):")
        print(f"{'='*60}")
        print(text)

        # Try to parse as JSON
        try:
            parsed = json.loads(text)
            print(f"\nParsed JSON keys: {list(parsed.keys())}")
            if "macro_action" in parsed:
                print(f"Macro actions: {parsed['macro_action']}")
        except json.JSONDecodeError:
            # Try to extract JSON from the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start:end])
                    print(f"\nExtracted JSON keys: {list(parsed.keys())}")
                except json.JSONDecodeError:
                    print("\nWARNING: Could not parse output as JSON")


def inference_gguf(model_path: str, inputs: list[str], args: argparse.Namespace):
    """Run inference using llama-cpp-python (GGUF model)."""
    try:
        from llama_cpp import Llama
    except ImportError:
        print("ERROR: llama-cpp-python not installed. Install with:")
        print("  pip install llama-cpp-python")
        sys.exit(1)

    log.info("Loading GGUF model from %s", model_path)
    llm = Llama(
        model_path=model_path,
        n_ctx=args.max_seq_length,
        n_gpu_layers=-1,  # offload all to GPU
    )

    system_prompt = (
        "You are a MOTA (Magic Tower) game solver. Given the current game state "
        "and a list of available actions as multiple-choice options, choose the "
        "best next action. Output a JSON object with answer, reason, and macro_action."
    )

    for i, user_input in enumerate(inputs):
        t0 = time.time()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            max_tokens=args.max_new_tokens,
            temperature=0.05,
            top_k=50,
            repeat_penalty=1.05,
        )
        elapsed = time.time() - t0
        text = response["choices"][0]["message"]["content"]

        print(f"\n{'='*60}")
        print(f"Input {i+1} ({elapsed:.2f}s):")
        print(f"{'='*60}")
        print(text)


def main():
    parser = argparse.ArgumentParser(description="Architecture C Inference")
    parser.add_argument("--model", required=True, help="Path to LoRA dir or GGUF file")
    parser.add_argument("--input", default=None, help="Direct text input")
    parser.add_argument("--input-file", default=None, help="File with input text")
    parser.add_argument("--max-new-tokens", type=int, default=600)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # Collect inputs
    inputs = []
    if args.input:
        inputs.append(args.input)
    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as f:
            inputs.append(f.read().strip())
    if not inputs:
        print("ERROR: Provide --input or --input-file")
        sys.exit(1)

    # Dispatch based on model format
    if args.model.endswith(".gguf"):
        inference_gguf(args.model, inputs, args)
    else:
        inference_unsloth(args.model, inputs, args)


if __name__ == "__main__":
    main()
