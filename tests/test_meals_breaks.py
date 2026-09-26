import unittest

from pydantic import ValidationError

from server import planner
from server.models import TripRequest

DEFAULT_MEALS = [{"name": "lunch", "time": "12:30"}, {"name": "dinner", "time": "19:00"}]


def cand(id, kind="sight", score=60, visit_min=45, must=False):
    return planner.Cand(id=id, name=id.title(), lat=0.0, lng=0.0, score=score, kind=kind,
                        visit_min=visit_min, windows=[(0, 1440)], must=must)


def session(cands, start=600, deadline=1260, **trip):
    """Every leg is a 10-minute walk; the day starts and ends at the hotel (node 0)."""
    n = len(cands) + 1
    walk = [[0 if i == j else 10 for j in range(n)] for i in range(n)]
    return planner.Session(
        id="test",
        trip={"city": "Testville", "pace": "normal", "getting_around": "walk",
              "by_neighborhood": False, "meals": DEFAULT_MEALS, "auto_breaks": True, **trip},
        date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
        hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
        end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0,
        cands=cands, walk=walk, walk_m=[[m * 80 for m in row] for row in walk],
        transit=walk, drive=None, start=start, deadline=deadline, now=start)


def solve(s):
    route = planner.solve(s, s.now, 0, list(range(1, len(s.cands) + 1)), time_limit_s=1)
    return route, planner.simulate(s, route, s.now, 0)


class MealPolicyTests(unittest.TestCase):
    def test_trip_request_defaults_to_lunch_and_dinner_with_breaks(self):
        trip = TripRequest(city="Lisbon").model_dump()

        self.assertEqual(trip["meals"], DEFAULT_MEALS)
        self.assertTrue(trip["auto_breaks"])

    def test_trip_request_rejects_bad_meal_time(self):
        with self.assertRaises(ValidationError):
            TripRequest(city="Lisbon", meals=[{"name": "lunch", "time": "noon"}])

    def test_meal_windows_follow_requested_times_in_day_order(self):
        windows = planner.meal_windows({"meals": [{"name": "dinner", "time": "20:15"},
                                                  {"name": "Breakfast", "time": "08:00"}]})

        self.assertEqual(list(windows.items()), [("breakfast", (420, 600)), ("dinner", (1155, 1335))])

    def test_default_meal_windows_are_lunch_and_dinner(self):
        self.assertEqual(planner.meal_windows({}), {"lunch": planner.LUNCH, "dinner": planner.DINNER})
        self.assertEqual(planner.meal_windows({"meals": DEFAULT_MEALS}), planner.meal_windows({}))
        self.assertEqual(planner.meal_windows({"meals": []}), {})

    def test_meal_windows_skip_invalid_and_duplicate_meals(self):
        windows = planner.meal_windows({"meals": [{"name": "lunch", "time": "12:00"},
                                                  {"name": "lunch", "time": "13:00"},
                                                  {"name": "brunch", "time": "11:00"},
                                                  {"name": "dinner", "time": "25:00"}]})

        self.assertEqual(windows, {"lunch": (660, 840)})

    def test_no_meals_means_restaurants_never_fit(self):
        s = session([cand("bistro", "meal")], meals=[])

        self.assertEqual(planner.allowed_starts(s, 1, s.now), [])

    def test_solver_fills_lunch_and_dinner_once_each(self):
        s = session([cand("a", "meal", 70, 60), cand("b", "meal", 65, 60), cand("c", "meal", 60, 60)])

        route, res = solve(s)

        notes = sorted(n for st in res["stops"] for n in st["notes"])
        self.assertEqual(notes, ["dinner", "lunch"])
        self.assertEqual(len(route), 2)

    def test_short_day_gets_only_the_meal_it_covers(self):
        s = session([cand("a", "meal", 70, 60), cand("b", "meal", 65, 60)], start=600, deadline=900)

        route, res = solve(s)

        self.assertEqual([st["notes"] for st in res["stops"]], [["lunch"]])

    def test_replan_after_lunch_only_offers_dinner(self):
        s = session([cand("a", "meal", 70, 60), cand("b", "meal", 65, 60)])
        s.completed = [{"node": 1, "notes": ["lunch"], "leave": 900}]
        s.now = 900

        route = planner.solve(s, s.now, 1, [2], time_limit_s=1)
        res = planner.simulate(s, route, s.now, 1)

        self.assertEqual([st["notes"] for st in res["stops"]], [["dinner"]])

    def test_breakfast_lands_near_its_time(self):
        s = session([cand("cafe", "meal", 70, 45)], start=420, deadline=660,
                    meals=[{"name": "breakfast", "time": "08:00"}])

        route, res = solve(s)

        stop = res["stops"][0]
        self.assertEqual(stop["notes"], ["breakfast"])
        self.assertTrue(420 <= stop["begin"] <= 600)

    def test_no_meals_plans_only_sights(self):
        s = session([cand("bistro", "meal", 90, 60), cand("tower", "sight", 60)], meals=[])

        route, res = solve(s)

        self.assertEqual(route, [2])
        cuts = planner.cut_reasons(s, [1, 2], route, s.now)
        self.assertEqual(cuts[0]["why"], "You asked for no sit-down meals")


