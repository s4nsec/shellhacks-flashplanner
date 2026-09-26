import asyncio
import unittest
from unittest import mock

from server import main, planner
from server.models import TripRequest


def resolve_end(trip: TripRequest, hits: list[dict]):
    queries = []

    async def fake_search(http, query, page_size=20, bias=None):
        queries.append((query, bias))
        return hits

    hotel = {"name": "Hotel", "lat": 45.5, "lng": -73.57}
    with mock.patch.object(main.places, "search_text", fake_search):
        result = asyncio.run(main.resolve_end(None, trip.model_dump(), trip.city, hotel))
    return result, queries


def session() -> planner.Session:
    candidate = planner.Cand(
        id="museum",
        name="Museum",
        lat=1.0,
        lng=1.0,
        score=100,
        visit_min=30,
        windows=[(0, 1440)],
    )
    # Nodes: 0 = hotel/start, 1 = candidate, 2 = station/end.
    walk = [
        [0, 10, 40],
        [5, 0, 20],
        [40, 20, 0],
    ]
    distances = [[minutes * 100 for minutes in row] for row in walk]
    return planner.Session(
        id="test",
        trip={"city": "Testville", "pace": "normal", "getting_around": "walk",
              "by_neighborhood": True, "loves": [], "skips": []},
        date="2026-09-26",
        weekday=6,
        utc_offset=0,
        sunset=None,
        hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
        end_location={"name": "Central Station", "lat": 2.0, "lng": 2.0},
        end_node=2,
        cands=[candidate],
        walk=walk,
        walk_m=distances,
        transit=walk,
        drive=None,
        start=100,
        deadline=200,
        now=100,
    )


class EndLocationTests(unittest.TestCase):
    def test_picked_end_place_is_not_looked_up_again(self):
        trip = TripRequest(city="Montreal", end_location="Central Station",
                           end_place={"place_id": "abc", "name": "Gare Centrale",
                                      "lat": 45.499, "lng": -73.566})

        place, queries = resolve_end(trip, [])

        self.assertEqual(place, {"name": "Gare Centrale", "lat": 45.499, "lng": -73.566})
        self.assertEqual(queries, [])

    def test_typed_end_location_is_searched_with_start_bias(self):
        trip = TripRequest(city="Montreal", end_location="Central Station")
        hit = {"displayName": {"text": "Gare Centrale"},
               "location": {"latitude": 45.499, "longitude": -73.566}}

        place, queries = resolve_end(trip, [hit])

        self.assertEqual(place["name"], "Gare Centrale")
        self.assertEqual(queries, [("Central Station, Montreal", (45.5, -73.57))])

    def test_picked_end_place_rejects_bad_coordinates(self):
        with self.assertRaises(ValueError):
            TripRequest(city="Montreal", end_place={"name": "X", "lat": 0, "lng": 999})

    def test_demo_defaults_end_location_to_start(self):
        payload = main.demo_plan()

        self.assertEqual(payload["end_location"], payload["hotel"])

    def test_simulate_finishes_at_distinct_end_node(self):
        s = session()

        result = planner.simulate(s, [1], s.start, 0)

        self.assertIsNotNone(result)
        self.assertEqual(result["back"]["from"], 1)
        self.assertEqual(result["back"]["min"], 20)
        self.assertEqual(result["end"], 160)
        self.assertEqual(s.point(s.end_node), (2.0, 2.0))

    def test_missing_end_location_still_returns_to_start(self):
        s = session()
        s.end_location = s.hotel
        s.end_node = 0

        result = planner.simulate(s, [1], s.start, 0)

        self.assertIsNotNone(result)
        self.assertEqual(result["back"]["min"], 5)
        self.assertEqual(result["end"], 145)

    def test_payload_exposes_end_location_and_final_polyline(self):
        s = session()
        s.route = [1]
        s.polylines[(1, s.end_node, "walk")] = "encoded-final-leg"

        payload = main._payload(s, "A good day.", [])

        self.assertEqual(payload["end_location"]["name"], "Central Station")
        self.assertEqual(payload["back"]["polyline"], "encoded-final-leg")


if __name__ == "__main__":
    unittest.main()
