# Sightline

An AI agent that plans a day in a city you've never visited. Tell it how long
you have, what you like, and where you need to finish. It finds the places worth
seeing, reads reviews to decide how long to stay at each, gets real travel times,
and uses OR-Tools to pick the best set of stops and the order to visit them. When
the day changes ("it's pouring", "I'm running late"), it re-plans from where you
are.

Built for ShellHacks: the Waymo Mobility Challenge and Best Use of Gemini API.

## What each part does

| Step | Service | Code |
|---|---|---|
| Read the optional "anything else" notes into settings | Gemini (structured output) | `server/gemini.py: parse_trip()` |
| Find candidate places, hours, ratings | Places API (New) Text Search | `server/places.py: search_text()` |
| Score each place for this traveler, estimate tickets and meal prices | Gemini | `server/gemini.py: score_places()` |
| Read up to 5 reviews per place for visit length | Places API + Gemini | `get_reviews()`, `estimate_visits()` |
| Opening hours, neighborhoods, sunset | local | `places.py: opening_windows()`, `planner.py` |
| Hourly rain forecast for the day | Weather API hourly forecast | `server/weather.py: hourly()` |
| Travel time between every pair of places | Routes API Compute Route Matrix | `server/routes.py: matrix()` |
| Choose stops and order | OR-Tools vehicle routing | `server/planner.py: solve()` |
| Street and transit shapes for the map | Routes API Compute Routes | `server/routes.py: polyline()` |
| Explain the plan and the changes | Gemini | `narrate_plan()`, `narrate_change()` |
| Turn "it's pouring" into an action | Gemini function calling | `interpret_event()` |
| Map | Maps JavaScript API | `web/index.html` |

Trips can span up to seven consecutive days. Sightline avoids repeating places,
steers later days toward neighborhoods not yet visited, and accepts a separate
start and finish time for each day. Weather and opening hours are fetched for
each date independently.

API keys stay on the server. The browser only gets the Maps JavaScript key,
which you restrict to your site's URLs.

## Setup

You need Python 3.10 or newer.

1. **Install**

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Get a Gemini API key** from https://aistudio.google.com/apikey

3. **Set up Google Maps Platform** at https://console.cloud.google.com
   - Create a project and turn on billing (new accounts get free credit).
   - Enable **Places API (New)**, **Routes API**, **Weather API** and
     **Maps JavaScript API**.
   - Create a **server key** under Credentials. Under API restrictions, allow
     Places API (New), Routes API and Weather API.
   - Create a **browser key**. Allow only Maps JavaScript API and Places API
     (New) (for the "Start at" suggestions), and under
     application restrictions add the HTTP referrer `http://localhost:8000/*`
     (plus your deployed URL later).

4. **Add the keys**

   ```bash
   cp .env.example .env
   ```

   Fill in `GEMINI_API_KEY`, `GOOGLE_MAPS_API_KEY` and `GOOGLE_MAPS_BROWSER_KEY`.

5. **Run**

   ```bash
   uvicorn server.main:app --reload
   ```

   Open http://localhost:8000. The badge at the top right says whether any keys
   are missing.

## HTTP API

- `GET /api/config`: which keys are set, and the browser map key.
- `GET /api/demo`: static no-key Montreal plan for judging or screenshots.
- `POST /api/parse` `{message, city?}`: Gemini turns the optional notes into trip
  settings. The page only uses them to fill fields left blank.
- `POST /api/plan` with the trip settings (plus `start_place` when "Start at"
  came from autocomplete, and optional `notes`): streams newline-delimited JSON,
  one `step` event per stage, then a `plan` event (or an `error` event). Set
  `days` from 1 to 7 and optionally provide `day_windows` entries with
  `start_time` and `end_time` for per-day schedules.
- `POST /api/interpret` `{session_id, text}`: Gemini function call, returns
  `{reason, delay_minutes}`.
