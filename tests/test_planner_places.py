import unittest
from datetime import date

from server import places, planner


def make_session(cands, walk):
    return planner.Session(
        id="test",
        trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True},
        date="2026-09-26",
        weekday=6,
        utc_offset=0,
        sunset=None,
        hotel={"name": "Start", "lat": 0.0, "lng": 0.0},
        end_location={"name": "Finish", "lat": 0.0, "lng": 0.02},
        end_node=len(cands) + 1,
        cands=cands,
        walk=walk,
        walk_m=[[x * 100 for x in row] for row in walk],
        transit=walk,
        drive=None,
        start=540,
        deadline=720,
        now=540,
    )


class OpeningWindowsTests(unittest.TestCase):
    def test_no_published_hours_are_treated_as_unknown_always_open(self):
        self.assertEqual(([(0, 1440)], False), places.opening_windows({}, 6))

    def test_twenty_four_seven_period_is_always_open(self):
        place = {"regularOpeningHours": {"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]}}
        self.assertEqual(([(0, 1440)], True), places.opening_windows(place, 6))

    def test_overnight_hours_include_after_midnight_close(self):
        place = {"regularOpeningHours": {"periods": [
            {"open": {"day": 5, "hour": 20}, "close": {"day": 6, "hour": 2}},
            {"open": {"day": 6, "hour": 21}, "close": {"day": 0, "hour": 1}},
        ]}}
        self.assertEqual(([(0, 120), (1260, 1440)], True), places.opening_windows(place, 6))

    def test_closed_day_has_no_windows(self):
        place = {"regularOpeningHours": {"periods": [
            {"open": {"day": 1, "hour": 9}, "close": {"day": 1, "hour": 17}},
        ]}}

        self.assertEqual(([], True), places.opening_windows(place, 6))


class PlannerTests(unittest.TestCase):
    def test_intersect_returns_overlapping_ranges(self):
        self.assertEqual([(10, 20), (30, 35)], planner.intersect([(0, 20), (30, 40)], [(10, 35)]))

    def test_simulate_waits_for_fixed_time_appointment(self):
        c = planner.Cand(id="appt", name="Dinner", lat=0.0, lng=0.01, visit_min=30,
                         windows=[(0, 1440)], appointment_time=600)
        s = make_session([c], [
            [0, 10, 20],
            [10, 0, 15],
            [20, 15, 0],
        ])

        res = planner.simulate(s, [1], 540, 0)

        self.assertIsNotNone(res)
        self.assertEqual(600, res["stops"][0]["begin"])
        self.assertEqual(50, res["stops"][0]["wait"])
        self.assertIn("appointment", res["stops"][0]["notes"])
        self.assertEqual(645, res["end"])

    def test_simulate_respects_meal_window(self):
        c = planner.Cand(id="meal", name="Lunch", lat=0.0, lng=0.01, kind="meal",
                         visit_min=30, windows=[(0, 1440)])
        s = make_session([c], [
            [0, 10, 20],
            [10, 0, 15],
            [20, 15, 0],
        ])
        s.deadline = 780

        res = planner.simulate(s, [1], 540, 0)

        self.assertIsNotNone(res)
        self.assertEqual(planner.LUNCH[0], res["stops"][0]["begin"])
        self.assertIn("lunch", res["stops"][0]["notes"])

    def test_simulate_rejects_route_past_deadline(self):
        c = planner.Cand(id="stop", name="Stop", lat=0.0, lng=0.01,
                         visit_min=30, windows=[(0, 1440)])
        s = make_session([c], [
            [0, 10, 20],
            [10, 0, 15],
            [20, 15, 0],
        ])
        self.assertIsNotNone(planner.simulate(s, [1], 540, 0))

        s.deadline = 580
        self.assertIsNone(planner.simulate(s, [1], 540, 0))

    def test_simulate_uses_distinct_finish_point_for_deadline(self):
        c = planner.Cand(id="stop", name="Stop", lat=0.0, lng=0.01, visit_min=15, windows=[(0, 1440)])
        s = make_session([c], [
            [0, 10, 20],
            [10, 0, 50],
            [20, 50, 0],
        ])
        s.deadline = 600

        self.assertIsNone(planner.simulate(s, [1], 540, 0))

        s.walk[1][2] = 5
        s.walk_m[1][2] = 500
        res = planner.simulate(s, [1], 540, 0)
        self.assertIsNotNone(res)
        self.assertEqual(570, res["end"])

    def test_sunset_minutes_for_new_york_equinox(self):
        sunset = planner.sunset_minutes(40.7128, -74.0060, date(2026, 9, 22), -240)

        self.assertAlmostEqual(1135, sunset, delta=5)

    def test_sunset_minutes_returns_none_for_polar_day_and_night(self):
        self.assertIsNone(planner.sunset_minutes(69.6492, 18.9553, date(2026, 6, 21), 120))
        self.assertIsNone(planner.sunset_minutes(69.6492, 18.9553, date(2026, 12, 21), 60))


if __name__ == "__main__":
    unittest.main()
