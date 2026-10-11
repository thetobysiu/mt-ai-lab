# Development history

This document keeps the material that was removed from the thesis in its final revision: the development
history of the agent and of the tower observation, superseded and excluded runs, and two pilots that are
not part of the thesis. The text is reproduced verbatim from the version before that revision, so section,
table, figure and appendix numbers refer to that version (for example, its Appendix F is Appendix D of the
final thesis, and its tower designs 1, 2 and 7 are the first, second and final tower observation).
The results themselves are unchanged and stay in `results/`.

## Contents

1. Removed from the main chapters: the tower designs (Chapter 5), the failure census, the tower runs by
   design with the 40 % override and the threshold replay, the supporting pilots (Chapter 6), and the
   discussion of the tower designs (Chapter 7).
2. Former Appendix D: Development History (experiment ledger E1 to E27, prompt-engineering case study,
   composite score, excluded runs, development of the tower designs).
3. Former Appendix E: The Fine-Tuned Small Model.
4. Former Appendix G: Monsters of the Tower.

## 1. Removed from the main chapters

#### 5.5.4 The Tower Loop

On the tower, the loop is the same; what changes is the observation.
It was developed in seven numbered *tower designs*, each introduced because of how the runs of the previous design stopped.
Table 5.2 lists what each design adds and the stop that motivated it; Chapter 6 reports the runs of every design side by side (Table 6.13).
The tower planning comparison used designs 1 and 2 and a development version of design 5 (Table 6.9).
The earlier tower prompts are listed in Appendix A.2, and Appendix D.4 describes the development of the designs.

**Table 5.2:** Tower designs. Each row lists what the design adds to the one before it and how the runs of the earlier designs stopped. Designs 1 to 4 ran with the strategic 40 % override of Section 5.6 (Table 6.13 also reports designs 3 and 4 without it); designs 5 to 7 run without it, on the corrected engine (Section 4.5.2). Design 7 is the final design.

| Design | What it adds to the observation or the engine | The stop of the previous design that motivated it |
|---|---|---|
| 1 | The current floor's actions, the up-staircase and *return* actions to earlier floors, climbing back one staircase per floor; other floors summarised in one line; keys counted per floor; shop rule "ATK above the highest DEF in scope" | none (first design) |
| 2 | Every reachable object on every visited floor, each floor with the full observation; travel inside the action; staircases only to unvisited floors; a tower-wide key budget; the price of the way to an unreached shop | Every run stopped at or below MT7; models shuttled between floors, one choosing the return to MT1 five times without opening the door it was offered for |
| 3 | The *stat-needs* line: the strongest pending monsters on all visited floors, with the ATK at which each becomes winnable and the ATK or DEF at which it costs at most 40 % of current HP; the shop rule in the affordability form | All four runs stopped on MT8 with ATK 79 to 92 against Red Bats of DEF 90, which cost about 15,000 HP even at ATK 92: the shop rule was met, and the fights were still unaffordable |
| 4 | The *way-up* line in place of the stat-needs line | The stat-needs line took the strongest monster seen as the reference for purchases, but early floors show monsters of later floors that are never on the way |
| 5 | The corrected engine; no 40 % override, and rule 4 at 60 %; plan memory (Section 5.5.5); no yellow or blue keys for sale; the in-order form of the way-up line; the purchase, price-per-point, event, treasure, red-door and Cross lines | Designs 1 to 4: in nine of the ten runs that stopped on MT3, the 40 % override had first replaced the model's choice of a Skeleton at 55 or 56 % of HP, and the same fight was taken later at 83 to 93 %; a run spent its last gold on a yellow key on MT8 and paid HP for fights that affordable DEF purchases would have made free; the way-up line priced the route at the current attributes and called a lethal fight unwinnable |
| 6 | The MT15 trades as actions; the key-reserve line; the scripted events marked 6 in Table 4.4, among them the upgrade of four kinds of monster after the Red Demon King | Every design-5 run that reached MT16 stopped at the Red Demon King, two of them without a red key for its door; the MT15 trades that bring the King within reach were not modelled |
| 7 | A quantity for repeated shop purchases; the vampire tag; the way and the missing keys on the lines of scripted events and of the MT7 seal | A run spent a third of its turns on single purchases, paid HP for vampire fights that the fight line called "already immune", and stopped on MT18 with the Ice Pickaxe behind a blue door and no blue key, which no line stated |
| 7b | Design 7 with blue keys for sale, as in the original game | A design-7 run again reached MT18 without a blue key, although the event line now named the door and the missing key; a stored position on MT18, continued with blue keys for sale, reached the normal ending |

The rest of this section describes the observation of design 7 and the rule changes of the tower prompt.

**Rule 4 threshold.**
*Purpose:* to keep a single fight from spending most of the HP.
*Definition:* from design 5 on, rule 4 of the tower prompt forbids a fight that costs more than 60 % of current HP unless nothing else can make progress; the single-floor prompt keeps 40 %, and the engine enforces neither.
*Justification:* in a replay of an MT3 decision, Qwen3.5-397B declined the fight an expert takes in three of six calls at 40 % and in none at 60 % or above.
No threshold made either model take the fight that ends the run (Table 6.14).

**Shop rule.**
*Purpose:* to make purchases serve the fights on the way up.
*Definition:* from design 3 on, rule 3 asks for enough ATK that the monsters still needed cost at most the rule-4 share of current HP, in place of ATK above the highest DEF in scope (Section 5.4 gives the full rule).
*Justification:* under the earlier form, the design-2 runs met the rule and still stopped on MT8 before unaffordable Red Bats (Table 5.2).

**Key sales.**
*Purpose:* to keep gold for the purchases an expert makes.
*Definition:* from design 5 on, yellow and blue keys are not offered for sale, while red keys are; design 7b offers blue keys again, as the original game does.
*Justification:* an expert never buys yellow or blue keys, and a design-3 run spent its last gold on a yellow key on MT8 because it was the only action that cost no HP.

**Scouting exception.**
Rule 1 makes one exception to scouting: a shop not yet used is reached first.
The rule matters only while the up-staircase is still behind fights or doors; once the staircase is reachable, the engine takes it (Section 5.6).
Without the exception, both models left an MT3 position by the way up although the gold shop lay behind a 72-HP fight (Appendix D.4).

#### 6.4.2 Failure Census

The census covers the 94 failed episodes of 31 reactive configurations with only mechanical assists, all run before the re-run of Table 6.2.
They are rows 2 to 9 of the repair sequence (Table 6.5) and their variants in lookahead depth, temperature, prompt length and reasoning cap.
The models are Qwen3.5-397B, Qwen3.6-35B, Qwen3.8-27B and DeepSeek-V4-Flash.
The 13 failed simple-floor episodes of the re-run are not included.
Their first departures fall at turn 22 (Qwen3.6-35B, four episodes), turn 18 (Mistral Medium 3.5, five) and turns 2, 4, 15 and 18 (DeepSeek-V4-Flash, one each).
A first departure need not be the decision that loses the floor; the census locates first departures, not losing decisions.
The first departures fall into five categories:

- **The door choice (36 episodes).** The episode opens the yellow door at (7,5). At turn 3 or 4 (31 episodes), it does so instead of taking the route through the door at (4,7). At turn 9 with lookahead depth 1 (5 episodes), it does so instead of opening the door at (7,0). At turns 3 and 4, the door at (7,5) spends the last yellow key.
- **Late fight order (21).** At turns 15 to 24, the Bat at (3,5), a Slime Lord and the door at (7,5) are taken in a different order from the winning route. Eighteen of these episodes are by Qwen3.6-35B or DeepSeek-V4-Flash.
- **An early expensive fight (20).** At turns 3 to 5, the episode fights a Bat that costs 182 HP (46.5 % of current HP at turn 4, Listing 6.2). In 12 of these episodes, the model follows the unguarded positive fight-order line (Table 6.5, row 8).
- **The Slime Lord before the door (13).** At turn 9, the episode fights the Slime Lord at (1,9) before opening the door at (7,0). Ten of these have no lookahead (depth 0): five on the annotation version of Table 6.5, row 6, and five in the final configuration (Table 6.3).
- **Other early fights (4).** At turn 2 or 3, the episode fights the Red Slime at (5,3) (two episodes) or the Slime Lord at (4,2) (two).

Before the stat-route and order lines were added (Table 6.5, rows 2 and 3), the ten failures split between the door choice (5), the Slime Lord at turn 9 (3) and early fights (2).

#### 6.7.3 The Tower

The tower was run with seven successive tower designs (Section 5.5.4, Table 5.2).
Each design was introduced because of how the runs of the previous one stopped.
The prompt rules of Section 5.4 apply to all of them.
The shop rule changed with design 3; with design 5, the rule 4 threshold rose to 60 %, rule 1 gained the shop exception and rule 3 its sentences on purchases (Table 6.13, Appendix A.2).
Table 6.13 lists the runs of each design from MT0 and the continuations of one stored run.
Runs with earlier, incomplete forms of design 5 belong to the development history (Appendix D.4).

**Table 6.13:** Tower runs from MT0 by tower design. Highest floor reached per run; ATK / DEF at the end of the best run. Design 1: actions of the current floor, the up-staircase and return actions to earlier floors; shop rule "ATK above the highest DEF in scope". Design 2: every reachable object on every visited floor, a tower-wide key budget and the price of the way to an unreached shop. Design 3: design 2 plus the stat-needs line, with the shop rule "ATK high enough that the strongest needed monster costs at most 40 % of HP". Design 4: design 3 with the way-up line in place of the stat-needs line. Designs 1 to 4 ran with the 40 % override of Section 5.6. Design 5 (first on the corrected engine): design 4 on the corrected engine (Section 4.5.2), without the override, with rule 4 at 60 %, with plan memory, without yellow and blue keys for sale, and with the in-order form of the way-up line (Section 5.5.4). Design 6: design 5 with the MT15 trades, the key-reserve line and the monster upgrades after the Red Demon King (Section 4.5.3). Design 7 (final): design 6 with a quantity for repeated shop purchases, the vampire ability in the prompt and on the fight line, and the way and the missing keys for the items and guards of scripted events (Section 5.5.4). Design 7b: design 7 with blue keys for sale, as in the original game. Resumed = the design-6 run of Qwen3.5-397B, continued from its arrival on MT18 (turn 708) by the model named, with the design given.

| Design | Agent | Runs | Highest floor | ATK / DEF | Stopped because |
|---|---|---|---|---|---|
| — ᵃ | heuristic (depth 3) | 1 | MT8 | 113 / 82 | Red Bats unwinnable |
| 1 | Qwen3.5-397B | 1 | MT7 | 36 / 35 | stuck; 131 EXP unspent |
| 1 | DeepSeek-V4-Flash | 5 | MT7 (4), MT3 | 33 / 38 | stuck; MT3 run at 25 HP |
| 2 | Qwen3.5-397B | 1 | MT8 | 81 / 117 | Red Bats unaffordable |
| 2 | DeepSeek-V4-Flash | 3 | MT8 (3) | 92 / 106 | Red Bats unaffordable |
| 3 | Qwen3.5-397B | 3 | MT8, MT3 (2) | 123 / 93 | MT3 runs: 25 HP after a 93 % fight |
| 3 | DeepSeek-V4-Flash | 3 | MT14 (2), MT8 | 227 / 254 | all remaining fights unwinnable |
| 4 | Qwen3.5-397B | 2 | MT8 (2) | 108 / 99 | Red Bats unaffordable |
| 4 | DeepSeek-V4-Flash | 3 | MT14 (2), MT8 | 314 / 192 | all remaining fights unwinnable |
| 3, no override | Qwen3.5-397B | 3 | MT14, MT8 (2) | 201 / 340 | MT8 runs: Red Bats lethal; MT14 run: all remaining fights unwinnable |
| 4, no override | Qwen3.5-397B | 3 | MT8 (3) | 104 / 106 | Red Bats unaffordable |
| — ᵃ | heuristic, corrected engine | 1 | MT8 | 113 / 82 | Red Bats unwinnable |
| 5 | DeepSeek-V4-Flash | 3 | MT16 (3) | 1,032 / 1,113 | Red Demon King unwinnable; no red key for the MT16 door, or DEF below 1,000 |
| 5, no plan memory | DeepSeek-V4-Flash | 2 | MT16, MT8 | 766 / 939 | Red Demon King unwinnable |
| 6 | DeepSeek-V4-Flash | 3 | MT17, MT14, MT8 | 1,238 / 1,011 | MT17: bought a red key after the key line and beat the Red Demon King at DEF 1,001, then the upgraded MT17 monsters were unwinnable; MT8: Red Bat at 93 % |
| 6 | Qwen3.5-397B | 3 | MT18, MT8 (2) | 1,346 / 1,314 ᵇ | MT18: the up-staircase is hidden until the princess talk, whose way needs a blue key, and none was left; MT8: lethal-only positions |
| 6, resumed at turn 708 | Qwen3.5-397B | 1 | MT18 | 1,488 / 1,595 | no blue key: the Ice Pickaxe behind MT12 (10,6) not reachable; spent all gold on ATK/DEF and sold its keys |
| 7 | DeepSeek-V4-Flash | 3 | MT17 (2), MT8 | 1,346 / 1,066 | MT17: the upgraded monsters (e.g. Nether Captain 2,070 HP at 1,069 HP) unwinnable; one run never used the first scripted event of the thief (MT2 room with 8 gems and two weapons); MT8: Senior Mage lethal |
| 7 | Qwen3.5-397B | 3 | MT18, MT8 (2) | 1,257 / 1,996 | MT18: hidden staircase, 0 blue keys; MT8: lethal-only positions |
| 7 | Qwen3.6-35B | 3 | MT16, MT8 (2) | 552 / 1,133 | MT16 run stuck on MT9; MT8: Red Bats lethal |
| 7 | Mistral Medium 3.5 | 3 | MT8, MT4 (2) | 98 / 100 | MT4: Skeletons lethal at 5 and 30 HP |
| 7, resumed at turn 708, blue keys for sale | Qwen3.5-397B | 1 | **MT21, normal ending** | 2,264 / 2,558 | won |
| 7, resumed at turn 708, blue keys for sale | DeepSeek-V4-Flash | 3 | MT21 (2), MT20 | 2,294 / 3,633 | turn limit of the test (860) reached |
| 7b | DeepSeek-V4-Flash | 1 ᶜ | MT17 | 1,152 / 1,048 | stopped at the time limit of the experiments at turn 619 (288 model calls), one blue key in hand |

ᵃ The rule-based heuristic reads no prompt and has no tower design; its two rows give the engine of designs 1 to 4 and the corrected engine (Section 4.5.2).
ᵇ At the arrival on MT18 (turn 708).
ᶜ Three runs were planned; the experiments were closed after the first.

Design-6 runs of Qwen3.6-35B and Mistral Medium 3.5 with an earlier version of the key-reserve line are listed in Appendix D.3.2.

**Designs 1 to 4: MT7, MT8 and MT14.**
With design 1, every run stopped at or below MT7.
Qwen3.5-397B bought four DEF and one ATK at the MT3 shop, DEF first as the prompt requires, and ended with 131 experience points unspent.
The experience shop on MT5 lies behind a Big Bat that cost 55 % of its HP.
With design 2, all four runs passed MT7, spent their experience and stopped on MT8 with ATK between 79 and 92.
Only the run with ATK 92 met the shop rule, ATK above the highest DEF in scope, here the Red Bats' DEF of 90.
Even at ATK 92, the Red Bats cost about 15,000 HP.
With design 3, two of three DeepSeek-V4-Flash runs climbed to MT14, in about 365 turns, of which about 190 were taken by the engine.
They ended with ATK 219 to 227 and DEF 254 to 271, above the expert walkthrough's attributes at the end of its third section (ATK 185, DEF 224).
The third run stopped on MT8 before the Red Bats.
The MT14 runs stopped on MT9 and MT10, when every remaining fight on the visited floors was lethal or unwinnable.
The staircase on MT14 lies behind a monster that needs ATK above 400.
With design 4, DeepSeek-V4-Flash reached the same floors (MT14 twice, MT8 once), one run with ATK 314.

**The MT3 position and the 40 % override.**
Ten runs of designs 1 to 4 stopped on MT3.
Three of them are in Table 6.13, and one is the run of design 2 with a single plan per floor in Table 6.9.
Five are design-1 planning runs with the max-steps wording (Section 6.6), and one is a design-1 variant with a shop-route line (Appendix D.4).
In nine of the ten, the 40 % override of Section 5.6 had first replaced the model's choice of the Skeleton at (2,3) with a Bat.
At that point, the Skeleton cost 55 or 56 % of HP.
The same fight was taken later at 83 to 93 % of HP, chosen by the model or by its plan, and the override let it through.
In the tenth, a design-1 run of DeepSeek-V4-Flash, no override occurred, and the model fought the Skeleton at 93 % of HP.

The two design-3 runs of Qwen3.5-397B that stopped on MT3 show the sequence.
At turn 15, with 570 HP, the model chose the Skeleton, 315 HP (55 %), which leads to the Iron Sword.
The override replaced it with a Bat at 190 HP (33 %).
After that Bat and a Red Slime, the hero had 340 HP and the same ATK and DEF.
At turn 17, the model chose the Skeleton again, now at 93 % of its HP, and the override let it through.
The hero was left with 25 HP and no fight it could survive.
In these runs, the reasoning at the second choice lists both costs and decides by the effective cost.
The effective cost of the Skeleton was −315, because the keys and the sword behind it count as 630 HP of value.
At the first choice, the reasoning had argued for the sword at 55 %, the choice of the expert walkthrough (Section 4.3).

The override replaced this Skeleton in 24 of the 39 runs of designs 1 to 4.
These are the 21 runs of Table 6.13, the five planning runs of design 2 in Table 6.9 and the ten design-1 planning runs of Section 6.6.
The other three are the design-1 run at temperature 0.6 of Table D.57 and two variants of designs 1 and 4 (Appendix D.4).
The override was removed from design 5 on, and designs 3 and 4 were repeated without it (Table 6.13).
The result of this repetition, with rule 4 at 40 %, is consistent with the attribution of the MT3 stops to the override.
None of the six Qwen3.5-397B runs stopped on MT3 (MT14 once, MT8 five times), against two of three runs of design 3 with the override.
Every Qwen3.5-397B run with the override in which the Bat was fought at turn 15, by the override or by the model, reached MT8.
These are the runs of design 2, one design-3 run and both design-4 runs.

**Rule 4 without the override.**
In a development run on the corrected engine with rule 4 at 40 % and without the override, Qwen3.5-397B took the Bat itself at turn 15 (Appendix D.4).
To separate the rule from the rest of the observation, both MT3 decisions were replayed with the stored system prompt and request (Table 6.14).
Only the threshold was changed, in rules 3 and 4 and in the engine lines that quote it.

**Table 6.14:** Replay of the two MT3 decisions with the threshold of rule 4 changed: choices per cell at temperature 0, two calls per cell and six for Qwen3.5-397B at 40 %; 100 % stands for no threshold. Turn 15 of the development run on the corrected engine (rule 4 at 40 %, no override): 570 HP, Skeleton 315 HP (55 %) or Bat 190 HP (33 %). Turn 17 of a design-3 run: 340 HP, Skeleton 315 HP (93 %, leaves 25 HP) or Bat 190 HP (56 %).

| Position | Model | 40 % | 60 % | 80 % | 100 % |
|---|---|---|---|---|---|
| turn 15 | Qwen3.5-397B | Bat 3, Skeleton 3 | Skeleton 2 | Skeleton 2 | Skeleton 2 |
| turn 15 | DeepSeek-V4-Flash | Skeleton 2 | Skeleton 2 | Skeleton 2 | Skeleton 2 |
| turn 17 | Qwen3.5-397B | Bat 6 | Bat 2 | Bat 2 | Bat 2 |
| turn 17 | DeepSeek-V4-Flash | Bat 2 | Bat 2 | Bat 2 | Bat 2 |

At 40 %, Qwen3.5-397B declines the Skeleton, which the expert walkthrough takes, in three of six calls, as it did in the development run.
At 60 % and above, it declines it in none of six calls.
At the second position, the stored design-3 run had chosen the 93 % Skeleton.
None of the 20 replays did, at any threshold or without one.
The second position arose only because the override had replaced the Skeleton at 55 % two turns earlier.
From design 5 on, the tower prompt states rule 4 at 60 %, a threshold chosen on these two positions only.
The single-floor prompt keeps 40 % (Section 6.3: at 60 %, Qwen3.5-397B won the simple floor 2/5 [0.12, 0.77] against 5/5).

**Designs 5 to 7: the Red Demon King and the scripted events.**
From design 5 on, the runs that pass MT8 meet the obstacles that the walkthrough describes as the second half of the game.
The Red Demon King on MT16 (DEF 1,000) stopped every design-5 run that reached MT16.
Of the three runs with plan memory, two had no red key left for the MT16 door, and the third had DEF below the King's ATK of 1,000.
Without plan memory, design 5 reached MT16 and MT8 in two DeepSeek-V4-Flash runs, against MT16 in all three runs with it.
Design 6 modelled the two trades on MT15 that sell the Holy Sword and the Holy Shield.
It also added the key-reserve line, which states that a door off the way up leaves no red key for the way up and names the price of one.
In one DeepSeek-V4-Flash run, the model then bought a red key, opened the MT16 door and beat the King at DEF 1,001 without losing HP.
The first design-6 run of Qwen3.5-397B did the same and reached MT18.
Killing the King triggers a scripted upgrade of the later monsters (Section 4.5.3).
After it, the monsters on MT17 need ATK above about 1,100 and cost 2,000 HP and more.
Both DeepSeek-V4-Flash runs of design 7 that reached MT17 stopped there, with ATK 1,048 and 1,346.
The design-6 run of Qwen3.5-397B passed MT17 and arrived on MT18 with ATK 1,346 and DEF 1,314.

**MT18 and the princess.**
In the game, the up-staircase of MT18 appears only after the hero talks to the princess.
Her cell is opened by the thief of MT4 once the hero brings him the Ice Pickaxe from MT12.
The staircase of MT20 appears when the Cross is handed in.
For the design-6 run of Qwen3.5-397B, Table 6.13 reports MT18, its highest floor on the corrected engine (Appendix H).
Continued from its arrival on MT18 on the corrected engine, the run could not climb further.
The pickaxe lies behind a blue door, and the run had used its last blue keys on three doors of MT7 at turns 604 to 609, about 100 turns earlier.
Blue keys were not offered for sale.
The run spent all gold on attributes, sold its keys and stopped.
The design-7 run of the same model reached MT18 with no blue key again, although the event line now named the blue door and the missing key.
With blue keys offered for sale, as the original game does (50 g at the Key Seller on MT5), the same stored position was continued four times.
Qwen3.5-397B bought one blue key, fetched the pickaxe, gave it to the thief and freed the princess.
It then climbed to MT19, defeated the last White Warrior on MT7 for the Cross and handed the Cross in.
At turn 832 it defeated the Nether Demon King on MT21, the normal ending of the game.
The three DeepSeek-V4-Flash continuations reached MT20, MT21 and MT21 before the turn limit of 860, 152 turns after the resumption.
From this position, one of four continuations reached the normal ending (1/4 [0.05, 0.70]).

**Design 7b.**
Design 7b, design 7 with blue keys for sale, was run once from MT0 with DeepSeek-V4-Flash.
The run reached MT17 and was stopped at the time limit of the experiments at turn 619, after 288 model calls.
It ended with ATK 1,152, DEF 1,048 and one blue key in hand.

Earlier tower runs with a walkthrough-derived prompt and unlogged strategic overrides are reported in Appendix D.4.

### 6.8 Supporting Pilots

#### 6.8.1 Vision-Language Observation

A vision-language model (Qwen3-Omni-30B) was given the MT3 floor as text only, as an image with text, and as an image only.
In all three conditions, every episode ended with the hero's death.
The pilot concerns the form of the observation (RQ1) but predates the repeated-run protocol; it is reported in full in Appendix D.

#### 6.8.2 Fine-Tuned Small Model

A 1.2-billion-parameter model (LFM2.5-1.2B-Thinking) was fine-tuned with low-rank adapters (Hu et al., 2022) on decisions of the rule-based agent and of the exact solver.
On held-out states from the training distribution, it matched the reference action in 90 % of cases.
A variant trained on the reasoning of a large model produced only a few repeated answers.
A variant trained on solver-guided reasoning chose, in 52.9 % of decisions, an action from which the exact optimum remained reachable.
The pilot concerns weight optimisation as the alternative to prompt optimisation (RQ2) and lies outside the comparison of Section 6.5.
It was not evaluated on complete episodes under the final configuration and is reported in full in Appendix E.

#### 7.1.4 Observation Design on the Tower

