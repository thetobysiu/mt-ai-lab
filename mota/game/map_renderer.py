"""
MOTA Game Map Image Renderer.

Renders the game state as a pixel image for Vision-Language model experiments.
Each tile type gets a distinct color; hero position is highlighted.

Target: 512×512 native resolution for LFM2.5-VL-1.6B (SigLIP2 NaFlex encoder).

Usage:
    from mota.game.map_renderer import render_map_image
    img = render_map_image(state)
    img.save("map.png")
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


# ── Tile color scheme ──────────────────────────────────────────────────────
# Colors are (R, G, B) tuples designed for visual clarity at small sizes.

COLORS = {
    "wall":       (40, 40, 40),       # Dark gray
    "ground":     (220, 220, 200),    # Light beige
    "hero":       (0, 120, 255),      # Bright blue
    "enemy":      (220, 50, 50),      # Red
    "enemy_ez":   (255, 140, 100),    # Light red (cheap enemy)
    "item_stat":  (0, 200, 100),      # Green (gems, sword, shield)
    "item_key":   (255, 215, 0),      # Gold (keys)
    "item_hp":    (255, 100, 200),    # Pink (potions)
    "item_misc":  (150, 200, 255),    # Light blue
    "door_y":     (255, 200, 0),      # Yellow door
    "door_b":     (70, 130, 255),     # Blue door
    "door_r":     (200, 30, 30),      # Red door
    "stairs_up":  (100, 255, 100),    # Bright green
    "stairs_down": (100, 200, 255),   # Light blue
    "shop":       (200, 150, 255),    # Purple
    "npc":        (255, 180, 120),    # Peach
    "terrain":    (130, 100, 70),     # Brown
    "unknown":    (128, 128, 128),    # Gray
}

# Enemy damage thresholds for color coding
CHEAP_ENEMY_THRESHOLD = 50  # Below this damage = light red


def render_map_image(
    state,
    cell_size: int = 38,
    margin: int = 4,
    show_hero: bool = True,
    show_labels: bool = False,
    max_pixels: int = 512,
) -> Image.Image:
    """
    Render the current game state as a pixel image.

    Args:
        state: GameState object with floor, hero, removed entities.
        cell_size: Pixels per grid cell.
        margin: Margin around the grid in pixels.
        show_hero: Whether to draw the hero marker.
        show_labels: Whether to draw text labels on tiles.
        max_pixels: Maximum image dimension (scales down if necessary).

    Returns:
        PIL Image (RGB) suitable for VL model input.
    """
    from ..game import data as D
    from ..game import damage as dmg_mod

    floor = state.floor
    gd = state.gd
    w, h = floor.width, floor.height

    # Auto-scale cell_size to fit within max_pixels
    total_w = w * cell_size + 2 * margin
    total_h = h * cell_size + 2 * margin
    if max(total_w, total_h) > max_pixels:
        scale = max_pixels / max(total_w, total_h)
        cell_size = max(8, int(cell_size * scale))
        margin = max(2, int(margin * scale))

    img_w = w * cell_size + 2 * margin
    img_h = h * cell_size + 2 * margin
    img = Image.new("RGB", (img_w, img_h), COLORS["wall"])
    draw = ImageDraw.Draw(img)

    # Try to get a small font for labels
    font = None
    if show_labels:
        try:
            font = ImageFont.truetype("arial.ttf", max(8, cell_size // 3))
        except (OSError, IOError):
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

    for y in range(h):
        for x in range(w):
            tile = floor.map[y][x]
            removed = (x, y) in state.removed
            px = margin + x * cell_size
            py = margin + y * cell_size

            # Determine tile color
            color, label = _classify_tile(tile, removed, x, y, state, gd, D, dmg_mod)

            # Draw filled rectangle
            draw.rectangle(
                [px + 1, py + 1, px + cell_size - 1, py + cell_size - 1],
                fill=color,
                outline=(60, 60, 60),
                width=1,
            )

            # Draw label text if enabled
            if show_labels and label and font:
                tw = draw.textlength(label, font=font)
                tx = px + (cell_size - tw) / 2
                ty = py + (cell_size - font.size) / 2
                # Pick contrasting text color
                brightness = color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114
                text_color = (0, 0, 0) if brightness > 128 else (255, 255, 255)
                draw.text((tx, ty), label, fill=text_color, font=font)

    # Draw hero marker
    if show_hero:
        hx = margin + state.hero.x * cell_size + cell_size // 2
        hy = margin + state.hero.y * cell_size + cell_size // 2
        r = max(3, cell_size // 3)
        draw.ellipse(
            [hx - r, hy - r, hx + r, hy + r],
            fill=COLORS["hero"],
            outline=(255, 255, 255),
            width=2,
        )

    return img


def _classify_tile(tile, removed, x, y, state, gd, D, dmg_mod):
    """Classify a tile and return (color, label) tuple."""
    if removed:
        return COLORS["ground"], ""

    if D.is_wall(tile):
        return COLORS["wall"], ""

    if D.is_ground(tile):
        return COLORS["ground"], ""

    if gd.is_enemy(tile):
        eid = gd.get_enemy_id(tile)
        m = gd.get_monster(eid)
        battle = dmg_mod.calculate(state.hero, m)
        if not battle.can_win:
            return (100, 0, 0), "X"  # Dark red for unwinnable
        if battle.total_damage <= CHEAP_ENEMY_THRESHOLD:
            return COLORS["enemy_ez"], "E"
        return COLORS["enemy"], "E"

    if D.is_item(tile):
        item_id = D.TILE_ITEMS.get(tile, "")
        if "Key" in item_id:
            return COLORS["item_key"], "K"
        if "Gem" in item_id or "sword" in item_id or "shield" in item_id:
            return COLORS["item_stat"], "G"
        if "Potion" in item_id or "potion" in item_id:
            return COLORS["item_hp"], "P"
        return COLORS["item_misc"], "I"

    if D.is_door(tile):
        door_type = D.TILE_DOORS.get(tile)
        if door_type:
            dt = door_type.value if hasattr(door_type, "value") else str(door_type)
            if "yellow" in dt.lower():
                return COLORS["door_y"], "D"
            if "blue" in dt.lower():
                return COLORS["door_b"], "D"
            if "red" in dt.lower():
                return COLORS["door_r"], "D"
        return COLORS["door_y"], "D"

    if D.is_stairs(tile):
        name = D.TILE_STAIRS.get(tile, "")
        if "up" in str(name).lower():
            return COLORS["stairs_up"], "S"
        return COLORS["stairs_down"], "S"

    if D.is_npc(tile):
        return COLORS["npc"], "N"

    if D.is_terrain(tile):
        return COLORS["terrain"], ""

    return COLORS["unknown"], "?"


def render_map_with_legend(state, cell_size: int = 38) -> Image.Image:
    """Render the map with a color legend sidebar for human readability."""
    map_img = render_map_image(state, cell_size=cell_size, show_labels=True)

    # Build legend
    legend_w = 160
    legend_h = map_img.height
    legend = Image.new("RGB", (legend_w, legend_h), (255, 255, 255))
    draw = ImageDraw.Draw(legend)

    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except (OSError, IOError):
        font = ImageFont.load_default()

    legend_items = [
        ("Hero", COLORS["hero"]),
        ("Enemy", COLORS["enemy"]),
        ("Cheap Enemy", COLORS["enemy_ez"]),
        ("Stat Item", COLORS["item_stat"]),
        ("Key", COLORS["item_key"]),
        ("Potion", COLORS["item_hp"]),
        ("Yellow Door", COLORS["door_y"]),
        ("Blue Door", COLORS["door_b"]),
        ("Red Door", COLORS["door_r"]),
        ("Stairs", COLORS["stairs_up"]),
        ("Shop/NPC", COLORS["npc"]),
        ("Wall", COLORS["wall"]),
        ("Ground", COLORS["ground"]),
    ]

    y_off = 10
    for label, color in legend_items:
        draw.rectangle([10, y_off, 30, y_off + 16], fill=color, outline=(0, 0, 0))
        draw.text((36, y_off), label, fill=(0, 0, 0), font=font)
        y_off += 22

    # Combine
    combined = Image.new("RGB", (map_img.width + legend_w, max(map_img.height, legend_h)), (255, 255, 255))
    combined.paste(map_img, (0, 0))
    combined.paste(legend, (map_img.width, 0))
    return combined
