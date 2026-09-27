import unittest
from datetime import date

from server import planner


class DaylightTests(unittest.TestCase):
    def test_sunrise_minutes_for_new_york_equinox(self):
        sunrise = planner.sunrise_minutes(40.7128, -74.0060, date(2026, 9, 22), -240)

        self.assertAlmostEqual(407, sunrise, delta=5)  # about 6:47 am EDT

    def test_sunrise_minutes_returns_none_for_polar_day_and_night(self):
        self.assertIsNone(planner.sunrise_minutes(69.6492, 18.9553, date(2026, 6, 21), 120))
        self.assertIsNone(planner.sunrise_minutes(69.6492, 18.9553, date(2026, 12, 21), 60))

    def test_daylight_park_is_left_out_after_dark(self):
        trail = planner.Cand(id="trail", name="Trail", lat=1.0, lng=1.0, score=80, kind="park",
                             setting="outdoor", daylight=True, visit_min=60, windows=[(0, 1440)])
        plaza = planner.Cand(id="plaza", name="Plaza", lat=1.0, lng=1.0, score=60, kind="sight",
                             setting="outdoor", visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=1110, sunrise=420,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[trail, plaza], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=1140, deadline=1320, now=1140,
        )

        route = planner.solve(s, s.start, 0, [1, 2], time_limit_s=1)
        cuts = planner.cut_reasons(s, [1, 2], route, s.start)

        self.assertEqual(route, [2])
        self.assertEqual(cuts, [{"id": "trail", "name": "Trail", "score": 80,
                                 "why": "Outdoors, and it would be dark by the time it fits"}])

    def test_daylight_visit_must_end_by_dusk(self):
        trail = planner.Cand(id="trail", name="Trail", lat=1.0, lng=1.0, score=80, kind="park",
                             setting="outdoor", daylight=True, visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=1110, sunrise=420,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[trail], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=1071, deadline=1320, now=1071,
        )

        self.assertIsNone(planner.simulate(s, [1], s.start, 0))
        self.assertEqual(planner.simulate(s, [1], 1070, 0)["stops"][0]["leave"], 1140)

    def test_daylight_visit_waits_for_sunrise(self):
        trail = planner.Cand(id="trail", name="Trail", lat=1.0, lng=1.0, score=80, kind="park",
                             setting="outdoor", daylight=True, visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=1110, sunrise=420,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[trail], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=360, deadline=600, now=360,
        )

        res = planner.simulate(s, [1], s.start, 0)

        self.assertEqual(res["stops"][0]["begin"], 420)

    def test_stretch_stops_at_dusk_for_a_daylight_park(self):
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80, kind="park",
                            setting="outdoor", daylight=True, visit_min=60, windows=[(0, 1440)])
        dinner = planner.Cand(id="dinner", name="Dinner", lat=1.0, lng=1.0, score=80, kind="meal",
                              visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True,
                  "meals": [{"name": "dinner", "time": "19:00"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=1010, sunrise=420,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[park, dinner], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=960, deadline=1260, now=960,
        )

        res = planner.simulate(s, [1, 2], s.start, 0)

        self.assertEqual((res["stops"][0]["begin"], res["stops"][0]["leave"]), (970, 1040))
        self.assertEqual(res["stops"][1]["begin"], 1080)

    def test_booked_time_at_a_daylight_place_is_kept_after_dark(self):
        tour = planner.Cand(id="tour", name="Night hike", lat=1.0, lng=1.0, score=80, kind="park",
                            setting="outdoor", daylight=True, visit_min=60, windows=[(0, 1440)],
                            appointment_time=1200)
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=1110, sunrise=420,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[tour], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=1140, deadline=1320, now=1140,
        )

        route = planner.solve(s, s.start, 0, [1], time_limit_s=1)

        self.assertEqual(route, [1])
        self.assertEqual(planner.simulate(s, route, s.start, 0)["stops"][0]["begin"], 1200)

    def test_daylight_is_not_limited_when_the_sun_never_sets(self):
        trail = planner.Cand(id="trail", name="Trail", lat=1.0, lng=1.0, score=80, kind="park",
                             setting="outdoor", daylight=True, visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "meals": []},
            date="2026-06-21", weekday=0, utc_offset=120, sunset=None, sunrise=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[trail], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=1320, deadline=1430, now=1320,
        )

        res = planner.simulate(s, [1], s.start, 0)

        self.assertEqual(res["stops"][0]["begin"], 1330)


if __name__ == "__main__":
    unittest.main()
