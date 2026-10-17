# Track-map verification

The implementation is committed: arc-length projection with branch continuity and lap
wrap, one buffered presentation stream for map and tower, code-only tags with collision
placement, leader lines and a dense-pack grid fallback. Prediction and notebook logic
are untouched.

## Status (October 17, 2026)

| Check | Suzuka 2025 recording | Bundled synthetic demo |
|---|---|---|
| 400px mobile matrix (4 checkpoints × 1/2/5×) | Passed, Oct 9 (`mobile-400.json`) | Passed, Oct 17 (`demo/mobile-400.json`) |
| 1440px desktop matrix | 5 of 12 runs, Oct 9 (`desktop-1440.json`) | Passed, Oct 17 (`demo/desktop-1440.json`) |
| Disconnect/reconnect and stale-coordinate faults | Not run | Passed at 1440px and 400px, Oct 17 (`demo/faults.json`) |
| Keyboard and tower selection, restart keeps selection | Passed (mobile), Oct 9 | Passed at both widths, Oct 17 |

**Still open:** the Suzuka desktop matrix and the Suzuka fault audit. They need
`cache/suzuka-replay.jsonl` (import with `python -m dashboard.historical`, see the README)
and `cache/track-maps/46-2025.json` from MultiViewer. Neither `livetiming.formula1.com`
nor `api.multiviewer.app` was reachable from the environment that ran the October 17
checks, so they were run against the bundled demo instead. That proves the harness, the
audit and the frontend's behaviour; it does not establish alignment on measured
coordinates. Run the commands under "Browser acceptance audit" in the README with the
Suzuka recording to close them:

```js
fetch('/api/verify/audit.js').then(r=>r.text()).then(s=>{(0,eval)(s);trackAudit('desktop-1440').then(()=>trackFaultAudit())})
```

## October 17: synthetic demo, headless Chromium

Recording `dashboard/recordings/demo.jsonl` (SHA256 `95c241de…e668c`), synthetic
outline, current Next.js production build. Checkpoints 15, 45, 75 and 100 s at 1×, 2×
and 5×, three seconds each; fault audit at 45 s.

- Desktop 1440×900 and mobile 400×860: 12/12 runs each with no errors. At least 174
  frames per run; largest marker-to-outline distance 0.00001px; no clock mismatch,
  identity mismatch, label overlap, branch jump or unfrozen pause.
- Faults, both widths: map and tower froze and showed **Disconnected · frozen**, then
  reconnected; with coordinates withheld all 6 markers faded, were gone after 15 s, and
  returned with fresh samples.
- Screenshots of the 45 s checkpoint: `demo/desktop-1440.png`, `demo/mobile-400.png`.

The harness was brought up to date before this run. It now serves the current
frontend through its rewrites instead of committed Vite builds (removed, along with
the raw checkpoint dumps), seeks checkpoints in absolute recording seconds (after the
October 11 change to open archive replays at lights out, the old restart-and-advance
landed that many seconds after lights out instead), accepts the reducer's `record`
argument (every replay event raised a `TypeError` in the old wrapper), and clears a
position fault at each checkpoint. The audit checks code-only tags against the tower,
and that a restart keeps the selection, matching the current dashboard.

## October 9: Suzuka 2025, Chrome (earlier work)

Source: full `cache/suzuka-replay.jsonl`, SHA256 in `source.json`, with cached
`cache/track-maps/46-2025.json`. Checkpoints: 3523.5 (SAI/HUL position change at
3523.924), 3600 (close pack near crossing/hairpin), 3630 (corners), 3648.5 (VER wraps
start/finish around 3649.3).

- `mobile-400.json`: all 12 checkpoint/speed combinations passed, with no label
  overlaps, map/tower identity or clock mismatches, or >1px marker errors. Pause,
  keyboard selection, tower selection and restart selection reset passed. (The
  dashboard has since been changed to remember the selection across restarts.)
- `mobile-label-failure.json`: an earlier failed layout, fixed by letting labels use
  the whole SVG viewport with a grid fallback. Before/after screenshots are kept.
- `desktop-1440.json`: the first 5 runs passed when paused; the rest were not run.
- `baseline.json`: baseline at 3600 with raw marker offsets and five timing-gap
  mismatches between the current tower and the buffered moment. At 400px its largest
  static center offset was 0.213px, so it does not establish a >1px baseline failure.

These ran against the Vite frontend of the time, before the Next.js migration. No
live-feed accuracy claim is supported by archive verification.