On the tower, each design of the observation was introduced because of how the runs of the previous one stopped, and each moved the highest floor reached (Tables 5.2 and 6.13).
With the first design, every run stopped at or below MT7, one floor below the heuristic.
Offering every reachable object of every visited floor as an action took all runs of design 2 to MT8, where they stopped with ATK between 79 and 92 against the Red Bats' DEF of 90.
Design 3 added a line that states, for the strongest monsters still needed, the ATK at which each costs at most 40 % of HP, together with a matching shop rule in the prompt.
Two of three DeepSeek-V4-Flash runs then reached MT14, with attributes above the expert walkthrough's at the corresponding point.
Design 4, which replaced that line with the way-up line, reached the same floors.
Design 5 took all three DeepSeek-V4-Flash runs to MT16, but it changed more than the observation.
Besides a new form of the way-up line, it introduced the corrected engine, removed the 40 % override, set the rule 4 threshold to 60 % and added plan memory; the contribution of each was not separated.
The Red Demon King on MT16 then stopped every run of design 5.
Design 6 modelled the MT15 trades and added a line stating that a door off the way up would leave no red key for the way up.
One DeepSeek-V4-Flash run and one Qwen3.5-397B run then bought a red key and beat the King.
The King's scripted upgrade of the later monsters stopped the DeepSeek-V4-Flash runs that reached MT17.
Qwen3.5-397B passed MT17 in designs 6 and 7 and stopped on MT18 both times, without the blue key needed on the way to the princess who reveals the staircase.
In the design-6 run, the last blue keys had been spent about a hundred turns earlier; in the design-7 run, a line naming the missing key did not prevent the same outcome.
Continued from MT18 with blue keys for sale, as the original game sells them, the same model completed the chain and reached the normal ending.
Three continuations of the same position by DeepSeek-V4-Flash reached MT20, MT21 and MT21 before the turn limit, about 150 turns after the resumption.
Design 7b, which offers blue keys for sale from the start, was run once from MT0, and that run reached MT17 (ATK 1,152, DEF 1,048) before the time limit.
The climb from MT7 to MT18 therefore came from annotations together with a more faithful engine, the removal of the override and a looser rule 4 threshold.
The remaining stops are failures of resource foresight: a key, gold or attack must be kept or built for a use that the observation shows only much later.
Stating the future need at the decision that spends the resource was followed by red-key purchases in two runs, but did not prevent the blue-key failure.

Ten tower runs of designs 1 to 4 ended at the same early position on MT3, and in nine of them the engine's 40 % override had shaped the outcome.
At turn 15, the override replaced a Skeleton that the model chose at 55 % of HP with a cheaper Bat.
Later the model, or its plan, chose the same Skeleton at 83 to 93 % of HP, and the override let it through; in the stored design-3 run, this left the hero with 25 HP and no fight it could survive.
The override replaced this Skeleton in 24 of the 39 runs of designs 1 to 4, and in the aggregate the result looked like a model error.
In the runs of Qwen3.5-397B, the second choice followed an effective cost of −315.
That figure counts the sword and keys behind the fight without the cost of reaching them, the first kind of one-sided annotation (Section 6.4.3).
Without the override, none of six Qwen3.5-397B runs of designs 3 and 4 stopped on MT3, against two of three with it.
The 40 % stated only as a prompt rule still made Qwen3.5-397B refuse the first Skeleton in three of six replayed calls (Table 6.14).
At no threshold, nor without one, did either model take the second.
On the tower, where costs grow faster than HP, a fixed share of 40 % therefore appears too strict as a proxy for "do not take a fight you cannot recover from".
The proxy also appears specific to the floor: at 60 %, Qwen3.5-397B won the simple floor in 2 of 5 episodes against 5 of 5 at 40 % (Section 6.3).
Plan memory, also part of design 5, lowered the same cell to 2 of 5.
On a floor with a single winning order, the 40 % limit and the absence of memory appear to be part of what keeps that order stable.
The final tower design states the rule at 60 %, a value chosen on two positions only; ideally, the prompt would need no tuned threshold at all.

## 2. Former Appendix D

### Appendix D: Development History

This appendix records how the agent and its evaluation were developed: the experiment ledger E1–E27 (D.1), the prompt-engineering case study that led to the solver-route prompt (D.2), the superseded composite score and the runs excluded from Chapter 6 (D.3), and the development of the tower designs (D.4).
Every score is a single episode unless $N$ is stated, and wherever Chapter 6 reports a repeated-run figure for the same question, that figure supersedes the one given here.
Results obtained before the scorer correction of April 2026 (D.1.16) are not comparable with later ones.
Several models used here, among them Qwen3-30B, DeepSeek-R1-Distill-Llama-70B, Qwen3-235B and three Qwen3.5 models, are no longer served, so their results cannot be reproduced.
Table D.1 lists the readings of this history that the final thesis replaces.

**Table D.1:** Superseded readings. Each row names a reading of the development history, the fact that replaces it and where the thesis reports that fact.

| Superseded reading | Current fact | Where |
|---|---|---|
| The complex floor's optimum is 22 HP, and episodes that end at 22 HP are "BFS-optimal" (D.1.9, D.1.10, D.1.12, D.2) | The exact optimum is 68 HP (ATK 16, DEF 20, MDEF 20). 22 HP is the best route of the published solver, which keeps the first state it reaches for each set of cleared obstacles instead of the best one. | Section 4.6, Table B.1 |
| The simple floor is "permutation-invariant", and 13 HP is the normal outcome of an LLM episode (D.1.12) | The floor has 13 HP of slack, and one ordering call is worth 12 HP. Every win in Table 6.2 on this floor ends at 2 HP; one repeated-run win ends at 13 HP. | Section 6.4.5 (Reasoning at the Decisive Turn), Table 6.5 |
| A capability threshold between 30 and 70 billion parameters; mixture-of-experts models outperform dense ones (D.1.5) | Not reproducible: three of the models were removed from the service. Model size alone did not order the repeated-run results. | Section 7.1.7 |
| Early prompt-optimisation gains: +146 % (E3), an 8B model that "significantly outperforms" a larger one (E16), "durable strategic principles" (D.1.3, D.1.14, D.2.1) | These gains were accepted on single episodes. Under the full observation, evolved prompts stay within the noise floor of the repeated, paired evaluation. | Section 6.5 |
| An optimal temperature range of [0.6, 1.0], from one episode per temperature (D.2.5) | In the re-run of Table 6.2, no success rate at 0.6 or 1.0 differs from the rate at 0 by more than one episode in five. The largest difference in the earlier runs (2/5 at 1.0 against 8/10 at 0) is not significant (one-sided Fisher exact test, $p = 0.17$). | Section 6.3, temperature rows of Table 6.3 |
| Hiding the annotations is the fix for annotation interference (D.2.4) | Switching the overrides off also hid the fight annotations, so results with overrides off were obtained with less information than reported. Overrides and annotations are now separate settings, and the final configuration shows all annotations. | Appendix H, incident 8 |
| The composite score as the headline measure (D.1, D.2) | Success rate with its Wilson interval first, then HP relative to the exact optimum among successes. The composite ranks a fatal boss attempt above a safe episode. | Section 5.9, D.3.1 |
| Per-turn reactive reasoning cannot match a floor plan (D.1.2) | On the simple floor, reactive control wins 14 of 20 episodes against 1 of 70 committed-plan episodes of the same two models. | Section 6.6 |
| Single-call coordinate plans measure the model's plan (D.1.1, D.1.10, D.1.12, D.1.16) | Most turns of these episodes fell back to the heuristic (28 to 32 of 36 on the simple floor). | Section 6.6, D.1.10 |
| The complex floor is lost because the model fights monsters that the optimum avoids (D.1.12) | The exact optimum fights five of these monsters after the stat items that make them cheap. The repeated-run episodes are lost at a fight taken before those items, 29 of 30 at the Red Slime (11,8). | Section 6.4.6, Table B.4 |

#### D.1 Experiment Ledger

The ledger reproduces the development experiments of April to July 2026 with their original labels.
Its sections keep the numbers of the chapter they come from: D.1.1 to D.1.19 correspond to the former Sections 8.1 to 8.19, and D.1.13 was not used.
This appendix keeps the labels of the early harness, among them *oneshot* for the single-call plan of Section 5.5.2 and *multistep-k* for commit-$k$.
Experiments E13, E14, E20 and E25 to E27 have no section of their own.
Architecture A is the reactive hybrid agent, Architecture B a single-call coordinate plan (a predecessor of the planning modes of Section 5.5.2), and Architecture C the fine-tuned small model of Appendix E; multistep-$k$ is the predecessor of commit-$k$.
"BFS" denotes the published solver of Section 4.6: on the simple floor its result, 13 HP, is the exact optimum; on the complex floor its result, 22 HP, is not (exact optimum 68 HP).
"GEPA" denotes the GEPA library run on a single task instance, the predecessor of the loops of Section 5.7.
All scores are composite scores (D.3.1).

##### D.1.1 E1: Baseline Evaluation

###### D.1.1.1 Heuristic Baseline

The deterministic heuristic achieves a composite score of 0.875 on MT3 in the early runs and 0.924 in the E6 evaluation, whose components Table D.2 gives.

**Table D.2:** E1, rule-based heuristic on MT3: components of the composite score (E6 evaluation).

| Component | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Completion | 1.000 | 0.35 | 0.350 |
| HP Score | 0.877 | 0.25 | 0.219 |
| Efficiency | 1.000 | 0.15 | 0.150 |
| Shop Score | 1.000 | 0.15 | 0.150 |
| Violation Score | 0.550 | 0.10 | 0.055 |
| **Composite** | **0.924** | — | **0.924** |

The original record attributed the difference between 0.875 and 0.924 to the non-deterministic endpoint, although the heuristic makes no model call.
All enemies are cleared (completion = 1.0), and the shop correctly purchases DEF.
The violation score of 0.55 reflects pre-sword corridor entry: the heuristic lacks the context-dependent rule to avoid fighting in the sword corridor before collecting the sword.

###### D.1.1.2 Architecture A, Seed Prompt v1

Architecture A with the seed prompt (v1) and Qwen3-30B-A3B-Thinking on MT3 achieved a composite score of 0.379 (Table D.3).

**Table D.3:** E1, Architecture A with seed prompt v1 (Qwen3-30B-A3B-Thinking) on MT3: components of the composite score.

| Component | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Completion | 0.35 | 0.35 | 0.123 |
| HP Score | 0.50 | 0.25 | 0.125 |
| Efficiency | 0.60 | 0.15 | 0.090 |
| Shop Score | 0.30 | 0.15 | 0.045 |
| Violation Score | 0.70 | 0.10 | 0.070 |
| **Composite** | **0.379** | — | — |

This was far below expectations.
The model's per-turn reasoning failed to maintain a coherent floor-wide strategy, resulting in poor completion (only about 6 of 17 enemies killed) and suboptimal shop use.
The record took the lack of a persistent floor plan to be the main weakness of the reactive architecture, visible as incoherent sequencing.
The endpoint was not deterministic at temperature 0 either: the same prompt scored 0.825 in a separate test run.

###### D.1.1.3 Architecture B, One-Shot Plan

Architecture B (one-shot coordinate plan) with the seed prompt and Qwen3-30B achieved a composite score of 0.875, matching the heuristic baseline.
The single model call produces a coordinate-priority list that is executed greedily, with heuristic fallback for newly revealed entities.
D.1.10 later found that plans of this kind were mostly replaced by the heuristic.

###### D.1.1.4 Baseline Summary

**Table D.4:** E1 on MT3: summary of the three configurations.

| Configuration | Score | Completion | LLM Calls | Notes |
|--------------|-------|------------|-----------|-------|
| Heuristic (no LLM) | 0.875–0.924 | 17/17 | 0 | Deterministic; the recorded score varies between runs |
| Arch A v1 (Reactive) | 0.379 | ~6/17 | ~25 | Per-turn reasoning fails at floor-level strategy |
| Arch B (One-Shot) | 0.875 | 17/17 | 1 | Matches heuristic; LLM adds no value over the deterministic agent |

##### D.1.2 E2: Architecture Comparison

###### D.1.2.1 Composite Score Comparison

**Table D.5:** E2: composite scores of the architectures on MT3.

| Architecture | Prompt | Model | Composite Score | LLM Calls | Notes |
|-------------|--------|-------|----------------|-----------|-------|
| Heuristic | — | — | 0.875–0.924 | 0 | Deterministic baseline |
| A (Reactive) v3 | GEPA-optimised | Qwen3-30B | **0.847** | ~25 | Per-turn reasoning |
| B (One-Shot) | Seed v1 | Qwen3-30B | **0.875** | 1 | Coordinate plan + heuristic fallback |

Architecture A with the GEPA-optimised prompt (v3) scored 0.847, an improvement over the seed prompt's 0.379 (+123 %) but still slightly below the deterministic heuristic (0.875).
Architecture B with the seed prompt matched the heuristic exactly at 0.875 with a single model call.

###### D.1.2.2 Qualitative Decision Analysis

The reading drawn from E2 was that per-turn reactive reasoning (Architecture A) cannot match a coherent floor plan (Architecture B or the heuristic), even with an optimised prompt.
The reactive architecture's decisions were locally coherent, each following the prompt rules, but globally inconsistent, because the model had no memory of its own earlier decisions.
Architecture B's single plan call produced a consistent ordering, and the heuristic fallback handled newly revealed entities.
The repeated runs of Section 6.6 reverse this reading (Table D.1): on the simple floor, reactive control wins 14 of 20 episodes against 1 of 70 committed-plan episodes, and Architecture B's result was largely the heuristic's (D.1.10).

A specific failure pattern was observed in Architecture A v3: the model correctly identified that it should "collect before fight" on early turns but later forgot this priority when the action list changed, occasionally fighting an enemy while a newly accessible item existed.
The record classified this as a Category I (planning) failure inherent to the reactive architecture rather than a question of prompt quality.

##### D.1.3 E3: GEPA Optimisation Trajectory

###### D.1.3.1 Preliminary Result

The first GEPA optimisation run produced one candidate (v3) with a score of 0.9833, 10.8 percentage points above the heuristic baseline of 0.875.

The prompt changes from v1 to v3 consisted of:
1. Addition of a "Key Economy" section with three rules on key spending priority.
2. Addition of a dead-end door filtering instruction.
3. Expansion of the strategic principles from four to ten items.

###### D.1.3.2 Multi-Generation Trajectory

The optimiser ran for 7 metric evaluations across 3 candidate generations (`GEPA_MAX_CALLS=20`, teacher Qwen3.5-397B), as Table D.6 shows.

**Table D.6:** E3: GEPA trajectory on MT3.

| Iteration | Candidate | Parent | Subsample Score | Full Val Score | Status |
|-----------|-----------|--------|----------------|----------------|--------|
| 0 | Seed (idx 0) | — | — | 0.3997 | Baseline |
| 1 | Candidate A | Seed | 0.8685 | — | Rejected (subsample < baseline 0.8752) |
| 2 | Candidate B (idx 1) | Seed | 0.83 | **0.9833** | **Accepted, new best** |
| 2 | Candidate C (idx 2) | idx 1 | — | 0.4859 | Regression |

**Key observations:**

1. **Non-monotonic trajectory**: the best candidate (idx 1, score 0.9833) derives from the seed, not from the rejected iteration-1 candidate. GEPA's parent selection returned to the seed after the first candidate was rejected.

2. **Subsample noise**: iteration 1's candidate scored 0.8685 on a subsample but was rejected because the seed's own subsample score was 0.8752, a gap of 0.7 percentage points. Because the endpoint is not deterministic at temperature 0, validation scores varied by ±5–10 % across runs, which made subsample-based accept and reject decisions noisy.

