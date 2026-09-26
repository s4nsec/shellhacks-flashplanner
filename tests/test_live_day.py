import asyncio
import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from server import main, planner, routes
from server.models import ReplanRequest

# 15:00 UTC on Sep 26 is 11:00 on Sep 26 in New York (UTC-4), 660 minutes after midnight.
CLIENT_TIME = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)


class LiveClockTests(unittest.TestCase):
    def test_device_clock_becomes_city_minutes_on_the_plan_day(self):
        s = planner.Session(id="clock", trip={}, date="2026-09-26", weekday=6, utc_offset=-240,
                            sunset=None, hotel={}, end_location={}, end_node=0, cands=[],
                            walk=[[0]], walk_m=[[0]], transit=[[0]], drive=None, start=600, deadline=900)

        self.assertEqual(main.live_minutes(s, CLIENT_TIME), 660)

    def test_device_clock_on_another_day_is_ignored(self):
        s = planner.Session(id="clock", trip={}, date="2026-09-27", weekday=0, utc_offset=-240,
                            sunset=None, hotel={}, end_location={}, end_node=0, cands=[],
                            walk=[[0]], walk_m=[[0]], transit=[[0]], drive=None, start=600, deadline=900)

        self.assertIsNone(main.live_minutes(s, CLIENT_TIME))

    def test_naive_device_clock_is_read_as_utc(self):
        s = planner.Session(id="clock", trip={}, date="2026-09-26", weekday=6, utc_offset=-240,
                            sunset=None, hotel={}, end_location={}, end_node=0, cands=[],
                            walk=[[0]], walk_m=[[0]], transit=[[0]], drive=None, start=600, deadline=900)

        self.assertEqual(main.live_minutes(s, datetime(2026, 9, 26, 15, 0)), 660)

    def test_replan_request_accepts_device_time_and_position(self):
        req = ReplanRequest(session_id="x", event="rain", client_time="2026-09-26T15:00:00.000Z",
                            lat=40.7, lng=-74.0)

        self.assertEqual(req.client_time, CLIENT_TIME)
        self.assertEqual((req.lat, req.lng), (40.7, -74.0))


class LivePositionTests(unittest.TestCase):
    def test_position_becomes_a_node_with_travel_times_out_of_it(self):
        a = planner.Cand(id="a", name="a", lat=0.0, lng=0.01, score=80, visit_min=60, windows=[(0, 1440)])
        s = planner.Session(
            id="pos", trip={"pace": "normal", "getting_around": "walk", "by_neighborhood": True},
            date="2026-09-26", weekday=6, utc_offset=0, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0, cands=[a],
            walk=[[0, 10], [10, 0]], walk_m=[[0, 1000], [1000, 0]], transit=[[0, 10], [10, 0]],
            drive=None, start=600, deadline=900, now=600)

        node = planner.add_position(s, (0.02, 0.02), [4, 3], [300, 200], [None, None])

        self.assertEqual(node, 2)
        self.assertEqual(s.point(2), (0.02, 0.02))
        self.assertEqual(s.walk, [[0, 10, None], [10, 0, None], [4, 3, 0]])
        self.assertEqual(s.walk_m, [[0, 1000, None], [1000, 0, None], [300, 200, 0]])
        self.assertEqual(planner.leg(s, 2, 1)["min"], 3)
        self.assertEqual(planner.solve(s, 660, 2, [1], time_limit_s=1), [1])
        self.assertEqual(planner.simulate(s, [1], 660, 2)["stops"][0]["arrive"], 663)

    def test_one_row_matrix_uses_the_given_origin(self):
        response = mock.Mock()
        response.json.return_value = [
            {"destinationIndex": 0, "condition": "ROUTE_EXISTS", "duration": "300s", "distanceMeters": 400},
            {"destinationIndex": 1, "condition": "ROUTE_EXISTS", "duration": "90s", "distanceMeters": 100},
            {"destinationIndex": 2, "condition": "ROUTE_NOT_FOUND"},
        ]
        http = mock.Mock()
        http.post = mock.AsyncMock(return_value=response)

        minutes, meters = asyncio.run(routes.matrix(
            http, [(0.0, 0.0), (0.0, 0.01), (0.0, 0.02)], "WALK", origins=[(0.5, 0.5)]))

        self.assertEqual(minutes, [[5, 2, None]])
        self.assertEqual(meters, [[400, 100, None]])
        body = http.post.call_args.kwargs["json"]
        self.assertEqual(body["origins"][0]["waypoint"]["location"]["latLng"], {"latitude": 0.5, "longitude": 0.5})
        self.assertEqual(len(body["destinations"]), 3)


