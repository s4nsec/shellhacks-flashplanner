import unittest

from server import planner


class ActivityLimitTests(unittest.TestCase):
    def test_long_day_keeps_sightseeing_within_the_pace_limit(self):
        cands = [planner.Cand(id=f"sight{i}", name=f"Sight {i}", lat=1.0, lng=1.0, score=90,
                              visit_min=60, windows=[(0, 1440)]) for i in range(6)]
        travel = [[0 if a == b else 10 for b in range(7)] for a in range(7)]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "transit", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=cands, walk=travel, walk_m=[[0 if a == b else 800 for b in range(7)] for a in range(7)],
            transit=travel, drive=None, start=540, deadline=1260, now=540,
        )

        self.assertEqual(planner.activity_left_min(s), 240)
        self.assertEqual(len(planner.solve(s, s.start, 0, [1, 2, 3, 4, 5, 6], time_limit_s=1)), 3)

        s.trip["pace"] = "normal"
        self.assertEqual(planner.activity_left_min(s), 330)
        self.assertEqual(len(planner.solve(s, s.start, 0, [1, 2, 3, 4, 5, 6], time_limit_s=1)), 5)

        s.trip["pace"] = "packed"
        self.assertEqual(planner.activity_left_min(s), 450)
        self.assertEqual(len(planner.solve(s, s.start, 0, [1, 2, 3, 4, 5, 6], time_limit_s=1)), 6)

    def test_meals_and_snacks_do_not_count_as_sightseeing(self):
        cands = [planner.Cand(id=f"sight{i}", name=f"Sight {i}", lat=1.0, lng=1.0, score=90,
                              visit_min=60, windows=[(0, 1440)]) for i in range(3)]
        cands.append(planner.Cand(id="bistro", name="Bistro", lat=1.0, lng=1.0, score=80,
                                  kind="meal", visit_min=60, windows=[(0, 1440)]))
        cands.append(planner.Cand(id="cafe", name="Cafe", lat=1.0, lng=1.0, score=80,
                                  kind="snack", visit_min=20, windows=[(0, 1440)]))
        travel = [[0 if a == b else 10 for b in range(6)] for a in range(6)]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "transit", "by_neighborhood": True,
                  "meals": [{"name": "lunch", "time": "12:30"}]},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=cands, walk=travel, walk_m=[[0 if a == b else 800 for b in range(6)] for a in range(6)],
            transit=travel, drive=None, start=540, deadline=1260, now=540,
        )

        self.assertEqual(planner.activity_min(s, 1), 75)
        self.assertEqual(planner.activity_min(s, 4), 0)
        self.assertEqual(planner.activity_min(s, 5), 0)
        self.assertEqual(sorted(planner.solve(s, s.start, 0, [1, 2, 3, 4, 5], time_limit_s=1)), [1, 2, 3, 4, 5])

    def test_must_see_places_stay_even_past_the_limit(self):
        cands = [planner.Cand(id=f"must{i}", name=f"Must {i}", lat=1.0, lng=1.0, score=90,
                              visit_min=60, windows=[(0, 1440)], must=True) for i in range(4)]
        cands.append(planner.Cand(id="extra", name="Extra", lat=1.0, lng=1.0, score=90,
                                  visit_min=60, windows=[(0, 1440)]))
        travel = [[0 if a == b else 10 for b in range(6)] for a in range(6)]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "transit", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=cands, walk=travel, walk_m=[[0 if a == b else 800 for b in range(6)] for a in range(6)],
            transit=travel, drive=None, start=540, deadline=1260, now=540,
        )

        self.assertEqual(sorted(planner.solve(s, s.start, 0, [1, 2, 3, 4, 5], time_limit_s=1)), [1, 2, 3, 4])

    def test_sightseeing_already_done_counts_against_the_limit(self):
        done = planner.Cand(id="done", name="Done", lat=1.0, lng=1.0, score=90,
                            visit_min=180, windows=[(0, 1440)])
        next_up = planner.Cand(id="next", name="Next", lat=1.0, lng=1.0, score=90,
                               visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "transit", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[done, next_up], walk=travel, walk_m=[[0, 800, 800], [800, 0, 800], [800, 800, 0]],
            transit=travel, drive=None, start=540, deadline=1260, now=775, loc=1,
            completed=[{"node": 1, "notes": [], "leg": {"mode": "walk", "min": 10, "km": 0.8}}],
        )

        self.assertEqual(planner.activity_left_min(s), 15)
        self.assertEqual(planner.solve(s, s.now, 1, [2], time_limit_s=1), [])

    def test_baseline_stays_within_the_activity_limit(self):
        cands = [planner.Cand(id=f"sight{i}", name=f"Sight {i}", lat=1.0, lng=1.0, score=90,
                              visit_min=60, windows=[(0, 1440)], list_rank=i) for i in range(6)]
        travel = [[0 if a == b else 10 for b in range(7)] for a in range(7)]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "transit", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=cands, walk=travel, walk_m=[[0 if a == b else 800 for b in range(7)] for a in range(7)],
            transit=travel, drive=None, start=540, deadline=1260, now=540,
        )

        self.assertEqual(planner.naive(s, s.start, 0, [1, 2, 3, 4, 5, 6]), [1, 2, 3])

    def test_cut_reason_names_the_pace(self):
        cands = [planner.Cand(id=f"sight{i}", name=f"Sight {i}", lat=1.0, lng=1.0, score=90 - i,
                              visit_min=60, windows=[(0, 1440)]) for i in range(4)]
        travel = [[0 if a == b else 10 for b in range(5)] for a in range(5)]
        s = planner.Session(
            id="test",
            trip={"pace": "relaxed", "getting_around": "transit", "by_neighborhood": True, "meals": []},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=cands, walk=travel, walk_m=[[0 if a == b else 800 for b in range(5)] for a in range(5)],
            transit=travel, drive=None, start=540, deadline=1260, now=540,
        )

        cuts = planner.cut_reasons(s, [1, 2, 3, 4], [1, 2, 3], s.start)

        self.assertEqual([c["why"] for c in cuts], ["Would pack too much into a relaxed-pace day"])


if __name__ == "__main__":
    unittest.main()
