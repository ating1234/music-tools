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

# 偵測是否使用遠端後端 (不包含 localhost 或 127.0.0.1)
USE_REMOTE_BACKEND=0
REMOTE_URL=""

read_env_file() {
  local env_file="$1"
  if [ -f "$env_file" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      # 移除前後空白與 CR 符號，並忽略註解與空行
      line_clean=$(echo "$line" | tr -d '\r' | xargs || true)
      if [[ ! "$line_clean" =~ ^# ]] && [[ "$line_clean" =~ = ]]; then
        key=$(echo "$line_clean" | cut -d'=' -f1 | tr -d '[:space:]')
        val=$(echo "$line_clean" | cut -d'=' -f2- | tr -d '[:space:]')
        if [ "$key" = "VITE_API_BASE_URL" ]; then
          REMOTE_URL="$val"
        fi
      fi
    done < "$env_file"
  fi
}

# 依序讀取 .env 與 .env.local，後者會覆蓋前者
read_env_file "$FRONTEND_DIR/.env"
read_env_file "$FRONTEND_DIR/.env.local"

if [ -n "$REMOTE_URL" ] && [[ "$REMOTE_URL" != *"localhost"* ]] && [[ "$REMOTE_URL" != *"127.0.0.1"* ]]; then
  USE_REMOTE_BACKEND=1
fi

if [ "$USE_REMOTE_BACKEND" = "1" ]; then
  echo "--- Remote Backend Mode Enabled ---"
  echo "Connecting to remote Space: $REMOTE_URL"
  echo "Skipping local backend, worker, and Redis startup."
  echo "-----------------------------------"
  
  # 僅需要 npm 與 lsof 即可運行前端
  require_command npm
  require_command lsof
else
  # 本地模式，需要所有依賴
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
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Frontend node_modules not found. Installing..."
  (cd "$FRONTEND_DIR" && npm install)
fi

# 只有在本地模式下才啟動 Redis 與 Python 後端
if [ "$USE_REMOTE_BACKEND" = "0" ]; then
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
fi

port_in_use() {
  lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

if port_in_use 5180; then
  echo "Frontend already appears to be running on port 5180."
else
  echo "Starting Frontend..."
  (cd "$FRONTEND_DIR" && npm run dev) &
  PIDS+=("$!")
fi

MAC_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
if [ -z "$MAC_IP" ]; then
  MAC_IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
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
