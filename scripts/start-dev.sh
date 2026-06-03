#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

PIDS=()
REDIS_STARTED=0

cleanup() {
  echo
  echo "Stopping Music Tools..."
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  if [ "$REDIS_STARTED" = "1" ]; then
    redis-cli shutdown >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1"
    exit 1
  fi
}

require_command redis-cli
require_command redis-server
require_command lsof
require_command ffmpeg
require_command rubberband
require_command yt-dlp
require_command npm
require_command curl

if [ ! -x "$BACKEND_DIR/.venv/bin/python" ]; then
  echo "Backend venv not found. Run: cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Frontend node_modules not found. Installing..."
  (cd "$FRONTEND_DIR" && npm install)
fi

if ! redis-cli ping >/dev/null 2>&1; then
  echo "Starting Redis..."
  redis-server --daemonize yes
  REDIS_STARTED=1
  sleep 1
fi

port_in_use() {
  lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

backend_health() {
  curl -fsS --max-time 2 http://127.0.0.1:8005/api/health 2>/dev/null || true
}

MAC_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
if [ -z "$MAC_IP" ]; then
  MAC_IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi

if port_in_use 8005; then
  HEALTH="$(backend_health)"
  if [[ "$HEALTH" == *'"ok":true'* ]]; then
    echo "Backend API already appears to be running on port 8005."
  else
    echo "Port 8005 is already in use, but it does not look like Music Tools Backend API."
    echo "Close the other app using port 8005, then run 2-Start.command again."
    echo
    lsof -nP -iTCP:8005 -sTCP:LISTEN || true
    exit 1
  fi
else
  echo "Starting Backend API..."
  (cd "$BACKEND_DIR" && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload) &
  PIDS+=("$!")
fi

echo "Starting Worker..."
(cd "$BACKEND_DIR" && .venv/bin/python -m app.worker) &
PIDS+=("$!")

if port_in_use 5180; then
  echo "Frontend already appears to be running on port 5180."
else
  echo "Starting Frontend..."
  (cd "$FRONTEND_DIR" && npm run dev) &
  PIDS+=("$!")
fi

echo
echo "Music Tools is starting."
echo "Computer: http://localhost:5180"
if [ -n "$MAC_IP" ]; then
  echo "Phone on same Wi-Fi: http://$MAC_IP:5180"
else
  echo "Phone URL: could not detect Wi-Fi IP. Run: ipconfig getifaddr en0"
fi
echo
echo "Keep this terminal open. Press Ctrl+C to stop."

if [ "${#PIDS[@]}" -gt 0 ]; then
  wait
fi
