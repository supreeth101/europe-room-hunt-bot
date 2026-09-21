"""
Generates com.roomhunt.bot.plist based on config.yaml's schedule.mode.
Run via scripts/install_launchd.sh, which also loads it into launchd.
"""
import plistlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config

# How often the bot checks for new listings. Higher frequency catches
# listings sooner but is a more bot-like pattern — higher risk of wg-gesucht
# flagging the account. Pick based on how much that tradeoff matters to you.
MODES = {
    "aggressive": {"StartInterval": 3600},    # every 1 hour
    "laid_back": {"StartInterval": 10800},    # every 3 hours
    "normal": {"StartInterval": 21600},       # every 6 hours
}


def main() -> None:
    cfg = load_config()
    mode = cfg.get("schedule", {}).get("mode", "normal")
    if mode not in MODES:
        print(f"Unknown schedule mode '{mode}', falling back to 'normal'. Valid modes: {list(MODES)}")
        mode = "normal"

    repo_dir = Path(__file__).resolve().parent.parent
    python_bin = repo_dir / ".venv" / "bin" / "python"

    plist = {
        "Label": "com.roomhunt.bot",
        "ProgramArguments": [str(python_bin), "-m", "src.main"],
        "WorkingDirectory": str(repo_dir),
        "StandardOutPath": str(repo_dir / "launchd.out.log"),
        "StandardErrorPath": str(repo_dir / "launchd.err.log"),
        "RunAtLoad": False,
    }
    plist.update(MODES[mode])

    out_path = repo_dir / "com.roomhunt.bot.plist"
    with open(out_path, "wb") as f:
        plistlib.dump(plist, f)

    print(f"Generated {out_path} for schedule mode '{mode}'")


if __name__ == "__main__":
    main()
