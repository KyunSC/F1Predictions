# AGENTS.md

Guidance for AI coding agents working in this repository. `CLAUDE.md` is a symlink to
this file; edit `AGENTS.md` only.

## Project

Predicts relative race pace for a target F1 Grand Prix from qualifying performance and
earlier races in the same season. The main output is a pace ranking, which is distinct
from finishing position; the notebook also validates a finishing-order ranker and
compares podium models. Model logic lives in `f1_race_prediction.ipynb`. A separate
local dashboard (`dashboard/` FastAPI backend, `frontend/` React/TypeScript) shows live
timing next to the notebook's exported `dashboard/predictions.json`; it never feeds race
data into the model or refits it. See `README.md` for the model, metrics, and dashboard.

## Commands

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m unittest discover -s tests -v    # offline, no network
(cd frontend && npm test && npm run build)            # dashboard frontend
./.venv/bin/jupyter notebook f1_race_prediction.ipynb  # needs network on first run
npm run dev                                            # dashboard backend + frontend
```

FastF1 downloads timing data into `cache/` (gitignored). A cold run can take several
minutes.

## How the tests load the notebook

`tests/test_prediction.py` parses every code cell and executes **only top-level
`def` statements** into a namespace (`NS`) that injects the imports and the
notebook-level constants those functions read (`FEATURES`, `TARGET_COL`,
`MIN_TRAIN_RACES`, and others). Consequences:

- Put testable logic in top-level functions, not loose cell code.
- If a tested function starts reading a new notebook-level constant, add it to `NS`
  in the test file or the test will raise `NameError`.
- Keep each code cell valid standalone Python (`ast.parse` runs per cell), so avoid
  IPython magics like `%matplotlib`.
- Tests mock `fastf1.get_session` / `fastf1.get_event_schedule`; keep calling them
  through the `fastf1` module so the patches apply.

## Invariants (data leakage)

These are the point of the project. Do not weaken them, and add a regression test
when you touch the related code.

- **Never load the target race session.** For the target, only qualifying (`"Q"`) is
  loaded, even when the notebook is rerun after race day.
- **Training races are strictly earlier** than the target by scheduled UTC race start.
  Order by `RaceStartUtc`, never by event name.
- **`PriorPace` uses `shift()` before the expanding mean**, so a row never sees its own
  race result.
- **Imputation and scaling are fitted inside each walk-forward fold** (`make_model()`
  pipeline), never on the full pool.
- **Training stays within 2026.** Earlier seasons are excluded because of the
  regulation reset.
- **Fail loudly** when target qualifying has no usable times; do not substitute
  averages. Missing sessions for training races are reported and skipped, and at
  least `MIN_TRAIN_RACES` (4) usable races are required.

## Target configuration

`TARGET_RACE = (2026, "Bahrain Grand Prix")` refers to the relocated **October 4 race at
Sepang/Kuala Lumpur**. FastF1 may still label the country as Bahrain, so
`resolve_schedule` validates location and date and rejects a stale Sakhir entry. When
changing the target, update the venue check, the README, and the schedule test
together.

## Conventions

- Keep the README's metrics table in sync with an actual executed run. Do not quote
  numbers you have not reproduced.
- Commit the notebook with outputs from a clean top-to-bottom run, or with no outputs.
  Do not commit partial or stale outputs.
- Dependencies go in `requirements.txt` with minimum-version pins (`>=`).
