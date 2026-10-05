# Latency census (retrospective, all stored run logs)

Source: 95 LLM run logs. One call = `thinking` -> non-forced `turn`/`parse_error` on the same turn; forced turns (single legal action) are excluded. Reasoning chars = length of the returned thinking text. Wall-clock includes network + queueing on the SAIA endpoint, so this is user-facing latency, not pure decode time.

| model | mode | episodes | calls | s/call median | s/call mean | s/call p90 | reasoning chars mean | calls/episode | min/episode mean |
|---|---|---|---|---|---|---|---|---|---|
| meta-llama-3.1-8b-instruct | instruct | 1 | 16 | 3.6 | 4.4 | 4.9 | 0 | 16.0 | 1.2 |
| qwen3-30b-a3b-instruct-2507 | instruct | 1 | 17 | 3.7 | 4.9 | 3.8 | 349 | 17.0 | 1.4 |
| qwen3.6-35b-a3b | thinking | 22 | 368 | 13.2 | 17.7 | 27.2 | 7293 | 16.7 | 4.9 |
| qwen3.5-397b-a17b | thinking | 40 | 709 | 16.9 | 31.6 | 45.0 | 6547 | 17.7 | 9.3 |
| qwen3.5-35b-a3b | thinking | 11 | 195 | 34.2 | 39.9 | 58.5 | 17509 | 17.7 | 11.8 |
| qwen3.8-27b | thinking | 20 | 373 | 108.3 | 168.9 | 394.1 | 9554 | 18.6 | 52.5 |