class CoffeeBreakTests(unittest.TestCase):
    def test_break_timing_follows_pace(self):
        self.assertEqual(planner.break_after_minutes({"pace": "relaxed"}), 120)
        self.assertEqual(planner.break_after_minutes({"pace": "normal"}), 180)
        self.assertEqual(planner.break_after_minutes({"pace": "packed"}), 240)
        self.assertIsNone(planner.break_after_minutes({"pace": "packed", "auto_breaks": False}))

    def test_only_long_enough_days_need_a_break(self):
        self.assertFalse(planner.needs_break({"pace": "normal"}, 600, 800))
        self.assertTrue(planner.needs_break({"pace": "normal"}, 600, 840))
        self.assertTrue(planner.needs_break({"pace": "relaxed"}, 600, 780))
        self.assertFalse(planner.needs_break({"pace": "packed"}, 600, 840))

    def test_marks_best_snacks_but_not_must_sees(self):
        cands = [cand("s1", "snack", 40, 60), cand("s2", "snack", 80), cand("s3", "snack", 60),
                 cand("s4", "snack", 50), cand("must", "snack", 99, must=True), cand("m", "museum")]

        picks = planner.mark_break_stops(cands, {"pace": "normal"}, 600, 1200)

        self.assertEqual([c.id for c in picks], ["s2", "s3", "s4"])
        self.assertEqual([c.id for c in cands if c.break_stop], ["s2", "s3", "s4"])
        self.assertLessEqual(max(c.visit_min for c in picks), planner.BREAK_MAX_VISIT_MIN)

    def test_poor_match_cafes_are_not_break_options(self):
        cands = [cand("meh", "snack", planner.MIN_SCORE - 1), cand("good", "snack", 70)]

        picks = planner.mark_break_stops(cands, {"pace": "normal"}, 600, 1200)

        self.assertEqual([c.id for c in picks], ["good"])

    def test_short_day_marks_no_breaks(self):
        cands = [cand("s1", "snack")]

        self.assertEqual(planner.mark_break_stops(cands, {"pace": "normal"}, 600, 700), [])
        self.assertFalse(cands[0].break_stop)

    def test_solver_schedules_exactly_one_break_after_the_pace_threshold(self):
        cands = [cand("tower"), cand("park", "park"), cand("gallery", "museum"),
                 cand("beans", "snack", 50, 20), cand("brew", "snack", 45, 20)]
        s = session(cands, start=600, deadline=1080, meals=[])
        planner.mark_break_stops(s.cands, s.trip, s.start, s.deadline)

        route, res = solve(s)

        breaks = [st for st in res["stops"] if "break" in st["notes"]]
        self.assertEqual(len(breaks), 1)
        self.assertTrue(780 <= breaks[0]["begin"] <= 780 + planner.BREAK_FLEX_MIN)

    def test_no_break_when_traveler_opts_out(self):
        cands = [cand("tower"), cand("beans", "snack", 50, 20)]
        s = session(cands, start=600, deadline=1080, meals=[], auto_breaks=False)
        planner.mark_break_stops(s.cands, s.trip, s.start, s.deadline)

        route, res = solve(s)

        self.assertFalse(any(c.break_stop for c in s.cands))
        self.assertFalse(any("break" in st["notes"] for st in res["stops"]))

    def test_second_break_is_not_planned_after_one_is_done(self):
        cands = [cand("beans", "snack", 50, 20), cand("brew", "snack", 45, 20), cand("tower")]
        s = session(cands, start=600, deadline=1080, meals=[])
        planner.mark_break_stops(s.cands, s.trip, s.start, s.deadline)
        s.completed = [{"node": 1, "notes": ["break"], "leave": 800}]
        s.now = 800

        route = planner.solve(s, s.now, 1, [2, 3], time_limit_s=1)

        self.assertEqual(route, [3])

    def test_meal_reservation_counts_as_nearest_requested_meal(self):
        c = cand("joe", "meal", 80, 60)
        c.appointment_time = 480
        s = session([c], start=420, deadline=720, meals=[{"name": "breakfast", "time": "08:30"},
                                                          {"name": "lunch", "time": "12:30"}])

        route, res = solve(s)

        self.assertEqual(res["stops"][0]["begin"], 480)
        self.assertIn("breakfast", res["stops"][0]["notes"])


if __name__ == "__main__":
    unittest.main()
