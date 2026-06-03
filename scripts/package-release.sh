#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="music-tools-mac-arm64"
DIST_DIR="$ROOT_DIR/dist"
STAGE_PARENT="$DIST_DIR/package-stage"
STAGE_DIR="$STAGE_PARENT/$PACKAGE_NAME"
ZIP_PATH="$DIST_DIR/$PACKAGE_NAME.zip"

rm -rf "$STAGE_PARENT"
mkdir -p "$STAGE_DIR" "$DIST_DIR"

rsync -a "$ROOT_DIR/" "$STAGE_DIR/" \
  --exclude ".git/" \
  --exclude ".DS_Store" \
  --exclude "dist/" \
  --exclude "backend/.venv/" \
  --exclude "frontend/node_modules/" \
  --exclude "frontend/dist/" \
  --exclude "storage/uploads/*" \
  --exclude "storage/outputs/*" \
  --exclude "storage/temp/*" \
  --exclude "__pycache__/" \
  --exclude "*.pyc"

mkdir -p "$STAGE_DIR/storage/uploads" "$STAGE_DIR/storage/outputs" "$STAGE_DIR/storage/temp"
touch "$STAGE_DIR/storage/uploads/.gitkeep" "$STAGE_DIR/storage/outputs/.gitkeep" "$STAGE_DIR/storage/temp/.gitkeep"
chmod +x "$STAGE_DIR/1-Install.command" "$STAGE_DIR/2-Start.command" "$STAGE_DIR/3-Stop.command" "$STAGE_DIR/scripts/start-dev.sh"

rm -f "$ZIP_PATH"
(cd "$STAGE_PARENT" && zip -qry -X "$ZIP_PATH" "$PACKAGE_NAME")
rm -rf "$STAGE_PARENT"

echo "Created: $ZIP_PATH"
