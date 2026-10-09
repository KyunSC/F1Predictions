# Track-map verification — paused at user request

Implementation is in the working tree; acceptance is **not complete**.

- Track projection follows polyline arc length, with branch continuity and lap wrap.
- Map and tower consume one buffered presentation stream and timestamped timing history.
- Labels show racing identity and official position; collision placement uses offsets,
  leader lines, responsive font sizing, and a dense-pack grid fallback.
- Prediction/notebook logic untouched. Existing AGENTS.md changes are user-owned.

## Evidence so far

Source: full `cache/suzuka-replay.jsonl`, SHA256 in `source.json`, exact cached
`cache/track-maps/46-2025.json`. The isolated harness reconstructs each checkpoint
by applying **only preceding events**, rather than seeding from the short fixture.

Checkpoints: 3523.5 (SAI/HUL position change at 3523.924), 3600 (close pack near
crossing/hairpin), 3630 (corners), 3648.5 (VER wraps start/finish around 3649.3).

- `mobile-400.json`: all 12 checkpoint/speed combinations passed (1x/2x/5x),
  no label overlaps, map/tower identity or clock mismatches, or >1px marker errors.
  Pause, keyboard selection, tower selection and restart selection reset passed.
- `mobile-label-failure.json`: earlier failed layout; fixed by allowing labels to use
  the whole SVG viewport and providing a grid fallback. Before/after screenshots saved.
- `desktop-1440.json`: first 5 runs passed when paused; remaining runs unfinished.
- `baseline.json`: baseline at 3600, raw marker offsets and five timing-gap mismatches
  between current tower and buffered moment. At 400px its largest static center
  offset was only 0.213px; this checkpoint does NOT establish a >1px baseline failure.
- Native Chrome browser controls worked after extension-based control failed.
  No Playwright was used. Screenshots include Chrome's responsive viewport controls.

## Validation and remaining work

51 offline Python tests passed. 17 frontend tests passed; production build passed.
Small final changes to timestamp metadata/reset handling were built afterward and
are in the desktop build; rerun final frontend tests before declaring completion.

Still required:
1. Finish desktop matrix and run the browser disconnect/reconnect and stale-coordinate
   fault audit. `audit.js` defines `trackAudit` and `trackFaultAudit`.
2. Recheck final mobile build if further code changes occur. Inspect/save final desktop
   screenshot; the current desktop after screenshot predates the last label refinement.
3. Review branch continuity and actual official-position transitions in desktop logs.
   Mobile matrix ran before the additional branch-step logging was added to audit.js.
4. Add/finish source-based regressions if new discrepancies appear, update README's
   old raw-coordinate description and previous overlapping-label verification claims.
5. Final tests, build, browser pass, diff review; keep generated builds/raw full checkpoint
   dumps out of commit as appropriate, retain screenshots and compact result logs.

Harness: `./.venv/bin/python -m dashboard.verify_replay --at 3600` serves localhost
8010, `/before/` and `/after/` compiled builds, plus test-only checkpoint/fault routes.
Original user dashboard services on 8000/5173 were not stopped or restarted.
The browser audit loop was stopped by reload and the isolated replay was paused.

To resume a browser matrix in the console on `/after/`:
`fetch('/audit.js').then(r=>r.text()).then(s=>{(0,eval)(s);trackAudit('desktop-1440').then(()=>trackFaultAudit())})`

The old source baseline is in `/private/tmp/f1-track-before` with an existing-node_modules
symlink. Generated before/after builds are in this directory. No live-feed accuracy
claim is supported by this Suzuka archive verification.
