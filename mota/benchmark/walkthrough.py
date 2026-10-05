"""
Walkthrough baseline for MT3 — structured from walkthrough2.txt.

The canonical walkthrough for Floor 3 (3F):
  Start: HP=860, ATK=10, DEF=10, Gold=5, EXP=4, Keys Y=1/B=0/R=0
  
  Phase 1: Kill accessible enemies before sword
    - Kill bat (-190 → 670 HP... wait, walkthrough says kill bat(-190) + 2 greenSlimes(-100) → 570)
    
  The walkthrough text for 3F:
    "3F：杀小蝙蝠-190、2绿头怪-100，剩下570；
     开黄门杀骷髅人-315、红头怪-40，剩下215；
     取黄钥匙3、铁剑+10=20ATK；
     杀2小蝙蝠-120、红头怪-15，剩下80；
     开黄门杀红头怪-15，剩下65；
     取黄钥匙5、红宝石+3=23ATK、蓝宝石+3=13DEF、喝大血瓶加到565；
     向上杀骷髅人-72=493；
     开黄门开启3F金币商店；
     金币买防御+4=17DEF；
     杀3小蝙蝠-45、4红头怪，剩下448"
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class WalkthroughCheckpoint:
    """A checkpoint in the walkthrough with expected hero state after a group of actions."""
    phase: str          # Phase description
    hp_after: int       # Expected HP after this phase
    atk_after: int      # Expected ATK
    def_after: int      # Expected DEF
    money_after: int    # Expected gold (approximate)
    actions_desc: str   # Human-readable action summary


# MT3 walkthrough phases (from walkthrough2.txt)
MT3_CHECKPOINTS = [
    WalkthroughCheckpoint(
        phase="Kill bat + 2 green slimes",
        hp_after=570, atk_after=10, def_after=10, money_after=10,
        actions_desc="Kill bat(-190), 2 greenSlime(-100) → 570 HP",
    ),
    WalkthroughCheckpoint(
        phase="Open yellow door, kill skeleton + red slime",
        hp_after=215, atk_after=10, def_after=10, money_after=17,
        actions_desc="Open Y-door, kill skeleton(-315), redSlime(-40) → 215 HP",
    ),
    WalkthroughCheckpoint(
        phase="Collect sword + 3 yellow keys",
        hp_after=215, atk_after=20, def_after=10, money_after=17,
        actions_desc="Collect sword1(+10 ATK=20), 3 yellowKeys",
    ),
    WalkthroughCheckpoint(
        phase="Kill 2 bats + red slime",
        hp_after=80, atk_after=20, def_after=10, money_after=25,
        actions_desc="Kill 2 bat(-120), redSlime(-15) → 80 HP",
    ),
    WalkthroughCheckpoint(
        phase="Open door, kill red slime",
        hp_after=65, atk_after=20, def_after=10, money_after=27,
        actions_desc="Open Y-door, kill redSlime(-15) → 65 HP",
    ),
    WalkthroughCheckpoint(
        phase="Collect gems + potion + 5 keys",
        hp_after=565, atk_after=23, def_after=13, money_after=27,
        actions_desc="Collect 5 Y-keys, redGem(+3 ATK=23), blueGem(+3 DEF=13), bluePotion(+500=565)",
    ),
    WalkthroughCheckpoint(
        phase="Kill skeleton upward",
        hp_after=493, atk_after=23, def_after=13, money_after=32,
        actions_desc="Kill skeleton(-72) → 493 HP",
    ),
    WalkthroughCheckpoint(
        phase="Open door, activate shop, buy DEF+4",
        hp_after=493, atk_after=23, def_after=17, money_after=7,
        actions_desc="Open Y-door, visit shop, buy DEF+4=17DEF (cost 25g)",
    ),
    WalkthroughCheckpoint(
        phase="Kill remaining 3 bats + 4 red slimes",
        hp_after=448, atk_after=23, def_after=17, money_after=23,
        actions_desc="Kill 3 bat(-45), 4 redSlime(0 damage each) → 448 HP",
    ),
]

# Final expected state after MT3 full clear
MT3_FINAL = {
    "hp": 448,
    "atk": 23,
    "def": 17,
    "money": 23,
    "exp": 46,
    "keys_yellow": 6,
    "keys_blue": 0,
    "keys_red": 0,
    "enemies_remaining": 0,
}

# Starting state for MT3 (entering from 1F)
MT3_START = {
    "hp": 860,
    "atk": 10,
    "def": 10,
    "mdef": 0,
    "money": 5,
    "exp": 4,
    "keys": {"yellow": 1, "blue": 0, "red": 0},
    "x": 1,
    "y": 11,
}
