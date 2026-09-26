"""Ride-mode context and deliberately conservative planning estimates.

Waymo does not publish a universal fare formula: the app quote varies with the
route, duration, and demand.  These ranges are therefore useful for comparing
plans, but are never presented as bookable prices.
"""
import re

WAYMO_SERVICE_URL = "https://support.google.com/waymo/answer/9059119"
WAYMO_PRICING_URL = "https://support.google.com/waymo/answer/15485636"

# Public service-area list checked 2026-09-26. Keep access distinctions visible:
# Austin and Atlanta rides are booked in Uber, while several markets are rolling
# out gradually rather than being generally available.
_WAYMO_APP = {
    "dallas", "houston", "los angeles", "miami", "nashville", "orlando",
    "phoenix", "san francisco", "san francisco bay area",
}
_WAYMO_GRADUAL = {"denver", "las vegas", "san antonio", "san diego", "tampa"}
_WAYMO_UBER = {"atlanta", "austin"}


def _city_key(city: str) -> str:
    value = re.sub(r"[^a-z ]", " ", city.lower()).strip()
    # Accept common "City, ST" input without making fuzzy matches such as
    # Francisco, Indiana -> San Francisco.
    return re.sub(r"\s+", " ", value.split("  ")[0]).strip()


def waymo_coverage(city: str) -> dict:
    key = _city_key(city)
    # A comma is removed by normalization, so also try the leading city words.
    matches = [name for name in _WAYMO_APP | _WAYMO_GRADUAL | _WAYMO_UBER
               if key == name or key.startswith(name + " ")]
    name = max(matches, key=len) if matches else None
    if name in _WAYMO_APP:
        return {"available": True, "access": "Waymo app", "status": "available",
                "text": "Waymo service is listed for this city", "source": WAYMO_SERVICE_URL}
    if name in _WAYMO_GRADUAL:
        return {"available": True, "access": "limited rollout", "status": "limited",
                "text": "Waymo is gradually adding riders in this city", "source": WAYMO_SERVICE_URL}
    if name in _WAYMO_UBER:
        return {"available": True, "access": "Uber app", "status": "partner",
                "text": "Waymo rides are listed through Uber in this city", "source": WAYMO_SERVICE_URL}
    return {"available": False, "access": None, "status": "not-listed",
            "text": "This city is not in Waymo's published service-area list",
            "source": WAYMO_SERVICE_URL}


def fare_range(km: float | None, minutes: int) -> dict | None:
    """Return a broad USD planning range, not a provider quote."""
    if km is None:
        return None
    miles = km * 0.621371
    drive_minutes = max(1, minutes - 4)  # exclude the planner's pickup allowance
    low = max(6, 3 + 1.20 * miles + 0.20 * drive_minutes)
    high = max(low + 2, 8 + 2.20 * miles + 0.50 * drive_minutes)
    return {"low": round(low, 2), "high": round(high, 2), "currency": "USD",
            "kind": "planning-range", "source": WAYMO_PRICING_URL}

