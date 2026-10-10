# Podium prediction: 2026 Singapore Sprint (Marina Bay, Oct 10)

Snapshot of the executed `f1_race_prediction.ipynb` run on 2026-10-10. Trained on the 21
earlier 2026 scored sessions (16 Grands Prix and 5 sprints). The run also included per-driver
venue-history features from 96 earlier-season (2023–2025) sessions at the same circuits,
including the 2023, 2024 and 2025 Singapore Grands Prix. For the target, only sprint qualifying
(`SQ`) was loaded. The sprint and the weekend's qualifying and Grand Prix were not loaded.
Grid = sprint qualifying position (no `TARGET_GRID` overrides). The run finished at 09:26 UTC,
after the 09:00 UTC sprint start, but it used no data from after sprint qualifying. Rerunning
the notebook overwrites its outputs, so this file is the record of this run.

## Best single answer

**1. Verstappen, 2. Russell, 3. Leclerc.** Seven of nine models agree on this podium. Verstappen
and Russell are nearly even: the simulation gives each a P(podium) of 0.60. Piastri is the most
plausible alternative for third.

## Predicted podium by model

Brackets are P(podium) where the model gives one.

| Model | 1st | 2nd | 3rd |
|---|---|---|---|
| Grid order | VER | RUS | LEC |
| Qualifying order | VER | RUS | LEC |
| Prior finish | VER | ANT | LEC |
| Ridge pace | VER | RUS | LEC |
| CatBoost | VER | RUS | PIA |
| Logistic | VER (0.74) | RUS (0.72) | LEC (0.52) |
| Shallow tree | VER (0.83) | RUS (0.75) | LEC (0.45) |
| Simulation | VER (0.60) | RUS (0.60) | LEC (0.49) |
| Grid-slot rate | VER (0.66) | RUS (0.59) | LEC (0.50) |

## Simulation and grid-slot probabilities (top eight by simulated P(podium))

| Driver | Sim P(win) | Sim P(podium) | Sim expected position | Grid-slot P(win) | Grid-slot P(podium) |
|---|---:|---:|---:|---:|---:|
| Max Verstappen | 0.254 | 0.603 | 5.19 | 0.367 | 0.662 |
| George Russell | 0.244 | 0.600 | 4.81 | 0.249 | 0.594 |
| Charles Leclerc | 0.158 | 0.488 | 5.39 | 0.133 | 0.504 |
| Oscar Piastri | 0.094 | 0.341 | 6.55 | 0.052 | 0.396 |
| Kimi Antonelli | 0.079 | 0.307 | 5.27 | 0.001 | 0.111 |
| Lando Norris | 0.075 | 0.279 | 7.44 | 0.015 | 0.282 |
| Lewis Hamilton | 0.064 | 0.261 | 6.00 | 0.004 | 0.183 |
| Liam Lawson | 0.011 | 0.038 | 8.88 | 0.001 | 0.062 |

The simulation's noise and retirement rates come from Grand Prix and sprint history pooled.
A sprint is shorter, so the pooled retirement rate may overstate a sprint's retirement risk, which
would lower the simulated expected positions of the front-runners.

## Singapore venue history

Each driver's mean pace ratio (`VenuePace`) and qualifying ratio (`VenueQualiRatio`) at Marina
Bay in 2023–2025, for the top eight on predicted pace (lower is faster):

| Driver | VenuePace | VenueQualiRatio |
|---|---:|---:|
| Max Verstappen | 0.9875 | 1.0056 |
| George Russell | 0.9899 | 1.0015 |
| Charles Leclerc | 0.9935 | 1.0035 |
| Oscar Piastri | 0.9926 | 1.0088 |
| Lando Norris | 0.9853 | 1.0026 |
| Kimi Antonelli | 0.9861 | 1.0043 |
| Lewis Hamilton | 0.9894 | 1.0050 |
| Isack Hadjar | 1.0002 | 1.0077 |

Validation found no gain from these features (next section), so they barely move the ranking.
The top three is the same as in a run without them.

## How much to trust it

Walk-forward validation on 17 held-out sessions (13 Grands Prix, 4 sprints; 51 podium places),
mean per session:

| Model | Podium overlap | Winner correct | Brier | Log loss | Overlap vs Ridge [95% CI] |
|---|---:|---:|---:|---:|---|
| Ridge pace | 0.667 | 0.647 | | | reference |
| Grid order | 0.647 | 0.647 | | | -0.020 [-0.059, 0.000] |
| Simulation | 0.647 | 0.529 | 0.066 | 0.201 | -0.020 [-0.059, 0.000] |
| Grid-slot rate | 0.647 | 0.647 | 0.066 | 0.212 | -0.020 [-0.059, 0.000] |
| Qualifying order | 0.627 | 0.647 | | | -0.039 [-0.098, 0.000] |
| Logistic | 0.627 | 0.588 | 0.067 | 0.214 | -0.039 [-0.118, 0.039] |
| Shallow tree | 0.588 | 0.529 | 0.078 | 0.238 | -0.078 [-0.157, 0.000] |
| CatBoost | 0.569 | 0.471 | | | -0.098 [-0.196, -0.000] (worse) |
| Prior finish | 0.451 | 0.118 | | | -0.216 [-0.294, -0.137] (worse) |

On the 4 held-out sprints only (Miami, Canada, British, Dutch; 12 podium places):

| Model | Podium places | Winner correct |
|---|---:|---:|
| Ridge pace | 10 of 12 | 3 of 4 |
| Grid / qualifying order | 10 of 12 | 3 of 4 |
| Shallow tree | 10 of 12 | 3 of 4 |
| Simulation | 10 of 12 | 2 of 4 |
| Grid-slot rate | 10 of 12 | 3 of 4 |
| CatBoost | 8 of 12 | 3 of 4 |
| Logistic | 8 of 12 | 2 of 4 |
| Prior finish | 6 of 12 | 0 of 4 |

On those sprints the pace model's mean Spearman (0.920) was below sprint qualifying order
(0.932). Without the venue-history features it was 0.931, and over all 17 folds 0.904 against
0.900 with them. For a sprint, the predicted order is close to the sprint qualifying order, and
the validation does not show that the model, with or without venue history, improves on it.

No model beat the Ridge pace ranking over all folds. Prior finish and CatBoost were clearly
worse; the rest are not distinguishable from it with 17 sessions, and four sprints is far too few
to rank models on sprints alone. The probabilities model only pace and retirement risk (no
strategy, safety cars or first-lap incidents), so treat them as rough. A grid penalty would
change the grid-based models; set `TARGET_GRID` and rerun.
