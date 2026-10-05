# Boss-floor run-log census (retrospective)

Every completed LLM episode found in `logs/runs/` and the archive, by floor and task model. Prompts and evaluator versions vary across dates, so these are *existence* counts, not a controlled sample. Episodes before 20260422 used the pre-fix scorer (scores not comparable, kill/no-kill still valid).

| floor | model | episodes | boss killed | died | kill rate [Wilson 95%] | kill scores (HP) | date range |
|---|---|---|---|---|---|---|---|
| complex | qwen3.5-35b-a3b | 11 | 1 | 10 | 1/11 = 0.09 [0.02, 0.38] | 0.8982 (17) | 20260525–20260527 |
| complex | qwen3.5-397b-a17b | 4 | 0 | 3 | 0/4 = 0.00 [0.00, 0.49] | — | 20260526–20260601 |
| simple | meta-llama-3.1-8b-instruct | 1 | 0 | 0 | 0/1 = 0.00 [0.00, 0.79] | — | 20260427–20260427 |
| simple | qwen3-30b-a3b-instruct-2507 | 1 | 0 | 0 | 0/1 = 0.00 [0.00, 0.79] | — | 20260502–20260502 |
| simple | qwen3.5-397b-a17b | 14 | 6 | 0 | 6/14 = 0.43 [0.21, 0.67] | 0.8333 (2), 0.7885 (2), 0.7885 (2), 0.7885 (2), 0.7885 (2), 0.7885 (2) | 20260424–20260601 |

## Boss-kill episodes

| date | floor | model | score | final HP | steps | file |
|---|---|---|---|---|---|---|
| 20260527 | complex | qwen3.5-35b-a3b | 0.8982 | 17 | 52 | `20260527_074006_704228_complex_llm.json` |
| 20260424 | simple | qwen3.5-397b-a17b | 0.8333 | 2 | 36 | `20260424_012713_937471_单层-最简单.txt_llm.json` |
| 20260426 | simple | qwen3.5-397b-a17b | 0.7885 | 2 | 36 | `20260426_222838_090047_simple_llm.json` |
| 20260430 | simple | qwen3.5-397b-a17b | 0.7885 | 2 | 36 | `20260430_200226_519008_simple_llm.json` |
| 20260430 | simple | qwen3.5-397b-a17b | 0.7885 | 2 | 36 | `20260430_212457_728253_simple_llm.json` |
| 20260502 | simple | qwen3.5-397b-a17b | 0.7885 | 2 | 36 | `20260502_001232_350216_simple_llm.json` |
| 20260601 | simple | qwen3.5-397b-a17b | 0.7885 | 2 | 36 | `20260601_033724_008241_simple_llm.json` |