- `POST /api/replan` `{session_id, event, delay_minutes, client_time, lat, lng}`
  where event is `done`, `rain`, `late`, `tired`, `skip` or `reset`: streams
  like `/api/plan`. `client_time` (ISO 8601) and `lat`/`lng` are optional; see
  "Live day" below.

Plans are cached in memory and backed by SQLite recipes. After a restart, the
server rebuilds a requested plan with fresh API calls and replays its live-day
actions. Set `SESSION_DB_PATH` to move the database (default: `sessions.sqlite3`).

## Tuning

Constants at the top of `server/planner.py`:

- `SWITCH_POINTS`: how strongly the day sticks to one neighborhood at a time.
- `TRAVEL_POINTS_PER_MIN`: how much travel time counts against a plan.
- `WALK_CAP_KM`: longest leg that's always walked, per mode.
- `MEAL_EARLY_MIN`, `MEAL_LATE_MIN`: how long before and after each requested
  meal time a sit-down meal may start. Meals come from the trip's `meals` list, which defaults to
  lunch at 12:30 and dinner at 19:00; add breakfast, change the times, or send
  `[]` for no sit-down meals.
- `BREAK_AFTER_MIN`: how long into the day (by pace) a café becomes a coffee
  break. Only days long enough get one, and `auto_breaks: false` turns it off.
- `PACE`: how pace scales visit lengths.
- `RAIN_FACTOR`: how much a visit in forecast rain is worth, by setting.

`RAIN_MIN_PROB` in `server/weather.py` sets the chance of rain (default 50%)
from which an hour counts as rainy.

In `server/main.py`, `SHORTLIST` (default 20) sets how many places get reviews,
travel times and a spot in the solver. More places means more API calls.

## Cost and limits per planned day

Roughly 5 Text Search calls (6 when the day is long enough for a coffee break),
up to 20 Place Details calls for reviews, 2 or 3 route matrices of about 440
pairs each, about a dozen Compute Routes calls, 1 to 10 Weather API calls (one
per 24 forecast hours until the end of the trip day), and 5 Gemini calls.
Reviews and ratings are billed at higher tiers than basic place
fields, so check the Maps Platform pricing page and set a budget alert.
Transit matrices allow 100 pairs per request; `routes.matrix()` batches them.

## Things to know

- **Terms.** The Maps Platform terms limit how long you can store Places
  content and require attribution when showing it. This app keeps place data
  and reviews in memory only. Its SQLite store contains the user's original
  trip settings and action log—not Places responses—then refetches data when
  restoring a session. Reviewer names are shown on quotes, and Google Maps is
  credited under the itinerary.
- **Reviews.** Places API returns at most 5 reviews per place. When none mention
  visit time, Gemini estimates from what it knows, and the itinerary says so.
- **Weather.** The Weather API forecast starts at the current hour and covers
  10 days, so hours already past and days further out are planned as dry. Outdoor stops are steered to dry
  hours, and the "It's raining" event marks the rest of the day as rainy.
- **Live day.** When the plan is for today in the city, re-plans use the
  device's clock instead of assuming you kept to the schedule, and the browser
  sends its location (if you allow it) so the rest of the day is planned from
  where you are, using a one-row route matrix. "Finish next stop" puts you at
  that stop at the real time and only re-plans if the rest no longer fits.
  "Running late" adds its delay on top of the real clock. If you're more than
  10 minutes past a stop's planned leave time, the Live day panel offers to
  re-plan from now. Locations more than 50 km from the start are ignored.
  Plans for other days keep the simulated clock.
- **Transit** isn't available everywhere. Where there's no transit route, legs
  fall back to walking.
- **"Walk + ride"** uses driving times and distances with traffic plus 4 minutes
  for pickup. Each ride leg shows a broad planning fare range, and the comparison
  panel totals ride time/cost against transit. These are not live quotes: actual
  fares vary by route, duration, and demand. Waymo availability links to its
  published service-area list; Austin and Atlanta access is through Uber, and
  cities in gradual rollout are labeled as limited.
- **Gemini model.** If `gemini-3.8-flash` isn't available to you, set
  `GEMINI_MODEL` to a current model name.
