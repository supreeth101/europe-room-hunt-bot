import logging
import random
import time
from pathlib import Path
from urllib.parse import urlparse

from .browser_session import looks_logged_out, SessionExpired

log = logging.getLogger("roomhunt.messenger")

BASE_URL = "https://www.wg-gesucht.de"

SUBMIT_TEXTS = ["Nachricht senden", "Senden", "Absenden", "Send message"]

SUCCESS_MARKERS = [
    "wurde versendet",
    "erfolgreich gesendet",
    "Nachricht wurde gesendet",
    "wurde erfolgreich kontaktiert",  # confirmed live: "<Name> wurde erfolgreich kontaktiert!"
]

# NOTE: wg-gesucht shows a generic "WG-Gesucht+" upsell banner ("Jetzt
# freischalten" / "Höhere Sichtbarkeit mit WG-Gesucht+") on ordinary pages,
# including the successful-contact confirmation page itself — it is NOT a
# reliable signal that sending was blocked. An earlier version of this file
# treated it as a paywall wall and mislabeled 3 genuinely-sent messages as
# failed. Do not resurrect a check based on this banner without a confirmed
# real example of what an actual send-blocked page looks like.


def _human_pause(cfg: dict) -> None:
    lo = cfg["limits"]["min_delay_seconds"]
    hi = cfg["limits"]["max_delay_seconds"]
    time.sleep(random.uniform(lo, hi))


def _message_url_for(listing_url: str) -> str:
    path = urlparse(listing_url).path
    return f"{BASE_URL}/nachricht-senden{path}"


def send_message(page, cfg: dict, listing: dict, message_text: str) -> tuple[bool, str]:
    """
    Returns (success, reason). On any doubt, returns False rather than
    guessing — a missed contact is far cheaper than looking like spam or
    sending a broken message.
    """
    url = _message_url_for(listing["url"])
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    _human_pause(cfg)

    if looks_logged_out(page):
        raise SessionExpired(
            "wg-gesucht logged us out. Re-run scripts/setup_login.py."
        )

    _dismiss_safety_modal(page)

    textareas = page.query_selector_all("textarea")
    target = None
    for ta in textareas:
        ta_id = ta.get_attribute("id") or ""
        if "note_textarea" in ta_id:
            continue  # this is the private "notes to self" box, not the message
        if ta.is_visible():
            target = ta
            break

    if target is None:
        _screenshot(page, cfg, listing["id"], "no_textarea")
        return False, "Could not find a message box on the contact page — check manually."

    target.click()
    target.fill(message_text)
    _human_pause(cfg)

    submit = None
    for text in SUBMIT_TEXTS:
        btn = page.query_selector(f'button:has-text("{text}")')
        if btn and btn.is_visible():
            submit = btn
            break
    if submit is None:
        submit = page.query_selector('button[type="submit"]')

    if submit is None:
        _screenshot(page, cfg, listing["id"], "no_submit_button")
        return False, "Could not find a send button on the contact page — check manually."

    _dismiss_safety_modal(page)
    submit.click(timeout=10000)
    page.wait_for_timeout(3000)

    body_text = page.inner_text("body")
    if any(marker in body_text for marker in SUCCESS_MARKERS):
        return True, "sent"

    # No clear confirmation text found — don't assume it worked.
    _screenshot(page, cfg, listing["id"], "unconfirmed")
    return False, "Sent, but couldn't confirm success on the page — please verify manually."


def _dismiss_safety_modal(page) -> None:
    """
    wg-gesucht shows a "Sicherheitstipps" (safety tips) modal dialog before
    letting you send a message — e.g. don't pay before viewing, don't share
    ID scans. It sits on top of the page and blocks clicks on the real form
    until dismissed. Best-effort: never let this raise and abort a send.
    """
    try:
        btn = page.query_selector("#sec_advice_submit_button")
        if btn and btn.is_visible():
            btn.click(timeout=5000)
            page.wait_for_timeout(500)
    except Exception:
        log.warning("Could not dismiss safety-tips modal (may not have been present)")


def _screenshot(page, cfg: dict, listing_id: str, tag: str) -> None:
    try:
        out_dir = Path(cfg["_root"]) / "screenshots"
        out_dir.mkdir(exist_ok=True)
        page.screenshot(path=str(out_dir / f"{listing_id}_{tag}.png"), full_page=True)
    except Exception:
        log.exception("Failed to save debug screenshot")
