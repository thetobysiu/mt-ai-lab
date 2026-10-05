# Fine-tuning pilot

Scripts and datasets of the small-model pilot reported in Appendix E of the thesis: a 1.2-billion-parameter
model (LFM2.5-1.2B-Thinking) fine-tuned with QLoRA on decisions of the engine and the solver.
The model weights, checkpoints and adapters are **not** included (about 11 GB).

| File | Role |
|---|---|
| `generate_bfs_ground_truth.py` | solver-optimal decisions as training examples |
| `generate_cot_data.py`, `collect_aligned_cot.py`, `align_prompt_to_bfs.py` | reasoning-annotated examples |
| `train.py`, `run_train.py` | QLoRA training (stages A, B, C) |
| `eval_finetuned.py`, `inference.py`, `Modelfile` | evaluation and local inference |
| `vl_experiment.py` | the vision-language pilot |
| `data/` | the generated datasets (JSONL) |
| `eval_results*.json`, `RESULTS_C2V2.md` | stored evaluation results |

The scripts are kept as they ran. They need extra packages (PyTorch, transformers, peft, bitsandbytes)
that are not part of the project dependencies, and some refer to the original solver's test maps by
their Chinese file names; the copies in `data/floors/` are `simple.txt` and `complex.txt`.
