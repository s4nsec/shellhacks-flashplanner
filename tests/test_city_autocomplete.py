from pathlib import Path
import unittest


WEB = Path(__file__).parents[1] / "web"
# The page markup plus its scripts, which live in web/assets/js.
PAGE = "\n".join(p.read_text(encoding="utf-8")
                 for p in [WEB / "index.html", *sorted((WEB / "assets" / "js").glob("*.js"))])


class CityAutocompleteTests(unittest.TestCase):
    def test_city_field_is_an_accessible_combobox(self):
        self.assertIn('id="city" placeholder="Montreal, Canada"', PAGE)
        self.assertIn('aria-controls="cityList"', PAGE)
        self.assertIn('id="cityList" class="ac-list" role="listbox"', PAGE)

    def test_city_suggestions_are_restricted_to_cities(self):
        self.assertIn('req.includedPrimaryTypes=["(cities)"]', PAGE)

    def test_selected_city_is_joined_to_its_country(self):
        self.assertIn('fields.push("addressComponents")', PAGE)
        self.assertIn('c.types?.includes("country")', PAGE)
        self.assertIn('prefix:"city",announcement:"City selected:",citiesOnly:true', PAGE)


if __name__ == "__main__":
    unittest.main()
