# F1 Race Predictions

Predicts Formula 1 race pace and finishing order for a target Grand Prix using only
information available **before the race starts** — qualifying performance and each
driver's form in earlier races.

## Overview

Given a target Grand Prix, the model estimates each driver's *relative race pace* and
ranks the grid. It is trained on a pool of past races, validated by walking forward
through the season, and scored against naive baselines so the reported error is
interpretable rather than decorative.

## Approach

| Step | What happens |
|---|---|
| 1. Extract | For each training race: qualifying pace, and the resulting race pace |
| 2. Normalise | Lap times become *ratios* (vs. pole, vs. field median) so different circuits pool together |
| 3. Engineer | Prior-form feature built from strictly earlier races via a shifted expanding mean |
| 4. Train | `HistGradientBoostingRegressor` on pre-race features only |
| 5. Validate | Walk-forward: train on races before race *k*, score on race *k* |
| 6. Compare | Reported against a field-median baseline and a qualifying-only baseline |

### Why ratios instead of raw lap times

A lap at Monza (~80 s) and a lap at Singapore (~95 s) are not comparable, so pooling raw
lap times across circuits is meaningless. Every quantity is normalised within its own
session:

- `QualiRatio` = driver's best qualifying lap / pole time — 1.000 is pole
- `PaceRatio` = driver's median race lap / field median lap — 1.000 is an average car

`PaceRatio` is the prediction target. Lower is faster.

### Features

All three are strictly pre-race:

- `QualiRatio` — one-lap pace relative to pole
- `GridPosition` — starting position
- `PriorPace` — mean `PaceRatio` across that driver's **earlier** races only

Race laps are filtered before the target is computed: in- and out-laps are dropped
(they include the pit lane), and laps slower than 107% of a driver's own median are
discarded as safety-car, traffic, or damage laps rather than representative pace.

## Tech Stack

- **Python 3.12**
- **Machine Learning**: scikit-learn
- **Data Processing**: pandas, numpy
- **F1 Data**: FastF1 API
- **Environment**: Jupyter Notebook

## Usage

```bash
pip install -r requirements.txt
jupyter notebook f1_race_prediction.ipynb
```

To predict a different race, edit `TARGET_RACE` in the configuration cell:

```python
TARGET_RACE = (2025, "Abu Dhabi Grand Prix")
```

`TRAINING_RACES` controls the pool the model learns from. More races give a better model
but a slower first run — each session is a few MB of timing data, cached under `cache/`
for subsequent runs.

## Interpreting the output

The notebook prints model MAE alongside two baselines. **A model that does not beat both
baselines has not learned anything** — that comparison is the point, not the raw MAE.
Mean per-race Spearman correlation is usually the more meaningful number, since the
practical question is finishing *order* rather than exact lap time.

## Limitations

- **Pace is not position.** The model predicts representative lap pace. Strategy,
  pit-stop timing, safety cars, and first-lap incidents routinely override raw pace.
- **Small training pool.** A dozen races is only a few hundred rows.
- **No weather, tyre, or fuel modelling.** Median lap time blends stint phases and
  compounds together.
- **Regulation changes.** Pooling seasons assumes the competitive order is broadly
  comparable across them, which is weakest across a rules reset.
- **Prior form is an average**, so it reacts slowly to mid-season upgrades.

## Data Source

Race data provided by the [FastF1 Python library](https://github.com/theOehrly/Fast-F1),
which accesses the official F1 live timing data.

## License

This project is for educational and portfolio purposes.

---

**Note**: Predictions are based on historical data and should not be used for betting or
gambling purposes.
