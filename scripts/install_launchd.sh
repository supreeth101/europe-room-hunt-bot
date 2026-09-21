#!/usr/bin/env bash
# Generates com.roomhunt.bot.plist (using config.yaml's schedule.mode) and
# loads it into launchd so the bot runs on its own schedule. macOS only.
# Safe to re-run after changing schedule.mode in config.yaml.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$REPO_DIR/.venv/bin/python"
PLIST_NAME="com.roomhunt.bot.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Error: $PYTHON_BIN not found. Run this first:" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && playwright install chromium" >&2
  exit 1
fi

"$PYTHON_BIN" "$REPO_DIR/scripts/generate_plist.py"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
cp "$REPO_DIR/$PLIST_NAME" "$PLIST_DEST"
launchctl load "$PLIST_DEST"

echo "Installed and loaded $PLIST_DEST"
echo "Runs from: $REPO_DIR"
echo "To stop it: launchctl unload $PLIST_DEST"
