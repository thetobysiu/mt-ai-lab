"""The thesis experiments as a runnable catalog (dashboard Experiments → Thesis experiments).

Each entry names a result file in results/reliability (the thesis's own run) and how to re-run it:
either registry codes of scripts/run_followups.py (the exact CLI arguments and env of the thesis run) or a
script command line (GEPA study). A re-run always writes to a new label (``rerun_<stamp>_<label>``), never
to the thesis result.
"""
from __future__ import annotations

# group, thesis section, id, title, what it shows, then either registry `codes` or a `script` command line.
CATALOG: list[dict] = [
    # --- RQ1: main results ---------------------------------------------------------------------------
    {"group": "RQ1 · main results", "section": "Table 6.2", "id": "main-results",
     "title": "Final configuration on the six single floors (Qwen3.5-397B)",
     "what": "Re-run of Table 6.2: simple floor, complex floor with the single-floor and with the solver-route prompt, "
             "hand01 to hand04; N = 5. Other models: codes VD…, VS…, VM… (Appendix F).",
     "codes": ["VQS5", "VQC5", "VQR5", "VQ15", "VQ25", "VQ35", "VQ45"]},
    # --- RQ1: simple floor -----------------------------------------------------------------------------
    {"group": "RQ1 · simple floor", "section": "Section 6.4.1, Table 6.5", "id": "override-census",
     "title": "Strategic override against mechanical assists",
     "what": "Table 6.5, row 1: earlier hand-written prompt with the logged strategic override; row 2: single-floor prompt "
             "with mechanical assists only; Table 6.3: all assists off.",
     "codes": ["R0", "B4", "A2"]},
    {"group": "RQ1 · simple floor", "section": "Section 6.4.4, Table 6.5", "id": "cost-aware-annotation",
     "title": "Two-sided annotations (rows 3 and 4)",
     "what": "Same model, prompt and lookahead depth: the alternative-route tag, then the net stat-route and fight-order lines.",
     "codes": ["B5", "B6", "B7"]},
    {"group": "RQ1 · simple floor", "section": "Table 6.5, row 6", "id": "key-economy",
     "title": "Key budget and per-door key lines", "what": "Qwen3.5-397B, N = 10.", "codes": ["B14"]},
    {"group": "RQ1 · simple floor", "section": "Tables 6.3 and 6.5 (row 9)", "id": "final-stack",
     "title": "Final configuration, earlier run",
     "what": "No conversation history, two-sided fight-order line with the 40 % guard, key line on fights; "
             "lookahead depth 3, N = 10.",
     "codes": ["G1", "G1s"]},
    {"group": "RQ1 · simple floor", "section": "Table 6.3", "id": "depth-curve",
     "title": "Lookahead depth 3 / 2 / 1 / 0", "what": "Qwen3.5-397B on the final configuration.",
     "codes": ["G1", "G2", "G3a", "G3b"]},
    {"group": "RQ1 · simple floor", "section": "Tables 6.3 and 6.4", "id": "map-only",
     "title": "Map-only condition",
     "what": "No action list and no annotations: the model lists its own options from the grid.",
     "codes": ["ME1", "ME1s"]},
    # --- RQ1: other floors -------------------------------------------------------------------------------
    {"group": "RQ1 · other floors", "section": "Section 6.2", "id": "complex-survival",
     "title": "Complex floor, solver-route prompt (earlier runs)",
     "what": "The published solver's route with a survival rule, before the re-run of Table 6.2.",
     "codes": ["CQR", "CR", "DCR"]},
    {"group": "RQ1 · other floors", "section": "Sections 6.2 and 6.4.6", "id": "complex-basic",
     "title": "Complex floor, single-floor prompt (earlier runs)",
     "what": "Final configuration, before the re-run of Table 6.2.", "codes": ["GC", "GCs"]},
    {"group": "RQ1 · other floors", "section": "Section 6.6", "id": "exact-route",
     "title": "Exact-route prompt (68-HP route)",
     "what": "The exact optimal route listed in the prompt (compiled-knowledge condition).", "codes": ["X68S", "X68D"]},
    {"group": "RQ1 · other floors", "section": "Table D.56", "id": "hand-floors",
     "title": "Hand-designed floors hand01 to hand04 (earlier runs)",
     "what": "Final configuration before the re-run of Table 6.2 (Table 6.11 reports the re-run).",
     "codes": ["HD1", "HD2", "HD3", "HD4", "HS1", "HS2", "HS3", "HS4"]},
    {"group": "RQ1 · other floors", "section": "Section 6.7.2, Table 6.12", "id": "gen-floors",
     "title": "Generated floors gen01 to gen05", "what": "Qwen3.5-397B and Qwen3.6-35B, N = 3 each.",
     "codes": ["GEN1", "GEN2", "GEN3", "GEN4", "GEN5", "GEN1s", "GEN2s", "GEN3s", "GEN4s", "GEN5s"]},
    # --- RQ2: prompt optimisation -------------------------------------------------------------------------
    {"group": "RQ2 · prompt optimisation", "section": "Section 6.5.2, Table 6.6", "id": "gepa-study",
     "title": "First prompt-optimisation study, one cell ((1+1) loop)",
     "what": "DeepSeek-V4-Flash, full observation: the (1+1) loop on the simple floor, gen01 and gen02, then the rules-only, "
             "evolved and single-floor prompts on the held-out floors. Other cells: --preset llama-3.1-8b and/or --obs bare.",
     "script": ["scripts/run_gepa_study.py", "--preset", "deepseek-v4-flash", "--obs", "full"]},
    {"group": "RQ2 · prompt optimisation", "section": "Table 6.3", "id": "gepa-refs",
     "title": "Reference runs without optimisation",
     "what": "Qwen3.5-397B, rules-only prompt, full against bare observation, simple floor, N = 3.",
     "script": ["scripts/run_gepa_study.py", "--preset", "qwen3.5-397b", "--obs", "full", "--no-gepa", "--prompts", "core",
                "--train", "simple", "--test", "none", "--repeat", "3", "--thinking-max-tokens", "32768"]},
    # --- RQ3: planning horizon -----------------------------------------------------------------------------
    {"group": "RQ3 · planning horizon", "section": "Section 6.6, Table 6.9", "id": "plan-397b",
     "title": "Qwen3.5-397B, simple floor: commit-2 / 3 / 5, long plan, single-call plan",
     "what": "Reactive arm: the final configuration (Table 6.3). The long and single-call plans use the whole-floor wording.",
     "codes": ["P2", "P3", "P5", "PF", "PO"]},
    {"group": "RQ3 · planning horizon", "section": "Section 6.6, Table 6.9", "id": "plan-deepseek-simple",
     "title": "DeepSeek-V4-Flash, simple floor: reactive and all plan modes", "what": "Each mode against its own reactive arm.",
     "codes": ["DSR", "DSP2", "DSP3", "DSP5", "DSPF", "DSPO"]},
    {"group": "RQ3 · planning horizon", "section": "Section 6.6, Table 6.9", "id": "plan-deepseek-complex",
     "title": "DeepSeek-V4-Flash, complex floor, solver-route prompt: reactive and plan modes",
     "what": "Engine overrides off, annotations on.", "codes": ["DCR", "DCP2", "DCP3", "DCP5", "DCPO"]},
    {"group": "RQ3 · planning horizon", "section": "Section 6.6, Table 6.9", "id": "plan-maxsteps",
     "title": "Long plans: as many actions as the model can",
     "what": "Re-planned and single-call; DeepSeek-V4-Flash on the simple and complex floors, Qwen3.5-397B on the simple floor.",
     "codes": ["DSMO", "DCMO", "DSM", "PMO", "PM"]},
    {"group": "RQ3 · planning horizon", "section": "Table 6.9, tower design 5", "id": "plan-tower",
     "title": "Tower: reactive against commit-3 and commit-5",
     "what": "Development version of design 5, three runs per cell.", "codes": ["T7DR", "T7QR", "T7D3", "T7D5", "T7Q3"]},
    # --- Tower -------------------------------------------------------------------------------------------------
    {"group": "Tower", "section": "Table 6.13", "id": "tower-final",
     "title": "Tower from MT0, design 7 (final design)", "what": "Three runs per model.",
     "codes": ["T11QR", "T11DR", "T11Q6", "T11MM"]},
    {"group": "Tower", "section": "Section 6.7.3", "id": "tower-resume",
     "title": "Design-6 run resumed on MT18 with blue keys for sale", "what": "Qwen3.5-397B; reached the normal ending.",
     "codes": ["PXQ"]},
]


