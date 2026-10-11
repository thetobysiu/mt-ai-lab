"""Index of the thesis results: which result files stand behind each table, figure and paragraph of Chapter 6.

The index follows Table D.4 of the thesis (Appendix D, "Result files") row by row; Table D.5 supplies the tower
labels. It writes

  results/thesis_index.json            rows of Table D.4 with their result files and aggregates (read by the dashboard)
  results/reliability/_thesis_labels.json   flat list of thesis labels (the "thesis" filter on the Logs page)
  docs/results.md                      the same index as a readable page

    python analysis/thesis_index.py --appendix path/to/11_appendix_d_configuration.md
    python analysis/thesis_index.py            # only re-render docs/results.md from results/thesis_index.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
INDEX = RESULTS / "thesis_index.json"
DOC = ROOT / "docs" / "results.md"
MODELS = r"(?:qwen3\.5-397b|qwen3\.6-35b|qwen3\.8-27b|deepseek-v4-flash|mistral-medium-3\.5)"
TOKENS = {"<m>": MODELS, "<i>": r"\d+", "<d>": r"\d", "<k>": r"\d+", "<floor>": r"(?:simple|complex_route|complex|hand0\d)"}


def table(text: str, caption: str) -> list[list[str]]:
    part = text.split(f"**{caption}:**", 1)[1].split("\n\n", 1)[1]
    rows = []
    for line in part.splitlines():
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if not re.fullmatch(r"[-: ]*", "".join(cells)):
            rows.append(cells)
    return rows[1:]


def to_regex(name: str, tower_labels: list[str]) -> str:
    rx = re.escape(name)
    for tok, sub in TOKENS.items():
        rx = rx.replace(re.escape(tok), sub)
    rx = rx.replace(re.escape("<label>"), "(?:" + "|".join(map(re.escape, tower_labels)) + ")")
    rx = rx.replace(re.escape("*"), ".*").replace(re.escape("[a-e]"), "[a-e]")
    return rx


def candidates(name: str, previous: list[str]) -> list[str]:
    """`…X` abbreviates a sibling of an earlier name in the same cell."""
    if not name.startswith("…"):
        return [name]
    suffix = name[1:]
    out = []
    for p in previous:
        p = re.sub(r"\.json$", "", p)
        out.append(p + suffix)
        out += [p[:m.start()] + suffix for m in re.finditer("_", p)]
    return out


def all_results() -> dict[str, Path]:
    files = {}
    for p in RESULTS.rglob("*.json"):
        if p.name in ("thesis_index.json", "_thesis_labels.json"):
            continue
        files[p.relative_to(ROOT).as_posix()] = p
    return files


def summarise(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT).as_posix()
    if isinstance(d, dict) and "aggregate" in d and "runs" in d:
        a = d["aggregate"] or {}
        return {"path": rel, "kind": "reliability", "label": d.get("label", path.stem), "n": a.get("n"),
                "successes": a.get("successes"), "ci": a.get("success_ci95"), "hp_ratio": a.get("hp_ratio_mean"),
                "died": a.get("died"), "floors_max": a.get("floors_reached_max"),
                "logs": sum(1 for r in d["runs"] if r.get("run_log"))}
    if isinstance(d, dict) and isinstance(d.get("episodes"), list):
        groups: dict[str, list[int]] = {}
        for e in d["episodes"]:
            key = f"{e.get('prompt')} · {e.get('split')}"
            g = groups.setdefault(key, [0, 0])
            g[0] += bool(e.get("success"))
            g[1] += 1
        return {"path": rel, "kind": "gepa_study", "label": d.get("label", path.stem),
                "groups": [{"group": k, "successes": v[0], "n": v[1]} for k, v in sorted(groups.items())],
                "logs": sum(1 for e in d["episodes"] if e.get("run_log"))}
    return {"path": rel, "kind": "other", "label": path.stem}


def build(appendix: Path) -> dict:
    text = appendix.read_text(encoding="utf-8")
    f5 = table(text, "Table D.5")
    tower_labels = sorted({m for row in f5 for m in re.findall(r"`([^`]+)`", row[1])}, key=len, reverse=True)
    design_label = {row[0]: re.findall(r"`([^`]+)`", row[1])[0] for row in f5 if re.findall(r"`([^`]+)`", row[1])}
    files = all_results()
    rows, unmatched = [], []
    for result, cell in table(text, "Table D.4"):
        names = re.findall(r"`([^`]+)`", cell)
        m = re.fullmatch(r"the (\S+)-observation rows of Table 6\.13", cell)
        if m and m.group(1) in design_label:
            names = [f"tower_<m>_{design_label[m.group(1)]}_reactive"]
        matched: dict[str, Path] = {}
        previous: list[str] = []
        prefix = None
        for name in names:
            if (name.endswith((".py", ".ps1", ".txt", ".md")) or name.startswith(("analysis/", "scripts/", "MOTA_"))
                    or name in tower_labels or re.match(r"^\d{8}_\d{6}_\d+_", name) or name in ("map_enum", "_t06", "_t10")):
                continue
            if name.endswith("_") and "<" in name:
                prefix = name
                continue
            cands = candidates(name, previous) + ([prefix + name] if prefix and not name.startswith("…") else [])
            hit = False
            for cand in cands:
                stem = cand[len("results/"):] if cand.startswith("results/") else cand
                stem = re.sub(r"\.json$", "", stem)
                rx = re.compile(r"(?:^|/)" + to_regex(stem, tower_labels) + r"(?:\.json)?$")
                for rel, p in files.items():
                    tail = rel[len("results/"):-len(".json")]
                    if rx.search(tail) and not re.search(r"glm-5\.3-flash", tail):
                        matched[rel] = p
                        hit = True
            if not name.startswith("…"):
                previous.append(name)
            if not hit:
                unmatched.append(f"{result}: {name}")
        rows.append({"result": result, "files_cell": cell, "matched": matched})
    # temperature rows name the suffixes `_t06`/`_t10` of cells reported elsewhere: add those variants
    reported = {Path(rel).stem for r in rows for rel in r["matched"]}
    for r in rows:
        if "`_t06`" in r["files_cell"]:
            for rel, p in files.items():
                base = re.sub(r"_t(06|10)$", "", p.stem)
                if base != p.stem and base in reported and "glm-5.3-flash" not in rel:
                    r["matched"][rel] = p
    for r in rows:
        r["items"] = [summarise(p) for _, p in sorted(r.pop("matched").items())]
    return {"source": "Thesis, Appendix D, Table D.4 (result files) and Table D.5 (tower labels)", "rows": rows,
            "unmatched": unmatched}


def fmt(it: dict) -> str:
    if it["kind"] == "reliability":
        k = f"{it['successes']}/{it['n']}" if it.get("n") is not None else "—"
        ci = f" [{it['ci'][0]:.2f}, {it['ci'][1]:.2f}]" if it.get("ci") else ""
        extra = []
        if it.get("hp_ratio") is not None:
            extra.append(f"HP/opt {it['hp_ratio']:.2f}")
        if it.get("died"):
            extra.append(f"{it['died']} died")
        if it.get("floors_max"):
            extra.append(f"highest floor MT{it['floors_max']}")
        return f"{k}{ci}" + (f" ({', '.join(extra)})" if extra else "")
    if it["kind"] == "gepa_study":
        return "; ".join(f"{g['group']} {g['successes']}/{g['n']}" for g in it["groups"])
    return "—"


def render(index: dict) -> str:
    out = ["# Results behind the thesis", "",
           "This page lists, for every table, figure and paragraph of Chapter 6, the result files in `results/` that",
           "it reports, following Table D.4 of the thesis. Successes are *k/N* episodes with the Wilson 95 % interval;",
           "HP/opt is the final HP relative to the exact optimum, averaged over successful episodes. Every episode names",
           "its run log; download the logs (`python scripts/fetch_run_logs.py`) to replay them in the platform",
           "(Experiments → Thesis results).", "",
           "Generated by `python analysis/thesis_index.py`; do not edit by hand.", ""]
    for row in index["rows"]:
        out.append(f"## {row['result']}")
        out.append("")
        if not row["items"]:
            out.append(f"No result file in `results/` (source: {row['files_cell']}).")
            out.append("")
            continue
        out.append("| Result file | Episodes | Successes |")
        out.append("|---|---:|---|")
        for it in row["items"]:
            out.append(f"| `{it['path']}` | {it.get('logs', '—')} | {fmt(it)} |")
        out.append("")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--appendix", type=Path, help="11_appendix_d_configuration.md of the thesis")
    a = ap.parse_args()
    if a.appendix:
        index = build(a.appendix)
        INDEX.write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
        labels = sorted({it["label"] for r in index["rows"] for it in r["items"] if it["kind"] == "reliability"})
        (RESULTS / "reliability" / "_thesis_labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
        n = sum(len(r["items"]) for r in index["rows"])
        print(f"{len(index['rows'])} rows, {n} result files, {len(labels)} thesis labels; unmatched names: {len(index['unmatched'])}")
        for u in index["unmatched"]:
            print("  unmatched:", u)
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(render(index), encoding="utf-8")
    print("wrote", DOC.relative_to(ROOT))


if __name__ == "__main__":
    main()
