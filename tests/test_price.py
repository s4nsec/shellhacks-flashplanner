import unittest

from server import places


class PriceTests(unittest.TestCase):
    def test_price_range_is_used_when_google_has_one(self):
        place = {"priceLevel": "PRICE_LEVEL_MODERATE", "priceRange": {
            "startPrice": {"currencyCode": "CAD", "units": "20"},
            "endPrice": {"currencyCode": "CAD", "units": "30"}}}

        self.assertEqual(places.price(place), {"low": 20, "high": 30, "currency": "CAD"})

    def test_open_ended_price_range_has_no_high(self):
        place = {"priceRange": {"startPrice": {"currencyCode": "USD", "units": "100"}}}

        self.assertEqual(places.price(place), {"low": 100, "high": None, "currency": "USD"})

    def test_price_level_is_used_without_a_range(self):
        self.assertEqual(places.price({"priceLevel": "PRICE_LEVEL_INEXPENSIVE"}), {"level": 1})
        self.assertEqual(places.price({"priceLevel": "PRICE_LEVEL_VERY_EXPENSIVE"}), {"level": 4})

    def test_no_price_when_google_has_neither(self):
        self.assertIsNone(places.price({}))
        self.assertIsNone(places.price({"priceLevel": "PRICE_LEVEL_UNSPECIFIED"}))
        self.assertIsNone(places.price({"priceLevel": "PRICE_LEVEL_FREE"}))


if __name__ == "__main__":
    unittest.main()
