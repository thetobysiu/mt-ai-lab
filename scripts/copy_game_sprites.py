"""Copy the original 24-floor game's sprite sheets into the dashboard and write the tile -> sprite index.

    python scripts/copy_game_sprites.py

Reads (never modifies) 24/project/{maps.js, icons.js, materials/*.png, images/hero.png}; writes
mota/dashboard/web/public/sprites/*.png and mota/dashboard/web/lib/sprites.json, used by FloorMap's
"game textures" view. Every sheet is a column of 32x32 tiles; animated sheets hold 2 or 4 frames side by side.
"""
from __future__ import annotations

import json
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "data" / "games" / "24" / "project"
WEB = ROOT / "mota" / "dashboard" / "web"
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from mota.game import data as D  # noqa: E402

SHEETS = {"terrains": "materials/terrains.png", "animates": "materials/animates.png", "enemys": "materials/enemys.png",
          "items": "materials/items.png", "npcs": "materials/npcs.png", "hero": "images/hero.png"}
BOSS_SPRITE = ("enemys", "magicDragon")  # the AI-test-floor boss (tile 299) has no tile in the game


def _js_object(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def main() -> None:
    maps, icons = _js_object(GAME / "maps.js"), _js_object(GAME / "icons.js")
    out = WEB / "public" / "sprites"
    out.mkdir(parents=True, exist_ok=True)
    sheets = {}
    for name, rel in SHEETS.items():
        src = GAME / rel
        shutil.copyfile(src, out / f"{name}.png")
        w, h = _png_size(src)
        sheets[name] = {"url": f"/sprites/{name}.png", "frames": w // 32, "w": w, "h": h}

    tiles = {"0": ["terrains", icons["terrains"]["ground"]]}
    for num, t in maps.items():
        idx = icons.get(t["cls"], {}).get(t["id"])
        if t["cls"] in sheets and isinstance(idx, int):
            tiles[num] = [t["cls"], idx]
    tiles["299"] = [BOSS_SPRITE[0], icons[BOSS_SPRITE[0]][BOSS_SPRITE[1]]]

    # Name fallback for run logs recorded before cells carried their tile number.
    names: dict[str, list] = {"Boss": tiles["299"]}
    for mid, idx in icons["enemys"].items():
        names[mid] = ["enemys", idx]
        if mid in D.MONSTER_NAMES_EN:
            names[D.MONSTER_NAMES_EN[mid]] = ["enemys", idx]
        m = D.MONSTERS.get(mid)
        if m is not None and getattr(m, "name_zh", None):
            names[m.name_zh] = ["enemys", idx]
    for iid, idx in icons["items"].items():
        names[iid] = ["items", idx]
        eff = D.ITEM_EFFECTS.get(iid)
        if eff and eff.get("name"):
            names[eff["name"].split(" (")[0]] = ["items", idx]
    for nid, idx in icons["npcs"].items():
        names[nid] = ["npcs", idx]

    hero = icons["hero"]
    index = {"source": "24/project (original game, copied by scripts/copy_game_sprites.py)", "sheets": sheets,
             "tiles": tiles, "names": names,
             "hero": {"sheet": "hero", "rows": 4, "cols": 4, "down": hero["down"]["loc"], "stop": hero["down"]["stop"]},
             "doors": {"Y": tiles["81"], "B": tiles["82"], "R": tiles["83"]},
             "stairs": {"up": tiles["87"], "down": tiles["88"]}, "wall": tiles["1"]}
    (WEB / "lib" / "sprites.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(sheets)} sheets -> {out.relative_to(ROOT)}; {len(tiles)} tiles, {len(names)} names -> web/lib/sprites.json")


if __name__ == "__main__":
    main()
