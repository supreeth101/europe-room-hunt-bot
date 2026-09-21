#!/usr/bin/env bash
# Generates com.roomhunt.bot.plist from the template (filling in this
# machine's actual paths) and loads it into launchd so the bot runs on
# its own schedule. macOS only. Safe to re-run after editing the schedule
# in com.roomhunt.bot.plist.template.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$REPO_DIR/.venv/bin/python"
PLIST_NAME="com.roomhunt.bot.plist"
PLIST_OUT="$REPO_DIR/$PLIST_NAME"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Error: $PYTHON_BIN not found. Run this first:" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && playwright install chromium" >&2
  exit 1
fi

sed -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" -e "s|__REPO_DIR__|$REPO_DIR|g" \
  "$REPO_DIR/$PLIST_NAME.template" > "$PLIST_OUT"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
cp "$PLIST_OUT" "$PLIST_DEST"
launchctl load "$PLIST_DEST"

echo "Installed and loaded $PLIST_DEST"
echo "Runs from: $REPO_DIR"
echo "To stop it: launchctl unload $PLIST_DEST"
