import json
import os
import shutil
from pathlib import Path


class StateCorrupted(Exception):
    pass


def load_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"seen_ids": [], "contacted": {}, "conversations": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        backup = p.with_suffix(p.suffix + ".corrupted")
        try:
            shutil.copy(p, backup)
        except OSError:
            pass
        # Never silently treat a corrupted file as "nothing contacted yet" —
        # that would risk re-sending to everyone already messaged. Fail
        # loud instead and let a human decide.
        raise StateCorrupted(
            f"{path} is corrupted ({e}). Backed up to {backup}. Refusing to "
            "run live until this is resolved — restore state.json from a "
            "backup, or delete it to start fresh (only do that if you "
            "understand it means re-checking every listing from zero)."
        ) from e


def save_state(path: str, state: dict) -> None:
    # Write to a temp file and rename over the target — rename is atomic on
    # POSIX, so a crash mid-write can never leave a half-written state.json.
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)
