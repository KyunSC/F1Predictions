# Prediction scorecard

Written by `score_predictions.py` from the snapshots in this folder and the actual classifications in `actual/`; rerun it after adding a snapshot. A hit is a predicted podium driver who finished on the podium, in any order. "Exact" counts the places called in the right position.

## Best single answer

| Session | Predicted | Actual podium | Podium places | Exact | Winner |
|---|---|---|---:|---:|---|
| 2026 Bahrain Grand Prix | VER, HAM, ANT | VER, ANT, HAM | 3 of 3 | 1 of 3 | yes |
| 2026 Singapore Sprint | VER, RUS, LEC | VER, HAM, LEC | 2 of 3 | 2 of 3 | yes |

## By model, over 2 sessions

| Model | Podium places | Exact | Winners |
|---|---:|---:|---:|
| Grid order | 4 of 6 | 3 of 6 | 2 of 2 |
| Qualifying order | 4 of 6 | 3 of 6 | 2 of 2 |
| Prior finish | 4 of 6 | 2 of 6 | 1 of 2 |
| Ridge pace | 5 of 6 | 3 of 6 | 2 of 2 |
| CatBoost | 3 of 6 | 1 of 6 | 1 of 2 |
| Logistic | 5 of 6 | 3 of 6 | 2 of 2 |
| Shallow tree | 4 of 6 | 3 of 6 | 2 of 2 |
| Simulation | 5 of 6 | 3 of 6 | 2 of 2 |
| Grid-slot rate | 4 of 6 | 3 of 6 | 2 of 2 |

## 2026 Bahrain Grand Prix (Sepang, 2026-10-04)

Prediction: [`podium_prediction_2026-10-04.md`](podium_prediction_2026-10-04.md). Actual podium: **VER, ANT, HAM**. Result from https://www.formula1.com/en/results/2026/races/1308/bahrain/race-result, retrieved 2026-10-17.

| Model | Predicted | Hits | Misses (actual finish) | Podium places | Exact | Winner |
|---|---|---|---|---:|---:|---|
| Best single answer | VER, HAM, ANT | VER, HAM, ANT | – | 3 | 1 | yes |
| Grid order | VER, HAM, HAD | VER, HAM | HAD P5 | 2 | 1 | yes |
| Qualifying order | VER, HAM, HAD | VER, HAM | HAD P5 | 2 | 1 | yes |
| Prior finish | ANT, VER, RUS | ANT, VER | RUS P20 (DNF) | 2 | 0 | no |
| Ridge pace | VER, HAM, ANT | VER, HAM, ANT | – | 3 | 1 | yes |
| CatBoost | HAM, VER, LEC | HAM, VER | LEC P4 | 2 | 0 | no |
| Logistic | VER, HAM, ANT | VER, HAM, ANT | – | 3 | 1 | yes |
| Shallow tree | VER, HAM, LEC | VER, HAM | LEC P4 | 2 | 1 | yes |
| Simulation | VER, HAM, ANT | VER, HAM, ANT | – | 3 | 1 | yes |
| Grid-slot rate | VER, HAM, HAD | VER, HAM | HAD P5 | 2 | 1 | yes |

## 2026 Singapore Sprint (Marina Bay, 2026-10-10)

Prediction: [`sprint_prediction_2026-10-10.md`](sprint_prediction_2026-10-10.md). Actual podium: **VER, HAM, LEC**. Result from https://www.formula1.com/en/results/2026/races/1296/singapore/sprint-results, retrieved 2026-10-17.

| Model | Predicted | Hits | Misses (actual finish) | Podium places | Exact | Winner |
|---|---|---|---|---:|---:|---|
| Best single answer | VER, RUS, LEC | VER, LEC | RUS DNF | 2 | 2 | yes |
| Grid order | VER, RUS, LEC | VER, LEC | RUS DNF | 2 | 2 | yes |
| Qualifying order | VER, RUS, LEC | VER, LEC | RUS DNF | 2 | 2 | yes |
| Prior finish | VER, ANT, LEC | VER, LEC | ANT P4 | 2 | 2 | yes |
| Ridge pace | VER, RUS, LEC | VER, LEC | RUS DNF | 2 | 2 | yes |
| CatBoost | VER, RUS, PIA | VER | RUS DNF, PIA P14 (DNF) | 1 | 1 | yes |
| Logistic | VER, RUS, LEC | VER, LEC | RUS DNF | 2 | 2 | yes |
| Shallow tree | VER, RUS, LEC | VER, LEC | RUS DNF | 2 | 2 | yes |
| Simulation | VER, RUS, LEC | VER, LEC | RUS DNF | 2 | 2 | yes |
| Grid-slot rate | VER, RUS, LEC | VER, LEC | RUS DNF | 2 | 2 | yes |
