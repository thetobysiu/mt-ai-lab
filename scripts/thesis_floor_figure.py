"""Render hand01 with the original game sprites for the thesis.

    python scripts/thesis_floor_figure.py   ->  thesis/graphs/2.4.png (rows 4-10, the three first choices), 4.1.png (full floor)
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


def render(floor: str, rows: range, marks: list[tuple[int, int, str]]) -> Image.Image:
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
    return out


if __name__ == "__main__":
    hand01 = str(ROOT / "data/floors/hand/hand01.txt")
    for name, fig in (("2.4", render(hand01, range(4, 11), [(4, 8, "1"), (6, 8, "2"), (5, 4, "3")])),
                      ("4.1", render(hand01, range(0, 11), []))):
        out = OUT.with_name(f"{name}.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.save(out, dpi=(300, 300))
        print("wrote", out, fig.size)
