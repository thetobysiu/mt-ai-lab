# Architecture C — Stage C2v2 Training Results

## Summary
Successfully trained LFM2.5-1.2B-Thinking on BFS-structured CoT data with decision tree analysis format.

## Training Configuration
- **Data**: 34 samples from `bfs_structured_cot_v2.jsonl`
- **Format**: Tree-based CoT (unlocks analysis, dead-end detection, strategic justification)
- **Batch size**: 1 (per-device), Gradient accumulation: 8 (effective batch=8)
- **Sequence length**: 2048 tokens (max observed: 2047)
- **Learning rate**: 1e-4, Warmup: 5 steps
- **Epochs**: 5, Total steps: 25

## Training Performance
- **Time**: 179.8 seconds (3 min)
- **Speed**: ~7.2 s/step (fast with batch=1 and gradient accumulation)
- **Final loss**: 0.4736 (good convergence)
- **LoRA saved**: `training/output/stage_c2v2/stage_c/lora`

## Model Specification
- **Base model**: LiquidAI/LFM2.5-1.2B-Thinking
- **LoRA rank**: 32, Alpha: 64
- **Trainable parameters**: 22.2M / 1.19B (1.86%)
- **Inference device**: NVIDIA GeForce RTX 2080 (8GB VRAM)
- **GPU memory used**: 861 MB

## CoT Quality (V2)
Observation: Rewritten `_build_bfs_cot()` produces meaningful strategic reasoning:
- ✓ Categorizes actions (free items, fights, doors)
- ✓ Renders unlock tree (behind doors, unlocks, via-chain items)
- ✓ Flags dead-end paths
- ✓ Explains optimal choice justification
- ✓ Shows BFS projection (final HP, goal reachable)

Example output format:
```
State: HP=470 ATK=9 DEF=4 | 14 enemies remaining
Evaluating 4 choices (BFS projection after each):
  1. Fight Enemy #204... -> final HP=509, boss UNREACHABLE
     Enemies behind: ⚔ Enemy #204
     Via [Enemy #204@(2,1)]: Red Gem (+1 ATK) [STAT]
  3. Fight Enemy #203... -> final HP=13, boss reachable ** BEST **
     Directly unlocks: yellow door
     Via [yellowDoor@(7,5) -> Enemy #203@(9,5)]: Blue Gem (+1 DEF) [STAT]
Best: Action 3 — fight Enemy #203 (cost=55 HP, final HP=13).
```

## Inference Testing
**Hardware**: RTX 2080 (Turing, compute 7.5, 8GB VRAM)
**Generation settings**: Greedy decoding (do_sample=False), max_new_tokens=20, use_cache=False
**Speed**: ~40 seconds per decision (BFS floor)
- Model loading: ~2 seconds
- Per-decision generation: 40-44 seconds

**Test result (Decision 0/17)**:
```
BFS: Fight Enemy #203 at (6,4) dmg=55
LLM: Fight Enemy #203 at (6,4) dmg=55
✓ EXACT MATCH
```

## Limitations & Notes
1. **RTX 2080 inference speed**: 40s/decision makes full 17-decision evaluation ~11 minutes total. Further optimization (use_cache, batch inference, quantization) needed for practical use.
2. **Small dataset**: 34 samples is minimal. Larger distillation (100+ samples) recommended for production.
3. **Model size**: 1.2B is constrained by 8GB VRAM. Larger models (7B+) unavailable on this hardware.
4. **Compilation crashes**: Unsloth's compiled LFM2 module causes CUDA errors during multi-iteration inference. Workaround: use_cache=False disables optimization.

## Next Steps
- [ ] Evaluate all 3 modes (reactive/multistep-5/oneshot) on faster GPU
- [ ] Profile inference bottlenecks (generation vs forward pass)
- [ ] Consider GGUF quantization for older hardware
- [ ] Expand CoT dataset with more floors for better generalization
- [ ] Compare reactive vs multistep-N planning modes

## Related Files
- Training script: `training/train.py`
- Evaluation script: `training/eval_finetuned.py`
- CoT generation: `training/collect_aligned_cot.py`
- Models: `training/output/stage_c2v2/stage_c/lora/`
