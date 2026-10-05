"""
Game data constants — monster stats, item effects, tile mappings, shop definitions.
Extracted from project/enemys.js, project/items.js, project/maps.js, project/data.js.
"""
from __future__ import annotations
from .types import Monster, DoorType, ItemTier

# ---------------------------------------------------------------------------
# Tile ID → semantic mapping (from project/maps.js)
# ---------------------------------------------------------------------------
TILE_GROUND = 0
TILE_WALLS = {1, 2, 3}  # yellowWall, whiteWall, blueWall

TILE_ITEMS = {
    21: "yellowKey", 22: "blueKey", 23: "redKey",
    27: "redGem", 28: "blueGem", 29: "greenGem", 30: "yellowGem",
    31: "redPotion", 32: "bluePotion", 33: "greenPotion", 34: "yellowPotion",
    35: "sword1", 36: "shield1", 37: "sword2", 38: "shield2",
    39: "sword3", 40: "shield3", 41: "sword4", 42: "shield4",
    43: "sword5", 44: "shield5",
    45: "book", 46: "fly", 47: "pickaxe", 49: "bomb",
    50: "centerFly", 51: "upFly", 52: "downFly",
    53: "coin", 55: "cross", 56: "superPotion",
    63: "pack", 64: "amulet",
}

TILE_DOORS = {
    6: DoorType.ICE,
    81: DoorType.YELLOW,
    82: DoorType.BLUE,
    83: DoorType.RED,
}

TILE_ENEMIES = {
    201: "greenSlime", 202: "redSlime", 203: "blackSlime",
    204: "slimelord", 205: "bat", 206: "bigBat",
    207: "redBat", 208: "vampire", 209: "skeleton",
    210: "skeletonSoilder", 211: "skeletonCaptain",
    212: "ghostSkeleton", 213: "zombie", 214: "zombieKnight",
    215: "rock", 216: "slimeMan", 217: "bluePriest",
    218: "redPriest", 219: "brownWizard", 220: "redWizard",
    221: "yellowGuard", 222: "blueGuard", 223: "redGuard",
    224: "swordsman", 225: "soldier", 226: "yellowKnight",
    227: "redKnight", 228: "darkKnight", 229: "blackKing",
    230: "yellowKing", 231: "greenKing",
    232: "blueKnight", 233: "goldSlime",
    234: "poisonSkeleton", 235: "poisonBat",
    236: "steelRock", 237: "skeletonPriest",
    238: "skeletonKing", 239: "skeletonWizard",
    240: "redSkeletonCaption", 241: "badHero",
    242: "demon", 243: "demonPriest",
    244: "goldHornSlime", 245: "redKing",
    246: "whiteKing", 247: "blackMagician",
    248: "silverSlime", 249: "swordEmperor",
    250: "whiteHornSlime", 251: "badPrincess",
    252: "badFairy", 253: "grayPriest",
    254: "redSwordsman", 255: "whiteGhost",
    256: "poisonZombie", 257: "magicDragon",
    258: "octopus", 259: "darkFairy",
    260: "greenKnight", 261: "angel",
    262: "elemental", 263: "steelGuard",
    264: "evilBat",
}

TILE_NPCS = {
    121: "man", 122: "trader", 123: "thief", 124: "fairy",
    125: "wizard", 126: "recluse", 127: "king", 128: "youngMan",
    129: "sign", 130: "expShop", 131: "moneyShop", 132: "princess",
}

TILE_STAIRS = {87: "upFloor", 88: "downFloor"}
TILE_TERRAINS = {
    7: "blueShopLeft", 8: "blueShopRight", 9: "pinkShopLeft", 10: "pinkShopRight",
}

