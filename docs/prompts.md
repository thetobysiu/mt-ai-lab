# Prompts

All prompts are plain text files in `seed_prompts/`. The system prompt is sent once per call, followed
by the static floor map (appended to the system prompt) and the observation of the current decision.

## The prompts of the main results

| File | Used for | Contents |
|---|---|---|
| `floor_basic.txt` | every single floor (default) | the combat formula, how to read the annotations, and five strategy rules: stat items before the fights they make cheaper, cheapest progress first, never pay HP for a fight that unlocks nothing needed, never fight a monster costing more than 40 % of current HP unless nothing else progresses, keys are scarce |
| `tower_basic.txt` | every tower run (default, design 7) | the same rules for the tower (HP rule at 60 %), plus scouting the next floor first and the shop rules (never buy HP or level-ups; DEF before ATK, ATK high enough for the strongest monster needed) |
| `complex_bfs_strategy_survival.txt` | complex floor, *solver-route prompt* | the route found by the published solver (allowed and forbidden fights, door order, phases) and a rule never to take a lethal fight; a compiled-knowledge condition, not a default |
| `complex_exact68_sequence.txt` | complex floor, *exact-route prompt* | the 21 decisions of the exact optimal route (68 HP) with the expected HP after each |
| `core_rules.txt` | prompt optimisation | the *rules-only prompt*: combat formula and answer format, no strategy |
| `floor_basic_hp60.txt` | ablation | `floor_basic.txt` with the HP rule at 60 % |

Prompts may contain the combat calculation, how to read the engine's annotations and general strategy
rules; they contain no floor-specific choices (coordinates, allow-lists, door orders), except for the
two labelled compiled-knowledge prompts.

## Earlier prompts

Kept for provenance (the thesis lists the prompts behind its results in Appendix F; earlier prompts are described in
[development-history.md](development-history.md)):

- tower designs 1, 3, 4, 5 and 6: `tower_basic_v1_stairs.txt`, `tower_basic_v3_statneeds.txt`,
  `tower_basic_v4_wayup.txt`, `tower_basic_v5_fidelity.txt`, `tower_basic_design6.txt`;
- development prompts: `target_boss_seed.txt` (the earlier hand-written prompt), `bare.txt`,
  `minimal.txt`, `format_aware_bare.txt`, `mt3_bare.txt`, `imperative_lookahead.txt`, `complex_aware.txt`,
  `complex_bfs_strategy.txt`, `complex_bfs_strategy_mechanical.txt`, `manual_aligned.txt`,
  `e3_best_prompt.txt`, `simple_basic_strict.txt`, `tower_seed_v1_walkthrough.txt`;
- the bare- and map-only conditions: `self_lookahead.txt`, `blocker_lookahead.txt`;
- `gepa_study/`: the evolved prompts of the prompt-optimisation study.

## Choosing a prompt

`mota/optimizer/seed_prompt.py::get_seed_for_floor` picks `floor_basic.txt` for single floors and
`tower_basic.txt` for tower ranges. Override it with `--prompt-file <name or path>` on the command line,
or with the prompt editor of the Play page (versions are stored in `logs/prompts/versions.json`).

The exact observation text at a reference decision is pinned by `mota/tests/test_prompt_golden.py`; a
deliberate change to the observation must be re-baselined with `scripts/rebaseline_golden.py`.
