import asyncio
import unittest
from datetime import date, datetime, timezone
from unittest import mock

from server import gemini, main
from server.models import ParseRequest

# 20:00 UTC on Sep 26 is already 05:00 on Sep 27 in Tokyo (UTC+9).
NOW_UTC = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW_UTC if tz else NOW_UTC.replace(tzinfo=None)


def parsed(**kw) -> gemini.ParsedTrip:
    fields = dict(city="Tokyo", date="", relative_day="", start_time="", end_time="",
                  start_location="", end_location="", loves=[], skips=[], must_see=[],
                  appointments=[], pace="normal", getting_around="transit",
                  by_neighborhood=True, meals=[gemini.ParsedMeal(name="lunch", time="12:30")],
                  auto_breaks=True)
    fields.update(kw)
    return gemini.ParsedTrip(**fields)


def run_parse(p: gemini.ParsedTrip, utc_offset: int = 540, form_city: str = "",
              queries: list | None = None) -> dict:
    async def fake_search(http, query, page_size=20, bias=None):
        if queries is not None:
            queries.append(query)
        return [{"utcOffsetMinutes": utc_offset}]

    with mock.patch.object(main, "datetime", FrozenDatetime), \
         mock.patch.object(main.config, "GEMINI_API_KEY", "test"), \
         mock.patch.object(main.config, "MAPS_KEY", "test"), \
         mock.patch.object(main.gemini, "parse_trip", mock.AsyncMock(return_value=p)), \
         mock.patch.object(main.places, "search_text", fake_search):
        return asyncio.run(main.parse(ParseRequest(message="Tokyo tomorrow", city=form_city)))


class ParseDateTests(unittest.TestCase):
    def test_parse_returns_valid_meals_and_break_setting(self):
        meals = [gemini.ParsedMeal(name="Breakfast", time="08:00"),
                 gemini.ParsedMeal(name="brunch", time="11:00"),
                 gemini.ParsedMeal(name="dinner", time="late")]
        result = run_parse(parsed(meals=meals, auto_breaks=False))
        self.assertEqual(result["meals"], [{"name": "breakfast", "time": "08:00"}])
        self.assertFalse(result["auto_breaks"])

    def test_tomorrow_uses_city_date_not_server_date(self):
        # The server's clock says Sep 26, so "tomorrow" used to become Sep 27,
        # which is today in Tokyo.
        self.assertEqual(run_parse(parsed(relative_day="tomorrow"))["date"], "2026-09-28")

    def test_today_uses_city_date(self):
        self.assertEqual(run_parse(parsed(relative_day="today"))["date"], "2026-09-27")

    def test_city_behind_utc(self):
        # 20:00 UTC is 13:00 on Sep 26 in Los Angeles (UTC-7).
        result = run_parse(parsed(city="Los Angeles", relative_day="today"), utc_offset=-420)
        self.assertEqual(result["date"], "2026-09-26")

    def test_form_city_wins_over_city_in_notes(self):
        queries = []
        run_parse(parsed(city="New York", relative_day="today"), form_city="Tokyo", queries=queries)
        self.assertEqual(queries, ["Tokyo"])

    def test_explicit_date_is_kept(self):
        self.assertEqual(run_parse(parsed(date="2026-10-03"))["date"], "2026-10-03")

    def test_no_day_leaves_date_empty(self):
        self.assertIsNone(run_parse(parsed())["date"])


class ResolveRelativeDayTests(unittest.TestCase):
    def test_weekdays_count_forward_from_city_date(self):
        sunday = date(2026, 9, 27)
        self.assertEqual(main.resolve_relative_day("sunday", sunday), sunday)
        self.assertEqual(main.resolve_relative_day("Saturday", sunday), date(2026, 10, 3))
        self.assertEqual(main.resolve_relative_day("monday", sunday), date(2026, 9, 28))

    def test_unknown_word(self):
        self.assertIsNone(main.resolve_relative_day("someday", date(2026, 9, 27)))


if __name__ == "__main__":
    unittest.main()
