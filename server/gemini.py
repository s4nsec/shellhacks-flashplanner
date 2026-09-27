"""Everything that talks to the Gemini API.

Gemini does the judgment calls: understanding the traveler's message, deciding
which places suit them, reading reviews for visit lengths, turning free-text
updates into a function call, and explaining the plan. It never does the route
math; OR-Tools does that in planner.py.
"""
import json
import typing

from google import genai
from google.genai import types
from pydantic import BaseModel

from . import config

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


# Response schemas. Fields have no defaults on purpose: the Gemini API rejects
# default values in response schemas, so "unknown" is an empty string or list.

class ParsedMeal(BaseModel):
    name: str               # breakfast | lunch | dinner
    time: str               # preferred start, HH:MM (24h)


class ParsedAppointment(BaseModel):
    place: str
    time: str              # HH:MM (24h)


class ParsedDayWindow(BaseModel):
    start_time: str
    end_time: str


class ParsedTrip(BaseModel):
    city: str
    date: str               # YYYY-MM-DD or ""
    relative_day: str       # today | tomorrow | monday ... sunday, or ""
    start_time: str         # HH:MM (24h) or ""
    end_time: str           # HH:MM (24h) or ""
    start_location: str     # hotel/address or ""
    end_location: str       # station/airport/hotel/address or ""
    loves: list[str]
    skips: list[str]
    must_see: list[str]
    appointments: list[ParsedAppointment]
    days: int
    day_windows: list[ParsedDayWindow]
    wheelchair_accessible: bool
    dietary_preferences: list[str]  # vegetarian | vegan
    pace: str               # relaxed | normal | packed
    getting_around: str     # walk | transit | ride
    by_neighborhood: bool
    meals: list[ParsedMeal]
    auto_breaks: bool
    budget: int             # per person for the day, local currency; -1 if not said


class PlaceJudgment(BaseModel):
    id: str
    score: int              # 0-100 for this traveler
    kind: str               # sight | museum | meal | snack | market | park | viewpoint | shopping | nightlife | other
    setting: str            # indoor | outdoor | covered
    timing: str             # any | morning | daytime | evening | night
    reason: str             # short phrase
    cost: int               # typical spend per person, whole units of local currency


class ScoredPlaces(BaseModel):
    currency: str           # ISO 4217 code of the city's currency
    places: list[PlaceJudgment]


class VisitEstimate(BaseModel):
    id: str
    minutes: int
    from_reviews: bool
    evidence: list[str]     # short exact quotes that mention time
    review_numbers: list[int]  # 1-based index of the review each quote came from


async def _structured(prompt: str, schema):
    resp = await client().aio.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        ),
    )
    if resp.parsed is not None:
        return resp.parsed
    data = json.loads(resp.text or "null")
    if typing.get_origin(schema) is list:
        item = typing.get_args(schema)[0]
        return [item.model_validate(x) for x in (data or [])]
    return schema.model_validate(data)


async def _text(prompt: str) -> str:
    resp = await client().aio.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.6),
    )
    return (resp.text or "").replace("**", "").strip()


async def parse_trip(message: str, today: str) -> ParsedTrip:
    prompt = f"""You turn a traveler's message into trip settings. Today is {today}.

Message:
\"\"\"{message}\"\"\"

Rules:
- city: the city they're visiting ("" if not said).
- date: YYYY-MM-DD only if they give a calendar date ("October 3", "the 12th"), else "".
- relative_day: if they name a day relative to now instead, one of "today", "tomorrow",
  or a lowercase weekday ("saturday"); else "". "Tonight" is "today". Leave date "" then;
  the server works out the date on the city's own clock.
- start_time / end_time: 24-hour HH:MM for when they're free, else "".
  If they give a duration ("6 hours from 11am"), compute end_time.
  An appointment time is not a start or end time unless they explicitly say their day starts or ends then.
- start_location: hotel, Airbnb, address or neighborhood they're staying in, else "".
- end_location: where they need to finish (station, airport, hotel, address), else "".
- loves: short interest phrases they like ("architecture", "street food", "jazz bars").
- skips: things they want to avoid ("museums", "crowds").
- must_see: specific places they insist on.
- appointments: fixed-time reservations, tickets, or events as place + 24-hour
  HH:MM time (for example, Joe Beef at 19:30). Do not put ordinary preferences here.
- days: number of consecutive days requested, from 1 to 7 (default 1).
- day_windows: one start_time/end_time object per day only when the traveler gives
  different hours for individual days; otherwise [].
- wheelchair_accessible: true when the traveler needs wheelchair-accessible places.
- dietary_preferences: include "vegetarian" and/or "vegan" only when requested.
- pace: "packed" if they want to see as much as possible, "relaxed" if they want it easy, else "normal".
- getting_around: "walk" if walking only, "ride" if they mention taxis, rideshare or robotaxis, else "transit".
- by_neighborhood: false only if they explicitly want maximum stops regardless of back-and-forth; otherwise true.
- meals: the sit-down meals they want, each with name (breakfast, lunch, or dinner) and a preferred HH:MM start.
  Default to lunch at 12:30 and dinner at 19:00. Omit meals they explicitly skip; return [] for no sit-down meals.
- auto_breaks: false only if they explicitly do not want coffee/rest stops; otherwise true.
- budget: how much they can spend per person on tickets and food for the day, as a whole number
  in the city's local currency (convert if they give another currency); -1 if they don't say."""
    return await _structured(prompt, ParsedTrip)


