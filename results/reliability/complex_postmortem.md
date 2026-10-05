# complex floor — episode post-mortem

45 LLM episodes with a stored run log (logs/runs + archives). BFS-optimal final HP = 22.

## Outcome classes

| class | n | meaning |
|---|---|---|
| kill | 5 | boss killed, hero alive |
| lethal_boss | 26 | hero attacked the boss with HP <= boss damage (suicide) |
| lethal_fight | 12 | hero died to a non-boss enemy |
| alive_no_kill | 2 | stopped / stuck alive without killing the boss |

## By model

| model | n | kill | lethal_boss | lethal_fight | alive_no_kill | kill HP (list) |
|---|---|---|---|---|---|---|
| qwen3.5-397b-a17b | 14 | 4 | 3 | 6 | 1 | [22, 22, 22, 22] |
| qwen3.5-35b-a3b | 11 | 0 | 4 | 6 | 1 | [] |
| qwen3.6-35b-a3b | 10 | 0 | 10 | 0 | 0 | [] |
| qwen3.8-27b | 10 | 1 | 9 | 0 | 0 | [22] |

## Lethal boss attempts (suicides)

Hero stats at the moment of the fatal boss fight. `damage` is what the engine showed the model *before* it chose the fight — the HP arithmetic was always available in the prompt.

| file | model | hp before | atk | def | boss damage shown | hp after | turns |
|---|---|---|---|---|---|---|---|
| 20260527_004951_863303_complex_llm.json | qwen3.5-35b-a3b | 270 | 14 | 17 | 412 | -142 | 49 |
| 20260527_163720_946596_complex_llm.json | qwen3.5-35b-a3b | 49 | 14 | 18 | 364 | -315 | 56 |
| 20260527_165216_394729_complex_llm.json | qwen3.5-35b-a3b | 360 | 14 | 17 | 412 | -52 | 49 |
| 20260527_170638_742491_complex_llm.json | qwen3.5-35b-a3b | 335 | 14 | 17 | 412 | -77 | 49 |
| 20260921_035343_001740_complex_llm.json | qwen3.5-397b-a17b | 32 | 14 | 18 | 364 | -332 | 57 |
| 20260921_045704_868196_complex_llm.json | qwen3.5-397b-a17b | 355 | 14 | 17 | 412 | -57 | 49 |
| 20260921_055639_514387_complex_llm.json | qwen3.5-397b-a17b | 344 | 14 | 18 | 364 | -20 | 54 |
| 20260921_060116_948018_complex_llm.json | qwen3.6-35b-a3b | 330 | 14 | 17 | 412 | -82 | 49 |
| 20260921_060550_612963_complex_llm.json | qwen3.6-35b-a3b | 330 | 14 | 17 | 412 | -82 | 49 |
| 20260921_061023_665324_complex_llm.json | qwen3.6-35b-a3b | 330 | 14 | 17 | 412 | -82 | 49 |
| 20260921_061502_790896_complex_llm.json | qwen3.6-35b-a3b | 330 | 14 | 17 | 412 | -82 | 49 |
| 20260921_061933_471372_complex_llm.json | qwen3.6-35b-a3b | 330 | 14 | 17 | 412 | -82 | 49 |
| 20260921_062343_640765_complex_llm.json | qwen3.6-35b-a3b | 330 | 14 | 17 | 412 | -82 | 49 |
| 20260921_062757_470932_complex_llm.json | qwen3.6-35b-a3b | 330 | 14 | 17 | 412 | -82 | 49 |
| 20260921_063206_351076_complex_llm.json | qwen3.6-35b-a3b | 330 | 14 | 17 | 412 | -82 | 49 |
| 20260921_063617_477872_complex_llm.json | qwen3.6-35b-a3b | 330 | 14 | 17 | 412 | -82 | 49 |
| 20260921_064224_185223_complex_llm.json | qwen3.6-35b-a3b | 288 | 14 | 17 | 412 | -124 | 53 |
| 20260921_085051_167065_complex_llm.json | qwen3.8-27b | 360 | 14 | 17 | 412 | -52 | 49 |
| 20260921_104407_811790_complex_llm.json | qwen3.8-27b | 360 | 14 | 17 | 412 | -52 | 49 |
| 20260921_113857_417713_complex_llm.json | qwen3.8-27b | 270 | 14 | 16 | 460 | -190 | 47 |
| 20260921_125427_522446_complex_llm.json | qwen3.8-27b | 360 | 14 | 17 | 412 | -52 | 50 |
| 20260921_144843_782892_complex_llm.json | qwen3.8-27b | 339 | 14 | 18 | 364 | -25 | 54 |
| 20260921_154518_640038_complex_llm.json | qwen3.8-27b | 360 | 14 | 17 | 412 | -52 | 49 |
| 20260921_171050_849165_complex_llm.json | qwen3.8-27b | 337 | 14 | 17 | 412 | -75 | 52 |
| 20260921_180535_662345_complex_llm.json | qwen3.8-27b | 67 | 14 | 18 | 364 | -297 | 56 |
| 20260921_184618_263394_complex_llm.json | qwen3.8-27b | 185 | 14 | 19 | 316 | -131 | 52 |