3. **Regression from a strong parent**: candidate C (iteration 2, parent idx 1) scored only 0.4859, a sharp regression from its parent's 0.9833. Its prompt contained leaked thinking tokens of the teacher (`` blocks.\n\n   Let's write it.\n</think>\n\n```text ``), which corrupted its structure. This is a known failure mode when thinking-enabled models are used for text generation.

4. **Total cost**: 7 full metric evaluations (each involving multiple game episodes) produced 1 successful improvement over the seed.

Every candidate was accepted on single episodes; Section 6.5 shows that differences of this kind lie within the noise floor under the full observation (Table D.1).

###### D.1.3.3 Prompt Evolution Analysis

The winning prompt (idx 1, score 0.9833) differs from the seed (idx 0, score 0.3997) in four targeted areas (Table D.7).

**Table D.7:** E3: rule changes from the seed (v1) to the accepted candidate (v3).

| Rule Area | Seed (v1) | GEPA v3 (idx 1) | Impact |
|-----------|-----------|-----------------|--------|
| Shop timing | "Visit shop when affordable" | + "After reaching a shop, buy DEF immediately if gold is available" | Prevents missed shop visits |
| Post-door items | (not mentioned) | + "After opening any door, collect all new items immediately (STEP 1)" | Eliminates the Category I failure of fighting before collecting newly accessible items |
| Dead-end doors | "Skip dead-end doors" | "Skip it entirely and never attempt to open it again" | Stronger language prevents re-opening |
| HP safety | "hpAfter < 15%" | "hpAfter < 20%" | More conservative safety threshold |

The changes are conservative and targeted: GEPA preserved the structure and most of the content of the seed and modified only rules that had directly caused failures in the game trace.
The record related this to DSPy's finding that prompt optimisation works best when the seed prompt is already close to correct (Khattab et al., 2024).

##### D.1.4 E4: Component Analysis

###### D.1.4.1 Component Changes from v1 to v3

The composite improvement of the GEPA v3 prompt (0.3997 → 0.9833) is driven mainly by the completion and shop components (Table D.8).

**Table D.8:** E4: approximate composite components of the seed (v1) and of the accepted candidate (v3) on MT3.

| Component | v1 (Seed) | v3 (GEPA) | Δ | Driver |
|-----------|-----------|-----------|---|--------|
| Completion | ~0.35 | ~1.00 | +0.65 | All 17 enemies killed vs ~6/17 |
| HP Score | ~0.50 | ~0.90 | +0.40 | Better fight ordering conserves HP |
| Efficiency | ~0.60 | ~0.95 | +0.35 | Fewer wasted turns |
| Shop Score | ~0.30 | ~1.00 | +0.70 | DEF-first shop rule correctly applied |
| Violation Score | ~0.70 | ~0.85 | +0.15 | Fewer pre-sword corridor violations |

The per-component values are approximate, derived from the composite formula and the game traces; exact isolation of the components would have required further instrumented runs.

###### D.1.4.2 Interpretation

The largest improvements are in completion (+0.65) and shop strategy (+0.70).
With the seed prompt, the per-turn reasoning often failed to reach the shop or skipped shop visits when gold was available; the added rule "buy DEF immediately" addressed this directly.
The completion improvement reflects better fight sequencing: collecting items first and buying DEF at the shop made later fights cheaper, so more enemies could be killed before HP ran out.

##### D.1.5 E5: Model Comparison

> **Superseded (September 2026).** This section reports single MT3 episodes from April to July 2026. Three readings drawn from them do not hold: a sharp capability threshold between 30B and 70B parameters, an advantage of mixture-of-experts routing over dense models, and a general failure of the 27B dense model. Three of the models were removed from the service, so the numbers cannot be reproduced. In the first repeated-run matrix ($N = 10$ per model, September 2026), the dense Qwen3.8-27B won the simple floor as often as Qwen3.5-397B, and in the planning study it won 3/3 reactively (Table 6.9). The early override ablation on MT3 (single episodes, April 2026: an 8B instruction-tuned model at 0.441 raw and 0.982 with overrides) does not hold either. The overrides of that time were strategic, so the census of Section 6.4.1 applies: the heuristic, not the model, made the rescued decisions. The section is kept as the history of the question that Section 7.1.7 answers.

###### D.1.5.1 First Comparison (E5)

Architecture A (reactive) with the GEPA v3 prompt was run with three models available on the endpoint (Table D.9).

**Table D.9:** E5: Architecture A with the GEPA v3 prompt on MT3.

| Model | Parameters | Active Params | Score | Key Observations |
|-------|-----------|---------------|-------|-----------------|
| Qwen3-30B-A3B-Thinking | 30B | 3B (MoE) | **0.379** | Poor completion; per-turn reasoning collapses at floor scale |
| DeepSeek-R1-Distill-LLaMA-70B | 70B | 70B (dense) | **0.992** | Near-perfect; consistent shop use, correct fight ordering |
| Qwen3-235B-A22B | 235B | 22B (MoE) | **0.992** | Identical score to 70B; both clear all enemies optimally |

###### D.1.5.2 Qwen3.5 Model Family (E7 Benchmark)

When the Qwen3.5 series (Yang et al., 2025) became available on the endpoint, four of its models were benchmarked with the GEPA v3 prompt (score 0.9833) on MT3 against the original Qwen3-30B baseline (Table D.10).

**Table D.10:** E7: Qwen3.5 models with the GEPA v3 prompt on MT3.

| Model | Total Params | Active Params | Score | HP | Violations | LLM Calls | Time(s) | s/call |
|-------|-------------|---------------|-------|-----|-----------|-----------|---------|--------|
| Heuristic (no LLM) | — | — | 0.875 | — | 3 pre-sword | 0 | — | — |
| Qwen3-30B-A3B | 30B | 3B (MoE) | 0.818 | 203 | 3 pre-sword | 30 | 349 | 11.6 |
| Qwen3.5-27B | 27B | 27B (dense) | 0.506 | **DIED** | 1 suicide | 13 | 432 | 33.3 |
| **Qwen3.5-35B-A3B** | 35B | 3B (MoE) | **0.992** | 433 | 0 | 30 | 331 | 11.0 |
| **Qwen3.5-122B-A10B** | 122B | 10B (MoE) | **0.992** | 433 | 0 | 23 | 332 | 14.4 |
| **Qwen3.5-397B-A17B** | 397B | 17B (MoE) | **0.992** | 433 | 0 | 27 | 168 | 6.2 |

**Observations and the readings of the time** (the readings do not hold, see the note above):

1. **Mixture-of-experts models**: all three Qwen3.5 mixture-of-experts models (35B, 122B, 397B) scored 0.992 with zero violations, while the dense Qwen3.5-27B died on turn 19 from a suicide fight. The record read this as an advantage of mixture-of-experts routing.

2. **Model generation**: Qwen3.5-35B-A3B (3B active parameters) scored 0.992 against 0.818 for the older Qwen3-30B-A3B (also 3B active), +21 % at the same active parameter count. The record read this as model generation mattering more than scale for this task.

3. **The 27B dense model**: Qwen3.5-27B scored lowest of all models, below the 3B-active mixture-of-experts variants, and was the slowest per call (33.3 s against 6–14 s). The record read this as a sign that mixture-of-experts routing specialises better for multi-step strategic reasoning; in the repeated runs, the dense Qwen3.8-27B won the simple floor as often as Qwen3.5-397B (note above).

4. **Latency**: Qwen3.5-397B was the fastest per call (6.2 s), which the record attributed to the service prioritising its flagship model. Qwen3.5-35B at 11.0 s per call offered the best balance of quality and latency for repeated evaluation runs at the time.

5. **Ceiling**: the three Qwen3.5 models that scored 0.992 ended with the same final HP (433, 15 below the optimum of 448) and zero violations. The 15-HP gap comes from one suboptimal ordering decision (fighting one bat before a DEF gain made it free), which the record took as the practical ceiling of the GEPA v3 prompt on MT3.

###### D.1.5.3 Combined Model Scaling Analysis

In this record, the step from 30B to 70B parameters was +161 % (0.379 → 0.992), and the step from 70B to 235B added nothing (0.992 → 0.992).
Together with E7, the record concluded that the capability threshold depends on architecture and generation rather than on parameter count: Qwen3.5-35B-A3B (3B active, 2025) matched the dense DeepSeek-R1-Distill-Llama-70B (2024), while the dense Qwen3.5-27B (27B active, 2025) failed.
It related this to the gap below 70B parameters reported by AgentBench (Liu, X. et al., 2023), suggesting that mixture-of-experts routing may lower the effective threshold and that newer model generations may remove it at the same active-parameter budget.
Neither conclusion is supported by the repeated runs (Section 7.1.7, Table D.1).

##### D.1.6 E6: Transfer Evaluation

The GEPA v3 prompt was evaluated on five floors (MT0–MT4) with the deterministic heuristic and with Architecture A (reactive, Qwen3-30B), as Table D.11 shows.

**Table D.11:** E6: transfer of the GEPA v3 prompt to MT0–MT4.

| Floor | Enemies | Heuristic | LLM (v3) | Δ | Notes |
|-------|---------|-----------|-----------|---|-------|
| MT0 | 0 | 0.895 | 0.895 | 0.000 | Trivial (items only, no enemies) |
| MT1 | 12 | 0.691 | 0.681 | **−0.010** | LLM slightly worse; stuck on unwinnable wizard |
| MT2 | 3 | 0.545 | 0.545 | 0.000 | Both take stairs immediately (0/3 enemies killed) |
| MT3 | 17 | **0.924** | 0.893 | −0.031 | Training floor; closest scores; LLM has pre-sword violations |
| MT4 | 20 | 0.568 | 0.568 | 0.000 | Both stuck after 3/20 kills (no keys for doors) |

###### D.1.6.1 Transfer Analysis

**MT0 (trivial)**: both modes achieve identical scores. With no enemies, the floor reduces to item collection and stair navigation, which both the heuristic and the model handle without difficulty.

**MT1 (LLM slightly worse)**: the model scored 0.681 against 0.691 for the heuristic, a marginal regression. Both modes complete 5 of 12 enemies before meeting an unwinnable Junior Mage at (7,6) with effectively infinite damage. The model navigated MT1 cleanly (8 model calls, zero parse errors) but consumed slightly more HP than the heuristic's deterministic ordering. On this floor the GEPA prompt provides no strategic advantage, because the obstacle is structural (an unwinnable enemy blocks progress) rather than strategic.

**MT2 (identical poor performance)**: both modes score 0.545, killing 0 of 3 enemies and ascending the stairs immediately. MT2 appears to require keys (available on MT1) to reach its enemies, so testing floors individually with fresh hero stats leaves nothing to do on MT2 beyond the stairs.

**MT3 (training floor)**: the closest gap between heuristic and model (0.924 against 0.893, Δ = −0.031). The GEPA prompt was optimised for this floor, and both modes complete all 17 enemies.

**MT4 (structural limitation)**: both modes score 0.568. MT4 has 20 enemies, but the hero starts with 0 keys and base stats (HP=1000, ATK=10, DEF=10). Only 3 enemies are reachable in the initial corridor before key-locked doors block further progress. MT4 is designed to be reached mid-game with resources accumulated on earlier floors, so testing it standalone with a fresh hero is structurally infeasible.

###### D.1.6.2 Transfer Findings

The transfer evaluation showed that:

1. **GEPA-optimised prompts did not transfer positively** to unseen floors with a 30B reactive model. Performance matched or fell below the heuristic on all non-training floors.
2. **The model added marginal negative value on MT1 and MT3**: it consumed slightly more HP than the heuristic because of suboptimal fight ordering (pre-sword corridor entry on MT3).
3. **Structural limitations dominated** on MT2 and MT4, where both modes were blocked by cross-floor resource dependencies (keys from earlier floors).
4. **The heuristic baseline served as an effective control**, and the composite score captured both strategic quality (completion, HP) and tactical correctness (violations).

##### D.1.7 Failure Mode Analysis

###### D.1.7.1 Taxonomy

To interpret agent errors beyond the composite score, the development phase classified failures into three categories drawn from the original thesis proposal.
Each category corresponds to a distinct phase of the agent's decision pipeline (strategic planning, tactical calculation and action execution), and each can be detected from the structured episode logs (Section 5.8).

**Category I: Planning and Strategic Failures.** Errors at the level of floor-wide strategy, where the agent selects legal and executable actions but in an order that is globally suboptimal (Table D.12).

**Table D.12:** Failure taxonomy, Category I: planning and strategic failures.

| Sub-type | Description | Detection |
|----------|-------------|-----------|
| Suboptimal Pathing | Taking items or fighting enemies in a sequence that wastes HP (e.g., fighting expensive enemies before collecting stat-boosting gems) | Violation component penalises "pre-sword corridor entry"; total damage > reference total damage |
| Resource Mismanagement | Wasting keys on dead-end doors, spending gold on ATK at the shop instead of DEF | Shop score < 1.0; dead-end door opened (logged in action trace) |
| Horizon Collapse | Ascending stairs before defeating accessible enemies or collecting accessible items, treating floor completion as partial | Late-game completion score < 1.0; stairs taken with non-zero remaining enemies |

**Category II: Tactical and Calculation Failures.** Errors where the agent's assessment of individual actions is incorrect (Table D.13).

**Table D.13:** Failure taxonomy, Category II: tactical and calculation failures.

| Sub-type | Description | Detection |
|----------|-------------|-----------|
| Mathematical Errors | Selecting a fight the agent incorrectly believes is safe, resulting in death or near-death | HP score ≈ 0 following a fight that the episode log marks as `total_damage > hp_before`; suicide fight violation |
| Constraint Violations | Attempting to take an action that requires resources the agent does not have (e.g., misjudging key counts) | Parse failures where the selected action is not in the valid action set; action validation rejects the action |

**Category III: Action and Execution Failures.** Errors at the level of producing valid responses, independent of strategic quality (Table D.14).

**Table D.14:** Failure taxonomy, Category III: action and execution failures.

| Sub-type | Description | Detection |
|----------|-------------|-----------|
| Formatting Errors | Outputting a non-existent action ID, malformed JSON, or a response the parser cannot extract | `consecutive_errors` counter > 0; heuristic fallback triggered |
| Action Repetition | Looping on the same sequence of actions (e.g., repeatedly moving toward a blocked entity without progress) | Turn count exceeds floor reference count by > 2×; same action repeated in trace |
| Refusal / Resignation | The model produces a non-action response (e.g., "I cannot determine the best move" or explanatory text only) | Parse failure; response contains no digit matching `ACTION: N` pattern |

Category II constraint violations are largely eliminated by the action enumeration: the BFS-based action list contains only currently valid actions (doors with insufficient keys are excluded).
In practice, the main source of constraint-like failures is the model selecting a fight it cannot win (`can_win = false`), which the interface allows but the strategy forbids.

###### D.1.7.2 Application to Experimental Results

Table D.15 categorises the observed failures of E1–E10 using the taxonomy above.

**Table D.15:** Failure categories observed in E1–E10.

| Experiment | Configuration | Category I (Planning) | Category II (Tactical) | Category III (Execution) |
|-----------|--------------|----------------------|----------------------|------------------------|
| E1 | Arch A v1 (30B) | Horizon collapse (6/17 killed); resource mismanagement (shop=0.30) | — | — |
| E1 | Arch B (One-Shot) | — | — | — |
| E2 | Arch A v3 (30B, GEPA) | Suboptimal pathing: forgot collect-before-fight mid-episode | — | — |
| E5 | 70B / 235B | — | — | — |
| E7 | Qwen3.5-27B dense | — | **Suicide fight** (died T19) | — |
| E7 | Qwen3.5-35B MoE | — | — | — |
| E9 | Oneshot (simple) | — | — | Formatting: 28–30/36 heuristic fallbacks (coord plan poorly parsed) |
| E9 | Multistep-10 (MT3) | — | **Suicide fight** against the Skeleton; plan degeneracy (2×10 repeat) | — |
| E9 | Reactive (complex) | — | **Suicide fight** Enemy #206 (died) | — |
| E9 | Multistep-5/10 (complex) | — | **Suicide fight** Enemy #201/#205 (died) | — |
| E10 | text\_only (1.6B) | Suboptimal pathing: fought the Skeleton at T5 before stat gear (dmg=315) | — | — |
| E10 | image\_only (1.6B) | None (deferred costly fights until stats built) | — | — |

The E10 rows describe episodes in which every decision was taken by the heuristic fallback (D.1.11).

**Dominant failure patterns:**

1. **Category I, suboptimal pathing**, was the most common failure. Both the 30B reactive model (E1/E2) and the 1.6B vision-language text modes (E10) fought expensive enemies before collecting stat-boosting items. The record gave different causes: the 30B model lacked a persistent floor-level memory (its per-turn decisions were locally coherent but globally inconsistent), while the 1.6B model was drawn to `blocksStrategic: true` annotations regardless of HP cost.

2. **Category II, the suicide fight**, was the most severe failure, causing death in E7 (27B dense), E9 (all multistep modes on the complex floor) and E9 (multistep-10 on MT3). It is a tactical calculation error: the model knows that the fight damage exceeds its HP but selects the fight anyway. Reactive mode mitigated it because each turn shows the updated HP after intervening actions.

3. **Category III, formatting errors**, appeared mainly in the one-shot mode (E9), where 78–83 % of turns fell back to the heuristic because the coordinate plans were poorly formatted. One-shot planning thus produced plans that the execution engine could not reliably consume.

##### D.1.8 Architecture C: Fine-Tuned Small Model

The first account of the fine-tuned small model (Architecture C) stood here: its training setup, the data-quality ablation C1, the in-distribution pilot, the hardware limits and the solver-guided distillation C2.
Appendix E reports these experiments and their assessment; its episode at 13 HP is not attributed to the small model alone, because the engine of that time still applied unlogged strategic overrides (Section E.4).

##### D.1.9 E8: Java BFS Reference Baseline

To obtain a reference for single-floor play, the Java BFS solver (`magic-tower-AI/AI/src/`), the published solver of Section 4.6, was run on the AI test floors.
Its values served as `target_hp` in the composite scorer for E9 and E10.

###### D.1.9.1 BFS Results on All AI Test Floors

**Table D.16:** E8: published solver on the two single-floor AI test floors. On the complex floor, the best route it reports is not optimal (D.1.9.2).

| Floor | Grid | BFS States | Solutions | Best HP (published solver) | ATK | DEF | Kills/Total | Runtime |
|-------|------|-----------|-----------|----------------|-----|-----|-------------|---------|
| Simple | 11×11 | 412 | 1 | **13** | 13 | 8 | 12/13 | 0.049 s |
| Complex | 13×13 | 703,456 | 13 | **22** (exact optimum 68) | 14 | 17 | 13/26 | ~2 s |

The two multi-floor test maps that ship with the solver have no solution within its 45-decision depth limit and are not used (Appendix B.2.4).

###### D.1.9.2 Key Findings

**Simple floor**: the single solution ends with HP=13 out of 470 initial HP, a 97.2 % HP loss.
The boss fight alone drives this cost: the boss has DEF=12, so the hero's ATK of 13 deals only 1 damage per turn, which takes 49 turns of combat during which the hero takes 12 damage per turn (588 total).
No route does better; 13 HP is the exact optimum.

**Complex floor**: 703,456 states were explored; the published solver reports 13 paths, all ending at HP=22, which kill 13 of the 26 enemies.
The skipped monsters include those with magic attack (hero DEF counts as 0) or break armour (⌊0.9 · hero DEF⌋ added before the fight), which the published route treats as costing more than they unlock at the hero's stat ceiling.
HP 22 is not the optimum.
The published solver keeps the first state it reaches for each set of cleared nodes instead of the best one (Section 4.6).
With that corrected, the optimum is HP 68 (ATK 16, DEF 20, MDEF 20, 16 fights including the boss), and the route replays legally in the game engine.
Every use of HP 22 as the complex-floor optimum in this appendix was re-expressed against 68 on 29 September 2026; success rates are unaffected.

**Multi-floor floors**: the framework's Python solver works floor by floor; the Java solver with the full graph can handle multi-floor connectivity but still finds no solution within depth 45.
These floors appear to require resources from earlier floors of the full game progression.

##### D.1.10 E9: Planning Horizon Experiment

> **Superseded (29 September 2026).** This section reports single episodes on the April–May stack, scored with the legacy composite. Its one-shot numbers are heuristic runs: the coordinate plans were almost never matched (28–32 of 36 turns fell back to the heuristic). The same defect was found again, and removed, in the final study. The planning-granularity question is answered by Section 6.6, on the final harness, with $N = 5$ per cell, a plan check on every committed plan, and each model compared with its own reactive arm.

**Goal:** compare planning granularity: reactive (one model call per turn), chunked (a plan of $N$ actions at a time) and one-shot (a single model call for the entire floor).

**Model:** Qwen3.5-397B-A17B (SAIA endpoint, thinking mode).
**BFS references:** simple floor HP 13 in 36 steps; complex floor published solver 22 (exact optimum 68) in 40 steps (D.1.9.2).

###### D.1.10.1 MT3 (Training Floor, Heuristic Target: HP=448 in ~33 Steps)

**Table D.17:** E9: planning modes of Qwen3.5-397B on MT3.

| Mode | Score | HP | ATK | DEF | Turns | LLM Calls | Notes |
|------|-------|----|-----|-----|-------|-----------|-------|
| Heuristic | 0.924 | 433 | 23 | 17 | 33 | 0 | Deterministic baseline |
| Reactive | **0.913** | 293 | 23 | 17 | 33 | 22 | 17/17 killed; HP crisis at Turn 7 (dropped to 150), recovered |
| Oneshot | **0.494** | 10 | 20 | 10 | 12 | 1 | 7/17 killed; 5/12 heuristic fallbacks; plan coord format poorly used |
| Multistep-5 | **0.963** | 381 | 23 | 17 | 34 | 7 | 17/17 killed; 1 parse error; 0 violations; healed HP crisis at Turn 20 |
| Multistep-10 | **0.441** | −165 | 10 | 10 | 10 | 2 | DIED; suicide_fight Skeleton; plan=[2×10] degenerate repetition; entity-ID reordering fatal |

###### D.1.10.2 Simple Floor (BFS Target: HP=13 in 36 Steps)

**Table D.18:** E9: planning modes of Qwen3.5-397B on the simple floor (scorer before its correction).

| Mode | Score | HP | ATK | DEF | Turns | Kills/BFS | LLM Calls | Notes |
|------|-------|----|-----|-----|-------|-----------|-----------|-------|
| Heuristic | **1.000** | 437 | 13 | 8 | 36 | 13/14 | 0 | Boss not fought |
| Reactive | **1.000** | 437 | 13 | 8 | 36 | 13/14 | 36 | Matches heuristic exactly |
| Oneshot | 0.47–1.00¹ | var | 13 | 8 | 36 | var | 1 | High variance; 28–30/36 heuristic fallbacks |
| Multistep-5 | **0.952** | 218 | 13 | 6 | 28 | 11/14 | 13 | DEF=6 vs target 8; plans ~3 actions/call |
| Multistep-10 | **0.952** | 218 | 13 | 6 | 28 | 11/14 | 12 | Identical to Multistep-5 |

HP 437 with 13 of 14 kills means that the boss was not fought.
The scores of 1.000 for this outcome are those of the scorer before its correction (D.1.16), which scored every episode that completed the stat collection as 1.000; E19 scores the same outcome 0.371.

###### D.1.10.3 Complex Floor (Exact Optimum HP 68)

**Table D.19:** E9: planning modes of Qwen3.5-397B on the complex floor.

| Mode | Score | HP | ATK | DEF | Turns | Kills/BFS | LLM Calls | Notes |
|------|-------|----|-----|-----|-------|-----------|-----------|-------|
| Heuristic | **0.890** | 190 | 11 | 14 | 31 | 10/26 | 0 | Safe; avoids lethal fights |
| Reactive | **~0.652** | −105 | 11 | 14 | 32 | 11/26 | 32 | DIED: suicide\_fight Enemy #206 |
| Oneshot | **0.890** | 190 | 11 | 14 | 31 | 10/26 | 1 | 30/31 heuristic fallbacks; LLM plan unused |
| Multistep-5 | **0.571** | −47 | 11 | 14 | 23 | 8/26 | 6 | DIED: suicide\_fight Enemy #205 |
| Multistep-10 | **0.508** | −41 | 11 | 14 | 14 | 6/26 | 5 | DIED: suicide\_fight Enemy #201 |

¹ Two independent runs: 0.470 and 1.000, both with near-total heuristic fallback. The score depends on which actions the heuristic executes.

###### D.1.10.4 Key Findings

1. **Reactive mode was the safest**: turn-by-turn state feedback corrected lethal fight selection, and the agent backed off when a fight became too expensive for its current stats. It matched the heuristic on the simple floor (boss not fought, D.1.10.2) and recovered from near-death states on the complex floor more reliably than the multistep modes.

2. **Chunk size made no difference**: multistep-5 and multistep-10 produced identical results on the simple floor (HP=218, DEF=6, 28 turns). The model generated about three action IDs per call regardless of the requested chunk size, so requesting longer planning horizons had no observable benefit.

3. **One-shot was effectively the heuristic**: on both floors, 28–30 of the turns fell back to the heuristic (coordinate plan poorly parsed). The headline score of 0.890 on the complex floor is the heuristic's score, not the model's. The high variance (0.470 and 1.000 on the same simple floor in two runs) confirms that the model's plan was largely bypassed.

4. **Suicide fights**: all multistep modes led to the hero's death on the complex floor by selecting a fight with `totalDamage > heroHP`. This is a Category II failure (tactical calculation error): the model knows the remaining HP and the fight damage but still selects the lethal action. Reactive mode avoided it in these episodes because each turn's state shows the updated HP after any intervening heuristic actions.

5. **Heuristic score per floor**: the heuristic scored 1.000 on the simple floor (an artefact of the scorer, D.1.10.2) and 0.890 on the complex floor, where it avoided the expensive fights and survived without defeating the boss. The record's reading that no strategy does better than 0.890 on the complex floor does not hold: the exact optimum defeats the boss with 68 HP (D.1.9.2).

##### D.1.11 E10: Vision-Language Modality Experiment

Section 6.8.1 summarises this pilot.
In its valid run (E15, D.1.11.1), all three conditions scored between 0.44 and 0.49 on the composite score used at the time, and all episodes ended with the hero's death; the image added no benefit.

**Goal:** compare three input representations for LFM2.5-VL-1.6B (local RTX 2080 GPU, 3.2 GB fp16).

**Hardware note:** `from_pretrained` fails on Windows with a paging-file error when memory-mapping a 3 GB safetensors file. It was fixed with a custom streaming reader (`struct.unpack` header + `file.read()` per tensor) that loads directly to CUDA and bypasses memory mapping.

**Table D.20:** E10: LFM2.5-VL-1.6B on MT3 by input representation (invalid, see the validity note).

| Mode | Score | HP | LLM Calls | Time/Call | Notes |
|------|-------|----|-----------|-----------|-------|
| Heuristic (baseline) | 0.891 | 433 | 0 | — | Deterministic |
| text\_only | **0.494** | −5 | 6 | 21.8s | Died T13; fought the Skeleton at T5 (dmg=315) before stat gear |
| image\_text | **0.494** | −50 | 6 | 0.6s* | Identical score; slightly different death turn (T13 small bat) |
| image\_only | **0.817** | +158 | 18 | 3.0s | 15+ kills; avoided the Skeleton until ATK/DEF built; dmg dropped 315→156→104 |

\*image\_text was fast because the model was already loaded and vision adds less than 1 s to the existing inference.

> **Validity note: the E10 results are heuristic fallback, not vision-language output.** Post-run inspection of `VL_comparison_20260413_005920.json` showed that LFM2.5-VL-1.6B produced 17/17 parse errors across all modes, so every turn fell back to the deterministic heuristic. The scores `image_only=0.817` and `text_only=0.494` above are therefore heuristic scores under different prompt contexts, not evidence of vision-language reasoning, and support no conclusion about the modality. D.1.11.1 gives the valid comparison (E15).

###### D.1.11.1 E15: Vision-Language Modality with a Cloud Model (Qwen3-Omni)

To obtain a valid vision-language baseline, E15 repeated the three-condition comparison with **qwen3-omni-30b-a3b-instruct** (Qwen3-Omni-30B, SAIA endpoint, MT3), which produced valid responses on all turns (Table D.21).

**Table D.21:** E15: Qwen3-Omni-30B on MT3 by input representation.

| Mode | Score | HP | LLM Calls | Time/Call | Notes |
|------|-------|----|-----------|-----------|-------|
| Heuristic (baseline) | 0.891 | 433 | 0 | — | Deterministic |
| text\_only | **0.441** | died | 5 | — | Died; fought the Skeleton before buying DEF at shop |
| image\_text | **0.494** | died | 6 | — | Died; same failure pattern |
| image\_only | **0.494** | died | 6 | — | Died; same failure pattern |

**Key findings (E15):**
- All three modes score about 0.49 and die; visual input added no measurable benefit for this 30B mixture-of-experts model.
- The failure was the same in every mode: the agent fought the Skeleton before buying DEF at the shop and lost HP it could not recover. Vision did not help the model avoid this strategic mistake.
- This is consistent with the BALROG benchmark finding (Paglieri et al., 2025) that vision-language agents perform no better than text-only agents on structured game environments.
- The record attributed the gap between the model and the heuristic (0.49 against 0.891) to strategic planning rather than to the choice of representation.

##### D.1.12 E11: Per-Decision BFS Alignment

**Goal:** measure the quality of strategic reasoning at every decision point by comparing each model action with the BFS oracle, using exact match and equivalence match.

**Model:** Qwen3.5-397B-A17B (SAIA endpoint, thinking mode).
**Floor:** simple AI test floor (BFS optimal HP=13, 17 BFS-optimal decisions).
**Oracle:** at each decision point with $k$ available actions, $k$ mini-BFS searches identify all actions that keep the globally optimal HP reachable; the equivalence set contains all such actions.

> **Note.** The HP values of E11 were recorded by the development harness, before overrides were logged. The repeated runs of Chapter 6 do not reproduce them: every win in Table 6.2 on the simple floor ends at 2 HP, and a win at 13 HP occurs once among the repeated runs (Section 6.2). The floor has 13 HP of slack, and one ordering call is worth 12 HP (Section 6.4.5, Table 6.5). The readings of this section that rest on HP 13 as the normal outcome ("forgiving", "permutation-invariant") are superseded (Table D.1).

###### D.1.12.1 Per-Decision Results, Reactive Mode

The reactive evaluator makes one model call per decision. Because its ordering differs from the solver's, the model's path diverges into 35 decisions in total (against 17 on the BFS-optimal path), as Table D.22 shows.

**Table D.22:** E11: per-decision alignment of the reactive mode on the simple floor.

| Metric | Value |
|--------|-------|
| Exact match | 20/35 = 57.1% |
| Equivalence match | 31/35 = 88.6% |
| Final HP | 13 (= BFS optimal) |
| Goal reached | Yes |
| LLM calls | 35 |
| Wall time | 704.6s |

**Mismatch analysis:** of the 4 true mismatches (non-equivalent decisions):
- **D2, D7** (fight before door): the model fights an expensive enemy instead of opening a yellow door, a consistent "fight-first" bias when both options are available.
- **D33, D34** (endgame boss ordering): with only 2 choices remaining, the model fights the weaker enemy before the boss, and the solver prefers the opposite order. Both orderings yield the same final HP; the solver's tie-break is arbitrary.

The 11 equivalence matches cluster in the mid-game (D11–D19), where 3–5 BFS-equivalent actions exist at each decision point, a phase in which several collect and fight orderings lead to identical outcomes.

###### D.1.12.2 Per-Decision Results, Multistep-5 Mode

The multistep-5 evaluator plans 5 actions per model call and consumes a buffered plan until it becomes stale (Table D.23).

**Table D.23:** E11: per-decision alignment of the multistep-5 mode on the simple floor.

| Metric | Value |
|--------|-------|
| Exact match | 11/35 = 31.4% |
| Equivalence match | 16/35 = 45.7% |
| Final HP | 13 (= BFS optimal) |
| Goal reached | Yes |
| LLM calls | 10 |
| Wall time | 330.4s |

**Analysis:** multistep-5 shows much lower per-decision accuracy than reactive (45.7 % against 88.6 % equivalence), yet this episode ended at the same HP of 13.
At the time, this was read as a property of the simple floor: an action set forgiving enough that even a suboptimal ordering reaches the optimal outcome, because no fight is lethal given the hero's available stat items.
This reading is superseded (note above).

The accuracy loss had two causes specific to the multistep mode:
1. **Stale plan consumption**: after the first 1–2 actions of a 5-action plan, the later action IDs referred to entities that had been killed or whose IDs had been reassigned.
2. **Amplified fight-first bias**: the chunked plan front-loaded fights (D0–D4 all select fights or fight-gated actions), whereas the solver interleaves doors and collections.

###### D.1.12.3 Per-Decision Results, Oneshot Mode

The oneshot evaluator first simulates the BFS-optimal path to collect all 17 decision states and then sends all states in a single model call, requesting a complete plan (Table D.24).

**Table D.24:** E11: per-decision alignment of the oneshot mode on the simple floor.

| Metric | Value |
|--------|-------|
| Exact match | 2/35 = 5.7% |
| Equivalence match | 5/35 = 14.3% |
| Final HP | 13 (= BFS optimal) |
| Goal reached | Yes |
| LLM calls | 1 |
| Wall time | 180.1s |

**Analysis:** oneshot had the lowest per-decision accuracy of the three modes: only 2 exact matches and 3 further equivalence matches out of 35 decisions.
Many plan entries contain invalid action IDs (e.g., `id=0`, `id=34`, `id=204`) that correspond to no available action at the respective decision point.
This confirms the E9 finding (D.1.10.4): the oneshot plan format is too fragile for multi-decision execution, because action IDs are state-dependent and change between decision points.

The episode nevertheless ended at HP 13.
The 30 non-matching decisions executed whatever action the invalid ID was mapped to, or the first available action as fallback.
The record took this as evidence that even a near-random ordering converges to the optimum on the simple floor; this reading is superseded (note above).

###### D.1.12.4 Comparative Summary

**Table D.25:** E11: summary of the three modes on the simple floor.

| Mode | Exact | Equiv | HP | LLM Calls | Time |
|------|-------|-------|-----|-----------|------|
| Reactive | 20/35 (57.1%) | 31/35 (88.6%) | 13 | 35 | 705s |
| Multistep-5 | 11/35 (31.4%) | 16/35 (45.7%) | 13 | 10 | 330s |
| Oneshot | 2/35 (5.7%) | 5/35 (14.3%) | 13 | 1 | 180s |

###### D.1.12.5 Key Findings

1. **Equivalence matching is necessary**: without it, the reactive agent appears to make 15 errors (42.9 % exact accuracy). With it, 11 of these "errors" turn out to be alternative orderings that keep the optimum reachable, and the accuracy rises to 88.6 %. Exact-match metrics thus underestimate strategic quality where several optimal orderings exist.

2. **Per-decision accuracy did not predict the outcome in this harness**: all three modes, reactive (88.6 % equivalence), multistep-5 (45.7 %) and oneshot (14.3 %), ended at HP 13. The record concluded that the simple floor has permutation-invariant action ordering, in which no fight's cost depends on the order of the other fights. This conclusion is superseded: on the simple floor, the order of two fights over the same monsters changes the cost by 12 HP (Section 6.4.5, Table 6.5).

3. **Reactive mode generated more decisions at higher accuracy**: the 35-decision reactive path (against 17 on the BFS-optimal path) results from early ordering divergence. Once the model fights an enemy "out of order" at D2, the state leaves the BFS-optimal trajectory and creates new decision points at intermediate states that the solver would have avoided. Reactive per-decision quality stayed high (88.6 % equivalence) because each turn received a fresh state.

4. **Model calls against accuracy**: reactive used 35 times more model calls than oneshot (35 against 1) and 3.5 times more than multistep-5 (35 against 10), for 88.6 %, 14.3 % and 45.7 % equivalence accuracy. The complex-floor evaluation below tested whether the accuracy advantage of the reactive mode translates into an outcome advantage where fight ordering creates damage cascades.

5. **The oneshot plan format did not work**: its action IDs are valid only at the first decision point. By D5, most plan entries referenced non-existent action IDs, which made the plan effectively random. Action IDs are state-dependent and cannot be predicted from an initial snapshot.

###### D.1.12.6 Complex Floor Setup

Because all three modes ended at HP 13 on the simple floor in this harness, the complex floor was used to test whether per-decision accuracy matters where fight ordering creates damage cascades.

**Complex floor parameters:**
- 13×13 grid, 8 enemy types (including boss #299); published solver 22 (exact optimum 68, D.1.9.2)
- Hero start: HP=1000, ATK=10, DEF=10
- 13 published-solver solutions, 703,456 reachable states, 19 BFS decision nodes
- Enemy special abilities: triple-hit (#201), armour-break (#203), magic-attack (#204), double-hit (#205), first-strike (#207), quad-hit (boss #299)
- The published solver's route avoids #203, #204 and the extra #201/#207 instances; the special abilities make them expensive at base stats

> **Correction (29 September 2026).** The exact optimum (HP 68, Section 4.6) does not avoid these monsters. It fights both armour-break monsters (#203 at (2,9) and (12,9)), the magic-attack monster (#204 at (3,10)) and two first-strike monsters (#207 at (0,9) and (4,2)). It takes them after raising DEF, MDEF and ATK, so their cost falls. Throughout D.1.12.6 to D.1.12.10, "BFS-avoided" means "avoided by the published solver's HP-22 route", and the reading "the gap is enemy avoidance" is replaced by "the gap is fight timing relative to the stat items" (finding 4 of D.1.12.10).

**Evaluation method:** per-decision Python BFS is computationally infeasible on the complex floor (about 100 s per decision × 25+ decisions).
Instead, a *free-play* mode was used: the model's chosen action is executed directly (no oracle), and the final HP is compared with the published solver's 22 HP (exact optimum 68).
The meaningful metric is the outcome, whether the agent survives and kills boss #299, rather than per-decision accuracy.

###### D.1.12.7 Complex Floor, Reactive Mode

**Table D.26:** E11: reactive mode on the complex floor (free play).

| Metric | Value |
|--------|-------|
| Decisions before death | 25 |
| Final HP at death | 184 |
| Reference HP | published solver 22 (exact optimum 68) |
| Goal reached (boss killed) | No |
| LLM calls | 25 |
| Wall time | 544.3s |

The reactive agent survived longer than either planning mode but died at D24 (fight #205, double-hit, damage=235 > HP=184).
It fought all 8 enemy types, including three that the published route avoids:

- **D12: #203 (armour-break)**, damage 153. The record explained the published route's avoidance by the armour-break ability (special=7), which it described as ignoring hero DEF. Break armour instead adds ⌊0.9 · hero DEF⌋ damage before the fight (Table 4.1), and the exact optimum fights both armour-break monsters after raising DEF.
- **D15: #204 (magic-attack)**, damage 235. Magic attack (special=2) ignores DEF entirely; only ATK reduces the number of turns, and MDEF reduces the final damage by 1 per hit.
- **D18: #207 (first-strike)**, damage 303. The published route avoids this instance because first strike adds a free monster hit; at hero DEF=10, the extra hit costs 46 HP.

The agent collected 4 Red Potions (+75 HP each = 300 HP recovered) and 4 Blue Gems (+1 DEF each), but the 691 HP spent on fights that the published route avoids ($153 + 235 + 303$) created a deficit it could not recover.
The total fight damage of 1,816 HP exceeded the 1,000 starting HP plus the 300 HP of potions, which guaranteed death before the boss.

###### D.1.12.8 Complex Floor, Multistep-5 Mode

**Table D.27:** E11: multistep-5 mode on the complex floor (free play).

| Metric | Value |
|--------|-------|
| Decisions before death | 12 |
| Final HP at death | 143 |
| Reference HP | published solver 22 (exact optimum 68) |
| Goal reached (boss killed) | No |
| LLM calls | 3 |
| Wall time | 109.6s |

Multistep-5 produced the worst outcome, and its first 5-action plan (model call 1) was decisive (Table D.28).

**Table D.28:** E11: the first 5-action plan of the multistep-5 mode on the complex floor.

| Step | Action | Damage | HP After |
|------|--------|--------|----------|
| D0 | Collect Blue Key | 0 | 1000 |
| D1 | Fight #201 (triple-hit) | 120 | 880 |
| D2 | Fight #207 (first-strike) | 368 | 512 |
| D3 | Fight #204 (magic-attack) | 240 | 272 |
| D4 | Fight #203 (armor-break) | 204 | 68 |

This single 5-action plan spent 932 HP (93.2 % of the starting HP) on three monsters in sequence that the published route avoids.
With only 68 HP left after plan 1, recovery was impossible.
The second plan collected potions and gems (HP recovered to 143), but the third plan attempted #204 again (damage 235 > HP 143), and the hero died at D11.

This confirms the E9 finding (D.1.10): multistep planning amplified a bad fight ordering by committing to several fights without re-evaluating the state between them.
The first 5 actions account for 82 % of all HP damage in the run.

###### D.1.12.9 Complex Floor, Oneshot Mode

**Table D.29:** E11: oneshot mode on the complex floor (free play).

| Metric | Value |
|--------|-------|
| Decisions before death | 13 |
| Final HP at death | 277 |
| Reference HP | published solver 22 (exact optimum 68) |
| Goal reached (boss killed) | No |
| LLM calls | 1 |
| Wall time | 44.7s |

The oneshot mode used coordinate-based planning without an oracle (free play): the model received the floor map and the initial state, wrote a complete coordinate plan, and the system executed it greedily.
Although it had the weakest per-decision accuracy on the simple floor, oneshot ended with the highest HP at death of the three complex-floor modes (277 against 184 reactive and 143 multistep-5).

The coordinate plan interleaved item collection between fights.
After fighting #201 (120 damage) and #207 (368 damage), the plan collected gems, keys and potions before the next fight, a pattern closer to the published solver's route than the eager fighting of the reactive and multistep modes.
The plan still included #207 and #204 (both avoided by the published route), and the hero died at D12 in a lethal fight.

###### D.1.12.10 Complex Floor Comparative Summary

**Table D.30:** E11: the three modes on the complex floor against the published route and the exact optimum.

| Mode | HP at Death | Decisions | LLM Calls | Time | Fatal Error |
|------|------------|-----------|-----------|------|-------------|
| Reactive | 184 | 25 | 25 | 544s | Fought 3 monsters the published route avoids |
| Multistep-5 | 143 | 12 | 3 | 110s | 932 HP in first 5-action plan |
| Oneshot | 277 | 13 | 1 | 45s | Fought 2 monsters the published route avoids |
| **Published-solver route** | **22** | **19** | **—** | **—** | **Avoids #203, #204, extra #201/#207** |
| **Exact optimum (Section 4.6)** | **68** | **20** | **—** | **—** | **Fights #203 ×2, #204, #207 ×2 after DEF/MDEF/ATK gains** |

**Key findings:**

1. **All modes died on the complex floor**: unlike the simple floor, where all modes ended at HP 13 in this harness, no mode survived the complex floor.

2. **Fight ordering mattered decisively**: fighting #207 at base stats costs 368 HP, 37 % of the 1,000-HP budget. The published route never fights #207, and the exact optimum fights two first-strike monsters only after raising its attributes. The record's contrast with a "permutation-invariant" simple floor is superseded (Table D.1).

3. **More model calls did not give better outcomes**: reactive (25 calls, HP=184) ended with less HP than oneshot (1 call, HP=277), which inverts the simple-floor ranking by per-decision accuracy. On the complex floor, the reactive mode's "fight-first" bias triggered fights as soon as they became reachable, while the oneshot plan's fixed coordinate sequence forced item collection between fights.

4. **The critical gap is fight timing relative to the stat items** (corrected 29 September 2026). All three modes fight the armour-break, magic-attack and first-strike monsters at base stats, where they cost 150–370 HP each. The exact optimum fights five of them too, but only after the DEF, MDEF and ATK items that make them cheap. The model sees the monsters' stats and abilities in the prompt but does not order these fights after the relevant stat items. The earlier reading, that the gap is enemy avoidance, rested on the published solver's HP-22 route and no longer holds.

###### D.1.12.11 Map-Based Reasoning Experiment (E12, Pathfinder Removal)

**Motivation:** all preceding experiments use the pathfinder abstraction: the formatter presents the model with a numbered list of reachable actions (fight, collect, open door), with pre-computed damage costs, HP projections and lookahead scores.
This experiment tested whether the model can reason directly from spatial map data without the pathfinder.
The map-only condition of Section 6.3 (Table 6.4) repeats this ablation with $N = 2$ per model.

**Design:** two new modes were introduced:

- **Map-reactive**: each turn, the model receives a text grid of the floor (`@`=hero, `#`=wall, `.`=ground, `M<id>`=monster, `I`=item, `Y/B/R`=doors) and a legend with entity stats and fight costs. It answers `TARGET: (x,y)`, a coordinate to move to; the game engine handles pathfinding and interaction.
- **Map-oneshot**: the model receives the grid once and answers `PLAN: (x1,y1), (x2,y2), ...`, a complete coordinate sequence executed greedily.

