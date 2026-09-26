import unittest
from datetime import datetime

from server import routes


class TransitDepartureTests(unittest.TestCase):
    def test_far_date_moves_to_same_weekday_and_time_within_horizon(self):
        now = datetime(2026, 9, 26, 23, 0)
        dep = routes.transit_departure(datetime(2026, 10, 29, 14, 0), now)
        self.assertEqual(datetime(2026, 10, 8, 14, 0), dep)
        self.assertEqual(3, dep.weekday())
        self.assertLessEqual(dep - now, routes.TRANSIT_HORIZON)

    def test_near_date_is_unchanged(self):
        now = datetime(2026, 9, 26, 23, 0)
        dep = routes.transit_departure(datetime(2026, 10, 8, 14, 0), now)
        self.assertEqual(datetime(2026, 10, 8, 14, 0), dep)

    def test_date_just_past_horizon_moves_back_one_week(self):
        now = datetime(2026, 9, 26, 23, 0)
        dep = routes.transit_departure(datetime(2026, 10, 11, 0, 0), now)
        self.assertEqual(datetime(2026, 10, 4, 0, 0), dep)


if __name__ == "__main__":
    unittest.main()
