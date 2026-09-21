import logging

import requests

log = logging.getLogger("roomhunt.notify")


def send_discord(cfg: dict, content: str, channel: str = "status") -> None:
    if channel == "replies":
        webhook = cfg.get("_discord_replies_webhook_url") or cfg.get("_discord_webhook_url")
    else:
        webhook = cfg.get("_discord_webhook_url")

    if not webhook:
        log.warning("No Discord webhook configured for channel=%s, skipping alert: %s", channel, content)
        return
    try:
        resp = requests.post(webhook, json={"content": content[:1900]}, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        log.exception("Failed to send Discord notification")
