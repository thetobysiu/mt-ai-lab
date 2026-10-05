"""Data figures 6.1-6.4 of the thesis, plotted from the stored result files -> thesis/graphs/6.{1,2,3,4}.png."""
import glob
import json
import math
import pathlib
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]
REL = ROOT / "results" / "reliability"
OUT = ROOT / "docs" / "figures"
BLUE, BLUE_E = "#AFC8F0", "#3E6199"
GREEN, GREEN_E = "#B5E0B0", "#3F7F3A"
YELLOW, YELLOW_E = "#F5DC9A", "#A07C12"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "savefig.dpi": 300, "savefig.bbox": "tight"})


def cell(label):
    runs = json.load(open(REL / f"{label}.json", encoding="utf-8"))["runs"]
    return sum(r["success"] for r in runs), len(runs), sum(r.get("llm_calls", 0) for r in runs) / len(runs)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def fig_6_1():
    rows = [
        ("1  earlier prompt,\n   strategic override", "legacy_strategic_control", None),
        ("2  single-floor prompt,\n   mechanical assists", "basic_mechanical_override", None),
        ("3  + alternative-route tag", "basic_mech_altroute", None),
        ("4  + stat-route and\n   fight-order lines", "basic_order_aware", "basic_order_aware"),
        ("5  + counts, potion-free cost,\n   guard, required budget", "basic_d1d4", "basic_d1d4"),
        ("6  + key budget and key lines", "basic_k1k2", "basic_k1k2_16k"),
        ("7  + no conversation history", "basic_k1k2_hist0", "basic_k1k2_16k_hist0"),
        ("8  + two-sided order line,\n   key line on fights", "final_la3", "final_la3"),
        ("9  + 40 % guard (final)", "final2_la3", "final2_la3"),
    ]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    y = list(range(len(rows)))[::-1]
    for i, (name, a, b) in enumerate(rows):
        for lab, off, fc, ec, model in ((a, 0.18, BLUE, BLUE_E, "qwen3.5-397b"), (b, -0.18, GREEN, GREEN_E, "qwen3.6-35b")):
            if lab is None:
                continue
            k, n, _ = cell(f"simple_{model}_{lab}")
            lo, hi = wilson(k, n)
            yy = y[i] + off
            ax.barh(yy, k / n, height=0.34, color=fc, edgecolor=ec, linewidth=0.8)
            ax.errorbar(k / n, yy, xerr=[[k / n - lo], [hi - k / n]], fmt="none", ecolor="#444", elinewidth=0.8, capsize=2)
            ax.text(1.02, yy, f"{k}/{n}", va="center", fontsize=8.5, color=ec)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8.5)
    ax.set_xlim(0, 1.12)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("Success rate on the simple floor (bars: k/N; whiskers: Wilson 95 % interval)")
    ax.legend(handles=[Patch(facecolor=BLUE, edgecolor=BLUE_E, label="Qwen3.5-397B"),
                       Patch(facecolor=GREEN, edgecolor=GREEN_E, label="Qwen3.6-35B")],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=8.5)
    fig.savefig(OUT / "6.1.png")
    plt.close(fig)


def fig_6_2():
    """Exact state value (highest final HP still reachable) per turn of every complex-floor episode (Table B.4)."""
    runs = {}
    for p in sorted(glob.glob(str(REL / "complex_value_trace_*.json"))):
        runs.update(json.load(open(p, encoding="utf-8")))
    unw = -12
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.6), sharey=True)
    for ax, route, title in ((axes[0], False, "Single-floor prompt"), (axes[1], True, "Solver-route prompt")):
        eps = [r for r in runs.values() if r["label"].startswith("complex_route_") == route]
        losses = {}  # losing action -> turns
        for r in eps:
            win = bool(r["success"])
            xs, ys = [0], [r["v_start"]]
            for t in r["turns"]:
                if "v_before" not in t or "Boss" in t["action"]:
                    continue  # a won boss fight has no successor state to value
                if t["v_after"] is None:
                    xs.append(t["turn"])
                    ys.append(unw)
                    if t["v_before"] is not None:
                        losses.setdefault(re.sub(r" dmg=\d+", "", t["action"].replace("Fight ", "")), []).append(t["turn"])
                    break
                xs.append(t["turn"])
                ys.append(t["v_after"])
            ax.step(xs, ys, where="post", color=GREEN_E if win else "#B03A2E", alpha=0.55 if win else 0.3,
                    lw=1.3 if win else 1.0, zorder=3 if win else 2)
        n_win = sum(bool(r["success"]) for r in eps)
        ax.axhline(unw, color="#999", lw=0.6, ls=":")
        ax.axhline(68, color="#999", lw=0.6, ls="--")
        if losses:
            act, turns = max(losses.items(), key=lambda kv: len(kv[1]))
            lo, hi = min(turns), max(turns)
            when = f"turn {lo}" if lo == hi else f"turns {lo}–{hi}"
            ax.annotate(f"{len(turns)} lost at {when}:\n{act}", xy=(lo, unw), xytext=(0.42 if route else 0.04, 0.2),
                        textcoords="axes fraction", fontsize=7.5, zorder=5, bbox=dict(fc="white", ec="none", alpha=0.85),
                        arrowprops=dict(arrowstyle="->", color="#555", lw=0.8))
        ax.set_title(f"{title} ({n_win} of {len(eps)} won)", fontsize=10)
        ax.set_xlabel("Turn")
    axes[0].set_yticks([unw, 0, 22, 42, 68])
    axes[0].set_yticklabels(["boss\nunwinnable", "0", "22", "42", "68 (optimum)"], fontsize=8)
    axes[0].set_ylabel("State value (best final HP still reachable)")
    axes[0].set_ylim(unw - 6, 76)
    fig.tight_layout()
    fig.savefig(OUT / "6.2.png")
    plt.close(fig)