## Divergence from the best stored kill (20260921_032609_399904_complex_llm.json, HP=22, 52 turns)

| first divergent turn | episodes |
|---|---|
| 9 | 7 |
| 16 | 1 |
| 21 | 1 |
| 24 | 6 |
| 27 | 1 |
| 30 | 1 |
| 37 | 12 |
| 40 | 1 |
| 49 | 12 |
| 50 | 1 |
| identical/prefix | 1 |

### What the failing episodes did at their divergence point

- turn 9: 7× `fight@(11,8)  (kill did fight@(12,9))`
- turn 16: 1× `fight@(9,3)  (kill did fight@(4,2))`
- turn 21: 1× `fight@(11,8)  (kill did fight@(2,4))`
- turn 24: 3× `fight@(0,2)  (kill did fight@(11,8))`
- turn 24: 2× `fight@(9,1)  (kill did fight@(11,8))`
- turn 24: 1× `fight@(6,4)  (kill did fight@(11,8))`
- turn 27: 1× `fight@(12,12)  (kill did fight@(9,1))`
- turn 30: 1× `fight@(0,2)  (kill did fight@(11,0))`
- turn 37: 10× `open_door@(5,8)  (kill did open_door@(12,2))`
- turn 37: 1× `fight@(6,4)  (kill did open_door@(12,2))`
- turn 37: 1× `open_door@(4,5)  (kill did open_door@(12,2))`
- turn 40: 1× `fight@(12,12)  (kill did fight@(6,4))`
- turn 49: 4× `fight@(6,0)  (kill did fight@(10,6))`
- turn 49: 3× `fight@(9,3)  (kill did fight@(10,6))`
- turn 49: 2× `fight@(2,9)  (kill did fight@(10,6))`
- turn 49: 2× `fight@(10,10)  (kill did fight@(10,6))`
- turn 50: 1× `fight@(6,0)  (kill did fight@(9,3))`

### Best kill trajectory (action signatures)

