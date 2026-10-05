# Engine and observation

## The game

Magic Tower is a deterministic, turn-based puzzle on a grid. The hero has hit points (HP), attack
(ATK) and defence (DEF), on some floors also magic defence (MDEF). Monsters, doors and items block
the way; walking is free.

- **Fights** are exact: the hero strikes first, each hit removes `ATK − monster DEF`, the monster hits
  back for `monster ATK − DEF` per round. A fight cannot be won if `ATK ≤ monster DEF`, and costs no HP
  if `DEF ≥ monster ATK`. HP cost = `max(0, monATK − DEF) × (ceil(monHP / (ATK − monDEF)) − 1)`;
  special abilities (first strike, double attack, magic attack, break armour, …) change it
  (`mota/game/damage.py`).
- **Doors** need a key of their colour (yellow, blue, red); keys are scarce.
- **Items**: gems raise ATK, DEF or MDEF, potions restore HP, keys open doors.
- **Single floors** are won by defeating the boss alive; the score is the HP left.
- **The tower** (24 floors, MT0–MT23) adds stairs, shops (gold and experience), scripted events and
  keys shared by all floors.

The order of fights, doors and items decides the outcome: the same set of fights can leave very
different HP depending on which stat items were collected first.

## What the engine does

1. **Reachability.** A breadth-first search finds every tile the hero can walk to without passing a
   monster or a closed door. Every monster, door, item, shop and staircase next to that region is one
   candidate action. The model chooses a target; the engine walks the shortest path.
2. **Exact consequences.** For every fight, the HP cost with the full damage formula and the HP left.
3. **Lookahead.** For every fight and door, the engine simulates the action and searches again: what
   becomes reachable (items, keys, doors, monsters, the boss), and behind each further *gateway*
   (a monster or door) what it opens, up to three gateways deep (two on the tower).

## The observation

The text the model receives at each decision: a state block and the numbered actions with their
annotations. A complete example is in the thesis (Listing 5.1); the code is
`GameState.format_state` and `GameState.format_actions` in `mota/game/state.py`.

| Annotation | Where | Content |
|---|---|---|
| Damage and HP after | every fight | `damage=55 (13.8%) hpAfter=345` |
| Status tags | fights, doors | `[SAFE]` ≤ 15 % of HP, `[MODERATE]` ≤ 30 %, `[RISKY]`, `[LETHAL]`, `[WINNABLE at ATK≥x]`, `FREE if DEF≥x`, `[OPTIONAL]`, `[DEAD END]`, alternative-route tag |
| Cost at maximum stats | winnable fights | `min-cost@maxStats`: cost after every remaining stat item is collected |
| DEF threshold tip | state block | smallest DEF gain that makes a group of monsters free |
| Lookahead tree | fights, doors | `→ unlocks: …`, `→ via [gateway]: …` with each gateway's cost |
| Lookahead value, effective cost | fights, doors | HP-equivalent of unlocked stat items and keys, net of gateway costs; effective cost = HP cost − value; potions listed separately |
| Net stat-route line | actions with stat items behind them | HP of fighting to reach them, HP they save on the other listed fights, net balance |
| Fight-order line | fights a listed route makes cheaper | HP wasted by fighting now, and after which action it is cheaper; never recommends a first step above the HP-rule threshold |
| Key line, key budget | doors, fights exposing keys, state block | keys used and gained, doors exposed, last-key warning; keys held and on the floor versus closed doors |
| Boss line, HP budget | state block | whether the boss is winnable now, ATK needed, HP needed at maximum stats for the monsters that block the way |

The tower adds lines for shops, stairs, the way up to the next floor, scripted events, key reserves
and plan memory; [configuration](configuration.md) lists the switches that turn them on.

**Bare observation** (`MOTA_BARE_OBS=1`): attributes, items, boss and the numbered actions with exact
costs only, no tree, tags or lines. **Map-only condition** (`--mode map-enum`): no action list at all;
the model lists its own options from the grid.

## Assists and overrides

The engine takes decisions that need no judgement and records them as *forced* turns: collecting a
reachable item or key, fighting a 0-HP monster, and on the tower taking the stairs to a floor never
visited. A *mechanical override* replaces a dead-end door, an unwinnable fight, or a lethal fight while
a non-lethal action exists; if only lethal or unwinnable fights remain, the episode ends as stuck.
Every override is logged with the model's original choice (`corrected_from`, `override` events).

*Strategic overrides* (the heuristic replacing a choice it judges worse) existed in the development
phase and produced the early wins; they are off unless `MOTA_STRATEGIC_OVERRIDES=1`.
`MOTA_DISABLE_OVERRIDES=1` switches off every assist and override.

## Answer parsing

The model ends its answer with `FINAL_CHOICE: <n>` (committed plans: also a `NEXT:` or `PLAN:` line).
An answer without a valid number goes to one repair call with reasoning disabled and constrained
decoding (a JSON object with one integer field restricted to the listed actions, excluding actions a
mechanical override would replace). After three failed requests at one decision the heuristic's action
is taken; every repair and fallback is logged.

## The tower engine

`mota/game/multi_floor.py` runs MT0 → MT23w. Stairs only go up; with `MOTA_REMOTE_ACTIONS=1` every
reachable object on every visited floor is an action and travel is part of the action. All six shops of
the game are modelled and registered on first contact. Scripted events that the engine models and
those it does not are listed per floor on the Maps page (`scripts/inventory_floor_events.py`).
`MOTA_TOWER_FIDELITY=1` selects the corrected engine of the final tower designs.
