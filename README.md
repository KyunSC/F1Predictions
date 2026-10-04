# F1 Race Predictions

Predict relative race pace using qualifying performance and earlier races from the
same season. The notebook defaults to the **2026 Bahrain Grand Prix at Sepang,
Malaysia (October 4)**. Its main output is a pace ranking. A CatBoost finishing-order
ranker is also validated, and its order is shown only if it beats simple baselines.
A podium section compares nine models, including logistic, tree and Monte Carlo
probabilities, on the same walk-forward folds.

## Run

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/jupyter notebook f1_race_prediction.ipynb
```

Run the notebook from top to bottom. Timing data is downloaded through FastF1 and
cached under `cache/`; the first run can take several minutes.

The configuration defaults to:

```python
TARGET_RACE = (2026, "Bahrain Grand Prix")
```

The notebook resolves the exact event name from FastF1's schedule, then loads
sessions by round number. For this event it requires the October 4 race at
Sepang/Kuala Lumpur, rejecting an outdated Sakhir schedule. FastF1 may still label
the country as Bahrain; the physical location and race date identify the venue.

Training rounds are selected automatically by race start time, strictly before
the target. For this target that means rounds 1–15, through Azerbaijan. Missing
sessions are reported and skipped; at least four usable races are required.
Target qualifying must contain usable times. The target race session is never
loaded, including when the notebook is rerun after the race.
If qualifying results contain no times, the notebook retries with official timing
laps and race-control messages so FastF1 can reconstruct the classification.

## Model

Ridge regression (`alpha=10`) uses three pre-race features:

| Feature | Meaning |
|---|---|
| `QualiRatio` | Best lap across Q1/Q2/Q3 divided by the fastest qualifying lap |
| `QualifyingPosition` | Qualifying classification, before grid penalties |
| `PriorPace` | Driver's average pace ratio from strictly earlier races |

The target, `PaceRatio`, is a driver's median representative race lap divided by
the median of the drivers' race paces. Lower is faster. In/out laps and laps slower
than 107% of the driver's own median are removed. This is a simple outlier filter,
not a complete safety-car or weather classification.

Races are ordered by scheduled UTC race start before computing shifted expanding
means. Imputation and standardization are fitted only on each training fold.
Entrants without qualifying times or historical form remain in the prediction,
with missing inputs filled from training means and explicit flags in the output.
An entirely missing training feature is retained and filled with zero.

### Finishing-order ranker

`CatBoostRanker` with the `YetiRank` objective learns the official classification
directly, with retirements included. Each example is one driver in one race, and races
are the ranking groups. The label is higher for a better finish. Trees are shallow and
strongly regularised (`depth=3`, `l2_leaf_reg=10`, 300 iterations) because the pool is
small.

| Feature | Meaning |
|---|---|
| `QualiRatio`, `QualifyingPosition` | As above |
| `GridPosition` | Actual starting grid (pit-lane start = back of the field) |
| `PriorPace` | As above |
| `PriorFinish` | Mean classification over the driver's last three earlier races |
| `PriorNotClassifiedRate` | Share of earlier races not classified (retired or did not start) |

For the target race, the race session is never loaded, so `GridPosition` defaults to
qualifying position. Set `TARGET_GRID` (e.g. `{"VER": 20}`) once grid penalties are known.

### Podium comparison

Nine models are compared on podium prediction. Each gives one score per driver, and its
predicted podium is the top three by that score; probabilistic models are ranked by
P(podium). Settings were fixed in the configuration cell before any held-out result was
inspected and were not tuned on the held-out races.

| Model | Description |
|---|---|
| Grid order, qualifying order, prior finish | Orderings that need no model (`PriorFinish` = mean of the last three finishes) |
| Ridge pace | The pace model above, ranked within the race |
| CatBoost | The `YetiRank` finishing-order ranker above |
| Logistic | L2 logistic regression (`C=1`) for P(top 3) on the finishing-order features; imputation and scaling are fitted inside each fold |
| Shallow tree | `HistGradientBoostingClassifier` (`max_depth=3`, 100 iterations, `min_samples_leaf=20`) for P(top 3) |
| Simulation | 10,000 simulated runs per race. Ridge pace plus noise resampled from the fold's training residuals. Each driver retires with chance `(rate * n + 5 * field) / (n + 5)`, from their `PriorNotClassifiedRate` over `n` earlier races and the field's rate. Retirements are classified behind all finishers. Gives P(win), P(podium) and expected position |
| Grid-slot rate | Historical P(podium \| grid slot) from earlier races, Gaussian-kernel smoothed (bandwidth 1.5 slots, 2 pseudo-observations at the pooled rate) |

P(win) is reported for the simulation and grid-slot rate only: the logistic regression and
tree are trained on the top-3 label, and a win classifier would have about one positive per
race to learn from.

Training stays within 2026 for this prediction. Earlier seasons are excluded to
avoid assuming their competitive order carries across the regulation change.

## Validation

Walk-forward validation trains on at least four earlier usable races and scores
the next race. With exactly four usable races, prediction is available but there
is no validation fold; the notebook reports this explicitly.

Reported metrics include:

- Pace-ratio MAE for the model and a constant field-median baseline of 1.000.
- Qualifying-ratio baseline MAE and model MAE on the same rows with qualifying times.
- Per-race and mean Spearman correlations for model pace and qualifying order.

Previous README metrics were removed because the earlier implementation ordered
races alphabetically, invalidating its chronological validation claims. Use the
corrected notebook's executed results to assess performance; improvement over the
baselines is not assumed.

The verified run loaded all 15 earlier races and evaluated 11 held-out races
(238 driver-races):

| Metric | Model | Baseline |
|---|---:|---:|
| Pace MAE, all rows | 0.007003 | 0.013719 (field median) |
| Pace MAE, rows with qualifying times | 0.006891 | 0.021788 (qualifying ratio) |
| Mean per-race Spearman | 0.902341 | 0.894571 (qualifying order) |

The finishing-order ranker uses the same walk-forward folds. It is compared with grid order
and with the Ridge pace prediction ranked within each race, using position MAE, per-race
Spearman correlation and top-three overlap (share of the actual podium predicted in the
top three). It is adopted only if it beats both baselines on mean position MAE and mean
Spearman. Verified run, 11 held-out races (242 classified driver-races):

| Method | Position MAE | Spearman | Top-3 overlap |
|---|---:|---:|---:|
| CatBoost ranker | 3.826 | 0.630 | 0.424 |
| Grid order | 3.521 | 0.631 | 0.576 |
| Ridge pace ranking | **3.430** | **0.669** | **0.606** |

The ranker is **not adopted**. A small exploratory sweep (depth 2–3, fewer iterations,
`PairLogit`/`QuerySoftMax`, reduced feature sets, other seeds) did not change this. The best
variant only matched the Ridge ranking on MAE (3.438), and was selected on these same
held-out races. With 15 races the pace ranking remains the best available finishing order.
The check runs again on every execution, so the ranker is adopted automatically if it
starts winning as the season pool grows.

### Podium comparison results

Same 11 held-out races, scored on the same 242 driver-races (33 podium places). Podium
overlap is correct places out of three; winner and exact order are the share of races
where the predicted winner or the predicted top three in order was right. Brier score and
log loss are per-driver podium (yes/no) probabilities, averaged per race; probabilities are
clipped to [0.001, 0.999] for log loss.

| Model | Podium overlap | Winner correct | Exact order | Brier | Log loss | Overlap diff vs Ridge [95% CI] |
|---|---:|---:|---:|---:|---:|---|
| Grid order | 0.576 | 0.545 | 0.000 | | | -0.030 [-0.091, 0.000] |
| Qualifying order | 0.576 | 0.545 | 0.000 | | | -0.030 [-0.091, 0.000] |
| Prior finish | 0.364 | 0.364 | 0.000 | | | -0.242 [-0.424, -0.061] (worse) |
| Ridge pace | **0.606** | 0.455 | **0.091** | | | reference |
| CatBoost | 0.424 | 0.364 | 0.000 | | | -0.182 [-0.273, -0.091] (worse) |
| Logistic | **0.606** | 0.545 | 0.000 | 0.070 | 0.217 | 0.000 [-0.091, 0.091] |
| Shallow tree | 0.545 | 0.455 | 0.000 | 0.076 | 0.230 | -0.061 [-0.152, 0.000] |
| Simulation | 0.545 | 0.545 | 0.000 | 0.070 | **0.212** | -0.061 [-0.152, 0.000] |
| Grid-slot rate | 0.576 | 0.545 | 0.000 | 0.072 | 0.231 | -0.030 [-0.091, 0.000] |

Intervals are paired percentile bootstraps over the 11 races (10,000 resamples). A model
is called better only if its interval excludes zero.

**No model beats the Ridge pace ranking.** Ridge and the logistic regression tie on podium
overlap (20 of 33 places). Prior finish and CatBoost are clearly worse; the other six models
are not distinguishable from Ridge. Winner prediction (4 to 6 of 11 races) and exact podium
order (right once, by Ridge) do not separate the models. Among probabilities, Brier scores
are 0.070 to 0.076. Only the logistic regression has a log loss clearly better than the
grid-slot rate (-0.014 [-0.025, -0.004]); that is one of 30 intervals with no multiplicity
correction, so it is suggestive only. Calibration bins are coarse (6 to 44 driver-races).
Eleven races cannot separate models that differ by a place or two per race, and failing to
reject is not evidence of equality. The per-race hits, bootstrap table and calibration table
are in the notebook.

Predicted target podiums (top three, with P(podium) where available): Verstappen, Hamilton
and then Antonelli (Ridge pace, simulation, logistic), Hadjar (grid order, qualifying order,
grid-slot rate) or Leclerc (shallow tree). Prior finish (Antonelli, Verstappen, Russell) and
CatBoost (Hamilton, Verstappen, Leclerc) order the top differently. Simulated P(win):
Verstappen 0.29, Hamilton 0.21, Antonelli 0.17. These
probabilities come from 11 validation races and model only pace and retirement risk, so
treat them as rough.

The saved Bahrain pace prediction contains 22 entrants. Its top five on pace are
Max Verstappen, Lewis Hamilton, Kimi Antonelli, Isack Hadjar, and Charles Leclerc.

## Prediction output

The table includes pace rank, driver, team, qualifying position, predicted pace
ratio, and flags for missing qualifying time, qualifying position, or prior form.
Ties use driver abbreviation for deterministic ordering. No absolute lap-time
estimate is shown: another circuit's lap time is not a valid Sepang scale.

The podium section prints each model's predicted top three for the target, with P(podium)
where the model has one, and the simulation's P(win), P(podium) and expected position.

If the ranker passes validation, a second table lists predicted finishing position, grid slot
(flagged when taken from qualifying), recent finishing form and non-classification rate.

Weather, tyre strategy, fuel load, and incidents are not modelled; grid penalties and
retirements enter only through the ranker's features. Season-average form reacts slowly to upgrades. A strong pace ranking
can still differ substantially from the final race classification.

## Regression checks

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

Offline fixtures check date-based historical form, target/future exclusion,
relocated-venue validation, missing qualifying data and form, absence of validation
folds, and the restriction to qualifying when loading target features. The finishing-order
checks cover shifted finishing form and reliability, deterministic rank ties, and ranker
folds that train only on earlier races. The podium checks cover the logistic and tree folds
training only on earlier races, the simulation's residuals coming from earlier races only,
every model ignoring the held-out race's outcome columns, valid probabilities with P(win)
summing to 1 and P(podium) to 3 per simulated race, retirement shrinkage, grid-slot rates,
agreement with the finishing-order folds, bootstrap intervals, and the case with no
validation folds.

## Data source

[FastF1](https://github.com/theOehrly/Fast-F1) provides official F1 timing data.
This project is for educational and portfolio purposes.
