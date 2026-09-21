import argparse
import logging
import re
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from .browser_session import SessionExpired, new_context, persist_storage_state
from .config import load_config
from .inbox import check_for_replies, sync_conversation_listing_map
from .messenger import send_message
from .notify import send_discord
from .scam_check import find_scam_flags
from .searcher import fetch_listings
from .state import load_state, save_state

log = logging.getLogger("roomhunt")


def setup_logging(log_file: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
    )


PLACEHOLDER_PATTERN = re.compile(r"\[[^\]\n]{1,60}\]")


def _template_has_placeholders(template_path: str) -> bool:
    with open(template_path, "r", encoding="utf-8") as f:
        text = f.read()
    return bool(PLACEHOLDER_PATTERN.search(text))


def render_template(template_text: str, listing: dict, cfg: dict) -> str:
    return template_text.format(
        listing_title=listing["title"],
        max_rent=cfg["search"]["max_rent"],
    )


def _listing_alert(l: dict, prefix: str) -> str:
    return (
        f"{prefix} **{l['title']}**\n"
        f"{l['price']} € · {l['size']} m² · from {l['available_from']}\n{l['url']}"
    )


def run(dry_run: bool) -> None:
    cfg = load_config()
    setup_logging(cfg["paths"]["log_file"])
    state = load_state(cfg["paths"]["state_file"])

    effective_live = cfg["live_mode"] and not dry_run
    if dry_run:
        log.info("Running in DRY RUN mode: no messages will be sent.")
    elif not cfg["live_mode"]:
        log.info("config.yaml live_mode is false: no messages will be sent.")

    if effective_live and _template_has_placeholders(cfg["message_template_path"]):
        log.error(
            "message_template.txt still has unfilled [PLACEHOLDER] text. "
            "Refusing to send real messages until it's edited."
        )
        send_discord(
            cfg,
            "⚠️ message_template.txt still has unfilled placeholders "
            "(like [DEIN NAME]) — no messages sent this run. Edit the "
            "template, then it'll go out next time.",
        )
        effective_live = False

    log.info("Fetching current listings...")
    listings = fetch_listings(cfg)
    log.info("Found %d listings matching search criteria.", len(listings))

    # seen_ids means "already handled" (dry-run alerted, or an actual contact
    # attempt was made) — NOT merely "appeared in search results". A listing
    # deferred by max_new_contacts_per_run must stay unseen so it's picked up
    # on a later run instead of being silently dropped forever.
    seen_ids = set(state.get("seen_ids", []))
    new_listings = [l for l in listings if l["id"] not in seen_ids]
    log.info("%d of those are new since last run.", len(new_listings))

    contacted = state.setdefault("contacted", {})
    limits = cfg["limits"]

    with open(cfg["message_template_path"], "r", encoding="utf-8") as f:
        template_text = f.read()

    if not effective_live:
        # No login available/wanted this run — just alert on everything new.
        for l in new_listings:
            send_discord(cfg, _listing_alert(l, "🏠 New listing (dry run, not contacted):"))
            seen_ids.add(l["id"])
        state["seen_ids"] = list(seen_ids)
        save_state(cfg["paths"]["state_file"], state)
        log.info("Done.")
        return

    try:
        with sync_playwright() as p:
            browser, context = new_context(p, cfg, headless=True)
            page = context.new_page()
            try:
                # Check which listings already have a conversation on
                # wg-gesucht — whether started by this bot or manually by
                # your brother — BEFORE deciding what's safe to auto-send.
                # Without this, a listing he messages himself between runs
                # looks "new" to the bot and gets auto-messaged again.
                log.info("Checking for existing conversations...")
                try:
                    existing_conversation_listing_ids = sync_conversation_listing_map(
                        page, cfg, state
                    )
                except SessionExpired:
                    raise
                except Exception:
                    log.exception("Unexpected error syncing conversation map")
                    existing_conversation_listing_ids = set()

                to_contact = []
                for l in new_listings:
                    if l["id"] in existing_conversation_listing_ids:
                        contacted[l["id"]] = {
                            "title": l["title"],
                            "url": l["url"],
                            "sent_at": None,
                            "success": True,
                            "reason": "already had an existing conversation (likely contacted manually) — auto-send skipped",
                        }
                        seen_ids.add(l["id"])
                        send_discord(
                            cfg,
                            _listing_alert(
                                l, "ℹ️ Already have a conversation for this one, skipped:"
                            ),
                        )
                        continue

                    if len(to_contact) >= limits["max_new_contacts_per_run"]:
                        send_discord(cfg, _listing_alert(l, "🏠 New listing (queued for next run):"))
                        continue  # deliberately NOT added to seen_ids

                    to_contact.append(l)

                state["seen_ids"] = list(seen_ids)
                save_state(cfg["paths"]["state_file"], state)

                for l in to_contact:
                    message = render_template(template_text, l, cfg)
                    try:
                        success, reason = send_message(page, cfg, l, message)
                    except SessionExpired:
                        raise
                    except Exception as e:
                        log.exception("Unexpected error sending to %s", l["url"])
                        success, reason = False, f"Unexpected error: {e}"
                    contacted[l["id"]] = {
                        "title": l["title"],
                        "url": l["url"],
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                        "success": success,
                        "reason": reason,
                    }
                    seen_ids.add(l["id"])
                    state["seen_ids"] = list(seen_ids)
                    if success:
                        send_discord(cfg, f"✅ Sent message to landlord: **{l['title']}**\n{l['url']}")
                    else:
                        send_discord(
                            cfg,
                            f"⚠️ Could not auto-send to **{l['title']}** ({reason})\n{l['url']}",
                        )
                    save_state(cfg["paths"]["state_file"], state)

                log.info("Checking inbox for replies...")
                try:
                    replies = check_for_replies(page, cfg, state)
                except SessionExpired:
                    raise
                except Exception:
                    log.exception("Unexpected error checking inbox")
                    replies = []
                for r in replies:
                    flags = find_scam_flags(r["snippet"])
                    msg = f"📩 New reply on wg-gesucht!\n{r['snippet']}\n{r['url']}"
                    if flags:
                        msg = (
                            "🚨 **Possible scam indicators** in this reply — "
                            f"{', '.join(flags)}. Verify carefully before sending "
                            "any money or documents.\n\n" + msg
                        )
                    send_discord(cfg, msg, channel="replies")
            finally:
                persist_storage_state(context, cfg)
                context.close()
                browser.close()
    except SessionExpired as e:
        log.error(str(e))
        send_discord(cfg, f"🔒 wg-gesucht session expired: {e}")

    save_state(cfg["paths"]["state_file"], state)
    log.info("Done.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and alert only, never send messages (safe to run without logging in).",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
