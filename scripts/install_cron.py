"""
Installs (or updates) a crontab entry to run the bot on config.yaml's
schedule.mode interval. Linux (or anywhere `crontab` is available — macOS
users should use install_launchd.sh instead, which better survives sleep).
Only ever touches its own marked line — never disturbs your other cron jobs.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config

MARKER = "# europe-room-hunt-bot"

MODE_TO_CRON_STEP = {"aggressive": 1, "laid_back": 3, "normal": 6}


def main() -> None:
    cfg = load_config()
    mode = cfg.get("schedule", {}).get("mode", "normal")
    step = MODE_TO_CRON_STEP.get(mode, 6)

    repo_dir = Path(__file__).resolve().parent.parent
    python_bin = repo_dir / ".venv" / "bin" / "python"
    line = (
        f"0 */{step} * * * cd {repo_dir} && {python_bin} -m src.main "
        f">> {repo_dir}/launchd.out.log 2>&1 {MARKER}"
    )

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("`crontab` isn't available on this system. Run this yourself on a schedule instead:")
        print(f"  cd {repo_dir} && {python_bin} -m src.main")
        return

    existing = result.stdout if result.returncode == 0 else ""
    kept_lines = [l for l in existing.splitlines() if MARKER not in l]
    kept_lines.append(line)
    new_crontab = "\n".join(kept_lines) + "\n"

    subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
    print(f"Installed cron job (mode: {mode}, every {step} hour(s)):")
    print(f"  {line}")
    print("To remove it later: crontab -e, then delete the line containing '# europe-room-hunt-bot'")


if __name__ == "__main__":
    main()
