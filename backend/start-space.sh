#!/usr/bin/env bash
set -e

echo "Starting Redis server..."
redis-server --daemonize yes

echo "Starting RQ Worker..."
# 啟動 Worker 並置於背景執行
python -m app.worker &

echo "Starting FastAPI API on port 7860..."
# 啟動 FastAPI，由 Uvicorn 託管，監聽 7860 連接埠 (Hugging Face Spaces 的標準映射連接埠)
exec uvicorn app.main:app --host 0.0.0.0 --port 7860