async def score_places(trip: dict, places: list[dict]) -> ScoredPlaces:
    prompt = f"""You are planning one day of sightseeing for this traveler:
{json.dumps(trip, ensure_ascii=False)}
"notes" is optional free text for anything the other fields don't cover. If it
contradicts another field (loves, skips, must_see, pace, ...), follow the field.

Candidate places from Google Maps (id, name, types, rating, review count, summary, price level):
{json.dumps(places, ensure_ascii=False)}

Return currency: the ISO 4217 code of the local currency (for example CAD).
Then for EVERY candidate return:
- id: copied exactly.
- score: 0-100, how worthwhile this place is for THIS traveler on a short visit.
  Reward matches with "loves", give places that match "skips" under 20, and give "must_see" and
  appointment places 95+.
  If wheelchair_accessible is true, heavily penalize candidates whose accessibilityOptions do not
  confirm an accessible entrance. For meal candidates, heavily penalize places that explicitly do
  not serve vegetarian food when vegetarian or vegan food is requested. Treat missing Places data
  as uncertainty rather than proof that a place is inaccessible or unsuitable.
  Give 0 to things that aren't worth a tourist's time (hotels, generic shops, offices,
  transit stations, duplicates of another candidate).
- kind: one of sight, museum, meal, snack, market, park, viewpoint, shopping, nightlife, other.
  Use "meal" only for sit-down restaurants or delis where you'd eat lunch or dinner.
- setting: indoor, outdoor, or covered (partly sheltered, like a covered market).
- timing: when in the day a visit makes sense. "morning" for brunch and breakfast spots or
  places best early; "daytime" for places that need daylight (parks, gardens, trails, beaches,
  outdoor markets); "evening" for bars, clubs, live music and night markets; "night" for places
  best after dark (night views, light shows); otherwise "any". Most places, including ordinary
  restaurants, cafés, museums and sights, are "any".
- reason: under 12 words, why it does or doesn't suit this traveler.
- cost: what one visitor typically spends there, in whole units of the local currency:
  the entry ticket for sights and museums, a typical meal for meals and snacks, 0 for free
  places like parks, viewpoints and churches. Use the price level as a guide where given."""
    return await _structured(prompt, ScoredPlaces)


async def estimate_visits(trip: dict, items: list[dict]) -> list[VisitEstimate]:
    """items: [{id, name, kind, reviews: [text, ...]}]"""
    prompt = f"""Traveler: {json.dumps({k: trip.get(k) for k in ("loves", "skips", "pace", "notes")}, ensure_ascii=False)}

For each place below, decide how many minutes this traveler should spend there,
from arrival to leaving (not getting there). Include all the waiting: the line to get
in or buy tickets, waiting for a table, ordering, waiting for food, paying. For example,
a restaurant with a 15 minute wait for a table needs about 45 minutes in total:
15-20 to wait, the rest to order, eat and pay. Don't undercount; a rushed plan is worse
than a few spare minutes.

Use the reviews first: look for phrases like "allow an hour", "20 minutes is enough",
"we spent two hours", and wait times like "waited 30 minutes for a table" or "long
line". Add the wait to the visit. Ignore opening hours ("open 24 hours" is not a visit
length). If reviews give a range, use the middle. If reviews disagree, lean toward the
typical visitor.

If at least one review mentions visit time: from_reviews = true, evidence = the exact
short phrases you used (copied verbatim), review_numbers = which review each came from.
Otherwise: from_reviews = false, evidence = [], review_numbers = [], and estimate
from what you know about the place.

Places:
{json.dumps(items, ensure_ascii=False)}"""
    return await _structured(prompt, list[VisitEstimate])


async def narrate_plan(facts: dict) -> str:
    prompt = f"""Write a short, friendly summary (3 to 4 sentences, plain text, no lists,
no markdown) of this day plan for the traveler. Mention how many stops, the
neighborhood blocks if there are several, when meals and any coffee break happen, any golden-hour
stop before sunset, when rain is expected if rain_forecast is set, one notable
place that was left out and why, and when and where they finish. Use only facts
from this JSON; don't invent anything.

{json.dumps(facts, ensure_ascii=False)}"""
    return await _text(prompt)


async def narrate_change(facts: dict) -> str:
    prompt = f"""Something changed during the traveler's day and the plan was re-optimized.
In 2 to 3 plain sentences (no markdown), say what changed, which stops were
dropped or added and why, what's next, and when and where they'll finish. Use only
these facts:

{json.dumps(facts, ensure_ascii=False)}"""
    return await _text(prompt)


REPLAN = types.FunctionDeclaration(
    name="replan",
    description="Re-plan the rest of the traveler's day after something changed.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "reason": types.Schema(
                type=types.Type.STRING,
                enum=["done", "rain", "late", "tired", "skip"],
                description=(
                    "done: finished the current next stop on time. "
                    "rain: bad weather, prefer indoor places. "
                    "late: running behind schedule. "
                    "tired: wants less walking. "
                    "skip: doesn't want to go to the next stop."
                ),
            ),
            "delay_minutes": types.Schema(
                type=types.Type.INTEGER,
                description="For late: how many minutes behind. Use 30 if not stated.",
            ),
        },
        required=["reason"],
    ),
)


async def interpret_event(text: str, context: dict) -> dict:
    prompt = f"""The traveler is mid-way through their day plan.
Context: {json.dumps(context, ensure_ascii=False)}
They just said: \"\"\"{text}\"\"\"
Call replan with the reason that best matches."""
    resp = await client().aio.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(function_declarations=[REPLAN])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY
                )
            ),
        ),
    )
    calls = resp.function_calls or []
    if not calls:
        raise ValueError("Gemini didn't return a replan call for that message.")
    args = dict(calls[0].args or {})
    return {"reason": args.get("reason", "late"), "delay_minutes": int(args.get("delay_minutes") or 30)}
