import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from server import main


class SessionRestoreTests(unittest.TestCase):
    def tearDown(self):
        main.SESSIONS.clear()
        main.SESSION_TOUCHED.clear()

    def test_restore_rebuilds_original_id_and_replays_actions(self):
        rebuilt = SimpleNamespace(id="new-id")
        replayed = []

        async def fake_plan_stream(req, persist=True):
            main.SESSIONS["new-id"] = rebuilt
            main.SESSION_TOUCHED["new-id"] = 1
            yield json.dumps({"type": "plan", "session_id": "new-id"})

        async def fake_replan_stream(req, persist=True):
            replayed.append((req.event, req.delay_minutes, persist))
            yield json.dumps({"type": "plan", "session_id": req.session_id})

        recipe = {
            "trip": {"city": "Montreal"},
            "actions": [{"event": "late", "delay_minutes": 20, "place_id": None}],
        }
        with mock.patch.object(main.session_store, "load", return_value=recipe), \
             mock.patch.object(main.session_store, "purge_expired"), \
             mock.patch.object(main, "plan_stream", fake_plan_stream), \
             mock.patch.object(main, "replan_stream", fake_replan_stream):
            restored = asyncio.run(main.restore_session("original-id"))

        self.assertIs(restored, rebuilt)
        self.assertEqual("original-id", rebuilt.id)
        self.assertIs(rebuilt, main.SESSIONS["original-id"])
        self.assertEqual([("late", 20, False)], replayed)


if __name__ == "__main__":
    unittest.main()
