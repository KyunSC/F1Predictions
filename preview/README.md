# Redesign preview (preview-only, do not merge)

Switch between the ten `redesign/N-*` branches with number keys: 1–9 show styles 1–9, 0 shows style 10.

1. `git fetch origin 'refs/heads/redesign/*:refs/remotes/origin/redesign/*'`
2. From the repo root on this branch: `npm run dev` (backend on 8000, baseline on 5173).
3. In a second terminal: `preview/run.sh`, then open http://127.0.0.1:5200.

`run.sh` checks out each redesign into `.preview/N`, copies `frontend/node_modules`, drops `forward-keys.ts` in as
`frontend/instrumentation-client.ts` (never committed) and runs `next dev` on 127.0.0.1:520N. The forwarder sends
digit keys from the focused style to the switcher with `postMessage`, using a capture-phase listener that calls
`preventDefault` so the replay's 1/2/5 speed shortcuts don't also fire. Digits typed into a text field or select stay there.

Preview-only changes on this branch, to drop before merging a style:
- `preview/` and the `.preview/` line in `.gitignore`
- the 5200–5210 origins added to the WebSocket allowlist in `dashboard/app.py`

To merge a style, merge its `redesign/N-*` branch; those branches contain only the redesign.
