import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("roomhunt.searcher")

BASE_URL = "https://www.wg-gesucht.de"

# Verified by hand against wg-gesucht.de on 2026-09-16. If wg-gesucht changes
# their search page markup or URL scheme, this is the first thing to re-check:
# open a search in a real browser with the desired filters and compare.
SEARCH_PATH_TEMPLATE = (
    "/wg-zimmer-und-1-zimmer-wohnungen-und-wohnungen-in-{city}.{city_id}.0+1+2.1.0.html"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# wg-gesucht marks each WG listing's "who are they looking for" with a small
# icon whose alt text is exactly one of these phrases (confirmed live on
# 2026-09-17). "Mitbewohnerin gesucht" = looking for a female flatmate only —
# skip those. Anything else (male-only, either, no icon at all e.g. plain
# apartments) is fine for a male applicant.
FEMALE_ONLY_ALT_TEXT = "Mitbewohnerin gesucht"

# Backstop for listings that state a gender restriction in free text without
# (or in addition to) the structured icon above.
FEMALE_ONLY_TEXT_PATTERN = re.compile(
    r"only girls|girls only|only women|women only|female only|"
    r"nur (für )?frauen|nur weiblich|sucht weibliche|mädchen gesucht|frauen-wg",
    re.IGNORECASE,
)


def build_search_url(cfg: dict) -> str:
    search = cfg["search"]
    if search.get("custom_url"):
        return search["custom_url"]

    if not search.get("city_id"):
        raise ValueError(
            "No search configured. In config.yaml, either set search.custom_url "
            "(build your search with filters on wg-gesucht.de and paste the URL), "
            "or set search.city_id and search.city_name — see config.example.yaml."
        )

    path = SEARCH_PATH_TEMPLATE.format(
        city=search["city_name"], city_id=search["city_id"]
    )
    params = {
        "offer_filter": 1,
        "city_id": search["city_id"],
        "sort_order": 0,
        "noDeact": 1,
        "min_rent": 0,
        "max_rent": search["max_rent"],
        "rMax": search["max_rent"],
        "dFr": search["_move_in_epoch"],
        "radDis": int(search["radius_km"] * 1000),
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    for cat in search["categories"]:
        query += f"&categories%5B%5D={cat}"
    for rt in search["rent_types"]:
        query += f"&rent_types%5B%5D={rt}"
    return f"{BASE_URL}{path}?{query}"


def fetch_listings(cfg: dict) -> list[dict]:
    url = build_search_url(cfg)
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    listings = []
    seen_ids_this_fetch = set()
    skipped_female_only = 0
    for card in soup.select('div[id^="liste-details-ad-"]'):
        listing_id = card.get("data-id")
        link_tag = card.select_one("h2.truncate_title a")
        if not listing_id or not link_tag:
            continue
        if listing_id in seen_ids_this_fetch:
            continue  # wg-gesucht can render a promoted listing twice on one page
        seen_ids_this_fetch.add(listing_id)
        title = link_tag.get_text(strip=True)
        href = link_tag.get("href", "")
        full_url = urljoin(BASE_URL, href)
        text = card.get_text(" ", strip=True)

        price_match = re.search(r"(\d[\d.,]*)\s?€", text)
        size_match = re.search(r"(\d+)\s?m²", text)
        date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)

        gender_icon = card.select_one('img[alt*="gesucht"]')
        gender_alt = gender_icon.get("alt", "") if gender_icon else ""
        if gender_alt == FEMALE_ONLY_ALT_TEXT or FEMALE_ONLY_TEXT_PATTERN.search(
            f"{title} {text}"
        ):
            skipped_female_only += 1
            continue  # female-only flatshare — not a fit, skip entirely

        listings.append(
            {
                "id": listing_id,
                "title": title,
                "url": full_url,
                "price": price_match.group(1) if price_match else "?",
                "size": size_match.group(1) if size_match else "?",
                "available_from": date_match.group(1) if date_match else "?",
            }
        )

    if skipped_female_only:
        log.info("Skipped %d female-only listings.", skipped_female_only)

    return listings
