#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "Stopping Music Tools services..."

stop_matching() {
  local pattern="$1"
  local pids
  pids="$(pgrep -f "$pattern" || true)"
  if [ -n "$pids" ]; then
    while IFS= read -r pid; do
      if [ -n "$pid" ]; then
        kill "$pid" >/dev/null 2>&1 || true
      fi
    done <<< "$pids"
  fi
}

stop_matching "$ROOT_DIR/backend/.venv/bin/uvicorn app.main:app"
stop_matching "$ROOT_DIR/backend/.venv/bin/python -m app.worker"
stop_matching "$ROOT_DIR/frontend/node_modules/.bin/vite --host 0.0.0.0"
stop_matching "npm run dev"

if command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
  redis-cli shutdown >/dev/null 2>&1 || true
fi

echo "Stopped."
echo
read -r -p "Press Return to close this window..." _ || true
