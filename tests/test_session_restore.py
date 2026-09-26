import asyncio
import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from server import main
from server.models import ReplanRequest


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
            replayed.append((req.event, req.delay_minutes, req.client_time, req.lat, req.lng, persist))
            yield json.dumps({"type": "plan", "session_id": req.session_id})

        recipe = {
            "trip": {"city": "Montreal"},
            "actions": [{
                "event": "late", "delay_minutes": 20, "place_id": None,
                "client_time": "2026-09-26T14:30:00-04:00", "lat": 45.5, "lng": -73.5,
            }],
        }
        with mock.patch.object(main.session_store, "load", return_value=recipe), \
             mock.patch.object(main.session_store, "purge_expired"), \
             mock.patch.object(main, "plan_stream", fake_plan_stream), \
             mock.patch.object(main, "replan_stream", fake_replan_stream):
            restored = asyncio.run(main.restore_session("original-id"))

        self.assertIs(restored, rebuilt)
        self.assertEqual("original-id", rebuilt.id)
        self.assertIs(rebuilt, main.SESSIONS["original-id"])
        self.assertEqual("late", replayed[0][0])
        self.assertEqual(20, replayed[0][1])
        self.assertEqual("2026-09-26T14:30:00-04:00", replayed[0][2].isoformat())
        self.assertEqual((45.5, -73.5, False), replayed[0][3:])

    def test_persisted_action_keeps_live_clock_and_location(self):
        req = ReplanRequest(
            session_id="session-id", event="done",
            client_time=datetime.fromisoformat("2026-09-26T14:30:00-04:00"),
            lat=45.5, lng=-73.5,
        )

        with mock.patch.object(main.session_store, "append_action") as append_action:
            main._persist_action(req)

        session_id, action = append_action.call_args.args
        self.assertEqual("session-id", session_id)
        self.assertEqual("2026-09-26T14:30:00-04:00", action["client_time"])
        self.assertEqual((45.5, -73.5), (action["lat"], action["lng"]))


if __name__ == "__main__":
    unittest.main()
