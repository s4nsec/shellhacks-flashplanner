import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from server import gemini, main, places, planner


class VenueTests(unittest.TestCase):
    def test_cinemas_theaters_and_concert_halls_are_venues(self):
        self.assertTrue(places.is_venue({"types": ["movie_theater", "point_of_interest"]}))
        self.assertTrue(places.is_venue({"primaryType": "concert_hall", "types": []}))
        self.assertTrue(places.is_venue({"types": ["performing_arts_theater"]}))

    def test_museums_and_parks_are_not_venues(self):
        self.assertFalse(places.is_venue({"primaryType": "museum", "types": ["museum", "tourist_attraction"]}))
        self.assertFalse(places.is_venue({"types": ["park"]}))
        self.assertFalse(places.is_venue({}))


class WhatsOnSearchTests(unittest.TestCase):
    def test_answers_without_a_web_search_are_dropped(self):
        resp = SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=None)],
                               text="Past Lives at 13:30")
        fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(
            generate_content=mock.AsyncMock(return_value=resp))))

        with mock.patch.object(gemini, "client", return_value=fake), \
             mock.patch.object(gemini, "_structured", new=mock.AsyncMock()) as structure:
            out = asyncio.run(gemini.whats_on("Cinéma du Parc", "Montréal", "Saturday 2026-09-26"))

        self.assertEqual({"showings": [], "sources": []}, out)
        structure.assert_not_awaited()

    def test_searched_listings_are_structured_with_their_sources(self):
        chunk = SimpleNamespace(web=SimpleNamespace(title="cinoche.com", uri="https://example.com/r"))
        resp = SimpleNamespace(
            candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[chunk]))],
            text="Past Lives (drama) at 1:30 PM and 9:15 PM")
        fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(
            generate_content=mock.AsyncMock(return_value=resp))))
        parsed = gemini.WhatsOn(showings=[gemini.Showing(
            title="Past Lives", detail="Drama", times=["13:30", "21:15"], url="")])

        with mock.patch.object(gemini, "client", return_value=fake), \
             mock.patch.object(gemini, "_structured", new=mock.AsyncMock(return_value=parsed)) as structure:
            out = asyncio.run(gemini.whats_on("Cinéma du Parc", "Montréal", "Saturday 2026-09-26"))

        self.assertIn("Past Lives (drama) at 1:30 PM and 9:15 PM", structure.await_args.args[0])
        self.assertEqual(["13:30", "21:15"], out["showings"][0]["times"])
        self.assertEqual([{"title": "cinoche.com", "uri": "https://example.com/r"}], out["sources"])


