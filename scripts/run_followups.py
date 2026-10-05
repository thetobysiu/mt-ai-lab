"""
Queued LLM experiments (single API key => strictly sequential).

Waits until no other run_reliability.py / run_model_matrix.py process and no API job in the
dashboard registry is alive, then runs the selected experiments one after the other. Every
experiment registers a job manifest first, so the whole queue is visible (and pausable) in the
dashboard's Live page while it runs.

  Essential set (the three claims the thesis needs to demonstrate):
    S1  simple floor, qwen3.6-35b, engine NOSHOP seed, overrides on, N=5   -> boss kill rate
    C1  complex floor, qwen3.6-35b, BFS+survival prompt, overrides off, N=5 -> boss kill rate
    T1  tower MT0->MT23w, qwen3.6-35b, tower_seed.txt, N=1                  -> highest floor reached
    S2  simple floor with a second model (qwen3.5-397b), N=5                -> model comparison

  Earlier follow-ups: A1 (mechanical framing), A2 (overrides-off ablation), A3 (survival gate).

    python scripts/run_followups.py --only S1 C1 T1     # the essential set, in order
    python scripts/run_followups.py --only T1
    python scripts/run_followups.py --dry-run --only S1 C1 T1
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from mota.dashboard import jobs as J  # noqa: E402

EXPERIMENTS = {
    # --- essential re-run set (2026-09-23, post log reset) --------------------------------------
    # Each writes a fresh results/reliability/<label>.json (no --append): N=5 on one clean stack.
    # S1  "the LLM beats the simple boss floor, reproducibly" — engine NOSHOP seed, overrides on
    #     (the configuration that produced every stored simple kill). Reference: 5/10 in the matrix.
    "S1": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.6-35b_reactive"],
    # C1  "the LLM beats the complex boss floor, reproducibly" — BFS-compiled prompt + survival gate,
    #     overrides OFF (mandatory for this prompt). Reference: A3 = 4/5.
    "C1": ["--floor", "complex", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
           "--disable-overrides", "--prompt-file", "complex_bfs_strategy_survival.txt",
           "--label", "complex_qwen3.6-35b_reactive_raw_survival"],
    # S2  second model on the simple floor (only if there is API budget left after S1/C1/T1).
    "S2": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_reactive"],
    # --- earlier follow-ups (kept for reproducibility) ------------------------------------------
    "A1": ["--floor", "complex", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
           "--disable-overrides", "--prompt-file", "complex_bfs_strategy_mechanical.txt",
           "--label", "complex_qwen3.6-35b_reactive_raw_mechanical", "--append"],
    "A2": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--disable-overrides", "--label", "simple_qwen3.5-397b_reactive_raw", "--append"],
    # A3: suicide hypothesis. 26/45 complex episodes attack a [LETHAL] boss because the BFS
    # prompt's allowlist rule dominates the survival check (35B: 10/10 identical). Same prompt +
    # an explicit survival gate (rule 0). Baseline 0/10.
    "A3": ["--floor", "complex", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
           "--disable-overrides", "--prompt-file", "complex_bfs_strategy_survival.txt",
           "--label", "complex_qwen3.6-35b_reactive_raw_survival", "--append"],
    # T1: full-tower LLM run with the basic tower prompt (engine default). 8K thinking cap.
    "T1": ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "qwen3.5-397b", "--repeats", "1",
           "--max-turns", "1500", "--lookahead", "2",
           "--label", "tower_qwen3.5-397b_basic"],
    # T0: the previous tower prompt (walkthrough-heavy) for comparison only.
    "T0": ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "qwen3.6-35b", "--repeats", "1",
           "--max-turns", "1500", "--prompt-file", "tower_seed_v1_walkthrough.txt",
           "--label", "tower_qwen3.6-35b_tower_seed"],
    # B1: the thesis-critical check — simple floor with the BASIC prompt (no hard-coded choices).
    "B1": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_basic"],
    # B3: same, after the 2026-09-24 refinements (prompt: tree-is-the-map + lowest effCost;
    # engine: '-> stat gems behind it save X HP' annotation, auto-fight 0-HP monsters). B1 = 1/5.
    "B3": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_basic_v2"],
    "B2": ["--floor", "complex", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--disable-overrides", "--label", "complex_qwen3.5-397b_basic_raw"],
    # --- 2026-09-24 root cause: _safety_correct silently replaced the LLM's action (94 unlogged
    #     overrides in 68 simple episodes; B3 0/5 = LLM chose Black Slime, engine executed the Bat).
    #     Overrides are now logged and mechanical-only (dead-end / unwinnable / lethal);
    #     MOTA_STRATEGIC_OVERRIDES=1 restores the historical stack. See SIMPLE_FLOOR_PLAN.md §5.
    # R0: control — historical stack (legacy NOSHOP seed + strategic overrides). Expect ~50%.
    "R0": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_legacy_strategic_control"],
    # B4: basic prompt, engine assists on, override mechanical-only (no strategic sabotage).
    "B4": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_basic_mechanical_override"],
    # B5: B4 + C0 alternative-route annotation ("[ALTERNATIVE ROUTE — everything this opens is also
    #     opened by X]"; B4 run 1 fought the redundant Red Slime (5,3) at turn 2, 56 HP > 11 HP slack).
    "B5": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_basic_mech_altroute"],
    # B6: B5 + C1 order-aware stat routes. R0 2/5 vs B4/B5 0/5 showed the LLM loses by ~12 HP on one
    #     ordering call; the stat hint advertised a 198-HP route as "save 155" while the 16-HP route
    #     said "save 94". Hints are now net of the route cost, and premature fights say how much they
    #     waste. Decisive turn 9: +78 (cheap) vs -43 (expensive) vs "wastes 12 HP".
    "B6": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_basic_order_aware"],
    # B7: confirmation of B6 (5/5, every kill HP=2, 0 overrides) to N=10.
    "B7": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_basic_order_aware", "--append"],
    # C2: does C1 disturb the complex floor? The door branch prints the stat hint even with
    #     overrides disabled, so the BFS+survival prompt's input changed. Baseline A3/C1 = 4/5.
    "C2": ["--floor", "complex", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
           "--disable-overrides", "--prompt-file", "complex_bfs_strategy_survival.txt",
           "--label", "complex_qwen3.6-35b_survival_order_aware"],
    # ---------------------------------------------------------------------------------------
    # OVERNIGHT 2026-09-24/25 (SIMPLE_FLOOR_PLAN.md §9). C2 = 1/5 with 4 deaths: the door hint
    # made 5/5 runs take blue door (12,2) at T37 (the BFS-optimal line, previously 1/5), and on
    # that line the T47 fight list had NO unlock trees (MOTA_DISABLE_OVERRIDES also suppressed
    # fight annotations) -> the 35B model could not see that Black Slime (2,9) guards the DEF
    # gem + potion, reasoned from coordinates ("I can just move to (1,9)"), fought the adjacent
    # OPTIONAL Big Bat (124 HP) and died. Control (overrides) and information (annotations) are
    # now separate knobs (MOTA_SUPPRESS_HINTS).
    # --- Lane A: complex + model transfer ---------------------------------------------------
    # CB1  THESIS-CRITICAL: complex with the basic prompt (two-prompt rule), engine assists,
    #      mechanical-only override, full annotations. BFS optimum HP 22. Never run before.
    "CB1": ["--floor", "complex", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
            "--label", "complex_qwen3.5-397b_basic_order_aware"],
    # C3   complex, survival prompt, overrides OFF but annotations ON -> isolates the information
    #      deficit that killed C2 (same trajectory to T47, now with fight trees visible).
    "C3": ["--floor", "complex", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
           "--disable-overrides", "--prompt-file", "complex_bfs_strategy_survival.txt",
           "--label", "complex_qwen3.6-35b_survival_hints_on"],
    # B8/B9  RQ2 model transfer: the B6 stack (10/10 on 397B) on the two faster models.
    "B8": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.6-35b_basic_order_aware"],
    "B9": ["--floor", "simple", "--preset", "glm-5.3-flash", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_glm-5.3-flash_basic_order_aware"],
    # --- Lane B: RQ3 planning granularity + lookahead depth (simple, 397B, B6 stack) ---------
    # G1/G2  the title's "reactive -> holistic" axis, on the stack that is 10/10 reactive.
    "G1": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--mode", "oneshot", "--label", "simple_qwen3.5-397b_basic_oneshot"],
    "G2": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--mode", "multistep-5", "--label", "simple_qwen3.5-397b_basic_multistep5"],
    # L1/L2  lookahead depth 1 and 2 (depth 3 = B6). Depth 1 has no via-chains.
    "L1": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "1",
           "--label", "simple_qwen3.5-397b_basic_order_aware_la1"],
    "L2": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "2",
           "--label", "simple_qwen3.5-397b_basic_order_aware_la2"],
    # --- Lane C: tower + anchors ------------------------------------------------------------
    # T2   tower with mechanical-only overrides (T1 had 18 silent overrides incl. shop buys and
    #      the ">20% fight -> stairs" rule that produced 52 floor changes).
    "T2": ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "qwen3.5-397b", "--repeats", "1",
           "--max-turns", "1500", "--lookahead", "2", "--label", "tower_qwen3.5-397b_basic_mechanical"],
    # M3/M4  MT3 / MT4 anchors on the basic stack (cheap; Ch8 needs N=5 numbers, only N=1 exist).
    "M3": ["--floor", "MT3", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "MT3_qwen3.5-397b_basic_order_aware"],
    "M4": ["--floor", "MT4", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "MT4_qwen3.5-397b_basic_order_aware"],
    # ---------------------------------------------------------------------------------------
    # ROUND 2 (2026-09-25, after engine fixes D1-D4 — SIMPLE_FLOOR_PLAN.md §11.7/§12). Same
    # formatter for every cell below; predictions pre-registered in Ch8 §8.20.8.
    # --- Lane A: simple regression guard + model transfer -----------------------------------
    # B10  regression guard: the 10/10 stack under D1-D4 must stay 5/5.
    "B10": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
            "--label", "simple_qwen3.5-397b_basic_d1d4"],
    # B11  qwen3.6-35b: D2 (both gems behind door (7,5)) + D3 (effCost w/o potions) target its T22.
    "B11": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
            "--label", "simple_qwen3.6-35b_basic_d1d4"],
    # B12  qwen3.8-27b (dense; the matrix had it at 5/10 with the override) on the D1-D4 stack.
    "B12": ["--floor", "simple", "--preset", "qwen3.8-27b", "--repeats", "3", "--lookahead", "3",
            "--label", "simple_qwen3.8-27b_basic_d1d4"],
    # --- Lane B: complex --------------------------------------------------------------------
    # CB2  complex, basic prompt: D3/D4 remove the two lines every CB1 death cited.
    "CB2": ["--floor", "complex", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
            "--label", "complex_qwen3.5-397b_basic_d1d4"],
    # CS1  complex, survival prompt, 397B, overrides off, hints on (35B C3 = 4/5; 397B never run
    #      with annotations on — its 4/10 in the matrix was hints-off).
    "CS1": ["--floor", "complex", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
            "--disable-overrides", "--prompt-file", "complex_bfs_strategy_survival.txt",
            "--label", "complex_qwen3.5-397b_survival_hints_on"],
    # CB3  complex, basic prompt, glm-5.3-flash (5/5 on simple).
    "CB3": ["--floor", "complex", "--preset", "glm-5.3-flash", "--repeats", "3", "--lookahead", "3",
            "--label", "complex_glm-5.3-flash_basic_d1d4"],
    # --- Lane C: tower + segments -----------------------------------------------------------
    # T3   tower, mechanical-only, with D1 (ORDER never recommends a >40% fight first).
    "T3": ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "qwen3.5-397b", "--repeats", "1",
           "--max-turns", "1500", "--lookahead", "2", "--label", "tower_qwen3.5-397b_basic_d1d4"],
    # M4b  MT3->MT4 segment (replaces the unwinnable single-floor MT4 fixture).
    "M4b": ["--tower", "--start", "MT3", "--end", "MT4", "--preset", "qwen3.5-397b", "--repeats", "5",
            "--max-turns", "300", "--lookahead", "3", "--label", "MT3-MT4_qwen3.5-397b_basic_d1d4"],
    # W1/W2  walkthrough segments 1 (MT5->MT8 red-bat gate) and 2 with the LLM (heuristic fails both).
    "W1": ["--tower", "--checkpoint", "1", "--preset", "qwen3.5-397b", "--repeats", "2",
           "--max-turns", "400", "--lookahead", "2", "--label", "segment1_qwen3.5-397b_basic_d1d4"],
    "W2": ["--tower", "--checkpoint", "2", "--preset", "qwen3.5-397b", "--repeats", "2",
           "--max-turns", "400", "--lookahead", "2", "--label", "segment2_qwen3.5-397b_basic_d1d4"],
    # --- Lane D: RQ3 + variance -------------------------------------------------------------
    # G2b  multistep-5 again on the new stack (PLAN schema still pending: the parse-error rate is
    #      itself the measurement; if it stays ~40% the D6 fix is confirmed necessary).
    "G2b": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "3", "--lookahead", "3",
            "--mode", "multistep-5", "--label", "simple_qwen3.5-397b_basic_multistep5_d1d4"],
    # V1  temperature 0.6 on the solved stack: does the residual nondeterminism return once
    #     sampling is on, or does the unambiguous annotation dominate? (Ch9 "variance = ambiguity")
    "V1": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--temperature", "0.6", "--label", "simple_qwen3.5-397b_basic_d1d4_t06"],
    # B13  glm N->10 on the new stack (cross-family headline needs the same N as 397B).
    "B13": ["--floor", "simple", "--preset", "glm-5.3-flash", "--repeats", "5", "--lookahead", "3",
            "--label", "simple_glm-5.3-flash_basic_d1d4"],
    # ---------------------------------------------------------------------------------------
    # ROUND 3 (2026-09-26, engine K1/K2 key economy + R1 repair candidates + S1 no level-ups —
    # SIMPLE_FLOOR_PLAN.md §15/§16; predictions pre-registered in Ch8 §8.20.10). Two lanes max.
    # --- Lane A: simple ----------------------------------------------------------------------
    # B14  397B, N=10: K2 separates the T4 doors ((4,7) yellow 1→2, (7,5) 1→0 last key) that
    #      B10/V1's three failures chose between on a 9-HP tie.
    "B14": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "10", "--lookahead", "3",
            "--label", "simple_qwen3.5-397b_basic_k1k2"],
    # B15  qwen3.6-35b with a 16K thinking cap (B11's 8K cap truncated → repair → heuristic) + R1.
    "B15": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
            "--label", "simple_qwen3.6-35b_basic_k1k2_16k"],
    # --- Lane B: complex + tower --------------------------------------------------------------
    # CB4  complex, basic prompt, 397B: K1 makes the 2-keys-for-3-yellow-doors budget visible;
    #      K2 does NOT separate the three yellow doors at the CB2 divergence (all 'last key').
    "CB4": ["--floor", "complex", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
            "--label", "complex_qwen3.5-397b_basic_k1k2"],
    # T4   tower, mechanical-only, S1 (no level-up offers) + K1/K2 + R1; T3 was void (crash).
    "T4": ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "qwen3.5-397b", "--repeats", "1",
           "--max-turns", "1500", "--lookahead", "2", "--label", "tower_qwen3.5-397b_basic_k1k2"],
    # W1b  walkthrough segment 1 (MT5->MT8 red-bat gate) with S1: W1 bought 2 level-ups.
    "W1b": ["--tower", "--checkpoint", "1", "--preset", "qwen3.5-397b", "--repeats", "2",
            "--max-turns", "400", "--lookahead", "2", "--label", "segment1_qwen3.5-397b_basic_k1k2"],
    # ---------------------------------------------------------------------------------------
    # ROUND 4a (2026-09-26): depth and context ablations on the solved simple stack (B14 = 10/10).
    # K1/K2 key lines are flood-fill facts independent of LOOKAHEAD_DEPTH, so the round-2 L1/L2 0/5
    # (all failed at the T4 key decision) must be re-measured. H0 drops the 6 prior user/assistant
    # pairs, ~75 % of every request's input.
    "LA0": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "0",
            "--label", "simple_qwen3.5-397b_basic_k1k2_la0"],
    "LA1": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "1",
            "--label", "simple_qwen3.5-397b_basic_k1k2_la1"],
    "LA2": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "2",
            "--label", "simple_qwen3.5-397b_basic_k1k2_la2"],
    "H0": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_basic_k1k2_hist0"],
    "H0s": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
            "--label", "simple_qwen3.6-35b_basic_k1k2_16k_hist0"],
    # ROUND 4b (2026-09-26): N 5 -> 10 on the round-4a cells that decide defaults (history off, LA2),
    # plus complex with history off. Lethal-only positions now end as 'stuck' (lethal_only_stop).
    "H0b": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3", "--append",
            "--label", "simple_qwen3.5-397b_basic_k1k2_hist0"],
    "H0sb": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3", "--append",
             "--label", "simple_qwen3.6-35b_basic_k1k2_16k_hist0"],
    "H0c": ["--floor", "complex", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
            "--label", "complex_qwen3.5-397b_basic_k1k2_hist0"],
    "LA2b": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "2", "--append",
             "--label", "simple_qwen3.5-397b_basic_k1k2_la2"],
    # ROUND 4c (tower): S2 shop-behind value + HP-floor 40 % rule (with needed-unlock exemption) +
    # lethal-only positions end as stuck. Same LA2 / 8K as T4 and W1b.
    "T5": ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "qwen3.5-397b", "--repeats", "1",
           "--max-turns", "1500", "--lookahead", "2", "--label", "tower_qwen3.5-397b_basic_s2hp"],
    "W1c": ["--tower", "--checkpoint", "1", "--preset", "qwen3.5-397b", "--repeats", "2",
            "--max-turns", "400", "--lookahead", "2", "--label", "segment1_qwen3.5-397b_basic_s2hp"],
    # CP1: MOTA_COMPACT_PROMPT=1 vs H0 (both history off), N=10 guard.
    "CP1": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "10", "--lookahead", "3",
            "--label", "simple_qwen3.5-397b_basic_k1k2_hist0_compact"],
    # ---------------------------------------------------------------------------------------
    # ROUND 5 (overnight 2026-09-27, final): candidate final stack = K1/K2 + history off +
    # F-ORD2 (two-sided, named ORDER line) + F-K3 (flood key line for fights). Depth curve on it,
    # the map-only choice-generation ablation (no action list, no lookahead, no annotations),
    # complex, tower. Lane A = 397B, lane B = qwen3.6-35b (fast) then tower.
    "F1": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "10", "--lookahead", "3",
           "--label", "simple_qwen3.5-397b_final_la3"],
    "F2": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "2",
           "--label", "simple_qwen3.5-397b_final_la2"],
    "F3a": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "3", "--lookahead", "1",
            "--label", "simple_qwen3.5-397b_final_la1"],
    "F3b": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "3", "--lookahead", "0",
            "--label", "simple_qwen3.5-397b_final_la0"],
    "ME1": ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "3", "--mode", "map-enum",
            "--label", "simple_qwen3.5-397b_mapenum"],
    "ME3": ["--floor", "complex", "--preset", "qwen3.5-397b", "--repeats", "2", "--mode", "map-enum",
            "--label", "complex_qwen3.5-397b_mapenum"],
    "FC": ["--floor", "complex", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3",
           "--label", "complex_qwen3.5-397b_final_la3"],
    "F1s": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "10", "--lookahead", "3",
            "--label", "simple_qwen3.6-35b_final_la3"],
    "F2s": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "10", "--lookahead", "2",
            "--label", "simple_qwen3.6-35b_final_la2"],
    "F3as": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "1",
             "--label", "simple_qwen3.6-35b_final_la1"],
    "F3bs": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "0",
             "--label", "simple_qwen3.6-35b_final_la0"],
    "ME1s": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "3", "--mode", "map-enum",
             "--label", "simple_qwen3.6-35b_mapenum"],
    "ME2s": ["--floor", "simple", "--preset", "qwen3.6-35b", "--repeats", "3", "--mode", "map-enum-costs",
             "--label", "simple_qwen3.6-35b_mapenum_costs"],
    "ME3s": ["--floor", "complex", "--preset", "qwen3.6-35b", "--repeats", "2", "--mode", "map-enum",
             "--label", "complex_qwen3.6-35b_mapenum"],
    "FCs": ["--floor", "complex", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
            "--label", "complex_qwen3.6-35b_final_la3"],
    "T6": ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "qwen3.5-397b", "--repeats", "1",
           "--max-turns", "1500", "--lookahead", "2", "--label", "tower_qwen3.5-397b_final"],
    "W1d": ["--tower", "--checkpoint", "1", "--preset", "qwen3.5-397b", "--repeats", "2",
            "--max-turns", "400", "--lookahead", "2", "--label", "segment1_qwen3.5-397b_final"],
}
# ROUND 5b (2026-09-27 afternoon): the round-5 F-ORD2 positive line had no 40 % guard and told
# 9/10 35B runs to take the 46 % Bat at T4 (F1s 1/10, F1 7/10). Guard added; same cells re-run
# under new labels (*_final2_*), the defective *_final_* results kept as the ablation.
for _src, _dst in (("F1", "G1"), ("F2", "G2"), ("FC", "GC"), ("F1s", "G1s"), ("F2s", "G2s"),
                   ("F3as", "G3as"), ("F3bs", "G3bs"), ("FCs", "GCs"), ("T6", "G6"), ("W1d", "GW1"),
                   ("F3a", "G3a"), ("F3b", "G3b")):
    EXPERIMENTS[_dst] = [a.replace("_final", "_final2") for a in EXPERIMENTS[_src]]
# ROUND 6 (2026-09-28, user-requested): held-out generated floors, LLM-side tower memory, LLM-built
# graph agent — all on the final stack (history off + guarded F-ORD2 + F-K3).
for _i in range(1, 6):
    EXPERIMENTS[f"GEN{_i}"] = ["--floor", f"data/floors/gen/gen{_i:02d}.txt", "--preset", "qwen3.5-397b",
                               "--repeats", "3", "--lookahead", "3", "--label", f"gen{_i:02d}_qwen3.5-397b_final2"]
    EXPERIMENTS[f"GEN{_i}s"] = ["--floor", f"data/floors/gen/gen{_i:02d}.txt", "--preset", "qwen3.6-35b",
                                "--repeats", "3", "--lookahead", "3", "--label", f"gen{_i:02d}_qwen3.6-35b_final2"]
EXPERIMENTS["TM1"] = ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "qwen3.5-397b", "--repeats", "1",
                      "--max-turns", "1500", "--lookahead", "2", "--label", "tower_qwen3.5-397b_final2_memory"]
EXPERIMENTS["MG1"] = ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "2", "--mode", "map-graph",
                      "--label", "simple_qwen3.5-397b_mapgraph"]

EXPERIMENT_ENV = {
    "T1": {"THINKING_MAX_TOKENS": "8192"},
    "T0": {"THINKING_MAX_TOKENS": "8192"},
    "T2": {"THINKING_MAX_TOKENS": "8192"},
    "T3": {"THINKING_MAX_TOKENS": "8192"},
    "W1": {"THINKING_MAX_TOKENS": "8192"},
    "W2": {"THINKING_MAX_TOKENS": "8192"},
    "R0": {"MOTA_LEGACY_SEEDS": "1", "MOTA_STRATEGIC_OVERRIDES": "1"},
    "C3": {"MOTA_SUPPRESS_HINTS": "0"},
    "CS1": {"MOTA_SUPPRESS_HINTS": "0"},
    "B8": {"THINKING_MAX_TOKENS": "8192"},
    "B11": {"THINKING_MAX_TOKENS": "8192"},
    "B12": {"THINKING_MAX_TOKENS": "8192"},
    "B15": {"THINKING_MAX_TOKENS": "16384"},
    "T4": {"THINKING_MAX_TOKENS": "8192"},
    "W1b": {"THINKING_MAX_TOKENS": "8192"},
    "H0": {"CONVERSATION_HISTORY_TURNS": "0"},
    "H0s": {"CONVERSATION_HISTORY_TURNS": "0", "THINKING_MAX_TOKENS": "16384"},
    "H0b": {"CONVERSATION_HISTORY_TURNS": "0"},
    "H0sb": {"CONVERSATION_HISTORY_TURNS": "0", "THINKING_MAX_TOKENS": "16384"},
    "H0c": {"CONVERSATION_HISTORY_TURNS": "0"},
    "T5": {"THINKING_MAX_TOKENS": "8192"},
    "W1c": {"THINKING_MAX_TOKENS": "8192"},
    "CP1": {"CONVERSATION_HISTORY_TURNS": "0", "MOTA_COMPACT_PROMPT": "1"},
}
_FINAL = {"CONVERSATION_HISTORY_TURNS": "0", "MOTA_ORDER_TWO_SIDED": "1", "MOTA_FIGHT_KEY_FLOOD": "1"}
for _k in ("F1", "F2", "F3a", "F3b", "FC"):
    EXPERIMENT_ENV[_k] = dict(_FINAL)
for _k in ("F1s", "F2s", "F3as", "F3bs", "FCs"):
    EXPERIMENT_ENV[_k] = {**_FINAL, "THINKING_MAX_TOKENS": "16384"}
for _k in ("ME1", "ME3"):
    EXPERIMENT_ENV[_k] = {"CONVERSATION_HISTORY_TURNS": "0", "THINKING_MAX_TOKENS": "32768"}
for _k in ("ME1s", "ME2s", "ME3s"):
    EXPERIMENT_ENV[_k] = {"CONVERSATION_HISTORY_TURNS": "0", "THINKING_MAX_TOKENS": "32768"}
for _k in ("T6", "W1d"):
    EXPERIMENT_ENV[_k] = {**_FINAL, "THINKING_MAX_TOKENS": "8192"}
for _src, _dst in (("F1", "G1"), ("F2", "G2"), ("FC", "GC"), ("F1s", "G1s"), ("F2s", "G2s"),
                   ("F3as", "G3as"), ("F3bs", "G3bs"), ("FCs", "GCs"), ("T6", "G6"), ("W1d", "GW1"),
                   ("F3a", "G3a"), ("F3b", "G3b")):
    EXPERIMENT_ENV[_dst] = dict(EXPERIMENT_ENV[_src])
for _i in range(1, 6):
    EXPERIMENT_ENV[f"GEN{_i}"] = dict(_FINAL)
    EXPERIMENT_ENV[f"GEN{_i}s"] = {**_FINAL, "THINKING_MAX_TOKENS": "16384"}
EXPERIMENT_ENV["TM1"] = {**_FINAL, "THINKING_MAX_TOKENS": "8192", "MOTA_LLM_MEMORY": "1"}
EXPERIMENT_ENV["MG1"] = {"CONVERSATION_HISTORY_TURNS": "0", "THINKING_MAX_TOKENS": "32768"}
# ROUND 7 (2026-09-29, RQ3 planning granularity on the prompts that clear each scenario). Same model, prompt,
# engine and annotations as the reactive arm; only how many actions one call commits to changes
# (MOTA_PLAN_STEPS=k: choose one action + commit k-1 more; a committed step that no longer fits the state
# triggers a new call; tower plans are cleared at every floor change, so k=60 = one plan per floor arrival).
# Reactive arms: simple G1 (10/10), tower G6 (MT7); complex needs a fresh reactive arm (C3 predates D1-D4/K1K2).
_SIMPLE = ["--floor", "simple", "--preset", "qwen3.5-397b", "--repeats", "5", "--lookahead", "3"]
_CPLX = ["--floor", "complex", "--preset", "qwen3.6-35b", "--repeats", "5", "--lookahead", "3",
         "--disable-overrides", "--prompt-file", "complex_bfs_strategy_survival.txt"]
_TOWER = ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "qwen3.5-397b", "--repeats", "1",
          "--max-turns", "1500", "--lookahead", "2"]
for _k, _steps in (("2", "2"), ("3", "3"), ("5", "5"), ("F", "60")):
    EXPERIMENTS[f"P{_k}"] = _SIMPLE + ["--label", f"simple_qwen3.5-397b_final2_plan{_k.lower()}"]
    EXPERIMENTS[f"CP{_k}"] = _CPLX + ["--label", f"complex_qwen3.6-35b_survival_final2_plan{_k.lower()}"]
    EXPERIMENTS[f"TP{_k}"] = _TOWER + ["--label", f"tower_qwen3.5-397b_final2_plan{_k.lower()}"]
    EXPERIMENT_ENV[f"P{_k}"] = {**_FINAL, "MOTA_PLAN_STEPS": _steps, "THINKING_MAX_TOKENS": "32768", "LLM_TIMEOUT": "1800"}
    EXPERIMENT_ENV[f"CP{_k}"] = {**_FINAL, "THINKING_MAX_TOKENS": "16384", "MOTA_SUPPRESS_HINTS": "0",
                                 "MOTA_PLAN_STEPS": _steps}
    EXPERIMENT_ENV[f"TP{_k}"] = {**_FINAL, "THINKING_MAX_TOKENS": "8192", "MOTA_PLAN_STEPS": _steps}
EXPERIMENTS["PO"] = _SIMPLE + ["--label", "simple_qwen3.5-397b_final2_oneshot_plan"]
EXPERIMENTS["CR"] = _CPLX + ["--label", "complex_qwen3.6-35b_survival_final2_reactive"]
EXPERIMENTS["CO"] = _CPLX + ["--label", "complex_qwen3.6-35b_survival_final2_oneshot_plan"]
EXPERIMENTS["TR"] = _TOWER + ["--append", "--label", "tower_qwen3.5-397b_final2"]  # 2nd reactive tower run (G6 = MT7)
# One-shot = one whole-floor NEXT plan, never re-planned (the legacy --mode oneshot PLAN parser matched 1/10 plans).
_ONESHOT = {"MOTA_PLAN_STEPS": "60", "MOTA_PLAN_NO_REPLAN": "1"}
EXPERIMENT_ENV["PO"] = {**_FINAL, **_ONESHOT, "THINKING_MAX_TOKENS": "32768", "LLM_TIMEOUT": "1800"}
EXPERIMENT_ENV["CR"] = {**_FINAL, "THINKING_MAX_TOKENS": "16384", "MOTA_SUPPRESS_HINTS": "0"}
EXPERIMENT_ENV["CO"] = {**EXPERIMENT_ENV["CR"], **_ONESHOT}
EXPERIMENT_ENV["TR"] = {**_FINAL, "THINKING_MAX_TOKENS": "8192"}
# ROUND 7b (user 2026-09-29: multi-step planning should be tested with the stronger reasoning models):
# every granularity INCLUDING its own reactive arm on deepseek-v4-flash (thinking) and qwen3.8-27b, so each
# comparison is within one model. 27B (~100 s/call) runs single floors only, N=3; deepseek also runs the tower.
# Round 7d (2026-09-29): + plan-2; every arm of this study (reactive included) at a 32K thinking cap and 1800 s
# timeout (16K truncated 27B plan answers 12-25x and deepseek complex reactive 11x); tower 16K. Reactive arms
# re-run under that budget get the suffix _t32 (the 16K runs stay as they are).
_MODES = (("R", None, None), ("P2", "2", None), ("P3", "3", None), ("P5", "5", None), ("PF", "60", None),
          ("PO", "60", "oneshot"))
_BUDGET = {"THINKING_MAX_TOKENS": "32768", "LLM_TIMEOUT": "1800"}
for _m, _preset, _n in (("D", "deepseek-v4-flash-think", "5"), ("Q", "qwen3.8-27b", "3")):
    _tag = _preset.replace("-think", "")
    for _code, _steps, _mode in _MODES:
        _extra = []
        _sfx = {"R": "reactive_t32", "P2": "plan2", "P3": "plan3", "P5": "plan5", "PF": "planf",
                "PO": "oneshot_plan"}[_code]
        _env = {**_FINAL, **_BUDGET, **({"MOTA_PLAN_STEPS": _steps} if _steps else {}),
                **({"MOTA_PLAN_NO_REPLAN": "1"} if _mode == "oneshot" else {})}
        EXPERIMENTS[f"{_m}S{_code}"] = ["--floor", "simple", "--preset", _preset, "--repeats", _n, "--lookahead", "3",
                                        *_extra, "--label", f"simple_{_tag}_final2_{_sfx}"]
        EXPERIMENTS[f"{_m}C{_code}"] = ["--floor", "complex", "--preset", _preset, "--repeats", _n, "--lookahead", "3",
                                        "--disable-overrides", "--prompt-file", "complex_bfs_strategy_survival.txt",
                                        *_extra, "--label", f"complex_{_tag}_survival_final2_{_sfx}"]
        EXPERIMENT_ENV[f"{_m}S{_code}"] = dict(_env)
        EXPERIMENT_ENV[f"{_m}C{_code}"] = {**_env, "MOTA_SUPPRESS_HINTS": "0"}
        if _m == "D" and _code != "PO":
            EXPERIMENTS[f"DT{_code}"] = ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", _preset,
                                         "--repeats", "1", "--max-turns", "1500", "--lookahead", "2",
                                         "--label", f"tower_{_tag}_final2_{_sfx.replace('_t32', '_t16')}"]
            EXPERIMENT_ENV[f"DT{_code}"] = {**_FINAL, "THINKING_MAX_TOKENS": "16384", "LLM_TIMEOUT": "1800",
                                            **({"MOTA_PLAN_STEPS": _steps} if _steps else {})}
# ROUND 8 (2026-09-29, last overnight batch): (a) the hand-designed floors in their final versions (unique solution,
# Java-verified), reactive final stack; (b) the complex floor with a prompt compiled from the EXACT HP-68 route
# (every earlier complex kill followed the published solver's HP-22 route). Both on key 2 after lane C.
for _m, _preset, _n in (("D", "deepseek-v4-flash-think", "5"), ("S", "qwen3.6-35b", "3")):
    _tag = _preset.replace("-think", "")
    for _h in (1, 2, 3, 4):
        EXPERIMENTS[f"H{_m}{_h}"] = ["--floor", f"data/floors/hand/hand{_h:02d}.txt", "--preset", _preset,
                                    "--repeats", _n, "--lookahead", "3", "--label", f"hand{_h:02d}_{_tag}_final2"]
        EXPERIMENT_ENV[f"H{_m}{_h}"] = {**_FINAL, "THINKING_MAX_TOKENS": "16384"}
    EXPERIMENTS[f"X68{_m}"] = ["--floor", "complex", "--preset", _preset, "--repeats", "5", "--lookahead", "3",
                               "--disable-overrides", "--prompt-file", "complex_exact68_sequence.txt",
                               "--label", f"complex_{_tag}_exact68_final2"]
    EXPERIMENT_ENV[f"X68{_m}"] = {**_FINAL, "THINKING_MAX_TOKENS": "16384", "MOTA_SUPPRESS_HINTS": "0"}
# 5th X68D episode (lost when its queue runner was stopped).
EXPERIMENTS["X68D1"] = [a if a != "5" else "1" for a in EXPERIMENTS["X68D"]] + ["--append"]
EXPERIMENT_ENV["X68D1"] = dict(EXPERIMENT_ENV["X68D"])
# Remaining 4 DCP3 episodes (1 stored before the queue was re-ordered: one-shot -> 5-step -> 3-step).
EXPERIMENTS["DCP3a"] = [a if a != "5" else "4" for a in EXPERIMENTS["DCP3"]] + ["--append"]
EXPERIMENT_ENV["DCP3a"] = dict(EXPERIMENT_ENV["DCP3"])
# The k=60 cells above asked for "your plan for the rest of this floor ... up to the goal"; keep that wording for
# exact reproduction. ROUND 9 (user 2026-09-29): the long-plan conditions ask for "as many actions as you can"
# (MOTA_PLAN_WORDING unset) and are re-run under new labels: *_maxsteps (re-planned) / *_maxsteps_once (one call).
for _c, _e in list(EXPERIMENT_ENV.items()):
    if _e.get("MOTA_PLAN_STEPS") == "60":
        _e["MOTA_PLAN_WORDING"] = "floor"
for _src, _new, _sfx in (("DSPF", "DSM", "maxsteps"), ("DSPO", "DSMO", "maxsteps_once"), ("DCPO", "DCMO", "maxsteps_once"),
                         ("PF", "PM", "maxsteps"), ("PO", "PMO", "maxsteps_once")):
    _args = list(EXPERIMENTS[_src])
    _i = _args.index("--label")
    _args[_i + 1] = _args[_i + 1].rsplit("_final2_", 1)[0] + f"_final2_{_sfx}"
    EXPERIMENTS[_new] = _args
    EXPERIMENT_ENV[_new] = {k: v for k, v in EXPERIMENT_ENV[_src].items() if k != "MOTA_PLAN_WORDING"}
# ROUND 10 (user 2026-09-30): fill the empty cells of Tables 6.2, 6.8 and 6.10.
# Qwen3.5-397B on hand02-04 (same settings as its hand01 cell); 4 more max-steps re-planned simple episodes (PM stopped at 1);
# deepseek tower commit-2 / long plan (both wordings); deepseek complex-route long plan re-planned (both wordings);
# deepseek complex with the single-floor prompt; Qwen3.8-27B committed plans at the study budget with its own 32K reactive arm.
for _h in (2, 3, 4):
    EXPERIMENTS[f"HQ{_h}"] = ["--floor", f"data/floors/hand/hand{_h:02d}.txt", "--preset", "qwen3.5-397b", "--repeats", "5",
                              "--lookahead", "3", "--label", f"hand{_h:02d}_qwen3.5-397b_final2"]
    EXPERIMENT_ENV[f"HQ{_h}"] = {**_FINAL, "THINKING_MAX_TOKENS": "32768", "LLM_TIMEOUT": "300"}
EXPERIMENTS["PMa"] = [a if a != "5" else "4" for a in EXPERIMENTS["PM"]] + ["--append"]
EXPERIMENT_ENV["PMa"] = dict(EXPERIMENT_ENV["PM"])
# hand02 stopped after 1 episode when lane A's runner was re-queued.
EXPERIMENTS["HQ2a"] = [a if a != "5" else "4" for a in EXPERIMENTS["HQ2"]] + ["--append"]
EXPERIMENT_ENV["HQ2a"] = dict(EXPERIMENT_ENV["HQ2"])
for _src, _new, _sfx in (("DTPF", "DTM", "maxsteps"), ("DCPF", "DCM", "maxsteps"), ("QSPF", "QSM", "maxsteps"),
                         ("QSPO", "QSMO", "maxsteps_once")):
    _args = list(EXPERIMENTS[_src])
    _i = _args.index("--label")
    _args[_i + 1] = _args[_i + 1].rsplit("_final2_", 1)[0] + f"_final2_{_sfx}"
    EXPERIMENTS[_new] = _args
    EXPERIMENT_ENV[_new] = {k: v for k, v in EXPERIMENT_ENV[_src].items() if k != "MOTA_PLAN_WORDING"}
EXPERIMENTS["DCB"] = ["--floor", "complex", "--preset", "deepseek-v4-flash-think", "--repeats", "5", "--lookahead", "3",
                      "--label", "complex_deepseek-v4-flash_final2_la3"]
EXPERIMENT_ENV["DCB"] = {**_FINAL, "THINKING_MAX_TOKENS": "32768"}
# Tower single call = one "as many as you can" plan per floor (later floors are unseen), heuristic for the rest.
EXPERIMENTS["DTMO"] = [a if a != "tower_deepseek-v4-flash_final2_maxsteps" else a + "_once" for a in EXPERIMENTS["DTM"]]
EXPERIMENT_ENV["DTMO"] = {**EXPERIMENT_ENV["DTM"], "MOTA_PLAN_NO_REPLAN": "1"}
# Qwen3.8-27B complex route prompt: reactive / commit 2, 3, 5 (QCR..QCP5 above) + max-steps re-planned and single call.
for _src, _new, _sfx in (("QCPF", "QCM", "maxsteps"), ("QCPO", "QCMO", "maxsteps_once")):
    _args = list(EXPERIMENTS[_src])
    _i = _args.index("--label")
    _args[_i + 1] = _args[_i + 1].rsplit("_final2_", 1)[0] + f"_final2_{_sfx}"
    EXPERIMENTS[_new] = _args
    EXPERIMENT_ENV[_new] = {k: v for k, v in EXPERIMENT_ENV[_src].items() if k != "MOTA_PLAN_WORDING"}
# Qwen3.8-27B via OpenRouter (user 2026-09-30; SAIA ~80 s/call): the whole 27B row, reactive arm included, on one host.
_OR = {"SAIA_BASE_URL": "https://openrouter.ai/api/v1"}
for _fl in ("S", "C"):
    for _src, _new in (("R", "R"), ("P2", "P2"), ("P3", "P3"), ("P5", "P5"), ("M", "M"), ("MO", "MO")):
        _code = f"Q{_fl}{_src}"
        EXPERIMENTS[f"OR{_fl}{_new}"] = [a.replace("qwen3.8-27b", "qwen3.8-27b-or") for a in EXPERIMENTS[_code]]
        EXPERIMENT_ENV[f"OR{_fl}{_new}"] = {**EXPERIMENT_ENV[_code], **_OR}
# Qwen3.8-27B via Groq (~10x faster decoding; max 16K output, reasoning_effort=high) at temperature 0.6 (user
# 2026-09-30: Qwen's recommended thinking-mode sampling); reactive arm included, so comparisons stay within one row.
_GQ = {"SAIA_BASE_URL": "https://api.groq.com/openai/v1", "THINKING_MAX_TOKENS": "16384"}
for _fl in ("S", "C"):
    for _m in ("R", "P2", "P3", "P5", "M", "MO"):
        _args = [a.replace("qwen3.8-27b", "qwen3.8-27b-groq").replace("_reactive_t32", "_reactive")
                 for a in EXPERIMENTS[f"Q{_fl}{_m}"]]
        _i = _args.index("--label")
        _args[_i + 1] += "_t06"
        EXPERIMENTS[f"GQ{_fl}{_m}"] = _args + ["--temperature", "0.6"]
        EXPERIMENT_ENV[f"GQ{_fl}{_m}"] = {**EXPERIMENT_ENV[f"Q{_fl}{_m}"], **_GQ}
# Groq free tier is capped at 8K tokens/min (~110 s/decision incl. waits), so the 27B row is split by floor:
# simple on Groq (GQS*), complex on SAIA key 2 (SQC*, 32K budget), both at T=0.6.
for _m in ("R", "P2", "P3", "P5", "M", "MO"):
    _args = list(EXPERIMENTS[f"QC{_m}"])
    _i = _args.index("--label")
    _args[_i + 1] += "_t06"
    EXPERIMENTS[f"SQC{_m}"] = _args + ["--temperature", "0.6"]
    EXPERIMENT_ENV[f"SQC{_m}"] = dict(EXPERIMENT_ENV[f"QC{_m}"])
# Groq free tier also caps OUTPUT at 1000 tokens/min (a 5K-token answer is rejected until the bucket refills):
# ~120 s/decision, so the simple-floor 27B cells run on SAIA too (SQS*).
for _m in ("R", "P2", "P3", "P5", "M", "MO"):
    _args = list(EXPERIMENTS[f"QS{_m}"])
    _i = _args.index("--label")
    _args[_i + 1] += "_t06"
    EXPERIMENTS[f"SQS{_m}"] = _args + ["--temperature", "0.6"]
    EXPERIMENT_ENV[f"SQS{_m}"] = dict(EXPERIMENT_ENV[f"QS{_m}"])
# ROUND 11 (user 2026-09-30): temperature 0.6 on the cells whose T=0 failures carry a claim (committed plans on the
# simple floor, the single-floor prompt on complex, hand03/04, tower), plus N 5->10 at both temperatures for the one
# cell that moved (deepseek complex route reactive 3/5 -> 5/5).
for _src in ("DSR", "DSP3", "DCB", "HD3", "HD4", "DTR", "P3", "GC"):
    _args = list(EXPERIMENTS[_src])
    _i = _args.index("--label")
    _args[_i + 1] += "_t06"
    EXPERIMENTS[f"T6{_src}"] = _args + ["--temperature", "0.6"]
    EXPERIMENT_ENV[f"T6{_src}"] = dict(EXPERIMENT_ENV.get(_src, {}))
EXPERIMENTS["DCRa"] = list(EXPERIMENTS["DCR"]) + ["--append"]
EXPERIMENT_ENV["DCRa"] = dict(EXPERIMENT_ENV["DCR"])
EXPERIMENTS["T06CRa"] = [a + "_t06" if a == "complex_deepseek-v4-flash_survival_final2_reactive_t32" else a
                         for a in EXPERIMENTS["DCR"]] + ["--temperature", "0.6", "--append"]
EXPERIMENT_ENV["T06CRa"] = dict(EXPERIMENT_ENV["DCR"])
# Temperature 1.0 pilot (the Qwen3.5+ thinking-mode recommendation): one cell per claim type, N=5.
for _src in ("DCR", "DCB", "G1"):
    _args = [a if a != "10" else "5" for a in EXPERIMENTS[_src]]
    _i = _args.index("--label")
    _args[_i + 1] += "_t10"
    EXPERIMENTS[f"T10{_src}"] = _args + ["--temperature", "1.0"]
    EXPERIMENT_ENV[f"T10{_src}"] = dict(EXPERIMENT_ENV.get(_src, {}))
# ROUND 12 (overnight 2026-09-30/10-01): how far do the main claims generalise beyond the development floor?
# (a) final configuration on the held-out generated floors gen03-gen15 (DeepSeek, N=3 each);
# (b) planning, bare observation and lookahead depth on hand01/hand02 (won reactively, not used in development);
# (c) consistency: route prompt on the final configuration for 397B/35B, GLM on the final configuration;
# (d) tower replicates (DeepSeek, 397B).
for _i in range(3, 16):
    EXPERIMENTS[f"GD{_i}"] = ["--floor", f"data/floors/gen/gen{_i:02d}.txt", "--preset", "deepseek-v4-flash-think",
                              "--repeats", "3", "--lookahead", "3", "--label", f"gen{_i:02d}_deepseek-v4-flash_final2"]
    EXPERIMENT_ENV[f"GD{_i}"] = {**_FINAL, "THINKING_MAX_TOKENS": "16384"}
for _h in (1, 2):
    _base = [a for a in EXPERIMENTS[f"HD{_h}"] if a != f"hand0{_h}_deepseek-v4-flash_final2"][:-1]
    _lab = f"hand0{_h}_deepseek-v4-flash_final2"
    for _code, _sfx, _env in (("R32", "reactive_t32", {}), ("P3", "plan3", {"MOTA_PLAN_STEPS": "3"}),
                              ("P5", "plan5", {"MOTA_PLAN_STEPS": "5"}), ("M", "maxsteps", {"MOTA_PLAN_STEPS": "60"})):
        EXPERIMENTS[f"HD{_h}{_code}"] = _base + ["--label", f"{_lab}_{_sfx}"]
        EXPERIMENT_ENV[f"HD{_h}{_code}"] = {**_FINAL, "THINKING_MAX_TOKENS": "32768", "LLM_TIMEOUT": "1800", **_env}
    EXPERIMENTS[f"HD{_h}B"] = _base + ["--label", f"{_lab}_bare"]
    EXPERIMENT_ENV[f"HD{_h}B"] = {**EXPERIMENT_ENV[f"HD{_h}"], "MOTA_BARE_OBS": "1"}
    EXPERIMENTS[f"HD{_h}L1"] = [a if a != "3" else "1" for a in _base] + ["--label", f"{_lab}_la1"]
    EXPERIMENT_ENV[f"HD{_h}L1"] = dict(EXPERIMENT_ENV[f"HD{_h}"])
EXPERIMENTS["CQR"] = [a.replace("qwen3.6-35b", "qwen3.5-397b") for a in EXPERIMENTS["CR"]]
EXPERIMENT_ENV["CQR"] = {**EXPERIMENT_ENV["CR"], "THINKING_MAX_TOKENS": "32768"}
EXPERIMENTS["GLS"] = ["--floor", "simple", "--preset", "glm-5.3-flash", "--repeats", "5", "--lookahead", "3",
                      "--label", "simple_glm-5.3-flash_final2_la3"]
EXPERIMENTS["GLC"] = ["--floor", "complex", "--preset", "glm-5.3-flash", "--repeats", "5", "--lookahead", "3",
                      "--label", "complex_glm-5.3-flash_final2_la3"]
EXPERIMENT_ENV["GLS"] = EXPERIMENT_ENV["GLC"] = {**_FINAL, "THINKING_MAX_TOKENS": "32768"}
EXPERIMENTS["DTRa"] = ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "deepseek-v4-flash-think",
                       "--repeats", "2", "--max-turns", "1500", "--lookahead", "2",
                       "--label", "tower_deepseek-v4-flash_final2_reactive", "--append"]
EXPERIMENT_ENV["DTRa"] = {**_FINAL, "THINKING_MAX_TOKENS": "8192"}
# Episodes lost to the 2026-09-30/10-01 connection outages (crashed runs removed by scratch/drop_error_runs.py).
for _src, _new in (("CQR", "CQRa"), ("T6P3", "T6P3a")):
    EXPERIMENTS[_new] = [a if a != "5" else "2" for a in EXPERIMENTS[_src]] + ["--append"]
    EXPERIMENT_ENV[_new] = dict(EXPERIMENT_ENV[_src])
# A third reactive DeepSeek tower run stopped on MT3 (HP 25, Red Slime (1,2)) like both max-steps runs: replicate the
# tower cells so "max-steps plans stop on MT3" can be told apart from an MT3 trap that reactive play also hits.
EXPERIMENTS["DTRb"] = list(EXPERIMENTS["DTRa"])  # 2 more reactive runs, appended (N = 5)
EXPERIMENT_ENV["DTRb"] = dict(EXPERIMENT_ENV["DTRa"])
for _src in ("DTM", "DTMO", "DTP5"):
    _args = list(EXPERIMENTS[_src])
    _args[_args.index("--repeats") + 1] = "2"
    EXPERIMENTS[f"{_src}a"] = _args + ["--append"]
    EXPERIMENT_ENV[f"{_src}a"] = dict(EXPERIMENT_ENV[_src])
# Shop-route line (MOTA_SHOP_ROUTE=1, user 2026-10-01): every run ends on MT7 with 113-131 EXP unspent because the EXP Old
# Man (MT5 (2,8)) sits behind a Big Bat that costs 81 % of HP at the agents' ATK 33; the new line prices the monsters on the
# way to an unreached shop now and after 1-3 registered ATK purchases. Reactive tower, same settings as DTR (8K).
EXPERIMENTS["DTS"] = ["--tower", "--start", "MT0", "--end", "MT23w", "--preset", "deepseek-v4-flash-think",
                      "--repeats", "3", "--max-turns", "1500", "--lookahead", "2",
                      "--label", "tower_deepseek-v4-flash_final2_shoproute"]
EXPERIMENT_ENV["DTS"] = {**_FINAL, "THINKING_MAX_TOKENS": "8192", "MOTA_SHOP_ROUTE": "1"}
EXPERIMENTS["TQS"] = [a.replace("deepseek-v4-flash-think", "qwen3.5-397b").replace("deepseek-v4-flash", "qwen3.5-397b")
                      for a in EXPERIMENTS["DTS"]]
EXPERIMENTS["TQS"][EXPERIMENTS["TQS"].index("--repeats") + 1] = "1"
EXPERIMENT_ENV["TQS"] = dict(EXPERIMENT_ENV["DTS"])
# + MOTA_REMOTE_ACTIONS=1 (user 2026-10-01): the shop-route run bounced MT3 -> MT1 -> MT3 five times on a deferred-door
# return it then did not take; stairs are travel now, actions on every visited floor are offered directly.
EXPERIMENTS["DTSR"] = [a if a != "tower_deepseek-v4-flash_final2_shoproute" else a + "_remote" for a in EXPERIMENTS["DTS"]]
EXPERIMENT_ENV["DTSR"] = {**EXPERIMENT_ENV["DTS"], "MOTA_REMOTE_ACTIONS": "1"}
EXPERIMENTS["TQSR"] = [a if a != "tower_qwen3.5-397b_final2_shoproute" else a + "_remote" for a in EXPERIMENTS["TQS"]]
EXPERIMENT_ENV["TQSR"] = {**EXPERIMENT_ENV["TQS"], "MOTA_REMOTE_ACTIONS": "1"}
# ROUND 13 (user 2026-10-01, replaces all tower results): the action list is every reachable object on every visited
# floor, each floor formatted with the full annotations; stairs only to scout an unvisited floor (auto); tower-wide key
# budget; shop-route line; tower prompt line 13 rewritten (old text: seed_prompts/tower_basic_v1_stairs.txt).
_T3 = {**_FINAL, "MOTA_REMOTE_ACTIONS": "1", "MOTA_SHOP_ROUTE": "1"}
_TW = ["--tower", "--start", "MT0", "--end", "MT23w", "--repeats", "1", "--max-turns", "1500", "--lookahead", "2"]
EXPERIMENTS["T3H"] = ["--tower", "--start", "MT0", "--end", "MT23w", "--max-turns", "1500", "--heuristic",
                      "--label", "tower_MT0-MT23w_heuristic_final3"]  # lookahead 3 as the stored heuristic baseline
EXPERIMENTS["T3DR"] = [*_TW[:5], "--repeats", "3", *_TW[7:], "--preset", "deepseek-v4-flash-think",
                       "--label", "tower_deepseek-v4-flash_final3_reactive"]
EXPERIMENTS["T3QR"] = _TW + ["--preset", "qwen3.5-397b", "--label", "tower_qwen3.5-397b_final3_reactive"]
EXPERIMENT_ENV["T3H"] = {"MOTA_REMOTE_ACTIONS": "1"}
EXPERIMENT_ENV["T3DR"] = EXPERIMENT_ENV["T3QR"] = {**_T3, "THINKING_MAX_TOKENS": "8192"}
for _code, _steps, _sfx, _once in (("T3D2", "2", "plan2", False), ("T3D3", "3", "plan3", False), ("T3D5", "5", "plan5", False),
                                   ("T3DM", "60", "maxsteps", False), ("T3DMO", "60", "maxsteps_once", True)):
    EXPERIMENTS[_code] = _TW + ["--preset", "deepseek-v4-flash-think", "--label", f"tower_deepseek-v4-flash_final3_{_sfx}"]
    EXPERIMENT_ENV[_code] = {**_T3, "THINKING_MAX_TOKENS": "16384", "LLM_TIMEOUT": "1800", "MOTA_PLAN_STEPS": _steps,
                             **({"MOTA_PLAN_NO_REPLAN": "1"} if _once else {})}
# ROUND 14 (user 2026-10-01): every final3 run stopped on MT8 with ATK 67-92 against DEF-90 Red Bats (winnable, not
# affordable). Engine: 'Stat needs' state line (ATK to win / to cost <= 40 % of HP for the strongest pending monsters on
# all visited floors), ATK gates and cross-floor value over all visited floors. Prompt rule 3: ATK high enough that the
# strongest needed monster costs <= 40 % of HP (was: ATK above its DEF). Same env flags as final3 (the code is new).
for _src, _new in (("T3DR", "T4DR"), ("T3QR", "T4QR")):
    EXPERIMENTS[_new] = [a.replace("_final3_", "_final4_") for a in EXPERIMENTS[_src]]
    EXPERIMENT_ENV[_new] = dict(EXPERIMENT_ENV[_src])
# Review 2026-10-01: the single 397B final4 run ended on MT3 (turn 17: Skeleton at 92.6 % of HP, chosen by effCost);
# two more runs so that the tower row is not N=1.
EXPERIMENTS["T4QRa"] = [a if a != "1" else "2" for a in EXPERIMENTS["T4QR"]] + ["--append"]
EXPERIMENT_ENV["T4QRa"] = dict(EXPERIMENT_ENV["T4QR"])
# ROUND 15 / design 4 (user 2026-10-01): the stat-needs line ranked the strongest monsters seen, and early floors show
# late-game monsters; replaced by the 'Way up' line (cheapest route to the next unvisited floor, exact fight costs, what
# each affordable ATK/DEF purchase does to them; actions on it tagged). Prompt: tower_basic.txt (v3 = _v3_statneeds).
for _src, _new in (("T4DR", "T5DR"), ("T4QR", "T5QR")):
    EXPERIMENTS[_new] = [a.replace("_final4_", "_final5_") for a in EXPERIMENTS[_src]]
    EXPERIMENT_ENV[_new] = {**EXPERIMENT_ENV[_src], "MOTA_WAY_UP": "1"}
EXPERIMENTS["T5QRa"] = [a if a != "1" else "2" for a in EXPERIMENTS["T5QR"]] + ["--append"]
EXPERIMENT_ENV["T5QRa"] = dict(EXPERIMENT_ENV["T5QR"])
# Key 2 ran out of its daily quota (2026-10-01 22:35) during T5QRa run 2: one more run on key 1.
EXPERIMENTS["T5QRb"] = list(EXPERIMENTS["T5QR"]) + ["--append"]
EXPERIMENT_ENV["T5QRb"] = dict(EXPERIMENT_ENV["T5QR"])
# Effective-cost test (user 2026-10-01): MOTA_EFFCOST_NET=1 values only the HP the stat gems behind an action save on the
# fights listed now, minus the other fights on the way to them (keys, doors, item scores count 0). Same settings as DSR /
# DCB / T5DR, DeepSeek-V4-Flash (fastest), N=5 / 5 / 1.
for _src, _new, _lab in (("DSR", "E1S", "simple_deepseek-v4-flash_effnet_t32"), ("DCB", "E1C", "complex_deepseek-v4-flash_effnet_la3"),
                         ("T5DR", "E1T", "tower_deepseek-v4-flash_final5_effnet")):
    _args = list(EXPERIMENTS[_src])
    _args[_args.index("--label") + 1] = _lab
    if _src == "T5DR":
        _args[_args.index("--repeats") + 1] = "1"
    EXPERIMENTS[_new] = _args
    EXPERIMENT_ENV[_new] = {**EXPERIMENT_ENV[_src], "MOTA_EFFCOST_NET": "1"}
# Tower fidelity (user 2026-10-01, MOTA_TOWER_FIDELITY=1): MT4 thief opens MT2 (2,7), items.js values for the nine
# differing items, the Cross handed to the MT0 fairy (x4/3, any time). Design 4 otherwise. Labels *_final6_*.
for _src, _new in (("T5DR", "T6DR"), ("T5QR", "T6QR")):
    _args = [a.replace("_final5_", "_final6_") for a in EXPERIMENTS[_src]]
    _args[_args.index("--repeats") + 1] = "3"
    EXPERIMENTS[_new] = _args
    EXPERIMENT_ENV[_new] = {**EXPERIMENT_ENV[_src], "MOTA_TOWER_FIDELITY": "1"}
EXPERIMENTS["T6H"] = [a.replace("_final3", "_final6") for a in EXPERIMENTS["T3H"]]
EXPERIMENT_ENV["T6H"] = {**EXPERIMENT_ENV["T3H"], "MOTA_TOWER_FIDELITY": "1"}
# User 2026-10-01: the tower 40 % HP-floor override is off (the rule is a suggestion). It had replaced the 55 % Skeleton
# at MT3 turn 15 with a Bat in about ten runs and then executed the same Skeleton at 93 % (confirmation gate) = the MT3
# trap. Corrected-engine cells re-run without it (partial results in results/reliability/_superseded_hpfloor/), and
# Qwen3.5-397B designs 3 and 4 re-run without it, each with the prompt those designs used.
for _c in ("T6DR", "T6QR"):
    EXPERIMENT_ENV[_c]["MOTA_TOWER_HP_FLOOR"] = "0"
    EXPERIMENT_ENV[_c]["MOTA_OFFER_LEVELUPS"] = "1"  # user 2026-10-01: rules are suggestions; prompt still says never
for _src, _new, _lab, _prompt in (("T4QR", "T4QRn", "tower_qwen3.5-397b_final4_nohp_reactive", "tower_basic_v3_statneeds.txt"),
                                  ("T5QR", "T5QRn", "tower_qwen3.5-397b_final5_nohp_reactive", "tower_basic_v4_wayup.txt")):
    _args = list(EXPERIMENTS[_src])
    _args[_args.index("--label") + 1] = _lab
    _args[_args.index("--repeats") + 1] = "3"
    EXPERIMENTS[_new] = _args + ["--prompt-file", _prompt]
    EXPERIMENT_ENV[_new] = {**EXPERIMENT_ENV[_src], "MOTA_TOWER_HP_FLOOR": "0"}
# User 2026-10-02: tower rule 4 at 60 % (replay of MT3 turn 15: 397B takes the Skeleton at 60/80/100 %, the Bat only at
# 40 %; both models refuse the 93 % Skeleton at every threshold; scratch/test_hp_rule.py). The tower scenario now sets 60
# in the engine lines too, so every earlier tower cell pins 40 and the corrected-engine cells keep their 40 % prompt.
for _c, _args in list(EXPERIMENTS.items()):
    if "--tower" in _args and _c in EXPERIMENT_ENV:
        EXPERIMENT_ENV[_c] = {**EXPERIMENT_ENV[_c], "MOTA_HP_RULE_PCT": "40"}
    elif "--tower" in _args:
        EXPERIMENT_ENV[_c] = {"MOTA_HP_RULE_PCT": "40"}
for _c in ("T6DR", "T6QR"):
    EXPERIMENTS[_c] = EXPERIMENTS[_c] + ["--prompt-file", "tower_basic_v5_fidelity.txt"]
# Design 5 = corrected engine + rule 4 at 60 % + one-line plan memory (MOTA_PLAN_MEMORY=1), prompt tower_basic.txt.
for _src, _new in (("T6DR", "T7DR"), ("T6QR", "T7QR")):
    EXPERIMENTS[_new] = [a.replace("_final6_", "_final7_") for a in EXPERIMENTS[_src][:-2]]
    EXPERIMENT_ENV[_new] = {k: v for k, v in EXPERIMENT_ENV[_src].items() if k != "MOTA_HP_RULE_PCT"} | {"MOTA_PLAN_MEMORY": "1",
                                                                                                   "MOTA_NO_KEY_PURCHASE": "1",
                                                                                                   "MOTA_WAYUP_COMBINED": "1",
                                                                                                   "MOTA_FREE_AFFORD": "1"}
# Overnight 2026-10-02 (user: N=3 is enough): heuristic on the design-5 engine and the tower planning comparison
# (Table 6.8 tower row) repeated on design 5 with DeepSeek-V4-Flash, commit-3 and commit-5, x3 each.
EXPERIMENTS["T7H"] = [a.replace("_final3", "_final7") for a in EXPERIMENTS["T3H"]]
EXPERIMENT_ENV["T7H"] = {**EXPERIMENT_ENV["T6H"], "MOTA_HP_RULE_PCT": "60"}
for _code, _steps in (("T7D3", "3"), ("T7D5", "5")):
    EXPERIMENTS[_code] = [a.replace("_final7_reactive", f"_final7_plan{_steps}") for a in EXPERIMENTS["T7DR"]]
    EXPERIMENT_ENV[_code] = {**EXPERIMENT_ENV["T7DR"], "MOTA_PLAN_STEPS": _steps, "THINKING_MAX_TOKENS": "16384",
                             "LLM_TIMEOUT": "1800"}
EXPERIMENTS["T7Q3"] = [a.replace("_final7_reactive", "_final7_plan3") for a in EXPERIMENTS["T7QR"]]
EXPERIMENT_ENV["T7Q3"] = {**EXPERIMENT_ENV["T7QR"], "MOTA_PLAN_STEPS": "3", "THINKING_MAX_TOKENS": "16384", "LLM_TIMEOUT": "1800"}
# 2026-10-02 morning: the final7 reactive runs never showed a plan (the PLAN line is in the reasoning field, the extractor
# read only the visible answer; fixed in evaluator._extract_plan_note). Same settings, labels *_final8_reactive.
for _src, _new in (("T7DR", "T8DR"), ("T7QR", "T8QR")):
    EXPERIMENTS[_new] = [a.replace("_final7_", "_final8_") for a in EXPERIMENTS[_src]]
    EXPERIMENT_ENV[_new] = dict(EXPERIMENT_ENV[_src])
# 2026-10-02 afternoon (grill round): key box / ice pickaxe tiles, Holy Water, treasure line, free-fight rewards, red-door
# key price, Cross line + rule. Final design = final9; T9DN = DeepSeek without plan memory (ablation; Qwen later, TODO).
for _src, _new, _sfx in (("T8DR", "T9DR", "_final9_reactive"), ("T8QR", "T9QR", "_final9_reactive"),
                         ("T8DR", "T9DN", "_final9_noplanmem")):
    EXPERIMENTS[_new] = [a.replace("_final8_reactive", _sfx) for a in EXPERIMENTS[_src]]
    EXPERIMENT_ENV[_new] = {k: v for k, v in EXPERIMENT_ENV[_src].items() if not (_new == "T9DN" and k == "MOTA_PLAN_MEMORY")}
# 2026-10-02 night: run 204754 stopped at MT16 (ATK 1028 DEF 969) with the MT15 trades unmodelled (Holy Sword 500 EXP,
# Holy Shield 500 g; either makes the Red Demon King winnable) and its last red key spent on MT10 at turn 426.
for _src, _new in (("T9DR", "T10DR"), ("T9QR", "T10QR")):
    EXPERIMENTS[_new] = [a.replace("_final9_", "_final10_") for a in EXPERIMENTS[_src]]
    EXPERIMENT_ENV[_new] = {**EXPERIMENT_ENV[_src], "MOTA_NPC_TRADES": "1", "MOTA_KEY_RESERVE": "1"}
# 2026-10-03: two more models on final10. Qwen3.6 35B thinks by default; Mistral Medium 3.5 accepts reasoning_effort
# none|high only and needed 430 s for a one-line question at high, so it runs without a reasoning channel (it writes its
# reasoning into the answer).
for _new, _preset in (("T10Q6", "qwen3.6-35b"), ("T10MM", "mistral-medium-3.5")):
    _args = list(EXPERIMENTS["T10DR"])
    _args[_args.index("--preset") + 1] = _preset
    EXPERIMENTS[_new] = [a.replace("deepseek-v4-flash", _preset) if a.startswith("tower_") else a for a in _args]
    EXPERIMENT_ENV[_new] = dict(EXPERIMENT_ENV["T10DR"])
# 2026-10-03 01:50: afterBattle monster changes (MT16 King -> stronger MT17+ monsters) for every final10 cell started
# from now on; T10DR runs 1-3 were already running without them (matters only once the King is dead).
for _c in ("T10QR", "T10Q6", "T10MM"):
    EXPERIMENT_ENV[_c]["MOTA_AFTER_BATTLE"] = "1"
# Lookahead inside the reasoning (user 2026-10-01): bare action list (legal actions, exact damage) + the current grid
# (MOTA_GRID_MAP=1) + an experimental prompt that asks the model to trace each option 2-3 actions ahead itself.
for _code, _floor, _lab in (("SLS", "simple", "simple"), ("SLH", "data/floors/hand/hand01.txt", "hand01")):
    EXPERIMENTS[_code] = ["--floor", _floor, "--preset", "deepseek-v4-flash-think", "--repeats", "5", "--lookahead", "3",
                          "--prompt-file", "self_lookahead.txt", "--label", f"{_lab}_deepseek-v4-flash_selflookahead"]
    EXPERIMENT_ENV[_code] = {**_FINAL, "THINKING_MAX_TOKENS": "32768", "LLM_TIMEOUT": "1800",
                             "MOTA_BARE_OBS": "1", "MOTA_GRID_MAP": "1"}
# Episode 1 of SLS finished on key 2 before its quota ran out; the key-1 lane appends the other four.
EXPERIMENTS["SLS"] = [a if a != "5" else "4" for a in EXPERIMENTS["SLS"]] + ["--append"]
# 2026-10-01 23:45: the model read (x,y) as (row, column) on the grid (CoT: "row7 col5 is Y"); grid axes and prompt now
# say which is which. SLS restarts fresh (old episodes in results/reliability/_superseded_grid/).
EXPERIMENTS["SLS"] = [a for a in EXPERIMENTS["SLS"] if a != "--append"]
EXPERIMENTS["SLS"][EXPERIMENTS["SLS"].index("--repeats") + 1] = "5"
# Middle condition (user 2026-10-01): the floor as areas + blockers (topology only), the model searches and computes.
for _code, _floor, _lab in (("BGS", "simple", "simple"), ("BGH", "data/floors/hand/hand01.txt", "hand01")):
    EXPERIMENTS[_code] = ["--floor", _floor, "--preset", "deepseek-v4-flash-think", "--repeats", "5", "--lookahead", "3",
                          "--prompt-file", "blocker_lookahead.txt", "--label", f"{_lab}_deepseek-v4-flash_blockergraph"]
    EXPERIMENT_ENV[_code] = {**_FINAL, "THINKING_MAX_TOKENS": "32768", "LLM_TIMEOUT": "1800",
                             "MOTA_BARE_OBS": "1", "MOTA_BLOCKER_GRAPH": "1"}
# Temperature check on the strongest T=0 cells (limitation, Ch7): 397B simple final stack (10/10 at T=0),
# deepseek complex-route reactive (3/5) and commit-5 (4/5), all at T=0.6, N=5.
for _src, _new in (("G1", "T06S"), ("DCR", "T06CR"), ("DCP5", "T06C5")):
    _args = [a if a != "10" else "5" for a in EXPERIMENTS[_src]]
    _i = _args.index("--label")
    _args[_i + 1] += "_t06"
    EXPERIMENTS[_new] = _args + ["--temperature", "0.6"]
    EXPERIMENT_ENV[_new] = dict(EXPERIMENT_ENV[_src])
# CANONICAL RE-RUN (user 2026-10-03): every column of Table 6.2 on the current code, N=3, one label family `*_canon`, so
# the main table comes from one engine version. Code V<model><floor>: model Q 397B / D DeepSeek (thinking) / S Qwen3.6-35B /
# M Mistral Medium 3.5 (no reasoning channel); floor S simple, C complex single-floor prompt, R complex route prompt
# (compiled knowledge, overrides off, hints on), 1-4 hand0n. Reasoning caps as in Table 6.1.
_CANON_MODELS = {"Q": ("qwen3.5-397b", {"THINKING_MAX_TOKENS": "32768"}),
                 "D": ("deepseek-v4-flash-think", {"THINKING_MAX_TOKENS": "32768", "LLM_TIMEOUT": "1800"}),
                 "S": ("qwen3.6-35b", {"THINKING_MAX_TOKENS": "16384"}),
                 "M": ("mistral-medium-3.5", {})}
_CANON_FLOORS = {"S": ("simple", "simple", []), "C": ("complex", "complex", []),
                 "R": ("complex", "complex_route", ["--disable-overrides", "--prompt-file", "complex_bfs_strategy_survival.txt"]),
                 **{str(_h): (f"data/floors/hand/hand{_h:02d}.txt", f"hand{_h:02d}", []) for _h in (1, 2, 3, 4)}}
CANON = {}
for _m, (_preset, _caps) in _CANON_MODELS.items():
    _tag = _preset.replace("-think", "")
    CANON[_m] = []
    for _f, (_floor, _name, _extra) in _CANON_FLOORS.items():
        _code = f"V{_m}{_f}"
        EXPERIMENTS[_code] = ["--floor", _floor, "--preset", _preset, "--repeats", "3", "--lookahead", "3", *_extra,
                              "--label", f"{_name}_{_tag}_canon"]
        EXPERIMENT_ENV[_code] = {**_FINAL, **_caps, **({"MOTA_SUPPRESS_HINTS": "0"} if _f == "R" else {})}
        CANON[_m].append(_code)
        # Grill 10-03: every canonical single-floor cell to N=5 (+2 appended).
        def _reps(args, n):
            out = list(args)
            out[out.index("--repeats") + 1] = n
            return out
        EXPERIMENTS[_code + "a"] = _reps(EXPERIMENTS[_code], "2") + ["--append"]
        EXPERIMENT_ENV[_code + "a"] = dict(EXPERIMENT_ENV[_code])
        if _m in ("Q", "D") and _f in ("S", "C", "R"):
            _base = _reps(EXPERIMENTS[_code], "5")
            _lab = _base[_base.index("--label") + 1]
            # Q3 (a): rule 3 of the single-floor prompt at 60 % (prompt differs only in that number; the route prompt
            # keeps its own text, the engine lines quote 60); (b) plan memory as on the tower.
            _hp = _base if _f == "R" else _base + ["--prompt-file", "floor_basic_hp60.txt"]
            EXPERIMENTS[f"H6{_m}{_f}"] = [a if a != _lab else _lab + "_hp60" for a in _hp]
            EXPERIMENT_ENV[f"H6{_m}{_f}"] = {**EXPERIMENT_ENV[_code], "MOTA_HP_RULE_PCT": "60"}
            EXPERIMENTS[f"PM{_m}{_f}"] = [a if a != _lab else _lab + "_planmem" for a in _base]
            EXPERIMENT_ENV[f"PM{_m}{_f}"] = {**EXPERIMENT_ENV[_code], "MOTA_PLAN_MEMORY": "1"}
            # Q4: temperature 0.6 and 1.0 on the canonical cells, N=5 (codes TT06../TT10.., not the tower T10.. cells).
            for _t, _ts in (("0.6", "t06"), ("1.0", "t10")):
                EXPERIMENTS[f"TT{_ts[1:]}{_m}{_f}"] = [a if a != _lab else f"{_lab}_{_ts}" for a in _base] + ["--temperature", _t]
                EXPERIMENT_ENV[f"TT{_ts[1:]}{_m}{_f}"] = dict(EXPERIMENT_ENV[_code])
        # 10-03 reorder (slowest model last): 397B canonical cells straight to N=5 in one go.
        EXPERIMENTS[_code + "5"] = _reps(EXPERIMENTS[_code], "5")
        EXPERIMENT_ENV[_code + "5"] = dict(EXPERIMENT_ENV[_code])
# VQC had 1 of 3 runs when its lane was stopped: 4 more to N=5.
EXPERIMENTS["VQCr"] = EXPERIMENTS["VQC"][:EXPERIMENTS["VQC"].index("--repeats") + 1] + ["4"] + \
    EXPERIMENTS["VQC"][EXPERIMENTS["VQC"].index("--repeats") + 2:] + ["--append"]
EXPERIMENT_ENV["VQCr"] = dict(EXPERIMENT_ENV["VQC"])
# Grill 10-03 Q2: Qwen3.6-35B route 5/5 on 09-30 vs 1/5 now on identical engine input; 5 more runs to N=10.
EXPERIMENTS["VSRb"] = EXPERIMENTS["VSRa"][:EXPERIMENTS["VSRa"].index("--repeats") + 1] + ["5"] + \
    EXPERIMENTS["VSRa"][EXPERIMENTS["VSRa"].index("--repeats") + 2:]
EXPERIMENT_ENV["VSRb"] = dict(EXPERIMENT_ENV["VSR"])
# 10-04 (user): hidden MT18/MT20 staircases now modelled (corrected engine); continue 397B design-6 run 1 from the
# state just before it took the hidden MT18 staircase (turn 708) instead of restarting from MT0.
EXPERIMENTS["T10QRres"] = [a if a != "tower_qwen3.5-397b_final10_reactive" else "tower_qwen3.5-397b_final10_resume"
                           for a in EXPERIMENTS["T10QR"]]
EXPERIMENTS["T10QRres"][EXPERIMENTS["T10QRres"].index("--repeats") + 1] = "1"
EXPERIMENT_ENV["T10QRres"] = {**EXPERIMENT_ENV["T10QR"], "MOTA_RESUME_LOG": "20261004_052939_498308_MT0-MT23w_llm.json",
                              "MOTA_RESUME_BEFORE_TURN": "708"}
# Grill 10-04 Q3/Q6: evolved-route prompt (the (1+1) loop on the complex floor alone, validator off, DeepSeek task model
# and teacher; scratch/launch_round30.ps1 writes the best prompt to seed_prompts/gepa_study/) evaluated at N=5.
EXPERIMENTS["ERD"] = ["--floor", "complex", "--preset", "deepseek-v4-flash-think", "--repeats", "5", "--lookahead", "3",
                      "--prompt-file", "seed_prompts/gepa_study/evolved_route_deepseek.txt",
                      "--label", "complex_evolved_route_deepseek-v4-flash"]
EXPERIMENT_ENV["ERD"] = {**_FINAL, "THINKING_MAX_TOKENS": "32768", "LLM_TIMEOUT": "1800"}
# Grill 10-04 pickaxe Q1 (b): can the model complete the MT18 princess chain? Resume 397B design-6 run 1 before turn 708
# with blue-key purchases offered (the chain needs one blue door on MT12); viable if a run reaches MT19.
for _code, _preset, _reps, _tag in (("PXD", "deepseek-v4-flash-think", "3", "deepseek-v4-flash"),
                                    ("PXQ", "qwen3.5-397b", "1", "qwen3.5-397b")):
    _args = [a if a != "tower_qwen3.5-397b_final10_resume" else f"tower_{_tag}_final10_resume_blue"
             for a in EXPERIMENTS["T10QRres"]]
    _args[_args.index("--preset") + 1] = _preset
    _args[_args.index("--repeats") + 1] = _reps
    _args[_args.index("--max-turns") + 1] = "860"
    EXPERIMENTS[_code] = _args
    EXPERIMENT_ENV[_code] = {**EXPERIMENT_ENV["T10QRres"], "MOTA_BLUE_KEY_PURCHASE": "1",
                             **({"LLM_TIMEOUT": "1800"} if _code == "PXD" else {})}
# Run 3 of 397B design 6 as a fresh process on the corrected engine (runs 1-2 started before the hidden staircases).
EXPERIMENTS["T10QR3"] = EXPERIMENTS["T10QR"][:EXPERIMENTS["T10QR"].index("--repeats") + 1] + ["1"] + \
    EXPERIMENTS["T10QR"][EXPERIMENTS["T10QR"].index("--repeats") + 2:] + ["--append"]
EXPERIMENT_ENV["T10QR3"] = dict(EXPERIMENT_ENV["T10QR"])
# Design 6 frozen (user 10-03) with the missing-key fact in the way-up line; the earlier design-6 runs are superseded.
EXPERIMENT_ENV["T10DR"]["MOTA_AFTER_BATTLE"] = "1"
# 2026-10-05: tower_basic.txt is now the design-7 prompt; design-6 cells keep the frozen text.
for _c in [c for c in EXPERIMENTS if c.startswith("T10") or c in ("PXD", "PXQ")]:
    if "--prompt-file" not in EXPERIMENTS[_c]:
        EXPERIMENTS[_c] = EXPERIMENTS[_c] + ["--prompt-file", "tower_basic_design6.txt"]
# DESIGN 7 (user 2026-10-05) = design 6 + QUANTITY for shop purchases + the [vampire] ability (prompt line and fight
# tag) + way and missing keys for event items and seal guards (Ice Pickaxe, last White Warrior); prompt tower_basic.txt.
_D7 = {"MOTA_BUY_QUANTITY": "1", "MOTA_VAMPIRE_TAG": "1", "MOTA_EVENT_WAY": "1"}
for _code, _src, _preset in (("T11DR", "T10DR", "deepseek-v4-flash-think"), ("T11QR", "T10QR", "qwen3.5-397b"),
                             ("T11Q6", "T10Q6", "qwen3.6-35b"), ("T11MM", "T10MM", "mistral-medium-3.5")):
    _args = [a.replace("_final10_", "_final11_") for a in EXPERIMENTS[_src]]
    _i = _args.index("--prompt-file")
    EXPERIMENTS[_code] = _args[:_i] + _args[_i + 2:]
    EXPERIMENT_ENV[_code] = {**EXPERIMENT_ENV[_src], "MOTA_AFTER_BATTLE": "1", **_D7}
# Princess-chain test on design 7 (user 10-05: "the current step should try to get the pickaxe in any case"): resume
# before turn 708 with blue keys for sale and the design-7 event lines that name the blue door before the pickaxe.
for _code, _src in (("PXD7", "PXD"), ("PXQ7", "PXQ")):
    _args = [a.replace("_final10_resume_blue", "_final11_resume_blue") for a in EXPERIMENTS[_src]]
    _i = _args.index("--prompt-file")
    EXPERIMENTS[_code] = _args[:_i] + _args[_i + 2:]
    EXPERIMENT_ENV[_code] = {**EXPERIMENT_ENV[_src], **_D7}
# DESIGN 7b (grill 10-05 Q1 b): design 7 with blue keys for sale as in the real game (MT5 Key Seller, 50 g); yellow keys
# stay hidden. The princess chain needs one blue key; with it, 397B won the resumed run.
EXPERIMENTS["T11DB"] = [a.replace("_final11_", "_final11b_") for a in EXPERIMENTS["T11DR"]]
EXPERIMENT_ENV["T11DB"] = {**EXPERIMENT_ENV["T11DR"], "MOTA_BLUE_KEY_PURCHASE": "1"}


def other_api_runs_alive() -> list[str]:
    """Command lines of other reliability/matrix python processes (Windows: WMI via PowerShell)
    plus any running API job in the dashboard job registry (logs/jobs/)."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -match 'run_reliability|run_model_matrix' -and $_.ProcessId -ne "
          f"{__import__('os').getpid()} }} | ForEach-Object {{ $_.CommandLine }}")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        out = ""
    alive = [l.strip() for l in out.splitlines() if l.strip() and "run_followups" not in l]
    for m in J.api_busy():
        alive.append(f"[job {m['job_id']}] {m.get('label')} (pid {m.get('pid')})")
    return alive


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=sorted(EXPERIMENTS), default=["S1", "C1", "T1"],
                    help="experiments to run, in the given order (default: the essential set)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--poll", type=int, default=120, help="seconds between checks while waiting")
    ap.add_argument("--wait", action="store_true",
                    help="wait for other API jobs to finish first (default only when MOTA_EXCLUSIVE_API=1)")
    args = ap.parse_args()

    # Queued manifests make the pending experiments visible in the dashboard's Live view.
    queued: dict[str, J.Job] = {}
    if not args.dry_run:
        for name in args.only:
            a = EXPERIMENTS[name]
            def _opt(flag):
                return a[a.index(flag) + 1] if flag in a else None
            queued[name] = J.Job.start(
                "tower" if "--tower" in a else "reliability", _opt("--label") or name, uses_api=True, source="cli",
                status="queued", floor=_opt("--floor"), start=_opt("--start"), end=_opt("--end"),
                preset=_opt("--preset"), mode=_opt("--mode") or "reactive",
                condition={"experiment": name, "args": a, "env": EXPERIMENT_ENV.get(name, {}), "queue": "run_followups"},
            )

    waited = 0
    wait_for_idle = args.wait or J.exclusive_api()
    while not args.dry_run and wait_for_idle:
        alive = other_api_runs_alive()
        if not alive:
            break
        if waited % 1800 == 0:
            print(f"[{time.strftime('%H:%M')}] waiting for {len(alive)} API run(s) to finish:", flush=True)
            for cmd in alive:
                print(f"    {cmd[-120:]}", flush=True)
        time.sleep(args.poll)
        waited += args.poll
    if waited:
        print(f"[{time.strftime('%H:%M')}] API free after {waited / 60:.0f} min", flush=True)

    t0 = time.time()
    for name in args.only:
        cmd = [sys.executable, str(ROOT / "run_reliability.py"), *EXPERIMENTS[name]]
        if name in queued:
            cmd += ["--job-id", queued[name].job_id]
        print(f"\n=== {name}: {' '.join(cmd[1:])}", flush=True)
        if args.dry_run:
            continue
        env = {**__import__('os').environ, **EXPERIMENT_ENV.get(name, {})}
        rc = subprocess.run(cmd, cwd=ROOT, check=False, env=env).returncode
        job = J.Job.load(queued[name].job_id) if name in queued else None
        if job is not None and job.m.get("status") in ("queued", "running"):
            job.finish("done" if rc == 0 else "failed", error=None if rc == 0 else f"exit code {rc}")
    if not args.dry_run:
        subprocess.run([sys.executable, str(ROOT / "run_reliability.py"), "--summary"], cwd=ROOT, check=False)
        print(f"\nfollow-ups done in {(time.time() - t0) / 60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
