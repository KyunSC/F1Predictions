#!/bin/sh
# Run from any directory; the launcher resolves paths relative to this file.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec python3 dashboard/run.py "$@"
