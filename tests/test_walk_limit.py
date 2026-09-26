import unittest

from server import planner


class WalkLimitTests(unittest.TestCase):
    def test_walk_only_day_stays_within_the_pace_walking_limit(self):
        tower = planner.Cand(id="tower", name="Tower", lat=1.0, lng=1.0, score=90,
                             visit_min=45, windows=[(0, 1440)])
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80,
                            visit_min=45, windows=[(0, 1440)])
        travel = [[0, 18, 18], [18, 0, 18], [18, 18, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "walk", "by_neighborhood": True},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[tower, park], walk=travel, walk_m=[[0, 1500, 1500], [1500, 0, 1500], [1500, 1500, 0]],
            transit=travel, drive=None, start=600, deadline=1140, now=600,
        )

        self.assertEqual(planner.walk_left_m(s), 4000)
        self.assertEqual(planner.solve(s, s.start, 0, [1, 2], time_limit_s=1), [1])

        s.trip["pace"] = "normal"
        self.assertEqual(planner.walk_left_m(s), 6000)
        self.assertEqual(sorted(planner.solve(s, s.start, 0, [1, 2], time_limit_s=1)), [1, 2])

        s.trip["pace"] = "packed"
        self.assertEqual(planner.walk_left_m(s), 10000)

    def test_transit_day_has_no_walking_limit(self):
        tower = planner.Cand(id="tower", name="Tower", lat=1.0, lng=1.0, score=90,
                             visit_min=45, windows=[(0, 1440)])
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80,
                            visit_min=45, windows=[(0, 1440)])
        travel = [[0, 18, 18], [18, 0, 18], [18, 18, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "transit", "by_neighborhood": True},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[tower, park], walk=travel, walk_m=[[0, 1500, 1500], [1500, 0, 1500], [1500, 1500, 0]],
            transit=travel, drive=None, start=600, deadline=1140, now=600,
        )

        self.assertIsNone(planner.walk_left_m(s))
        self.assertEqual(sorted(planner.solve(s, s.start, 0, [1, 2], time_limit_s=1)), [1, 2])

    def test_walking_already_done_counts_against_the_limit(self):
        done = planner.Cand(id="done", name="Done", lat=1.0, lng=1.0, score=90,
                            visit_min=45, windows=[(0, 1440)])
        next_up = planner.Cand(id="next", name="Next", lat=1.0, lng=1.0, score=90,
                               visit_min=45, windows=[(0, 1440)])
        travel = [[0, 18, 18], [18, 0, 18], [18, 18, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[done, next_up], walk=travel, walk_m=[[0, 1500, 1500], [1500, 0, 1500], [1500, 1500, 0]],
            transit=travel, drive=None, start=600, deadline=1140, now=700, loc=1,
            completed=[{"node": 1, "notes": [], "leg": {"mode": "walk", "min": 45, "km": 3.5}}],
        )

        self.assertEqual(planner.walk_left_m(s), 2500)
        self.assertEqual(planner.solve(s, s.now, 1, [2], time_limit_s=1), [])

    def test_baseline_stays_within_the_walking_limit(self):
        tower = planner.Cand(id="tower", name="Tower", lat=1.0, lng=1.0, score=90,
                             visit_min=45, windows=[(0, 1440)], list_rank=0)
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80,
                            visit_min=45, windows=[(0, 1440)], list_rank=1)
        travel = [[0, 18, 18], [18, 0, 18], [18, 18, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "walk", "by_neighborhood": True},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[tower, park], walk=travel, walk_m=[[0, 1500, 1500], [1500, 0, 1500], [1500, 1500, 0]],
            transit=travel, drive=None, start=600, deadline=1140, now=600,
        )

        self.assertEqual(planner.naive(s, s.start, 0, [1, 2]), [1])

    def test_cut_reason_names_the_walking_limit(self):
        tower = planner.Cand(id="tower", name="Tower", lat=1.0, lng=1.0, score=90,
                             visit_min=45, windows=[(0, 1440)])
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=80,
                            visit_min=45, windows=[(0, 1440)])
        travel = [[0, 18, 18], [18, 0, 18], [18, 18, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "walk", "by_neighborhood": True},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[tower, park], walk=travel, walk_m=[[0, 1500, 1500], [1500, 0, 1500], [1500, 1500, 0]],
            transit=travel, drive=None, start=600, deadline=1140, now=600,
        )

        cuts = planner.cut_reasons(s, [1, 2], [1], s.start)

        self.assertEqual([c["why"] for c in cuts], ["Would go over your 4 km walking limit"])


if __name__ == "__main__":
    unittest.main()
