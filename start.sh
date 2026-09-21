#!/usr/bin/env bash
# The one command to run. Sets up the Python environment (first run only)
# and hands off to the interactive onboarding wizard, which walks through
# everything else — no other commands, no editing files by hand required.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but wasn't found on this machine." >&2
  echo "Install Python 3 first: https://www.python.org/downloads/" >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "First run — setting up (installs dependencies + a headless browser, takes a minute or two)..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r requirements.txt
python -m playwright install chromium

python scripts/onboard.py
