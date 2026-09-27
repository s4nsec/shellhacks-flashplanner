"""Google Places API (New): finding places, their hours, and their reviews.

Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
Reviews and ratings are billed at higher tiers than basic fields, so reviews are
fetched only for the shortlist. Keep results in memory for the session; the
Maps Platform terms limit storing Places content.
"""
import httpx

from . import config

BASE = "https://places.googleapis.com/v1"

SEARCH_FIELDS = ",".join("places." + f for f in [
    "id", "displayName", "location", "regularOpeningHours", "rating",
    "userRatingCount", "types", "primaryType", "formattedAddress",
    "addressComponents", "utcOffsetMinutes", "editorialSummary", "googleMapsUri",
    "accessibilityOptions", "servesVegetarianFood", "priceLevel", "priceRange",
])

# Things that show up in "attractions" searches but aren't places to visit.
SKIP_TYPES = {
    "lodging", "hotel", "motel", "hostel", "bus_station", "subway_station",
    "train_station", "transit_station", "light_rail_station", "parking", "atm",
    "bank", "car_rental", "travel_agency", "tour_agency", "real_estate_agency",
}

# Venues whose worth depends on what's on that day: films, shows, concerts, games.
VENUE_TYPES = {
    "movie_theater", "performing_arts_theater", "concert_hall", "opera_house",
    "philharmonic_hall", "amphitheatre", "comedy_club", "live_music_venue",
    "event_venue", "auditorium", "arena", "stadium",
}


def _headers(field_mask: str) -> dict:
    return {"X-Goog-Api-Key": config.MAPS_KEY, "X-Goog-FieldMask": field_mask}


async def search_text(http: httpx.AsyncClient, query: str, page_size: int = 20,
                      bias: tuple[float, float] | None = None) -> list[dict]:
    body = {"textQuery": query, "pageSize": page_size, "languageCode": config.LANGUAGE}
    if bias:
        body["locationBias"] = {"circle": {
            "center": {"latitude": bias[0], "longitude": bias[1]}, "radius": 15000.0}}
    r = await http.post(f"{BASE}/places:searchText", json=body, headers=_headers(SEARCH_FIELDS))
    r.raise_for_status()
    return r.json().get("places", [])


async def get_reviews(http: httpx.AsyncClient, place_id: str) -> list[dict]:
    """Up to 5 reviews, the most Places API returns. Each: {text, author, uri}."""
    r = await http.get(f"{BASE}/places/{place_id}", params={"languageCode": config.LANGUAGE},
                       headers=_headers("reviews"))
    r.raise_for_status()
    out = []
    for rv in r.json().get("reviews", []):
        text = (rv.get("text") or rv.get("originalText") or {}).get("text", "")
        if text:
            author = rv.get("authorAttribution", {})
            out.append({"text": text, "author": author.get("displayName", "A Google user"),
                        "uri": author.get("uri", "")})
    return out


PRICE_LEVELS = {"PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2,
                "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4}


def price(place: dict) -> dict | None:
    """Google's price per person, like Maps shows it: a range {low, high, currency}
    (high is None for "$100+"), else a level {level: 1-4} for $ to $$$$, else None."""
    rng = place.get("priceRange", {})
    if "startPrice" in rng:
        low, high = rng["startPrice"], rng.get("endPrice")
        return {"low": int(low.get("units", 0)), "high": int(high.get("units", 0)) if high else None,
                "currency": low.get("currencyCode", "")}
    level = PRICE_LEVELS.get(place.get("priceLevel"))
    return {"level": level} if level else None


def display_name(place: dict) -> str:
    return place.get("displayName", {}).get("text", "Unnamed place")


def neighborhood(place: dict) -> str:
    comps = place.get("addressComponents", [])
    for wanted in ("neighborhood", "sublocality_level_1", "sublocality"):
        for c in comps:
            if wanted in c.get("types", []):
                return c.get("longText", "")
    return ""


def is_visitable(place: dict) -> bool:
    types_ = set(place.get("types", [])) | {place.get("primaryType", "")}
    return not (types_ & SKIP_TYPES)


def is_venue(place: dict) -> bool:
    types_ = set(place.get("types", [])) | {place.get("primaryType", "")}
    return bool(types_ & VENUE_TYPES)


def opening_windows(place: dict, weekday: int) -> tuple[list[tuple[int, int]], bool]:
    """Opening windows for one day, in minutes after midnight.

    weekday uses the Places convention: 0 = Sunday ... 6 = Saturday.
    Returns (windows, hours_known). Places without published hours (squares,
    parks, viewpoints) are treated as always open, with hours_known = False.
    An empty list means closed that day.
    """
    roh = place.get("regularOpeningHours")
    if not roh or not roh.get("periods"):
        return [(0, 1440)], False
    periods = roh["periods"]
    # Open 24/7 is a single period that opens Sunday 00:00 and never closes.
    if len(periods) == 1 and "close" not in periods[0]:
        return [(0, 1440)], True
    wins = []
    for p in periods:
        o, c = p.get("open", {}), p.get("close")
        if c is None:
            continue
        od, om = o.get("day", 0), o.get("hour", 0) * 60 + o.get("minute", 0)
        cd, cm = c.get("day", 0), c.get("hour", 0) * 60 + c.get("minute", 0)
        if od == weekday:
            wins.append((om, cm if cd == od and cm > om else 1440))
        elif cd == weekday and od == (weekday - 1) % 7 and cm > 0:
            wins.append((0, cm))  # opened yesterday, closes after midnight today
    wins.sort()
    merged = []
    for w in wins:
        if merged and w[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], w[1]))
        else:
            merged.append(w)
    return merged, True
