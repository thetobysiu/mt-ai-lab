"""The model's turns per episode of single-floor result files (Sections 6.3 and 6.4 of the thesis).

    python analysis/simple_turns.py results/reliability/simple_qwen3.5-397b_canon.json [more result files]

For every episode: the run log, the final HP, the number of overrides, and the first nine turns the model
chose (assisted turns are skipped). Comparing these with the optimal route of
`scripts/floor_lab.py analyse data/floors/simple.txt --decisions` gives the first decision, the winning
trajectory and each departure with its state value. Run logs are read from logs/runs/ (fetch them with
scripts/fetch_run_logs.py).
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")


def find_log(name: str) -> str | None:
    hits = glob.glob(os.path.join("logs", "runs", "**", os.path.basename(name)), recursive=True)
    return hits[0] if hits else None


def model_turns(log: str) -> tuple[list[tuple[str, str, str | None]], int]:
    turns = json.load(open(log, encoding="utf-8")).get("turns") or []
    chosen = [(t.get("turn"), t.get("action"), t.get("corrected_from")) for t in turns
              if t.get("type") == "turn" and t.get("action") and str(t.get("forced")) != "True"]
    overrides = sum(1 for t in turns if t.get("type") == "override" or t.get("corrected_from"))
    return chosen, overrides


def main() -> None:
    for result in sys.argv[1:]:
        print("==", result)
        data = json.load(open(result, encoding="utf-8"))
        for ep in data.get("runs") or data.get("episodes") or []:
            name = ep.get("log_file") or ep.get("log") or ep.get("run_log")
            log = find_log(name) if name else None
            if not log:
                print("  run log not found:", name)
                continue
            chosen, overrides = model_turns(log)
            short = "; ".join(f"T{t}:{a.split(' dmg')[0]}" + (f" [override of {c}]" if c else "") for t, a, c in chosen[:9])
            print(f"  {os.path.basename(log)} hp={ep.get('final_hp', ep.get('hp'))} overrides={overrides} | {short}")


if __name__ == "__main__":
    main()
