import unittest

from server import main, planner


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
