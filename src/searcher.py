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

# German-locale ASCII transliteration for the city slug in the URL path.
# Confirmed live (2026-09-21): the numeric city_id is what actually
# determines results, but the slug still has to be a plain-ASCII ready
# match — a percent-encoded umlaut (e.g. "M%C3%BCnchen") 404s, while the
# ASCII transliteration wg-gesucht itself uses ("Muenchen") works.
UMLAUT_MAP = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
)


def _url_safe_city_slug(city_name: str) -> str:
    slug = city_name.translate(UMLAUT_MAP).replace(" ", "-")
    return re.sub(r"[^A-Za-z0-9-]", "", slug) or "Stadt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# wg-gesucht's own server-side gender filters, confirmed live on 2026-09-21
# by setting each dropdown and reading the resulting URL param:
#   wgSea = "Gesucht"  — the gender of flatmate they're recruiting (your
#                        eligibility to apply)
#   wgFla = "Bewohner" — the gender of the WG's *current* residents (a
#                        preference about who you'd be living with)
# Both take the same codes; omitting the param means "egal" (no filter).
GENDER_CODES = {"female": 1, "male": 2, "divers": 3}

# Client-side backstop for listings that state a gender restriction in free
# text (title/description) without it being reflected in the structured
# "Gesucht" field wgSea already filters on server-side. Only meaningful for
# male/female applicants — there's no clean free-text pattern for excluding
# "divers"-incompatible listings, so that relies on wgSea alone.
INCOMPATIBLE_ALT_TEXT = {
    "male": "Mitbewohnerin gesucht",  # female-only wanted
    "female": "Mitbewohner gesucht",  # male-only wanted
}
INCOMPATIBLE_TEXT_PATTERNS = {
    "male": re.compile(
        r"only girls|girls only|only women|women only|female only|"
        r"nur (für )?frauen|nur weiblich|sucht weibliche|mädchen gesucht|frauen-wg",
        re.IGNORECASE,
    ),
    "female": re.compile(
        r"only boys|boys only|only men|men only|male only|"
        r"nur (für )?männer|nur männlich|sucht männlichen|männer-wg",
        re.IGNORECASE,
    ),
}


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

    # Confirmed live (2026-09-21): only the numeric city_id actually
    # determines results — this slug is cosmetic (wg-gesucht renders the
    # right city's search page even with a nonsense slug). Still URL-encode
    # it properly rather than relying on that, since an un-encoded umlaut
    # or space in the raw URL string is asking for trouble.
    path = SEARCH_PATH_TEMPLATE.format(
        city=_url_safe_city_slug(str(search["city_name"])),
        city_id=search["city_id"],
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

    applicant_gender = search.get("applicant_gender", "any")
    if applicant_gender in GENDER_CODES:
        query += f"&wgSea={GENDER_CODES[applicant_gender]}"

    room_gender_preference = search.get("room_gender_preference", "any")
    if room_gender_preference in GENDER_CODES:
        query += f"&wgFla={GENDER_CODES[room_gender_preference]}"

    return f"{BASE_URL}{path}?{query}"


def fetch_listings(cfg: dict) -> list[dict]:
    url = build_search_url(cfg)
    applicant_gender = cfg["search"].get("applicant_gender", "any")
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    incompatible_alt = INCOMPATIBLE_ALT_TEXT.get(applicant_gender)
    incompatible_pattern = INCOMPATIBLE_TEXT_PATTERNS.get(applicant_gender)

    listings = []
    seen_ids_this_fetch = set()
    skipped_gender = 0
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

        # Germany/Austria show € — Switzerland shows CHF (confirmed live on
        # a Zürich search on 2026-09-21). Capture whichever is present so
        # price display isn't silently wrong/missing for Swiss listings.
        price_match = re.search(r"(\d[\d.,]*)\s?(€|CHF)", text)
        size_match = re.search(r"(\d+)\s?m²", text)
        date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)

        if incompatible_alt or incompatible_pattern:
            gender_icon = card.select_one('img[alt*="gesucht"]')
            gender_alt = gender_icon.get("alt", "") if gender_icon else ""
            text_is_incompatible = bool(
                incompatible_pattern and incompatible_pattern.search(f"{title} {text}")
            )
            if gender_alt == incompatible_alt or text_is_incompatible:
                skipped_gender += 1
                continue  # not eligible for this listing — skip entirely

        listings.append(
            {
                "id": listing_id,
                "title": title,
                "url": full_url,
                "price": price_match.group(1) if price_match else "?",
                "currency": price_match.group(2) if price_match else "€",
                "size": size_match.group(1) if size_match else "?",
                "available_from": date_match.group(1) if date_match else "?",
            }
        )

    if skipped_gender:
        log.info("Skipped %d listings not open to applicant_gender=%s.", skipped_gender, applicant_gender)

    return listings
