# Prompt optimisation

Two reflective loops evolve the system prompt through the same engine, assists and measures as every
other run (thesis Section 5.7). A *teacher* model reads the traces of the current prompt's episodes and
writes a revised prompt; a *validator* rejects candidates with floor-specific content.

## The loops

**(1+1) loop** (`--loop oneplusone`, default). One prompt at a time:

1. evaluate the current prompt, one episode per training floor at temperature 0 (fitness = mean goal score);
2. build the reflection request: task scope, a description of the observation, the rules a prompt must
   follow, the current prompt, one trace per episode (decisions, attributes, overrides, end of the
   reasoning, outcome) and up to two earlier rewrites that scored worse;
3. the teacher writes a diagnosis and a complete revised prompt;
4. the validator rejects coordinates, monster names, routes, allow-lists and numbers of 100 or more
   (one retry with the reasons);
5. the candidate replaces the best prompt if its fitness is at least as high.

**Pareto loop** (`--loop pareto`). The same teacher, validator and traces, with GEPA's selection:
every candidate joins the population, the parent is drawn from the candidates that are best on at least
one training floor, and at the last slot the teacher merges the two best frontier candidates.

`--no-validate` (with `run_constrained_gepa.py`) lets the teacher write positions and orders for a
single floor; the result is floor-specific knowledge (the thesis calls it the evolved-route prompt).

## Running the study

```bash
# optimise from the rules-only prompt on simple, gen01, gen02; evaluate rules-only, evolved and
# single-floor prompts on the training floors and the 13 held-out floors gen03-gen15
python scripts/run_gepa_study.py --preset deepseek-v4-flash --obs full --label my_study

# bare observation, Pareto loop, reasoning task model, teacher sees the options at each decision
python scripts/run_gepa_study.py --preset deepseek-v4-flash-think --obs bare --loop pareto --rich-trace \
    --reflection-model deepseek-v4-flash-0731 --repeat 3 --label my_pareto

# evaluate prompts only (no optimisation)
python scripts/run_gepa_study.py --preset qwen3.5-397b --obs bare --no-gepa --prompts core basic \
    --train simple --test "" --repeat 3 --label my_refs
```

| Option | Meaning |
|---|---|
| `--obs full / bare` | final configuration or bare observation |
| `--train`, `--test` | comma-separated floors (default `simple,gen01,gen02` and `gen03`…`gen15`) |
| `--iterations` | evaluations of the loop (default 6) |
| `--repeat` | episodes per prompt and floor in the evaluation |
| `--prompts` | arms to evaluate: `core` (rules-only), `gepa` (evolved), `basic` (single-floor prompt), `seed` |
| `--seed-file` | seed prompt in `seed_prompts/` (default `core_rules.txt`) |
| `--gepa-from` | reuse the best prompt of an earlier run |
| `--reflection-model`, `--rich-trace` | teacher model; show the options offered at each decision |

Outputs: `results/gepa_study/<label>.json` (every episode with its run log), the loop in
`results/gepa/gepa_result_<label>.json` and the best prompt in `seed_prompts/gepa_study/<label>_best.txt`.
The GEPA page of the platform shows each iteration with the prompt diff, the teacher's diagnosis and the
validator's verdict.

A single loop without the study evaluation:

```bash
python scripts/run_constrained_gepa.py --floor simple --preset qwen3.6-35b --label my_loop --iterations 6
python scripts/run_constrained_gepa.py --tower MT0 MT8 --preset deepseek-v4-flash-think --label my_tower_loop
```

## The GEPA library

`python -m mota.optimizer.run_gepa` runs `gepa.optimize_anything` (Agrawal et al., 2025) on a single
task instance; it was used in the development phase (thesis Appendix D) and needs the `reflection`
extra (`pip install -e ".[reflection]"`).