Neither mode receives the formatted action list, the lookahead trees or the pre-computed `hpAfter` and `effCost` values.
The model must infer reachability, door-key dependencies and fight order from the raw grid.

**Results** (Table D.31):

**Table D.31:** E12: map-based modes of Qwen3.5-397B on the simple and complex floors.

| Floor | Mode | HP | BFS Opt | Goal | Decisions | LLM Calls | Time |
|-------|------|----|---------|------|-----------|-----------|------|
| Simple | Map-reactive | 59† | 13 | DIED (D13) | 14 | 14 | 229s |
| Simple | Map-oneshot | 63 | 13 | No (plan exhausted) | 4 | 1 | 28s |
| Complex | Map-reactive | 263† | 22 (exact 68) | DIED (D4) | 5 | 5 | 49s |
| Complex | Map-oneshot | 1000 | 22 (exact 68) | No (plan exhausted) | 2 | 1 | 20s |

**Comparison with the standard modes (same model, same floor)** (Table D.32):

**Table D.32:** E12: standard modes (E11 harness) and map-based modes compared.

| Floor | Standard Reactive | Standard Oneshot | Map-Reactive | Map-Oneshot |
|-------|-------------------|------------------|--------------|-------------|
| Simple | HP=13 ✓ (BFS-opt) | HP=13 ✓ (BFS-opt) | HP=59 DIED | HP=63 (no goal) |
| Complex | HP=184 DIED | HP=277 DIED | HP=263 DIED (D4) | HP=1000 (no goal) |

####### Analysis

**Simple floor, collapse**: in the E11 harness, all three standard modes ended at HP 13 with the boss killed.
Both map modes failed: map-reactive died at decision 13 (a lethal fight chosen), and map-oneshot produced only 4 actions (all fights; no items, no doors, no boss).
With grid input, the model fought aggressively without interleaving item collection; it did not infer that items are free without the pathfinder labelling them as zero-cost collect actions.

