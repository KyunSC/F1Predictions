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

## Local live dashboard

A separate React/TypeScript dashboard displays official timing alongside a fixed
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
For live timing, use `npm run dev:live`. No root-level `npm install` is needed;
these commands use the same launcher as `./start.sh` and `./start.sh --live`.
Existing `F1_RECORDING` and
`F1_PREDICTIONS` environment variables still work. Stop any separately running
backend or frontend first; the launcher reports occupied ports without killing them.

### Separate services (optional)

From the repository root, start the backend (demo replay is the default):

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

Open <http://127.0.0.1:5173>. Both services bind to localhost. Vite proxies the API
and WebSocket to the backend. Run one backend process/worker so all browser tabs
share one upstream connection and one replay clock. No account or paid access is used.

To receive live timing, restart the backend with:

```bash
F1_MODE=live ./.venv/bin/uvicorn dashboard.app:app --host 127.0.0.1 --port 8000
```

The unauthenticated SignalR Core client follows the JSON subscription used by
[FastF1's live client](https://github.com/theOehrly/Fast-F1/blob/main/fastf1/livetiming/client.py).
It subscribes only to SessionInfo, SessionStatus, DriverList, TimingData,
TimingAppData, TrackStatus, WeatherData, RaceControlMessages, LapCount and Position.z.
CarData.z and credentials are excluded. Position.z contains actual Cartesian car
coordinates, not inferred race positions. A rejected position subscription reconnects
with the original timing topics; missing or malformed coordinates do not stop timing.
There is no paid fallback. The client reconnects with exponential
backoff capped at 30 seconds. Snapshots are sent no more than once per second per
browser. Disconnected data or updates over 15 seconds old are marked stale. Receipt
age and upstream timestamp age are separate; both are exposed by the API.

### Fixed predictions

A clean notebook run now ends with `export_predictions(target, TARGET_EVENT,
target_year)`, writing `dashboard/predictions.json` atomically. It includes the
session's year, physical venue, scheduled UTC race date, generation time, qualifying
racing numbers, pace ranks, predicted pace ratios and missing-feature flags.
Racing numbers come from target qualifying; the target race is never loaded.
The backend reads this file once at startup. Restart it after a new export, or set
`F1_PREDICTIONS=/absolute/path/predictions.json`. Missing exports show an explanation.
Predictions are withheld for non-race sessions or mismatching year, venue, or UTC
race date; Sepang and Kuala Lumpur are recognized as the same venue. Drivers are
matched by racing number, never name. Pace rank is distinct from finishing position.
The notebook outputs were cleared after this edit; existing README model metrics
were not changed, and no new model results are claimed.

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

The included `demo.jsonl` is a two-minute, six-driver **Demo replay** with synthetic
values. Pause/resume, restart and 1×/2×/5× speed controls apply to all connected tabs.
At the end, use Restart to play again. Recordings are selected only at startup;
the browser cannot select arbitrary filesystem paths.

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
  `{"action":"restart"}`, or `{"action":"speed","speed":2}`. Returns 409 in live mode.

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

Geometry comes only from [MultiViewer](https://api.multiviewer.app), at
`/api/v1/circuits/{circuit_key}/{year}`. The backend uses a 10-second timeout and
validates circuit, response year, physical venue, finite outline and rotation.
Exact-year validated responses are cached in ignored `cache/track-maps/`. Event
names cannot select a circuit: Kuala Lumpur/Sepang metadata must not select Sakhir.
A missing or incompatible response shows **Track map unavailable**. No FastF1 race
session is loaded. Responses to obsolete session requests are discarded.

The independent position buffer retains ten seconds, at most 300 samples per driver,
plus a final held coordinate for stale/hide handling. Duplicate and late samples
are discarded. The decoder supports compressed initial snapshots and updates using
the [FastF1 documented source format](https://github.com/theOehrly/Fast-F1/blob/master/fastf1/_api.py)
without importing private APIs. Raw packets retain the existing JSONL format.
The display runs one presentation-second behind receipt time and interpolates only
between measured samples no more than two seconds apart. It never extrapolates.
Markers become stale after five seconds and disappear after fifteen. Reduced motion
holds actual samples without interpolation. Disconnect, pause and replay end freeze
the display; restart clears selection and buffers. Replay speeds share the timing
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
  Its exact MultiViewer geometry endpoint `/12/2026` returned 404, so the original
  race's complete map behavior remains unverified.
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
