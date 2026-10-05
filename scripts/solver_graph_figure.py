"""Figure: the exact solver's node graph for a single floor (thesis chapters_v2 §4.5).

    python scripts/solver_graph_figure.py [hand01] [--out docs/images/fig_solver_graph_hand01.png]

Nodes and edges follow tools/java_bfs/Graph.buildMap/isLinked: every key, gem, potion, door, monster and the
boss is a node, the hero's start is node 0, and two nodes are linked when a 4-connected path over empty floor
joins them. Nodes are drawn at their map positions over the grid; merging of adjacent items (mergeNode) is not
applied, so each tile of the map appears as its own node.
"""
from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

KIND = {21: ("k", "key"), 22: ("K", "key"), 23: ("R", "key"), 27: ("a", "gem"), 28: ("d", "gem"), 29: ("g", "gem"),
        31: ("p", "potion"), 32: ("P", "potion"), 81: ("Y", "door"), 82: ("B", "door"), 83: ("R", "door")}
COLOUR = {"hero": "#f59e0b", "boss": "#7f1d1d", "monster": "#dc2626", "door": "#a16207", "key": "#ca8a04",
          "gem": "#2563eb", "potion": "#db2777"}


def load(path: Path) -> tuple[list[list[int]], tuple[int, int]]:
    lines = [l for l in path.read_text(encoding="utf-8").splitlines()]
    w, h = map(int, lines[1].split())
    grid = [list(map(int, lines[3 + y].split())) for y in range(h)]
    hero = lines[-1].split() if lines[-1].strip() else lines[-2].split()
    return grid, (int(hero[-1]), int(hero[-2]))  # hero line ends with "row col" -> (x, y)


def nodes_of(grid, hero):
    out = [("hero", "@", hero)]
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if v == 299:
                out.append(("boss", "Boss", (x, y)))
            elif v >= 201:
                out.append(("monster", str(v - 200), (x, y)))
            elif v in KIND:
                glyph, kind = KIND[v]
                out.append((kind, glyph, (x, y)))
    return out


def linked(grid, a, b) -> bool:
    """Graph.isLinked: BFS from a over empty floor (0); reaching b's tile (adjacent) counts."""
    h, w = len(grid), len(grid[0])
    seen, q = {a}, deque([a])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if (nx, ny) == b:
                return True
            if (nx, ny) in seen or grid[ny][nx] != 0:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("floor", nargs="?", default="hand01")
    ap.add_argument("--out", default=str(ROOT / "docs" / "images" / "fig_solver_graph_hand01.png"))
    a = ap.parse_args()
    p = Path(a.floor) if Path(a.floor).exists() else ROOT / "data" / "floors" / "hand" / f"{a.floor}.txt"
    grid, hero = load(p)
    grid[hero[1]][hero[0]] = 0
    ns = nodes_of(grid, hero)
    edges = [(i, j) for i in range(len(ns)) for j in range(i + 1, len(ns)) if linked(grid, ns[i][2], ns[j][2])]

    cell, pad = 64, 40
    h, w = len(grid), len(grid[0])
    img = Image.new("RGB", (w * cell + 2 * pad, h * cell + 2 * pad + 70), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arialbd.ttf", 20)
        small = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = small = ImageFont.load_default()
    c = lambda xy: (pad + xy[0] * cell + cell // 2, pad + xy[1] * cell + cell // 2)
    for y in range(h):
        for x in range(w):
            box = [pad + x * cell, pad + y * cell, pad + (x + 1) * cell, pad + (y + 1) * cell]
            d.rectangle(box, fill="#9ca3af" if grid[y][x] == 1 else "#f3f4f6", outline="#e5e7eb")
    for x in range(w):
        d.text((pad + x * cell + cell // 2 - 5, 12), str(x), fill="#6b7280", font=small)
    for y in range(h):
        d.text((12, pad + y * cell + cell // 2 - 9), str(y), fill="#6b7280", font=small)
    for i, j in edges:
        d.line([c(ns[i][2]), c(ns[j][2])], fill="#111827", width=2)
    r = cell // 3
    for kind, glyph, xy in ns:
        cx, cy = c(xy)
        shape = [cx - r, cy - r, cx + r, cy + r]
        (d.rectangle if kind == "door" else d.ellipse)(shape, fill=COLOUR[kind], outline="black", width=2)
        tw = d.textlength(glyph, font=font)
        d.text((cx - tw / 2, cy - 12), glyph, fill="white", font=font)
    legend = [("hero", "@ hero"), ("monster", "1-6 monster"), ("boss", "boss"), ("door", "Y/B door"),
              ("key", "k/K key"), ("gem", "a/d gem"), ("potion", "p potion")]
    lx, ly = pad, h * cell + 2 * pad + 10
    for kind, text in legend:
        d.ellipse([lx, ly, lx + 22, ly + 22], fill=COLOUR[kind], outline="black")
        d.text((lx + 28, ly + 1), text, fill="black", font=small)
        lx += 28 + int(d.textlength(text, font=small)) + 24
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out)
    print(f"{p.stem}: {len(ns)} nodes, {len(edges)} edges -> {a.out}")


if __name__ == "__main__":
    main()