class LiveReplanTests(unittest.IsolatedAsyncioTestCase):
    async def test_finishing_on_time_keeps_the_plan_and_uses_the_real_clock(self):
        a = planner.Cand(id="a", name="a", lat=0.0, lng=0.01, score=80, visit_min=60, windows=[(0, 1440)])
        b = planner.Cand(id="b", name="b", lat=0.0, lng=0.02, score=80, visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="live-done-on-time", trip={"city": "Testville", "pace": "normal", "getting_around": "walk",
                                          "by_neighborhood": False, "loves": [], "skips": []},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0, cands=[a, b],
            walk=travel, walk_m=[[m * 100 for m in row] for row in travel], transit=travel,
            drive=None, start=600, deadline=900, now=600, route=[1, 2])
        main.remember_session(s)
        req = ReplanRequest(session_id=s.id, event="done", client_time=CLIENT_TIME)

        with mock.patch.object(main.routes, "polyline", mock.AsyncMock(return_value=None)):
            events = [json.loads(x) async for x in main.replan_stream(req)]

        self.assertEqual([e["key"] for e in events if e["type"] == "step"], ["done"])
        self.assertIn("by your clock", events[0]["result"])
        self.assertEqual((s.now, s.loc, s.route), (660, 1, [2]))
        self.assertEqual(events[-1]["stops"][0]["arrive"], 670)

    async def test_finishing_too_late_for_the_rest_re_plans(self):
        a = planner.Cand(id="a", name="a", lat=0.0, lng=0.01, score=80, visit_min=60, windows=[(0, 1440)])
        b = planner.Cand(id="b", name="b", lat=0.0, lng=0.02, score=80, visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="live-done-late", trip={"city": "Testville", "pace": "normal", "getting_around": "walk",
                                       "by_neighborhood": False, "loves": [], "skips": []},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0, cands=[a, b],
            walk=travel, walk_m=[[m * 100 for m in row] for row in travel], transit=travel,
            drive=None, start=600, deadline=800, now=600, route=[1, 2])
        main.remember_session(s)
        # 17:00 UTC is 13:00 in the city: 780, too late to fit b (60 min) before 800.
        req = ReplanRequest(session_id=s.id, event="done", client_time=datetime(2026, 9, 26, 17, 0, tzinfo=timezone.utc))

        with mock.patch.object(main.routes, "polyline", mock.AsyncMock(return_value=None)), \
                mock.patch.object(main.gemini, "narrate_change", mock.AsyncMock(return_value="Story")):
            events = [json.loads(x) async for x in main.replan_stream(req)]

        self.assertIn("resolve", [e["key"] for e in events if e["type"] == "step"])
        self.assertEqual((s.now, s.loc, s.route), (780, 1, []))
        self.assertEqual(events[-1]["dropped"], ["b"])
        self.assertTrue(events[-1]["shifted"])

    async def test_finishing_without_a_device_clock_keeps_the_simulated_clock(self):
        a = planner.Cand(id="a", name="a", lat=0.0, lng=0.01, score=80, visit_min=60, windows=[(0, 1440)])
        b = planner.Cand(id="b", name="b", lat=0.0, lng=0.02, score=80, visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="sim-done", trip={"city": "Testville", "pace": "normal", "getting_around": "walk",
                                 "by_neighborhood": False, "loves": [], "skips": []},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0, cands=[a, b],
            walk=travel, walk_m=[[m * 100 for m in row] for row in travel], transit=travel,
            drive=None, start=600, deadline=900, now=600, route=[1, 2])
        main.remember_session(s)
        req = ReplanRequest(session_id=s.id, event="done")

        with mock.patch.object(main.routes, "polyline", mock.AsyncMock(return_value=None)):
            events = [json.loads(x) async for x in main.replan_stream(req)]

        self.assertIn("on schedule", events[0]["result"])
        self.assertEqual((s.now, s.loc, s.route), (670, 1, [2]))

    async def test_rain_re_plans_from_the_device_position_and_clock(self):
        a = planner.Cand(id="a", name="a", lat=0.0, lng=0.01, score=80, visit_min=60, windows=[(0, 1440)])
        b = planner.Cand(id="b", name="b", lat=0.0, lng=0.02, score=80, visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="live-rain", trip={"city": "Testville", "pace": "normal", "getting_around": "walk",
                                  "by_neighborhood": False, "loves": [], "skips": []},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0, cands=[a, b],
            walk=travel, walk_m=[[m * 100 for m in row] for row in travel], transit=travel,
            drive=None, start=600, deadline=900, now=600, route=[1, 2])
        main.remember_session(s)
        req = ReplanRequest(session_id=s.id, event="rain", client_time=CLIENT_TIME, lat=0.01, lng=0.01)
        matrix = mock.AsyncMock(return_value=([[7, 7, 7]], [[500, 500, 500]]))

        with mock.patch.object(main.routes, "matrix", matrix), \
                mock.patch.object(main.routes, "polyline", mock.AsyncMock(return_value=None)), \
                mock.patch.object(main.gemini, "narrate_change", mock.AsyncMock(return_value="Story")):
            events = [json.loads(x) async for x in main.replan_stream(req)]

        self.assertEqual(matrix.call_count, 2)  # walk and transit rows
        self.assertEqual(matrix.call_args.kwargs["origins"], [(0.01, 0.01)])
        self.assertIn("locate", [e["key"] for e in events if e["type"] == "step"])
        self.assertEqual((s.now, s.loc), (660, 3))
        plan = events[-1]
        self.assertEqual(plan["here"], {"lat": 0.01, "lng": 0.01})
        self.assertEqual(plan["at"], "your current location")
        self.assertEqual(plan["stops"][0]["arrive"], 667)

    async def test_position_far_from_the_city_is_ignored(self):
        a = planner.Cand(id="a", name="a", lat=0.0, lng=0.01, score=80, visit_min=60, windows=[(0, 1440)])
        b = planner.Cand(id="b", name="b", lat=0.0, lng=0.02, score=80, visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="live-far", trip={"city": "Testville", "pace": "normal", "getting_around": "walk",
                                 "by_neighborhood": False, "loves": [], "skips": []},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0, cands=[a, b],
            walk=travel, walk_m=[[m * 100 for m in row] for row in travel], transit=travel,
            drive=None, start=600, deadline=900, now=600, route=[1, 2])
        main.remember_session(s)
        req = ReplanRequest(session_id=s.id, event="rain", client_time=CLIENT_TIME, lat=10.0, lng=10.0)
        matrix = mock.AsyncMock()

        with mock.patch.object(main.routes, "matrix", matrix), \
                mock.patch.object(main.routes, "polyline", mock.AsyncMock(return_value=None)), \
                mock.patch.object(main.gemini, "narrate_change", mock.AsyncMock(return_value="Story")):
            events = [json.loads(x) async for x in main.replan_stream(req)]

        matrix.assert_not_called()
        self.assertEqual((s.now, s.loc), (660, 0))
        self.assertIsNone(events[-1]["here"])

    async def test_late_on_the_real_clock_adds_only_the_extra_delay(self):
        a = planner.Cand(id="a", name="a", lat=0.0, lng=0.01, score=80, visit_min=60, windows=[(0, 1440)])
        b = planner.Cand(id="b", name="b", lat=0.0, lng=0.02, score=80, visit_min=60, windows=[(0, 1440)])
        travel = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        s = planner.Session(
            id="live-late", trip={"city": "Testville", "pace": "normal", "getting_around": "walk",
                                  "by_neighborhood": False, "loves": [], "skips": []},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 0.0, "lng": 0.0},
            end_location={"name": "Hotel", "lat": 0.0, "lng": 0.0}, end_node=0, cands=[a, b],
            walk=travel, walk_m=[[m * 100 for m in row] for row in travel], transit=travel,
            drive=None, start=600, deadline=900, now=600, route=[1, 2])
        main.remember_session(s)
        req = ReplanRequest(session_id=s.id, event="late", delay_minutes=0, client_time=CLIENT_TIME)

        with mock.patch.object(main.routes, "polyline", mock.AsyncMock(return_value=None)), \
                mock.patch.object(main.gemini, "narrate_change", mock.AsyncMock(return_value="Story")):
            events = [json.loads(x) async for x in main.replan_stream(req)]

        self.assertEqual(s.now, 660)
        self.assertEqual(events[-1]["now"], 660)


if __name__ == "__main__":
    unittest.main()
