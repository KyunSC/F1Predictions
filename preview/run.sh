#!/bin/sh
# Preview-only: serve the 10 redesign branches side by side and switch with number keys on http://127.0.0.1:5200.
# Start the backend first from the repo root with `npm run dev` (this branch's dashboard/app.py allows 5200-5210).
# Each redesign/N-* branch gets a worktree in .preview/N with node_modules copied from frontend/ and the
# key forwarder dropped in as frontend/instrumentation-client.ts (uncommitted). Ctrl+C stops everything.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
[ -d frontend/node_modules ] || (cd frontend && npm ci)
pids=''
stop(){ kill $pids 2>/dev/null; pkill -f 'next dev --hostname 127.0.0.1 --port 52(0[1-9]|10)' 2>/dev/null; }
trap stop EXIT INT TERM
for n in 1 2 3 4 5 6 7 8 9 10; do
 branch=$(git for-each-ref --format='%(refname:short)' "refs/heads/redesign/$n-*" "refs/remotes/origin/redesign/$n-*" | head -n1)
 [ -n "$branch" ] || { echo "No redesign/$n-* branch; fetch them first: git fetch origin 'refs/heads/redesign/*:refs/remotes/origin/redesign/*'"; exit 1; }
 dir=.preview/$n
 [ -d "$dir" ] || git worktree add --detach "$dir" "$branch"
 [ -d "$dir/frontend/node_modules" ] || if [ "$(uname)" = Darwin ]; then cp -cR frontend/node_modules "$dir/frontend/node_modules"; else cp -al frontend/node_modules "$dir/frontend/node_modules"; fi
 cp preview/forward-keys.ts "$dir/frontend/instrumentation-client.ts"
 (cd "$dir/frontend" && exec npx next dev --hostname 127.0.0.1 --port $((5200+n))) > "$dir.log" 2>&1 &
 pids="$pids $!"
done
python3 -m http.server 5200 --bind 127.0.0.1 --directory preview > /dev/null 2>&1 &
pids="$pids $!"
echo 'Switcher on http://127.0.0.1:5200 (keys 1-9, 0 = style 10). Logs in .preview/N.log'
wait
