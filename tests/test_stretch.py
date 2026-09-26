import unittest

from server import planner


class StretchTests(unittest.TestCase):
    def test_wait_before_dinner_becomes_a_longer_park_visit(self):
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80, kind="park",
                            setting="outdoor", visit_min=60, windows=[(0, 1440)])
        dinner = planner.Cand(id="dinner", name="Dinner", lat=1.0, lng=1.0, score=80, kind="meal",
                              visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True,
                  "meals": [{"name": "dinner", "time": "19:00"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[park, dinner], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=960, deadline=1260, now=960,
        )

        res = planner.simulate(s, [1, 2], s.start, 0)

        self.assertEqual((res["stops"][0]["begin"], res["stops"][0]["leave"]), (970, 1070))
        self.assertEqual((res["stops"][1]["arrive"], res["stops"][1]["begin"]), (1080, 1080))
        self.assertEqual(res["waited"], 0)

    def test_stretch_is_capped_at_double_the_visit(self):
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80, kind="park",
                            setting="outdoor", visit_min=60, windows=[(0, 1440)])
        dinner = planner.Cand(id="dinner", name="Dinner", lat=1.0, lng=1.0, score=80, kind="meal",
                              visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True,
                  "meals": [{"name": "dinner", "time": "19:00"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[park, dinner], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=890, deadline=1260, now=890,
        )

        res = planner.simulate(s, [1, 2], s.start, 0)

        self.assertEqual(res["stops"][0]["leave"] - res["stops"][0]["begin"], 120)
        self.assertEqual(res["depart"], 940)
        self.assertEqual((res["stops"][1]["arrive"], res["stops"][1]["begin"]), (1080, 1080))
        self.assertEqual(res["waited"], 0)

    def test_stretch_stops_at_closing_time(self):
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80, kind="park",
                            setting="outdoor", visit_min=60, windows=[(0, 1040)])
        dinner = planner.Cand(id="dinner", name="Dinner", lat=1.0, lng=1.0, score=80, kind="meal",
                              visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True,
                  "meals": [{"name": "dinner", "time": "19:00"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[park, dinner], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=960, deadline=1260, now=960,
        )

        res = planner.simulate(s, [1, 2], s.start, 0)

        self.assertEqual(res["stops"][0]["leave"], 1040)
        self.assertEqual(res["waited"], 30)

    def test_stretch_stops_before_rain_at_an_outdoor_place(self):
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80, kind="park",
                            setting="outdoor", visit_min=60, windows=[(0, 1440)])
        dinner = planner.Cand(id="dinner", name="Dinner", lat=1.0, lng=1.0, score=80, kind="meal",
                              visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True,
                  "meals": [{"name": "dinner", "time": "19:00"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[park, dinner], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=900, deadline=1260, now=900, rain_hours={17},
        )

        res = planner.simulate(s, [1, 2], s.start, 0)

        self.assertEqual(res["stops"][0]["leave"], 1020)
        self.assertEqual(res["waited"], 50)

    def test_lunch_is_not_stretched_to_fill_a_wait(self):
        lunch = planner.Cand(id="lunch", name="Lunch", lat=1.0, lng=1.0, score=80, kind="meal",
                             visit_min=60, windows=[(0, 1440)])
        tower = planner.Cand(id="tower", name="Tower", lat=1.0, lng=1.0, score=80, kind="sight",
                             visit_min=45, windows=[(840, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True,
                  "meals": [{"name": "lunch", "time": "12:30"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[lunch, tower], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=680, deadline=1140, now=680,
        )

        res = planner.simulate(s, [1, 2], s.start, 0)

        self.assertEqual(res["depart"], 760)
        self.assertEqual((res["stops"][0]["begin"], res["stops"][0]["leave"]), (770, 830))
        self.assertEqual((res["stops"][1]["arrive"], res["stops"][1]["begin"]), (840, 840))
        self.assertEqual(res["waited"], 0)

    def test_wait_is_spread_over_several_earlier_stops(self):
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80, kind="park",
                            setting="outdoor", visit_min=60, windows=[(0, 1440)])
        fountain = planner.Cand(id="fountain", name="Fountain", lat=1.0, lng=1.0, score=80, kind="sight",
                                setting="outdoor", visit_min=15, windows=[(0, 1440)])
        dinner = planner.Cand(id="dinner", name="Dinner", lat=1.0, lng=1.0, score=80, kind="meal",
                              visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10, 10], [10, 0, 10, 10], [10, 10, 0, 10], [10, 10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True,
                  "meals": [{"name": "dinner", "time": "19:00"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[park, fountain, dinner], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=900, deadline=1260, now=900,
        )

        res = planner.simulate(s, [1, 2, 3], s.start, 0)

        self.assertEqual(res["depart"], 900)
        self.assertEqual((res["stops"][0]["begin"], res["stops"][0]["leave"]), (910, 1030))
        self.assertEqual((res["stops"][1]["begin"], res["stops"][1]["leave"]), (1040, 1070))
        self.assertEqual((res["stops"][2]["arrive"], res["stops"][2]["begin"]), (1080, 1080))
        self.assertEqual(res["waited"], 0)

    def test_wait_before_the_first_stop_becomes_a_later_departure(self):
        tower = planner.Cand(id="tower", name="Tower", lat=1.0, lng=1.0, score=80, kind="sight",
                             visit_min=45, windows=[(840, 1440)])
        travel = [[0, 10], [10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[tower], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=1140, now=600,
        )

        res = planner.simulate(s, [1], s.start, 0)

        self.assertEqual(res["depart"], 830)
        self.assertEqual((res["stops"][0]["arrive"], res["stops"][0]["begin"]), (840, 840))
        self.assertEqual(res["waited"], 0)


if __name__ == "__main__":
    unittest.main()
