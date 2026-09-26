"""Google Routes API: travel times between every pair of places, and route shapes.

Docs: https://developers.google.com/maps/documentation/routes/compute_route_matrix
Matrix limits: 625 origin-destination pairs per request in general, 100 for
TRANSIT. Requests are split by origin rows and sent in parallel.
"""
import asyncio
import math
from datetime import datetime, timedelta

import httpx

from . import config

MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
LIMITS = {"WALK": 625, "TRANSIT": 100, "DRIVE": 625}
TRANSIT_HORIZON = timedelta(days=14)  # Google's transit timetables don't reliably reach further


def _wp(pt: tuple[float, float]) -> dict:
    return {"waypoint": {"location": {"latLng": {"latitude": pt[0], "longitude": pt[1]}}}}


def _loc(pt: tuple[float, float]) -> dict:
    return {"location": {"latLng": {"latitude": pt[0], "longitude": pt[1]}}}


def transit_departure(dep_utc: datetime, now_utc: datetime) -> datetime:
    """A departure Google has transit timetables for: the same weekday and time, moved back
    whole weeks until it's within TRANSIT_HORIZON of now. Past the horizon, Google returns
    long detours, such as 4 hours to an airport that is 1.5 hours away."""
    weeks = max(0, math.ceil((dep_utc - now_utc - TRANSIT_HORIZON) / timedelta(weeks=1)))
    return dep_utc - timedelta(weeks=weeks)


async def matrix(http: httpx.AsyncClient, pts: list[tuple[float, float]], mode: str,
                 departure_iso: str | None = None,
                 origins: list[tuple[float, float]] | None = None) -> tuple[list[list], list[list]]:
    """Returns (minutes, meters) as origins x pts lists; None where no route exists.
    Origins default to pts, giving the full n x n matrix."""
    square = origins is None
    origins = pts if square else origins
    n = len(pts)
    minutes = [[None] * n for _ in origins]
    meters = [[None] * n for _ in origins]
    rows = max(1, LIMITS[mode] // n)
    headers = {"X-Goog-Api-Key": config.MAPS_KEY,
               "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters,condition"}

    async def fetch(offset: int):
        body = {"origins": [_wp(p) for p in origins[offset:offset + rows]],
                "destinations": [_wp(p) for p in pts], "travelMode": mode}
        if mode == "TRANSIT" and departure_iso:
            body["departureTime"] = departure_iso
        if mode == "DRIVE":
            body["routingPreference"] = "TRAFFIC_AWARE"
            if departure_iso:
                body["departureTime"] = departure_iso
        r = await http.post(MATRIX_URL, json=body, headers=headers)
        r.raise_for_status()
        for e in r.json():
            # Proto3 JSON omits zero values, so index 0 arrives as a missing key.
            i = offset + e.get("originIndex", 0)
            j = e.get("destinationIndex", 0)
            if e.get("condition") == "ROUTE_EXISTS" and "duration" in e:
                minutes[i][j] = math.ceil(int(e["duration"].rstrip("s")) / 60)
                meters[i][j] = e.get("distanceMeters", 0)

    await asyncio.gather(*(fetch(o) for o in range(0, len(origins), rows)))
    if square:
        for i in range(n):
            minutes[i][i], meters[i][i] = 0, 0
    return minutes, meters


async def polyline(http: httpx.AsyncClient, a: tuple[float, float], b: tuple[float, float],
                   mode: str) -> str | None:
    """Encoded polyline for one leg, so the map draws real streets and métro lines."""
    body = {"origin": _loc(a), "destination": _loc(b), "travelMode": mode}
    r = await http.post(ROUTES_URL, json=body, headers={
        "X-Goog-Api-Key": config.MAPS_KEY, "X-Goog-FieldMask": "routes.polyline.encodedPolyline"})
    r.raise_for_status()
    routes = r.json().get("routes", [])
    return routes[0]["polyline"]["encodedPolyline"] if routes else None
