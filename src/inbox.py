import hashlib
import logging
import re

from .browser_session import looks_logged_out, SessionExpired

log = logging.getLogger("roomhunt.inbox")

BASE_URL = "https://www.wg-gesucht.de"


def sync_conversation_listing_map(page, cfg: dict, state: dict) -> set:
    """
    Returns the set of listing IDs that already have a conversation on
    wg-gesucht — whether started by this bot or manually (e.g. your brother
    messaging someone himself before the bot got to it). This must run
    before deciding what counts as "new" to contact, otherwise the bot has
    no way to know a human already reached out and will duplicate it.

    Each conversation's listing ID is looked up once (via its "Zur Anzeige"
    link) and cached in state["conversation_listing_map"], so this only
    costs an extra page load for conversations we haven't mapped yet.
    """
    inbox_url = cfg.get("inbox_url")
    if not inbox_url:
        return set()

    page.goto(inbox_url, wait_until="domcontentloaded", timeout=30000)
    if looks_logged_out(page):
        raise SessionExpired("wg-gesucht logged us out. Re-run scripts/setup_login.py.")

    conv_ids = set()
    for link in page.query_selector_all('a[href*="nachricht.html?nachrichten-id="]'):
        href = link.get_attribute("href") or ""
        match = re.search(r"nachrichten-id=(\d+)", href)
        if match:
            conv_ids.add(match.group(1))

    conv_listing_map = state.setdefault("conversation_listing_map", {})
    new_conv_ids = [c for c in conv_ids if c not in conv_listing_map]

    for conv_id in new_conv_ids:
        page.goto(
            f"{BASE_URL}/nachricht.html?nachrichten-id={conv_id}&list=1",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        listing_id = None
        for link in page.query_selector_all("a"):
            href = link.get_attribute("href") or ""
            m = re.search(r"\.(\d{6,8})\.html", href)
            if m:
                listing_id = m.group(1)
                break
        if listing_id:
            conv_listing_map[conv_id] = listing_id
        else:
            log.warning("Could not find a listing link for conversation %s", conv_id)

    return set(conv_listing_map.values())


def check_for_replies(page, cfg: dict, state: dict) -> list[dict]:
    """
    Best-effort reply detector: wg-gesucht's inbox markup wasn't inspected
    while logged in (that requires a real login, which this project
    deliberately never automates). This walks conversation links on the
    inbox page and flags any whose content hash changed since last run.

    If this stops finding anything after wg-gesucht changes their site,
    the fix is to open inbox_url in a real browser, find how each
    conversation row is marked, and update the selector below.
    """
    inbox_url = cfg.get("inbox_url")
    if not inbox_url:
        log.warning(
            "No inbox_url in config.yaml — run scripts/setup_login.py to auto-detect it, "
            "or set it manually once you find your messages page URL."
        )
        return []

    page.goto(inbox_url, wait_until="domcontentloaded", timeout=30000)
    if looks_logged_out(page):
        raise SessionExpired("wg-gesucht logged us out. Re-run scripts/setup_login.py.")

    new_replies = []
    conversations = state.setdefault("conversations", {})

    # Each conversation row on /nachrichten.html repeats the same href across
    # several <a> tags (avatar initials, poster name, listing title, message
    # preview) — only the longest text is the actual message snippet, so we
    # gather every link per conversation id and keep the longest.
    links = page.query_selector_all('a[href*="nachricht.html?nachrichten-id="]')
    texts_by_conv = {}
    href_by_conv = {}
    for link in links:
        href = link.get_attribute("href") or ""
        match = re.search(r"nachrichten-id=(\d+)", href)
        if not match:
            continue
        conv_id = match.group(1)
        href_by_conv.setdefault(conv_id, href)
        text = (link.inner_text() or "").strip()
        if len(text) > len(texts_by_conv.get(conv_id, "")):
            texts_by_conv[conv_id] = text

    for conv_id, snippet in texts_by_conv.items():
        if not snippet:
            continue
        snippet_hash = hashlib.sha256(snippet.encode("utf-8")).hexdigest()

        prev_hash = conversations.get(conv_id)
        if prev_hash is None:
            # First time seeing this conversation — record it, don't alert
            # (avoids a flood of "new reply" alerts on first run).
            conversations[conv_id] = snippet_hash
            continue

        if prev_hash != snippet_hash:
            conversations[conv_id] = snippet_hash
            href = href_by_conv[conv_id]
            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            new_replies.append({"id": conv_id, "url": full_url, "snippet": snippet[:300]})

    return new_replies
