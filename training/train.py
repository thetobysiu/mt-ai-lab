"""
Architecture C — Algorithmic Distillation Fine-Tuning Script

Trains LFM2.5-1.2B-Thinking on MOTA look-ahead graph data using Unsloth QLoRA.
Curriculum SFT: Stage A (synthetic) → Stage B (augmented real) → Stage C (full mix).

Hardware target: RTX 2080 8GB (4-bit quantized, LoRA rank=32).

Usage:
    python training/train.py --data training/data/train.jsonl --output training/output
    python training/train.py --stage A --data training/data/synthetic.jsonl
    python training/train.py --stage C --resume training/output/stage_b
"""
from __future__ import annotations

# Suppress library-internal warnings (torch.jit deprecation, BnB FutureWarning, etc.)
import warnings
warnings.filterwarnings("ignore", message=".*torch.jit.script_method.*")
warnings.filterwarnings("ignore", message=".*_check_is_size.*")
warnings.filterwarnings("ignore", message=".*Redirects are currently not supported.*")
warnings.filterwarnings("ignore", category=FutureWarning, module="bitsandbytes")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.jit")
import os
os.environ["PYTHONWARNINGS"] = "ignore::FutureWarning:bitsandbytes,ignore::DeprecationWarning:torch.jit"
os.environ["PYTHONIOENCODING"] = "utf-8"

# Python 3.14 pickle compatibility patch: _batch_setitems signature changed
import sys
if sys.version_info >= (3, 14):
    try:
        import dill._dill as _dill_mod
        _orig_save_module_dict = _dill_mod.save_module_dict
        def _patched_save_module_dict(pickler, obj):
            """Patched save_module_dict avoiding Python 3.14 _batch_setitems bug."""
            try:
                return _orig_save_module_dict(pickler, obj)
            except TypeError as e:
                if '_batch_setitems' in str(e):
                    # Fall back to basic dict pickling
                    import pickle
                    pickler.save_reduce(dict, (list(obj.items()),), obj=obj)
                else:
                    raise
        import copyreg
        _dill_mod.save_module_dict = _patched_save_module_dict
        # Re-register the patched handler
        _dill_mod.Pickler.dispatch[dict] = _patched_save_module_dict
    except Exception:
        pass

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataset preparation
# ---------------------------------------------------------------------------

def load_jsonl_dataset(path: str, max_samples: int | None = None) -> list[dict]:
    """Load JSONL training file as list of {input, output} dicts."""
    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sample = json.loads(line)
            if "input" not in sample or "output" not in sample:
                continue
            samples.append(sample)
            if max_samples and len(samples) >= max_samples:
                break
    log.info("Loaded %d samples from %s", len(samples), path)
    return samples


