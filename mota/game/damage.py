"""
Deterministic damage calculator for MOTA combat.
Port of mota-comm-framework/src/core/damage-calculator.js
"""
from __future__ import annotations
import math
from .types import Hero, Monster, BattleResult
from .data import BREAK_ARMOR_RATIO, COUNTER_ATTACK_RATIO, PURIFY_MULTIPLIER


def calculate(hero: Hero, monster: Monster) -> BattleResult:
    """Calculate the deterministic outcome of hero vs monster combat."""
    specials = monster.specials
    h_atk = hero.atk
    h_def = hero.def_
    h_mdef = hero.mdef
    h_hp = hero.hp

    m_hp = monster.hp
    m_atk = monster.atk
    m_def = monster.def_

    # --- Special ability pre-processing ---

    # Mimic (10): monster copies hero stats
    if 10 in specials:
        m_atk = h_atk
        m_def = h_def

    # Solid (3): monster DEF = heroATK - 1 if lower
    if 3 in specials:
        if m_def < h_atk - 1:
            m_def = h_atk - 1

    # Hero's damage per hit on monster
    hero_dmg_per_hit = max(0, h_atk - m_def)
    if hero_dmg_per_hit <= 0:
        return BattleResult(can_win=False, total_damage=999999999, hp_after=-1, turns=0)

    # Turns to kill
    turns = math.ceil(m_hp / hero_dmg_per_hit)

    # --- Monster damage per hit on hero ---

    # Magic Attack (2): ignores hero DEF
    if 2 in specials:
        per_damage = m_atk
    else:
        per_damage = max(0, m_atk - h_def)

    # Multi-hit multipliers
    if 4 in specials:
        per_damage *= 2
    elif 5 in specials:
        per_damage *= 3
    elif 6 in specials:
        n_hits = monster.n if monster.n > 0 else 4
        per_damage *= n_hits

    # --- Pre-combat / bonus damage ---
    init_damage = 0

    # First Strike (1): one free hit before combat
    if 1 in specials:
        init_damage += per_damage

    # Vampire (11): absorbs % of hero HP
    if 11 in specials:
        vamp_ratio = monster.vampire if monster.vampire > 0 else 0.0
        init_damage += int(h_hp * vamp_ratio)

    # Break Armor (7): bonus = floor(breakArmor * heroDEF)
    if 7 in specials:
        init_damage += int(BREAK_ARMOR_RATIO * h_def)

    # Purify (9): bonus = purifyMultiplier * heroMDEF
    if 9 in specials:
        init_damage += PURIFY_MULTIPLIER * h_mdef

    # --- Counter attack damage per turn ---
    counter_per_turn = 0
    if 8 in specials:
        counter_per_turn = int(COUNTER_ATTACK_RATIO * h_atk)

    # --- Total damage ---
    # Hero takes (turns - 1) normal hits + counter damage each turn + init damage
    # Counter fires in rounds where the monster is still alive to retaliate:
    # that is (turns - 1) rounds (not turns), matching Java: per_damage added into
    # per_hit and multiplied by (monHP-1)/(heroATK-monDEF) = turns - 1.
    combat_damage = per_damage * (turns - 1)
    counter_damage = counter_per_turn * (turns - 1)
    total = init_damage + combat_damage + counter_damage

    # Fixed damage (22): added on top
    if 22 in specials:
        total += monster.damage

    # Subtract MDEF shield
    total = max(0, total - h_mdef)

    hp_after = h_hp - total
    return BattleResult(
        can_win=hp_after > 0,
        total_damage=total,
        hp_after=hp_after,
        turns=turns,
    )