**Complex floor, plan collapse**: map-reactive died at decision 4 after only 5 turns, having lost 737 HP on three monsters that the published route avoids (#207=368, #204=240, #203=204).
Map-oneshot output only 2 actions (collect Blue Key, collect Yellow Key), and then the plan stopped: the model did not turn the 13×13 grid into a coherent multi-step route.

**Key findings:**

1. **The pathfinder abstraction was the critical component.** Removing it made the simple floor, which all standard modes had ended at HP 13 in the E11 harness, unsolvable in these episodes. The gap is one of representation, not of prompt engineering.

2. **Spatial pathfinding from text grids failed.** Although the grid was complete, Qwen3.5-397B did not infer reachability (which entities can be reached without keys or fights), door-key dependencies or a sensible traversal order. The text grid is informationally complete but computationally opaque.

3. **Fight-first bias without cost annotations**: without the pathfinder's damage annotations (`totalDamage`, `hpAfter`, `effCost`), the model defaulted to fighting the nearest visible enemy. On the simple floor, map-reactive fought two copies of #204 (114 HP each) before collecting any free item; standard reactive collects items first because they appear as zero-cost actions in the sorted list.

4. **Truncated plans without action enumeration**: map-oneshot produced very short plans (4 actions on the simple floor, 2 on the complex floor) against standard oneshot (35 decisions on the simple floor, 13 on the complex floor). The model did not simulate the game state after each action without the pathfinder recomputing the available choices.

5. **Consistency with the hybrid design**: the model's contribution is strategic priority (which action to choose from an enumerated list), not spatial reasoning (which actions exist). The deterministic engine supplies the spatial grounding that makes the model's reasoning effective; without it, Qwen3.5-397B produced very short or fatal plans in these episodes.

##### D.1.14 GEPA Generalisation Study: Smaller Task Models and Multi-Floor Scenarios (E16–E18)

Experiments E16–E18 extended the GEPA runs beyond the standard MT3 setting in two ways: (1) a weaker, faster task model (`meta-llama-3.1-8b-instruct`, Llama-3.1-8B, about 0.5 s per call) to reduce evaluation cost, and (2) a two-floor sequential scenario (MT3 → MT4).
The question was whether the reflection mechanism can compensate for a weaker task model and generalise to multi-floor objectives.

###### D.1.14.1 E16: GEPA with Llama-3.1-8B on MT3

**Configuration.** The task model was Llama-3.1-8B in instruct (non-thinking) mode, about 40 times fewer parameters than the Qwen3.5-397B teacher of these runs.
The seed prompt was `mt3_bare.txt`: a minimal scaffold containing only game mechanics and the floor goal (reach the stairs up), with no strategic rules.
The reflection model remained `qwen3.5-397b-a17b`, and early stopping was set to a score of at least 0.95.

**Results.** The seed prompt scored 0.4408: the agent died at turn 8 from a suicide fight (it attempted the Bat at HP=65 when the fight cost 72 HP).
After a single reflection call (83.3 seconds), the evolved prompt scored 0.9916, which triggered early stopping after 3 evaluations in total (Table D.33).

**Table D.33:** E16: GEPA with Llama-3.1-8B on MT3.

| Stage | Score | Notes |
|-------|-------|-------|
| Seed (`mt3_bare.txt`) | 0.4408 | Died T8: suicide\_fight Bat (HP=65 < cost=72) |
| After 1 reflection (83s) | **0.9916** | Early stop (3 evals total) |

The reflection model diagnosed the failure from the score breakdown and the trace: the agent lacked a survival check before fights and had no shop-first protocol.
The evolved prompt added (i) a SHOP FIRST rule (visit the shop before heavy enemies, target DEF ≥ 17), (ii) a SURVIVAL CHECK (skip a fight if `expected_damage ≥ current_HP`), and (iii) a STAIRS PROTOCOL (do not use the stairs until the floor is cleared).

**Reading at the time.** The record took the +125 % gain from one 83-second reflection call as evidence that reflection can compensate for a weaker task model and that correctly stated strategic rules matter more than model scale.
It also stated that Llama-3.1-8B with the evolved prompt (0.9916) "significantly outperforms" Qwen3.5-397B with the bare seed, quoting 0.4408, which is the Llama-3.1-8B seed score above; no test was run.
Both scores are single episodes accepted without repetition; under the repeated, paired evaluation of Section 6.5, evolved prompts stay within the noise floor under the full observation (Table D.1).

###### D.1.14.2 E18: GEPA on the Simple Benchmark Floor, Re-Verified

**Configuration.** The same Llama-3.1-8B task model was applied to the simple benchmark floor (11×11, 14 enemies, goal: kill boss #299).
The seed prompt was `bare.txt`, a score-aware minimal scaffold without strategic rules; early stopping at 0.95.

**Original results (broken scorer).** Seed score 0.5693; after 1 reflection (83 s), the evolved prompt scored 1.0000, as if one step had perfected the prompt.

**Re-verification with the corrected scorer (confirmed 2026-04-22).** The 1.0000 was a false positive caused by the three-bug scoring error documented in D.1.16.
Re-running both prompts with the corrected scorer gave the results of Table D.34.

**Table D.34:** E18: seed and evolved prompt on the simple floor, re-scored with the corrected scorer.

| Prompt | Score (corrected) | Final HP | Steps | Boss? | Violations |
|--------|-------------------|----------|-------|-------|-----------|
| Seed (`bare.txt`) | 0.5437 | −1 | 17 | Suicide | `suicide_fight: Enemy #299` |
| Evolved (GEPA output) | **0.3721** | 352 | 36 | ✗ | `boss_not_killed` |

Under the corrected scorer, the evolved prompt fell below the seed (0.54 → 0.37).
The reflection had found that fighting the boss with low DEF caused death and had added a COMBAT SAFETY rule: *"Do not fight Boss #299 with low DEF (e.g., DEF < 15)."*
Because the maximum reachable DEF on this floor is 8, well below the rule's threshold of 15, the evolved prompt permanently prevents the boss fight.
The agent completes all 13 non-boss enemies (ATK=13, DEF=8, HP=352) but stops at the boss and scores 0.37 under the boss-not-killed multiplier.

The reflection model thus proposed a correct safety principle with a wrong parameter.
The true condition for a winnable boss fight is ATK ≥ 13 (boss DEF=12) and HP ≥ 589 (the boss costs 588 damage), not DEF ≥ 15.
The reflection model generalised from "DEF is too low, so the hero died" to "require DEF ≥ 15" without computing the damage formula for this floor.

**Root cause of the original 1.0000.** Under the broken scorer, `hp_score = 1.0` whenever `final_hp ≥ target_hp` (13), completion was capped at 1.0 when all non-boss enemies were killed, and `goal_reached` was never checked.
Any agent that completed all 13 stat-collection enemies scored 1.0000 whether or not the boss was fought, and the reflection had taught the agent to do exactly this.

**Reading.** E18 does not show that GEPA works on this floor; it shows a false convergence caused by misaligned scorer incentives.
The later analysis (E22, D.1.17) used a seed derived from a manual run that encodes the HP reservation needed to kill the boss.

**Note on seed score variance.** The E18 GEPA run reported a seed score of 0.5693 internally; an independent re-run, used in the re-verification, scored 0.5437.
The agent died in both cases (a suicide fight and the boss at DEF=5), and the model's stochasticity changed only the step of the fatal fight.

###### D.1.14.3 E17: GEPA Multi-Floor (MT3 → MT4)

**Configuration.** GEPA was applied to a two-floor sequential objective: the agent must complete both MT3 and MT4, with the score $S = 0.50 \times \text{floor\_progress} + 0.30 \times \text{goal\_bonus} + 0.20 \times \text{hp\_ratio}$.
Task model (Llama-3.1-8B) and reflection model (`qwen3.5-397b-a17b`) were the same as in E16/E18; seed `mt3_bare.txt`; early stop at 0.95.

**Results.** The seed scored 0.846, much higher than in E16 (0.44) or E18 (0.57), because the multi-floor score's floor-progress component gives partial credit even for reaching MT4's entrance without completing it.
After 1 reflection call, the evolved prompt scored 0.941, an 11 % improvement.
All 7 reflections then stayed at 0.941, and the early-stop threshold of 0.95 was never reached (Table D.35).

**Table D.35:** E17: GEPA with Llama-3.1-8B on MT3 → MT4.

| Stage | Score | Notes |
|-------|-------|-------|
| Seed (`mt3_bare.txt`) | 0.846 | High: floor\_progress grants partial MT4 credit |
| After 1 reflection | **0.941** | Best score reached |
| Reflections 2–7 | 0.941 | Plateau; 0.95 threshold not reached |

All 7 reflections produced variations of the same rule set: SHOP IMMEDIATELY, FLOOR COMPLETION, HP SAFETY MARGIN (≥ 200), KEY CONSERVATION.
The reflection model found no new rule that broke the 0.941 ceiling, which the record attributed to Llama-3.1-8B arriving on MT4 with too little HP for the 0.20 × hp_ratio component.

**Reading.** In contrast to E16 and E18, the record saw the effect of GEPA depend on the seed score's headroom.
A bare seed (0.44–0.57) leaves clear failure traces for the reflection model; a higher seed (0.846) hides strategic gaps behind the generous partial credit for floor progress.
The reflection model identified individual rules correctly but did not overcome the multi-floor HP problem at the capability of Llama-3.1-8B.

###### D.1.14.4 Cross-Experiment GEPA Pattern

**Table D.36:** GEPA runs E3 and E16–E18: seed, best score and cost.

| Experiment | Task Model | Seed | Seed Score | Best Score | Reflections | Evals | Time |
|-----------|-----------|------|-----------|-----------|------------|-------|------|
| E3 | qwen3.5-397b | e3\_seed | 0.3997 | 0.9833 | ~3 | ~7 | ~20 min |
| E16 | llama-3.1-8b | mt3\_bare | 0.4408 | **0.9916** | 1 | 3 | ~2 min |
| E17 | llama-3.1-8b | mt3\_bare | 0.846 | **0.941** | 1 (plateau) | 7 | ~30 min |
| E18 | llama-3.1-8b | bare | 0.5437 | ~~1.0000~~ **0.3721** | — | — | FALSE POSITIVE |

**Note on E18.** The original E18 result (seed 0.5693, best 1.0000) was a false positive of the broken scorer.
With the corrected scorer, the seed scored 0.5437 (suicide fight at DEF=5) and the evolved prompt 0.3721 (boss not killed, because its DEF < 15 rule blocks the boss fight on a floor where the maximum DEF is 8).
E18 is excluded from the headroom analysis; D.1.14.2 gives the full re-verification.

The pattern of a low seed score (0.40–0.57), one reflection call and a best score of at least 0.99 held for E3 and E16, where the scorer was valid.
E17 showed the headroom constraint, and E18 a failure mode: when the scorer is misaligned, GEPA optimises the wrong objective.
The record drew three conclusions:

1. **The domain is learnable by reflection**: the failure taxonomy (suicide\_fight, shop\_skip, wrong\_buy) is small and unambiguous, so the reflection model identified the root cause in a single pass when the seed score left a detectable failure trace and the scorer was aligned.
2. **Faster evaluation accelerates GEPA**: with Llama-3.1-8B (about 0.5 s per call) instead of Qwen3.5-397B (about 6–14 s per call), E16 finished in 2 minutes against potentially more than 20 minutes for E3.
3. **Seed score headroom is the binding constraint**: a bare seed (0.44–0.57) maximises the reflection signal, while a rich seed (0.85+) compresses it; E17 (seed 0.846) improved from 0.846 to 0.941 (+11 %) but no further.

All three rest on single-episode evaluations; Section 6.5 replaces them with the repeated, paired study.

##### D.1.15 Summary of Results

Table D.37 summarises the ledger as it stood after E21.

**Table D.37:** Summary of the development experiments E1–E21 and Architecture C (single episodes; composite scores).

| Experiment | Key finding |
|-----------|-------------|
| E1 | Heuristic (0.875–0.924) above the 30B reactive model (0.379); one-shot plan (0.875) matches the heuristic |
| E2 | GEPA-optimised prompt improves Arch A (0.379→0.847) but stays below the heuristic |
| E3 | GEPA trajectory: 3 candidates in 7 evaluations, best=0.9833 (+146 % over the seed) |
| E4 | Completion (+0.65) and shop strategy (+0.70) drive the largest improvements |
| E5 | 30B=0.379, 70B=0.992, 235B=0.992; read at the time as a threshold at about 70B (not reproducible, D.1.5) |
| E6 | No positive transfer to unseen floors; model ≤ heuristic on all non-training floors |
| E7 | Qwen3.5-35B-A3B (3B active) = 0.992, matching 70B+; 27B dense = 0.506 (died); the mixture-of-experts reading does not hold (D.1.5) |
| E8 | Published solver: simple 13 HP (1 solution, the exact optimum), complex 22 HP (13 solutions; exact optimum 68); the two multi-floor test maps have no solution within the depth limit |
| E9 | Reactive safest (1.000 simple under the old scorer, ~0.913 MT3); multistep modes cause suicide fights on the complex floor |
| E10 | INVALID: LFM2.5-VL-1.6B (local) produced 17/17 parse errors; all scores were heuristic fallback. Superseded by E15 |
| E15 | Vision adds no benefit: qwen3-omni-30b, MT3: text\_only=0.441, image\_text=0.494, image\_only=0.494; all modes die. Consistent with BALROG |
| E11 | Simple: all modes HP 13 in the development harness; complex: all modes die (HP at death 184/143/277; published solver 22, exact optimum 68). Critical gap: fight timing relative to the stat items (corrected reading) |
| E12 | Map-based modes fail: simple floor HP=59/63 (against 13), complex HP=263/1000 (plan collapse). Pathfinder abstraction is the critical component |
| E16 | llama-8b + bare seed: GEPA 0.4408 → 0.9916 in 1 reflection, 3 evals, ~2 min (MT3) |
| E17 | llama-8b + mt3\_bare, multi-floor MT3→MT4: 0.846 → 0.941 (+11 %); plateau, 7 reflections |
| E18 | FALSE POSITIVE (broken scorer). Corrected: seed=0.5437 (suicide), evolved=0.3721 (boss\_not\_killed). GEPA optimised the wrong objective; the evolved DEF<15 rule blocks the boss on a floor where max DEF=8 |
| E19 | No bare-seed condition kills the boss (scoring bug found and fixed). Boss-avoidance modes ~0.371 (reactive/oneshot/heuristic); boss-attempted MS modes 0.64–0.72 (suicide, ATK=12). HP over-spending: killing all 13 non-boss enemies leaves HP=437–442 < 601 boss threshold. Highest: llama-8b MS-5=0.720. 397B MS-3/MS-5 overconfident (force the boss fight at ATK=12); llama-8b reactive dies early (T9) |
| E21 | GEPA 397B, bare seed, simple floor: seed=0.371 (boss not killed, corrected scorer); best 0.371 after 3 reflections, which hallucinated shops (D.1.17) |
| Arch C | 1.2B fine-tuned model achieves 90 % in-distribution accuracy (Appendix E) |

**Narrative at this stage.** The deterministic heuristic was a strong baseline.
The record concluded that model reasoning adds value only when (a) the model is capable enough, (b) the prompt is optimised, and (c) the architecture provides spatial grounding (pathfinding and action enumeration).
Of these, (a) rests on the model comparison of D.1.5, which is not reproducible, and (b) on single-episode gains (Table D.1); (c) is consistent with the bare-observation and map-only results of Section 6.3.
A lesson that holds is that scorer alignment matters as much as prompt alignment: E18's false positive shows that an optimiser can learn the wrong objective when the scorer rewards partial completion without penalising boss-skipping.
After the three-bug scoring error was fixed (D.1.16), E16 remained a gain on MT3 (0.44 → 0.99, one reflection), and E18 became a regression (evolved prompt 0.37, boss not killed).
E19 found that no bare-seed condition kills the boss on the simple floor: agents kill all 13 non-boss enemies and arrive at the boss with HP=437–442, below the 589 HP needed.
Multistep modes that attempted the boss at ATK=12 scored 0.64–0.72, avoidance modes about 0.371.
E21 and E22 tested whether GEPA can find the HP reservation strategy; E22 used a seed derived from a manual run that encodes the correct boss chain (D.1.17).

##### D.1.16 E19: Planning Horizon × Model Scale on the Simple Benchmark Floor

**Goal:** compare all four planning modes (reactive, multistep-3, multistep-5, oneshot) for two models (Qwen3.5-397B and Llama-3.1-8B) on the simple benchmark floor.
The experiment cross-checked the E9 planning-horizon findings with a weaker model and added a chunk size of 3.

**Background.** E9 (D.1.10), with the E3 GEPA prompt, and E11 (D.1.12) had reported near-perfect simple-floor results for the planning modes of Qwen3.5-397B.
E18 (D.1.14.2) had shown that Llama-3.1-8B in reactive mode with a bare seed scores about 0.57–0.65 and dies.
This experiment used the bare seed for both models to separate the planning architecture from prompt quality.
The question was whether planning lookahead can compensate for model weakness.
The simple floor imposes two hard constraints: (1) the hero's ATK must reach at least 13 before the boss fight (boss DEF=12, so ATK=12 deals 0 damage), and (2) the hero must keep enough HP for the 600-HP boss fight, which requires skipping 1 of the 13 non-boss enemies.

**Scorer validity.** The original E19 run used a flawed scorer that awarded 1.000 to any agent completing all stat collection, whether or not the boss was killed.
The results in D.1.16.1 come from a re-run with the corrected scorer, which penalises boss-skipping with a 0.5× multiplier; they show that no bare-seed condition reaches the floor's optimal outcome.

**Configuration:**

- **Floor:** simple AI test floor, BFS-optimal HP=13 in about 36 steps
- **Seed prompt:** `bare.txt` (minimal, no strategy rules)
- **Task models:** `qwen3.5-397b-a17b` (thinking mode) and `meta-llama-3.1-8b-instruct` (instruct mode)
- **Modes:** reactive, multistep-3 (chunk\_size=3), multistep-5 (chunk\_size=5), oneshot
- **Heuristic baseline:** run once (model-independent)

###### D.1.16.1 Results

**Table D.38:** E19: planning modes of Qwen3.5-397B and Llama-3.1-8B on the simple floor with the bare seed (corrected scorer).

| Condition | Score | HP | ATK | DEF | Kills | Steps | Boss Attempted | Violation |
|-----------|-------|----|-----|-----|-------|-------|----------------|-----------|
| Heuristic | 0.371 | 437 | 13 | 8 | 13/14 | 36 | ✗ | boss\_not\_killed |
| 397B reactive | 0.371 | 442 | 13 | 8 | 13/14 | 36 | ✗ | boss\_not\_killed |
| **397B multistep-3** | **0.672** | −1 | 12 | 5 | 11/14 | 26 | ✓ (suicide) | suicide\_fight: boss #299 |
| 397B multistep-5 | 0.643 | −1 | 12 | 5 | 10/14 | 25 | ✓ (suicide) | suicide\_fight: boss #299 |
| 397B oneshot | 0.371 | 437 | 13 | 8 | 13/14 | 36 | ✗ | boss\_not\_killed |
| llama-8b reactive | 0.248 | −7 | 11 | 4 | 6/14 | 9 | ✗ | suicide\_fight: Enemy #201; boss\_not\_killed |
| llama-8b multistep-3 | 0.372 | 389 | 13 | 8 | 13/14 | 36 | ✗ | boss\_not\_killed |
| **llama-8b multistep-5** | **0.720** | −1 | 12 | 7 | 12/14 | 33 | ✓ (suicide) | suicide\_fight: boss #299 |
| llama-8b oneshot | 0.371 | 437 | 13 | 8 | 13/14 | 36 | ✗ | boss\_not\_killed |

"Boss attempted (suicide)" means that the agent fought the boss with ATK=12 (boss DEF=12, so the hero deals 0 damage and cannot win).
The scorer applies the 0.5× multiplier for boss\_not\_killed (avoidance) but not for suicide\_fight (the goal was attempted), which explains the gap between the multistep modes (0.64–0.72) and the avoidance modes (0.37).

###### D.1.16.2 Key Findings

**1. No bare-seed condition killed the boss; HP preservation was the critical gap.**

The challenge of the simple floor is not stat collection (all long-running conditions reach ATK=13, DEF=8) but HP preservation for the boss fight.
With DEF=8, the boss deals $\max(0, 20-8) \times 50 = 600$ HP of damage, so the hero must arrive at the boss with at least 601 HP.
The BFS-optimal path arrives with HP=613 by killing only 12 of 13 non-boss enemies, skipping 2 expensive enemies that are not on the critical path.
Every bare-seed condition killed all 13 non-boss enemies, took the extra damage and arrived at the boss with HP=437–442, below the 601 threshold.
The stat problem was solved; the resource-conservation problem was not.

**2. The scores fell into two clusters: boss avoidance (0.37) and boss attempted (0.64–0.72).**

Conditions in which the agent recognised the boss as unwinnable (HP < 601) and stopped (heuristic, 397B reactive, 397B oneshot, llama-8b MS-3, llama-8b oneshot) all scored about 0.371 (boss\_not\_killed violation and the 0.5× multiplier).
Conditions in which the agent attempted the boss at ATK=12 and died (397B MS-3 and MS-5, llama-8b MS-5) scored 0.64–0.72, without the multiplier.
The scorer therefore ranked attempted-and-failed above avoided, giving partial credit for goal-seeking behaviour without completion; this inversion is one reason why the composite was replaced (D.3.1).

**3. The multistep modes of Qwen3.5-397B were overconfident about the boss fight.**

The reactive mode of Qwen3.5-397B recognised the boss fight as unwinnable and stopped (HP=442 < 601).
In MS-3, however, it put the boss into a 3-action chunk (T26, ATK=12, DEF=5), and in MS-5 at T24 (ATK=12, DEF=5).
At ATK=12, the hero deals $\max(0, 12-12) = 0$ damage per turn, so the fight cannot be won at any HP.
The 3- and 5-action windows let the model schedule the boss as an objective without checking that ATK must reach 13 to deal any damage.
Per-turn reactive reasoning was safer here: the evaluator rejected the boss fight as unwinnable at each turn, while chunk planning queued it without checking the ATK prerequisite.

**4. Llama-3.1-8B multistep-5 scored highest (0.720) by reaching the boss better prepared.**

The llama-8b MS-5 run survived to turn 32 before fighting the boss (ATK=12, DEF=7, HP=467 entering the fight).
Compared with 397B MS-5 (T25, ATK=12, DEF=5), it killed more enemies (12/14 against 10/14) and had better stats before the suicide.
Its 5-action chunks deferred the boss fight longer and collected more resources before the inevitable suicide attempt; the scores (0.720 against 0.643) reflect completion, not boss success.

**5. Llama-3.1-8B multistep-3 avoided the boss entirely (0.372), unlike Qwen3.5-397B multistep-3 (0.672).**

397B MS-3 attempted the boss fight; llama-8b MS-3 never did, running 36 turns, killing 13/14 enemies and ending with HP=389 and boss\_not\_killed.
Both used the same chunk size.
In 3-action planning, the larger model scheduled the boss explicitly, while llama-8b MS-3 kept selecting local non-boss actions across 11 chunk calls; the record attributed this to model capability.

**6. Oneshot was the heuristic for both models.**

llama-8b oneshot scored 0.371 with 29/36 heuristic fallbacks (invalid plan coordinates), and 397B oneshot 0.371 with 32/36.
The heuristic resolved almost all turns in both cases, so the one-shot result reflects the heuristic's own boss avoidance (HP=437 < 601), not a contribution of the model.

##### D.1.17 E21/E22: GEPA on the Simple Benchmark Floor, Corrected Experiments

**Goal:** establish whether GEPA can find the HP reservation strategy required to kill the boss on the simple floor.
After the three-bug scorer error was fixed (D.1.16), all bare-seed conditions scored about 0.371, with the boss never killed.
E21 ran GEPA with the bare seed (Qwen3.5-397B, headroom 0.629).
E22 ran GEPA with a seed derived from a manual run, which explicitly encodes the HP reservation strategy of a human expert playthrough (score about 0.865); it provided a stronger starting point and tested whether GEPA can refine a near-human prompt.

**Manual run analysis.** A human expert playthrough of the simple floor (37 turns, HP=6 after the boss kill) was analysed to identify the winning strategy (Table D.39).

**Table D.39:** E21/E22: the manual playthrough against the bare-seed agent of E19 on the simple floor.

| Metric | Manual (human) | AI bare seed (E19) | Difference |
|--------|---------------|---------------------|-----------|
| Final HP | 6 (boss killed!) | 437–442 (boss not killed) | HP over-spending |
| Boss fought? | Yes | No | ✗ |
| Score | 0.865 | 0.371 | +0.494 |
| Blue Potion (10,2) collected at | T29 (HP=406→606) | T16 (HP=433→633) | 13 turns earlier (AI) |
| Top-right potions saved as buffer | Yes | No | Critical gap |

The decisive difference: the human player deferred the top-right corridor potions (+275 HP at (10,2) and (9,2)) until T29–T30, immediately before the boss chain.
The agent collected them greedily at T16, then spent that HP fighting the remaining enemies and arrived at the boss with only HP=442 (against the human's HP=594).
The playthrough also shows the boss chain: free kill of Enemy #201@(9,0) → collect the top-right potions → fight Enemy #205@(3,5) → collect the items behind it → fight Enemy #205@(5,9) → boss.

**Manual run, full action trace** (Table D.40):

**Table D.40:** E21/E22: action trace of the manual playthrough of the simple floor.

| Turn | Action | HP | ATK | DEF |
|------|--------|----|-----|-----|
| T2 | Fight #203@(6,4) dmg=55 | 415 | 9 | 4 |
| T3 | Fight #201@(5,6) dmg=24 | 391 | 9 | 4 |
| T4 | Open door (4,7) | 391 | 9 | 4 |
| T5 | Fight #203@(3,7) dmg=55 | 336 | 9 | 4 |
| T6–T9 | Collect Yellow Key, Blue Gem, Yellow Key | 336 | 9 | 5 |
| T10 | Open door (7,5), right side corridor | 336 | 9 | 5 |
| T11–T13 | Red Potion +75, Fight #203@(9,5) dmg=55, Blue Gem +DEF | 356 | 9 | 6 |
| T14–T17 | Red Potion +75, Fight #204@(1,9) dmg=76, Blue Potion +200, Blue Gem +DEF | 555 | 9 | 7 |
| T18–T21 | Fight #202@(10,7), Fight #204@(9,9), Blue Gem +DEF, Red Gem +ATK | 466 | 10 | 8 |
| T22–T25 | Fight #204@(4,2), Fight #204@(2,1), Yellow Key, Red Gem +ATK | 406 | 11 | 8 |
| T26–T28 | Open (7,0), Open (8,0), Fight #201@(9,0) dmg=0 (FREE) | 406 | 11 | 8 |
| **T29–T31** | **Blue Potion +200, Red Potion +75, Red Gem +ATK** (boss preparation) | **681** | 12 | 8 |
| T32 | Fight #205@(3,5) dmg=81 | 600 | 12 | 8 |
| T33–T35 | Yellow Key, Red Gem +ATK, Red Potion +75 | 675 | 13 | 8 |
| T36 | Fight #205@(5,9) dmg=81, boss gate | 594 | 13 | 8 |
| **T37** | **Fight Boss #299 dmg=588** | **6** | 13 | 8 |

**E22 seed prompt.** The seed prompt `manual_aligned.txt` encoded (1) the boss fight damage (588 HP at ATK=13, DEF=8), (2) the HP reservation rule (do not collect the top-right potions until stat collection is complete), (3) the mandatory boss chain, and (4) the minimum HP before each gate fight.

**Configuration:**
- **E21:** bare seed (`bare.txt`), Qwen3.5-397B thinking, simple floor
- **E22:** manual-aligned seed (`manual_aligned.txt`), Qwen3.5-397B thinking, simple floor
- **Reflection model:** `qwen3.5-397b-a17b`
- **Early stop:** 0.99

###### D.1.17.1 Results

**Table D.41:** E21/E22: GEPA on the simple floor from the bare and the manual-aligned seed.

| Experiment | Seed prompt | Seed score | Best score | Change | GEPA reflections | Failure mode |
|-----------|------------|-----------|-----------|--------|-----------------|-------------|
| E21 | `bare.txt` | 0.371 | **0.371** | 0 | 3 | Reflection hallucinated shop mechanics (no shop on simple floor) |
| E22 | `manual_aligned.txt` | **0.735** | **0.370** | −0.365 | 2 | Reflection again hallucinated shops; evolved prompt scored worse than seed |

**E21 outcome.** The reactive Qwen3.5-397B agent with the bare seed scored 0.371 (boss not killed).
All three reflections proposed changes that invoke shop purchases (e.g. "buy DEF upgrades before boss chain"), although the simple floor has no shop.
The evolved prompt inherited these invalid shop references and scored the same as the seed.

**E22 outcome.** The manual-aligned seed (explicit HP reservation, boss chain and correct fight costs) scored 0.735 at baseline: the agent reached DEF=8 and attempted the boss but died from an HP margin error.
After two reflections, the evolved prompt again hallucinated shop mechanics and scored 0.370, below the seed.
The headroom of 0.265 from seed to ceiling was consumed by false improvement signals.

###### D.1.17.2 Headroom Analysis

**Table D.42:** E17, E18, E21 and E22: seed score, headroom and the hypothesis tested.

| Experiment | Seed prompt | Expected seed score | Headroom | GEPA hypothesis |
|-----------|------------|--------------------|---------:|-----------------|
| E21 | `bare.txt` | ~0.371 | ~0.629 | GEPA must find HP reservation rule from scratch |
| **E22** | `manual_aligned.txt` | ~0.6–0.9 | ~0.1–0.4 | GEPA refines explicit HP reservation rule |
| E18 (false positive) | `bare.txt` | 0.5437 | — | FALSE POSITIVE, excluded from headroom analysis |
| E17 | `mt3_bare` | 0.846 | 0.15 | Confirmed: low headroom → small gain (+11%) |

###### D.1.17.3 Analysis

**Reflection hallucination, not task difficulty, blocked GEPA.** In both E21 and E22, the reflection model (Qwen3.5-397B) proposed edits that referenced shop mechanics absent from the simple floor.
On MT3 (E16), GEPA had found the boss-avoidance rule in a single reflection and gained 0.55.
On the simple floor, the same reflection model generated suggestions that could not be executed (buying DEF upgrades).
The reflection model must identify the correct failure mode from the score and the game log; when it hallucinates mechanics that the environment lacks, the headroom cannot be used, however large it is.

**The E22 seed was both the best and the worst outcome.** The manual-aligned seed scored 0.735, the highest baseline of any prompt tested on the simple floor at the time.
GEPA regressed it to 0.370, below the bare seed.
The record explained this as false attribution: the higher seed score signalled to the reflection model that the hallucinated "shop strategy" was related to the observed improvement.
E22 thus isolated reflection-model hallucination as the binding constraint.

**The headroom pattern still held where the reflection model was not misled.** Comparing E16 (MT3, headroom 0.55, high gain), E17 (MT4, headroom 0.15, low gain) and E21 (simple, headroom 0.629, zero gain), the simple floor was the anomaly: high headroom and zero gain, caused by hallucination.
The headroom pattern of D.1.14.4 held for environments in which the reflection model identified the failure mode correctly.

**Consequence for E23/E24.** Because GEPA did not improve the simple-floor agent reliably, E23 and E24 switched to seed engineering, writing the boss chain directly into the prompt without GEPA.

##### D.1.18 E23: Seed Rewrite (DEF-First Framing) and Formatter Annotation

**Goal:** test whether a completely rewritten seed, with explicit DEF-first framing and no shop references, lets the Qwen3.5-397B agent execute the boss chain on the simple floor.
A new formatter annotation (`min-cost@maxStats save=Z HP`) was added to show the expected stat ceiling.

**Configuration:**
- Task model: `qwen3.5-397b-a17b` (thinking), reactive mode
- Seed: `seed_prompts/manual_aligned.txt` (rewritten: 5 sections, no shop references, DEF-first framing)
- Formatter: `mota/game/state.py` with `_compute_remaining_stat_gems()` and the `min-cost@maxStats` annotation
- Floor: `data/floors/simple.txt`

**Result: 0.3704 (boss not killed)** (Table D.43)

**Table D.43:** E23: outcome on the simple floor.

| Metric | Value |
|--------|-------|
| Score | 0.3704 |
| HP at termination | (boss not reached) |
| ATK | 13 |
| DEF | 8 |
| Steps | 36 |
| Boss killed? | No |

**Execution trace (key turns)** (Table D.44):

**Table D.44:** E23: key turns of the execution trace.

| Turn | Action | HP | ATK | DEF |
|------|--------|----|-----|-----|
| T1–T7 | Collect Blue Gems, open doors | 470→406 | 9 | 5→7 |
| T8 | Fight #204@(1,9) dmg=95 | 241 | 9 | 7 |
| T9 | Blue Potion +200 | 441 | 9 | 7 |
| T16 | Red Potion +75 | 633 | 9 | 7 |
| T17 | Red Potion +75 | 708 | 9→10 | 8 (via gems) |
| T18 | Fight #204@(4,2) dmg=-60 | 576 | 10 | 8 |
| T33 | Red Potion +75 | 659 | 12 | 8 |
| **T35** | **Fight #202@(5,3) dmg=15 (unnecessary)** | **644** | 12 | 8 |
| T36 | Fight #205@(5,9) dmg=81 | **563** | 12→13 | 8 |
| T37 | Boss #299 costs 588 HP, **unwinnable** (HP=563 < 589) | — | — | — |

**Root cause (found during analysis):** the E23 seed had been rewritten on a false premise of ATK=14.
The simple floor has only 4 Red Gems (start ATK=9, maximum ATK=13).
The seed stated a boss cost of 288 HP (actual: 588 HP at ATK=13) and a minimum HP of 367 before the chain (actual: 676 HP).
The agent executed the correct stat-building sequence (ATK=13, DEF=8) but budgeted only 367 HP instead of 676 HP before starting the boss chain.
The secondary fight (#202@(5,3), cost 15 HP) was a symptom: even without it, HP=578 < 589.

**Consequence for E24.** The seed was rewritten with verified figures: ATK=13 (maximum), boss fight cost 588 HP, chain threshold 676 HP, fight `#205@(3,5)` at ATK=12 to reach the 4th Red Gem (ATK→13), fight `#205@(5,9)` at ATK=13, then the boss.

##### D.1.19 E24: ATK=13 Corrected Seed, Final Attempt

**Goal:** re-evaluate the seed after correcting all numerical errors found in E23.
The revised `manual_aligned.txt` encoded: (1) fight `#205@(3,5)` at ATK=12 (unlocks the 4th Red Gem, ATK→13), (2) fight `#205@(5,9)` at ATK=13, (3) boss cost 588 HP, (4) at least 676 HP before the chain.

**Configuration:**
- Task model: `qwen3.5-397b-a17b` (thinking), reactive mode
- Seed: `seed_prompts/manual_aligned.txt` (ATK=13 chain, 676 HP threshold, corrected fight costs)
- Floor: `data/floors/simple.txt`
- Label: `E24-simple-397b-atk13-bosschain`

**Result: 0.3706 (boss not killed)** (Table D.45)

**Table D.45:** E24: outcome on the simple floor.

| Metric | Value |
|--------|-------|
| Score | 0.3706 |
| HP at termination | 529 |
| ATK | 13 |
| DEF | 8 |
| Steps | 36 |
| Boss killed? | No |
| Violation | `boss_not_killed` |

**Execution trace (key turns)** (Table D.46):

**Table D.46:** E24: key turns of the execution trace.

| Turn | Action | HP | ATK | DEF | Note |
|------|--------|----|-----|-----|------|
| T14 | Fight #201@(9,0) dmg=8 | 433 | 9 | — | Free kill (ATK≫DEF) |
| T16 | Blue Potion +200 | 633 | — | — | |
| T17 | Red Potion +75 | 708 | — | — | |
| T18 | Fight #204@(4,2) dmg=60 | 648 | 10 | — | |
| T19 | Fight #204@(2,1) dmg=60 | 588 | 11 | — | |
| T23 | Red Potion +75 | 663 | — | — | |
| T24 | Fight #203@(9,5) dmg=35 | 628 | — | — | |
| T26 | Red Potion +75 | 703 | 12 | 8 | HP≥676 gate ✅ |
| T27 | Fight #202@(10,7) dmg=24 | 679 | — | — | Still above gate |
| **T28** | **Fight #204@(9,9) dmg=39** | **640** | — | — | **ATK=12 enable; HP drops below 676 gate** |
| **T30** | **Fight #205@(5,9) dmg=90** (wrong order) | **550** | 12 | 7 | CoT said "collect Blue Gem" but action was this fight |
| T31 | Collect Blue Gem | — | — | 8 | |
| T32 | Fight #205@(3,5) dmg=81 | 469 | 12→13 | 8 | Should have been first |
| T33 | Collect Red Gem (ATK→13) | — | 13 | — | |
| T34 | Red Potion +75 | 544 | — | — | |
| T36 | Fight #202@(5,3) dmg=15 | 529 | — | — | |
| — | Boss #299 costs 588 HP | — | — | — | **HP=529 < 588 → unwinnable** |

**Failure mode: reasoning-action disconnect.** At turn 30, the model's reasoning read: *"I need to collect the remaining Blue Gem (+1 DEF) at (8,10) to reach DEF=8 before the mandatory #205@(3,5) fight. This is a free collection with no fight required."*
The executed action was `Fight Enemy #205 at (5,9) dmg=90 → HP=550 ATK=12 DEF=7`.
The reasoning identified the required sequence correctly (Blue Gem, then fight #205@(3,5)), but the final action contradicted it.
This differs from hallucination or wrong knowledge: knowledge and reasoning were correct, and the action selection failed.

**Why the correct order would also have failed.** Even if the agent had collected the Blue Gem before fighting #205 at turn 30, the outcome would have been fatal.
The T28 fight (#204@(9,9), −39 HP) was needed to unlock the 3rd free Red Gem (ATK→12), and it dropped HP from 679 to 640, below the 676 gate.
From HP=640 with the correct order:

$$640 - 81\;\text{(\#205@3,5)} + 75\;\text{(potion)} - 81\;\text{(\#205@5,9)} - 588\;\text{(boss)} = -35$$

From HP=640, death was certain.
The seed's boss-chain rule ("HP≥676 before starting chain") and its rule for the ATK=12 fight ("fight #204@(9,9) to unlock 3rd gem") were mutually incompatible: meeting the ATK=12 condition violated the HP threshold.

**Secondary seed error.** The E24 seed stated that `#205@(5,9)` costs 75 HP at ATK=13, DEF=8.
The damage formula gives $\lceil 100 / (13-2) \rceil \times (17-8) = \lceil 9.09 \rceil \times 9 = 10 \times 9 = 90$ HP (not 75 HP, and not the 81 HP assumed elsewhere).
This error did not affect the 676-HP threshold, which had been derived independently from the manual playthrough.

###### D.1.19.1 The E21–E24 Arc: A Failure Mode Taxonomy

Four successive experiments targeted the same boss kill on the same floor, and all ended with the same `boss_not_killed` score of about 0.371 (Table D.47).

**Table D.47:** E21–E24: approach, score and root cause.

| Experiment | Approach | Score | Root Cause |
|-----------|---------|-------|-----------|
| E21 | GEPA, bare seed, 397B | 0.371 | Reflection hallucinated shops (none on floor) |
| E22 | GEPA, manual-aligned seed, 397B | 0.370 evolved | Reflection again hallucinated shops; GEPA regressed seed |
| E23 | Seed rewrite (DEF-first), no GEPA | 0.3704 | False ATK=14 premise; wrong boss cost and threshold |
| **E24** | **Corrected seed, no GEPA** | **0.3706** | **Reasoning-action disconnect; HP gate violated by ATK=12 fight** |

The failure modes span four distinct categories: (1) **reflection hallucination**, in which the optimiser introduces mechanics that do not exist; (2) **adversarial regression**, in which an optimiser that cannot tell the original content from its own hallucinations regresses a correct seed; (3) **numeric premise error**, in which the prompt encodes wrong game constants; and (4) **reasoning-action disconnect**, in which the model's reasoning identifies the required sequence but the final action contradicts it.

Category 4 matters most for the hybrid design.
Categories 1 to 3 can be addressed by correcting the prompt; category 4 is a failure of output faithfulness, in which the model knows the right answer but does not execute it.
Prompt engineering alone cannot remove it, which motivated the design of Architecture A, where a deterministic engine validates and constrains action execution against the current game state whatever the model's reasoning produces.

**Reading.** The E21–E24 arc showed that, for constrained multi-step sequential planning (fight A at stat X, fight B at stat Y, fight the boss with HP ≥ Z), Qwen3.5-397B with thinking and an expert-engineered prompt did not execute the plan correctly in these episodes.
The limit was not model scale, not reasoning depth (thinking mode with explicit chain-of-thought) and not prompt quality (manually verified domain knowledge).
The bottleneck identified at the time was the step from reasoning to action selection, which the hybrid agent addresses through deterministic pathfinding and action enumeration (Sections 5.1 and 5.3).
The simple floor was later won 10/10 without any strategic override after engine changes to the annotations (Section 6.4.4, Table 6.5).

#### D.2 Prompt-Engineering Case Study: From Minimal Seed to the Solver-Route Prompt

This section analyses the prompt evolution that led to the first complex-floor boss kills with the solver-route prompt.
It covers (1) the lineage of the prompt versions and the insight each contributed to later ones; (2) the lookahead annotation system of the development phase, which became both an enabler and an obstacle; (3) the reasoning of three representative runs under different prompt and annotation configurations; and (4) annotation interference, in which engine-generated annotations overrode explicit strategy instructions, together with the fix applied at the time.
The solver-route prompt lists the route of the published solver, which is not optimal: it ends at 22 HP against the exact optimum of 68 HP (Section 4.6); the development record called it "BFS-compiled".
Scores are composite scores (D.3.1) of single episodes.

##### D.2.1 Prompt Version Lineage

Table I.1 (Appendix I) lists the system prompts of the study with their character counts and roles; the prompt files are in `seed_prompts/` of the repository.
Three layers must be kept apart: the system prompt, the engine-generated floor map appended to it at the start of a run, and the engine-generated per-turn observation; only the first is a prompt version (Appendix I).
Monster names in all three layers are the English translations of the `enemys.js` names (Appendix G); the `enemys.js` id (e.g. `redBat`) is the stable reference.
The narrative below numbers the prompts as follows:

- v0: the selector prompt of the JavaScript prototype (Section 5.5.3), seven rules with the answer format `ACTION:`/`REASON:`, with which the instruction-tuned Qwen3-30B (`qwen3-30b-a3b-instruct`) played the floors MT0 to MT3 or MT4 at under one second per decision;
- v1 `minimal.txt`, v2 `bare.txt` and v3 `format_aware_bare.txt`: the minimal, bare and format-aware seeds;
- v4 `imperative_lookahead.txt`: the imperative lookahead prompt;
- v5 `e3_best_prompt.txt`: the evolved MT3 prompt of E3 (D.1.3);
- v6 `mt3_bare.txt`: compact game mechanics for multi-floor scenarios;
- v7 `manual_aligned.txt`: the hand-compiled boss prompt (D.1.17 to D.1.19);
- v8 `target_boss_seed.txt`: the shop seed (`seed_prompt.SEED_PROMPT`); its variant without shops (`SEED_PROMPT_NOSHOP`, no file) produced the stored simple-floor wins of the development phase;
- v9 `simple_basic_strict.txt`: the strict-format prompt;
- v10 `complex_aware.txt`: the complex-aware prompt;
- v11 `complex_bfs_strategy.txt`: the solver-route prompt without survival rule;
- v12 `complex_bfs_strategy_mechanical.txt`: v11 with an instruction to execute it mechanically (0 of 5 with Qwen3.6-35B, all lethal boss attempts);
- v13 `complex_bfs_strategy_survival.txt`: v11 with the survival rule, the solver-route prompt of Chapter 6 (4 of 5 against 0 of 10 for v11 with Qwen3.6-35B);
- v14 `tower_seed.txt`: the walkthrough tower prompt (D.4.1);
- v15 `complex_exact68_sequence.txt`: the exact-route prompt (Section 6.6).

###### D.2.1.1 Evolution Narrative

The prompt evolution was not monotonic: several prompts were designed for different floors or architectural configurations, and insights from one branch were carried forward selectively.
Four lineages matter.

**Lineage A: annotation interpretation** (v1→v3→v4→v5). The initial `minimal.txt` did not mention the engine's annotation format. When the engine began computing lookahead values and via-chain trees, the model could not interpret them. `format_aware_bare.txt` (v3) was the first to document the annotation schema, teaching the model that `lookahead=N` represents future item value and that `effCost = damage - lookahead` is the true cost metric. `imperative_lookahead.txt` (v4) hardened this into rules: "NEVER fight an enemy with lookahead=0 when another has lookahead>0". The GEPA-evolved `e3_best_prompt.txt` (v5) refined these rules through automated prompt optimisation and added compound interactions such as "shop DEF upgrades reduce surplus cost — count it as HP gained".

**Lineage B: boss arithmetic** (v2→v7→v10→v11). `bare.txt` (v2) introduced the boss-goal objective but contained no fight-ordering logic. `manual_aligned.txt` (v7) was a hand-crafted prompt with exact arithmetic for the simple-floor boss (ATK=13, 675 HP chain cost, mandatory 3-step sequence); the record took it as evidence that models can follow compiled arithmetic when it is presented imperatively, and E22 to E24 (D.1.17 to D.1.19) show the limits of that reading. `complex_aware.txt` (v10) adapted the boss goal to the complex floor, with `magic-atk` avoidance rules and an HP reserve threshold. `complex_bfs_strategy.txt` (v11) transcribed the published solver's route (22 HP, not the exact optimum of 68 HP) into a position-based allowlist with 6 phases, and v13 added the survival rule.

**Lineage C: format control** (v6→v9). For multi-floor evaluation, `mt3_bare.txt` (v6) provided compact game mechanics. `simple_basic_strict.txt` (v9) showed that format compliance (`FINAL_CHOICE:` prefix, no markdown preamble) was a necessary condition for the evaluator to parse the model's output correctly.

**Lineage D: GEPA optimisation** (v1→v5, carried forward). The GEPA prompt optimiser, the predecessor of the loops of Section 5.7, took `minimal.txt` as its seed and evolved it into `e3_best_prompt.txt` over 3 reflection iterations, with a score improvement from 0.3997 to 0.9833 (+146 %). The four mutations it found were: (1) "buy DEF immediately if gold is available", (2) "collect all new items immediately after opening a door (STEP 1)", (3) "if a door is marked DEAD END, skip it entirely", (4) the HP safety threshold changed from `<15%` to `<20%`. These four rules were carried into several later prompts. The gain was measured on single episodes; Section 6.5 finds no gain beyond the noise floor under the full observation (Table D.1).

###### D.2.1.2 Size and Complexity Growth

The prompts grew in three phases (character counts in Table I.1): GEPA-driven expansion (v5, about 4.5 K characters), the solver-route specification (v11 and v13, about 4.9 K to 5.5 K characters), and the walkthrough distillation for the tower (v14, about 8.5 K characters).
The hand-compiled boss prompt (v7, about 5.8 K characters) is the peak of human-authored single-floor complexity.
v11 reached a similar size by transcribing the published solver's trace rather than by manual reasoning, and v13 shows that one additional survival rule, not more compiled detail, was the decisive change.

##### D.2.2 The Lookahead Annotation System

The development engine annotated each available action with computed heuristic values before presenting it to the model.
This section documents the computation, the value formulas and the depth discount as they stood during the development phase; Section 5.2.2 defines the lookahead tree, lookahead value and effective cost used in Chapter 6.

###### D.2.2.1 Architecture

The annotation pipeline consists of three components:

1. **BFS reachability** (`pathfinder.find_reachable()`): given the current map grid, hero position, key inventory and the set of removed (defeated or collected) entities, a breadth-first search finds all accessible positions. Enemies and locked doors are impassable; keys in the inventory open matching doors.

2. **Depth-N frontier explorer** (`state._compute_unlocks()`): for each fight or door action, the engine simulates removing that entity and re-runs the reachability search to find newly accessible items, doors, enemies, shops and stairs. It recurses to a configurable depth by also simulating the removal of newly discovered gateway enemies and the opening of newly accessible doors. The result is a tree of via-chains: "fighting enemy A unlocks item X; via enemy B (behind A), unlock item Y".

3. **Tree renderer** (`state._format_unlocks_tree()`): converts the tree into indented text that the model can parse.

###### D.2.2.2 Value Formula

Each unlocked entity is valued by `_score_unlock()` with the weights of Table D.48.

**Table D.48:** Development-phase value of each unlocked entity (`_score_unlock()`).

| Entity Type | Value Formula | Rationale |
|-------------|---------------|-----------|
| DEF gem (+1) | 90 HP-equivalent | Each DEF point reduces every future fight's per-round cost by 1; compound value across all remaining fights |
| ATK gem (+1) | 70 HP-equivalent | Each ATK point reduces fight turns by increasing per-round damage; slightly lower compound value than DEF |
| MDEF gem (+N) | N × 45 HP-equivalent | Magic DEF subtracts from all fight final damage; partially compounds |
| HP potion | Face value | Direct HP restoration; no compounding |
| Yellow key | 60 HP-equivalent | Common; unlocks one yellow door |
| Blue key | 90 HP-equivalent | Rare; unlocks higher-value areas |
| Red key | 120 HP-equivalent | Extremely rare; gates critical content |
| Shop NPC | Sum of stat changes across all shop choices | Shops sell permanent stat upgrades; value computed from upgrade magnitudes |
| Stairs | 120 HP-equivalent | Floor transition; enables progress |
| Gold (N coins) | N / 5 HP-equivalent | Low direct value; enables shop purchases |
| Other (score-based) | score × 4 | Fallback for special items |

###### D.2.2.3 Depth Discounting

Items behind several gateway enemies are discounted by depth (Table D.49).

**Table D.49:** Depth discount of unlocked items.

| Depth | Scale Factor | Meaning |
|-------|-------------|---------|
| 0 | 1.00 | Directly accessible after this action |
| 1 | 0.70 | Behind one additional gateway |
| 2 | 0.50 | Behind two additional gateways |
| 3+ | 0.35 | Behind three or more gateways |

###### D.2.2.4 Net Lookahead and Effective Cost

The net lookahead value is computed as:

$$\text{lookahead} = \max\left(0,\; \sum_{\text{reward unlocks}} v_i \cdot s_{\text{depth}(i)} \;-\; \sum_{\text{unique gateways}} \text{damage}_j\right)$$

where $v_i$ is the item value, $s_d$ the depth scale factor and $\text{damage}_j$ the combat damage of each unique gateway enemy in the via-chains.
Gateway costs are deduplicated: if two items share the same gateway enemy, its damage is counted once.

The effective cost is then:

$$\text{effCost} = \text{fight\_damage} - \text{lookahead}$$

A negative effCost indicates that the fight "pays for itself": the unlocked items are worth more than the HP spent.

###### D.2.2.5 Risk Labels

Each fight received a categorical label based on its damage as a percentage of current hero HP (Table D.50).

**Table D.50:** Development-phase risk labels of fights.

| Label | Condition |
|-------|-----------|
| `[SAFE]` | damage% ≤ 15% |
| `[MODERATE]` | 15% < damage% ≤ 30% |
| `[RISKY]` | damage% > 30% |
| `[LETHAL]` | Cannot win (heroATK ≤ monDEF) |

The current `[LETHAL]` tag also marks fights that the hero can win but not survive (Section 5.2.1).

###### D.2.2.6 Min-Cost at Maximum Stats

For enemies without magic attack, the engine also computed the fight cost if the hero first collected all remaining DEF and ATK gems on the floor:

$$\text{min-cost} = \text{damage}(\text{hero}_{\text{maxStats}}, \text{monster})$$
$$\text{save} = \text{damage}_{\text{current}} - \text{min-cost}$$

This is rendered as `min-cost=Y@maxStats(ATK=X,DEF=Z) save=W HP — collect stat gems first`, signalling that deferring the fight until after the stat gems saves W HP.

##### D.2.3 Chain-of-Thought Analysis

This section analyses the reasoning of three complex-floor evaluations with the solver-route prompt without survival rule (`complex_bfs_strategy.txt`, v11 in the numbering of D.2.1; the development record calls this text revision "v7").
All three use the same prompt text; they differ in annotation suppression and temperature, and the second also in the model.

###### D.2.3.1 Successful Run: Boss Killed at 17 HP (Composite 0.898)

**Configuration:** Qwen3.5-35B (`qwen3.5-35b-a3b`, thinking mode, since removed from the service), temperature 0.6, `MOTA_DISABLE_OVERRIDES=1` (annotations suppressed).

**Run summary:** 52 turns, 0 violations, final stats ATK=14 DEF=17 MDEF=20. Boss killed at Turn 52 with HP=429−412=17 remaining.

####### Turn 3: Opening Decision (Structural Reasoning)

At Turn 3, the model faces 10 available actions, including forbidden fights, the boss-gate door and the correct Phase 1 door. The reasoning (11,000+ characters) shows:

1. **Inventory tracking**: "I have 1 Yellow Key now… There are 3 Yellow Keys on map total… (7,8), (12,10), (0,0)."
2. **Key allocation planning**: "Yellow Door at (8,7) — FIRST (use starting yellow key)… Door at (8,4) — SECOND (use key from (12,10))… Door at (5,8) — FIFTH (use key from (0,0))."
3. **Phase-sequence reasoning**: "Phase 1 requires fighting Green Slime@(8,12) and Black Slime@(12,9)… The Door Sequence Step 1 is: Open Yellow Door at (8,7)."
4. **Constraint resolution**: the model considers both the door sequence and the phase sequence, determines that opening the door is compatible with Phase 1, and correctly selects action 3 (open Yellow Door at (8,7)).

This pattern of cross-referencing several constraint systems (phase gates, door sequences, key economy) is characteristic of the successful run.
The model treats the prompt's constraints as a constraint-satisfaction problem rather than as a simple priority ranking.

####### Turn 42: Phase 5 Gate Check (ATK Threshold Verification)

At Turn 42, 10 actions are available, and only one (Green Slime at (6,4)) is in the allowlist. The reasoning shows systematic allowlist verification:

1. **Full allowlist scan**: the model enumerates all 14 allowlist positions and marks each as "Done" or "Pending".
2. **Elimination of forbidden options**: each of the 9 non-allowlist actions is checked against the FORBIDDEN list and rejected.
3. **ATK gate verification**: "Phase 5 (ONLY after ATK≥14 AND DEF≥16!)… My stats: ATK=14, DEF=17. So the cost is indeed 3 HP (as listed in the action details: damage=3)."
4. **Correct selection**: FINAL_CHOICE: 6 (Green Slime at (6,4), costing 3 HP).

At ATK=14, this fight costs 3 HP; at ATK=13 (as in the partial-success run), it costs 44 HP, about 15 times as much.
The ATK gate check preserved 41 HP, which was the margin between surviving with 17 HP and dying.

The reasoning at this turn is constraint-satisfaction reasoning: instead of evaluating each action individually, the model first eliminates all forbidden options by reference to the allowlist ("Black Slime (0,4) — FORBIDDEN. Not in allowlist."), then checks the remaining candidate against the phase gates ("Phase 5 (ONLY after ATK≥14 AND DEF≥16!)…").
Only after both constraint layers are satisfied does it proceed with the action.

####### Turn 52: Boss Fight (Terminal Decision)

The model faces 9 actions at Turn 52, and only the Boss is in the allowlist for Phase 6. The reasoning:

1. **Phase completion check**: "Phase 6: 6a. Open Yellow Door@(5,8) ✓ (done T46), 6b. Fight Green Slime@(3,8) ✓ (done T47), 6c. Fight Boss@(6,0) — FINAL."
2. **HP survival calculation**: "HP 429 − 412 = 17 HP. This is enough to win."
3. **Alternative rejection**: the model considers whether fighting other enemies to collect potions could increase HP, but determines: "Fighting Slime Lords is FORBIDDEN… Fighting Red Bat (4,11) is FORBIDDEN… The Allowlist explicitly lists Boss as the last fight."
4. **Risk acceptance**: "Winning with 17 HP is better than dying trying to get more items."

The model computed correctly that following the allowlist maximised its expected value even at a tight margin.

###### D.2.3.2 Failed Run: Death at a Big Bat (Composite 0.318, Before the Fix)

**Configuration:** Qwen3.5-397B (`qwen3.5-397b-a17b`, thinking mode), temperature 0, annotations not suppressed (`MOTA_DISABLE_OVERRIDES` not set).

**Run summary:** 32 turns; fought several forbidden enemies; died at Big Bat@(12,12).

####### The Annotation Interference Pattern

At Turn 16, the model must choose between six actions. With annotations present, the action list includes:

- **Red Slime at (9,3)**: `[SAFE] lookahead=82 effCost=9 | save=91HP — collect stat gems first`
- **Bat at (8,2)**: `[RISKY] lookahead=47 effCost=212 | save=152HP — collect stat gems first`

The prompt's FORBIDDEN section lists the Red Slime at (9,3) explicitly: "Red Slime at (9,3) — ABSOLUTELY FORBIDDEN. This wastes 25+ HP for nothing."
The engine's annotations nevertheless present it as the best choice: low damage (10.6 %), the `[SAFE]` label, a low effCost (9) and a positive lookahead (82).
The Bat at (8,2), an allowlist Phase 2 fight, is labelled `[RISKY]` with effCost=212 and save=152HP.

The reasoning acknowledges the allowlist ("According to the ABSOLUTE ALLOWLIST and PHASE transitions") but ends by selecting the fight with the better annotations. It includes: "The Red Slime at (9,3) presents an interesting tactical opportunity. With minimal HP cost and potential stat gains, it could provide a strategic advantage."

The record named this pattern *annotation interference*: when heuristic annotations designed for generic prompts contradict an explicit strategy, their quantitative specificity (`effCost=9` against `effCost=212`) overrides the strategy's qualitative constraint ("ABSOLUTELY FORBIDDEN").
The model appears to treat the annotations as more authoritative than the prose instructions because they are numerically precise and computed by the engine.

####### Cascade of Phase Violations

The annotation interference at Turn 16 triggered a cascade (Table D.51).

**Table D.51:** Failed run: forbidden fights from turn 16 on and the annotations that accompanied them.

| Turn | Action | Status | Annotation Bait |
|------|--------|--------|-----------------|
| 16 | Red Slime (9,3) | FORBIDDEN | `[SAFE] effCost=9` |
| 18 | Bat (11,4) | FORBIDDEN | `effCost=259` (high, but adjacent) |
| 27 | Green Slime (10,6) | FORBIDDEN | `[SAFE]` |
| 28 | Slime Lord (10,10) | FORBIDDEN | `lookahead=200` |
| 32 | Big Bat (12,12) | Death | Out-of-phase, insufficient stats |

By Turn 28, the model had spent 581 HP on forbidden fights, leaving too little HP for the boss chain.
The Slime Lord at (10,10), a magic-attack enemy, cost 230 HP that no stat gain could recover.

###### D.2.3.3 Partial Success: Death at the Boss (Composite 0.701, After the Fix)

**Configuration:** Qwen3.5-35B (`qwen3.5-35b-a3b`, thinking mode), temperature 0.6, `MOTA_DISABLE_OVERRIDES=1` (annotations suppressed).

**Run summary:** same prompt and model as the successful run, different random seed (stochastic sampling). Reached the boss but died with HP=−142.

####### The Cost Cliff at ATK=13

At the critical Phase 5 decision (Turn 24), the model had HP=225, ATK=13, DEF=14. The reasoning (31,186 characters, the longest single reasoning chain of the experiment) sets out a multi-layered dilemma.

**Layer 1, ATK gate awareness**: the model identifies the cost cliff correctly:

> "Phase 5 includes Green Slimes at (6,4), (6,6). I have ATK 13. Phase 5 requires ATK ≥ 14 for Green Slimes. The allowlist says: 'costs 3 HP at ATK≥14; costs 44 HP at ATK=13'."

**Layer 2, path planning**: it then computes a path to the ATK gem:

> "There is an ATK+1 gem at (1,1). I am at (1,5). So going to (1,1) → (6,4) is on the way."

**Layer 3, phase conflict recognition**: the model acknowledges the rule violation:

> "Phase 4 is earlier than Phase 5. If I skip Phase 4, I fail this rule. However, if I fight (0,2) I die."

**Layer 4, HP budget calculation**: detailed arithmetic follows:

> "Big Bat at (0,2) costs 180 HP. Current HP = 225 → 45 remaining. If I fight Green Slime first: 225 − 44 = 181 HP. Then Big Bat: 181 − 180 = 1 HP. Survival margin: negative."

**Layer 5, auto-collection assumption**: the model assumes that the ATK gem will be collected on the way:

> "If I go (1,5) → (1,1) → (6,4), I pick up ATK gem. Then ATK=14. Then (6,4) costs 3 HP."

This assumption was wrong: the engine's action system does not collect items along the path. The fight action `Green Slime at (6,4)` is computed at the hero's current stats (ATK=13, damage=44), not at projected stats after a collection.

**Layer 6, decision**: although it has identified the phase violation, the model selects the Green Slime:

> "Option 6 is better than Option 1 (directly). (6,4) is closer. And (6,4) enables ATK upgrade (on the way). Conclusion: Option 6."

The 31,186-character reasoning shows a model that identifies all relevant constraints, computes correct arithmetic and understands the cost implications, but in the end prioritises immediate HP safety over global phase compliance.
The phase violation cost 41 HP (44 − 3), which cascaded into a deficit of 142 HP at the boss fight.

####### Comparison: Same Prompt, Same Model, Different Outcome

**Table D.52:** Successful and partial run with the same prompt, model and temperature.

| Metric | Successful (0.898) | Partial (0.701) |
|--------|-------------------|-----------------|
| Temperature | 0.6 | 0.6 |
| ATK at Phase 5 | 14 (gate satisfied) | 13 (gate violated) |
| Green Slime (6,4) cost | 3 HP | 44 HP |
| HP at boss | 429 | 270 |
| Boss outcome | Killed (17 HP left) | Died (−142 HP) |
| Root cause | Phase order respected | Phase order violated |

The difference between success and failure was one decision at Phase 5: whether to respect the ATK ≥ 14 gate or to optimise locally.
At temperature 0.6, sampling occasionally selects the suboptimal token at this branch point.
The margin is narrow: 41 HP of waste separates `boss_killed` from `suicide_fight`.

##### D.2.4 Annotation Interference: Discovery and the Fix of the Time

###### D.2.4.1 Definition

*Annotation interference* occurs when engine-generated action annotations, designed as decision support for generic prompts, override the constraints of an explicit strategy prompt.
The annotations are numerically precise and computed by the engine; the strategy constraints are natural-language rules.
When the two conflicted, the model in these runs followed the numerical annotations.

###### D.2.4.2 Mechanism

The engine's `format_actions()` method annotated each fight action with:

1. **Risk label**: `[SAFE]`, `[MODERATE]`, `[RISKY]`, `[LETHAL]`, based on the damage percentage
2. **Lookahead value**: `lookahead=N`, the HP-equivalent value of the items unlocked
3. **Effective cost**: `effCost=N`, damage minus lookahead
4. **Deferral hint**: `save=X HP — collect stat gems first`, the saving from deferral
5. **Unlock tree**: indented `→ unlocks:` / `→ via [...]` lines showing causal chains

For a generic prompt (e.g., `e3_best_prompt.txt`), these annotations are essential: they encode the engine's spatial reasoning (lookahead over the reachability search) that the model cannot perform, and the model relies on `effCost` comparisons to make approximately optimal fight-ordering decisions.

For an explicit strategy prompt (e.g., `complex_bfs_strategy.txt`), the record judged them harmful: the strategy already specifies which enemies to fight, taken from the published solver's route, and the annotations re-introduce the engine's independent ranking, which may disagree with that route.

###### D.2.4.3 The Specific Interference

On the complex floor, the Red Slime at (9,3) is FORBIDDEN in the solver-route allowlist. The engine nevertheless annotated it as:

```
[SAFE] lookahead=82 effCost=9
```

The Bat at (8,2), an allowlist Phase 2 fight, was annotated:

```
[RISKY] effCost=212 | save=152HP — collect stat gems first
```

From the annotations alone, the Red Slime appears 23 times more efficient than the Bat.
The `[SAFE]` label adds reassurance, and the `save=152HP` hint on the Bat tells the model not to fight it yet.

At temperature 0, the model selected the Red Slime over the Bat in all 6 consecutive runs, with two models (Qwen3.5-35B and Qwen3.5-397B), each producing the same forbidden-fight trace.

###### D.2.4.4 The Fix of the Time

The fix had two components.

**1. Engine-side suppression**: the environment variable `MOTA_DISABLE_OVERRIDES=1` gated the annotation sections in `format_actions()`. When it was set, `lookahead`, `effCost`, `min-cost/save` and the unlock trees were suppressed, and the action line kept only the fight name, position, stats, damage and HP after the fight: factual information without engine judgement.

**2. Prompt-side override**: the `CRITICAL OVERRIDE` paragraph was added to the solver-route prompt:

> "The action list will show [SAFE], lookahead values, and effCost for ALL enemies — IGNORE these labels for enemies NOT in the allowlist below. A fight can be [SAFE] with high lookahead and STILL be FORBIDDEN because it wastes HP needed for the boss."

The record gave two reasons for using both:
- Engine suppression alone would remove annotations that the model might need in cases the allowlist does not cover.
- The prompt override alone was insufficient at temperature 0, where the model attended more to the quantitative annotations than to prose overrides.

The combination achieved the boss kill (score 0.898) on the first evaluation after deployment, a single episode; D.2.5 shows the variation at the same setting.

The engine-side suppression later turned out to be a defect: switching the overrides off also hid the annotations of fight actions while door actions kept theirs, so results with overrides off were obtained with less information than reported (Appendix H, incident 8).
Overrides and annotations have been separate settings since, and the final configuration shows all annotations.

###### D.2.4.5 Implications Drawn at the Time

The record drew three implications for hybrid deterministic-neural architectures:

1. **Heuristic annotations help weak models**: for small models or generic prompts, lookahead and effective cost enable approximate planning without spatial reasoning.
2. **Heuristic annotations hurt compiled strategies**: for compiled strategies (solver-route allowlists, GEPA-optimised prompts), the annotations introduce a competing objective.
3. **Temperature**: the record suggested that at temperature 0 the model follows the most confident signal (the annotations) and that sampling at higher temperature can free it from annotation bias, at the risk of other errors. The repeated runs at 0, 0.6 and 1.0 do not show such an effect (Section 6.3, Table D.1).

It proposed *annotation authority levels*: suppressing engine annotations when the prompt encodes a compiled strategy, and showing them only when the prompt relies on the engine for spatial reasoning.
The final thesis takes the opposite route: one-sided annotations are completed rather than hidden (Section 6.4.3), and the final configuration shows all annotations with every prompt.

##### D.2.5 Temperature Sensitivity

Temperature controls the sampling diversity during token generation.
At temperature 0, the model selects the highest-probability token at each step; as temperature increases, lower-probability tokens become more likely.

###### D.2.5.1 Complex Floor Temperature Sweep

All runs use the solver-route prompt without survival rule (`complex_bfs_strategy.txt`, v11) with `MOTA_DISABLE_OVERRIDES=1` on Qwen3.5-35B (thinking mode).
Each temperature was tested once.
The reference successful run (score 0.898, boss killed, HP 17) was obtained in a separate, earlier evaluation at temperature 0.6 (Table D.53).

**Table D.53:** Complex floor, temperature sweep: one episode per temperature (Qwen3.5-35B, solver-route prompt without survival rule, annotations suppressed).

| Temperature | Score | HP | Boss Killed | Steps | Violations | ATK | DEF | Key Failure Mode |
|-------------|-------|----|-------------|-------|------------|-----|-----|------------------|
| 0.0 | 0.675 | −315 | No | 56 | 1 | 14 | 18 | Post-Phase-3 deviation: fought 5 forbidden enemies; opened wrong blue door (4,5) instead of (12,2) |
| 0.3 | 0.304 | −2 | No | 36 | 2 | 14 | 16 | Opened wrong blue door; skipped Phase 4c (Red Slime 11,0); died at Green Slime(6,6) with HP=~7 |
| 0.6 | 0.701 | −52 | No | 49 | 1 | 14 | 17 | Reached boss but insufficient HP; phase deviation |
| 0.6* | **0.898** | **17** | **Yes** | **52** | **0** | **14** | **17** | **Successful run, strict phase compliance** |
| 1.0 | 0.701 | −77 | No | 49 | 1 | 14 | 17 | Reached boss but insufficient HP; phase deviation |

\* Reference run from an earlier evaluation session.

###### D.2.5.2 Analysis

**No temperature produced a reproducible boss kill.** The reference successful run (score 0.898) was obtained at temperature 0.6 in a separate, earlier evaluation, while the sweep's run at temperature 0.6 scored 0.701, which shows high variance at this decision boundary.
The boss kill could not be obtained by setting a particular temperature; it required a favourable sequence of correct phase-order decisions at several critical junctures.

**Temperature 0 (greedy decoding)**: score 0.675, the second-best result. The model executed Phases 1–3 (T6–T23) correctly but deviated from Phase 4 on:
- T27: Big Bat@(12,12) fought out of phase (a Phase 5 enemy fought during Phase 4)
- T33: opened the Blue Door at (4,5) instead of (12,2), missing the DEF gem at (12,3)
- T41–T54: after completing Phases 5 and 6, the model "cleaned up" by fighting 5 forbidden enemies (Green Slime 10,6, Red Slime 9,3, Bat 11,4, Black Slime 0,4, Black Slime 2,9)
- Final DEF=18 (higher than in any other run, because of the extra gems), but HP exhausted to −315

In this episode, temperature 0 produced a "completionist" strategy: after the main phases, the model fought all available enemies and ignored the allowlist's FORBIDDEN designations. The extra fights cost about 318 HP.

**Temperature 0.3**: score 0.304, the worst result. The model died at Turn 36, far earlier than in the other runs:
- T30: Big Bat@(0,2) fought immediately after Big Bat@(9,1) without collecting the potions in between (Phase 4 order violated)
- T34: opened the wrong Blue Door (4,5), missing the DEF gem at (12,3), so DEF stayed at 16
- T36: died fighting Green Slime@(6,6) with HP≈7, damage=9 → HP=−2

The record read this single episode as a "worst of both worlds" zone: enough noise to leave the greedy ordering, not enough to escape the local optimum.

**Temperature 0.6 and 1.0**: both scored 0.701 with similar traces (49 steps, 1 violation). Both reached the boss and died with insufficient HP. The difference from the reference run (0.898) is stochastic: at temperature 0.6 and above, the model sometimes makes the correct Phase 5 ATK gate check (preserving 41 HP) and sometimes does not, and the reference run was the successful sample from this distribution.

###### D.2.5.3 Reading at the Time

1. **An optimal temperature range.** The record placed the optimal temperature for this task in [0.6, 1.0], from one episode per temperature: temperature 0.3 was worse than 0, and 0 worse than 0.6 and 1.0. The repeated runs do not support an optimal range: in the re-run of Table 6.2, no success rate at 0.6 or 1.0 differs from the rate at 0 by more than one episode in five (Section 6.3, Table D.1).

2. **Stochastic phase compliance.** No temperature guaranteed correct phase ordering. The boss kill requires correct decisions at about 4–5 critical junctions (Phase 4/5 boundary, ATK gate check, door selection, Big Bat timing, boss HP margin); the record estimated that at temperature 0.6 each junction has roughly a 50–70 % probability of the correct choice, for an overall success probability of about 10–25 %.

3. **A limit beyond temperature.** The record concluded that the remaining failure cannot be addressed by temperature tuning, because the model must maintain a 6-phase meta-plan across 50+ turns; it proposed either (a) a more constrained action space or (b) a multi-step planning architecture that enforces phase compliance externally. The solver-route prompt of Chapter 6 adds instead one survival rule (v13), and with it three of four models win the complex floor in 4/5, 3/5 and 4/10 episodes (Table 6.2).

##### D.2.6 Prompt Contribution Map

Table D.54 identifies which prompt version contributed each insight that the first complex-floor kills needed.

**Table D.54:** Prompt contribution map: insights carried from each version to the solver-route prompt.

| Prompt Version | Contributed Insight | Carried Forward To | Role in Boss Kill |
|----------------|--------------------|--------------------|-------------------|
| v1 `minimal.txt` | Damage formula | All subsequent | Foundation: model can calculate fight costs |
| v2 `bare.txt` | Boss-goal objective | v7, v10, v11 | Objective: model understands boss is the terminal goal |
| v3 `format_aware_bare.txt` | Annotation schema | v4, v5, v8 | Not used in v11 (annotations suppressed at the time) |
| v4 `imperative_lookahead.txt` | Hard constraint style | v7, v11 | Style: "NEVER VIOLATE" imperative language |
| v5 `e3_best_prompt.txt` | GEPA auto-discoveries | v8, v10 | Partially carried: dead-end avoidance, HP budget concept |
| v7 `manual_aligned.txt` | Mandatory defer rules | v10, v11 | Architecture: mandatory fight sequences, phase gates |
| v9 `simple_basic_strict.txt` | Format compliance | v11 | Essential: `FINAL_CHOICE:` prefix for evaluation parsing |
| v10 `complex_aware.txt` | Magic-ATK avoidance | v11 | Critical: Slime Lord avoidance (saves 480+ HP) |
| v11 `complex_bfs_strategy.txt` | Solver-route allowlist (published route) | v12, v13 | The prompt of the first complex-floor kills |
| v13 `complex_bfs_strategy_survival.txt` | Survival rule: never take a lethal action | (terminal) | The solver-route prompt of Chapter 6: 4 of 5 against 0 of 10 for v11 (Qwen3.6-35B) |

In the development record, the two decisive elements were the position-based allowlist of v11, which removed the need to judge which monsters matter, and the `CRITICAL OVERRIDE` paragraph telling the model to distrust the annotations, which came from the discovery of annotation interference in the failed runs.
In the later repeated runs, the survival rule of v13 made the difference between 0 of 10 and 4 of 5 for Qwen3.6-35B, and the annotations are shown again (D.2.4.4).

##### D.2.7 Reflection Template of the Final Study

The exact request that the teacher received in the loops of Section 5.7 is reproduced as Listing A.9 in Appendix A.8.
A filled request of DeepSeek-V4-Flash under the full observation at iteration 2 is kept in `analysis/teacher_prompt_gs_dsv4flash_full_it2.txt`.

#### D.3 Superseded Measure and Excluded Runs

##### D.3.1 The Composite Score

During development, episodes were scored by a composite of five components, each in $[0, 1]$:

$$S_{\text{comp}} = 0.35\,C + 0.25\,H + 0.15\,E + 0.15\,A + 0.10\,V,$$

where:

- $C$ is completion: monsters defeated relative to the reference solver's kill count, or to all monsters where no reference exists;
- $H$ is the HP score: final HP relative to the reference HP; on reference floors, a final HP above the reference is scored as reference / final, because it indicates that the boss was not fought;
- $E$ is step efficiency: 1 up to the reference number of steps, then decreasing linearly;
- $A$ is the stat or shop score: final ATK and DEF relative to the reference, or whether DEF was bought on floors with a shop;
- $V = 1 - \min(1, 0.15 \cdot \text{number of rule violations})$ is the violation score.

If the floor's goal is a boss and the boss survives, the total is halved.

The composite ranks outcomes in the wrong order for the questions of this thesis.
A fatal boss attempt that defeated most monsters scores higher than a safe episode that stopped with the boss alive, and HP above the reference is penalised.
It is therefore not used for any claim of Chapter 6; the goal score of Section 5.9.3 replaced it.
It remains the score of the development-phase pilots of Section 6.8.1, and every score in D.1 and D.2 is a composite score.

##### D.3.2 Runs Excluded from Chapter 6

Table D.55 lists the stored results that were excluded from Chapter 6 because a defect of the harness or of the setup made them invalid, or because a later version of the same configuration superseded them.
They are kept under a file-name prefix or in a sub-folder of `results/reliability/` that names the defect, and they are not pooled with valid results.
Most of them come from the planning study of Section 6.6.
Before valid data were obtained, the plan harness was corrected four times: a plan line was discarded when reasoning preceded it, the parser of an earlier single-plan mode matched almost no plan, models repeated the chosen action as the first planned step, and a planned step that had become unwinnable was handed to the heuristic instead of ending the plan.
In addition, the reasoning cap was raised, because short caps truncated plan answers.

**Table D.55:** Excluded and superseded results.

| Prefix or folder | Defect | Effect | Episodes |
|---|---|---|---|
| `_void_nexttrunc_` | The answer extractor kept only the `FINAL_CHOICE` line when reasoning preceded it, so the `NEXT:` plan line was lost. | DeepSeek-V4-Flash executed no commitments (its planning cells were reactive in effect); Qwen3.5-397B about half. | 32 (simple, tower) |
| `_void_oneshotparser_` | The legacy single-plan mode expected coordinates in a `PLAN:` line; Qwen3.5-397B wrote none, and the other plans listed items and unreachable tiles. | In 9 of 10 episodes, the heuristic chose every decision. | 10 (simple) |
| `_v1next_` | The instruction "the next $k-1$ actions after it" was read as including the chosen action; a committed step that had become unwinnable was handed to the heuristic instead of ending the plan. | DeepSeek-V4-Flash repeated the chosen action as the first planned step in every plan; three to eight heuristic turns per cell. | 44 (simple, complex, tower) |
| `_v1next_complex_deepseek-v4-flash_survival_final2_plan3`, `…_plan5` | In addition, the daily request limit of the second API key was exhausted during the batch (Appendix H, incident 14). | Empty answers and fallback turns in the commit-3 and commit-5 cells of DeepSeek-V4-Flash on the complex floor. | 7 (complex; included in the 44 above) |
| `_void_preoverridefix_` | Same defect as `_v1next_` (an unwinnable committed step handed to the heuristic); one episode started before the fix. | — | 1 (simple) |
| `_void_…_noparse` | First planning trial, before the plan line was parsed. | — | 2 (simple) |
| `_ablation_effcost_numeric` | A placeholder in the effective-cost annotation was replaced by a number (Appendix H, incident 1). | Kept as an unintended ablation: 0 of 20. | 20 (simple) |
| `_stale_shop_prompt` | A surviving process ran an obsolete configuration alongside the corrected one (Appendix H, incident 4). | — | 3 (simple) |
| `_partial_` | Run stopped at the user's request after one episode. | — | 1 (complex) |
| `_superseded_hpfloor/` | Corrected engine with the tower prompt at the 40 % rule, before plan memory (development label `final6`): the DeepSeek-V4-Flash runs with the strategic 40 % override of designs 1 to 4 (HP floor), the Qwen3.5-397B run without it. | Superseded by design 5 (no override, rule 4 at 60 %, plan memory). Section 6.7.3 quotes the turn-15 decision of the Qwen3.5-397B run, which Table 6.14 replays. Highest floors MT8, MT8 (DeepSeek-V4-Flash) and MT8 (Qwen3.5-397B). | 3 (tower) |
| `_superseded_keyfact/` | Design 6 with an earlier version of the key-reserve line, which did not yet state the keys that the doors on the way up still need. | The DeepSeek-V4-Flash cell (MT16, MT8, MT8; best run ATK 1,005 / DEF 938) was re-run, and Table 6.13 reports the re-run. The Qwen3.6-35B runs (MT16, MT8, MT8; ATK / DEF 757 / 1,060, 101 / 110 and 98 / 100) and the Mistral Medium 3.5 runs (MT8, MT4, MT4; 119 / 98, 26 / 24 and 26 / 24) were not re-run and are not reported in Chapter 6. Qwen3.6-35B's MT16 run had bought both MT15 trades but held no red key, and its ATK (757) was below the Red Demon King's DEF; the Mistral Medium 3.5 MT4 runs stopped before a Black Slime that was lethal at 20 to 75 HP. | 9 (tower) |

The earlier runs of Qwen3.8-27B at temperature 0 and 16,384 tokens are not reported in Chapter 6.
They won 3/3 reactively and 0/3 with a single whole-floor plan (0.7 valid calls per episode), and their committed plans exist only in the `_v1next_` version.
Table 6.9 therefore reports this model's committed plans from the later runs at temperature 0.6 (note ᵃ of Table 6.9).
Two further sub-folders, `_superseded_cross/` and `_superseded_plannote/`, hold development versions of tower design 5; Appendix F describes them.
The vision-language pilot of Section 6.8.1 is reported in D.1.11: its first run (E10) was invalid because every answer failed to parse and the heuristic took every decision, and the valid run (E15) used Qwen3-Omni-30B.

**Earlier hand-floor runs.**
Before the re-run of Table 6.2, the hand-designed floors were run with the final configuration (`hand0<i>_<m>_final2`; Qwen3.6-35B $N = 3$, DeepSeek-V4-Flash at 16,384 tokens).
Table 6.11 reports the re-run; Table D.56 keeps the earlier results.

**Table D.56:** Earlier hand-floor runs: successes $k/N$ and, in parentheses, HP relative to the exact optimum among the wins.

| Floor | Qwen3.5-397B | DeepSeek-V4-Flash | Qwen3.6-35B |
|---|---|---|---|
| hand01 | 5/5 (0.43) | 4/5 (0.68) | 3/3 (0.64) |
| hand02 | 3/5 (0.54) | 5/5 (0.31) | 3/3 (0.31) |
| hand03 | 0/5 | 0/5 | 0/3 |
| hand04 | 0/5 | 0/5 | 0/3 |

At 32,768 tokens, DeepSeek-V4-Flash won hand01 5/5 (0.66) and hand02 4/5 (0.29).
On hand03, the models repeatedly chose fights they could not win (16 mechanical overrides in five DeepSeek-V4-Flash episodes, 9 in three Qwen3.6-35B episodes); on hand04, they repeatedly chose doors marked as dead ends (11 and 5).
In these runs, the first decision on hand01 separated the two model families.
DeepSeek-V4-Flash opened the left yellow door at (4,8) first in all five episodes, which keeps the optimum of 14 HP reachable; its wins end at 9 and 10 HP.
Qwen3.6-35B and Qwen3.5-397B opened the right yellow door at (6,8) first in every episode (3 and 5), after which at most 10 HP is reachable; their wins end at 9 HP or less.

**Earlier temperature repetitions.**
Before the re-run of Table 6.2, the main cells of the final configuration were also repeated at temperatures 0.6 and, in part, 1.0 (Section 6.3).
Table 6.3 reports the repetitions of the re-run; Table D.57 keeps the earlier ones.

**Table D.57:** Earlier temperature repetitions of the final configuration: successes $k/N$ at temperatures 0 · 0.6 · 1.0. Reasoning cap of DeepSeek-V4-Flash 32,768 tokens, except on hand03 and hand04 (16,384) and on the tower (8,192 at temperature 0, five runs, four of them on MT7; 16,384 at 0.6, one run). "—" = not run.

| Floor and condition | Qwen3.5-397B | DeepSeek-V4-Flash |
|---|---|---|
| Simple | 10/10 · 5/5 · 4/5 ᵃ | 1/5 · 2/5 · — |
| Simple, annotation version of Table 6.5, row 5 | 4/5 · 3/5 ᵇ · — | — |
| Simple, commit-3 plans | 0/5 · 0/5 · — | 0/5 · 0/5 · — |
| Complex, single-floor prompt | 0/5 · 0/5 · — | 0/5 · 0/5 · 0/5 |
| Complex, solver-route prompt | — | 8/10 · 8/10 ᶜ · 2/5 |
| Complex, solver-route prompt, commit-5 plans | — | 4/5 · 4/5 · — |
| hand03 | — | 0/5 · 0/5 · — |
| hand04 | — | 0/5 · 0/5 · — |
| Tower, design 1 (highest floor reached) | — | MT7 · MT7 · — |

ᵃ One win at 10 HP; the failure ended alive at 526 HP.
ᵇ Both failures followed the trajectory of the failure at temperature 0.
ᶜ One death in the marked cell.

#### D.4 Development of the Tower Designs

This section keeps the design history of the tower observation that Chapter 5 condenses into Table 5.2.
For each design, it states what the design added, the stop of the earlier design that motivated it, and the development observations that Chapter 6 does not report.
Development observations come from single runs or single replays and carry no repeated-run claim.
Chapter 6 reports the runs of every design side by side (Table 6.13), Appendix F maps each design to its result-file label (Table F.5), and Appendix A.2 lists the earlier tower prompts.
In the original description, several sentences called design 4 or design 5 the "final design"; below, each line is attributed to the design that introduced it, and design 7 is the final design.

##### D.4.1 Before Design 1: Walkthrough Checkpoints and the First Tower Runs

An expert walkthrough of the 24-floor edition (Expert walkthrough, n.d.) records the hero's attributes after each of its sections.
These records are checkpoints from which a tower segment can be started with the expert's attributes, so that later floors can be evaluated without first playing the earlier ones.
The earlier floors are left untouched at the start of a segment.
The engine stores the checkpoints as `data.WALKTHROUGH_CHECKPOINTS`, and `run_reliability.py --tower --checkpoint N` starts a segment from checkpoint N.
The rule-based heuristic passes segments 0, 3 and 4 and fails segments 1, 2, 5, 6 and 7.

The first tower runs used the walkthrough tower prompt (v14 of D.2.1) and unlogged strategic overrides, both of which the prompt rules of Section 5.4 exclude; with them, Qwen3.6-35B reached MT14.
Two segment runs started from an expert checkpoint ended on MT7 at ATK 32.
A variant in which the model wrote its own notes at every floor change reached MT7 by turn 163 and was stopped.

##### D.4.2 Design 1: Current Floor, Up-Staircase and Return Actions

In design 1, the action list held the up-staircase, *return* actions to earlier floors and the current floor's actions only; climbing back took one staircase action per floor.
The other floors' actions were hidden behind a one-line summary, the kind of one-sided observation that Section 6.4.3 shows to mislead, and keys were counted per floor although they are shared.
The shop rule of the tower prompt asked for ATK above the highest DEF in scope.
Design 1 ran with the 40 % override of Section 5.6, as did designs 2 to 4.

**Stop that motivated design 2.**
Every design-1 run stopped at or below MT7 (Section 6.7.3).
Models shuttled between floors: in a DeepSeek-V4-Flash run of design 1 with the shop-route line, the model chose the return to MT1 five times and climbed straight back each time without opening the door the return was offered for.
Design 2 followed from this: travel is not a decision in the game, and treating it as one created decisions without content.

**Development observation (one variant run, not in Table 6.13).**
A design-1 variant of DeepSeek-V4-Flash with the shop-route line (`tower_deepseek-v4-flash_final2_shoproute_remote`) stopped on MT3 after 27 turns with 5 HP; it is one of the ten MT3 stops of Section 6.7.3.

##### D.4.3 Design 2: Every Reachable Object on Every Visited Floor

On the tower, the loop is the same as on single floors; from design 2 on, what changes is the action list.
It contains every reachable object on every visited floor, regardless of how many floors there are: the current floor's actions first, then one block per other visited floor, each formatted by that floor's own engine instance with the full observation of Section 5.2 (lookahead tree, effective cost, stat-route, order and key lines, status tags).
Choosing an action on another floor walks there, which costs nothing in the game, and performs it in the same step.
A staircase appears only as the way up to a floor that has not been visited yet, and the engine takes it itself (Section 5.6).
Purchases at every shop the hero has found are listed once, usable from any floor.
Keys are counted in one tower-wide budget.
A shop that has not been reached yet is priced on the action that leads to it: what the hero's gold or experience would buy there, and the cost of every monster on the way, now and after one to three of the ATK purchases already available.

Stat items and shop purchases are annotated with their value across all visited floors: which fights they make winnable or free and how much HP they save on the fights listed.
For ATK purchases, the annotation also states how many of them make a fight winnable and how many make it cost at most the share of current HP that rule 4 of the tower prompt allows (60 % from design 5 on, 40 % before).
The original description does not state the design that introduced this cross-floor value.

The planning comparison on the tower used designs 1 and 2 and the development version `final7` of design 5, whose reactive and committed runs form the design-5 rows of Table 6.9.

**Stop that motivated design 3.**
All four design-2 runs stopped on MT8 with ATK between 79 and 92 against Red Bats of DEF 90, which even at ATK 92 were winnable only at about 15,000 HP.
The shop rule of the prompt was satisfied, and the fights it was meant to open were still unaffordable (Section 6.7.3).
The original sentence said that "every run stopped on MT8 with ATK between 67 and 92"; the design-2 result files give hero ATK 92, 82 and 79 (DeepSeek-V4-Flash) and 81 (Qwen3.5-397B), and the design-1 runs stopped on MT7 and MT3.

##### D.4.4 Design 3: Stat-Needs Line and the Affordability Form of the Shop Rule

In design 3, a *stat-needs* line in the state block listed the strongest pending monsters on all visited floors with the ATK at which each becomes winnable and the ATK or DEF at which it costs at most 40 % of current HP.
The stat-needs line and the affordability form of the shop rule ("ATK high enough that the strongest needed monster costs at most 40 % of HP") replaced the rule that had asked only for ATK above the highest DEF.

**Development observations (one design-3 run, not in Chapter 6).**
A design-3 run spent its last gold on a yellow key at MT8, because it was the only action that cost no HP.
Those 10 gold were the margin: fighting the Red Bat on the way up at that turn and spending the gold and experience on DEF would have left 16 HP after the next paying fight on the route, while after the purchase that fight was lethal by 7 HP.
The same run fought two Skeleton Captains on MT7 for 85 and 75 HP with 176 gold in hand, although two DEF purchases for 50 gold would have made both free.
These observations motivated the in-order way-up line, the purchase lines and the end of yellow- and blue-key sales in design 5 (D.4.6).

**Stop that motivated design 4.**
The way-up line replaced the stat-needs line because early floors show monsters of later floors that are never on the way, so the strongest monster seen is the wrong reference for what to buy.

##### D.4.5 Design 4: Way-Up Line

Design 4 replaces the stat-needs line with a *way-up* line: the cheapest route on the highest visited floor to its up-staircase, found by a shortest-path search that orders routes by unwinnable fights, HP, doors and steps.
The line gives the exact cost of every fight on the route at the hero's attributes, a mark on the fights that lie on every route, the total as a share of current HP, the ATK or DEF at which every fight on it costs at most the rule-4 share, and what one to three of each affordable ATK or DEF purchase does to these costs.
Actions on the route are tagged in the action list.
Like the other annotations, the stat-needs line and the way-up line compute and do not recommend.

**Development observation (replay, not in Chapter 6).**
Replayed under design 4, the design-3 position of the yellow-key purchase (D.4.4) shows the limits of the design-4 line: it priced the route at the hero's current attributes (2,380 HP for 2,318 HP), offered purchases one shop at a time and called the lethal fight unwinnable.
The original text does not state which of the two numbers is the route cost and which the HP in hand.
The in-order line of design 5 states "passable, 16 HP left" in that position and "not passable" after the purchase.

**Development observation (one variant run, not in Table 6.13).**
A design-4 variant of DeepSeek-V4-Flash with the effective-cost setting `MOTA_EFFCOST_NET=1` (`tower_deepseek-v4-flash_final5_effnet`) reached MT8 in 220 turns with ATK 129 and DEF 91 and stopped with only lethal or unwinnable fights left; it is one of the 39 runs of designs 1 to 4 counted in Section 6.7.3.

**Stop that motivated design 5.**
Ten runs of designs 1 to 4 stopped on MT3.
In nine of them, the 40 % override had first replaced the model's choice of the Skeleton at (2,3) with a Bat, and the same fight was taken later at 83 to 93 % of HP; the override replaced this Skeleton in 24 of the 39 runs of designs 1 to 4 (Section 6.7.3).
Together with the observations of D.4.4 and D.4.5, this led to design 5.

##### D.4.6 Design 5: Corrected Engine, Rule 4 at 60 %, Plan Memory and the In-Order Way-Up Line

Design 5 moves to the corrected engine (Section 4.5.2), removes the 40 % override, raises rule 4 of the tower prompt to 60 % and adds plan memory (Section 5.5.5).
The way-up line adds three facts: purchases of one attribute are combined across gold and experience shops; a fight that the hero can win but not survive is marked as lethal with its cost instead of as unwinnable; and a last line states whether the route is passable in path order.
For that verdict, the gold and experience in hand, including what the earlier fights on the route pay, buy the cheapest-making attributes before each paying fight, and the line gives the HP left at the staircase or the fight that cannot be survived.
Scripted characters that open areas or change attributes are stated in *event* lines: what the character does, what it gives access to and the exact way there.
Three further facts are attached to actions and one to the state.
A door or fight that makes 0-HP fights reachable states their number and the gold and experience they pay.
A red door states how many red keys the hero holds and what the key seller charges for one.
The Cross states that its gain is a third of the attributes at the moment it is handed in.
A *treasure* line lists up to five uncollected treasures on the visited floors (equipment, feathers, key boxes, the Cross, Holy Water and characters that hand such items over), each with the in-order verdict of the way there.

**Purchase lines.**
A fight that costs HP states what the purchases affordable now do to it (the fewest DEF purchases that make it free, otherwise the DEF or ATK purchases that make it cheapest), and rule 3 of the tower prompt asks the model to buy them before paying the HP; the two Skeleton Captains of D.4.4 motivated this line.
Each single-attribute purchase also states its price per point and, when another open shop sells the same attribute for less per point in the same currency, that shop's price and how much is still missing (the gold shop on MT11 sells +20 for 100 gold, 5 per point, against +4 for 25 gold on MT3).
Rule 3 asks the model to spend experience before gold, which also buys red keys, and to use the dearer shop only when the better one is out of reach and the upgrade is needed now.

**Key sales.**
From design 5 up to design 7, yellow and blue keys are not offered for sale (design 7b sells blue keys again, D.4.9).
An expert never buys them, and the design-3 run of D.4.4 spent its last gold on a yellow key at MT8.

**Rule 4 at 60 %.**
Before design 5, the corrected engine was run with rule 4 at 40 % (development label `final6`, D.3.2).
Without the 40 % override, rule 4 of the prompt had the same effect at the MT3 position of D.4.5 as the override.
In the first Qwen3.5-397B run on the corrected engine without the override, the model itself took the Bat at turn 15; its reasoning computes 40 % of 570 HP as 228 HP and concludes that "the Skeleton fight violates the 40% HP rule" although it "gates critical stat upgrades".
That run reached MT8.
Rule 4 of the tower prompt was raised from 40 % to 60 % after a replay showed that the 40 % rule alone made Qwen3.5-397B decline the fight an expert takes on MT3 in half of the calls, while no threshold made either model take the fight that ends the run (Table 6.14).
The single-floor prompt keeps 40 %.

**Scouting exception.**
Rule 1 of the tower prompt makes one exception to scouting, for reaching a shop that has not been used yet; the development version `final7` of design 5 did not yet contain it (Table 6.9).
Development observation (replay, not in Chapter 6): at an MT3 position where the Gold Shop was listed behind a 72-HP Skeleton, both models took the way up in all six calls with lookahead 2 and with lookahead 3.
With the exception, Qwen3.5-397B took the Skeleton in two of three calls, DeepSeek-V4-Flash in none.

**Plan memory.**
Without conversation history, a decision does not see why the previous one was made.
In the run replayed in Table 6.14, the model opened the door towards the Iron Sword at turn 14; at turn 15, it declined the fight on the way to the sword under the 40 % rule, and nothing in the request recorded the earlier intention (Section 5.5.5).
Plan memory carries the one-line plan that the model writes at the end of each answer into its next request.
The plan is not a summary written by a second call at floor changes, the design of an earlier notes experiment (D.4.1) in which the model ignored a notes line placed after its answer.
The line is read from the visible answer and, if it is not there, from the reasoning.
Both thinking models write it inside their reasoning and answer only with the choice.
In the runs of the development version `final7` of design 5, the engine read the visible answer only, so no plan was ever shown.
These runs are development history (DeepSeek-V4-Flash MT14 three times; Qwen3.5-397B MT16, MT14 and MT8), and so are the `final8` runs, which lacked the treasure, red-door and Cross lines (DeepSeek-V4-Flash MT16, MT14 and MT3; Qwen3.5-397B MT14 three times).
Table 6.9 reports the reactive, commit-3 and commit-5 runs of `final7`, which also lacked the scouting exception and the treasure line, in its design-5 rows.
The condition without plan memory in Section 6.7.3 is a separate design-5 cell (`final9_noplanmem`, Table F.5); an earlier description had attributed it to the `final7` runs.
DeepSeek-V4-Flash writes a plan in 491 of 496 decisions of the final runs (99 %), Qwen3.5-397B in 73 of 594 (12 %); the original text does not name the design of these runs.
The effect of plan memory was measured with design 5 only, run with and without it (Section 6.7.3).

**Development observation: the design-5 run of Qwen3.5-397B.**
It was stopped by the purchase-enumeration defect after reaching MT16 and has no result file (Appendix H, incident 16).

**Stop that motivated design 6.**
Design 6 was added after a design-5 run of DeepSeek-V4-Flash stopped on MT16 at ATK 1,028 and DEF 969 with no red key: it had spent its last one on MT10 at turn 426, with the MT16 red door on the way up.
The MT15 trades were not modelled, although the run earned 1,868 gold and 1,775 experience after reaching MT15.
The original description called this run the best design-5 run, which it is not: the best ended at ATK 1,032 and DEF 1,113 (Table 6.13).
It also said that the trades "would have made the Red Demon King winnable"; at ATK 1,028 against the King's DEF of 1,000 the King was already winnable, and the Holy Shield would have made the fight free.
Every design-5 run that reached MT16 stopped at the Red Demon King, two of them without a red key for its door (Table 5.2).

##### D.4.7 Design 6: MT15 Trades, Key-Reserve Line and Monster Upgrades

Tower design 6 adds two facts and two events of Table 4.4.
The MT15 trades become actions once the hero holds 500 experience or 500 gold; they are never taken by the engine, because they spend resources, and the treasure line lists them with their price and what the hero holds.
A door that is not on the way up and would leave fewer keys of its colour than the doors on the way up still need states so, with the coordinates of those doors.
The fight with the Red Demon King strengthens four kinds of monster for the rest of the game, as its script in the game data does.

The first design-6 runs of DeepSeek-V4-Flash, Qwen3.6-35B and Mistral Medium 3.5 used an earlier version of the key-reserve line, which did not yet state the keys that the doors on the way up still need (D.3.2).
A design-6 run of Qwen3.5-397B reached "MT21" on an engine that showed the staircases of MT18 and MT20 from the start; on the corrected engine its highest floor is MT18 (Appendix H, incident 17).

**Stop that motivated design 7 (development observation; Chapter 6 reports only the MT18 stop).**
Design 7 was added after the first design-6 run of Qwen3.5-397B.
Of its 946 turns, 321 were single purchases, each a model call of about 50 s.
It bought HP four times and then fought three White Warriors at 24,000 HP, paying 14,131 HP for fights that cost a quarter of the current HP, while the fight line called them "already immune".
It stopped on MT18 because the Ice Pickaxe and the last White Warrior each lay behind a blue door and its last blue keys had been spent, which no line stated.
It had entered MT17 at turn 638 with ATK 1,024 and DEF 1,003 and arrived on MT18 at turn 708 with ATK 1,346 and DEF 1,314; its last blue keys went to three doors of MT7 at turns 604, 606 and 609, about 100 turns before the arrival.

##### D.4.8 Design 7: Purchase Quantities, Vampire Tag and the Way to Event Items

Tower design 7 adds three changes.
A shop purchase may carry a quantity: the answer may end with `QUANTITY: n` (at most 10), and the engine repeats the purchase without asking again while it stays affordable.
Monsters whose damage is a share of the hero's current HP (the White Warriors take 25 %) carry the tag "[vampire: takes 25% of your current HP whatever your DEF, so it costs less when your HP is lower]" in place of the DEF threshold, and the prompt's list of special abilities names the ability.
The line of a scripted event whose item or guard lies behind doors now states the way there with its doors and the keys missing for them (for example, the Ice Pickaxe behind a blue door on MT12, "needs 1 blue key(s), you have 0").
The seal line states the doors in front of the remaining guards and how many keys they need together.

**Stop that motivated design 7b.**
A design-7 run of Qwen3.5-397B again reached MT18 without a blue key, although the event line now named the door and the missing key (Section 6.7.3).

##### D.4.9 Design 7b: Blue Keys for Sale

Design 7b is design 7 with blue keys for sale, as in the original game.
It followed when the stored position of the design-6 run on MT18, continued with blue keys for sale, reached the normal ending (Section 6.7.3); the rule against key purchases was kept for yellow keys.
Its one run from MT0 (DeepSeek-V4-Flash) reached MT17 and was stopped at the time limit of the experiments at turn 619 (288 model calls), with ATK 1,152, DEF 1,048 and one blue key in hand (Table 6.13); it has no result file (Appendix F).
Three runs were planned; the experiments were closed after the first.

## 3. Former Appendix E

### Appendix E: The Fine-Tuned Small Model

This appendix reports the pilot of Section 6.8.2 in full.
It asked whether decisions of the rule-based agent, the solver and a large model can be transferred into a model small enough to run on a consumer graphics card.
The pilot predates the final configuration and the repeated-run protocol, and no claim of Chapter 7 rests on it.

#### E.1 Setup

**Table E.1:** Fine-tuning setup.

| Parameter | First experiments | Solver-guided variant |
|---|---|---|
| Base model | LFM2.5-1.2B-Thinking | same |
| Method | low-rank adapters on a 4-bit quantised model (QLoRA; Dettmers et al., 2023) | same |
| Adapter rank / scaling | 32 / 64 | 16 / 32 |
| Trainable parameters | 22.2 million (1.86 %) | — |
| Learning rate | $2 \times 10^{-4}$, cosine schedule | $1 \times 10^{-4}$ |
| Epochs | 2 | 5 |
| Maximum sequence length | 1,024 to 2,048 tokens | 4,096 tokens |
| Effective batch size | 8 | — |
| Hardware | one graphics card with 8 GB of memory | same |

Two alternative base models, Gemma-4-E4B and Gemma-4-E2B (Google DeepMind, 2026), could not be fine-tuned on this card.
Their vocabulary of 262,144 tokens yields an embedding table of 1.6 to 3.2 GB in 16-bit precision, which the 4-bit quantisation does not reduce, and the total exceeded 8 GB.
The 65,536-token vocabulary of LFM2.5-1.2B-Thinking avoids this.

#### E.2 Decisions of the Rule-Based Agent

The first experiment trained on 342 game states of floor MT3 with the rule-based agent's action as the target, as a choice among labelled options.
On 20 held-out states from the same distribution, the fine-tuned model chose the reference action in 18 cases (90 %), with a valid output format in all cases.

#### E.3 Reasoning of a Large Model

A second experiment compared three training sets of the same format (Table E.2).

**Table E.2:** Training data and accuracy on 30 held-out states (in distribution and out of distribution).

| Training data | Examples | Final loss | Accuracy (out of distribution) | Accuracy (in distribution) | Valid format |
|---|---|---|---|---|---|
| Decisions of the solver and the rule-based agent | 736 | 0.030 | 26/30 | 26/30 | 100 % |
| The same plus reasoning of Qwen3.5-397B | 836 | 0.057 | 26/30 | 26/30 | 100 % |
| Reasoning of Qwen3.5-397B only | 100 | 0.146 | 8/30 | 11/30 | 97 % |

The first two models produced identical predictions: the 100 reasoning examples had no measurable effect in the mixture.
Trained on the reasoning alone, the model collapsed to two of the three possible answers.
Three factors confound this condition: it had about seven times fewer examples, 27 % of its answers used labels that did not occur in the test set, and it had not converged.

#### E.4 Solver-Guided Reasoning

The third experiment kept only reasoning whose decision the framework's Python breadth-first solver confirms; on the simple floor, its optimum of 13 HP equals the exact one.
This solver determined the optimal action at 197 states of the simple floor, and Qwen3.5-397B generated reasoning for these states.
The 30 traces whose chosen action was optimal or *equivalent* (an action from which the optimum remains reachable) formed the training set.
The fine-tuned model chose an optimal or equivalent action in 52.9 % of decisions on the simple floor.
Played as an agent, it reached 13 HP, the floor's optimum, in one episode on the engine version of that time.
That version still contained the unlogged strategic overrides of Section 6.4.1, so the episode is not attributed to the small model alone.

#### E.5 Assessment

The pilot suggests that a 1.2-billion-parameter model can learn the output format and the decisions of a rule-based policy from a few hundred examples.
Whether unverified reasoning of a large model is a poor training signal at this scale cannot be separated from the smaller, unconverged training set of that condition (Section E.3).
Whether solver-verified traces produce a small agent that wins complete episodes under the final configuration is untested (Section 7.6).

## 4. Former Appendix G

### Appendix G: Monsters of the Tower

The tower uses the monster table of the 24-floor edition of the game (`data/games/24/project/enemys.js` in the repository).
Table G.1 lists the 43 of its 66 entries that the engine defines.
The other 23 entries occur on no floor map.
They are 20 placeholders with 0 / 0 / 0, the Skeleton Priest (`skeletonPriest`, 100 / 100 / 0), and `vampire2` and `vampire3`.
The last two hold the values that the after-battle scripts of MT19 and MT21 write into the Nether Demon King.
The single floors use their own monster tables, which are given with their maps in Appendix B.5.
The engine shows the English names in the second column; the game's identifier in the first column is the stable reference in the code and the logs.
The three entries with 0 / 0 / 0 in Table G.1 are placeholders of the game data that occur on no floor of the tower.
Abilities marked "not modelled" are not applied by the engine.
They are poison, weaken and curse, which the game defines without applying them in combat (Table 4.1), and the repulse of the Steel Guard; no monster with them occurs on a floor of the tower.

**Table G.1:** Monsters of the 24-floor tower defined by the engine, with the values of the game data before any after-battle script.

| Identifier | Name in the engine | HP | ATK | DEF | Ability |
|---|---|---|---|---|---|
| `greenSlime` | Green Slime | 50 | 20 | 1 | – |
| `redSlime` | Red Slime | 70 | 15 | 2 | – |
| `blackSlime` | Black Slime | 200 | 35 | 10 | – |
| `slimelord` | Slime Lord | 700 | 250 | 125 | – |
| `bat` | Bat | 100 | 20 | 5 | – |
| `bigBat` | Big Bat | 150 | 65 | 30 | – |
| `redBat` | Red Bat | 550 | 160 | 90 | – |
| `skeleton` | Skeleton | 110 | 25 | 5 | – |
| `skeletonSoilder` | Skeleton Soldier | 150 | 40 | 20 | – |
| `skeletonCaptain` | Skeleton Captain | 400 | 90 | 50 | – |
| `ghostSkeleton` | Nether Captain | 2500 | 900 | 850 | – |
| `zombie` | Beast-Man | 300 | 75 | 45 | – |
| `zombieKnight` | Beast Warrior | 900 | 450 | 330 | – |
| `rock` | Rock Man | 500 | 115 | 65 | – |
| `slimeMan` | Shadow Warrior | 3100 | 1150 | 1050 | – |
| `bluePriest` | Junior Mage | 125 | 50 | 25 | – |
| `redPriest` | Senior Mage | 100 | 200 | 110 | – |
| `brownWizard` | Hemp-Robe Mage | 250 | 120 | 70 | fixed damage (100) |
| `redWizard` | Red-Robe Mage | 500 | 400 | 260 | fixed damage (300) |
| `yellowGuard` | Junior Guard | 450 | 150 | 90 | – |
| `blueGuard` | Mid Guard | 1250 | 500 | 400 | – |
| `redGuard` | Senior Guard | 1500 | 560 | 460 | – |
| `swordsman` | Two-Hand Swordsman | 1200 | 620 | 520 | – |
| `soldier` | Nether Warrior | 2000 | 680 | 590 | – |
| `yellowKnight` | Gold Sentinel | 850 | 350 | 200 | – |
| `redKnight` | Gold Captain | 900 | 750 | 650 | – |
| `darkKnight` | Spirit Warrior | 1200 | 980 | 900 | – |
| `blackKing` | Black Demon King | 1000 | 500 | 0 | – |
| `redKing` | Red Demon King | 15000 | 1000 | 1000 | – |
| `vampire` | Nether Demon King | 30000 | 1700 | 1500 | – |
| `magicDragon` | Magic Dragon | 99999 | 9999 | 5000 | – |
| `octopus` | Blood Shadow | 99999 | 5000 | 4000 | – |
| `poisonSkeleton` | Purple Skeleton | 0 | 0 | 0 | – |
| `badPrincess` | Witch of Agony | 0 | 0 | 0 | – |
| `whiteKing` | White Warrior | 1300 | 300 | 150 | vampire (1/4 of current HP) |
| `blackMagician` | Spirit Mage | 1500 | 830 | 730 | vampire (1/3 of current HP) |
| `blueKnight` | Blue Knight | 100 | 120 | 0 | counter attack |
| `poisonBat` | Purple Bat | 100 | 120 | 0 | weaken, not modelled |
| `silverSlime` | Silver Slime | 100 | 120 | 0 | curse, not modelled |
| `redSwordsman` | Sword King | 100 | 120 | 0 | 8-strike attack |
| `poisonZombie` | Green Beast-Man | 100 | 120 | 0 | poison, not modelled |
| `steelGuard` | Steel Guard | 0 | 0 | 0 | repulse, not modelled |
| `evilBat` | Evil Bat | 1000 | 1 | 0 | magic attack, solid |

From tower design 6 on, the engine applies the after-battle scripts of the game data that change monster values for the rest of the run (Section 4.5.3).
Defeating the Red Demon King on MT16 raises four monsters to new values (HP / ATK / DEF):

- Spirit Warrior (`darkKnight`) 1600 / 1306 / 1200;
- Nether Captain (`ghostSkeleton`) 3333 / 1200 / 1133;
- Spirit Mage (`blackMagician`) 2000 / 1106 / 973;
- Red Demon King (`redKing`) 20000 / 1333 / 1333.

Defeating the Nether Demon King on MT19 raises it to 45000 / 2550 / 2250 for the fight on MT21 (the values of the `vampire2` entry).
The design-6 and design-7 runs of Table 6.13 that defeat the Red Demon King fight these upgraded monsters on the floors above.
The script after the fight on MT21 raises the same monsters again (the Nether Demon King to the `vampire3` values); it applies only beyond the normal ending, which is out of scope.

Tower designs 1 to 4 used, for nine items of the upper floors (three swords, four shields, the green gem and the pack), the values of another edition of the game.
The corrected engine of designs 5 to 7 uses the values of the game data (Section 4.5.2).
The single floors are not affected.
