import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from server import session_store


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sessions.sqlite3"
        self.patch = mock.patch.object(session_store, "DB_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_round_trip_recipe_and_actions(self):
        trip = {"city": "Montreal", "loves": ["architecture"]}
        session_store.save("abc", trip, now=100)
        session_store.append_action("abc", {"event": "late", "delay_minutes": 20}, now=110)

        self.assertEqual(
            {"trip": trip, "actions": [{"event": "late", "delay_minutes": 20}]},
            session_store.load("abc", ttl_seconds=50, now=120),
        )

    def test_expired_recipe_is_deleted(self):
        session_store.save("abc", {"city": "Montreal"}, now=100)

        self.assertIsNone(session_store.load("abc", ttl_seconds=50, now=151))

    def test_database_contains_recipe_not_places_response(self):
        session_store.save("abc", {"city": "Montreal"}, now=100)
        session_store.append_action("abc", {"event": "lock", "place_id": "place-123"}, now=101)

        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT trip_json, actions_json FROM session_recipes").fetchone()

        stored = " ".join(row)
        self.assertIn("place-123", stored)  # Place IDs are exempt from caching restrictions.
        self.assertNotIn("Notre-Dame Basilica", stored)
        self.assertNotIn("rating", stored)
        self.assertNotIn("reviews", stored)


if __name__ == "__main__":
    unittest.main()
