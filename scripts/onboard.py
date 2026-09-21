"""
One-stop onboarding wizard, launched via ./start.sh — walks through
whichever setup steps aren't done yet (search criteria, Discord alerts,
your message, logging in, a test run, going live, automatic scheduling)
and skips anything already in place. Safe to re-run any time.
"""
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    val = input(f"{prompt} ({hint}): ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def step_config() -> None:
    config_path = ROOT / "config.yaml"
    if config_path.exists():
        print("✓ config.yaml already exists — skipping search setup.")
        if ask_yes_no("  Want to redo it anyway?", default=False):
            subprocess.run([PYTHON, str(ROOT / "scripts" / "configure.py")], check=True)
        return
    print("\n--- Step 1: Search criteria ---")
    subprocess.run([PYTHON, str(ROOT / "scripts" / "configure.py")], check=True)


def step_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        print("✓ .env already exists — skipping Discord setup.")
        return
    print("\n--- Step 2: Discord alerts ---")
    print("In Discord: Channel Settings -> Integrations -> Webhooks -> New Webhook,")
    print("then copy the URL. You can use two channels (one for status, one for")
    print("landlord replies) or just reuse the same one for both.")
    main_url = ""
    while not main_url.startswith("https://discord.com/api/webhooks/"):
        main_url = input("Webhook URL for status alerts (new listings, sends, errors): ").strip()
        if not main_url.startswith("https://discord.com/api/webhooks/"):
            print("  That doesn't look like a Discord webhook URL — it should start with")
            print("  https://discord.com/api/webhooks/ — try pasting it again.")
    replies_url = input(
        "Webhook URL for landlord replies (Enter to reuse the same one): "
    ).strip() or main_url
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"DISCORD_WEBHOOK_URL={main_url}\n")
        f.write(f"DISCORD_REPLIES_WEBHOOK_URL={replies_url}\n")
    print(f"Wrote {env_path}")


def step_template() -> None:
    template_path = ROOT / "message_template.txt"
    if template_path.exists():
        print("✓ message_template.txt already exists — skipping.")
        return
    print("\n--- Step 3: Your message to landlords ---")
    example = ROOT / "message_template.example.txt"
    template_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Created {template_path} from the template.")
    print("IMPORTANT: open that file now in any text editor and replace the")
    print("[bracketed placeholders] with your real name, phone number, and a")
    print("sentence about yourself — in both the German and English sections.")
    print("The bot refuses to send live messages until this is done.")
    input("Press Enter once you've saved your edits (or to come back to it later)... ")


def step_login() -> None:
    storage_state = ROOT / "storage_state.json"
    if storage_state.exists():
        print("✓ Already logged in (storage_state.json exists) — skipping.")
        if ask_yes_no("  Log in again anyway to refresh the session?", default=False):
            subprocess.run([PYTHON, str(ROOT / "scripts" / "setup_login.py")], check=True)
        return
    print("\n--- Step 4: Log in to wg-gesucht ---")
    print("A browser window will open. You log in yourself there — this script")
    print("never sees or handles your password.")
    input("Press Enter to continue... ")
    subprocess.run([PYTHON, str(ROOT / "scripts" / "setup_login.py")], check=True)


def step_dry_run() -> None:
    print("\n--- Step 5: Test run ---")
    if ask_yes_no("Run a dry-run now? (searches and alerts on Discord, sends nothing)", default=True):
        subprocess.run([PYTHON, "-m", "src.main", "--dry-run"], check=True, cwd=ROOT)
        print("\nCheck Discord — you should see alerts for any matching listings.")


def step_go_live() -> None:
    print("\n--- Step 6: Go live ---")
    config_path = ROOT / "config.yaml"
    text = config_path.read_text(encoding="utf-8")
    if "live_mode: true" in text:
        print("✓ live_mode is already true.")
        return
    if ask_yes_no("Turn on live sending now? (real messages will go to real landlords)", default=False):
        text = text.replace("live_mode: false", "live_mode: true")
        config_path.write_text(text, encoding="utf-8")
        print("live_mode set to true.")
    else:
        print("Left live_mode as false — flip it in config.yaml whenever you're ready.")


def step_schedule() -> None:
    print("\n--- Step 7: Automatic scheduling ---")
    system = platform.system()
    if system == "Darwin":
        if ask_yes_no("Install the automatic schedule now (macOS launchd)?", default=True):
            subprocess.run(["bash", str(ROOT / "scripts" / "install_launchd.sh")], check=True)
    elif system == "Linux":
        if ask_yes_no("Install the automatic schedule now (cron)?", default=True):
            subprocess.run([PYTHON, str(ROOT / "scripts" / "install_cron.py")], check=True)
    else:
        print(f"Automatic scheduling isn't set up for {system} yet.")
        print("Run `python -m src.main` yourself on whatever schedule you like.")


def main() -> None:
    print("=== europe-room-hunt-bot onboarding ===")
    print("Walks through everything needed to get the bot running.")
    print("Already done a step before? It's skipped automatically.\n")

    step_config()
    step_env()
    step_template()
    step_login()
    step_dry_run()
    step_go_live()
    step_schedule()

    print("\n=== All set ===")
    print("Check bot.log or your Discord channels to see it working.")
    print("Re-run ./start.sh any time — it only redoes what you ask it to.")


if __name__ == "__main__":
    main()
