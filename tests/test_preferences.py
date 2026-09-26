import unittest

from server import main, places
from server.models import TripRequest


class PreferenceModelTests(unittest.TestCase):
    def test_trip_accepts_accessibility_and_dietary_preferences(self):
        trip = TripRequest(city="Montreal", wheelchair_accessible=True,
                           dietary_preferences=["vegan"])

        self.assertTrue(trip.wheelchair_accessible)
        self.assertEqual(["vegan"], trip.dietary_preferences)

    def test_places_requests_accessibility_and_dietary_fields(self):
        self.assertIn("places.accessibilityOptions", places.SEARCH_FIELDS)
        self.assertIn("places.servesVegetarianFood", places.SEARCH_FIELDS)


class PreferenceScoreTests(unittest.TestCase):
    def test_explicitly_inaccessible_place_is_filtered(self):
        place = {"accessibilityOptions": {"wheelchairAccessibleEntrance": False}}

        score, reason = main.preference_adjusted_score(
            90, "museum", place, {"wheelchair_accessible": True})

        self.assertEqual(0, score)
        self.assertIn("wheelchair", reason.lower())

    def test_unknown_accessibility_is_penalized_not_filtered(self):
        score, reason = main.preference_adjusted_score(
            90, "museum", {}, {"wheelchair_accessible": True})

        self.assertEqual(75, score)
        self.assertIsNone(reason)

    def test_restaurant_that_does_not_match_diet_is_filtered(self):
        score, reason = main.preference_adjusted_score(
            85, "meal", {"servesVegetarianFood": False},
            {"dietary_preferences": ["vegetarian"]})

        self.assertEqual(0, score)
        self.assertIn("diet", reason.lower())

    def test_diet_does_not_penalize_non_meal_stops(self):
        score, reason = main.preference_adjusted_score(
            85, "museum", {}, {"dietary_preferences": ["vegan"]})

        self.assertEqual(85, score)
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