# ---------------------------------------------------------------------------
# Monster definitions (from project/enemys.js)
# ---------------------------------------------------------------------------
MONSTERS: dict[str, Monster] = {
    "greenSlime":      Monster("greenSlime",      "绿头怪",   hp=50,   atk=20,  def_=1,   money=1,  exp=1),
    "redSlime":        Monster("redSlime",        "红头怪",   hp=70,   atk=15,  def_=2,   money=2,  exp=2),
    "blackSlime":      Monster("blackSlime",      "青头怪",   hp=200,  atk=35,  def_=10,  money=5,  exp=5),
    "slimelord":       Monster("slimelord",       "怪王",     hp=700,  atk=250, def_=125, money=32, exp=30),
    "bat":             Monster("bat",             "小蝙蝠",   hp=100,  atk=20,  def_=5,   money=3,  exp=3),
    "bigBat":          Monster("bigBat",          "大蝙蝠",   hp=150,  atk=65,  def_=30,  money=10, exp=8),
    "redBat":          Monster("redBat",          "红蝙蝠",   hp=550,  atk=160, def_=90,  money=25, exp=20),
    "skeleton":        Monster("skeleton",        "骷髅人",   hp=110,  atk=25,  def_=5,   money=5,  exp=4),
    "skeletonSoilder": Monster("skeletonSoilder", "骷髅士兵", hp=150,  atk=40,  def_=20,  money=8,  exp=6),
    "skeletonCaptain": Monster("skeletonCaptain", "骷髅队长", hp=400,  atk=90,  def_=50,  money=15, exp=12),
    "ghostSkeleton":   Monster("ghostSkeleton",   "冥队长",   hp=2500, atk=900, def_=850, money=84, exp=75),
    "zombie":          Monster("zombie",          "兽面人",   hp=300,  atk=75,  def_=45,  money=13, exp=10),
    "zombieKnight":    Monster("zombieKnight",    "兽面武士", hp=900,  atk=450, def_=330, money=50, exp=50),
    "rock":            Monster("rock",            "石头人",   hp=500,  atk=115, def_=65,  money=15, exp=15),
    "slimeMan":        Monster("slimeMan",        "影子战士", hp=3100, atk=1150,def_=1050,money=92, exp=80),
    "bluePriest":      Monster("bluePriest",      "初级法师", hp=125,  atk=50,  def_=25,  money=10, exp=7),
    "redPriest":       Monster("redPriest",       "高级法师", hp=100,  atk=200, def_=110, money=30, exp=25),
    "brownWizard":     Monster("brownWizard",     "麻衣法师", hp=250,  atk=120, def_=70,  money=20, exp=17, special=22, damage=100),
    "redWizard":       Monster("redWizard",       "红衣法师", hp=500,  atk=400, def_=260, money=47, exp=45, special=22, damage=300),
    "yellowGuard":     Monster("yellowGuard",     "初级卫兵", hp=450,  atk=150, def_=90,  money=22, exp=19),
    "blueGuard":       Monster("blueGuard",       "中级卫兵", hp=1250, atk=500, def_=400, money=55, exp=55),
    "redGuard":        Monster("redGuard",        "高级卫兵", hp=1500, atk=560, def_=460, money=60, exp=60),
    "swordsman":       Monster("swordsman",       "双手剑士", hp=1200, atk=620, def_=520, money=65, exp=75),
    "soldier":         Monster("soldier",         "冥战士",   hp=2000, atk=680, def_=590, money=70, exp=65),
    "yellowKnight":    Monster("yellowKnight",    "金卫士",   hp=850,  atk=350, def_=200, money=45, exp=40),
    "redKnight":       Monster("redKnight",       "金队长",   hp=900,  atk=750, def_=650, money=77, exp=70),
    "darkKnight":      Monster("darkKnight",      "灵武士",   hp=1200, atk=980, def_=900, money=88, exp=75),
    "blackKing":       Monster("blackKing",       "黑衣魔王", hp=1000, atk=500, def_=0,   money=1000,exp=1000),
    "redKing":         Monster("redKing",         "红衣魔王", hp=15000,atk=1000,def_=1000,money=100,exp=100),
    "vampire":         Monster("vampire",         "冥灵魔王", hp=30000,atk=1700,def_=1500,money=250,exp=220),
    "magicDragon":     Monster("magicDragon",     "魔龙",     hp=99999,atk=9999,def_=5000,money=0,  exp=0),
    "octopus":         Monster("octopus",         "血影",     hp=99999,atk=5000,def_=4000,money=0,  exp=0),
    "poisonSkeleton":  Monster("poisonSkeleton",  "紫骷髅",   hp=0,    atk=0,   def_=0,   money=0,  exp=0),
    "badPrincess":     Monster("badPrincess",     "痛苦魔女", hp=0,    atk=0,   def_=0,   money=0,  exp=0),
    "whiteKing":       Monster("whiteKing",       "白衣武士", hp=1300, atk=300, def_=150, money=40, exp=35, special=11, vampire=0.25),
    "blackMagician":   Monster("blackMagician",   "灵法师",   hp=1500, atk=830, def_=730, money=80, exp=70, special=11, vampire=1/3),
    "blueKnight":      Monster("blueKnight",      "蓝骑士",   hp=100,  atk=120, def_=0,   money=9,  exp=0, special=8),
    "poisonBat":       Monster("poisonBat",       "紫蝙蝠",   hp=100,  atk=120, def_=0,   money=14, exp=0, special=13),
    "silverSlime":     Monster("silverSlime",     "银头怪",   hp=100,  atk=120, def_=0,   money=15, exp=0, special=14),
    "redSwordsman":    Monster("redSwordsman",    "剑王",     hp=100,  atk=120, def_=0,   money=7,  exp=0, special=6, n=8),
    "poisonZombie":    Monster("poisonZombie",    "绿兽人",   hp=100,  atk=120, def_=0,   money=13, exp=0, special=12),
    "steelGuard":      Monster("steelGuard",      "铁守卫",   hp=0,    atk=0,   def_=0,   money=0,  exp=0, special=18),
    "evilBat":         Monster("evilBat",         "邪恶蝙蝠", hp=1000, atk=1,   def_=0,   money=0,  exp=0, special=[2, 3]),
}

