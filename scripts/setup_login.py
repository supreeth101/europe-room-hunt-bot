"""
One-time interactive login.

This opens a real, visible browser window pointed at wg-gesucht.de. YOU log
in by hand (username/password, and any captcha wg-gesucht shows) — this
script never sees or touches your password. Once you're logged in, it saves
your session so the automated bot can reuse it without logging in again.

Run it again any time the bot reports the session expired.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from src.config import load_config

MESSAGES_LINK_HINTS = ["nachrichten", "conversations", "inbox"]


def main() -> None:
    cfg = load_config()
    storage_state_path = cfg["paths"]["storage_state"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.wg-gesucht.de/")

        print("\nA browser window has opened.")
        print("1. Log in to wg-gesucht.de yourself in that window.")
        print("   If you see a 'Stay logged in' / 'Angemeldet bleiben' checkbox, check it —")
        print("   it extends how long the session lasts before you need to log in again.")
        print("2. Solve any captcha it shows you.")
        print("3. Once you can see your account (e.g. your name top-right), come back here.\n")
        input("Press Enter once you are fully logged in... ")

        context.storage_state(path=storage_state_path)
        print(f"Saved logged-in session to {storage_state_path}")

        inbox_url = _try_detect_inbox_url(page)
        if inbox_url:
            _write_inbox_url(cfg, inbox_url)
            print(f"Auto-detected your messages inbox: {inbox_url}")
            print("Saved it into config.yaml as inbox_url.")
        else:
            print(
                "Could not auto-detect your messages inbox URL. Open your "
                "'Nachrichten' / messages page by hand, copy its URL, and set "
                "inbox_url in config.yaml manually."
            )

        browser.close()


def _try_detect_inbox_url(page) -> str | None:
    try:
        for hint in MESSAGES_LINK_HINTS:
            link = page.query_selector(f'a[href*="{hint}"]')
            if link:
                href = link.get_attribute("href")
                if href and href != "#":
                    page.goto(href)
                    page.wait_for_load_state("domcontentloaded")
                    return page.url
        return None
    except Exception:
        return None


def _write_inbox_url(cfg: dict, inbox_url: str) -> None:
    config_path = cfg["_root"] / "config.yaml"
    text = config_path.read_text(encoding="utf-8")
    if "inbox_url: null" in text:
        text = text.replace("inbox_url: null", f'inbox_url: "{inbox_url}"')
    elif "inbox_url:" in text:
        import re

        text = re.sub(r"inbox_url:.*", f'inbox_url: "{inbox_url}"', text)
    else:
        text += f'\ninbox_url: "{inbox_url}"\n'
    config_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
