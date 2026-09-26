import asyncio
import unittest
from unittest import mock

from server import main
from server.models import TripRequest


def resolve(trip: TripRequest, hits: list[dict]):
    queries = []

    async def fake_search(http, query, page_size=20, bias=None):
        queries.append(query)
        return hits

    with mock.patch.object(main.places, "search_text", fake_search):
        result = asyncio.run(main.resolve_start(None, trip.model_dump(), trip.city))
    return result, queries


class ResolveStartTests(unittest.TestCase):
    def test_picked_place_is_not_looked_up_again(self):
        trip = TripRequest(city="Montreal", start_location="Sheraton",
                           start_place={"place_id": "abc", "name": "Le Centre Sheraton",
                                        "lat": 45.5, "lng": -73.57, "utc_offset_minutes": -240})
        (hotel, offset), queries = resolve(trip, [])
        self.assertEqual(hotel, {"name": "Le Centre Sheraton", "lat": 45.5, "lng": -73.57})
        self.assertEqual(offset, -240)
        self.assertEqual(queries, [])

    def test_picked_place_without_offset_asks_the_city(self):
        trip = TripRequest(city="Montreal",
                           start_place={"name": "Hotel", "lat": 45.5, "lng": -73.57})
        (hotel, offset), queries = resolve(trip, [{"utcOffsetMinutes": -240}])
        self.assertEqual(hotel["name"], "Hotel")
        self.assertEqual(offset, -240)
        self.assertEqual(queries, ["Montreal"])

    def test_typed_text_is_searched(self):
        trip = TripRequest(city="Montreal", start_location="Sheraton downtown")
        hit = {"displayName": {"text": "Sheraton"}, "utcOffsetMinutes": -240,
               "location": {"latitude": 45.5, "longitude": -73.57}}
        (hotel, offset), queries = resolve(trip, [hit])
        self.assertEqual(hotel, {"name": "Sheraton", "lat": 45.5, "lng": -73.57})
        self.assertEqual(offset, -240)
        self.assertEqual(queries, ["Sheraton downtown, Montreal"])

    def test_typed_text_not_found(self):
        trip = TripRequest(city="Montreal", start_location="Nowhere Inn")
        result, _ = resolve(trip, [])
        self.assertIn("couldn't find “Nowhere Inn, Montreal”", result)

    def test_notes_default_to_empty(self):
        self.assertEqual(TripRequest(city="Montreal").notes, "")


if __name__ == "__main__":
    unittest.main()
