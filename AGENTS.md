# AGENTS.md

Guidance for AI coding agents working in this repository. `CLAUDE.md` is a symlink to
this file; edit `AGENTS.md` only.

## Project

Predicts relative race pace for a target F1 Grand Prix or sprint from its qualifying
performance and earlier races and sprints in the same season. The main output is a pace ranking, which is distinct
from finishing position; the notebook also validates a finishing-order ranker and
compares podium models. Model logic lives in `f1_race_prediction.ipynb`. A separate
local dashboard (`dashboard/` FastAPI backend, `frontend/` Next.js/React/TypeScript) shows live
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

## Running the dashboard

Needs Python 3.12 and Node.js 20.19+. The backend listens on `127.0.0.1:8000`, the
frontend on `127.0.0.1:5173`; open <http://127.0.0.1:5173>.

Start both services with one command from the repo root:

```bash
npm run dev          # same as ./start.sh; opens in Historical, toggle Live in the header
```

`dashboard/run.py` creates `.venv`, installs `requirements.txt` and runs `npm ci` in
`frontend/` if they are missing, then starts and supervises both services. Ctrl+C stops
both. It fails if port 8000 or 5173 is already in use. No root-level `npm install` is needed.
Do not start the services separately; `npm run dev` is the only supported way.

Next.js rewrites in `frontend/next.config.ts` proxy `/api` and the WebSockets to the
backend, so the frontend needs no backend URL. Run a single backend worker so all tabs
share one upstream connection and replay clock.

Backend environment variables:

- `F1_MODE=live` starts in live timing; the default is `replay` (Historical). There is
  one launch command; the header's Historical/Live toggle calls `POST /api/mode`, which
  cancels the current task and rebuilds `State` in the other mode.
- `F1_RECORDING=dashboard/recordings/<file>.jsonl` picks the replay recording (with
  `F1_MODE=replay`). `dashboard/run.py` sets it, when unset, to the most recent
  archived Grand Prix race (`python -m dashboard.historical --latest-race`, sprints
  skipped), importing it to a gitignored `dashboard/recordings/archive-*.jsonl` if
  missing. Unset in the backend, or if that import fails, it is `demo.jsonl` (six
  synthetic drivers). Tests that start the app pin it to the demo.
  The replay bar's **Change session** picker (`GET /api/archive`,
  `POST /api/archive/load`) imports and replays any archived session from 2018 on
  without a restart; it is display only and never feeds the model.
- `F1_PREDICTIONS=/absolute/path/predictions.json` overrides the export location.
- `F1_PIT_LOSS=/absolute/path/pit_loss.json` overrides the pit-loss table location
  (default `dashboard/pit_loss.json`, tracked). Regenerate it with
  `./.venv/bin/python -m dashboard.pit_loss --seasons 2023 2024 2025 2026`. It holds
  per-race green, SC and VSC medians; the dashboard picks one from `TrackStatus`. Lookups
  use only races that started strictly before the session shown. Display only; it never
  feeds the model.
- `F1TV_TOKEN=<subscription token>` authenticates the live connection. Without it the
  backend uses the token saved by `./.venv/bin/python -m fastf1 auth f1tv --authenticate`.
  F1 only streams car coordinates (`Position.z`) to F1TV Access/Pro subscribers; with no
  valid token, live timing still works but the track map shows no cars. Never log or
  record the token.

The backend reads `dashboard/predictions.json`, `dashboard/pit_loss.json` and the
recording once at startup, so restart it after re-exporting predictions or regenerating
the pit-loss table. Before relying on the frontend, run
`./.venv/bin/python -m dashboard.smoke --seconds 45` to check live-timing access (needs
network and an active session).

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

- **Never load the target session.** For a race target, only qualifying (`"Q"`) is
  loaded. For a sprint target, only sprint qualifying (`"SQ"`) is loaded, never the
  target's `"S"`, `"Q"` or `"R"`. This holds even when the notebook is rerun afterwards.
- **Training sessions are strictly earlier** than the target by scheduled UTC start.
  Order by `RaceStartUtc`, never by event name. `RaceStartUtc` is the UTC start of the
  *scored* session (Grand Prix or sprint), so a weekend's sprint and GP are separate rows.
- **`PriorPace` uses `shift()` before the expanding mean**, so a row never sees its own
  race result.
- **Imputation and scaling are fitted inside each walk-forward fold** (`make_model()`
  pipeline), never on the full pool.
- **Training rows and targets stay within 2026** because of the regulation reset.
  Earlier seasons (`VENUE_HISTORY_SEASONS`, 2023–2025) enter only as per-driver
  venue-history features (`VenuePace`, `VenueQualiRatio`), built the same way for every
  2026 session's circuit. `load_venue_history` refuses any season at or after the target
  season, and `add_venue_history` rejects such history rows.
- **Fail loudly** when target qualifying has no usable times; do not substitute
  averages. Missing sessions for training races are reported and skipped, and at
  least `MIN_TRAIN_RACES` (4) usable races are required.

## Target configuration

`TARGET_RACE = (2026, "Singapore Grand Prix")` with `TARGET_KIND = "sprint"` targets the
**Singapore Sprint at Marina Bay, October 10 (09:00 UTC)**. `TARGET_KIND` is `"race"`
(`Q` → `R`) or `"sprint"` (`SQ` → `S`), per `SESSION_CODES`. Training pools every earlier
2026 Grand Prix and sprint; a sprint's `RaceId` ends in `" Sprint"`.

`resolve_schedule` checks the target against `EXPECTED_VENUES`, keyed by
`(year, event, kind)`: location and the scored session's UTC date. It also keeps the
relocated 2026 Bahrain GP (October 4, Sepang/Kuala Lumpur) and rejects a stale Sakhir
entry. When changing the target, update `EXPECTED_VENUES`, the README, and the schedule
tests together. The dashboard export records the session `name` (`"Race"`/`"Sprint"`)
and date, and `dashboard/state.py:match_predictions` requires both to match.

## Conventions

- Keep the README's metrics table in sync with an actual executed run. Do not quote
  numbers you have not reproduced.
- Commit the notebook with outputs from a clean top-to-bottom run, or with no outputs.
  Do not commit partial or stale outputs.
- Dependencies go in `requirements.txt` with minimum-version pins (`>=`).

## Git

- Never run `git commit` or `git push`. The maintainer commits and pushes. Agents may
  stage changes, show diffs, and draft commit messages when asked.
- No AI attribution anywhere: no `Co-Authored-By` trailers, "Generated with" lines, or
  similar mentions in commit messages, PR descriptions, code, comments, or docs.
