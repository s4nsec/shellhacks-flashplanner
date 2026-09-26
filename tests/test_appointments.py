import unittest

from server import planner
from server.models import TripRequest


def session(*candidates: planner.Cand) -> planner.Session:
    size = len(candidates) + 1
    travel = [[0 if i == j else 10 for j in range(size)] for i in range(size)]
    distances = [[minutes * 100 for minutes in row] for row in travel]
    return planner.Session(
        id="test",
        trip={"city": "Testville", "pace": "normal", "getting_around": "walk",
              "by_neighborhood": True, "loves": [], "skips": []},
        date="2026-09-26",
        weekday=6,
        utc_offset=0,
        sunset=None,
        hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
        end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0},
        end_node=0,
        cands=list(candidates),
        walk=travel,
        walk_m=distances,
        transit=travel,
        drive=None,
        start=600,
        deadline=900,
        now=600,
    )


class AppointmentTests(unittest.TestCase):
    def test_trip_request_accepts_place_and_time(self):
        trip = TripRequest(
            city="Montreal",
            appointments=[{"place": "Joe Beef", "time": "19:30"}],
        )

        self.assertEqual(trip.appointments[0].place, "Joe Beef")
        self.assertEqual(trip.appointments[0].time, "19:30")

    def test_simulate_waits_for_fixed_start(self):
        show = planner.Cand(
            id="show", name="Theatre", lat=1.0, lng=1.0, score=1,
            visit_min=60, windows=[(0, 1440)], appointment_time=720,
        )
        s = session(show)

        result = planner.simulate(s, [1], s.start, 0)

        self.assertIsNotNone(result)
        self.assertEqual(result["depart"], 710)
        self.assertEqual(result["stops"][0]["arrive"], 720)
        self.assertEqual(result["stops"][0]["begin"], 720)
        self.assertEqual(result["stops"][0]["wait"], 0)
        self.assertIn("appointment", result["stops"][0]["notes"])

    def test_simulate_rejects_late_arrival(self):
        show = planner.Cand(
            id="show", name="Theatre", lat=1.0, lng=1.0, score=1,
            visit_min=60, windows=[(0, 1440)], appointment_time=605,
        )
        s = session(show)

        self.assertIsNone(planner.simulate(s, [1], s.start, 0))

    def test_reservation_overrides_generic_meal_slots(self):
        brunch = planner.Cand(
            id="brunch", name="Cafe", lat=1.0, lng=1.0, score=1,
            kind="meal", visit_min=60, windows=[(0, 1440)], appointment_time=630,
        )
        s = session(brunch)

        result = planner.simulate(s, [1], s.start, 0)

        self.assertIsNotNone(result)
        self.assertEqual(result["stops"][0]["begin"], 630)

    def test_solver_keeps_low_score_appointment_at_exact_time(self):
        show = planner.Cand(
            id="show", name="Theatre", lat=1.0, lng=1.0, score=0,
            visit_min=60, windows=[(0, 1440)], appointment_time=720,
        )
        s = session(show)

        route = planner.solve(s, s.start, 0, [1], time_limit_s=1)
        result = planner.simulate(s, route, s.start, 0)

        self.assertEqual(route, [1])
        self.assertEqual(result["stops"][0]["begin"], 720)

    def test_solver_can_wait_more_than_four_hours_for_appointment(self):
        dinner = planner.Cand(
            id="dinner", name="Joe Beef", lat=1.0, lng=1.0, score=0,
            kind="meal", visit_min=60, windows=[(0, 1440)], appointment_time=1170,
        )
        s = session(dinner)
        s.deadline = 1260

        route = planner.solve(s, s.start, 0, [1], time_limit_s=1)

        self.assertEqual(route, [1])
        self.assertEqual(planner.simulate(s, route, s.start, 0)["stops"][0]["begin"], 1170)


if __name__ == "__main__":
    unittest.main()