def fig_6_3():
    d = json.load(open(ROOT / "results" / "gepa_study" / "gs3_dsbare_confirm.json", encoding="utf-8"))
    floors = [f"gen{i:02d}" for i in range(3, 16)]
    kills = {f: {"core": 0, "gepa": 0} for f in floors}
    for e in d["episodes"]:
        kills[e["floor"]][e["prompt"]] += e["success"]
    selected = {"gen10", "gen12", "gen13", "gen14"}
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    for x, f in enumerate(floors):
        if f in selected:
            ax.axvspan(x - 0.45, x + 0.45, color="#EEEEEE", zorder=0)
        a, b = kills[f]["core"], kills[f]["gepa"]
        if a != b:
            ax.annotate("", xy=(x, b), xytext=(x, a), arrowprops=dict(arrowstyle="->", color="#555", lw=1.1), zorder=1)
        ax.scatter(x - (0.12 if a == b else 0), a, s=70, marker="o", color=BLUE, edgecolor=BLUE_E, zorder=2)
        ax.scatter(x + (0.12 if a == b else 0), b, s=70, marker="s", color=YELLOW, edgecolor=YELLOW_E, zorder=2)
    ax.set_xticks(range(len(floors)))
    ax.set_xticklabels(floors, fontsize=8.5)
    ax.set_yticks([0, 1, 2, 3])
    ax.set_ylim(-0.4, 3.4)
    ax.set_ylabel("Kills out of 3")
    ax.set_xlabel("Generated floor (grey: floors of the trial that selected the rewrite)")
    ax.scatter([], [], s=50, marker="o", color=BLUE, edgecolor=BLUE_E, label="rules-only prompt")
    ax.scatter([], [], s=50, marker="s", color=YELLOW, edgecolor=YELLOW_E, label="evolved prompt")
    ax.legend(loc="lower left", frameon=False, fontsize=8.5, ncol=2, bbox_to_anchor=(0, 1.0))
    fig.savefig(OUT / "6.3.png")
    plt.close(fig)


def fig_6_4():
    modes = [("reactive", "R"), ("plan2", "C2"), ("plan3", "C3"), ("plan5", "C5"),
             ("planf", "LP\nWF"), ("maxsteps", "LP\nMS"), ("oneshot_plan", "SC\nWF"), ("maxsteps_once", "SC\nMS")]
    panels = [
        ("Simple floor", [("Qwen3.5-397B", "simple_qwen3.5-397b_final2_", BLUE, BLUE_E),
                          ("DeepSeek-V4-Flash", "simple_deepseek-v4-flash_final2_", GREEN, GREEN_E),
                          ("Qwen3.8-27B (T = 0.6)", "simple_qwen3.8-27b_final2_", YELLOW, YELLOW_E)]),
        ("Complex floor, solver-route prompt", [
            ("DeepSeek-V4-Flash", "complex_deepseek-v4-flash_survival_final2_", GREEN, GREEN_E),
            ("Qwen3.8-27B (T = 0.6)", "complex_qwen3.8-27b_survival_final2_", YELLOW, YELLOW_E)]),
    ]

    def labels(prefix, suffix):
        """Result files of one bar; DeepSeek's reactive bar pools its two reasoning caps (16K and 32K)."""
        if "27b" in prefix:
            if suffix in ("planf", "oneshot_plan") or (suffix == "maxsteps_once" and prefix.startswith("simple")):
                return []  # not run / no parsable plan in any episode
            return [prefix + ("reactive_t32" if suffix == "reactive" else suffix) + "_t06"]
        if suffix == "reactive":
            return [prefix + "la3"] if "397b" in prefix else [prefix + "reactive", prefix + "reactive_t32"]
        return [prefix + suffix]

    def pooled(labs):
        cells = [cell(lab) for lab in labs if (REL / f"{lab}.json").exists()]
        if not cells:
            return None
        k, n = sum(c[0] for c in cells), sum(c[1] for c in cells)
        return k, n, sum(c[2] * c[1] for c in cells) / n

    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.8), sharey=True, gridspec_kw={"width_ratios": [8, 6]})
    for ax, (title, series) in zip(axes, panels):
        present = [(s, n) for s, n in modes if any(pooled(labels(p, s)) for _, p, _, _ in series)]
        width = 0.84 / len(series)
        for j, (model, prefix, fc, ec) in enumerate(series):
            for x, (suffix, _) in enumerate(present):
                c = pooled(labels(prefix, suffix))
                if c is None:
                    continue
                k, n, calls = c
                xx = x + (j - (len(series) - 1) / 2) * width
                ax.bar(xx, max(k / n, 0.006), width=width * 0.92, color=fc, edgecolor=ec, linewidth=0.8)
                ax.text(xx, k / n + 0.02, f"{k}/{n} ({calls:.1f})", ha="center", va="bottom", fontsize=6,
                        color=ec, rotation=90)
        ax.set_xticks(range(len(present)))
        ax.set_xticklabels([n for _, n in present], fontsize=7)
        ax.set_title(title, fontsize=10)
    handles = [Patch(facecolor=fc, edgecolor=ec, label=m) for m, _, fc, ec in panels[0][1]]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False, fontsize=8)
    axes[0].set_ylabel("Success rate")
    axes[0].set_ylim(0, 1.25)
    axes[0].set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    fig.tight_layout()
    fig.savefig(OUT / "6.4.png")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1:] or ["6.1", "6.2", "6.3", "6.4"]
    for name in only:
        globals()["fig_" + name.replace(".", "_")]()
    print("written:", sorted(p.name for p in OUT.glob("6.*.png")))
