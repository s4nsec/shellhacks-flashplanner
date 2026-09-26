import unittest

from server import planner, rides


class RideDetailsTests(unittest.TestCase):
    def test_waymo_access_channel_is_visible(self):
        self.assertEqual(rides.waymo_coverage("Austin, TX")["access"], "Uber app")
        self.assertEqual(rides.waymo_coverage("Las Vegas, NV")["status"], "limited")
        self.assertFalse(rides.waymo_coverage("Montreal")["available"])

    def test_fare_range_is_ordered_and_labeled(self):
        fare = rides.fare_range(8.0, 24)
        self.assertLess(fare["low"], fare["high"])
        self.assertEqual(fare["kind"], "planning-range")
        self.assertEqual("https://support.google.com/waymo/answer/9059184", fare["source"])

    def test_ride_leg_uses_driving_distance_for_fare(self):
        c = planner.Cand(id="x", name="X", lat=1, lng=1, score=80,
                         windows=[(0, 1440)])
        s = planner.Session(
            id="test", trip={"city": "Phoenix", "getting_around": "ride", "pace": "normal"},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0, "lng": 0},
            end_location={"name": "Hotel", "lat": 0, "lng": 0}, end_node=0,
            cands=[c], walk=[[0, 30], [30, 0]], walk_m=[[0, 2000], [2000, 0]],
            transit=[[0, 20], [20, 0]], drive=[[0, 10], [10, 0]],
            start=600, deadline=900, drive_m=[[0, 8000], [8000, 0]])

        leg = planner.leg(s, 0, 1)

        self.assertEqual(leg["mode"], "ride")
        self.assertEqual(leg["km"], 8.0)
        self.assertIn("fare", leg)


if __name__ == "__main__":
    unittest.main()
