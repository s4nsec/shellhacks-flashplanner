import asyncio
import unittest
from unittest import mock

from server import gemini, main, planner
from server.models import ParseRequest, TripRequest


class BudgetTests(unittest.TestCase):
    def test_trip_request_budget_defaults_to_no_limit(self):
        self.assertIsNone(TripRequest(city="Montreal").budget)
        self.assertEqual(TripRequest(city="Montreal", budget=80).budget, 80)

    def test_trip_request_rejects_negative_budget(self):
        with self.assertRaises(ValueError):
            TripRequest(city="Montreal", budget=-1)

    def test_parse_passes_budget_through_and_unset_budget_as_none(self):
        fields = dict(city="Montreal", date="", relative_day="", start_time="", end_time="",
                      start_location="", end_location="", loves=[], skips=[], must_see=[],
                      appointments=[], pace="normal", getting_around="transit", by_neighborhood=True)
        with mock.patch.object(main.config, "GEMINI_API_KEY", "test"), \
             mock.patch.object(main.gemini, "parse_trip",
                               mock.AsyncMock(return_value=gemini.ParsedTrip(**fields, budget=120))):
            with_budget = asyncio.run(main.parse(ParseRequest(message="Montreal on $120")))
        with mock.patch.object(main.config, "GEMINI_API_KEY", "test"), \
             mock.patch.object(main.gemini, "parse_trip",
                               mock.AsyncMock(return_value=gemini.ParsedTrip(**fields, budget=-1))):
            without = asyncio.run(main.parse(ParseRequest(message="Montreal")))

        self.assertEqual(with_budget["budget"], 120)
        self.assertIsNone(without["budget"])

    def test_solver_keeps_spend_within_budget(self):
        museum = planner.Cand(id="museum", name="Museum", lat=1.0, lng=1.0, score=90,
                              visit_min=45, windows=[(0, 1440)], cost=30)
        tower = planner.Cand(id="tower", name="Tower", lat=1.0, lng=1.0, score=80,
                             visit_min=45, windows=[(0, 1440)], cost=30)
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "budget": 40},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[museum, tower], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=900, now=600,
        )

        self.assertEqual(planner.solve(s, s.start, 0, [1, 2], time_limit_s=1), [1])

        s.trip["budget"] = None
        self.assertEqual(sorted(planner.solve(s, s.start, 0, [1, 2], time_limit_s=1)), [1, 2])

    def test_zero_budget_keeps_only_free_places(self):
        park = planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=60,
                            visit_min=45, windows=[(0, 1440)], cost=0)
        museum = planner.Cand(id="museum", name="Museum", lat=1.0, lng=1.0, score=90,
                              visit_min=45, windows=[(0, 1440)], cost=25)
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "budget": 0},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[park, museum], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=900, now=600,
        )

        self.assertEqual(planner.solve(s, s.start, 0, [1, 2], time_limit_s=1), [1])

    def test_completed_stops_count_against_budget(self):
        done = planner.Cand(id="done", name="Done", lat=1.0, lng=1.0, score=90,
                            visit_min=45, windows=[(0, 1440)], cost=30)
        next_up = planner.Cand(id="next", name="Next", lat=1.0, lng=1.0, score=90,
                               visit_min=45, windows=[(0, 1440)], cost=30)
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "budget": 50},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[done, next_up], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=900, now=655, loc=1,
            completed=[{"node": 1, "notes": []}],
        )

        self.assertEqual(planner.budget_left(s), 20)
        self.assertEqual(planner.solve(s, s.now, 1, [2], time_limit_s=1), [])

    def test_baseline_skips_places_over_budget(self):
        pricey = planner.Cand(id="pricey", name="Pricey", lat=1.0, lng=1.0, score=90,
                              visit_min=45, windows=[(0, 1440)], cost=50, list_rank=0)
        cheap = planner.Cand(id="cheap", name="Cheap", lat=1.0, lng=1.0, score=80,
                             visit_min=45, windows=[(0, 1440)], cost=10, list_rank=1)
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "budget": 40},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[pricey, cheap], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=900, now=600,
        )

        self.assertEqual(planner.naive(s, s.start, 0, [1, 2]), [2])

    def test_cut_reason_names_the_budget(self):
        cheap = planner.Cand(id="cheap", name="Cheap", lat=1.0, lng=1.0, score=90,
                             visit_min=45, windows=[(0, 1440)], cost=10)
        pricey = planner.Cand(id="pricey", name="Pricey", lat=1.0, lng=1.0, score=80,
                              visit_min=45, windows=[(0, 1440)], cost=35)
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="test",
            trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True, "budget": 40},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
            cands=[cheap, pricey], walk=travel, walk_m=[[x * 100 for x in row] for row in travel],
            transit=travel, drive=None, start=600, deadline=900, now=600,
        )

        cuts = planner.cut_reasons(s, [1, 2], [1], s.start)

        self.assertEqual([c["why"] for c in cuts], ["Would go over your budget"])


if __name__ == "__main__":
    unittest.main()
