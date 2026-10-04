# Podium prediction: 2026 Bahrain Grand Prix (Sepang, Oct 4)

Snapshot of the executed `f1_race_prediction.ipynb` run on 2026-10-04. Trained on the 15
earlier 2026 races; only target qualifying was loaded. Grid = qualifying position (no
`TARGET_GRID` overrides). Rerunning the notebook overwrites its outputs, so this file is the
record of this run.

## Best single answer

**1. Verstappen, 2. Hamilton, 3. Antonelli** (Ridge pace ranking, simulation and logistic
regression agree). Third place is open: Hadjar and Leclerc are plausible.

## Predicted podium by model

Brackets are P(podium) where the model gives one.

| Model | 1st | 2nd | 3rd |
|---|---|---|---|
| Grid order | VER | HAM | HAD |
| Qualifying order | VER | HAM | HAD |
| Prior finish | ANT | VER | RUS |
| Ridge pace | VER | HAM | ANT |
| CatBoost | HAM | VER | LEC |
| Logistic | VER (0.67) | HAM (0.63) | ANT (0.36) |
| Shallow tree | VER (0.86) | HAM (0.60) | LEC (0.52) |
| Simulation | VER (0.60) | HAM (0.57) | ANT (0.53) |
| Grid-slot rate | VER (0.62) | HAM (0.56) | HAD (0.49) |

## Simulation and grid-slot probabilities (top eight by simulated P(podium))

| Driver | Sim P(win) | Sim P(podium) | Sim expected position | Grid-slot P(win) | Grid-slot P(podium) |
|---|---:|---:|---:|---:|---:|
| Max Verstappen | 0.291 | 0.604 | 5.74 | 0.353 | 0.618 |
| Lewis Hamilton | 0.210 | 0.569 | 4.83 | 0.243 | 0.563 |
| Kimi Antonelli | 0.173 | 0.532 | 4.45 | 0.053 | 0.403 |
| Isack Hadjar | 0.099 | 0.350 | 6.82 | 0.133 | 0.491 |
| Charles Leclerc | 0.076 | 0.303 | 6.77 | 0.016 | 0.296 |
| Lando Norris | 0.050 | 0.207 | 8.53 | 0.004 | 0.194 |
| Oscar Piastri | 0.039 | 0.177 | 8.17 | 0.002 | 0.119 |
| George Russell | 0.034 | 0.160 | 7.78 | 0.002 | 0.070 |

## How much to trust it

Walk-forward validation on 11 held-out races (33 podium places), mean per race:

| Model | Podium overlap | Winner correct | Brier | Log loss | Overlap vs Ridge [95% CI] |
|---|---:|---:|---:|---:|---|
| Ridge pace | 0.606 | 0.455 | | | reference |
| Logistic | 0.606 | 0.545 | 0.070 | 0.217 | 0.000 [-0.091, 0.091] |
| Grid / qualifying order | 0.576 | 0.545 | | | -0.030 [-0.091, 0.000] |
| Grid-slot rate | 0.576 | 0.545 | 0.072 | 0.231 | -0.030 [-0.091, 0.000] |
| Shallow tree | 0.545 | 0.455 | 0.076 | 0.230 | -0.061 [-0.152, 0.000] |
| Simulation | 0.545 | 0.545 | 0.070 | 0.212 | -0.061 [-0.152, 0.000] |
| CatBoost | 0.424 | 0.364 | | | -0.182 [-0.273, -0.091] (worse) |
| Prior finish | 0.364 | 0.364 | | | -0.242 [-0.424, -0.061] (worse) |

No model beat the Ridge pace ranking. Only CatBoost and prior finish were clearly worse; the
rest are not distinguishable from it with 11 races. The probabilities model only pace and
retirement risk (no strategy, safety cars or first-lap incidents), so treat them as rough.
A grid penalty would change the grid-based models; set `TARGET_GRID` and rerun.
