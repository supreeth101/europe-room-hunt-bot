import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

log = logging.getLogger("roomhunt.session")

LOGIN_WALL_MARKERS = ["Kostenfrei registrieren", "Schön, dass Sie vorbeischauen"]


class SessionExpired(Exception):
    pass


def require_storage_state(cfg: dict) -> str:
    path = cfg["paths"]["storage_state"]
    if not Path(path).exists():
        raise SessionExpired(
            f"No saved login found at {path}. Run "
            "`python scripts/setup_login.py` once to log in manually."
        )
    return path


def looks_logged_out(page) -> bool:
    body_text = page.inner_text("body")
    return any(marker in body_text for marker in LOGIN_WALL_MARKERS)


def new_context(playwright, cfg: dict, headless: bool = True):
    storage_state = require_storage_state(cfg)
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(storage_state=storage_state)
    return browser, context


def persist_storage_state(context, cfg: dict) -> None:
    """
    wg-gesucht uses a short-lived access token plus a long-lived refresh
    token; a real browser silently renews the access token via JS before it
    expires. If we only ever replay the cookie snapshot from the original
    manual login, that renewal (when it happens during an automated run)
    gets thrown away the moment the browser closes, and the next run starts
    from the same aging snapshot again. Re-saving after every run carries
    any such renewal forward, so the login should last far longer in
    practice than a single static snapshot would.
    """
    try:
        context.storage_state(path=cfg["paths"]["storage_state"])
    except Exception:
        log.exception("Failed to persist refreshed session state")


def run_with_session(cfg: dict, fn, headless: bool = True):
    """Open a browser with the saved session, run fn(page), always close up."""
    with sync_playwright() as p:
        browser, context = new_context(p, cfg, headless=headless)
        try:
            page = context.new_page()
            return fn(page)
        finally:
            context.close()
            browser.close()
