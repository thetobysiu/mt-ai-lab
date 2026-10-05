# Glossary

The terms of the thesis and of this documentation: an LLM agent plays Magic Tower on single floors and on the multi-floor tower, grounded by a deterministic engine. Each entry ends with terms to avoid because they are ambiguous.

## Language

**Normal ending**:
The end of the game reached by defeating the Nether Demon King on MT21; a tower run that reaches it has won. The floors above it lead to a hidden ending that is out of scope.
_Avoid_: final boss (ambiguous with the hidden ending), clear, beat the tower

**Game rule**:
What the game itself enforces: movement, the combat formula, keys used up by doors, items and shops.
_Avoid_: mechanic (when it means a strategy), basic rule

**Strategy principle**:
What follows from the game rules or from expert play but is not enforced by the game, labelled by its source (the combat formula, the exact solver, or the expert walkthrough).
_Avoid_: tip, advanced rule, heuristic (that is the rule-based agent)

**Prompt rule**:
A strategy principle as written in a system prompt (the numbered rules 1–6 of the tower prompt). Walkthrough principles are never prompt rules.
_Avoid_: strategy rule (ambiguous between the two above)

**Scripted event**:
A script attached to a tile that changes the map or the hero beyond what the tile's kind does (a character opening a passage on another floor, a trade, a seal, a script after a fight). Shops are not scripted events; they are part of the game rules.
_Avoid_: event (alone; also the engine's log entries), NPC

**Single-floor prompt**:
The one general system prompt used on every single floor: combat rules, how to read the observation, five prompt rules; nothing specific to a floor.
_Avoid_: basic prompt, floor_basic, seed prompt

**Solver-route prompt**:
A prompt for the complex floor only that lists the route found by the published solver: the fights allowed by position, the fights forbidden, the door order and the phases, plus a rule never to take a lethal fight. The plan-execution reference: it measures whether a model can carry out a given route, not whether it can find one. A compiled-knowledge condition, always reported next to, never instead of, the single-floor prompt.
_Avoid_: route prompt (alone), BFS prompt, survival prompt, complex_bfs_strategy

**Rules-only prompt**:
The starting prompt of the prompt optimisation study: the game rules, the goal and the answer format, and no strategy.
_Avoid_: core prompt, core_rules, seed (a seed is whatever prompt a run starts from)

**Teacher**:
The model that reads the traces of a prompt's episodes and writes a diagnosis and one revised prompt; called the reflection model by Agrawal et al. (2025).
_Avoid_: reflector, reflection model, optimiser model

**Validator**:
The check that rejects a revised prompt that contains floor-specific knowledge (coordinates, names, routes, allowed or forbidden lists, numbers taken from a floor).
_Avoid_: filter, guard

**(1+1) loop**:
Prompt evolution with one prompt at a time: the teacher rewrites the best prompt so far, and the rewrite replaces it only if it scores at least as well. An evolutionary algorithm with a population of one, mutation by the teacher and elitist selection.
_Avoid_: constrained GEPA, cGEPA, GEPA (it has no Pareto selection and no merge)

**Pareto loop**:
Prompt evolution with a population: every prompt is scored on each training floor, the parent of the next rewrite is drawn from the prompts that are best on at least one floor, and once two such prompts are merged into one. Follows GEPA's selection idea without using the GEPA library.
_Avoid_: GEPA run, full GEPA

**Evolved prompt**:
The best prompt of a (1+1) or Pareto loop run with the validator on; it contains no floor-specific knowledge.
_Avoid_: optimised prompt, GEPA prompt, rewrite (that is any candidate the teacher writes)

**Evolved-route prompt**:
The prompt that the (1+1) loop produces on the complex floor alone with the validator switched off, so that it may learn positions and orders from its own traces. Floor-specific knowledge like the solver-route prompt: a labelled condition, never a default.
_Avoid_: self-compiled route, evolved prompt (that is the validator-on result)

**Simple floor**:
The 11 × 11 boss floor of the published solver's test maps (exact optimum 13 HP) on which the observation was developed and on which the error analysis is done.
_Avoid_: reference floor, development floor (as a name; acceptable once as a description), 单层-最简单

**Hit points (HP)**:
The hero's health value; a fight costs HP, potions add HP, and the hero dies at 0.
_Avoid_: health, health points

**Planning horizon**:
How many actions the model commits to per call: one (reactive control), k (commit-k), as many as it can (long plan) or all in one call (single-call plan).
_Avoid_: planning granularity, granularity, one-shot plan ("-shot" counts examples)

**Strategic override**:
An engine replacement of the model's choice by a judgement of the rule-based heuristic (a much cheaper alternative, the 40 % rule of tower designs 1 to 4). Never present in a reported result of the final configuration.
_Avoid_: correction, safety correction, silent correction, engine correction

**Mechanical override**:
An engine replacement of a choice that cannot be executed usefully: a dead-end door, an unwinnable or a lethal fight. Logged per turn in every episode.
_Avoid_: safety correction, assist (assists are the automatic collections and 0-HP fights)

**Tower design**:
One numbered version (1–7) of what the engine shows the model on the tower: the action list, the state lines and the matching tower prompt. Each design was introduced because of how the runs of the previous one stopped. Design 6 adds the MT15 trades, the key-reserve line (including the keys the way up still needs) and the monster upgrades after the Red Demon King to design 5. Design 7 adds a quantity for shop purchases, the vampire ability (prompt and fight line) and the way and missing keys for event items and seal guards; it is the final design. Design 7b is design 7 with blue keys for sale, as in the original game.
_Avoid_: version, stack, final2…final7 (those are result-file labels, mapped in Appendix F)

**Final configuration**:
The settings every single-floor episode uses unless an experiment states otherwise (temperature 0, lookahead depth 3, no conversation history, all annotations, mechanical assists only).
_Avoid_: final stack, final2

**Highest floor reached**:
The outcome of a tower run: the highest floor the hero ever stood on, whatever floor the run ended on.
_Avoid_: max floor, floors cleared, ceiling

**State value**:
The highest final HP that the exact solver can still reach from a state of an episode; none when the boss can no longer be defeated. The decision after which it becomes none is the decision that lost the episode.
_Avoid_: crucial point (informal), regret (alone)

**Way up**:
The cheapest route from the hero to the up-staircase of the highest visited floor whose next floor has not been visited, with the exact cost of each fight on it.
_Avoid_: progress gate, stat needs

**Corrected engine**:
The tower engine of designs 5 to 7: models the MT4 thief, the Cross at the MT0 fairy, the hero's level with the Small and Big Feathers and the seal in front of the Cross, and uses the game data's item values (from design 6 also the MT15 trades and the monster upgrades after the Red Demon King).
_Avoid_: fidelity mode, final6

**Plan memory**:
The one-line to-do list the model writes at the end of each tower answer (what comes next and why, and what gold, EXP or keys it is saving for), shown at its next decision with the actions taken since. Nothing in it is executed.
_Avoid_: notes, memory (the floor-change notes of the development history), commitment (Section 5.5.2)

**Treasure**:
A one-off item that changes the run when collected: equipment, feathers, key boxes, the Cross, Holy Water, or a character that hands such an item over.
_Avoid_: key item (collides with keys), special item, unique item

**Rule 4 threshold**:
The share of current HP above which the prompt tells the model not to fight: 40 % on single floors (rule 3 of the single-floor prompt, which numbers its rules differently), 60 % on the tower since design 5 (rule 4 of the tower prompt). A prompt rule, never enforced by the engine in the final designs.
_Avoid_: HP floor (that is the removed override)

**One-sided annotation**:
An annotation that states one side of a trade-off without the other: a saving without the cost of reaching it, a value that counts potions as fight value, an efficiency without its affordability, a deficit without its scope, or a count without its multiplicity.
_Avoid_: misleading hint, bad annotation

**Bare observation**:
The observation reduced to the enumerated actions with their exact costs: no lookahead tree, tags or annotation lines.
_Avoid_: bare obs, raw view

**Map-only condition**:
The condition without an action list: the model reads the grid, lists its own options and names a target by position.
_Avoid_: map-enum

**Exact-route prompt**:
A prompt for the complex floor only that lists the decisions of the exact optimal route with the HP expected after each. A compiled-knowledge condition like the solver-route prompt.
_Avoid_: exact68 prompt

**Compiled-knowledge condition**:
A result obtained with a prompt that contains floor-specific knowledge (the solver-route, exact-route and evolved-route prompts); always labelled, never a default.
_Avoid_: oracle prompt

**Re-run of Table 6.2**:
The repetition of every cell of the main results table on the final version of the code, five episodes per cell; earlier runs of the same configuration are reported only where labelled.
_Avoid_: canonical run, canon

**Rule-based heuristic**:
The agent that acts on the same engine output by fixed priorities, without a language model; the baseline of every floor.
_Avoid_: greedy agent, heuristic agent (when the strategy principle is meant)

**Assist**:
An action the engine takes without asking the model: collecting items and keys, fighting monsters that cost 0 HP, and on the tower climbing to a floor not yet visited. Logged as forced turns.
_Avoid_: override (that replaces a choice), auto-play

**Published solver**:
The breadth-first solver released with the game's AI test maps; it keeps the first state taken from the queue per cleared set and reports 22 HP on the complex floor.
_Avoid_: Java BFS, BFS solver, original solver

**Exact solver**:
The same search with the dominance test also applied when a state is taken from the queue; it computes the optimum of every single floor (68 HP on the complex floor).
_Avoid_: corrected solver (acceptable once as a description), BFS optimum

**Episode**:
One play of a single floor from its start state; success rates count episodes.
_Avoid_: run (reserved for the tower), rollout

**Run**:
One play of the tower from MT0, or a continuation of a stored tower run; reported by the highest floor reached.
_Avoid_: episode (for the tower), trial

**Resumed run**:
A stored tower run continued from a given turn on the current engine, used to test a chain of events from a fixed position.
_Avoid_: replay (that is re-showing a stored episode)

**Held-out floors**:
The generated floors gen03 to gen15, on which no prompt or annotation was developed; gen01 and gen02 are training floors of the prompt optimisation study.
_Avoid_: test set (alone), unseen floors

**Noise floor**:
The score difference between two runs of the same prompt, measured with byte-identical prompts; the smallest difference between prompts that can be read as an effect.
_Avoid_: noise band

**Validity incident**:
A dated defect of the measurement, not of the agent, that moved or could have moved a result; all are listed in Appendix H, and Section 7.3 draws six lessons from them.
_Avoid_: bug, I-1 … I-6

**Expert walkthrough**:
The anonymous Chinese community walkthrough of the 24-floor tower, the source of the walkthrough principles; cited as (Expert walkthrough, n.d.).
_Avoid_: guide, strategy guide

**Critical action / forced action**:
An action on the optimal route at which at least one alternative (critical) or every alternative (forced) makes the boss unwinnable.
_Avoid_: key decision (collides with keys)