def registry():
    """(EXPERIMENTS, EXPERIMENT_ENV) of scripts/run_followups.py, imported without running it."""
    import importlib.util
    import sys
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_followups.py"
    spec = importlib.util.spec_from_file_location("_mota_followups_registry", path)
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    try:
        sys.argv = [str(path)]
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod.EXPERIMENTS, mod.EXPERIMENT_ENV


def _arg(args: list[str], flag: str, default=None):
    return args[args.index(flag) + 1] if flag in args else default


def describe(code: str, experiments: dict, env: dict) -> dict:
    a = experiments[code]
    e = env.get(code, {})
    tower = "--tower" in a
    return {
        "code": code, "label": _arg(a, "--label"),
        "scenario": f"tower {_arg(a, '--start', 'MT0')}→{_arg(a, '--end', 'MT23w')}" if tower else _arg(a, "--floor"),
        "preset": _arg(a, "--preset"), "repeats": int(_arg(a, "--repeats", "1")), "lookahead": int(_arg(a, "--lookahead", "3")),
        "prompt_file": _arg(a, "--prompt-file"), "overrides_off": "--disable-overrides" in a,
        "checkpoint": _arg(a, "--checkpoint"), "mode": _arg(a, "--mode", "reactive"),
        "plan_steps": int(e.get("MOTA_PLAN_STEPS", "1")), "one_shot": e.get("MOTA_PLAN_NO_REPLAN") == "1",
        "final_stack": e.get("CONVERSATION_HISTORY_TURNS") == "0" and e.get("MOTA_ORDER_TWO_SIDED") == "1",
        "flags": _flags(e),
        "env": dict(e), "args": list(a),
    }


def _flags(e: dict) -> list[str]:
    """Human-readable engine flags that change the condition (the final stack and plan keys are shown separately)."""
    out = []
    if e.get("MOTA_LEGACY_SEEDS") == "1":
        out.append("legacy seed prompt")
    if e.get("MOTA_STRATEGIC_OVERRIDES") == "1":
        out.append("strategic overrides on")
    if "MOTA_SUPPRESS_HINTS" in e:
        out.append("hints hidden" if e["MOTA_SUPPRESS_HINTS"] == "1" else "hints shown")
    if e.get("MOTA_COMPACT_PROMPT") == "1":
        out.append("compact prompt")
    if e.get("MOTA_LLM_MEMORY") == "1":
        out.append("LLM memory")
    if e.get("MOTA_BARE_OBS") == "1":
        out.append("bare observation")
    if "THINKING_MAX_TOKENS" in e:
        out.append(f"{int(e['THINKING_MAX_TOKENS']) // 1024}K thinking")
    return out
