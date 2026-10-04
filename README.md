# F1 Race Predictions

Predict relative race pace using qualifying performance and earlier races from the
same season. The notebook defaults to the **2026 Bahrain Grand Prix at Sepang,
Malaysia (October 4)**. Its output is a pace ranking, not a forecast of finishing
positions or win probabilities.

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

The saved Bahrain prediction contains 22 entrants. Its top five on pace are
Max Verstappen, Lewis Hamilton, Kimi Antonelli, Isack Hadjar, and Charles Leclerc.
These are pace estimates, not calibrated finishing probabilities.

## Prediction output

The table includes pace rank, driver, team, qualifying position, predicted pace
ratio, and flags for missing qualifying time, qualifying position, or prior form.
Ties use driver abbreviation for deterministic ordering. No absolute lap-time
estimate is shown: another circuit's lap time is not a valid Sepang scale.

Weather, tyre strategy, fuel load, grid penalties, incidents, and retirements are
not modelled. Season-average form reacts slowly to upgrades. A strong pace ranking
can still differ substantially from the final race classification.

## Regression checks

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

Offline fixtures check date-based historical form, target/future exclusion,
relocated-venue validation, missing qualifying data and form, absence of validation
folds, and the restriction to qualifying when loading target features.

## Data source

[FastF1](https://github.com/theOehrly/Fast-F1) provides official F1 timing data.
This project is for educational and portfolio purposes.
