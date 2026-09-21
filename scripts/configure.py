"""
Interactive setup wizard for config.yaml — no YAML editing required.

Walks through every search criterion (city, budget, radius, move-in date,
room type, gender filters, check-frequency) and writes config.yaml for you.
City names are resolved against wg-gesucht's own public lookup, so you
never need to know their internal numeric city IDs.

Safe to re-run any time you want to change your criteria — it'll ask
before overwriting an existing config.yaml.
"""
import sys
from pathlib import Path
from urllib.parse import quote

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent

CITY_API = "https://www.wg-gesucht.de/api/location/cities/names/{query}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    )
}

GENDER_CHOICES = ["male", "female", "divers", "any"]
SCHEDULE_CHOICES = ["aggressive", "laid_back", "normal"]
CATEGORY_MAP = {"1": 0, "2": 1, "3": 2, "4": 3}


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default


def ask_int(prompt: str, default: int) -> int:
    while True:
        raw = ask(prompt, str(default))
        try:
            return int(raw)
        except ValueError:
            print("  Please enter a whole number.")


def ask_choice(prompt: str, options: list, default: str) -> str:
    labeled = "/".join(o.upper() if o == default else o for o in options)
    while True:
        val = ask(f"{prompt} ({labeled})", default).lower()
        if val in options:
            return val
        print(f"  Please enter one of: {', '.join(options)}")


def ask_date(prompt: str) -> str:
    import datetime

    while True:
        raw = ask(f"{prompt} (YYYY-MM-DD)")
        if not raw:
            print("  This one's required — pick your earliest acceptable move-in date.")
            continue
        try:
            datetime.datetime.strptime(raw, "%Y-%m-%d")
            return raw
        except ValueError:
            print("  Please use YYYY-MM-DD format, e.g. 2026-03-01.")


def resolve_city() -> dict:
    while True:
        query = ask("\nWhich city? (e.g. 'Munich', 'Zurich', 'Vienna', 'Berlin')")
        if not query:
            continue
        try:
            resp = requests.get(
                CITY_API.format(query=quote(query)), headers=HEADERS, timeout=10
            )
            resp.raise_for_status()
            cities = resp.json().get("_embedded", {}).get("cities", [])
        except requests.RequestException as e:
            print(f"  Could not reach wg-gesucht.de ({e}). Check your connection and try again.")
            continue

        if not cities:
            print("  No matching city found on wg-gesucht.de — try a different spelling.")
            continue

        if len(cities) == 1:
            city = cities[0]
            confirm = ask(
                f"  Found: {city['city_and_state']} (id {city['city_id']}). Use this? (Y/n)", "y"
            ).lower()
            if confirm in ("y", "yes"):
                return city
            continue

        print("  Multiple matches:")
        for i, city in enumerate(cities, 1):
            print(f"    {i}. {city['city_and_state']}")
        pick = ask(f"  Pick 1-{len(cities)}")
        if pick.isdigit() and 1 <= int(pick) <= len(cities):
            return cities[int(pick) - 1]
        print("  Invalid choice, try again.")


def ask_categories() -> list:
    print("\nRoom type — what are you looking for? You can pick more than one, e.g. '1,2'")
    print("  1. WG room (shared flat)")
    print("  2. 1-room flat")
    print("  3. Flat")
    print("  4. House")
    while True:
        raw = ask("Which number(s)", "1,2")
        picked = [CATEGORY_MAP[c.strip()] for c in raw.split(",") if c.strip() in CATEGORY_MAP]
        if picked:
            return sorted(set(picked))
        print("  Please enter at least one of 1, 2, 3, 4.")


def build_config(city: dict, categories: list, max_rent: int, radius_km: int,
                  move_in: str, applicant_gender: str, room_gender_preference: str,
                  schedule_mode: str) -> dict:
    return {
        "search": {
            "custom_url": "",
            "city_id": int(city["city_id"]),
            "city_name": city["city_name"],
            "categories": categories,
            "rent_types": [1, 2, 3],
            "max_rent": max_rent,
            "radius_km": radius_km,
            "move_in_earliest": move_in,
            "applicant_gender": applicant_gender,
            "room_gender_preference": room_gender_preference,
        },
        "limits": {
            "max_new_contacts_per_run": 5,
            "min_delay_seconds": 8,
            "max_delay_seconds": 20,
        },
        "live_mode": False,
        "schedule": {"mode": schedule_mode},
        "message_template_path": "message_template.txt",
        "paths": {
            "storage_state": "storage_state.json",
            "state_file": "state.json",
            "log_file": "bot.log",
        },
        "inbox_url": None,
    }


def write_config(config: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "# Generated by scripts/configure.py — see config.example.yaml for\n"
            "# full documentation on every field. Re-run the wizard any time to\n"
            "# regenerate this, or edit it directly.\n\n"
        )
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def main() -> None:
    print("=== europe-room-hunt-bot setup wizard ===")
    print("Answers your search criteria and writes config.yaml — no YAML editing needed.")
    print("Press Enter to accept the [default] shown for any question.")

    config_path = ROOT / "config.yaml"
    if config_path.exists():
        overwrite = ask(f"\n{config_path.name} already exists. Overwrite it? (y/N)", "n").lower()
        if overwrite not in ("y", "yes"):
            print("Cancelled — existing config.yaml left untouched.")
            return

    city = resolve_city()
    currency = "CHF" if city.get("country_code") == "ch" else "EUR"

    categories = ask_categories()
    max_rent = ask_int(f"\nMax rent per month, warm/all-inclusive, in {currency}", 800)
    radius_km = ask_int("Search radius in km (includes nearby towns)", 10)
    move_in = ask_date("Earliest move-in date")

    print(
        "\nYour own gender — filters out listings you're not eligible for "
        "(some flatshares only want a specific gender)."
    )
    applicant_gender = ask_choice("Your gender", GENDER_CHOICES, "any")

    print(
        "\nOptional: a preference for the *current residents'* gender, "
        "independent of who a listing is recruiting."
    )
    room_gender_preference = ask_choice("Residents preference", GENDER_CHOICES, "any")

    print(
        "\nHow often should it check for new listings? aggressive=1h (fastest, "
        "most bot-like) / laid_back=3h / normal=6h (lowest risk)"
    )
    schedule_mode = ask_choice("Schedule", SCHEDULE_CHOICES, "normal")

    config = build_config(
        city, categories, max_rent, radius_km, move_in,
        applicant_gender, room_gender_preference, schedule_mode,
    )
    write_config(config, config_path)

    print(f"\nWrote {config_path}")
    print(f"  City: {city['city_and_state']} (id {city['city_id']})")
    print(f"  Max rent: {max_rent} {currency} | Radius: {radius_km} km | Move-in from: {move_in}")
    print(f"  Applicant gender: {applicant_gender} | Residents preference: {room_gender_preference}")
    print(f"  Schedule: {schedule_mode}")
    print("\nNext steps:")
    print("  1. cp message_template.example.txt message_template.txt   (then fill in your details)")
    print("  2. cp .env.example .env   (then add your Discord webhook URLs)")
    print("  3. python scripts/setup_login.py")
    print("  4. python -m src.main --dry-run")


if __name__ == "__main__":
    main()
