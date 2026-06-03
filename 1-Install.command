#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

pause() {
  echo
  read -r -p "Press Return to close this window..." _ || true
}

trap pause EXIT

echo "Music Tools installer"
echo "====================="

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required but was not found."
  echo "Install Homebrew first: https://brew.sh"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found."
  echo "Install Python 3 first, or install it with Homebrew: brew install python"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but was not found."
  echo "Install Node.js first: brew install node"
  exit 1
fi

echo "Installing Homebrew packages..."
brew install ffmpeg redis yt-dlp rubberband

echo "Creating backend Python environment..."
cd "$BACKEND_DIR"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "Installing frontend dependencies..."
cd "$FRONTEND_DIR"
npm install
npm run build

echo
echo "Installation complete."
echo "Next: double-click 2-Start.command"
