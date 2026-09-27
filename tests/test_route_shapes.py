import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import httpx

from server import main, planner, routes


def _session():
    a = planner.Cand(id="a", name="a", lat=0.0, lng=0.01, score=80, visit_min=60, windows=[(0, 1440)])
    travel = [[0, 20], [20, 0]]
    return planner.Session(
        id="shapes", trip={"city": "Testville", "pace": "normal", "getting_around": "transit",
                           "by_neighborhood": False, "loves": [], "skips": []},
        date=(datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat(), weekday=0, utc_offset=-240,
        sunset=None, hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
        end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0, cands=[a],
        walk=[[0, 40], [40, 0]], walk_m=[[0, 4000], [4000, 0]], transit=travel,
        drive=None, start=600, deadline=900, now=600, route=[1])


class RouteShapeTests(unittest.TestCase):
    def test_transit_shapes_ask_for_the_legs_departure_time(self):
        s = _session()
        shape = mock.AsyncMock(return_value="enc")
        with mock.patch.object(main.routes, "polyline", shape):
            asyncio.run(main._fetch_polylines(None, s))

        departures = sorted(c.args[4] for c in shape.call_args_list)
        # Leaves the hotel at 10:00 local (UTC-4) and a's 20 + 60 minutes later: 14:00 and 15:20 UTC.
        self.assertEqual(departures, [f"{s.date}T14:00:00Z", f"{s.date}T15:20:00Z"])
        self.assertEqual(s.polylines[(0, 1, "transit")], "enc")
        self.assertEqual(s.polylines[(1, 0, "transit")], "enc")

    def test_transit_without_a_route_falls_back_to_walking_streets(self):
        seen = []

        async def fake(http, a, b, mode, dep=None):
            seen.append((mode, dep is not None))
            return "walked" if mode == "WALK" else None

        with mock.patch.object(routes, "polyline", fake):
            got = asyncio.run(routes.leg_shape(None, (0, 0), (0, 1), "TRANSIT", "2026-10-01T14:00:00Z"))

        self.assertEqual(got, "walked")
        self.assertEqual(seen, [("TRANSIT", True), ("TRANSIT", False), ("WALK", False)])

    def test_failed_request_does_not_stop_the_fallback(self):
        calls = []

        async def fake(http, a, b, mode, dep=None):
            calls.append(mode)
            if len(calls) == 1:
                raise httpx.HTTPError("quota")
            return "again"

        with mock.patch.object(routes, "polyline", fake):
            self.assertEqual(asyncio.run(routes.leg_shape(None, (0, 0), (0, 1), "TRANSIT", None)), "again")

    def test_walk_legs_have_no_fallback(self):
        with mock.patch.object(routes, "polyline", mock.AsyncMock(return_value=None)) as p:
            self.assertIsNone(asyncio.run(routes.leg_shape(None, (0, 0), (0, 1), "WALK")))
        self.assertEqual(p.await_count, 1)


if __name__ == "__main__":
    unittest.main()
