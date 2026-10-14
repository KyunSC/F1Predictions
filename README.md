# F1 Race Predictions

Predict relative race pace using qualifying performance and earlier races and sprints
from the same season. The notebook defaults to the **2026 Singapore Sprint at Marina
Bay (October 10)**; set `TARGET_KIND = "race"` to predict a Grand Prix instead. Its main
output is a pace ranking. A CatBoost finishing-order
ranker is also validated, and its order is shown only if it beats simple baselines.
A podium section compares 24 orderings and probability models (rankers, ratings,
classifiers, two race simulations and ensembles), a retirement section compares two
retirement models, and a pace section compares 16 pace models, all on the same
walk-forward folds.

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
TARGET_RACE = (2026, "Singapore Grand Prix")
TARGET_KIND = "sprint"   # or "race"
SESSION_CODES = {"race": ("Q", "R"), "sprint": ("SQ", "S")}
```

The notebook resolves the exact event name from FastF1's schedule, then loads
sessions by round number. `EXPECTED_VENUES` pins known targets to a location and the
UTC date of the scored session: the Singapore Sprint must be at Marina Bay on
October 10, and the relocated Bahrain GP at Sepang/Kuala Lumpur on October 4 (an
outdated Sakhir entry is rejected).

Training sessions are selected automatically: every 2026 Grand Prix **and** sprint
whose scored session starts strictly before the target, ordered by UTC start. For the
Singapore Sprint (09:00 UTC) that is all 16 earlier Grands Prix (rounds 1–16, through
the October 4 race at Sepang) and the 5 earlier sprints (China, Miami, Canada, British,
Dutch): 21 sessions. Sprint and GP rows can be pooled because every quantity is a ratio
within its own session. Each sprint is its own group (`RaceId` ends in `Sprint`), and a
weekend's sprint precedes its Grand Prix in the form features. No sprint flag is added
to the features. Missing sessions are reported and skipped; at least four usable
sessions are required.

For the target, only sprint qualifying (`SQ`) is loaded. The sprint itself, and the
weekend's later qualifying and Grand Prix, are never loaded, including when the notebook
is rerun afterwards. Target qualifying must contain usable times. If qualifying results
contain no times, the notebook retries with official timing laps and race-control
messages so FastF1 can reconstruct the classification. That fallback matters for
sprint qualifying, which the Ergast-compatible results service does not provide.

## Model

Ridge regression (`alpha=10`) uses five pre-race features:

| Feature | Meaning |
|---|---|
| `QualiRatio` | Best lap across Q1/Q2/Q3 (SQ1/SQ2/SQ3 for a sprint) divided by the fastest qualifying lap |
| `QualifyingPosition` | Qualifying classification, before grid penalties |
| `PriorPace` | Driver's average pace ratio from strictly earlier races and sprints |
| `VenuePace` | Driver's mean pace ratio at this circuit in 2023–2025 Grands Prix and sprints |
| `VenueQualiRatio` | Driver's mean qualifying ratio at this circuit in 2023–2025 qualifying |

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
| `VenuePace`, `VenueQualiRatio` | As above |

For the target, the scored session is never loaded, so `GridPosition` defaults to
the qualifying position (sprint qualifying for a sprint). Set `TARGET_GRID` (e.g. `{"VER": 20}`) once grid penalties are known.

### Podium comparison

Twenty-four models are compared on podium prediction. Each gives one score per driver, and its
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
| PairLogit | The CatBoost ranker with CatBoost's pairwise `PairLogit` objective, the objective behind XGBoost's `rank:pairwise` |
| Plackett-Luce | Linear model of the whole classification as successive choices (winner from the field, second from the rest, ...), L2 penalty 1. Retirements are never chosen but stay in every choice set. P(win) is exact; P(podium) is sampled from 10,000 orders |
| Bradley-Terry | Logistic regression (`C=1`, no intercept) on feature differences, one comparison per pair of drivers in a race (pairs of two retirements excluded) |
| Elo, Glicko-2, TrueSkill | Driver ratings updated race by race from earlier classifications only, each race a game against every other starter: multiplayer Elo (`K=32` shared across opponents), Glicko-2 (one rating period per race, `tau=0.5`) and TrueSkill (the `trueskill` package, no draws). No qualifying input |
| Ordinal logit | Cumulative-logit model of finishing position (statsmodels `OrderedModel`; positions past 20 pooled), giving P(win) and P(top 3) |
| Random forest | 300 trees, leaves of at least 5 rows, for P(top 3) |
| CatBoost classifier | Depth-3 CatBoost (300 iterations, `l2_leaf_reg=10`) for P(top 3) |
| MLP | One hidden layer of 16 units, `alpha=1`, for P(top 3) |
| Logistic + isotonic, Shallow tree + isotonic | The logistic and tree models recalibrated by isotonic regression on out-of-fold predictions from four race-grouped folds inside the training pool |
| Lap simulation | 2,000 lap-by-lap races (below) |
| Rank average | Mean rank over the 22 non-ensemble methods |
| Probability average | Mean P(podium) over the 12 other probabilistic models |

P(win) is reported for the two simulations, the grid-slot rate, Plackett-Luce and the ordinal
model. The other classifiers are trained on the top-3 label, and a win classifier would have
about one positive per race to learn from.

**Lap simulation.** Each run starts from the Ridge pace plus a residual resampled from the
fold's training residuals, as in the simulation above, and steps through the race lap by lap
in pace-ratio units (the field's median lap = 1). Each lap adds noise (0.004), tyre wear
(`DegPerLap` times tyre age) and, on a stop lap, the pit loss with fresh tyres. Stops fall
within 15% of race distance of an even split. Cars start 0.003 apart per grid slot. A car that
catches the one ahead passes only if it would be 0.005 clear; otherwise it is held 0.004
behind. A safety car starts on any lap with chance `SCPerLap` and bunches the field 0.01 apart
for 4 laps. Lap count, pit loss, stops per driver, wear and safety-car rate are medians over
earlier sessions of the same kind (sprint or Grand Prix), measured from those sessions' laps:
pit loss is the in-lap plus out-lap against twice the driver's green-flag median, wear is the
within-stint slope of lap time on tyre age (fuel burn included, so it can be negative), and
safety-car rate counts SC and VSC deployments per lap. Retirements come from the hazard model
and are classified last, by laps completed. These inputs are measured only for training
sessions; the target session is never loaded.

**Retirement models.** The simulation's shrunk rate counts a retirement per race. The hazard
model counts distance: a classified driver covers the session, a retirement the share of laps
it completed, and a sprint counts for a third of a Grand Prix. Each team's retirement rate per
Grand Prix distance is pulled toward the field's, and each driver's toward their team's, with
five Grand Prix distances of pseudo-exposure at each step; the rate is then scaled to the
session's distance. Both are scored on P(not classified) with the Brier score and log loss.

### Pace model comparison

Sixteen pace models are scored on the same folds and rows as the Ridge validation, which the
`Ridge` row reproduces exactly (the notebook checks this):

| Model | Description |
|---|---|
| Ridge | The pace model (`alpha=10`) |
| Lasso, ElasticNet | L1 and mixed penalties; strength (and ElasticNet's mix of 0.1, 0.5 or 0.9) chosen by four race-grouped folds inside the training pool |
| Bayesian ridge | Penalty and noise estimated from the data; gives an 80% predictive interval |
| Quantile | Linear median regression; the 10th and 90th percentile fits give the interval |
| Mixed effects | The same features plus random intercepts per driver and per team. Variances by REML (statsmodels `MixedLM`), then the fixed effects and shrunken driver and team effects from Henderson's mixed-model equations; unseen drivers and teams get zero |
| Ridge + EWM form | `PriorPace` replaced by an exponentially weighted mean of earlier pace ratios (half-life three sessions) |
| Ridge + Kalman form | `PriorPace` replaced by a one-step-ahead Kalman forecast: a local-level model with drift 0.002 per session, observation noise 0.006 and a prior of 1.000 ± 0.01 |
| Kalman form only | That forecast alone, with no qualifying input |
| Random forest | 300 trees, leaves of at least 5 rows |
| Gradient boosting | `HistGradientBoostingRegressor` with the shallow-tree settings |
| CatBoost | Depth-3 CatBoost regressor (300 iterations, `l2_leaf_reg=10`) |
| Gaussian process | RBF kernel with one length scale per feature plus a white-noise term, fitted by marginal likelihood; gives an 80% interval |
| MLP | One hidden layer of 16 units, `alpha=1`, standardised target |
| Mean of models | The mean of the fourteen models above |
| Stacked | Non-negative weights on Ridge, mixed effects, random forest, gradient boosting and the Gaussian process, fitted on out-of-fold predictions from four race-grouped folds inside the training pool |

Not included: sequence networks (LSTM, transformers) and a full Bayesian hierarchical model
(PyMC or Stan). With about 20 sessions per driver and a few hundred rows, a sequence network
has far more parameters than data, and the mixed-effects model already gives the partial
pooling a Bayesian hierarchy would. XGBoost and LightGBM need the OpenMP runtime on macOS
(`brew install libomp`), which this environment does not have; their tree boosting is covered
by the CatBoost and histogram-boosting models, and XGBoost's pairwise objective by `PairLogit`.
LambdaMART is missing. CatBoost's `LambdaMart` objective was in the first run and put none of
the 51 podium places in its top three. Checked on training data only, it did not fit its own
training races (training NDCG at the level of the reversed order), and the direction of the
order it learned flipped with CatBoost's leaf-estimation method. That is a fitting failure in
catboost 1.2.10, so it was removed rather than re-tuned on held-out results. LightGBM's
`lambdarank` would be the replacement once `libomp` is installed.

Training rows and targets stay within 2026, so the model does not assume that an
earlier season's competitive order carries across the regulation change. Earlier seasons
enter only through the two venue-history features. For every 2026 session, not just
Singapore, the notebook loads that circuit's 2023–2025 qualifying, Grands Prix and sprints
(`VENUE_HISTORY_SEASONS`). It then averages each driver's qualifying ratio and pace ratio
there. Circuits are matched by FastF1 location (with aliases for renamed locations such as
Miami Gardens/Miami), so the 2026 Barcelona race matches earlier Spanish Grands Prix and
Madrid and Sepang have no history. Because every training session gets the same features,
the walk-forward learns and scores how much circuit history is worth. Drivers without
history at a circuit get the fold's training mean. These numbers mostly reflect the car a
driver had in those seasons, so they are a weak signal about the driver at that circuit.
The first run downloads about 100 earlier-season sessions.

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

The verified run (October 10, 2026, Singapore Sprint target, venue history included)
loaded all 21 earlier scored sessions (16 Grands Prix, 5 sprints) and 96 earlier-season
venue-history sessions. 2025 Miami qualifying has no usable times in FastF1 and was skipped.
It evaluated 17 held-out sessions, 13 Grands Prix and 4 sprints (368 driver-sessions with
race pace):

| Metric | Model | Baseline |
|---|---:|---:|
| Pace MAE, all rows | 0.006858 | 0.013386 (field median) |
| Pace MAE, rows with qualifying times | 0.006777 | 0.022341 (qualifying ratio) |
| Mean per-session Spearman | 0.900344 | 0.898312 (qualifying order) |

The same scores on the 4 held-out sprints only (Miami, Canada, British, Dutch; 86 rows):

| Metric | Model | Baseline |
|---|---:|---:|
| Pace MAE, all rows | 0.004870 | 0.012234 (field median) |
| Pace MAE, rows with qualifying times | 0.004716 | 0.022647 (qualifying ratio) |
| Mean per-sprint Spearman | 0.920491 | 0.932005 (sprint qualifying order) |

Four sprints is a very small sample. On them the model is calibrated better than the
baselines but orders drivers no better than sprint qualifying does.

**Venue history did not help.** The notebook refits the pace model on the same folds without
`VenuePace` and `VenueQualiRatio`:

| Folds | Features | Pace MAE | Mean Spearman |
|---|---|---:|---:|
| All 17 | With venue history | 0.006858 | 0.900344 |
| All 17 | Without venue history | **0.006807** | **0.903830** |
| 4 sprints | With venue history | 0.004870 | 0.920491 |
| 4 sprints | Without venue history | **0.004755** | **0.931028** |

The differences are small and untested, but they all point the same way: 2023–2025 results at
a circuit add nothing measurable beyond 2026 qualifying and form. The features remain in the
configuration on request; `VENUE_FEATURES = []` removes them.

The finishing-order ranker uses the same walk-forward folds. It is compared with grid order
and with the Ridge pace prediction ranked within each session, using position MAE, per-session
Spearman correlation and top-three overlap (share of the actual podium predicted in the
top three). It is adopted only if it beats both baselines on mean position MAE and mean
Spearman, over all folds. Verified run, 17 held-out sessions (374 classified driver-sessions):

| Method | Position MAE | Spearman | Top-3 overlap | Sprints only: MAE | Spearman | Top-3 |
|---|---:|---:|---:|---:|---:|---:|
| CatBoost ranker | 3.289 | 0.706 | 0.569 | 2.227 | 0.869 | 0.667 |
| Grid order | **3.128** | 0.697 | 0.647 | **1.773** | **0.888** | **0.833** |
| Ridge pace ranking | 3.193 | **0.714** | **0.667** | 2.182 | 0.861 | **0.833** |

The ranker is **not adopted**. An earlier exploratory sweep (depth 2–3, fewer iterations,
`PairLogit`/`QuerySoftMax`, reduced feature sets, other seeds), run on the 15-race Bahrain
pool, did not change the decision there and was selected on those same held-out races. The
check runs again on every execution, so the ranker is adopted automatically if it starts
winning as the season pool grows.

### Podium comparison results

Same 17 held-out sessions, scored on the same 374 driver-sessions (51 podium places).
Podium overlap is correct places out of three; winner and exact order are the share of
sessions where the predicted winner or the predicted top three in order was right. Brier
score and log loss are per-driver podium (yes/no) probabilities, averaged per session;
probabilities are clipped to [0.001, 0.999] for log loss.

| Model | Podium overlap | Winner correct | Exact order | Brier | Log loss | Overlap diff vs Ridge [95% CI] |
|---|---:|---:|---:|---:|---:|---|
| Grid order | 0.647 | **0.647** | 0.000 | | | -0.020 [-0.059, 0.000] |
| Qualifying order | 0.627 | **0.647** | 0.000 | | | -0.039 [-0.098, 0.000] |
| Prior finish | 0.451 | 0.118 | 0.000 | | | -0.216 [-0.294, -0.137] (worse) |
| Ridge pace | 0.667 | **0.647** | 0.059 | | | reference |
| CatBoost | 0.569 | 0.471 | 0.000 | | | -0.098 [-0.196, -0.000] (worse) |
| Logistic | 0.627 | 0.588 | 0.000 | 0.067 | 0.214 | -0.039 [-0.118, 0.039] |
| Shallow tree | 0.588 | 0.529 | 0.059 | 0.078 | 0.238 | -0.078 [-0.157, 0.000] |
| Simulation | 0.647 | 0.529 | 0.059 | 0.066 | 0.201 | -0.020 [-0.059, 0.000] |
| Grid-slot rate | 0.647 | **0.647** | 0.000 | 0.066 | 0.212 | -0.020 [-0.059, 0.000] |
| PairLogit | 0.569 | 0.588 | 0.000 | | | -0.098 [-0.196, 0.020] |
| Plackett-Luce | 0.647 | 0.529 | 0.059 | 0.085 | 0.273 | -0.020 [-0.078, 0.039] |
| Bradley-Terry | 0.647 | **0.647** | 0.059 | | | -0.020 [-0.078, 0.039] |
| Elo | 0.451 | 0.235 | 0.000 | | | -0.216 [-0.353, -0.078] (worse) |
| Glicko-2 | 0.471 | 0.176 | 0.000 | | | -0.196 [-0.314, -0.078] (worse) |
| TrueSkill | 0.490 | 0.353 | 0.000 | | | -0.176 [-0.314, -0.039] (worse) |
| Ordinal logit | 0.647 | 0.588 | 0.000 | 0.069 | 0.220 | -0.020 [-0.059, 0.000] |
| Random forest | 0.647 | 0.471 | 0.059 | 0.067 | 0.201 | -0.020 [-0.078, 0.039] |
| CatBoost classifier | 0.647 | 0.529 | **0.118** | 0.074 | 0.242 | -0.020 [-0.118, 0.078] |
| MLP | 0.627 | 0.529 | 0.000 | 0.071 | 0.229 | -0.039 [-0.137, 0.059] |
| Logistic + isotonic | 0.627 | 0.588 | 0.000 | 0.071 | 0.250 | -0.039 [-0.137, 0.059] |
| Shallow tree + isotonic | 0.608 | 0.588 | 0.059 | 0.079 | 0.255 | -0.059 [-0.137, 0.020] |
| Lap simulation | 0.627 | 0.588 | 0.000 | **0.064** | **0.198** | -0.039 [-0.098, 0.000] |
| Rank average | 0.627 | **0.647** | **0.118** | | | -0.039 [-0.098, 0.000] |
| Probability average | **0.686** | **0.647** | 0.059 | 0.066 | 0.204 | +0.020 [-0.039, 0.098] |

Intervals are paired percentile bootstraps over the 17 sessions (10,000 resamples). A model
is called better only if its interval excludes zero.

**No model beats the Ridge pace ranking.** Ridge gets 34 of 51 podium places; the probability
average gets 35, within noise, and fourteen models get 32 or 33. Five are clearly worse: prior
finish, the CatBoost ranker, and the three rating systems (Elo, Glicko-2, TrueSkill), which use
only earlier finishing orders and no qualifying. Among probabilities, Brier scores run from
0.064 (lap simulation) to 0.085 (Plackett-Luce). Against the grid-slot rate, Plackett-Luce is
worse on Brier and log loss, and the ordinal model, the shallow tree and the recalibrated tree
are worse on Brier; no model is better. Plackett-Luce spreads probability too evenly (drivers
it gave 0.35–0.65 made the podium 68% of the time), and isotonic recalibration made the
logistic and tree probabilities worse rather than better. On the 4 held-out sprints (12
podium places), twelve models got 10 of 12 and none got more. The comparison draws 69
intervals against Ridge and 24 against the grid-slot rate with no multiplicity correction, and
seventeen sessions cannot separate models that differ by a place or two per session. The
per-session hits, bootstrap table and calibration table are in the notebook.

**Retirement models.** On P(not classified) per driver, the distance-based hazard model and
the shrunk per-race rate are indistinguishable: Brier 0.1285 vs 0.1281 (difference +0.0003
[-0.0069, +0.0068]), log loss 0.4215 vs 0.4242 (-0.0026 [-0.0267, +0.0179]). The actual
non-classification rate was 0.155 per driver; the two models predicted 0.192 and 0.178.

### Pace model comparison results

Same 17 held-out sessions and 368 driver-sessions as the pace validation. MAE is pooled over
rows; Spearman is the mean per session; differences from Ridge are per-session paired
bootstraps.

| Model | Pace MAE | Mean Spearman | 80% coverage | MAE diff vs Ridge [95% CI] | Spearman diff vs Ridge [95% CI] |
|---|---:|---:|---:|---|---|
| Ridge | 0.006858 | 0.900 | | reference | reference |
| Lasso | 0.006910 | 0.900 | | +0.000052 [-0.000096, 0.000194] | -0.000 [-0.004, 0.004] |
| ElasticNet | 0.006892 | 0.901 | | +0.000034 [-0.000117, 0.000181] | +0.001 [-0.002, 0.004] |
| Bayesian ridge | 0.006854 | 0.901 | 0.910 | -0.000004 [-0.000025, 0.000024] | +0.001 [-0.000, 0.003] |
| Quantile | **0.006627** | **0.902** | 0.747 | -0.000227 [-0.000359, -0.000103] (better) | +0.002 [-0.006, 0.008] |
| Mixed effects | 0.007025 | 0.890 | | +0.000172 [-0.000021, 0.000404] | -0.010 [-0.022, -0.002] (worse) |
| Ridge + EWM form | 0.006910 | 0.900 | | +0.000051 [-0.000029, 0.000142] | -0.000 [-0.003, 0.003] |
| Ridge + Kalman form | 0.006918 | 0.899 | | +0.000057 [-0.000096, 0.000233] | -0.001 [-0.005, 0.003] |
| Kalman form only | 0.007816 | 0.856 | | +0.000955 [0.000481, 0.001485] (worse) | -0.045 [-0.068, -0.023] (worse) |
| Random forest | 0.007084 | 0.900 | | +0.000225 [0.000025, 0.000426] (worse) | -0.000 [-0.011, 0.012] |
| Gradient boosting | 0.007021 | 0.894 | | +0.000160 [-0.000084, 0.000431] | -0.006 [-0.018, 0.003] |
| CatBoost | 0.007132 | 0.896 | | +0.000269 [-0.000037, 0.000642] | -0.005 [-0.014, 0.006] |
| Gaussian process | 0.006983 | 0.896 | 0.872 | +0.000119 [-0.000057, 0.000283] | -0.004 [-0.013, 0.003] |
| MLP | 0.007402 | 0.868 | | +0.000532 [-0.000022, 0.001287] | -0.033 [-0.091, -0.001] (worse) |
| Mean of models | 0.006661 | **0.902** | | -0.000198 [-0.000358, -0.000062] (better) | +0.001 [-0.002, 0.005] |
| Stacked | 0.006847 | 0.901 | | -0.000010 [-0.000122, 0.000116] | +0.000 [-0.008, 0.008] |

**Nothing orders drivers better than Ridge**; mixed effects, the MLP and the Kalman forecast
alone order them worse. Two models have a lower pace MAE with intervals that exclude zero, the
median (quantile) regression and the mean of models, both about 3% lower. The median regression
minimises absolute error, the metric scored, so its gain is partly the choice of loss. EWM and
Kalman form, which react faster to upgrades, changed nothing measurable. Partial pooling by
driver and team made ordering slightly worse, and the tree ensembles, Gaussian process and MLP
are no better and mostly worse on a pool this small. Nominal 80% intervals covered 91%
(Bayesian ridge), 87% (Gaussian process) and 75% (quantile) of actual pace ratios. On the 4
held-out sprints, the quantile model's mean Spearman (0.933) is level with sprint qualifying
order (0.932). The Ridge pace model stays the main prediction: the gains are small, and
adopting a model because it won this comparison would be selected on the same held-out
sessions.

Predicted Singapore Sprint podiums (top three, with P(podium) where available): Verstappen,
Russell, Leclerc from Ridge pace, grid order, qualifying order, Bradley-Terry, the rank
average and every probabilistic model except two. The lap simulation gives 0.72, 0.67 and
0.50 (P(win) 0.32, 0.26, 0.13); the plain simulation gives 0.60, 0.60 and 0.49 (P(win) 0.25,
0.24, 0.16). Plackett-Luce has the same three with Russell first (0.35, 0.32, 0.29). PairLogit
and the CatBoost classifier have Norris third, the CatBoost ranker has Piastri third, and prior
finish has Antonelli second. Elo, Glicko-2 and TrueSkill, which ignore
qualifying, put Antonelli first. These probabilities come from 17 validation sessions, 4 of
them sprints, so treat them as rough.

The saved Singapore Sprint pace prediction contains 22 entrants. Its top five on pace are
Max Verstappen, George Russell, Charles Leclerc, Oscar Piastri, and Lando Norris. A snapshot
is in `results/sprint_prediction_2026-10-10.md`; the earlier Bahrain run is in
`results/podium_prediction_2026-10-04.md`.

## Prediction output

The table includes pace rank, driver, team, qualifying position, predicted pace
ratio, and flags for missing qualifying time, qualifying position, or prior form.
Ties use driver abbreviation for deterministic ordering. No absolute lap-time
estimate is shown: another circuit's lap time is not a valid Marina Bay scale.

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
folds, and the restriction to qualifying when loading target features. The venue-history checks
cover renamed-location aliases, loading only earlier seasons at the requested circuits
(failures skipped, a target-season entry refused), and per-driver venue means that reject
history from the target season. The sprint checks
cover one schedule row per scored session (the target weekend's sprint, qualifying and
race excluded; ordering by UTC start; wrong venue or date rejected), a sprint target
loading only `SQ`, a sprint training session loading `SQ` and `S` under a `Sprint` group,
a weekend's sprint feeding its Grand Prix's `PriorPace` but not the reverse, and the
sprint-only filter. The finishing-order
checks cover shifted finishing form and reliability, deterministic rank ties, and ranker
folds that train only on earlier races. The podium checks cover the logistic and tree folds
training only on earlier races, the simulation's residuals coming from earlier races only,
every model ignoring the held-out race's outcome columns, valid probabilities with P(win)
summing to 1 and P(podium) to 3 per simulated race, retirement shrinkage, grid-slot rates,
agreement with the finishing-order folds, bootstrap intervals, and the case with no
validation folds. The model-comparison checks cover race conditions measured from laps
(and NaN when a column is missing, and for the target), Kalman and EWM form that never see
the session's own result, Plackett-Luce and Bradley-Terry learning a known order with valid
probabilities, ordinal probabilities, Elo, Glicko-2 and TrueSkill following results in date
order, Glickman's published volatility example, the hazard model's distance scaling and
team shrinkage, the retirement comparison, lap-simulation probabilities, retirements and
passing, race-grouped inner folds for calibration, the ensembles, every pace model ignoring
the held-out session's outcome, unseen drivers and teams in the mixed-effects model, and the
pace comparison reproducing the Ridge validation folds.

## Data source

[FastF1](https://github.com/theOehrly/Fast-F1) provides official F1 timing data.
This project is for educational and portfolio purposes.

## Local live dashboard

A separate Next.js (React/TypeScript) dashboard displays official timing alongside a fixed
notebook export. The dashboard never loads race data into the model or refits it.
Python 3.12 and Node 20.19+ are supported.

### One-command startup

From the repository root:

```bash
npm run dev
```

Open <http://127.0.0.1:5173>. This starts both services in one terminal; press
**Ctrl+C** to stop both. It sets up missing dependencies on first use (requires
Python 3.12 and Node.js 20.19+ installed). Later starts reuse the installation.
The dashboard opens in Historical (replay); use the **Historical / Live** toggle at
the top right to switch to live timing without restarting (`POST /api/mode`). Each
switch rebuilds the timing state, so replay position and live buffers start fresh,
and all open tabs follow it. No root-level `npm install` is needed; `npm run dev`
uses the same launcher as `./start.sh`.
Historical opens on the most recent archived Grand Prix race (see
[Recordings and controls](#recordings-and-controls)); **Change session** picks any
other archived session. Existing `F1_RECORDING` and
`F1_PREDICTIONS` environment variables still work. Stop any separately running
backend or frontend first; the launcher reports occupied ports without killing them.

### Separate services (optional)

From the repository root, start the backend (Historical plays the demo unless
`F1_RECORDING` is set; `npm run dev` sets it to the most recent race):

```bash
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn dashboard.app:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. Both services bind to localhost. Next.js rewrites
(`frontend/next.config.ts`) proxy the API and WebSockets to the backend. Run one backend process/worker so all browser tabs
share one upstream connection and one replay clock. No account or paid access is used.