```
  1. Collect Blue Key at (6,9)
  2. Collect Yellow Key at (7,8)
  3. open_door@(8,7)
  4. Collect Red Potion (+75 HP) at (8,6)
  5. Collect Blue Gem (+1 DEF) at (8,5)
  6. fight@(8,12)
  7. Collect Green Gem (+5 MDEF) at (8,11)
  8. Collect Red Gem (+1 ATK) at (8,10)
  9. fight@(12,9)
 10. Collect Yellow Key at (12,10)
 11. Collect Red Potion (+75 HP) at (12,11)
 12. open_door@(8,4)
 13. fight@(8,2)
 14. open_door@(6,2)
 15. Collect Red Gem (+1 ATK) at (6,1)
 16. fight@(4,2)
 17. Collect Blue Gem (+1 DEF) at (4,0)
 18. Collect Blue Gem (+1 DEF) at (4,4)
 19. Collect Green Gem (+5 MDEF) at (3,0)
 20. Collect Red Potion (+75 HP) at (3,1)
 21. fight@(2,4)
 22. Collect Blue Gem (+1 DEF) at (1,3)
 23. Collect Red Gem (+1 ATK) at (1,5)
 24. fight@(11,8)
 25. Collect Blue Gem (+1 DEF) at (12,6)
 26. Collect Red Potion (+75 HP) at (12,7)
 27. fight@(9,1)
 28. Collect Blue Gem (+1 DEF) at (9,0)
 29. Collect Red Potion (+75 HP) at (8,0)
 30. fight@(11,0)
 31. Collect Red Potion (+75 HP) at (12,0)
 32. Collect Green Gem (+5 MDEF) at (12,1)
 33. fight@(0,2)
 34. Collect Red Gem (+1 ATK) at (1,1)
 35. Collect Blue Key at (1,0)
 36. Collect Yellow Key at (0,0)
 37. open_door@(12,2)
 38. Collect Blue Gem (+1 DEF) at (12,3)
 39. Collect Red Potion (+75 HP) at (12,4)
 40. fight@(6,4)
 41. Collect Red Potion (+75 HP) at (6,5)
 42. fight@(6,6)
 43. Collect Green Gem (+5 MDEF) at (4,6)
 44. fight@(12,12)
 45. Collect Blue Potion (+200 HP) at (10,12)
 46. open_door@(5,8)
 47. fight@(3,8)
 48. Collect Red Potion (+75 HP) at (1,7)
 49. fight@(10,6)
 50. fight@(9,3)
 51. Collect Red Potion (+75 HP) at (10,3)
 52. fight@(6,0)
```

## All episodes