def get_monster(monster_id: str) -> Monster:
    m = MONSTERS.get(monster_id)
    if m is None:
        raise KeyError(f"Unknown monster: {monster_id}")
    # Return a copy so callers don't mutate the template
    return Monster(
        id=m.id, name=display_monster_name(m.id, m.name), hp=m.hp, atk=m.atk, def_=m.def_,
        money=m.money, exp=m.exp, special=m.special,
        damage=m.damage, vampire=m.vampire, n=m.n, name_zh=m.name,
    )


# ---------------------------------------------------------------------------
# Monster display names. enemys.js names are Chinese; the LLM prompt and the UI use English
# by default (MOTA_MONSTER_NAMES=en|zh|both). The enemys.js id (e.g. `redBat`) is the stable
# reference for the thesis; the mapping below is the translation table (Appendix).
# ---------------------------------------------------------------------------
MONSTER_NAMES_EN: dict[str, str] = {
    "greenSlime": "Green Slime", "redSlime": "Red Slime", "blackSlime": "Black Slime", "slimelord": "Slime Lord",
    "bat": "Bat", "bigBat": "Big Bat", "redBat": "Red Bat", "skeleton": "Skeleton",
    "skeletonSoilder": "Skeleton Soldier", "skeletonCaptain": "Skeleton Captain", "ghostSkeleton": "Nether Captain",
    "zombie": "Beast-Man", "zombieKnight": "Beast Warrior", "rock": "Rock Man", "slimeMan": "Shadow Warrior",
    "bluePriest": "Junior Mage", "redPriest": "Senior Mage", "brownWizard": "Hemp-Robe Mage", "redWizard": "Red-Robe Mage",
    "yellowGuard": "Junior Guard", "blueGuard": "Mid Guard", "redGuard": "Senior Guard", "swordsman": "Two-Hand Swordsman",
    "soldier": "Nether Warrior", "yellowKnight": "Gold Sentinel", "redKnight": "Gold Captain", "darkKnight": "Spirit Warrior",
    "blackKing": "Black Demon King", "redKing": "Red Demon King", "vampire": "Nether Demon King",
    "magicDragon": "Magic Dragon", "octopus": "Blood Shadow", "poisonSkeleton": "Purple Skeleton",
    "badPrincess": "Witch of Agony", "whiteKing": "White Warrior", "blackMagician": "Spirit Mage",
    "blueKnight": "Blue Knight", "poisonBat": "Purple Bat", "silverSlime": "Silver Slime", "redSwordsman": "Sword King",
    "poisonZombie": "Green Beast-Man", "steelGuard": "Steel Guard", "evilBat": "Evil Bat",
    # extra ids seen in enemys.js (24/51) but not on any 24-layer floor
    "yellowKing": "Yellow Demon King", "greenKing": "Green Demon King", "goldSlime": "Gold Slime",
    "steelRock": "Steel Rock", "skeletonPriest": "Skeleton Priest", "skeletonKing": "Skeleton King",
    "skeletonWizard": "Skeleton Wizard", "redSkeletonCaption": "Red Skeleton Captain", "badHero": "Fallen Hero",
    "demon": "Demon", "demonPriest": "Demon Priest", "goldHornSlime": "Gold-Horn Slime", "whiteHornSlime": "White-Horn Slime",
    "badFairy": "Dark Fairy", "darkFairy": "Shadow Fairy", "grayPriest": "Gray Priest", "whiteGhost": "White Ghost",
    "swordEmperor": "Sword Emperor", "angel": "Angel", "elemental": "Elemental", "greenKnight": "Green Knight",
    "vampire2": "Vampire II", "vampire3": "Vampire III", "skeletonSoldier": "Skeleton Soldier",
}


