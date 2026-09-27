import unittest

from server import planner


class TimeOfDayTests(unittest.TestCase):
    def test_bar_is_scheduled_in_the_evening(self):
        bar = planner.Cand(id="bar", name="Bar", lat=1.0, lng=1.0, score=80, kind="nightlife",
                           timing="evening", visit_min=90, windows=[(0, 1440)])
        museum = planner.Cand(id="museum", name="Museum", lat=1.0, lng=1.0, score=70, kind="museum",
                              visit_min=90, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": False, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[bar, museum], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=1260, now=600,
        )

        route = planner.solve(s, s.now, 0, [1, 2], time_limit_s=1)
        res = planner.simulate(s, route, s.now, 0)

        self.assertEqual(sorted(route), [1, 2])
        begins = {st["node"]: st["begin"] for st in res["stops"]}
        self.assertGreaterEqual(begins[1], planner.EVENING_START)

    def test_brunch_spot_is_lunch_only_before_noon(self):
        brunch = planner.Cand(id="brunch", name="Brunch", lat=1.0, lng=1.0, score=80, kind="meal",
                              timing="morning", visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": False,
                  "meals": [{"name": "lunch", "time": "12:30"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[brunch], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=1260, now=600,
        )

        self.assertEqual(planner.allowed_starts(s, 1, s.now), [(690, 719)])

    def test_daytime_park_visit_ends_by_sunset(self):
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80, kind="park",
                            setting="outdoor", timing="daytime", visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": False, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=1080,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[park], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=1260, now=600,
        )

        self.assertEqual(planner.allowed_starts(s, 1, s.now), [(600, 1020)])

    def test_night_view_starts_after_sunset(self):
        view = planner.Cand(id="view", name="View", lat=1.0, lng=1.0, score=80, kind="viewpoint",
                            setting="outdoor", timing="night", visit_min=30, windows=[(0, 1440)])
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": False, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=1230,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[view], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=1320, now=600,
        )

        self.assertEqual(planner.allowed_starts(s, 1, s.now), [(1230, 1290)])

    def test_must_see_ignores_time_of_day(self):
        bar = planner.Cand(id="bar", name="Bar", lat=1.0, lng=1.0, score=95, kind="nightlife",
                           timing="evening", visit_min=90, windows=[(0, 1440)], must=True)
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": False, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[bar], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=960, now=600,
        )

        self.assertEqual(planner.allowed_starts(s, 1, s.now), [(600, 870)])

    def test_evening_place_in_a_daytime_trip_says_why_it_was_left_out(self):
        bar = planner.Cand(id="bar", name="Bar", lat=1.0, lng=1.0, score=80, kind="nightlife",
                           timing="evening", visit_min=90, windows=[(0, 1440)])
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": False, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[bar], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=960, now=600,
        )

        cuts = planner.cut_reasons(s, [1], [], s.now)

        self.assertEqual(cuts[0]["why"], "Best in the evening, outside your time window")

    def test_daytime_park_does_not_stretch_past_sunset(self):
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80, kind="park",
                            setting="outdoor", timing="daytime", visit_min=60, windows=[(0, 1440)])
        dinner = planner.Cand(id="dinner", name="Dinner", lat=1.0, lng=1.0, score=80, kind="meal",
                              visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True,
                  "meals": [{"name": "dinner", "time": "19:00"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=1050,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[park, dinner], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=960, deadline=1260, now=960,
        )

        res = planner.simulate(s, [1, 2], s.start, 0)

        self.assertEqual((res["stops"][0]["begin"], res["stops"][0]["leave"]), (970, 1050))
        self.assertEqual(res["stops"][1]["begin"], 1080)


if __name__ == "__main__":
    unittest.main()
