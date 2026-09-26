import unittest

from server import planner
from tests.test_appointments import session


def meal(id, score, **kw):
    return planner.Cand(id=id, name=id, lat=1.0, lng=1.0, score=score, kind="meal",
                        visit_min=60, windows=[(0, 1440)], **kw)


class MealAndLockTests(unittest.TestCase):
    def test_solver_keeps_reservation_outside_meal_hours(self):
        late = meal("late", 0, appointment_time=1290)   # 21:30, after the dinner window
        s = session(late)
        s.deadline = 1400

        route = planner.solve(s, s.start, 0, [1], time_limit_s=1)
        result = planner.simulate(s, route, s.start, 0)

        self.assertEqual(route, [1])
        self.assertEqual(result["stops"][0]["begin"], 1290)
        self.assertIn("dinner", result["stops"][0]["notes"])

    def test_reservation_counts_as_the_days_dinner(self):
        s = session(meal("booked", 0, appointment_time=1290), meal("other", 90))
        s.deadline = 1400

        route = planner.solve(s, s.start, 0, [1, 2], time_limit_s=1)
        notes = [st["notes"] for st in planner.simulate(s, route, s.start, 0)["stops"]]

        self.assertIn(1, route)
        self.assertEqual(sum("dinner" in n for n in notes), 1)

    def test_at_most_one_lunch(self):
        s = session(meal("a", 90), meal("b", 90))
        s.start = s.now = 690

        route = planner.solve(s, s.start, 0, [1, 2], time_limit_s=1)

        self.assertEqual(len(route), 1)

    def test_locked_place_is_kept_despite_low_score(self):
        weak = planner.Cand(id="weak", name="Weak", lat=1.0, lng=1.0, score=5,
                            visit_min=60, windows=[(0, 1440)])
        s = session(weak)
        self.assertEqual(planner.solve(s, s.start, 0, [1], time_limit_s=1), [])

        s.locked.add(1)
        self.assertEqual(planner.solve(s, s.start, 0, [1], time_limit_s=1), [1])


if __name__ == "__main__":
    unittest.main()


class ForecastTests(unittest.TestCase):
    def park(self, **kw):
        return planner.Cand(id="park", name="Park", lat=1.0, lng=1.0, score=90, kind="park",
                            setting="outdoor", visit_min=60, windows=[(0, 1440)], **kw)

    def test_outdoor_stop_moves_to_dry_hours(self):
        s = session(self.park())
        s.rain_hours = {10, 11}

        route = planner.solve(s, s.start, 0, [1], time_limit_s=1)
        stop = planner.simulate(s, route, s.start, 0)["stops"][0]

        self.assertEqual(route, [1])
        self.assertGreaterEqual(stop["begin"], 720)
        self.assertNotIn("rain", stop["notes"])

    def test_outdoor_appointment_in_rain_is_kept(self):
        s = session(self.park(appointment_time=630))
        s.rain_hours = {10, 11}

        route = planner.solve(s, s.start, 0, [1], time_limit_s=1)
        stop = planner.simulate(s, route, s.start, 0)["stops"][0]

        self.assertEqual(route, [1])
        self.assertEqual(stop["begin"], 630)
        self.assertIn("rain", stop["notes"])
