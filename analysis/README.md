# Analysis scripts

Scripts that produce the tables, figures and paragraphs of Chapter 6 of the thesis. Appendix D (Table D.4)
of the thesis names, for each result, the script and the result files behind it;
[docs/results.md](../docs/results.md) lists the result files per table.

Run them from the repository root. Scripts that read run logs need the logs in `logs/runs/`
(`python scripts/fetch_run_logs.py`); `test_hp_rule.py` also needs an API key.

| Script | Produces |
|---|---|
| `thesis_index.py` | `results/thesis_index.json`, `results/reliability/_thesis_labels.json`, `docs/results.md` |
| `table62_canon.py` | Table 6.2 (main results) |
| `failure_census_simple.py` | the failure census of the simple floor ([development history](../docs/development-history.md)) |
| `override_census.py` | turns on which the executed action differs from the model's choice (Section 6.4.1) |
| `complex_value_trace.py`, `complex_value_summary.py` | exact state values of the complex-floor episodes (Section 6.4.5, Figure 6.2) |
| `special_abilities_census.py` | special abilities per floor (Table 4.1) |
| `mapenum_rescore.py` | the map-only condition (Table 6.4) |
| `gepa_rule_themes.py` | rules written by the prompt optimiser (Table 6.7) |
| `ch6b1_*.py`, `ch6b2_*.py`, `ch6b_*.py` | numbers quoted in Sections 6.5–6.7 (study pairs, planning, hand floors, tower) |
| `tower_calls.py` | model calls of tower runs (planned steps excluded) |
| `test_hp_rule.py`, `replay_tower.py` | the threshold replay of a stored tower decision ([development history](../docs/development-history.md)) |
| `appI_prompt_chars.py`, `appI_runlog_prompt.py`, `render_first_prompt.py` | prompt lengths and the prompts recovered from run logs (Appendix F) |
| `appJ_extract_reasoning.py`, `extract_cot.py`, `ch6b2_hand01_cot.py` | reasoning excerpts (Appendix G) |
| `tune_sweep.py`, `tune_sweep_hand03.py` | start HP against optimum and winning sets (Table 4.5) |
| `build_run_logs_zip.py` | the `run_logs.zip` release asset |
| `repo_inventory.py` | run-log references and sizes |
| `teacher_prompt_gs_dsv4flash_full_it2.txt` | a filled reflection request of the prompt optimiser (Appendix D) |

The scripts were written for the thesis and kept as they ran; some print raw numbers rather than
formatted tables.
