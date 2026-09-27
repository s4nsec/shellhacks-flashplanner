import unittest

from fastapi.testclient import TestClient

from server import main


class CacheHeaderTests(unittest.TestCase):
    def test_assets_are_revalidated_on_every_load(self):
        r = TestClient(main.app).get("/assets/js/sheet.js")

        self.assertEqual(200, r.status_code)
        self.assertEqual("no-cache", r.headers["cache-control"])

    def test_page_is_revalidated_on_every_load(self):
        r = TestClient(main.app).get("/")

        self.assertEqual(200, r.status_code)
        self.assertEqual("no-cache", r.headers["cache-control"])

    def test_unchanged_asset_comes_back_as_not_modified(self):
        client = TestClient(main.app)
        etag = client.get("/assets/js/sheet.js").headers["etag"]

        r = client.get("/assets/js/sheet.js", headers={"if-none-match": etag})

        self.assertEqual(304, r.status_code)


if __name__ == "__main__":
    unittest.main()