def monster_name_mode() -> str:
    import os
    return os.environ.get("MOTA_MONSTER_NAMES", "en").lower()


def display_monster_name(monster_id: str, zh_name: str) -> str:
    """Name shown to the LLM and in the UI. `en` (default) | `zh` (original) | `both` ("Red Bat (红蝙蝠)")."""
    mode = monster_name_mode()
    en = MONSTER_NAMES_EN.get(monster_id)
    if mode == "zh" or not en:
        return zh_name
    if mode == "both":
        return f"{en} ({zh_name})"
    return en


# ---------------------------------------------------------------------------
# Item effects (from project/items.js + project/data.js)
# ---------------------------------------------------------------------------
ITEM_EFFECTS: dict[str, dict] = {
    # Keys
    "yellowKey": {"keys.yellow": 1, "tier": ItemTier.KEY, "score": 80, "name": "Yellow Key"},
    "blueKey":   {"keys.blue": 1,   "tier": ItemTier.KEY, "score": 85, "name": "Blue Key"},
    "redKey":    {"keys.red": 1,    "tier": ItemTier.KEY, "score": 90, "name": "Red Key"},
    # Gems
    "redGem":    {"atk": 3, "tier": ItemTier.CORE_STAT, "score": 90,  "name": "Red Gem (+3 ATK)"},
    "blueGem":   {"def": 3, "tier": ItemTier.CORE_STAT, "score": 90,  "name": "Blue Gem (+3 DEF)"},
    "greenGem":  {"mdef": 3,"tier": ItemTier.CORE_STAT, "score": 85,  "name": "Green Gem (+3 MDEF)"},
    # Potions
    "redPotion":    {"hp": 200,  "tier": ItemTier.HP, "score": 60, "name": "Red Potion (+200 HP)"},
    "bluePotion":   {"hp": 500,  "tier": ItemTier.HP, "score": 70, "name": "Blue Potion (+500 HP)"},
    "greenPotion":  {"hp": 800,  "tier": ItemTier.HP, "score": 75, "name": "Green Potion (+800 HP)"},
    "yellowPotion": {"hp": 500,  "tier": ItemTier.HP, "score": 70, "name": "Yellow Potion (+500 HP)"},
    # Equipment
    "sword1": {"atk": 10, "tier": ItemTier.MAJOR_STAT, "score": 95, "name": "Iron Sword (+10 ATK)"},
    "shield1":{"def": 10, "tier": ItemTier.MAJOR_STAT, "score": 95, "name": "Iron Shield (+10 DEF)"},
    "sword2": {"atk": 70, "tier": ItemTier.MAJOR_STAT, "score": 98, "name": "Steel Sword (+70 ATK)"},
    "shield2":{"def": 20, "tier": ItemTier.MAJOR_STAT, "score": 96, "name": "Silver Shield (+20 DEF)"},
    "sword3": {"atk": 40, "tier": ItemTier.MAJOR_STAT, "score": 97, "name": "Knight Sword (+40 ATK)"},
    "shield3":{"def": 40, "tier": ItemTier.MAJOR_STAT, "score": 97, "name": "Knight Shield (+40 DEF)"},
    "sword4": {"atk": 80, "tier": ItemTier.MAJOR_STAT, "score": 98, "name": "Holy Sword (+80 ATK)"},
    "shield4":{"def": 80, "tier": ItemTier.MAJOR_STAT, "score": 98, "name": "Holy Shield (+80 DEF)"},
    "sword5": {"atk": 160,"tier": ItemTier.MAJOR_STAT, "score": 99, "name": "Divine Sword (+160 ATK)"},
    "shield5":{"def": 100,"tier": ItemTier.MAJOR_STAT, "score": 99, "name": "Divine Shield (+100 DEF)"},
    # Constants
    "book":  {"tier": ItemTier.MISC, "score": 30, "name": "Monster Handbook"},
    "fly":   {"tier": ItemTier.MISC, "score": 30, "name": "Floor Transporter"},
    "cross": {"tier": ItemTier.MISC, "score": 50, "name": "Cross"},
    "coin":  {"tier": ItemTier.MISC, "score": 40, "name": "Lucky Coin"},
    "pack":  {"money": 500, "tier": ItemTier.MISC, "score": 60, "name": "Money Bag (+500g)"},
}

def get_item_effect(item_id: str) -> dict:
    return ITEM_EFFECTS.get(item_id, {"tier": ItemTier.MISC, "score": 10, "name": item_id})