To receive live timing, restart the backend with:

```bash
F1_MODE=live ./.venv/bin/uvicorn dashboard.app:app --host 127.0.0.1 --port 8000
```

The SignalR Core client follows the JSON subscription used by
[FastF1's live client](https://github.com/theOehrly/Fast-F1/blob/main/fastf1/livetiming/client.py).
It subscribes only to SessionInfo, SessionStatus, DriverList, TimingData,
TimingAppData, TrackStatus, WeatherData, RaceControlMessages, LapCount and Position.z.
CarData.z is excluded.

F1 streams Position.z only to F1TV Access/Pro subscribers, so live cars on the track
map need a subscription token. Sign in once with
`./.venv/bin/python -m fastf1 auth f1tv --authenticate` (FastF1 saves the token), or
set `F1TV_TOKEN`, then restart the backend. The token is sent as a bearer header and
is never recorded. Without a valid token, timing still works and the track map explains
why no cars are shown. Position.z contains actual Cartesian car
coordinates, not inferred race positions. A rejected position subscription reconnects
with the original timing topics; missing or malformed coordinates do not stop timing.
There is no paid fallback. The client reconnects with exponential
backoff capped at 30 seconds. Snapshots are sent no more than once per second per
browser. Disconnected data or updates over 15 seconds old are marked stale. Receipt
age and upstream timestamp age are separate; both are exposed by the API.

### Fixed predictions

A clean notebook run now ends with `export_predictions(target, TARGET_EVENT,
target_year)`, writing `dashboard/predictions.json` atomically. It includes the
session's year, physical venue, scheduled UTC date of the scored session, session name
(`Race` or `Sprint`), generation time, qualifying racing numbers, pace ranks, predicted
pace ratios and missing-feature flags. Racing numbers come from target qualifying (`SQ`
for a sprint); the target session is never loaded.
The backend reads this file once at startup. Restart it after a new export, or set
`F1_PREDICTIONS=/absolute/path/predictions.json`. Missing exports show an explanation.
Predictions are withheld for non-race sessions or mismatching year, venue, UTC date or
session name. The live feed reports a sprint as `Type: "Race"`, `Name: "Sprint"`, so a sprint
export is shown only during the sprint, not Sunday's Grand Prix. Exports without a name
(from before this field) match on year, venue and date only. Sepang and Kuala Lumpur are
recognized as the same venue. Drivers are
matched by racing number, never name. Pace rank is distinct from finishing position.

Each prediction row also shows where that car is running now against its pace rank
(`P3 ▲2`: running third, two places ahead of pace rank 5; `OUT` once retired). When a
replay reaches its end, a **How the prediction did** card compares the pace ranking with
the final classification: Spearman correlation and podium overlap over the drivers
classified in both, and whether the predicted fastest driver won. These are display
only; they never feed or refit the model, and one race says little about the model.

### If pitted now

The timing tower's **IF PIT** column answers "if this driver pitted now, where would they
rejoin?" It adds the circuit's pit loss to the driver's current time behind the leader and
re-ranks against every other running car, giving the projected race position (`P7 ▼3`
means three places lost). Hover the cell for the cars they would rejoin behind and ahead
of, with gaps. A driver in the pit lane shows `IN PIT`; retired drivers and cars without a
numeric gap or interval chain show `—`. Lapped cars use the car ahead's time plus their
interval. The projection is race order, not on-track traffic, and is shown only in races
(Grand Prix and sprint).

Pit loss comes from `dashboard/pit_loss.json`, measured separately for green-flag,
safety-car (SC) and virtual-safety-car (VSC) stops in past Grands Prix:

- **Green flag:** both the in-lap and the out-lap are fully green. The loss is in-lap
  plus out-lap minus twice the median of that driver's clean green-flag laps within
  five laps of the stop. Kept if 10–45 s.
- **SC:** both laps include safety-car running, with no red flag. **VSC:** the in-lap
  includes VSC, the out-lap VSC or VSC ending, with no SC or red flag. Under either,
  everyone laps slowly and a queue forms behind the safety car, so the driver's own green
  laps are no reference. The loss is instead the time from the start of the in-lap to
  the end of the out-lap, minus the median of the same two laps for the three
  non-pitting cars that were closest on track when the in-lap began. Kept if 5–35 s;
  a stop always costs some time against the pit-lane limit, and lower values come from
  races where nearly everyone pitted and the cars that stayed out were held in the queue. SC losses vary more from race to race than green or VSC ones,
  because the queue bunches differently each time.

All conditions drop lap-1 stops and stops whose lane time exceeds 1.5× the race's median
(penalties, repairs). A race keeps a condition only with at least three such stops, and
the table stores one median per race and condition. The dashboard picks the condition from
the live track status (SC for code 4, VSC for 6 and 7, green otherwise), then uses the
median of the circuit's race medians for that condition, from races that started strictly
before the session shown. A circuit with no history for that condition (the 2026 Bahrain GP
at Sepang, or the synthetic demo) falls back to the median across all circuits; if no
circuit has SC or VSC history, the green-flag loss is used and the footer says so. Under a
red flag pit stops are not projected. The footer names the value, its condition and its
basis. This is display only and never feeds the model.

Regenerate the table (uses the FastF1 `cache/`, downloading any missing race):

```bash
./.venv/bin/python -m dashboard.pit_loss --seasons 2023 2024 2025 2026
```

The backend reads it once at startup; restart after regenerating, or set
`F1_PIT_LOSS=/absolute/path/pit_loss.json`. Without the file the column shows `—` and the
footer explains why.

### Championship if positions hold

The **Championship if positions hold** panel shows the drivers' standings if every car
finished where it runs now. It comes straight from the feed's `ChampionshipPrediction`
topic, so F1 does the points, tie-breaks and penalties. The dashboard computes nothing.
Each row shows the projected position and points, the points gained in this session
(`+25`), and places gained or lost against the standings before the session (`▲1`). A
driver in the standings who is not entered in this session is listed by racing number.
It is shown only in races (Grand Prix and sprint). Recordings imported before this topic
was subscribed have no championship data and say so. Re-import them with
`dashboard.historical`, or delete the `dashboard/recordings/archive-*.jsonl` file and
load the session again from **Change session**. This is display only and never feeds the model.

### Timing tower and race control

The overall fastest best lap is highlighted in purple. The race-control panel colours
messages by importance: red for safety cars, red and chequered flags, and penalties;
amber for yellow and black-and-white flags, incidents, investigations and marshals on
track; everything else (blue flags, deleted lap times, track clear, steward decisions with
no further action) is routine. **Important only** hides the routine messages; that choice
is remembered in the browser. The browser tab title shows the lap, the leader and any
SC, VSC, yellow or red flag, e.g. `L23/62 · VER leads · SC · Pitwall`.

### Recordings and controls

Live mode writes received subscribed messages to ignored timestamped JSONL files
under `dashboard/recordings/live-*.jsonl`. Each line contains `at` (receipt Unix
seconds), `topic`, `data`, and optional upstream `timestamp`. Initial subscription
snapshots are recorded too. Replay sorts by receipt time (stable for ties), then
feeds the same reducer. Choose a local recording at backend startup:

```bash
F1_MODE=replay F1_RECORDING=dashboard/recordings/live-smoke.jsonl \
  ./.venv/bin/uvicorn dashboard.app:app --host 127.0.0.1 --port 8000
```

Without `F1_RECORDING`, `npm run dev` opens Historical on the most recent archived
Grand Prix **Race** (sprints are skipped; a race counts as archived an hour after it
ends, and in January the previous season's last race is used). It runs
`./.venv/bin/python -m dashboard.historical --latest-race`, which imports the race to
`dashboard/recordings/archive-<year>-<event>-<session>-<key>.jsonl` if it is missing,
reusing `cache/historical/` and downloading only what is missing. A race file is
about 30 MB and gitignored; the first import of a new race takes a while. The current
season's archive index is refetched on each start (falling back to the cached copy
offline); earlier seasons stay cached. If the import fails (e.g. offline on a fresh
clone), the launcher prints a warning and the backend falls back to the bundled
`demo.jsonl`, a two-minute, six-driver **Demo replay** with synthetic values.

**Change session** (in the replay bar, or beside the mode switch in Live) opens a
Year / Event / Session picker covering every session in F1's archive index from 2018
to the current season: practice, qualifying, sprint qualifying, sprints, races and
testing days. Sessions that ended less than an hour ago are disabled ("Not archived
yet"); ones already imported are marked "· downloaded" and load without a download.
**Load** imports the session if needed (progress shows in the panel), then replays
it for all tabs; loading from Live switches to Historical, and toggling Live and back
returns to the picked session. An import error leaves the current replay running. The
choice is not persisted across restarts. Predictions stay hidden on any session other
than the predicted one. Reconstructed archive recordings open at lights out (the
first `SessionStatus` `Started`) with all earlier timing already applied, and
Restart returns there. The progress bar stays on the recording clock; click or drag it
(or focus it and use the arrow keys) to jump to any point. A jump rebuilds the timing
state from the start of the recording up to that point, as Restart does. Keyboard
shortcuts: **Space** pauses or resumes, **R** restarts, **1**/**2**/**5** set the speed
(ignored while a control has focus). Pause/resume, restart, seek and 1×/2×/5× speed
controls apply to all connected tabs.
At the end, use Restart to play again. The browser picks archive sessions by
year and numeric session key only; it cannot select arbitrary filesystem paths.

- `GET /api/state`: session, drivers, matching predictions, messages, weather,
  track/lap status, connection freshness, replay state and `map_id`.
- `/ws`: pushes the same complete snapshot format once per second.
- `GET /api/track-map`: `session_identity`, `geometry_id`, availability/reason,
  coordinate system, ordered outline, bounds, rotation, attribution and provenance.
- `/ws/positions`: at most five snapshots per second, with `session_identity`, reset
  `generation`, increasing `sequence`, availability/reason, `presentation_clock`,
  connection/replay state, per-driver age and samples grouped by racing number.
  Samples retain x/y/z, upstream status, source UTC epoch seconds and presentation
  seconds (receipt time live; recording offsets during replay). Both WebSockets use
  the same localhost origin restrictions and one shared upstream connection.
- `POST /api/replay/control`: `{"action":"pause"}`, `{"action":"resume"}`,
  `{"action":"restart"}`, `{"action":"speed","speed":2}`, or
  `{"action":"seek","position":1800}` (recording seconds, clamped to the recording).
  Returns 409 in live mode.
- `GET /api/archive?year=2026`: `years` (2018 to the current year), `year`, and
  `events` in index order, each with `sessions` (`key`, `name`, `type`, `start_utc`,
  `available`, `cached`). 422 for an out-of-range year; 502 if the index can't be
  fetched and isn't cached.
- `POST /api/archive/load` `{"year":2026,"key":11731}`: 202 with the import job
  (`id`, `status`, `year`, `key`, `label`, `error`); 422 for an unknown or not yet
  archived session; 409 while another import runs. Progress and errors arrive in the
  snapshot's `archive` field.

### Dashboard verification

```bash
./.venv/bin/python -m unittest discover -s tests -v
(cd frontend && npm test && npm run build)
./.venv/bin/python -m dashboard.smoke --seconds 45
```

On October 4, 2026 at approximately 09:54 UTC, an unauthenticated active-session
smoke test completed negotiation and WebSocket subscription, received all nine
subscribed topics, and received 158 TimingData messages with 22 timing lines/drivers.
The provider identified the Bahrain GP at Kuala Lumpur, session 11731, as Started.
At the end of the 25-second test, receipt age was 0.28 seconds and the latest
upstream timing timestamp was about 2.36 seconds old. This verifies free reception
for that session; future upstream availability is not guaranteed. Run the smoke
command during a session to verify current access. The UI verifies the current
connection when timestamped timing arrives for a session marked Started.

### Track map behavior and verification

The SVG map sits above the timing tower. Click a marker or driver button, or focus
it and press Enter/Space, to select the same driver in both views. Marker colors
come from DriverList; labels fall back to racing numbers. A shared rotation and
Y-axis flip preserve aspect ratio and measured coordinates, including OffTrack
samples. OffTrack does not imply a pit-lane visit. Obvious coordinate-frame
mismatches show an unavailable reason; coordinates are never rescaled to fit.

Geometry comes from [MultiViewer](https://api.multiviewer.app), at
`/api/v1/circuits/{circuit_key}/{year}`. The backend uses a 10-second timeout and
validates circuit, response year, physical venue, finite outline and rotation.
Exact-year validated responses are cached in ignored `cache/track-maps/`. Event
names cannot select a circuit: Kuala Lumpur/Sepang metadata must not select Sakhir.
When MultiViewer answers **404** for the circuit (Sepang has no outline for any
year), the backend traces one from this session's own on-track coordinates instead:
each car's path is thinned to a point every 5 m, a lap is a 2–8 km stretch that
returns within 30 m of its start, and the median-length lap of at least three cars
becomes the outline, so a lap through the pit lane is not chosen. It is labelled
**Traced from {year} car coordinates**. Until three cars have lapped, the map says it
is tracing and the frontend asks again every 3 seconds. Another circuit or a
different venue's outline is never substituted, and any other incompatible or
failed response still shows **Track map unavailable**. No FastF1 race session is
loaded. Responses to obsolete session requests are discarded.

The independent position buffer retains ten seconds, at most 300 samples per driver,
plus a final held coordinate for stale/hide handling. Duplicate and late samples
are discarded. The decoder supports compressed initial snapshots and updates using
the [FastF1 documented source format](https://github.com/theOehrly/Fast-F1/blob/master/fastf1/_api.py)
without importing private APIs. Raw packets retain the existing JSONL format.
The display runs one presentation-second behind receipt time and interpolates only
between measured samples no more than two seconds apart. It never extrapolates.
Markers become stale after five seconds and disappear after fifteen. Reduced motion
holds actual samples without interpolation. Disconnect, pause and replay end freeze
the display; restart and seeking clear the buffers. The selected driver is remembered
in the browser (`localStorage`) across restarts, reloads and session changes, and is
highlighted only while that car is in the session. Replay speeds share the timing
clock and never reveal future recording events.

The bundled demo includes deterministic synthetic compressed coordinates and a
matching synthetic outline, clearly labeled and entirely offline. Older recordings
remain usable and show “No position data in this recording.”

On October 4, 2026 at approximately 10:19 UTC, the extended 20-second live smoke
check connected to session 11731 (Kuala Lumpur, circuit key 12), received 22 drivers
and 22 timing lines, and ended with timing source age 2.20 seconds. It received
**zero position samples**. MultiViewer `/api/v1/circuits/12/2026` returned 404.
A separate `/63/2026` probe returned Sakhir data labeled 2022; the implementation
rejects that year mismatch. Therefore live coordinate reception and marker alignment
remain **unverified**, while timing operated with positions unavailable. The smoke
command reports sample counts, driver coverage, source age and geometry availability.

Offline checks cover parsing, freshness, buffers, reconnect fallback, session resets,
geometry validation/cache/failures, WebSocket origins, replay and the synthetic demo.
Frontend tests cover interpolation, coordinate transforms, clocks, stale markers,
reduced motion and linked selection. Desktop and 400px mobile demo layouts were
visually inspected. During an accessible position feed, additionally verify actual
car-to-circuit alignment before relying on the map.

### Historical dashboard replay and diagnosis

Import raw Formula 1 archive streams (requires `curl`), independently of the
prediction notebook:

```bash
./.venv/bin/python -m dashboard.historical --year 2025 \
  --event 'Japanese Grand Prix' --session Race --output cache/suzuka-replay.jsonl
F1_MODE=replay F1_RECORDING=cache/suzuka-replay.jsonl \
  ./.venv/bin/uvicorn dashboard.app:app --host 127.0.0.1 --port 8000
./.venv/bin/python -m dashboard.diagnostics cache/suzuka-replay.jsonl \
  --geometry cache/track-maps/46-2025.json
```

`--latest-race` (no other flags needed) imports the most recent archived Grand Prix
race to `dashboard/recordings/` if missing and prints its path as JSON; `npm run dev`
uses it at startup.

Open the frontend normally. Geometry is cached after the map is first opened;
omit `--geometry` for a coordinates-only offline report. Event and session names
must match the archive index exactly (case insensitive). Downloads are cached in
`cache/historical/`; keep output recordings under ignored `cache/` as well.
Missing HTTP streams are reported; SessionInfo is required. No alternate circuit
or year is substituted. The importer preserves raw compressed Position.z payloads
and uses the archive's common elapsed-time prefixes for **all** topics, following
[FastF1's archive framing implementation](https://github.com/theOehrly/Fast-F1/blob/master/fastf1/_api.py).
Replay passes them through the same decoder and reducer as live mode.

The label **Reconstructed archive replay** distinguishes archive time from live
receipt time: network delays cannot be recovered. Additive `reconstructed` and
`provenance` fields leave existing JSONL recordings compatible. Coordinates use
one source-to-presentation clock offset per session/reconnect, anchored to the
latest sample in the first valid packet. Later delivery delays do not shift old
samples forward. That initial offset is an estimate, not proof of exact live
synchronization. The map retains its one-second interpolation buffer; the timing
tower is updated independently once per second. Physical track order need not
match official race position, especially for lapped cars and pit stops.

The map's expandable diagnostics and `/ws/positions` now report packet/sample
counts, racing-number coverage, missing drivers, rejected entries by reason, and
gaps over five seconds. The offline command also validates geometry metadata and
reports the fraction of on-track samples inside its bounds. Bounds are a coarse
compatibility check, not a proof of exact survey alignment. Malformed driver
entries are isolated; other drivers and timing updates continue normally.

Verification on October 4, 2026:

- The affected October 4 race at Kuala Lumpur (session 11731) has **15,018 archived
  Position.z packets**, with 57,287 decoded samples for each of 22 racing numbers,
  plus IDs 241/242/243. The two local live recordings still contain zero coordinate
  packets. This establishes archive availability, not live subscription delivery.
  Its exact MultiViewer geometry endpoint `/12/2026` returned 404 (as do `/12/2025`
  and `/12/2017`). With the traced fallback, by lights out all 22 cars have closed a
  pre-race lap of 5.54–5.60 km. The median lap gives a 479-point outline, and the
  Historical map shows all 22 cars on it.
- Searching backward through the 2026 and 2025 archive indexes found the newest
  exact-year geometry at **Suzuka, April 6, 2025**, circuit 46. Recent endpoints
  often returned older geometry (for example `/144/2026` returned year 2022);
  strict validation rejected these responses rather than using them.
- The complete Suzuka replay processed **8,266 coordinate packets and 640,980
  samples across all 20 drivers**, with no rejected samples or gaps over five
  seconds (maximum gap 3.260s). All 640,980 on-track samples were within the
  matching geometry bounds plus the existing 10% margin.
- Chrome desktop and 400px responsive inspection used a reconstructed excerpt
  of normalized replay seconds **3598–3630**, ending on lap 3. All 20 markers
  were present on matching geometry. Selecting Hamilton also selected his timing
  row and displayed official **P8**, without changing his measured coordinates.
  Closely grouped labels overlap, particularly on mobile; keyboard/tower
  selection remains available. This verifies general historical rendering, not
  the exact reported Sepang failure.
- Failing regression cases reproduced per-packet clock shifting (a sample at
  source +1s arriving at replay 13s incorrectly appeared at 13s instead of 11s)
  and a malformed driver's entry dropping other valid cars. Both are fixed.
  Synthetic overtake/lapped-car tests preserve coordinates while official
  standings change. No historical overtake is claimed from the inspected excerpt.

The small attributed fixture in `tests/fixtures/` contains three original
compressed packets and explicitly reconstructed starting snapshots. Full archive
downloads and geometry probes remain outside Git. Prediction training, notebook
outputs and reported model metrics are unchanged by this work.
