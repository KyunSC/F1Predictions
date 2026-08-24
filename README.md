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
| 4. Train | Ridge regression on pre-race features only |
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

### Why a linear model

With roughly 230 rows and three weakly-correlated features, a gradient-boosted tree
overfits. Measured walk-forward over the 2026 season, `HistGradientBoostingRegressor`
scores MAE 0.0060 against Ridge's 0.0057, and produces coarse leaf values that assign
identical predictions to unrelated drivers. The regularisation strength is insensitive
(alpha of 1, 10 and 50 all land within 0.0002), so it is not tuned to the metric.

## Results

Walk-forward over the 2026 season to date — 7 held-out races, 147 driver-races:

| | MAE (pace ratio) | ~seconds/lap |
|---|---|---|
| **Model** (quali + grid + form) | **0.0051** | **0.46** |
| Baseline: field median | 0.0117 | 1.05 |
| Baseline: qualifying ratio | 0.0211 | 1.90 |

Mean per-race Spearman rank correlation: **0.916**.

Held out a single race entirely (2026 Hungarian GP, excluded from training) as an
end-to-end check: MAE 0.0039 against a 0.0130 field-median baseline, Spearman 0.948,
with the predicted top eight matching the actual top eight on pace.

One honest caveat: the model's *ranking* is barely better than sorting by qualifying
time (Spearman 0.935 vs 0.934 on the 2026 pool). What it adds over qualifying is
calibrated *magnitude* — how large the pace gaps are — which is where the 4x MAE
improvement comes from.

## Tech Stack

- **Python 3.12**
- **Machine Learning**: scikit-learn
- **Data Processing**: pandas, numpy
- **F1 Data**: FastF1 API
- **Environment**: Jupyter Notebook

## Usage

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/jupyter notebook f1_race_prediction.ipynb
```

The first run downloads timing data for every configured race and takes a few minutes;
subsequent runs are served from `cache/`.

To predict a different race, edit `TARGET_RACE` in the configuration cell:

```python
TARGET_RACE = (2026, "Dutch Grand Prix")
```

`TRAINING_RACES` controls the pool the model learns from. More races give a better model
but a slower first run — each session is a few MB of timing data, cached under `cache/`
for subsequent runs.

It currently holds the completed 2026 races only. The 2026 regulation reset changed the
car order outright, so earlier seasons are not a usable prior — adding them teaches the
model a hierarchy that no longer exists. This is measurable, not theoretical: trained on
a pooled 2023/2024 set, the model scores MAE 0.0134 against a 0.0096 field-median
baseline — worse than predicting that every driver is average. Extend the list as the
season goes on; append each new race once its Sunday timing data is published.

A prediction needs the target's **qualifying session to have run**. Before then the
notebook says so and stops at that cell; the validation section above it still runs.

Event names are not stable between seasons — take them from
`fastf1.get_event_schedule(2026)` rather than copying an earlier season's list. In 2026
`"Spanish Grand Prix"` is Madrid, and Barcelona races under `"Barcelona Grand Prix"`.

## Interpreting the output

The notebook prints model MAE alongside two baselines. **A model that does not beat both
baselines has not learned anything** — that comparison is the point, not the raw MAE.
Mean per-race Spearman correlation is usually the more meaningful number, since the
practical question is finishing *order* rather than exact lap time.

## Limitations

- **Pace is not position.** The model predicts representative lap pace. Strategy,
  pit-stop timing, safety cars, and first-lap incidents routinely override raw pace.
- **Small pool, and it cannot be widened.** The 2026 regulation reset rules out earlier
  seasons as a prior, so the pool is capped at the races run so far this season — a few
  hundred rows, growing one race at a time.
- **No weather, tyre, or fuel modelling.** Median lap time blends stint phases and
  compounds together.
- **Early rounds are weakest.** `PriorPace` is missing for the whole grid at round 1 and
  thin for several rounds after, so the model leans almost entirely on qualifying until
  the pool fills out.
- **Prior form is an average**, so it reacts slowly to mid-season upgrades.

## Data Source

Race data provided by the [FastF1 Python library](https://github.com/theOehrly/Fast-F1),
which accesses the official F1 live timing data.

## License

This project is for educational and portfolio purposes.

---

**Note**: Predictions are based on historical data and should not be used for betting or
gambling purposes.