| file | model | class | final HP | score | turns | llm turns | last action |
|---|---|---|---|---|---|---|---|
| 20260601_031150_389884_complex_llm.json | qwen3.5-397b-a17b | alive_no_kill | 196 | 0.3409 | 31 | 13 | Fight Big Bat at (9,1) dmg=237 |
| 20260527_074006_704228_complex_llm.json | qwen3.5-35b-a3b | alive_no_kill | 17 | 0.8982 | 52 | 21 | Fight Boss at (6,0) dmg=412 |
| 20260921_032609_399904_complex_llm.json | qwen3.5-397b-a17b | kill | 22 | 0.955 | 52 | 21 | Fight Boss at (6,0) dmg=412 |
| 20260921_041936_660792_complex_llm.json | qwen3.5-397b-a17b | kill | 22 | 0.955 | 52 | 21 | Fight Boss at (6,0) dmg=412 |
| 20260921_052611_292539_complex_llm.json | qwen3.5-397b-a17b | kill | 22 | 0.9587 | 51 | 20 | Fight Boss at (6,0) dmg=412 |
| 20260921_053654_868941_complex_llm.json | qwen3.5-397b-a17b | kill | 22 | 0.9587 | 51 | 20 | Fight Boss at (6,0) dmg=412 |
| 20260921_074534_654049_complex_llm.json | qwen3.8-27b | kill | 22 | 0.955 | 52 | 21 | Fight Boss at (6,0) dmg=412 |
| 20260921_055639_514387_complex_llm.json | qwen3.5-397b-a17b | lethal_boss | -20 | 0.6825 | 54 | 22 | Fight Boss at (6,0) dmg=364 |
| 20260921_144843_782892_complex_llm.json | qwen3.8-27b | lethal_boss | -25 | 0.6825 | 54 | 22 | Fight Boss at (6,0) dmg=364 |
| 20260527_165216_394729_complex_llm.json | qwen3.5-35b-a3b | lethal_boss | -52 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_085051_167065_complex_llm.json | qwen3.8-27b | lethal_boss | -52 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_104407_811790_complex_llm.json | qwen3.8-27b | lethal_boss | -52 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_125427_522446_complex_llm.json | qwen3.8-27b | lethal_boss | -52 | 0.6975 | 50 | 20 | Fight Boss at (6,0) dmg=412 |
| 20260921_154518_640038_complex_llm.json | qwen3.8-27b | lethal_boss | -52 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_045704_868196_complex_llm.json | qwen3.5-397b-a17b | lethal_boss | -57 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_171050_849165_complex_llm.json | qwen3.8-27b | lethal_boss | -75 | 0.69 | 52 | 21 | Fight Boss at (6,0) dmg=412 |
| 20260527_170638_742491_complex_llm.json | qwen3.5-35b-a3b | lethal_boss | -77 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_060116_948018_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -82 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_060550_612963_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -82 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_061023_665324_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -82 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_061502_790896_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -82 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_061933_471372_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -82 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_062343_640765_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -82 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_062757_470932_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -82 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_063206_351076_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -82 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_063617_477872_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -82 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_064224_185223_complex_llm.json | qwen3.6-35b-a3b | lethal_boss | -124 | 0.6862 | 53 | 22 | Fight Boss at (6,0) dmg=412 |
| 20260921_184618_263394_complex_llm.json | qwen3.8-27b | lethal_boss | -131 | 0.69 | 52 | 20 | Fight Boss at (6,0) dmg=316 |
| 20260527_004951_863303_complex_llm.json | qwen3.5-35b-a3b | lethal_boss | -142 | 0.7012 | 49 | 19 | Fight Boss at (6,0) dmg=412 |
| 20260921_113857_417713_complex_llm.json | qwen3.8-27b | lethal_boss | -190 | 0.7043 | 47 | 19 | Fight Boss at (6,0) dmg=460 |
| 20260921_180535_662345_complex_llm.json | qwen3.8-27b | lethal_boss | -297 | 0.675 | 56 | 24 | Fight Boss at (6,0) dmg=364 |
| 20260527_163720_946596_complex_llm.json | qwen3.5-35b-a3b | lethal_boss | -315 | 0.675 | 56 | 24 | Fight Boss at (6,0) dmg=364 |
| 20260921_035343_001740_complex_llm.json | qwen3.5-397b-a17b | lethal_boss | -332 | 0.6712 | 57 | 25 | Fight Boss at (6,0) dmg=364 |
| 20260527_164622_858094_complex_llm.json | qwen3.5-35b-a3b | lethal_fight | -2 | 0.3039 | 36 | 13 | Fight Green Slime at (6,6) dmg=9 |
| 20260526_003549_619976_complex_llm.json | qwen3.5-35b-a3b | lethal_fight | -9 | 0.3337 | 54 | 22 | Fight Bat at (11,4) dmg=108 |
| 20260921_043231_101056_complex_llm.json | qwen3.5-397b-a17b | lethal_fight | -21 | 0.33 | 56 | 24 | Fight Big Bat at (0,6) dmg=115 |
| 20260921_030547_431629_complex_llm.json | qwen3.5-397b-a17b | lethal_fight | -31 | 0.3152 | 35 | 13 | Fight Big Bat at (9,1) dmg=147 |
| 20260921_044206_292641_complex_llm.json | qwen3.5-397b-a17b | lethal_fight | -31 | 0.3152 | 35 | 13 | Fight Big Bat at (12,12) dmg=147 |
| 20260525_233756_828593_complex_llm.json | qwen3.5-35b-a3b | lethal_fight | -41 | 0.3184 | 32 | 14 | Fight Slime Lord at (10,10) dmg=230 |
| 20260526_231938_468873_complex_llm.json | qwen3.5-397b-a17b | lethal_fight | -41 | 0.3184 | 32 | 14 | Fight Big Bat at (12,12) dmg=237 |
| 20260527_001148_654820_complex_llm.json | qwen3.5-397b-a17b | lethal_fight | -41 | 0.3184 | 32 | 14 | Fight Big Bat at (12,12) dmg=237 |
| 20260527_003627_192765_complex_llm.json | qwen3.5-35b-a3b | lethal_fight | -41 | 0.3184 | 32 | 14 | Fight Big Bat at (12,12) dmg=237 |
| 20260525_232548_460808_complex_llm.json | qwen3.5-35b-a3b | lethal_fight | -50 | 0.3184 | 32 | 14 | Fight Bat at (8,2) dmg=230 |
| 20260527_002529_405244_complex_llm.json | qwen3.5-35b-a3b | lethal_fight | -88 | 0.3184 | 32 | 14 | Fight Red Bat at (4,11) dmg=284 |
| 20260527_010026_613155_complex_llm.json | qwen3.5-397b-a17b | lethal_fight | 0 | 0.2856 | 30 | 11 | Fight Big Bat at (12,12) dmg=165 |