# MOTA_TOWER_FIDELITY=1: the nine items whose built-in values differ from 24/project/items.js (pinned in
# test_project_adapter.KNOWN_BUILTIN_DISCREPANCIES); the built-in table stays the default for every stored result.
TOWER_ITEM_EFFECTS: dict[str, dict] = {
    "greenGem": {**ITEM_EFFECTS["greenGem"], "mdef": 5, "name": "Green Gem (+5 MDEF)"},
    "shield2": {**ITEM_EFFECTS["shield2"], "def": 30, "name": "Silver Shield (+30 DEF)"},
    "sword3": {**ITEM_EFFECTS["sword3"], "atk": 70, "name": "Knight Sword (+70 ATK)"},
    "shield3": {**ITEM_EFFECTS["shield3"], "def": 85, "name": "Knight Shield (+85 DEF)"},
    "sword4": {**ITEM_EFFECTS["sword4"], "atk": 120, "name": "Holy Sword (+120 ATK)"},
    "shield4": {**ITEM_EFFECTS["shield4"], "def": 120, "name": "Holy Shield (+120 DEF)"},
    "sword5": {**ITEM_EFFECTS["sword5"], "atk": 150, "name": "Divine Sword (+150 ATK)"},
    "shield5": {**ITEM_EFFECTS["shield5"], "def": 190, "name": "Divine Shield (+190 DEF)"},
    "pack": {**ITEM_EFFECTS["pack"], "money": 300, "name": "Money Bag (+300g)"},
    # items.js itemEffect: lv/hp/atk/def; centerFly lies on MT6 (1,1), I338 is what the MT13 wizard hands over
    "centerFly": {"lv": 1, "hp": 1000, "atk": 10, "def": 10, "tier": ItemTier.MAJOR_STAT, "score": 99,
                  "name": "Small Feather (level +1: HP +1000, ATK +10, DEF +10)"},
    "I338": {"lv": 3, "hp": 3000, "atk": 30, "def": 30, "tier": ItemTier.MAJOR_STAT, "score": 99,
             "name": "Big Feather (level +3: HP +3000, ATK +30, DEF +30)"},
    # tile 26 (MT5 (1,1), MT14 (4,1)) and tile 48 (MT12 (11,1)) were walls in the engine (user 2026-10-02)
    "bigKey": {"keys.yellow": 1, "keys.blue": 1, "keys.red": 1, "tier": ItemTier.KEY, "score": 90,
               "name": "Key Box (+1 yellow, +1 blue, +1 red key)"},
    "icePickaxe": {"tier": ItemTier.MISC, "score": 20, "name": "Ice Pickaxe (the thief on MT4 asks for it)"},
    "superPotion": {"hp_mul": 2, "tier": ItemTier.HP, "score": 99, "name": "Holy Water (doubles your HP when picked up)"},
}
TOWER_TILE_ITEMS: dict[int, str] = {**TILE_ITEMS, 26: "bigKey", 48: "icePickaxe"}
# Items listed on the treasure line (MOTA_FREE_AFFORD=1): equipment, feathers, key boxes, the Cross, Holy Water.
TREASURE_ITEMS = frozenset({"sword1", "sword2", "sword3", "sword4", "sword5", "shield1", "shield2", "shield3", "shield4",
                            "shield5", "centerFly", "I338", "bigKey", "cross", "superPotion"})

# MOTA_TOWER_FIDELITY=1: NPCs whose event is defined on the tile in maps.js (not in the floor file): npc id -> item.
NPC_TILE_GIFTS: dict[str, str] = {"wizard": "I338"}
# MOTA_TOWER_FIDELITY=1: tiles that stay closed until every monster of one kind on that floor is dead
# (user 2026-10-02: the MT7 seal in front of the Cross opens after all four White Warriors).
FLOOR_SEALS: dict[str, dict] = {"MT7": {"tile": (5, 5), "monster": "whiteKing", "behind": "the Cross"}}


# ---------------------------------------------------------------------------
# Shop definitions (from project/data.js)
# Solver configuration
BFS_MAX_STATES = 500000  # Increased for complex floors