class WhatsOnEndpointTests(unittest.TestCase):
    def tearDown(self):
        main.SESSIONS.clear()
        main.SESSION_TOUCHED.clear()
        main.WHATS_ON.clear()

    def test_listings_come_back_with_start_times_in_minutes(self):
        cinema = planner.Cand(id="cinema", name="Cinéma du Parc", lat=45.51, lng=-73.57,
                              address="3575 Av. du Parc, Montréal", venue=True)
        s = planner.Session(
            id="sid", trip={"city": "Montreal", "getting_around": "walk", "pace": "normal"},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 45.5, "lng": -73.5},
            end_location={"name": "Hotel", "lat": 45.5, "lng": -73.5}, end_node=0,
            cands=[cinema], walk=[[0, 10], [10, 0]], walk_m=[[0, 800], [800, 0]],
            transit=[[0, 10], [10, 0]], drive=None, start=600, deadline=1140)
        main.SESSIONS["sid"] = s
        main.SESSION_TOUCHED["sid"] = time.time()
        found = {"showings": [{"title": "Past Lives", "detail": "Drama, 13+",
                               "times": ["21:15", "13:30", "evening", "13:30"], "url": ""}],
                 "sources": [{"title": "cinemaduparc.com", "uri": "https://example.com/listing"}]}

        with mock.patch.object(main.session_store, "purge_expired"), \
             mock.patch.object(main.session_store, "touch"), \
             mock.patch.object(main.gemini, "whats_on", new=mock.AsyncMock(return_value=found)) as ask:
            out = asyncio.run(main.whats_on("sid", "cinema"))

        ask.assert_awaited_once_with("Cinéma du Parc", "3575 Av. du Parc, Montréal", "Saturday 2026-09-26")
        self.assertEqual([810, 1275], out["showings"][0]["times"])
        self.assertEqual("Past Lives", out["showings"][0]["title"])
        self.assertEqual("https://example.com/listing", out["sources"][0]["uri"])

    def test_listings_are_fetched_once_per_place_and_day(self):
        cinema = planner.Cand(id="cinema", name="Cinéma du Parc", lat=45.51, lng=-73.57, venue=True)
        s = planner.Session(
            id="sid", trip={"city": "Montreal", "getting_around": "walk", "pace": "normal"},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 45.5, "lng": -73.5},
            end_location={"name": "Hotel", "lat": 45.5, "lng": -73.5}, end_node=0,
            cands=[cinema], walk=[[0, 10], [10, 0]], walk_m=[[0, 800], [800, 0]],
            transit=[[0, 10], [10, 0]], drive=None, start=600, deadline=1140)
        main.SESSIONS["sid"] = s
        main.SESSION_TOUCHED["sid"] = time.time()
        found = {"showings": [{"title": "Past Lives", "detail": "", "times": ["13:30"], "url": ""}],
                 "sources": []}

        with mock.patch.object(main.session_store, "purge_expired"), \
             mock.patch.object(main.session_store, "touch"), \
             mock.patch.object(main.gemini, "whats_on", new=mock.AsyncMock(return_value=found)) as ask:
            first = asyncio.run(main.whats_on("sid", "cinema"))
            second = asyncio.run(main.whats_on("sid", "cinema"))

        self.assertEqual(1, ask.await_count)
        self.assertEqual(first, second)

    def test_places_that_are_not_venues_have_no_listings(self):
        museum = planner.Cand(id="museum", name="Musée des beaux-arts", lat=45.49, lng=-73.58)
        s = planner.Session(
            id="sid", trip={"city": "Montreal", "getting_around": "walk", "pace": "normal"},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 45.5, "lng": -73.5},
            end_location={"name": "Hotel", "lat": 45.5, "lng": -73.5}, end_node=0,
            cands=[museum], walk=[[0, 10], [10, 0]], walk_m=[[0, 800], [800, 0]],
            transit=[[0, 10], [10, 0]], drive=None, start=600, deadline=1140)
        main.SESSIONS["sid"] = s
        main.SESSION_TOUCHED["sid"] = time.time()

        with mock.patch.object(main.session_store, "purge_expired"), \
             mock.patch.object(main.session_store, "touch"), \
             mock.patch.object(main.gemini, "whats_on", new=mock.AsyncMock()) as ask, \
             self.assertRaises(HTTPException) as err:
            asyncio.run(main.whats_on("sid", "museum"))

        self.assertEqual(404, err.exception.status_code)
        ask.assert_not_awaited()

    def test_gemini_failure_is_reported_and_not_cached(self):
        cinema = planner.Cand(id="cinema", name="Cinéma du Parc", lat=45.51, lng=-73.57, venue=True)
        s = planner.Session(
            id="sid", trip={"city": "Montreal", "getting_around": "walk", "pace": "normal"},
            date="2026-09-26", weekday=6, utc_offset=-240, sunset=None,
            hotel={"name": "Hotel", "lat": 45.5, "lng": -73.5},
            end_location={"name": "Hotel", "lat": 45.5, "lng": -73.5}, end_node=0,
            cands=[cinema], walk=[[0, 10], [10, 0]], walk_m=[[0, 800], [800, 0]],
            transit=[[0, 10], [10, 0]], drive=None, start=600, deadline=1140)
        main.SESSIONS["sid"] = s
        main.SESSION_TOUCHED["sid"] = time.time()

        with mock.patch.object(main.session_store, "purge_expired"), \
             mock.patch.object(main.session_store, "touch"), \
             mock.patch.object(main.gemini, "whats_on", new=mock.AsyncMock(side_effect=RuntimeError("quota"))), \
             self.assertRaises(HTTPException) as err:
            asyncio.run(main.whats_on("sid", "cinema"))

        self.assertEqual(502, err.exception.status_code)
        self.assertEqual({}, main.WHATS_ON)

    def test_expired_plan_is_a_404(self):
        with mock.patch.object(main.session_store, "purge_expired"), \
             mock.patch.object(main.session_store, "load", return_value=None), \
             self.assertRaises(HTTPException) as err:
            asyncio.run(main.whats_on("gone", "cinema"))

        self.assertEqual(404, err.exception.status_code)


if __name__ == "__main__":
    unittest.main()
