import os
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str = None) -> dict:
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["_root"] = ROOT
    cfg["_discord_webhook_url"] = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    cfg["_discord_replies_webhook_url"] = os.environ.get(
        "DISCORD_REPLIES_WEBHOOK_URL", ""
    ).strip()

    for key in ("storage_state", "state_file", "log_file"):
        cfg["paths"][key] = str(ROOT / cfg["paths"][key])

    cfg["message_template_path"] = str(ROOT / cfg["message_template_path"])

    move_in = cfg["search"]["move_in_earliest"]
    dt = datetime.strptime(move_in, "%Y-%m-%d")
    cfg["search"]["_move_in_epoch"] = int(dt.timestamp())

    return cfg