# --- Entity Definitions ---
# Shops are keyed by the `openShop` event id used in project/floors/MT*.js.
# `currency` is the hero field debited ("money" or "exp"); `cost` may be set per
# choice (exp shops) or once per shop. `changes` may touch hp/atk/def/mdef, keys.*
# and money (key sales). Values are copied verbatim from project/data.js.
_SHOP1_CHOICES = [
    {"id": "hp",  "label": "HP +800",  "changes": {"hp": 800}},
    {"id": "atk", "label": "ATK +4",   "changes": {"atk": 4}},
    {"id": "def", "label": "DEF +4",   "changes": {"def": 4}},
]
SHOPS = {
    "moneyShop1": {"name": "Gold Shop (3F)", "currency": "money", "cost": 25, "choices": _SHOP1_CHOICES},
    # legacy alias used by AI test floors
    "moneyShop": {"name": "moneyShop", "currency": "money", "cost": 25, "choices": _SHOP1_CHOICES},
    "moneyShop2": {
        "name": "Gold Shop (11F)", "currency": "money", "cost": 100,
        "choices": [
            {"id": "hp",  "label": "HP +4000", "changes": {"hp": 4000}},
            {"id": "atk", "label": "ATK +20",  "changes": {"atk": 20}},
            {"id": "def", "label": "DEF +20",  "changes": {"def": 20}},
        ],
    },
    "expShop1": {
        "name": "EXP Old Man (5F)", "currency": "exp", "cost": 30,
        "choices": [
            {"id": "level", "label": "Level up: HP +1000, ATK +7, DEF +7", "cost": 100,
             "changes": {"hp": 1000, "atk": 7, "def": 7, "lv": 1}},
            {"id": "atk", "label": "ATK +5", "cost": 30, "changes": {"atk": 5}},
            {"id": "def", "label": "DEF +5", "cost": 30, "changes": {"def": 5}},
        ],
    },
    "expShop2": {
        "name": "EXP Old Man (13F)", "currency": "exp", "cost": 95,
        "choices": [
            {"id": "level", "label": "Level up x3: HP +3000, ATK +20, DEF +20", "cost": 270,
             "changes": {"hp": 3000, "atk": 20, "def": 20, "lv": 3}},
            {"id": "atk", "label": "ATK +17", "cost": 95, "changes": {"atk": 17}},
            {"id": "def", "label": "DEF +17", "cost": 95, "changes": {"def": 17}},
        ],
    },
    "keyShop1": {
        "name": "Key Seller (5F)", "currency": "money", "cost": 10,
        "choices": [
            {"id": "buy_yellow", "label": "Buy Yellow Key", "cost": 10,  "changes": {"keys.yellow": 1}},
            {"id": "buy_blue",   "label": "Buy Blue Key",   "cost": 50,  "changes": {"keys.blue": 1}},
            {"id": "buy_red",    "label": "Buy Red Key",    "cost": 100, "changes": {"keys.red": 1}},
        ],
    },
    "keyShop2": {
        "name": "Key Buyer (12F)", "currency": "money", "cost": 0,
        "choices": [
            {"id": "sell_yellow", "label": "Sell Yellow Key for 7g",  "cost": 0, "requires_key": "yellow",
             "changes": {"keys.yellow": -1, "money": 7}},
            {"id": "sell_blue",   "label": "Sell Blue Key for 35g",   "cost": 0, "requires_key": "blue",
             "changes": {"keys.blue": -1, "money": 35}},
            {"id": "sell_red",    "label": "Sell Red Key for 70g",    "cost": 0, "requires_key": "red",
             "changes": {"keys.red": -1, "money": 70}},
        ],
    },
}


# ---------------------------------------------------------------------------
# Expert walkthrough checkpoints (community walkthrough, not distributed; values transcribed here)
# ---------------------------------------------------------------------------
# Hero stats quoted at the end of each walkthrough section ("此时生命…").
# `floor` is where the hero stands at that moment; `target` is the highest new
# floor the walkthrough reaches during the *next* section (segment goal; the
# walkthrough itself back-tracks, but engine stairs only go up). Floor contents
# are NOT restored (a segment run starts with every earlier floor untouched), so
# segments are somewhat easier than the walkthrough — state this when reporting.
WALKTHROUGH_CHECKPOINTS: list[dict] = [
    {"id": 0, "section": "start", "floor": "MT0", "target": "MT5",
     "hero": {"hp": 1000, "atk": 10, "def": 10, "money": 0, "exp": 0, "yellow": 1, "blue": 1, "red": 1}},
    {"id": 1, "section": "一 取圣光徽 (holy emblem)", "floor": "MT5", "target": "MT8",
     "hero": {"hp": 2640, "atk": 29, "def": 42, "money": 22, "exp": 136, "yellow": 4, "blue": 5, "red": 0}},
    {"id": 2, "section": "二 杀红蝙蝠 (red bat)", "floor": "MT8", "target": "MT11",
     "hero": {"hp": 823, "atk": 112, "def": 70, "money": 128, "exp": 23, "yellow": 5, "blue": 7, "red": 1}},
    {"id": 3, "section": "三 解救小偷 (rescue thief)", "floor": "MT4", "target": "MT13",
     "hero": {"hp": 714, "atk": 185, "def": 224, "money": 138, "exp": 181, "yellow": 8, "blue": 9, "red": 0}},
    {"id": 4, "section": "四 取十字架 (cross)", "floor": "MT7", "target": "MT13",
     "hero": {"hp": 5, "atk": 348, "def": 412, "money": 560, "exp": 759, "yellow": 16, "blue": 4, "red": 1}},
    {"id": 5, "section": "五 杀金队长 (gold captain)", "floor": "MT13", "target": "MT16",
     "hero": {"hp": 55, "atk": 696, "def": 625, "money": 78, "exp": 2314, "yellow": 3, "blue": 1, "red": 3}},
    {"id": 6, "section": "六 红衣魔王 (red demon king)", "floor": "MT12", "target": "MT19",
     "hero": {"hp": 1055, "atk": 1091, "def": 1020, "money": 752, "exp": 124, "yellow": 6, "blue": 1, "red": 2}},
    {"id": 7, "section": "七 冥灵魔王 (nether king)", "floor": "MT19", "target": "MT23w",
     "hero": {"hp": 4204, "atk": 2025, "def": 1707, "money": 320, "exp": 273, "yellow": 0, "blue": 0, "red": 0}},
]