def build_conversations(samples: list[dict], system_prompt: str) -> list[dict]:
    """Convert {input, output} pairs to ChatML conversation format."""
    conversations = []
    for s in samples:
        conv = {
            "conversations": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": s["input"]},
                {"role": "assistant", "content": s["output"]},
            ]
        }
        conversations.append(conv)
    return conversations


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


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(args: argparse.Namespace) -> None:
    """Main training function."""
    try:
        from unsloth import FastModel
    except ImportError:
        try:
            from unsloth import FastLanguageModel as FastModel
        except ImportError:
            print("ERROR: unsloth not installed. Install with: pip install unsloth")
            sys.exit(1)

    import torch
    from trl import SFTTrainer, SFTConfig
    from unsloth.chat_templates import train_on_responses_only, get_chat_template

    # ── Model ──────────────────────────────────────────────────────
    model_name = args.model or "LiquidAI/LFM2.5-1.2B-Thinking"
    is_gemma4 = "gemma-4" in model_name.lower() or "gemma4" in model_name.lower()
    log.info("Loading model: %s (gemma4=%s)", model_name, is_gemma4)

    # Resolve model name to Unsloth Hub path.
    # Gemma-4 E2B/E4B: use pre-quantized "unsloth/gemma-4-E2B-it-unsloth-bnb-4bit"
    # to avoid OOM from on-device quantization of the full 10.2GB BF16 model.
    # (Unsloth officially says "E2B LoRA works on 8-10GB VRAM")
    if is_gemma4:
        # If user already passed the correct pre-quantized model, use it directly
        if "unsloth-bnb-4bit" in model_name or "GGUF" in model_name:
            resolved_name = model_name
        else:
            # Normalise to unsloth pre-quantized hub path
            base = model_name.split("/")[-1]
            if not base.startswith("gemma-4-"):
                base = base.replace("gemma4-", "gemma-4-").replace("_", "-")
            resolved_name = f"unsloth/{base}-unsloth-bnb-4bit"
        log.info("Resolved Gemma-4 model: %s", resolved_name)

        model, tokenizer = FastModel.from_pretrained(
            model_name=resolved_name,
            max_seq_length=args.max_seq_length,
            load_in_4bit=True,
            full_finetuning=False,
            dtype=None,
        )
        # Apply Gemma-4 chat template (uses <|turn>role\n...<turn|> format)
        tokenizer = get_chat_template(tokenizer, chat_template="gemma-4")
        log.info("Applied Gemma-4 chat template")
    else:
        # LFM / other models: try Unsloth hub path first, then original
        unsloth_name = f"unsloth/{model_name.split('/')[-1]}"
        try:
            model, tokenizer = FastModel.from_pretrained(
                model_name=unsloth_name,
                max_seq_length=args.max_seq_length,
                load_in_4bit=True,
                full_finetuning=False,
                dtype=torch.float16,
            )
            log.info("Loaded via Unsloth path: %s", unsloth_name)
        except (RuntimeError, OSError):
            log.info("Unsloth path failed, using original: %s", model_name)
            model, tokenizer = FastModel.from_pretrained(
                model_name=model_name,
                max_seq_length=args.max_seq_length,
                load_in_4bit=True,
                full_finetuning=False,
                dtype=torch.float16,
            )

    # ── LoRA adapters ──────────────────────────────────────────────
    if is_gemma4:
        # Gemma-4: use FastModel's new API which auto-selects correct modules
        model = FastModel.get_peft_model(
            model,
            finetune_vision_layers=False,
            finetune_language_layers=True,
            finetune_attention_modules=True,
            finetune_mlp_modules=True,
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=0,
            bias="none",
            random_state=42,
            use_rslora=False,
        )
    else:
        # LFM2.5 uses custom projection names
        lora_targets = [
            "q_proj", "k_proj", "v_proj", "out_proj", "in_proj",
            "w1", "w2", "w3",
        ]
        model = FastModel.get_peft_model(
            model,
            r=args.lora_r,
            target_modules=lora_targets,
            lora_alpha=args.lora_alpha,
            lora_dropout=0,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=42,
            use_rslora=False,
        )

    # ── Resume from previous stage ────────────────────────────────
    if args.resume:
        log.info("Resuming from LoRA checkpoint: %s", args.resume)
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.resume, is_trainable=True)

    # ── Data ───────────────────────────────────────────────────────
    raw_samples = load_jsonl_dataset(args.data, args.max_samples)
    conversations = build_conversations(raw_samples, SYSTEM_PROMPT)

    # Format as text using chat template (bypass datasets.map for Python 3.14 compat)
    texts = []
    bos = tokenizer.bos_token or ""
    for conv in conversations:
        text = tokenizer.apply_chat_template(
            conv["conversations"],
            tokenize=False,
            add_generation_prompt=False,
        )
        if text.startswith(bos):
            text = text[len(bos):]
        texts.append(text)

    from datasets import Dataset
    import datasets
    datasets.disable_caching()  # Avoid pickle serialization (Python 3.14 compat)
    dataset = Dataset.from_dict({"text": texts})

    # ── Trainer ────────────────────────────────────────────────────
    output_dir = Path(args.output) / f"stage_{args.stage.lower()}"
    output_dir.mkdir(parents=True, exist_ok=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        eval_dataset=None,
        args=SFTConfig(
            dataset_text_field="text",
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            warmup_steps=args.warmup_steps,
            num_train_epochs=args.epochs,
            max_steps=args.max_steps or -1,
            learning_rate=args.lr,
            logging_steps=10,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            seed=42,
            output_dir=str(output_dir),
            save_strategy="epoch",
            report_to="none",
            max_seq_length=args.max_seq_length,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
        ),
    )

    # Only train on assistant responses (mask user/system tokens)
    # Gemma-4 uses <|turn>model / <|turn>user delimiters (NOT Gemma-3's <start_of_turn>)
    # LFM / Qwen uses <|im_start|>assistant / <|im_start|>user markers
    if is_gemma4:
        trainer = train_on_responses_only(
            trainer,
            instruction_part="<|turn>user\n",
            response_part="<|turn>model\n",
        )
    else:
        trainer = train_on_responses_only(
            trainer,
            instruction_part="<|im_start|>user\n",
            response_part="<|im_start|>assistant\n",
        )

    # ── Train ──────────────────────────────────────────────────────
    gpu_stats = torch.cuda.get_device_properties(0)
    max_memory = round(gpu_stats.total_memory / 1024 / 1024 / 1024, 3)
    log.info("GPU: %s, VRAM: %.1f GB", gpu_stats.name, max_memory)

    stats = trainer.train()
    log.info(
        "Training complete: %.1f seconds, loss=%.4f",
        stats.metrics["train_runtime"],
        stats.metrics.get("train_loss", -1),
    )

    # ── Save ───────────────────────────────────────────────────────
    lora_dir = output_dir / "lora"
    model.save_pretrained(str(lora_dir))
    tokenizer.save_pretrained(str(lora_dir))
    log.info("LoRA adapters saved to %s", lora_dir)

    # Merge + export if requested
    if args.export_merged:
        merged_dir = output_dir / "merged_16bit"
        model.save_pretrained_merged(
            str(merged_dir), tokenizer, save_method="merged_16bit"
        )
        log.info("Merged 16-bit model saved to %s", merged_dir)

    if args.export_gguf:
        gguf_dir = output_dir / "gguf"
        model.save_pretrained_gguf(
            str(gguf_dir), tokenizer, quantization_method="q4_k_m"
        )
        log.info("GGUF model saved to %s", gguf_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Architecture C: MOTA Algorithmic Distillation Fine-Tuning"
    )
    parser.add_argument("--data", required=True, help="Path to JSONL training data")
    parser.add_argument("--output", default="training/output", help="Output directory")
    parser.add_argument(
        "--stage", default="A", choices=["A", "B", "C"],
        help="Curriculum stage: A=synthetic, B=augmented, C=full"
    )
    parser.add_argument("--resume", default=None, help="Path to LoRA checkpoint to resume from")
    parser.add_argument("--model", default=None, help="HuggingFace model ID (default: LFM2.5-1.2B-Thinking, or gemma-4-26b for Gemma)")

    # Training hyperparameters
    parser.add_argument("--epochs", type=int, default=2, help="Number of epochs")
    parser.add_argument("--max-steps", type=int, default=None, help="Max steps (overrides epochs)")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size")
    parser.add_argument("--grad-accum", type=int, default=4, help="Gradient accumulation steps")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--warmup-steps", type=int, default=100, help="Warmup steps")
    parser.add_argument("--max-seq-length", type=int, default=2048, help="Max sequence length")

    # LoRA
    parser.add_argument("--lora-r", type=int, default=32, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=64, help="LoRA alpha")

    # Data
    parser.add_argument("--max-samples", type=int, default=None, help="Max training samples")

    # Export
    parser.add_argument("--export-merged", action="store_true", help="Export merged 16-bit model")
    parser.add_argument("--export-gguf", action="store_true", help="Export GGUF (q4_k_m)")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    train(args)


if __name__ == "__main__":
    main()
