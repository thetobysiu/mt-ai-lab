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
What follows from the game rules or from expert play but is not enforced by the game, labelled by its source (mainly the combat formula, the exact solver or the expert walkthrough; also a design choice of this thesis, the tower's structure or a game rule).
_Avoid_: tip, advanced rule, heuristic (that is the rule-based agent)

**Prompt rule**:
A strategy principle as written in a system prompt (the numbered rules of the single-floor or the tower prompt). The walkthrough-only principles S11 to S14 are never prompt rules.
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
The prompt that the (1+1) loop produces on the complex floor alone with the validator switched off, so that it may learn positions and orders from its own traces. Allowed to contain floor-specific knowledge; the prompt produced names no position. A labelled condition, never a default.
_Avoid_: self-compiled route, evolved prompt (that is the validator-on result)

**Simple floor**:
The 11 × 11 boss floor of the published solver's test maps (exact optimum 13 HP) on which the observation was developed, on which the error analysis is done, and which is the running example of the thesis.
_Avoid_: reference floor, development floor (as a name; acceptable once as a description), 单层-最简单

**Hit points (HP)**:
The hero's health value; a fight costs HP, potions add HP, and the hero dies at 0.
_Avoid_: health, health points

**Planning horizon**:
How many actions the model commits to per call: one (reactive control), k (commit-k), as many as it can (long plan) or all in one call (single-call plan).
_Avoid_: planning granularity, granularity, one-shot plan ("-shot" counts examples)

**Strategic override**:
An engine replacement of the model's choice by a judgement of the rule-based heuristic (a much cheaper alternative, or the 40 % override of the first and second tower observations). Never present in a reported result of the final configuration.
_Avoid_: correction, safety correction, silent correction, engine correction

**Mechanical override**:
An engine replacement of a choice that cannot be executed usefully: a dead-end door, an unwinnable or a lethal fight. Logged per turn in every episode; off in the compiled-knowledge conditions.
_Avoid_: safety correction, assist (assists are the automatic collections and 0-HP fights)

**Tower observation**:
One of the three versions of what the engine shows the model on the tower, compared in Table 6.13: the first (current floor, up-staircase and returns), the second (every reachable object on every visited floor) and the final one.
_Avoid_: tower design, design N, stack, final2/final3/final11 (those are result-file labels, mapped in Table D.5)

**Final configuration**:
The settings every single-floor episode uses unless an experiment states otherwise (temperature 0, lookahead depth 3, no conversation history, all annotations, assists and mechanical overrides only).
_Avoid_: final stack, final2

**Cell**:
One configuration with one model on one floor (or the tower), played N times; one entry of a results table, backed by one result file (Table D.4).
_Avoid_: experiment (ambiguous), condition (for a single cell), run (for its episodes)

**Highest floor reached**:
The outcome of a tower run: the highest floor the hero ever stood on, whatever floor the run ended on.
_Avoid_: max floor, floors cleared, ceiling

**State value**:
The highest final HP that the exact solver can still reach from a state of an episode; none when the boss can no longer be defeated. The decision after which it becomes none is the decision that lost the episode.
_Avoid_: crucial point (informal), regret (alone)

**Way up**:
The cheapest route on the highest visited floor to its up-staircase, with the exact cost of each fight on it at the hero's attributes.
_Avoid_: progress gate, stat needs

**Plan memory**:
The one-line to-do list the model writes at the end of each tower answer (what comes next and why, and what gold, EXP or keys it is saving for), shown at its next decision with the actions taken since. Nothing in it is executed.
_Avoid_: notes, memory (alone), commitment (Section 5.5.2)

**Treasure**:
A one-off item that changes the run when collected: equipment, feathers, key boxes, the Cross, Holy Water, or a character that hands such an item over.
_Avoid_: key item (collides with keys), special item, unique item

**Rule 4 threshold**:
The share of current HP above which the prompt tells the model not to fight, also called the HP limit: 40 % on single floors (rule 3 of the single-floor prompt, which numbers its rules differently) and with the first and second tower observations, 60 % with the final tower observation (rule 4 of the tower prompt). A prompt rule; only the first and second tower observations enforced it, by a strategic override.
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
A result obtained with a prompt that contains floor-specific knowledge (the solver-route and exact-route prompts); always labelled, never a default, and run without mechanical overrides and automatic 0-HP fights.
_Avoid_: oracle prompt

**Re-run of Table 6.2**:
The repetition of every cell of the main results table on the final version of the code, five episodes per cell (ten for Qwen3.6-35B with the solver-route prompt; three runs per tower cell); earlier episodes of the same configuration are reported only where labelled.
_Avoid_: canonical run, canon

**Rule-based heuristic**:
The agent that acts on the same engine output by fixed priorities, without a language model; the baseline of every floor.
_Avoid_: greedy agent, heuristic agent (when the strategy principle is meant)

**Assist**:
An action the engine takes without asking the model: collecting items and keys, fighting monsters that cost 0 HP, and on the tower opening ice gates and climbing to a floor not yet visited. Its turn is an assisted turn.
_Avoid_: override (that replaces a choice), auto-play, forced turn (forced is the solver's term)

**Published solver**:
The breadth-first solver released with the game's AI test maps; it keeps the first state taken from the queue per cleared set and reports 22 HP on the complex floor.
_Avoid_: Java BFS, BFS solver, original solver

**Exact solver**:
The same search with the dominance test also applied when a state is taken from the queue; it computes the optimum of every single floor (68 HP on the complex floor).
_Avoid_: corrected solver (acceptable once as a description), BFS optimum

**Episode**:
One play of a single floor from its start state; success rates count episodes.
_Avoid_: run (reserved for the tower), rollout

**Turn**:
One executed action of an episode or run, chosen by the model or taken by the engine, numbered from 1; the observation's header shows the turns completed. On the simple floor, the engine's key pickup is turn 1.
_Avoid_: step (except in an algorithm listing and for a plan step, one entry of a committed plan)

**Decision**:
A turn at which the model is asked to choose; for the solver, the clearing of one monster or door (or a merged group of them).
_Avoid_: turn (when the engine acted alone), move

**Winning set**:
The set of monsters and doors cleared on a winning route; a floor with one winning set can be won in only one way, up to order.
_Avoid_: set of fights, winning route (that is an order)

**Optimal route**:
The order of actions with which the exact solver reaches the optimum of a floor.
_Avoid_: BFS route, solver route (that is the published solver's route in the solver-route prompt)

**Winning trajectory**:
The sequence of actions that the winning episodes of a configuration share; on the simple floor it is the optimal route with the Slime Lord (1,9) taken at turn 15, before the Bat (3,5), and ends at 2 HP (Table 4.4, last column).
_Avoid_: winning route, optimal route (it is not optimal)

**Slack**:
The final HP of the optimal route (13 on the simple floor): a decision that wastes this much HP or more loses the floor. After a decision that lowers the state value, the remaining slack is the new state value (2 on the winning trajectory from turn 15).
_Avoid_: margin (reserved for the HP-budget line of the observation), margin for error

**Region (simple floor)**:
A part of the simple floor opened by one door or monster: central corridor, left corridor, boss corridor, lower-left room, top-right room, top-left corner, right-hand rooms (Section 4.5.1). Used at first mention next to a coordinate.
_Avoid_: wing (used only for hand01's two halves), area

**Departure**:
The first action at which an episode leaves the winning trajectory; it loses the floor only if the state value after it is none.
_Avoid_: failure (when the state value is still positive)

**Run**:
One play of the tower from MT0, or a continuation of a stored tower run; reported by the highest floor reached. An optimiser run is one execution of the (1+1) or Pareto loop.
_Avoid_: episode (for the tower), trial (except for the trial before the paired confirmation), run (for a set of single-floor episodes: earlier episodes, cell)

**Resumed run**:
A stored tower run continued from a given turn on the current engine, used to test a chain of events from a fixed position.
_Avoid_: replay (that is re-showing a stored episode)

**Held-out floors**:
The generated floors gen03 to gen15, on which no prompt or annotation was developed; gen01 and gen02 are training floors of the prompt optimisation study.
_Avoid_: test set (alone), unseen floors

**Noise floor**:
The score difference between two evaluations of the same prompt, measured with byte-identical prompts; the smallest difference between prompts that can be read as an effect.
_Avoid_: noise band

**Validity incident**:
A dated defect of the measurement, not of the agent, that moved or could have moved a result; all are listed in Appendix E, and Section 7.3 draws six lessons from them.
_Avoid_: bug, I-1 … I-6

**Expert walkthrough**:
The anonymous Chinese community walkthrough of the 24-floor tower, the source of the walkthrough principles; cited as (Expert walkthrough, n.d.).
_Avoid_: guide, strategy guide

**Critical action / forced action**:
An action on the optimal route at which at least one alternative (critical) or every alternative (forced) makes the boss unwinnable.
_Avoid_: key decision (collides with keys), critical/forced decision, forced (alone, for the engine's assisted turns)