def checkpoint_target_floor(checkpoint_id: int) -> str:
    """Segment goal floor for a checkpoint start."""
    return WALKTHROUGH_CHECKPOINTS[checkpoint_id]["target"]


def shop_unit(currency: str) -> str:
    return "exp" if currency == "exp" else "g"


def hero_balance(hero, currency: str) -> int:
    return hero.exp if currency == "exp" else hero.money


def apply_shop_effect(hero, action) -> None:
    """Debit the action's currency and apply its stat/key/money changes to `hero`."""
    if action.currency == "exp":
        hero.exp -= action.money_cost
    else:
        hero.money -= action.money_cost
    for stat, value in action.stat_changes.items():
        if stat == "hp":
            hero.hp += value
        elif stat == "atk":
            hero.atk += value
        elif stat == "def":
            hero.def_ += value
        elif stat == "mdef":
            hero.mdef += value
        elif stat == "money":
            hero.money += value
        elif stat == "keys.yellow":
            hero.keys.yellow += value
        elif stat == "keys.blue":
            hero.keys.blue += value
        elif stat == "keys.red":
            hero.keys.red += value
        elif stat == "lv":
            hero.lv += value


def shop_choice_affordable(hero, shop: dict, choice: dict) -> bool:
    currency = shop.get("currency", "money")
    cost = choice.get("cost", shop.get("cost", 0))
    if hero_balance(hero, currency) < cost:
        return False
    req = choice.get("requires_key")
    if req and getattr(hero.keys, req, 0) < 1:
        return False
    return True


# ---------------------------------------------------------------------------
# Game constants (from project/data.js)
# ---------------------------------------------------------------------------
BREAK_ARMOR_RATIO = 0.9     # Special 7: % of hero DEF as bonus damage
COUNTER_ATTACK_RATIO = 0.1  # Special 8: % of hero ATK per turn
PURIFY_MULTIPLIER = 3       # Special 9: multiplier on hero MDEF


# ---------------------------------------------------------------------------
# Tile classification helpers
# ---------------------------------------------------------------------------
def is_wall(tile: int) -> bool:
    return tile in TILE_WALLS or tile == 3

def is_ground(tile: int) -> bool:
    return tile == TILE_GROUND

def is_item(tile: int) -> bool:
    return tile in TILE_ITEMS

def is_door(tile: int) -> bool:
    return tile in TILE_DOORS

def is_enemy(tile: int) -> bool:
    return tile in TILE_ENEMIES

def is_npc(tile: int) -> bool:
    return tile in TILE_NPCS

def is_stairs(tile: int) -> bool:
    return tile in TILE_STAIRS

def is_terrain(tile: int) -> bool:
    return tile in TILE_TERRAINS

def is_walkable(tile: int) -> bool:
    """Is this tile walkable (ground, terrain, or stairs)."""
    return is_ground(tile) or is_terrain(tile) or is_stairs(tile)


# ---------------------------------------------------------------------------
# GameData — pluggable data context for custom floors
# ---------------------------------------------------------------------------

