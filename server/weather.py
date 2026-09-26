"""Google Weather API: which hours of the day are likely to be rainy.

Docs: https://developers.google.com/maps/documentation/weather/hourly-forecast
The hourly forecast starts at the current hour and reaches 240 hours ahead, 24
hours per page. Hours already past, or days further out, have no forecast and
are planned as dry.
"""
import math
from datetime import date as Date, datetime, timedelta, timezone

import httpx

from . import config

URL = "https://weather.googleapis.com/v1/forecast/hours:lookup"
MAX_HOURS = 240
RAIN_MIN_PROB = 50   # an hour counts as rainy from this chance of precipitation, in percent


async def hourly(http: httpx.AsyncClient, lat: float, lng: float, day: Date, utc_offset: int) -> list[dict]:
    """One entry per remaining local hour of the day: {hour, prob, mm}."""
    day_end = datetime.combine(day + timedelta(days=1), datetime.min.time()) - timedelta(minutes=utc_offset)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    needed = math.ceil((day_end - now) / timedelta(hours=1))
    if needed <= 0 or needed - 24 >= MAX_HOURS:   # the day is over, or starts past the forecast
        return []
    params = {"location.latitude": lat, "location.longitude": lng, "hours": min(MAX_HOURS, needed),
              "pageSize": 24}
    out = []
    while True:
        r = await http.get(URL, params=params, headers={"X-Goog-Api-Key": config.MAPS_KEY})
        r.raise_for_status()
        data = r.json()
        for h in data.get("forecastHours", []):
            d = h["displayDateTime"]
            if Date(d["year"], d["month"], d["day"]) == day:
                p = h.get("precipitation", {})
                out.append({"hour": d.get("hours", 0), "prob": p.get("probability", {}).get("percent", 0),
                            "mm": p.get("qpf", {}).get("quantity", 0)})
        if not data.get("nextPageToken"):
            return out
        params["pageToken"] = data["nextPageToken"]


def rain_hours(forecast: list[dict]) -> set[int]:
    return {x["hour"] for x in forecast if x["prob"] >= RAIN_MIN_PROB}
