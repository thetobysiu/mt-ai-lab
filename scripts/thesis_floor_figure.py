"""Render single floors with the original game sprites for the thesis.

    python scripts/thesis_floor_figure.py   ->  docs/figures/2.4.png (simple floor rows 0-5, the four first choices),
        4.1.png (full simple floor, optimal route numbered), B.1.png (complex floor), B.2.png (hand01, first decision)
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mota.optimizer import evaluator as ev  # noqa: E402

WEB = ROOT / "mota" / "dashboard" / "web"
S = json.loads((WEB / "lib" / "sprites.json").read_text(encoding="utf-8"))
SHEETS = {k: Image.open(WEB / "public" / v["url"].lstrip("/")).convert("RGBA") for k, v in S["sheets"].items()}
OUT = ROOT / "docs" / "figures" / "2.4.png"
CELL, SCALE = 32, 3


def frame(sheet: str, idx: int) -> Image.Image:
    return SHEETS[sheet].crop((0, idx * CELL, CELL, (idx + 1) * CELL))


def sprite_for(c) -> Image.Image | None:
    """Same rule as the dashboard's FloorMap: tile number first, then the cell type / entity name."""
    if isinstance(c, str):
        c = {"t": c}
    if c.get("id") is not None and str(c["id"]) in S["tiles"]:
        return frame(*S["tiles"][str(c["id"])])
    t = c.get("t")
    if t == "#":
        return frame(*S["wall"])
    if t in S["doors"]:
        return frame(*S["doors"][t])
    if t == "S":
        return frame(*S["stairs"]["down" if c.get("dir") == "downFloor" else "up"])
    name = c.get("name") or ""
    sp = S["names"].get(name) or S["names"].get(name.split(" (")[0])
    return frame(*sp) if sp else None


def hero_sprite() -> Image.Image:
    h = S["hero"]
    sheet = SHEETS[h["sheet"]]
    fw, fh = sheet.width // h["cols"], sheet.height // h["rows"]
    return sheet.crop((h["stop"] * fw, h["down"] * fh, (h["stop"] + 1) * fw, (h["down"] + 1) * fh)).resize((CELL, CELL))


def render(floor: str, rows: range, marks: list[tuple[int, int, str]],
           route: list[tuple[int, int]] = ()) -> Image.Image:
    ev.configure_scenario(floor)
    m = ev._serialize_rich_map(ev._create_state())
    grid, hero = m["grid"], m["hero"]
    w = len(grid[0])
    ground = frame(*S["tiles"]["0"])
    img = Image.new("RGBA", (w * CELL, len(rows) * CELL))
    for j, y in enumerate(rows):
        for x in range(w):
            img.alpha_composite(ground, (x * CELL, j * CELL))
            sp = hero_sprite() if (x, y) == (hero["x"], hero["y"]) else sprite_for(grid[y][x])
            if sp is not None:
                img.alpha_composite(sp, (x * CELL, j * CELL))
    img = img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST)

    margin_l, margin_t = 46, 40
    out = Image.new("RGB", (img.width + margin_l + 8, img.height + margin_t + 8), "white")
    out.paste(img, (margin_l, margin_t), img)
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
        bold = ImageFont.truetype("arialbd.ttf", 26)
    except OSError:
        font = bold = ImageFont.load_default()
    c = CELL * SCALE
    for x in range(w):
        d.text((margin_l + x * c + c / 2, margin_t / 2), str(x), fill="#333", font=font, anchor="mm")
    for j, y in enumerate(rows):
        d.text((margin_l / 2, margin_t + j * c + c / 2), str(y), fill="#333", font=font, anchor="mm")
    for x, y, label in marks:
        j = rows.index(y)
        x0, y0 = margin_l + x * c, margin_t + j * c
        d.rectangle((x0 + 2, y0 + 2, x0 + c - 3, y0 + c - 3), outline="#e8b400", width=5)
        r = 17
        cx, cy = x0 + c - r + 2, y0 + r - 2
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="#e8b400", outline="black", width=2)
        d.text((cx, cy), label, fill="black", font=bold, anchor="mm")
    try:
        small = ImageFont.truetype("arialbd.ttf", 21)
    except OSError:
        small = ImageFont.load_default()
    for k, (x, y) in enumerate(route, 1):
        x0, y0 = margin_l + x * c, margin_t + rows.index(y) * c
        r = 16
        cx, cy = x0 + r + 1, y0 + r + 1
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="white", outline="#1f3a93", width=3)
        d.text((cx, cy), str(k), fill="#1f3a93", font=small, anchor="mm")
    return out


# the 17 actions of the simple floor's exact optimal route (Section 4.5.1)
SIMPLE_ROUTE = [(6, 4), (5, 6), (4, 7), (3, 7), (7, 0), (8, 0), (9, 0), (3, 5), (7, 5), (9, 5),
                (1, 9), (10, 7), (9, 9), (4, 2), (2, 1), (5, 9), (5, 10)]


if __name__ == "__main__":
    simple = str(ROOT / "data/floors/simple.txt")
    figs = (("2.4", lambda: render(simple, range(0, 6), [(4, 2, "1"), (5, 3, "2"), (6, 4, "3"), (7, 0, "4")])),
            ("4.1", lambda: render(simple, range(0, 11), [], SIMPLE_ROUTE)),
            ("B.1", lambda: render(str(ROOT / "data/floors/complex.txt"), range(0, 13), [(8, 7, "1"), (11, 8, "2")])),
            ("B.2", lambda: render(str(ROOT / "data/floors/hand/hand01.txt"), range(0, 11),
                                   [(4, 8, "1"), (5, 4, "2"), (6, 8, "3")])))
    for name, make in figs:
        fig = make()
        out = OUT.with_name(f"{name}.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.save(out, dpi=(300, 300))
        print("wrote", out, fig.size)
