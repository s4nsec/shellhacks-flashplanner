import asyncio
import json
import unittest
from unittest import mock

from server import main
from server.models import DayWindow, TripRequest


class MultiDayModelTests(unittest.TestCase):
    def test_trip_accepts_per_day_hours(self):
        trip = TripRequest(city="Montreal", days=2, day_windows=[
            DayWindow(start_time="09:00", end_time="17:00"),
            DayWindow(start_time="11:00", end_time="20:00"),
        ])

        self.assertEqual(2, trip.days)
        self.assertEqual("11:00", trip.day_windows[1].start_time)

    def test_days_are_limited_to_one_week(self):
        with self.assertRaises(ValueError):
            TripRequest(city="Montreal", days=8)


class MultiDayStreamTests(unittest.TestCase):
    def test_days_use_distinct_dates_hours_places_and_zone_preferences(self):
        calls = []

        async def fake_plan_stream(req, exclude_place_ids=None, avoid_zones=None):
            calls.append((req, set(exclude_place_ids or ()), set(avoid_zones or ())))
            day = len(calls)
            yield json.dumps({"type": "step", "key": "find", "title": "Find places"}) + "\n"
            yield json.dumps({
                "type": "plan", "session_id": f"s{day}", "date": req.date,
                "completed": [], "stops": [{"id": f"p{day}", "zone": f"z{day}"}],
            }) + "\n"

        req = TripRequest(city="Montreal", date="2026-10-01", days=2, day_windows=[
            DayWindow(start_time="09:00", end_time="17:00"),
            DayWindow(start_time="11:00", end_time="20:00"),
        ])
        async def collect():
            return [json.loads(line) async for line in main.multi_day_plan_stream(req)]

        with mock.patch.object(main, "plan_stream", fake_plan_stream):
            events = asyncio.run(collect())

        self.assertEqual("2026-10-01", calls[0][0].date)
        self.assertEqual("2026-10-02", calls[1][0].date)
        self.assertEqual(("09:00", "17:00"), (calls[0][0].start_time, calls[0][0].end_time))
        self.assertEqual(("11:00", "20:00"), (calls[1][0].start_time, calls[1][0].end_time))
        self.assertEqual({"p1"}, calls[1][1])
        self.assertEqual({"z1"}, calls[1][2])
        self.assertEqual(["s1", "s2"], [d["session_id"] for d in events[-1]["days"]])
        self.assertEqual("day-2-find", events[1]["key"])

    def test_candidate_places_pass_through_with_their_day(self):
        async def fake_plan_stream(req, exclude_place_ids=None, avoid_zones=None):
            yield json.dumps({"type": "places", "stage": "found",
                              "places": [{"id": "p", "name": "P", "lat": 1, "lng": 2}]}) + "\n"
            yield json.dumps({"type": "plan", "session_id": "s", "date": req.date,
                              "completed": [], "stops": []}) + "\n"

        req = TripRequest(city="Montreal", date="2026-10-01", days=2)
        async def collect():
            return [json.loads(line) async for line in main.multi_day_plan_stream(req)]

        with mock.patch.object(main, "plan_stream", fake_plan_stream):
            events = asyncio.run(collect())

        places = [e for e in events if e["type"] == "places"]
        self.assertEqual([1, 2], [e["day"] for e in places])
        self.assertEqual("found", places[0]["stage"])


if __name__ == "__main__":
    unittest.main()
