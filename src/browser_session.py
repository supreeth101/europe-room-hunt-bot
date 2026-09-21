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