class GameData:
    """
    Wraps all data lookups. Supports custom monster stats, item effects,
    shop definitions, and extra enemy tile IDs (for AI test floors), plus — for
    foreign HTML5-mota projects (mota.game.project) — overriding tile classification
    (items, doors, NPCs, walls, terrains, stairs).

    When no overrides are given, delegates to the module-level defaults, so
    DEFAULT_GAME_DATA reproduces the hard-coded 24-layer tables exactly.
    """

    def __init__(
        self,
        custom_monsters: dict[str, Monster] | None = None,
        custom_items: dict[str, dict] | None = None,
        custom_shops: dict[str, dict] | None = None,
        extra_enemy_tiles: dict[int, str] | None = None,
        tile_items: dict[int, str] | None = None,
        tile_doors: dict[int, DoorType] | None = None,
        tile_npcs: dict[int, str] | None = None,
        tile_stairs: dict[int, str] | None = None,
        tile_walls: set[int] | None = None,
        tile_terrains: set[int] | None = None,
        source: str | None = None,
    ):
        self._custom_monsters = custom_monsters or {}
        self._custom_items = custom_items or {}
        self._custom_shops = custom_shops  # None = use defaults, {} = explicitly no shops
        self._extra_enemy_tiles = extra_enemy_tiles or {}
        # Tile-table overrides. None = module defaults; a dict/set REPLACES the default table.
        self._tile_items = tile_items
        self._tile_doors = tile_doors
        self._tile_npcs = tile_npcs
        self._tile_stairs = tile_stairs
        self._tile_walls = tile_walls
        self._tile_terrains = tile_terrains
        self.source = source or "24/project (built-in)"

    @property
    def tile_items(self) -> dict[int, str]:
        return self._tile_items if self._tile_items is not None else TILE_ITEMS

    @property
    def tile_doors(self) -> dict[int, DoorType]:
        return self._tile_doors if self._tile_doors is not None else TILE_DOORS

    @property
    def tile_npcs(self) -> dict[int, str]:
        return self._tile_npcs if self._tile_npcs is not None else TILE_NPCS

    @property
    def tile_stairs(self) -> dict[int, str]:
        return self._tile_stairs if self._tile_stairs is not None else TILE_STAIRS

    def is_enemy(self, tile: int) -> bool:
        return tile in TILE_ENEMIES or tile in self._extra_enemy_tiles

    def get_enemy_id(self, tile: int) -> str | None:
        if tile in self._extra_enemy_tiles:
            return self._extra_enemy_tiles[tile]
        return TILE_ENEMIES.get(tile)

    def get_item_id(self, tile: int) -> str | None:
        return self.tile_items.get(tile)

    def get_door_type(self, tile: int) -> DoorType | None:
        return self.tile_doors.get(tile)

    def get_npc_id(self, tile: int) -> str | None:
        return self.tile_npcs.get(tile)

    def get_stairs(self, tile: int) -> str | None:
        return self.tile_stairs.get(tile)

    def get_monster(self, monster_id: str) -> Monster:
        if monster_id in self._custom_monsters:
            m = self._custom_monsters[monster_id]
            return Monster(
                id=m.id, name=display_monster_name(m.id, m.name), hp=m.hp, atk=m.atk, def_=m.def_,
                money=m.money, exp=m.exp, special=m.special,
                damage=m.damage, vampire=m.vampire, n=m.n, name_zh=m.name_zh or m.name,
            )
        return get_monster(monster_id)

    def get_item_effect(self, item_id: str) -> dict:
        if item_id in self._custom_items:
            return self._custom_items[item_id]
        return get_item_effect(item_id)

    def get_shops(self) -> dict:
        if self._custom_shops is not None:
            return self._custom_shops
        return SHOPS

    # Tile classification — delegates to module-level tables unless overridden
    def is_wall(self, tile: int) -> bool:
        if self._tile_walls is not None:
            return tile in self._tile_walls
        return is_wall(tile)

    def is_ground(self, tile: int) -> bool:
        return is_ground(tile)

    def is_item(self, tile: int) -> bool:
        return tile in self.tile_items

    def is_door(self, tile: int) -> bool:
        return tile in self.tile_doors

    def is_npc(self, tile: int) -> bool:
        return tile in self.tile_npcs

    def is_stairs(self, tile: int) -> bool:
        return tile in self.tile_stairs

    def is_terrain(self, tile: int) -> bool:
        if self._tile_terrains is not None:
            return tile in self._tile_terrains
        return is_terrain(tile)

    def is_walkable(self, tile: int) -> bool:
        return self.is_ground(tile) or self.is_terrain(tile) or self.is_stairs(tile)


# Singleton default instance (no overrides)
DEFAULT_GAME_DATA = GameData()
